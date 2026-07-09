import json

import pytest

import app.session as session
from app.session import sanitize_messages, save_session

# 极小构造器:每个 case 只有几行,被测的「缺陷」一眼可见 —— 这正是单测该有的样子,
# 而不是内联一整段真实 session(缺陷会被埋没看不见)。


def _user(text="hi"):
    return {"role": "user", "content": text}


def _assistant(text="ok"):
    return {"role": "assistant", "content": text}


def _calls(*ids):
    """一条发起 tool_calls 的 assistant,ids 是它请求的 tool_call id。"""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": cid, "type": "function", "function": {"name": "noop", "arguments": "{}"}} for cid in ids],
    }


def _tool(cid):
    return {"role": "tool", "tool_call_id": cid, "content": "result"}


# --- 不该被改动的输入(全程配对良好)---

_empty = []

_plain_chat = [_user(), _assistant(), _user(), _assistant()]

_paired_single = [_user(), _calls("a"), _tool("a")]

_paired_multi = [_user(), _calls("a", "b"), _tool("a"), _tool("b")]


# --- 该被截断的输入(尾部/中间残缺)---

# 尾部孤儿:最后一组请求 b、c,只回了 b → 整组连同它前面那条悬空 user 之后全丢。
# 期望保留到 index 4(含末尾那条 user —— 只有 user 没 assistant 回复是合法的)。
_trailing_partial = [_user(), _calls("a"), _tool("a"), _user(), _calls("b", "c"), _tool("b")]
_trailing_partial_expected = _trailing_partial[:4]

# 尾部孤儿极端:assistant 刚发完 tool_calls 就崩,一条 tool 结果都没有。
_trailing_none = [_user(), _calls("a")]
_trailing_none_expected = _trailing_none[:1]

# 中间孤儿(v2 专属能力):干净轮 + 残缺组 + 后续闲聊。残缺组之后 pending 永不清空,
# safe_len 冻结在残缺组之前 → 只保留最长合法前缀。
_middle = [_user(), _calls("a"), _tool("a"), _user(), _calls("b", "c"), _tool("b"), _user(), _assistant()]
_middle_expected = _middle[:4]

# 中间孤儿 + 后面又跟一组「完整」调用 —— 专治「新组覆盖 pending」的洗白 bug。
# 第 4 组 calls(b,c) 缺 c,但第 6 组 calls(d) 配对良好。若实现用 pending={...} 直接覆盖,
# 会把悬空的 c 冲掉、safe_len 一路推到末尾 → 漏掉中间孤儿(喂 OpenAI 照样 400)。
# 正确行为:撞到第二个未闭合组就冻结,只保留到第一个孤儿之前(index 4)。
_middle_then_clean = [
    _user(),
    _calls("a"),
    _tool("a"),
    _user(),
    _calls("b", "c"),  # 孤儿:缺 c
    _tool("b"),
    _user(),
    _calls("d"),  # 后面这组是干净的,不该让它洗白前面的孤儿
    _tool("d"),
]
_middle_then_clean_expected = _middle_then_clean[:4]


CASES = [
    ("empty", _empty, _empty),
    ("plain_chat_unchanged", _plain_chat, _plain_chat),
    ("paired_single_unchanged", _paired_single, _paired_single),
    ("paired_multi_unchanged", _paired_multi, _paired_multi),
    ("trailing_orphan_partial_truncated", _trailing_partial, _trailing_partial_expected),
    ("trailing_orphan_no_results_truncated", _trailing_none, _trailing_none_expected),
    ("middle_orphan_truncated_to_prefix", _middle, _middle_expected),
    ("middle_orphan_then_clean_round_truncated", _middle_then_clean, _middle_then_clean_expected),
]


@pytest.mark.parametrize(
    "messages, expected",
    [(c[1], c[2]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_sanitize_messages(messages, expected):
    assert sanitize_messages(messages) == expected


def test_sanitize_does_not_mutate_input():
    # 纯函数应返回新列表,不改原 messages
    original = [_user(), _calls("a")]
    before = list(original)
    sanitize_messages(original)
    assert original == before


# --- save_session 原子落盘 ---


def test_save_session_writes_completely(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "SESSION_DIR", tmp_path)
    sid = save_session([_user("hello")], "model-x", "sess1")
    data = json.loads((tmp_path / f"{sid}.json").read_text(encoding="utf-8"))
    assert data["messages"][0]["content"] == "hello"
    assert list(tmp_path.glob("*.tmp")) == []  # 无临时文件残留


def test_save_session_crash_before_replace_keeps_old_file(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "SESSION_DIR", tmp_path)
    save_session([_user("v1")], "model-x", "sess1")
    path = tmp_path / "sess1.json"
    old = path.read_text(encoding="utf-8")

    # 模拟「临时文件已写完、os.replace 前崩溃」
    def boom(*args, **kwargs):
        raise RuntimeError("crash before replace")

    monkeypatch.setattr(session.os, "replace", boom)
    with pytest.raises(RuntimeError):
        save_session([_user("v2-corrupt")], "model-x", "sess1")

    # 原文件仍是旧的完整版,且没有半截临时文件残留
    assert path.read_text(encoding="utf-8") == old
    assert json.loads(path.read_text(encoding="utf-8"))["messages"][0]["content"] == "v1"
    assert list(tmp_path.glob("*.tmp")) == []
