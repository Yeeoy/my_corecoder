from app.tools import ReadFileTool


def test_read_success(tmp_path):
    tmp_file = "test.txt"
    (tmp_path / tmp_file).write_text("hello\nworld")
    read_tool = ReadFileTool(workspace_root=tmp_path)
    result = read_tool.execute(tmp_file)
    assert result.ok
    assert result.content == "1  hello\n2  world"
    assert result.error is None
    assert result.metadata.get("total_lines") == 2
    assert result.metadata["tool"] == "read_file"
    assert isinstance(result.metadata["duration_ms"], int)


def test_read_failure(tmp_path):
    tmp_file = "test.txt"
    read_tool = ReadFileTool(workspace_root=tmp_path)
    result = read_tool.execute(tmp_file)
    assert not result.ok
    assert result.content == ""
    assert "File not found" in result.error
    assert not result.metadata.get("exists")


def test_read_is_directory(tmp_path):
    read_tool = ReadFileTool()
    result = read_tool.execute(str(tmp_path))
    assert not result.ok
    assert result.content == ""
    assert "Not a file" in result.error
    assert not result.metadata.get("is_file")


def test_read_binary_file(tmp_path):
    tmp_binary_file = "tmp_binary_file"
    (tmp_path / tmp_binary_file).write_bytes(b"\xff")
    read_tool = ReadFileTool(tmp_path)
    result = read_tool.execute(tmp_binary_file)
    assert not result.ok
    assert result.content == ""
    assert "File is not valid UTF-8 text" in result.error
    assert result.metadata.get("is_binary")


def test_read_empty_file(tmp_path):
    tmp_file = "test.txt"
    (tmp_path / tmp_file).write_text("")
    read_tool = ReadFileTool(workspace_root=tmp_path)
    result = read_tool.execute(tmp_file)
    assert result.ok
    assert result.content == "(empty file)"
    assert result.error is None
    assert result.metadata.get("total_lines") == 0
