from __future__ import annotations

from pathlib import Path

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


def test_env_example_contains_all_settings_variables() -> None:
    content = Path(".env.example").read_text(encoding="utf-8")
    configured = {
        line.split("=", 1)[0]
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    expected = {field_name.upper() for field_name in Settings.model_fields}

    assert expected - configured == set()


def test_s3_asset_storage_warnings_require_bucket_and_secret() -> None:
    settings = Settings(
        asset_storage_backend="s3",
        s3_bucket="",
        s3_access_key_id="",
        s3_secret_access_key="",
    )

    warnings = settings.runtime_warnings()
    assert "ASSET_STORAGE_BACKEND=s3 但 S3_BUCKET 为空。" in warnings
    assert "ASSET_STORAGE_BACKEND=s3 但 S3 访问密钥未完整配置。" in warnings
