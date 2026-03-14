from __future__ import annotations

from app.core.settings import Settings


def test_allowed_upload_extensions_normalizes_and_deduplicates() -> None:
    settings = Settings(
        jwt_secret_key="test-secret",
        upload_allowed_exts=" PDF , txt , pdf , md ",
    )

    assert settings.allowed_upload_extensions == ("pdf", "txt", "md")


def test_allowed_upload_extensions_keeps_legacy_pdf_fallback() -> None:
    settings = Settings(jwt_secret_key="test-secret", upload_allowed_exts="pdf")

    assert settings.allowed_upload_extensions == (
        "pdf",
        "docx",
        "html",
        "htm",
        "md",
        "txt",
    )


def test_runtime_warnings_reports_default_jwt_secret() -> None:
    settings = Settings(jwt_secret_key="CHANGE_ME")

    assert "JWT_SECRET_KEY 仍为默认值，部署前必须替换。" in settings.runtime_warnings()
