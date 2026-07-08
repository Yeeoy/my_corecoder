from app.tools import EditFileTool, WriteFileTool


def test_not_found():
    edit_tool = EditFileTool()
    edit_result = edit_tool.execute("test.txt", "This is not in the file.", "This is a test.")
    assert "File not found" in edit_result.error and not edit_result.ok


def test_not_utf8_file(tmp_path):
    (tmp_path / "invalid_utf8.bin").write_bytes(b"\xff")
    edit_tool = EditFileTool(workspace_root=tmp_path)
    edit_result = edit_tool.execute("invalid_utf8.bin", "This is not in the file.", "This is a test.")
    assert "File is not a UTF-8 text file" in edit_result.error and not edit_result.ok


def test_no_occurrence(tmp_path):
    tmp_file = "test.txt"
    write_tool = WriteFileTool(workspace_root=tmp_path)
    write_result = write_tool.execute(tmp_file, "This is a test.")
    assert write_result.ok
    edit_tool = EditFileTool(workspace_root=tmp_path)
    edit_result = edit_tool.execute(tmp_file, "This is not in the file.", "This is a test.")
    assert "not found" in edit_result.error and not edit_result.ok


def test_one_occurrence(tmp_path):
    tmp_file = "test.txt"
    write_tool = WriteFileTool(workspace_root=tmp_path)
    write_result = write_tool.execute(tmp_file, "This is a bad test.")
    assert write_result.ok
    edit_tool = EditFileTool(workspace_root=tmp_path)
    edit_result = edit_tool.execute(tmp_file, "bad", "good")
    assert "Edited" in edit_result.content and edit_result.ok
    read_result = (tmp_path / tmp_file).read_text()
    assert "good" in read_result and "bad" not in read_result


def test_multiple_occurrence(tmp_path):
    tmp_file = "test.txt"
    write_tool = WriteFileTool(workspace_root=tmp_path)
    write_result = write_tool.execute(tmp_file, "This is a test and a new test.")
    assert write_result.ok
    edit_tool = EditFileTool(workspace_root=tmp_path)
    edit_result = edit_tool.execute(tmp_file, "test", "food")
    assert "appears 2 times" in edit_result.error and not edit_result.ok
