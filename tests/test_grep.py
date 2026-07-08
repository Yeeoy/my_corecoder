from app.tools import GrepTool


def test_grep_found(tmp_path):
    tmp_file = "test.txt"
    (tmp_path / tmp_file).write_text("hello\nworld\nworld")
    grep_tool = GrepTool(workspace_root=tmp_path)
    result = grep_tool.execute("world", tmp_file)
    assert result.ok
    assert result.error is None
    assert result.metadata.get("match_count") == 2
    assert result.metadata["tool"] == "grep"
    assert isinstance(result.metadata["duration_ms"], int)


def test_grep_no_matches(tmp_path):
    tmp_file = "test.txt"
    (tmp_path / tmp_file).write_text("hello\nworld\nworld")
    grep_tool = GrepTool(workspace_root=tmp_path)
    result = grep_tool.execute("universe", tmp_file)
    assert result.ok
    assert result.error is None
    assert result.content == "No matches found."
    assert result.metadata.get("match_count") == 0


def test_grep_invalid_regex(tmp_path):
    grep_tool = GrepTool(workspace_root=tmp_path)
    result = grep_tool.execute("[a", "test.txt")
    assert not result.ok
    assert "Invalid regex pattern" in result.error


def test_grep_path_not_found(tmp_path):
    grep_tool = GrepTool(workspace_root=tmp_path)
    result = grep_tool.execute("world", "test.txt")
    assert not result.ok
    assert "not found" in result.error
