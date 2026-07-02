from dataclasses import dataclass, field

from app.llm import LLM


def _approx_tokens(text: str) -> int:
    return len(text) // 3


def _estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        if m.get("content"):
            total += _approx_tokens(m["content"])
        if m.get("tool_calls"):
            total += _approx_tokens(str(m["tool_calls"]))
    return total


@dataclass
class CompressionResult:
    compressed: bool = False
    layers: list[str] = field(default_factory=list)
    before_tokens: int = 0
    after_tokens: int = 0


class ContextManager:
    def __init__(self, max_tokens: int = 120_000):
        self.max_tokens = max_tokens
        self._snip_at = int(max_tokens * 0.5)
        self._summarize_at = int(max_tokens * 0.70)
        self._collapse_at = int(max_tokens * 0.90)

    def maybe_compress(
        self,
        messages: list[dict],
        llm: LLM | None = None,
        runtime_state: str = "",
    ) -> CompressionResult:
        before_tokens = _estimate_tokens(messages)
        current = before_tokens
        layers: list[str] = []

        # Layer 1: snip verbose tool outputs
        if current > self._snip_at and self._snip_tool_outputs(messages):
            layers.append("snip_tool_outputs")
            current = _estimate_tokens(messages)

        # Layer 2: LLM-powered summarization of old turns
        if (
            current > self._summarize_at
            and len(messages) > 10
            and self._summarize_old(
                messages,
                llm,
                keep_recent=8,
                runtime_state=runtime_state,
            )
        ):
            layers.append("summarize_old")
            current = _estimate_tokens(messages)

        # Layer 3: hard collapse - last resort
        if (
            current > self._collapse_at
            and len(messages) > 4
            and self._hard_collapse(messages, llm, runtime_state=runtime_state)
        ):
            layers.append("hard_collapse")
            current = _estimate_tokens(messages)

        return CompressionResult(
            compressed=bool(layers),
            layers=layers,
            before_tokens=before_tokens,
            after_tokens=current,
        )

    @staticmethod
    def _snip_tool_outputs(messages: list[dict]) -> bool:
        changed = False

        for m in messages:
            if m.get("role") != "tool":
                continue

            content = m.get("content", "")

            # Do not snip read_file outputs.
            # Code/file content is often the core evidence for the next reasoning step.
            if content.startswith("File: ") and "\nComplete: " in content[:300]:
                continue

            if len(content) <= 1500:
                continue

            lines = content.splitlines()
            if len(lines) <= 6:
                continue

            snipped = (
                "\n".join(lines[:3])
                + f"\n...({len(lines)} lines, snipped to save context) ...\n"
                + "\n".join(lines[-3:])
            )
            m["content"] = snipped
            changed = True

        return changed

    @staticmethod
    def _safe_split(messages: list[dict], keep_recent: int) -> int:
        split = max(0, len(messages) - keep_recent)
        while split > 0 and messages[split].get("role") == "tool":
            split -= 1
        return split

    def _summarize_old(
        self,
        messages: list[dict],
        llm: LLM | None,
        keep_recent: int = 8,
        runtime_state: str = "",
    ) -> bool:
        if len(messages) <= keep_recent:
            return False

        before_snapshot = self._snapshot(messages)
        before_tokens = _estimate_tokens(messages)

        split = self._safe_split(messages, keep_recent)
        old = messages[:split]
        tail = messages[split:]

        old_tokens = _estimate_tokens(old)

        # Do not summarize tiny history. The summary wrapper may be larger than the old content.
        if len(old) < 4 or old_tokens < 2_000:
            return False

        summary = self._get_summary(old, llm)

        combined_summary = self._combine_runtime_state_and_summary(
            runtime_state=runtime_state,
            conversation_summary=summary,
        )

        messages.clear()
        messages.append(
            {
                "role": "user",
                "content": f"[Context compressed - conversation summary]\n{combined_summary}",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Got it, I have the compressed context and runtime state.",
            }
        )
        messages.extend(tail)

        after_tokens = _estimate_tokens(messages)

        # Roll back if compression did not actually reduce context.
        # Require at least 10% reduction to avoid useless churn.
        if after_tokens >= int(before_tokens * 0.90):
            messages.clear()
            messages.extend(before_snapshot)
            return False

        return True

    def _hard_collapse(
        self,
        messages: list[dict],
        llm: LLM | None,
        runtime_state: str = "",
    ) -> bool:
        before_snapshot = [dict(m) for m in messages]
        before_tokens = _estimate_tokens(messages)

        split = self._safe_split(messages, 4 if len(messages) > 4 else 2)
        tail = messages[split:]
        summary = self._get_summary(messages[:split], llm)

        combined_summary = self._combine_runtime_state_and_summary(
            runtime_state=runtime_state,
            conversation_summary=summary,
        )

        messages.clear()
        messages.append(
            {
                "role": "user",
                "content": f"[Context compressed - hard collapse]\n{combined_summary}",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Context restored. Continuing from where we left off.",
            }
        )
        messages.extend(tail)

        after_tokens = _estimate_tokens(messages)

        if after_tokens >= int(before_tokens * 0.90):
            messages.clear()
            messages.extend(before_snapshot)
            return False

        return True

    def _get_summary(self, messages: list[dict], llm: LLM | None) -> str:
        flat = self._flatten(messages)

        if llm:
            try:
                resp = llm.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Compress this conversation into a concise but useful summary.\n"
                                "Keep the summary under 800 Chinese characters "
                                "or 500 English words unless critical details require more.\n"
                                "Preserve:\n"
                                "- user goal\n"
                                "- current task state\n"
                                "- files read or edited\n"
                                "- commands run\n"
                                "- tool failures or permission denials\n"
                                "- decisions made\n"
                                "- remaining work\n\n"
                                "Drop:\n"
                                "- verbose command output\n"
                                "- long code listings\n"
                                "- redundant back-and-forth"
                            ),
                        },
                        {"role": "user", "content": flat[:15000]},
                    ],
                )
                return resp.content
            except Exception:
                pass

        return self._extract_key_info(messages)

    @staticmethod
    def _flatten(messages: list[dict]) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "?")
            text = m.get("content", "") or ""
            if text:
                parts.append(f"{role}: {text}")
        return "\n".join(parts)

    @staticmethod
    def _extract_key_info(messages: list[dict]) -> str:
        import re

        files_seen = set()
        errors = []

        for m in messages:
            text = m.get("content", "") or ""
            for match in re.finditer(r"[\w./\-]+\.\w{1,8}", text):
                files_seen.add(match.group())
            for line in text.splitlines():
                if "error" in line.lower():
                    errors.append(line.strip()[:150])

        parts = []
        if files_seen:
            parts.append(f"Files touched: {', '.join(sorted(files_seen)[:20])}")
        if errors:
            parts.append(f"Errors seen: {', '.join(errors[:5])}")

        return "\n".join(parts) or "(no extractable context)"

    @staticmethod
    def _combine_runtime_state_and_summary(runtime_state: str, conversation_summary: str) -> str:
        parts = []

        if runtime_state.strip():
            parts.append(runtime_state.strip())

        parts.append("# Conversation Summary")
        parts.append(conversation_summary.strip() or "(no conversation summary)")

        return "\n\n".join(parts)

    @staticmethod
    def _snapshot(messages: list[dict]) -> list[dict]:
        return [dict(m) for m in messages]
