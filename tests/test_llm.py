from types import SimpleNamespace

import pytest

from app.cancellation import CancellationToken
from app.llm import LLM


def _text_chunk(text):
    """造一个最小的 content chunk,字段要凑齐 chat() 访问到的那些。"""
    delta = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=delta)])


class FakeStream:
    """假 SSE 流:支持 with(上下文管理器)+ for(迭代器)。"""

    def __init__(self, chunks, token, cancel_after):
        self._chunks = chunks
        self._token = token
        self._cancel_after = cancel_after  # 产出第几个 chunk 后触发取消
        self.pulled = 0  # __next__ 被调了几次 = 实际拉了多少
        self.closed = False

    # --- 上下文管理器 ---
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, tb):
        self.closed = True
        return False  # 别吞异常,让 InterruptedError 冒出去

    # --- 迭代器 ---
    def __iter__(self):
        return self

    def __next__(self):
        if self.pulled >= len(self._chunks):
            raise StopIteration
        chunk = self._chunks[self.pulled]
        self.pulled += 1
        # TODO 1: 当 self.pulled == self._cancel_after 时,self._token.cancel()
        #         (模拟"流吐到一半,用户按了 Stop")
        if self.pulled == self._cancel_after:
            self._token.cancel()
        return chunk


def test_chat_cancel_midstream(monkeypatch):
    token = CancellationToken()
    # TODO 2: 造 10 个 content chunk,cancel_after=2(第 2 个后取消)
    chunks = [_text_chunk(f"tok{i}") for i in range(10)]
    fake = FakeStream(chunks, token, cancel_after=2)

    llm = LLM(model="x", api_key="x")  # 不会真发请求,下一行绕开了
    monkeypatch.setattr(llm, "_call_with_retry", lambda params: fake)

    # TODO 3: 三条断言
    # (a) 取消 → 抛 InterruptedError
    with pytest.raises(InterruptedError):
        llm.chat(messages=[], cancellation_token=token)

    # (b) 灵魂断言:没把 10 个 chunk 拉完 = 真提前停,不是跑完才报。
    #     推演:第 2 次 __next__ 里 pulled=2 → token.cancel(),同次返回 chunk1;
    #     for 回到循环体顶部查 cancelled=True → raise。cancel 与产出在同一次 __next__,
    #     所以不用再拉第 3 个,pulled 停在 2。
    assert fake.pulled == 2
    assert fake.pulled < 10

    # (c) with stream 退出时真的关了连接(哪怕是 raise 出去的)
    assert fake.closed is True
