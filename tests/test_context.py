from types import SimpleNamespace

import pytest

from app.context import ContextManager, _estimate_tokens


@pytest.mark.parametrize(
    "keep_recent,expected",
    [
        (3, 10 - 3),
        (4, 10 - 4 - 1),
        (7, max(0, 10 - 7 - 1 - 1 - 1 - 1)),
    ],
    ids=["normal", "tool", "all tools"],
)
def test_safe_split(keep_recent, expected):
    # Comments mark where each case's raw split (len - keep_recent) lands before back-up:
    history = [
        {"role": "tool"},
        {"role": "tool"},
        {"role": "tool"},
        {"role": "tool"},  # "all tools": keep_recent=7 → raw split=3, backs up through tools to 0
        {"role": "assistant"},
        {"role": "user"},
        {"role": "tool"},  # "tool": keep_recent=4 → raw split=6 lands on tool, backs up to 5
        {"role": "assistant"},  # "normal": keep_recent=3 → raw split=7, already non-tool, no back-up
        {"role": "user"},
        {"role": "assistant"},
    ]
    result = ContextManager._safe_split(history, keep_recent=keep_recent)
    assert result == expected
    assert result == 0 or history[result]["role"] != "tool"


@pytest.mark.parametrize(
    "content, should_snip",
    [
        ("LLM\n" * 500, True),  # 2000 chars (>1500) & 500 lines (>6) → both gates pass → snip
        ("LLM" * 1000, False),  # 3000 chars (>1500) but 1 line (<=6) → line gate blocks
        ("LLM\n" * 300, False),  # 1200 chars (<=1500) → char gate blocks
        ("LLM\n" * 6, False),  # 24 chars & exactly 6 lines (<=6) → both gates block (6 is the boundary)
    ],
    ids=["long_content", "short_content", "long_lines", "short_lines"],
)
def test_snip_tool_outputs(content, should_snip):
    """Snip fires only when a tool output clears BOTH gates: len(content) > 1500 AND len(lines) > 6."""
    history = [
        {"role": "assistant", "content": content},
        {"role": "tool", "content": content},
    ]
    assert ContextManager._snip_tool_outputs(history) == should_snip
    assert history[0].get("content") == content
    snipped = history[1]["content"] != content
    assert snipped == should_snip


# token ≈ chars/3 (_approx_tokens = len//3). ContextManager(max_tokens=100) layer thresholds:
#   _snip_at=50, _summarize_at=70, _collapse_at=90 (tokens).
# Only the snip layer needs no LLM, so these cases run with llm=None (the default).


@pytest.mark.parametrize(
    "content,expected_result",
    [
        ("LLM", {"compressed": False, "layers": []}),  # ~1 token < snip_at(50) → no layer fires
        ("x\n" * 1000, {"compressed": True, "layers": ["snip_tool_outputs"]}),  # ~1333 tokens → snip only
    ],
    ids=[
        "not_compress",
        "snip",
    ],
)
def test_maybe_compress_with_snip(content, expected_result):
    history = [
        {"role": "assistant", "content": content},
        {"role": "tool", "content": content},
    ]
    result = ContextManager(max_tokens=100).maybe_compress(messages=history)
    assert result.compressed == expected_result["compressed"]
    assert result.layers == expected_result["layers"]


class FakeLLM:
    """Test double for LLM: returns a fixed summary so tests stay deterministic and offline."""

    def __init__(self, summary_text):
        self._summary_text = summary_text

    def chat(self, messages, **kwargs):  # 签名要吃掉 messages + 任意 kwargs
        return SimpleNamespace(content=self._summary_text)


def _make_summarizable_history():
    """Build a message list that clears every gate inside _summarize_old.

    Gates (app/context.py _summarize_old):
      - len(messages) > keep_recent(8)
      - after _safe_split, the sliced `old` part: len(old) >= 4 AND
        old_tokens >= self._summarize_floor  (== max_tokens * 0.02)

    Default ContextManager(max_tokens=120000) → floor = 2400 tokens.
    12 messages: first 4 are FAT (3500 chars each ≈ 1166 tokens → ~4664 total),
    comfortably above the 2400 floor (survives a floor bump without false-red).
    keep_recent=8 → split at index 4, and messages[4] is a user turn (not tool)
    so _safe_split won't back the boundary up.
    """
    fat = "word " * 700  # 3500 chars ≈ 1166 tokens
    return [
        {"role": "user", "content": fat},
        {"role": "assistant", "content": fat},
        {"role": "user", "content": fat},
        {"role": "assistant", "content": fat},
        {"role": "user", "content": "keep 1"},  # index 4: split boundary, non-tool
        {"role": "assistant", "content": "keep 2"},
        {"role": "user", "content": "keep 3"},
        {"role": "assistant", "content": "keep 4"},
        {"role": "user", "content": "keep 5"},
        {"role": "assistant", "content": "keep 6"},
        {"role": "user", "content": "keep 7"},
        {"role": "assistant", "content": "keep 8"},
    ]


def test_summarize_old_success():
    """D1: a short summary shrinks context >10% → returns True and replaces old turns."""
    messages = _make_summarizable_history()
    before_tokens = _estimate_tokens(messages)

    fake = FakeLLM("compressed summary")  # short → result far smaller than original

    result = ContextManager()._summarize_old(messages, llm=fake, keep_recent=8)

    assert result is True
    # old turns gone, replaced by one compressed-context marker message
    assert any("[Context compressed" in (m.get("content") or "") for m in messages)
    assert _estimate_tokens(messages) < before_tokens


def test_summarize_old_rollback():
    """D2: a summary bigger than the original → no real reduction → rollback restores messages verbatim."""
    messages = _make_summarizable_history()

    before = [dict(m) for m in messages]  # deep-ish snapshot: new dicts, not just a new list

    fake = FakeLLM("bla " * 5000)  # huge → after_tokens >= before*0.90 → rollback

    result = ContextManager()._summarize_old(messages, llm=fake, keep_recent=8)

    assert result is False
    assert messages == before  # rollback restored the original list verbatim
