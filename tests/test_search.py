import time
from types import SimpleNamespace

from app.tools import SearchTool


class FakeTavily:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def search(self, query, search_depth=None):
        return {"results": []}


def test_search_has_no_fixed_delay(monkeypatch):
    # 让 API key 有值,绕过 search.py:36 的 early-return 分支
    monkeypatch.setattr(
        "app.tools.search.get_config",
        lambda: SimpleNamespace(TAVILY_API_KEY="fake-key"),
    )
    # 用立即返回的假客户端替掉真 TavilyClient(search.py:46)
    monkeypatch.setattr("app.tools.search.TavilyClient", FakeTavily)

    start = time.perf_counter()
    result = SearchTool().execute(query="anything")
    elapsed = time.perf_counter() - start

    # ok=True 证明穿过了真分支(early-return 是 ok=False),防绿在错的原因
    assert result.ok is True
    # 护栏:曾经的 time.sleep(3) 一旦复活,这里必炸
    assert elapsed < 0.5
