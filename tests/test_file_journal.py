from app.file_journal import FileJournal


def test_rollback_restores_modified_file_and_clears_journal(tmp_path):
    target_path = tmp_path / "text.txt"
    target_path.write_text("original\n", encoding="utf-8")
    file_journal = FileJournal()
    file_journal.snapshot_before_write(target_path)
    target_path.write_text("changed\n", encoding="utf-8")
    file_journal.rollback()
    assert target_path.read_text(encoding="utf-8") == "original\n"
    assert file_journal.changes() == []


def test_rollback_removes_created_file_and_clears_journal(tmp_path):
    target_path = tmp_path / "created.txt"
    assert not target_path.exists()
    file_journal = FileJournal()
    file_journal.snapshot_before_write(target_path)
    target_path.write_text("new content\n", encoding="utf-8")
    file_journal.rollback()
    assert not target_path.exists()
    assert file_journal.changes() == []


def test_multiple_mutations_keep_first_snapshot(tmp_path):
    target_path = tmp_path / "modified.txt"
    target_path.write_text("original\n", encoding="utf-8")
    file_journal = FileJournal()
    file_journal.snapshot_before_write(target_path)
    target_path.write_text("first change\n", encoding="utf-8")
    file_journal.snapshot_before_write(target_path)
    target_path.write_text("second change\n", encoding="utf-8")
    file_journal.rollback()
    assert target_path.read_text(encoding="utf-8") == "original\n"
    assert file_journal.changes() == []


def test_diff_compares_original_with_latest_content(tmp_path):
    target_path = tmp_path / "modified.txt"
    target_path.write_text("original\n", encoding="utf-8")
    journal = FileJournal()
    journal.snapshot_before_write(target_path)
    target_path.write_text("intermediate\n", encoding="utf-8")
    journal.snapshot_before_write(target_path)
    target_path.write_text("latest\n", encoding="utf-8")
    diff = journal.diff()
    assert "-original\n" in diff
    assert "+latest\n" in diff
    assert "intermediate" not in diff

    journal.snapshot_before_write(target_path)
    target_path.write_text("second change\n", encoding="utf-8")
    journal.rollback()
    assert target_path.read_text(encoding="utf-8") == "original\n"
    assert journal.changes() == []


def test_accept_keeps_current_content_and_clears_journal(tmp_path):
    target_path = tmp_path / "modified.txt"
    target_path.write_text("original\n", encoding="utf-8")
    file_journal = FileJournal()
    file_journal.snapshot_before_write(target_path)
    target_path.write_text("accepted\n", encoding="utf-8")
    assert file_journal.changes() == [(str(target_path), "modified")]
    file_journal.accept()
    assert target_path.read_text(encoding="utf-8") == "accepted\n"
    assert file_journal.changes() == []
    file_journal.rollback()
    assert target_path.read_text(encoding="utf-8") == "accepted\n"
