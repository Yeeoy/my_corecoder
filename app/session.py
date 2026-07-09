import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

SESSION_DIR = Path(__file__).resolve().parents[1] / "sessions"
_SAFE_SESSION_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_SESSION_ID_LEN = 100


def _normalize_session_id(session_id: str | None) -> str:
    if not session_id:
        return _new_session_id()

    name = session_id.strip().replace("\\", "/").split("/")[-1]
    name = _SAFE_SESSION_RE.sub("-", name).strip(".-_")
    if len(name) > _MAX_SESSION_ID_LEN:
        name = name[:_MAX_SESSION_ID_LEN].strip(".-_")
    return name or _new_session_id()


def _new_session_id() -> str:
    return f"session_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _session_path(session_id: str) -> Path:
    path = (SESSION_DIR / f"{_normalize_session_id(session_id)}.json").resolve()
    root = SESSION_DIR.resolve()
    if root != path.parent:
        raise ValueError(f"Invalid session id: {session_id}")
    return path


def save_session(messages: list[dict], model: str, session_id: str | None = None) -> str:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_id = _normalize_session_id(session_id)

    data = {
        "id": session_id,
        "model": model,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
    }

    path = _session_path(session_id)
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    return session_id


def _atomic_write_text(path: Path, text: str) -> None:
    """原子落盘:先写同目录临时文件,再 os.replace 覆盖目标。

    直接 path.write_text 会先 truncate 再写,若中途崩溃(kill/断电/磁盘满)
    会留下半截 JSON —— 正是下次 load 读到坏数据的源头。

    关键点:
    - 临时文件必须和目标在【同一目录】(同一文件系统),否则 os.replace 会退化成
      跨设备的「复制+删除」,失去原子性。所以 dir=path.parent,不能用系统 /tmp。
    - 用 os.replace 而非 os.rename:前者跨平台都是「目标存在则覆盖」,Windows 上
      os.rename 遇已存在目标会报错。
    - 出错清理临时文件,避免残留 .tmp 垃圾。
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())  # 确保数据落到磁盘,而非仅停在页缓存(防断电级丢失)
        os.replace(tmp_path, path)  # 原子:读者只会看到旧的完整版或新的完整版
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def load_session(session_id: str) -> tuple[list[dict], str] | None:
    path = _session_path(session_id)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        messages, model = data["messages"], data["model"]
        return sanitize_messages(messages), model
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def delete_session(session_id: str) -> bool:
    path = _session_path(session_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def list_sessions() -> list[dict]:
    if not SESSION_DIR.exists():
        return []

    sessions = []
    for f in sorted(SESSION_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            preview = ""
            for m in data.get("messages", []):
                if m.get("role") == "user" and m.get("content"):
                    preview = m["content"][:80]
                    break
            sessions.append(
                {
                    "id": data.get("id", f.stem),
                    "model": data.get("model", "unknown"),
                    "saved_at": data.get("saved_at", "unknown"),
                    "preview": preview,
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue

    return sessions[:20]


def sanitize_messages(messages: list[dict]) -> list[dict]:
    safe_len = 0
    pending: set[str] = set()
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            if pending:
                break
            pending = {call["id"] for call in msg["tool_calls"]}
        elif msg.get("role") == "tool":
            pending.discard(msg.get("tool_call_id"))
        if not pending:
            safe_len = i + 1
    return list(messages[:safe_len])
