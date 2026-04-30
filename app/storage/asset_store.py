"""图片资产对象存储适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings


@dataclass(slots=True)
class StoredAsset:
    """已读取的图片资产内容。"""

    content: bytes
    media_type: str
    file_name: str


class AssetObjectStore:
    """管理图片资产在 S3/MinIO 中的读写。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None

    @property
    def enabled(self) -> bool:
        """判断是否启用对象存储。"""

        return self._settings.asset_storage_backend == "s3"

    def put_asset(
        self,
        asset_id: str,
        file_name: str,
        media_type: str,
        content: bytes,
    ) -> None:
        """将图片资产写入对象存储；本地后端不执行远端写入。"""

        if not self.enabled:
            return
        key = self._asset_key(asset_id, Path(file_name).suffix.lower())
        try:
            self._s3_client().put_object(
                Bucket=self._settings.s3_bucket,
                Key=key,
                Body=content,
                ContentType=media_type,
                Metadata={"asset-id": asset_id},
            )
        except Exception as exc:
            raise AppError(
                code=ErrorCode.INGEST_PARSE_FAILED,
                message="图片资产写入对象存储失败",
                detail={"asset_id": asset_id, "storage_backend": "s3", "error": str(exc)},
                status_code=503,
            ) from exc

    def get_asset(self, asset_id: str) -> StoredAsset | None:
        """按资产 ID 从对象存储读取图片内容。"""

        if not self.enabled:
            return None
        key = self._find_asset_key(asset_id)
        if key is None:
            return None
        try:
            response = self._s3_client().get_object(
                Bucket=self._settings.s3_bucket,
                Key=key,
            )
            content = response["Body"].read()
            media_type = response.get("ContentType") or _guess_media_type(Path(key).suffix)
            return StoredAsset(
                content=content,
                media_type=media_type,
                file_name=Path(key).name,
            )
        except Exception as exc:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="图片资产读取失败",
                detail={"asset_id": asset_id, "storage_backend": "s3", "error": str(exc)},
                status_code=404,
            ) from exc

    def _find_asset_key(self, asset_id: str) -> str | None:
        """通过固定前缀查找资产对象 Key。"""

        prefix = self._asset_key_prefix(asset_id)
        response = self._s3_client().list_objects_v2(
            Bucket=self._settings.s3_bucket,
            Prefix=prefix,
            MaxKeys=1,
        )
        contents = response.get("Contents") or []
        if not contents:
            return None
        key = contents[0].get("Key")
        return str(key) if key else None

    def _s3_client(self) -> Any:
        """延迟创建 S3 客户端，避免本地模式强依赖 boto3。"""

        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="已启用 S3 图片存储，但缺少 boto3 依赖",
                detail={"storage_backend": "s3"},
                status_code=500,
            ) from exc

        addressing_style = "path" if self._settings.s3_force_path_style else "auto"
        self._client = boto3.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            aws_access_key_id=self._settings.s3_access_key_id,
            aws_secret_access_key=self._settings.s3_secret_access_key,
            region_name=self._settings.s3_region,
            use_ssl=self._settings.s3_use_ssl,
            config=Config(s3={"addressing_style": addressing_style}),
        )
        return self._client

    def _asset_key(self, asset_id: str, suffix: str) -> str:
        """生成资产对象 Key，使用 asset_id 保证可由接口反查。"""

        normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        return f"{self._asset_key_prefix(asset_id)}{normalized_suffix}"

    def _asset_key_prefix(self, asset_id: str) -> str:
        """生成资产对象 Key 前缀。"""

        prefix = self._settings.s3_prefix.strip("/")
        if prefix:
            return f"{prefix}/assets/{asset_id}"
        return f"assets/{asset_id}"


def _guess_media_type(suffix: str) -> str:
    """按文件后缀推断图片媒体类型。"""

    normalized = suffix.lower()
    if normalized in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if normalized == ".png":
        return "image/png"
    if normalized == ".gif":
        return "image/gif"
    return "application/octet-stream"
