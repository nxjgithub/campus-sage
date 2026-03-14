from __future__ import annotations

from pathlib import Path

from scripts.bootstrap_demo_academic_kb import (
    is_terminal_job_status,
    list_corpus_files,
)


def test_list_corpus_files_filters_and_sorts_supported_files(tmp_path: Path) -> None:
    (tmp_path / "b.md").write_text("# b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "ignore.json").write_text("{}", encoding="utf-8")

    files = list_corpus_files(tmp_path)

    assert [item.name for item in files] == ["a.txt", "b.md"]


def test_is_terminal_job_status_matches_expected_values() -> None:
    assert is_terminal_job_status("completed") is True
    assert is_terminal_job_status("succeeded") is True
    assert is_terminal_job_status("failed") is True
    assert is_terminal_job_status("canceled") is True
    assert is_terminal_job_status("queued") is False
