from pathlib import Path


def test_api_spec_is_present() -> None:
    content = Path("docs/API_SPEC.md").read_text(encoding="utf-8")
    assert "# API_SPEC.md" in content
    assert "/api/v1" in content
    assert "RAG_CONTRACT.md" in content
