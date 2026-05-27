from __future__ import annotations

import base64
from pathlib import Path

from app.core.settings import Settings
from app.ingest.staged import StagedAsset, StagedDocumentService, StagedPreviewBlock


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
)


def test_preview_chunks_group_adjacent_text_blocks(tmp_path: Path) -> None:
    """连续预览段落应先合并再切分，避免段落级小块污染入库。"""

    service = _build_service(tmp_path)
    blocks = [
        StagedPreviewBlock(block_type="paragraph", order_index=0, text="第一段说明。"),
        StagedPreviewBlock(block_type="paragraph", order_index=1, text="第二段说明。"),
        StagedPreviewBlock(block_type="paragraph", order_index=2, text="第三段说明。"),
    ]

    chunks = service._build_preview_ordered_chunks(blocks, [])

    assert len(chunks) == 1
    assert "第一段说明" in chunks[0].text
    assert "第二段说明" in chunks[0].text
    assert "第三段说明" in chunks[0].text


def test_preview_chunks_attach_image_after_buffered_text(tmp_path: Path) -> None:
    """图片前的连续正文应保持为同一语义块，并绑定后续图片资产。"""

    service = _build_service(tmp_path)
    asset = StagedAsset(
        asset_id="asset_1",
        label="图 1",
        file_name="image1.png",
        media_type="image/png",
        relative_path="assets/asset_1.png",
        url="/api/v1/assets/asset_1",
        order_index=1,
        source="docx",
    )
    blocks = [
        StagedPreviewBlock(block_type="paragraph", order_index=0, text="第一段说明。"),
        StagedPreviewBlock(block_type="paragraph", order_index=1, text="第二段说明。"),
        StagedPreviewBlock(
            block_type="image",
            order_index=2,
            asset_id="asset_1",
            asset_label="图 1",
            asset_url="/api/v1/assets/asset_1",
        ),
        StagedPreviewBlock(block_type="paragraph", order_index=3, text="第三段说明。"),
    ]

    chunks = service._build_preview_ordered_chunks(blocks, [asset])

    assert len(chunks) == 2
    assert "第一段说明" in chunks[0].text
    assert "第二段说明" in chunks[0].text
    assert chunks[0].assets is not None
    assert chunks[0].assets[0]["asset_id"] == "asset_1"
    assert "第三段说明" in chunks[1].text


def test_extract_pdf_assets_converts_unsupported_image_to_png(
    monkeypatch, tmp_path: Path
) -> None:
    """PDF 中浏览器支持不稳定的图片格式应转成 PNG 资产。"""

    service = _build_service(tmp_path)
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    class FakeImageObject:
        mode = "RGBA"

        def save(self, buffer, format: str) -> None:
            assert format == "PNG"
            buffer.write(_PNG_BYTES)

    class FakePdfImage:
        name = "Screen.jp2"
        data = b"not-a-supported-browser-image"
        image = FakeImageObject()

    class FakePage:
        images = [FakePdfImage()]

    class FakeReader:
        pages = [FakePage()]

    monkeypatch.setattr(service, "_load_pdf_reader", lambda _path: FakeReader())

    assets = service._extract_pdf_assets("stg_pdf", pdf_path)

    assert len(assets) == 1
    assert assets[0].file_name == "page1_Screen.png"
    assert assets[0].media_type == "image/png"
    assert assets[0].page_number == 1
    stored = service.get_asset(assets[0].asset_id)
    assert stored.content == _PNG_BYTES


def _build_service(tmp_path: Path) -> StagedDocumentService:
    """构造使用临时目录的暂存服务。"""

    settings = Settings(
        storage_dir=str(tmp_path),
        asset_storage_backend="local",
        chunk_size=500,
        chunk_overlap=100,
    )
    return StagedDocumentService(settings)
