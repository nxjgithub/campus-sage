from __future__ import annotations

from app.core.settings import Settings


def test_allowed_upload_extensions_normalizes_and_deduplicates() -> None:
    settings = Settings(
        jwt_secret_key="test-secret-key-with-32-bytes-minimum!!",
        upload_allowed_exts=" PDF , txt , pdf , md ",
    )

    assert settings.allowed_upload_extensions == ("pdf", "txt", "md")


def test_allowed_upload_extensions_keeps_legacy_pdf_fallback() -> None:
    settings = Settings(
        jwt_secret_key="test-secret-key-with-32-bytes-minimum!!",
        upload_allowed_exts="pdf",
    )

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


def test_runtime_warnings_reports_weak_jwt_secret() -> None:
    settings = Settings(jwt_secret_key="short-secret")

    assert "JWT_SECRET_KEY 长度过短，建议至少 32 个字符。" in settings.runtime_warnings()


def test_runtime_errors_blocks_default_jwt_secret_in_prod() -> None:
    settings = Settings(app_env="prod", jwt_secret_key="CHANGE_ME")

    assert settings.runtime_errors() == ["生产环境禁止使用默认 JWT_SECRET_KEY。"]


def test_runtime_errors_blocks_weak_jwt_secret_in_prod() -> None:
    settings = Settings(app_env="prod", jwt_secret_key="short-secret")

    assert settings.runtime_errors() == ["生产环境要求 JWT_SECRET_KEY 至少 32 个字符。"]
