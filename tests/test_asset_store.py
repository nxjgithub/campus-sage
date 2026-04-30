from __future__ import annotations

import io

from app.core.settings import Settings
from app.storage.asset_store import AssetObjectStore


def test_s3_asset_store_puts_and_reads_by_asset_id_prefix() -> None:
    settings = Settings(
        asset_storage_backend="s3",
        s3_bucket="assets",
        s3_prefix="campus-sage-test",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
    )
    store = AssetObjectStore(settings)
    store._client = _FakeS3Client()  # noqa: SLF001

    store.put_asset(
        asset_id="asset_demo",
        file_name="asset_demo.jpeg",
        media_type="image/jpeg",
        content=b"\xff\xd8demo\xff\xd9",
    )
    stored = store.get_asset("asset_demo")

    assert stored is not None
    assert stored.content == b"\xff\xd8demo\xff\xd9"
    assert stored.media_type == "image/jpeg"
    assert stored.file_name == "asset_demo.jpeg"


class _FakeS3Client:
    """模拟最小 S3 行为，避免单元测试依赖真实 MinIO。"""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_object(
        self,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        Metadata: dict[str, str],
    ) -> None:
        del Bucket, Metadata
        self.objects[Key] = (Body, ContentType)

    def list_objects_v2(self, Bucket: str, Prefix: str, MaxKeys: int) -> dict[str, object]:
        del Bucket, MaxKeys
        keys = [key for key in self.objects if key.startswith(Prefix)]
        return {"Contents": [{"Key": keys[0]}]} if keys else {}

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        del Bucket
        content, media_type = self.objects[Key]
        return {"Body": io.BytesIO(content), "ContentType": media_type}
