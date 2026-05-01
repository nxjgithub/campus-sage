"""暂存文档预览服务。"""

from __future__ import annotations

import binascii
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo
import zlib

from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.core.utils import new_id, utc_now_iso
from app.ingest.chunker import Chunk, Chunker
from app.ingest.parser import DocumentParser, ParsedPage
from app.storage.asset_store import AssetObjectStore, StoredAsset

_REL_NS = {
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@dataclass(slots=True)
class StagedAsset:
    """暂存文档中的图片资产。"""

    asset_id: str
    label: str
    file_name: str
    media_type: str
    relative_path: str
    url: str
    order_index: int
    source: str


@dataclass(slots=True)
class StagedAssetRef:
    """文本分块关联的图片资产引用。"""

    asset_id: str
    asset_label: str
    asset_url: str
    media_type: str
    file_name: str


@dataclass(slots=True)
class StagedChunk:
    """预览阶段可编辑/禁用的分块。"""

    chunk_id: str
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    enabled: bool
    source_kind: str
    asset_id: str | None = None
    asset_label: str | None = None
    asset_url: str | None = None
    assets: list[dict[str, str]] | None = None


@dataclass(slots=True)
class StagedPreviewBlock:
    """预览阶段用于还原原文档版式的结构块。"""

    block_type: str
    order_index: int
    text: str | None = None
    level: int | None = None
    rows: list[list[str]] | None = None
    page_number: int | None = None
    section_path: str | None = None
    asset_id: str | None = None
    asset_label: str | None = None
    asset_url: str | None = None


class StagedDocumentService:
    """管理暂存上传、解析预览和预览结果。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._parser = DocumentParser()
        self._chunker = Chunker(settings.chunk_size, settings.chunk_overlap)
        self._asset_store = AssetObjectStore(settings)

    def create_staged_document(
        self,
        kb_id: str,
        filename: str | None,
        doc_name: str | None,
        doc_version: str | None,
        published_at: str | None,
        source_uri: str | None,
    ) -> dict[str, Any]:
        """创建暂存记录，文件内容由路由层随后写入。"""

        name = doc_name or filename or "document"
        extension = Path(filename or name).suffix.lower().lstrip(".")
        if extension not in set(self._settings.allowed_upload_extensions):
            raise AppError(
                code=ErrorCode.FILE_TYPE_NOT_ALLOWED,
                message="文件类型不允许",
                detail={"ext": extension},
                status_code=400,
            )
        staged_doc_id = new_id("stg")
        root = self._staged_root(staged_doc_id)
        root.mkdir(parents=True, exist_ok=False)
        original_path = root / f"source.{extension}"
        manifest = {
            "staged_doc_id": staged_doc_id,
            "kb_id": kb_id,
            "doc_name": name,
            "doc_version": doc_version,
            "published_at": published_at,
            "source_uri": self._normalize_source_uri(source_uri),
            "filename": filename or name,
            "extension": extension,
            "source_type": self._resolve_source_type(extension),
            "status": "uploaded",
            "file_path": str(original_path),
            "assets": [],
            "pages": [],
            "preview_blocks": [],
            "chunks": [],
            "warnings": [],
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        self._write_manifest(staged_doc_id, manifest)
        return manifest

    def get_upload_path(self, staged_doc_id: str) -> Path:
        """返回暂存源文件路径。"""

        return Path(self.get_manifest(staged_doc_id)["file_path"])

    def build_preview(self, staged_doc_id: str) -> dict[str, Any]:
        """解析暂存文件并生成可预览的页面、图片与分块。"""

        manifest = self.get_manifest(staged_doc_id)
        file_path = Path(manifest["file_path"])
        if not file_path.exists():
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="暂存文件不存在",
                detail={"staged_doc_id": staged_doc_id},
                status_code=404,
            )

        assets = self._extract_assets(staged_doc_id, file_path)
        pages: list[ParsedPage] = []
        warnings: list[str] = []
        try:
            pages = self._parser.parse(file_path)
        except AppError as exc:
            if assets:
                warnings.append(f"未提取到正文文本，仅发现 {len(assets)} 个图片资产")
            else:
                raise exc

        preview_blocks = self._build_preview_blocks(file_path, pages, assets)
        chunks = self._build_staged_chunks(pages, assets, preview_blocks)
        if assets:
            warnings.append("图片已作为原始资产保存；未配置 OCR 时只能按图片编号引用")
        if not chunks:
            warnings.append("当前预览无可入库文本分块，确认入库前需要补充 OCR 或正文")

        manifest.update(
            {
                "status": "previewed",
                "assets": [asdict(asset) for asset in assets],
                "pages": [
                    {
                        "page_number": page.page_number,
                        "text": page.text,
                        "section_path": page.section_path,
                    }
                    for page in pages
                ],
                "preview_blocks": [asdict(block) for block in preview_blocks],
                "chunks": [asdict(chunk) for chunk in chunks],
                "warnings": warnings,
                "updated_at": utc_now_iso(),
            }
        )
        self._write_manifest(staged_doc_id, manifest)
        return manifest

    def get_manifest(self, staged_doc_id: str) -> dict[str, Any]:
        """读取暂存 manifest。"""

        path = self._manifest_path(staged_doc_id)
        if not path.exists():
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="暂存文档不存在",
                detail={"staged_doc_id": staged_doc_id},
                status_code=404,
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def update_chunk(
        self,
        staged_doc_id: str,
        chunk_id: str,
        enabled: bool | None,
        text: str | None,
    ) -> dict[str, Any]:
        """更新暂存分块的启用状态或文本。"""

        manifest = self.get_manifest(staged_doc_id)
        updated = False
        for chunk in manifest.get("chunks", []):
            if chunk.get("chunk_id") != chunk_id:
                continue
            if enabled is not None:
                chunk["enabled"] = enabled
            if text is not None:
                normalized = text.strip()
                if not normalized:
                    raise AppError(
                        code=ErrorCode.VALIDATION_FAILED,
                        message="分块文本不能为空",
                        detail={"chunk_id": chunk_id},
                        status_code=400,
                    )
                chunk["text"] = normalized
            updated = True
            break
        if not updated:
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="暂存分块不存在",
                detail={"staged_doc_id": staged_doc_id, "chunk_id": chunk_id},
                status_code=404,
            )
        manifest["updated_at"] = utc_now_iso()
        self._write_manifest(staged_doc_id, manifest)
        return manifest

    def enabled_chunks(self, staged_doc_id: str) -> list[Chunk]:
        """把启用的暂存分块转换为入库分块。"""

        manifest = self.get_manifest(staged_doc_id)
        chunks: list[Chunk] = []
        for fallback_index, item in enumerate(manifest.get("chunks", [])):
            if not item.get("enabled", True):
                continue
            metadata = {
                "source_kind": item.get("source_kind", "text"),
            }
            for key in ("asset_id", "asset_label", "asset_url"):
                if item.get(key):
                    metadata[key] = item[key]
            if item.get("asset_id"):
                metadata["asset_type"] = "image"
            attached_assets = self._normalize_chunk_assets(item.get("assets"))
            if attached_assets:
                metadata["assets"] = attached_assets
                first_asset = attached_assets[0]
                metadata.setdefault("asset_id", first_asset["asset_id"])
                metadata.setdefault("asset_label", first_asset["asset_label"])
                metadata.setdefault("asset_url", first_asset["asset_url"])
                metadata.setdefault("asset_type", "image")
            chunks.append(
                Chunk(
                    chunk_index=int(item.get("chunk_index", fallback_index)),
                    text=str(item.get("text", "")).strip(),
                    page_start=item.get("page_start"),
                    page_end=item.get("page_end"),
                    section_path=item.get("section_path"),
                    metadata=metadata,
                )
            )
        return chunks

    def copy_to_document_storage(self, staged_doc_id: str, target_file: Path) -> None:
        """把暂存源文件和资产复制到正式文档目录，并同步对象存储。"""

        manifest = self.get_manifest(staged_doc_id)
        source = Path(manifest["file_path"])
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_file)
        asset_target = target_file.parent / target_file.stem / "assets"
        for asset in manifest.get("assets", []):
            staged_asset = self._staged_root(staged_doc_id) / asset["relative_path"]
            if not staged_asset.exists():
                continue
            asset_target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_asset, asset_target / staged_asset.name)
            self._asset_store.put_asset(
                asset_id=str(asset["asset_id"]),
                file_name=str(staged_asset.name),
                media_type=str(asset.get("media_type") or self._guess_media_type(staged_asset.suffix)),
                content=staged_asset.read_bytes(),
            )

    def get_asset(self, asset_id: str) -> StoredAsset:
        """按资产 ID 读取图片内容，优先读取对象存储，兼容本地旧资产。"""

        stored = self._asset_store.get_asset(asset_id)
        if stored is not None:
            if self._is_valid_image_bytes(stored.content, stored.media_type):
                return stored
            raise AppError(
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="图片资产格式不合法",
                detail={"asset_id": asset_id},
                status_code=404,
            )
        path = self.find_asset_path(asset_id)
        content = path.read_bytes()
        media_type = self._guess_media_type(path.suffix)
        return StoredAsset(content=content, media_type=media_type, file_name=path.name)

    def find_asset_path(self, asset_id: str) -> Path:
        """按资产 ID 查找图片文件。"""

        storage_root = Path(self._settings.storage_dir).resolve()
        matches = list(storage_root.rglob(f"{asset_id}.*"))
        for match in matches:
            resolved = match.resolve()
            if (
                storage_root in resolved.parents
                and resolved.is_file()
                and self._is_valid_image_bytes(resolved.read_bytes(), self._guess_media_type(resolved.suffix))
            ):
                return resolved
        raise AppError(
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="图片资产不存在",
            detail={"asset_id": asset_id},
            status_code=404,
        )

    def _build_staged_chunks(
        self,
        pages: list[ParsedPage],
        assets: list[StagedAsset],
        preview_blocks: list[StagedPreviewBlock] | None = None,
    ) -> list[StagedChunk]:
        """构造文本分块，并为图片生成可引用的资产分块。"""

        if preview_blocks:
            preview_chunks = self._build_preview_ordered_chunks(preview_blocks, assets)
            if preview_chunks:
                return preview_chunks

        chunks: list[StagedChunk] = []
        for chunk in self._chunker.build(pages):
            chunks.append(
                StagedChunk(
                    chunk_id=new_id("pchunk"),
                    chunk_index=len(chunks),
                    text=chunk.text,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_path=chunk.section_path,
                    enabled=True,
                    source_kind="text",
                )
            )
        for asset in assets:
            chunks.append(
                StagedChunk(
                    chunk_id=new_id("pchunk"),
                    chunk_index=len(chunks),
                    text=(
                        f"{asset.label}：文档内嵌图片 {asset.file_name}。"
                        "该图片作为原始视觉证据保存，需查看原图确认具体内容。"
                    ),
                    page_start=None,
                    page_end=None,
                    section_path="图片资产",
                    enabled=True,
                    source_kind="image_asset",
                    asset_id=asset.asset_id,
                    asset_label=asset.label,
                    asset_url=asset.url,
                    assets=[asdict(self._asset_ref(asset))],
                )
            )
        return chunks

    def _build_preview_ordered_chunks(
        self,
        preview_blocks: list[StagedPreviewBlock],
        assets: list[StagedAsset],
    ) -> list[StagedChunk]:
        """按预览结构建立文本分块与邻近图片的引用关系。"""

        asset_by_id = {asset.asset_id: asset for asset in assets}
        chunks: list[StagedChunk] = []
        pending_assets: list[dict[str, str]] = []
        current_heading: str | None = None

        for block in preview_blocks:
            if block.block_type == "heading" and block.text:
                current_heading = block.text.strip() or current_heading
            if block.block_type in {"heading", "paragraph", "table"}:
                text = self._preview_block_text(block)
                if text:
                    block_chunks = self._split_preview_block_text(
                        text=text,
                        section_path=block.section_path or current_heading,
                        pending_assets=pending_assets,
                        start_index=len(chunks),
                    )
                    chunks.extend(block_chunks)
                    pending_assets = []
                continue
            if block.block_type == "image" and block.asset_id:
                asset = asset_by_id.get(block.asset_id)
                if asset is None:
                    continue
                asset_ref = asdict(self._asset_ref(asset))
                if chunks:
                    self._append_asset_to_chunk(chunks[-1], asset_ref)
                else:
                    pending_assets.append(asset_ref)

        if pending_assets:
            chunks.extend(self._image_asset_chunks(pending_assets, len(chunks)))
        return chunks

    def _split_preview_block_text(
        self,
        text: str,
        section_path: str | None,
        pending_assets: list[dict[str, str]],
        start_index: int,
    ) -> list[StagedChunk]:
        """切分单个预览文本块，并把前置图片绑定到首个文本分块。"""

        parsed_chunks = self._chunker.build(
            [ParsedPage(page_number=None, text=text, section_path=section_path)]
        )
        result: list[StagedChunk] = []
        for offset, chunk in enumerate(parsed_chunks):
            attached_assets = pending_assets if offset == 0 and pending_assets else None
            result.append(
                StagedChunk(
                    chunk_id=new_id("pchunk"),
                    chunk_index=start_index + offset,
                    text=chunk.text,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_path=chunk.section_path,
                    enabled=True,
                    source_kind="text",
                    assets=attached_assets,
                    asset_id=attached_assets[0]["asset_id"] if attached_assets else None,
                    asset_label=(
                        attached_assets[0]["asset_label"] if attached_assets else None
                    ),
                    asset_url=attached_assets[0]["asset_url"] if attached_assets else None,
                )
            )
        return result

    def _image_asset_chunks(
        self, asset_refs: list[dict[str, str]], start_index: int
    ) -> list[StagedChunk]:
        """为没有邻近正文的图片生成兜底分块。"""

        chunks: list[StagedChunk] = []
        for asset_ref in asset_refs:
            chunks.append(
                StagedChunk(
                    chunk_id=new_id("pchunk"),
                    chunk_index=start_index + len(chunks),
                    text=(
                        f"{asset_ref['asset_label']}：文档内嵌图片 {asset_ref['file_name']}。"
                        "该图片作为原始视觉证据保存，需查看原图确认具体内容。"
                    ),
                    page_start=None,
                    page_end=None,
                    section_path="图片资产",
                    enabled=True,
                    source_kind="image_asset",
                    asset_id=asset_ref["asset_id"],
                    asset_label=asset_ref["asset_label"],
                    asset_url=asset_ref["asset_url"],
                    assets=[asset_ref],
                )
            )
        return chunks

    def _append_asset_to_chunk(self, chunk: StagedChunk, asset_ref: dict[str, str]) -> None:
        """把图片引用追加到已存在的文本分块。"""

        existing = list(chunk.assets or [])
        if any(item.get("asset_id") == asset_ref["asset_id"] for item in existing):
            return
        existing.append(asset_ref)
        chunk.assets = existing
        chunk.asset_id = chunk.asset_id or asset_ref["asset_id"]
        chunk.asset_label = chunk.asset_label or asset_ref["asset_label"]
        chunk.asset_url = chunk.asset_url or asset_ref["asset_url"]

    def _preview_block_text(self, block: StagedPreviewBlock) -> str:
        """把预览结构块转换为可向量化的文本。"""

        if block.block_type in {"heading", "paragraph"}:
            return (block.text or "").strip()
        if block.block_type == "table" and block.rows:
            return "\n".join(" | ".join(cell.strip() for cell in row) for row in block.rows)
        return ""

    def _asset_ref(self, asset: StagedAsset) -> StagedAssetRef:
        """构造文本分块内的图片引用快照。"""

        return StagedAssetRef(
            asset_id=asset.asset_id,
            asset_label=asset.label,
            asset_url=asset.url,
            media_type=asset.media_type,
            file_name=asset.file_name,
        )

    def _normalize_chunk_assets(self, value: object) -> list[dict[str, str]]:
        """归一化暂存 manifest 中的图片引用列表。"""

        if not isinstance(value, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            asset_id = item.get("asset_id")
            asset_url = item.get("asset_url")
            if not isinstance(asset_id, str) or not isinstance(asset_url, str):
                continue
            normalized.append(
                {
                    "asset_id": asset_id,
                    "asset_label": str(item.get("asset_label") or item.get("label") or "图片"),
                    "asset_url": asset_url,
                    "media_type": str(item.get("media_type") or "image/jpeg"),
                    "file_name": str(item.get("file_name") or asset_id),
                }
            )
        return normalized

    def _build_preview_blocks(
        self,
        file_path: Path,
        pages: list[ParsedPage],
        assets: list[StagedAsset],
    ) -> list[StagedPreviewBlock]:
        """生成用于前端预览的结构块，尽量保持原文档阅读顺序。"""

        if file_path.suffix.lower() == ".docx":
            blocks = self._build_docx_preview_blocks(file_path, assets)
            if blocks:
                return blocks
        return self._build_text_preview_blocks(pages)

    def _build_docx_preview_blocks(
        self, file_path: Path, assets: list[StagedAsset]
    ) -> list[StagedPreviewBlock]:
        """解析 DOCX 的段落、表格和图片顺序，用于预览还原。"""

        try:
            with ZipFile(file_path) as archive:
                rels = self._read_docx_relationships(archive)
                document_xml = archive.read("word/document.xml")
        except (BadZipFile, KeyError):
            return []
        try:
            root = ET.fromstring(document_xml)
        except ET.ParseError:
            return []
        body = root.find(".//w:body", {"w": _WORD_NS})
        if body is None:
            return []

        asset_by_name = {asset.file_name: asset for asset in assets}
        blocks: list[StagedPreviewBlock] = []
        for child in body:
            if child.tag == self._word_tag("p"):
                text = self._extract_docx_preview_paragraph_text(child)
                level = self._extract_docx_heading_level(child)
                if text:
                    blocks.append(
                        StagedPreviewBlock(
                            block_type="heading" if level else "paragraph",
                            order_index=len(blocks),
                            text=text,
                            level=level,
                        )
                    )
                for target in self._extract_docx_paragraph_image_targets(child, rels):
                    asset = asset_by_name.get(Path(target).name)
                    if asset is None:
                        continue
                    blocks.append(
                        StagedPreviewBlock(
                            block_type="image",
                            order_index=len(blocks),
                            asset_id=asset.asset_id,
                            asset_label=asset.label,
                            asset_url=asset.url,
                            text=asset.file_name,
                        )
                    )
                continue
            if child.tag == self._word_tag("tbl"):
                rows = self._extract_docx_preview_table_rows(child)
                if rows:
                    blocks.append(
                        StagedPreviewBlock(
                            block_type="table",
                            order_index=len(blocks),
                            rows=rows,
                        )
                    )
        return blocks

    def _build_text_preview_blocks(self, pages: list[ParsedPage]) -> list[StagedPreviewBlock]:
        """将普通解析页转换为文档式预览块。"""

        blocks: list[StagedPreviewBlock] = []
        for page in pages:
            pending_rows: list[list[str]] = []
            for raw_line in page.text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if " | " in line:
                    pending_rows.append([cell.strip() for cell in line.split("|")])
                    continue
                if pending_rows:
                    blocks.append(
                        StagedPreviewBlock(
                            block_type="table",
                            order_index=len(blocks),
                            rows=pending_rows,
                            page_number=page.page_number,
                            section_path=page.section_path,
                        )
                    )
                    pending_rows = []
                block_type = "heading" if self._is_preview_heading(line) else "paragraph"
                blocks.append(
                    StagedPreviewBlock(
                        block_type=block_type,
                        order_index=len(blocks),
                        text=line,
                        level=2 if block_type == "heading" else None,
                        page_number=page.page_number,
                        section_path=page.section_path,
                    )
                )
            if pending_rows:
                blocks.append(
                    StagedPreviewBlock(
                        block_type="table",
                        order_index=len(blocks),
                        rows=pending_rows,
                        page_number=page.page_number,
                        section_path=page.section_path,
                    )
                )
        return blocks

    def _extract_assets(self, staged_doc_id: str, file_path: Path) -> list[StagedAsset]:
        """抽取 DOCX 内嵌图片资产。"""

        if file_path.suffix.lower() != ".docx":
            return []
        try:
            with ZipFile(file_path) as archive:
                rels = self._read_docx_relationships(archive)
                ordered_targets = self._read_docx_image_targets(archive, rels)
                if not ordered_targets:
                    ordered_targets = sorted(
                        entry.filename
                        for entry in archive.infolist()
                        if entry.filename.startswith("word/media/")
                    )
                assets: list[StagedAsset] = []
                asset_dir = self._staged_root(staged_doc_id) / "assets"
                asset_dir.mkdir(parents=True, exist_ok=True)
                seen: set[str] = set()
                for order_index, target in enumerate(ordered_targets, start=1):
                    if target in seen:
                        continue
                    seen.add(target)
                    data = self._read_zip_member_bytes(archive, target)
                    if data is None:
                        continue
                    source_name = Path(target).name
                    suffix = Path(source_name).suffix.lower() or ".bin"
                    media_type = self._guess_media_type(suffix)
                    if not self._is_valid_image_bytes(data, media_type):
                        continue
                    asset_id = new_id("asset")
                    file_name = f"{asset_id}{suffix}"
                    relative_path = f"assets/{file_name}"
                    (asset_dir / file_name).write_bytes(data)
                    self._asset_store.put_asset(
                        asset_id=asset_id,
                        file_name=file_name,
                        media_type=media_type,
                        content=data,
                    )
                    assets.append(
                        StagedAsset(
                            asset_id=asset_id,
                            label=f"图 {len(assets) + 1}",
                            file_name=source_name,
                            media_type=media_type,
                            relative_path=relative_path,
                            url=f"/api/v1/assets/{asset_id}",
                            order_index=order_index,
                            source="docx",
                        )
                    )
                return assets
        except (BadZipFile, KeyError, ET.ParseError):
            return []

    def _read_docx_relationships(self, archive: ZipFile) -> dict[str, str]:
        """读取 DOCX relationship，建立 rId 到媒体文件的映射。"""

        try:
            rels_xml = archive.read("word/_rels/document.xml.rels")
        except KeyError:
            return {}
        root = ET.fromstring(rels_xml)
        rels: dict[str, str] = {}
        for node in root.findall("rel:Relationship", _REL_NS):
            rel_id = node.attrib.get("Id")
            target = node.attrib.get("Target", "")
            if not rel_id or not target.startswith("media/"):
                continue
            rels[rel_id] = f"word/{target}"
        return rels

    def _read_docx_image_targets(self, archive: ZipFile, rels: dict[str, str]) -> list[str]:
        """按文档出现顺序读取图片目标路径。"""

        try:
            document_xml = archive.read("word/document.xml")
        except KeyError:
            return []
        root = ET.fromstring(document_xml)
        targets: list[str] = []
        for blip in root.findall(".//a:blip", _REL_NS):
            rel_id = blip.attrib.get(f"{{{_REL_NS['r']}}}embed")
            target = rels.get(rel_id or "")
            if target:
                targets.append(target)
        return targets

    def _extract_docx_preview_paragraph_text(self, paragraph: ET.Element) -> str:
        """提取预览段落文本，保留换行和制表符。"""

        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == self._word_tag("t"):
                parts.append(node.text or "")
            elif node.tag == self._word_tag("tab"):
                parts.append("\t")
            elif node.tag == self._word_tag("br"):
                parts.append("\n")
        return "\n".join(part.strip() for part in "".join(parts).splitlines() if part.strip()).strip()

    def _extract_docx_heading_level(self, paragraph: ET.Element) -> int | None:
        """识别 DOCX 标题级别，供预览层级展示。"""

        style = paragraph.find("./w:pPr/w:pStyle", {"w": _WORD_NS})
        style_value = style.attrib.get(f"{{{_WORD_NS}}}val", "") if style is not None else ""
        style_lower = style_value.lower()
        if style_lower.startswith("heading"):
            level_text = style_lower.replace("heading", "", 1).strip()
            if level_text.isdigit():
                return max(1, min(6, int(level_text)))
        return None

    def _extract_docx_paragraph_image_targets(
        self, paragraph: ET.Element, rels: dict[str, str]
    ) -> list[str]:
        """提取段落中的图片目标路径。"""

        targets: list[str] = []
        for blip in paragraph.findall(".//a:blip", _REL_NS):
            rel_id = blip.attrib.get(f"{{{_REL_NS['r']}}}embed")
            target = rels.get(rel_id or "")
            if target and target not in targets:
                targets.append(target)
        return targets

    def _read_zip_member_bytes(self, archive: ZipFile, target: str) -> bytes | None:
        """读取 ZIP 条目；遇到仅 CRC 异常的 Office 图片时尝试保守恢复。"""

        try:
            return archive.read(target)
        except KeyError:
            return None
        except BadZipFile:
            try:
                info = archive.getinfo(target)
            except KeyError:
                return None
            return self._read_zip_member_ignoring_crc(archive, info)

    def _read_zip_member_ignoring_crc(self, archive: ZipFile, info: ZipInfo) -> bytes | None:
        """绕过错误 CRC 读取媒体条目，仍限制压缩格式和后续图片校验。"""

        if info.flag_bits & 0x1:
            return None
        if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
            return None
        fp = archive.fp
        if fp is None:
            return None
        current_pos = fp.tell()
        try:
            fp.seek(info.header_offset)
            header = fp.read(30)
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                return None
            name_length = int.from_bytes(header[26:28], "little")
            extra_length = int.from_bytes(header[28:30], "little")
            fp.seek(name_length + extra_length, 1)
            raw_data = fp.read(info.compress_size)
            if len(raw_data) != info.compress_size:
                return None
            if info.compress_type == ZIP_STORED:
                return raw_data
            return zlib.decompress(raw_data, -15)
        except (OSError, zlib.error):
            return None
        finally:
            fp.seek(current_pos)

    def _extract_docx_preview_table_rows(self, table: ET.Element) -> list[list[str]]:
        """提取预览表格行，保留列结构。"""

        rows: list[list[str]] = []
        for row in table.findall("./w:tr", {"w": _WORD_NS}):
            values = [
                self._extract_docx_preview_cell_text(cell)
                for cell in row.findall("./w:tc", {"w": _WORD_NS})
            ]
            normalized = [value for value in values if value]
            if normalized:
                rows.append(normalized)
        return rows

    def _extract_docx_preview_cell_text(self, cell: ET.Element) -> str:
        """提取预览单元格文本。"""

        paragraphs = [
            self._extract_docx_preview_paragraph_text(paragraph)
            for paragraph in cell.findall(".//w:p", {"w": _WORD_NS})
        ]
        return " ".join(paragraph for paragraph in paragraphs if paragraph).strip()

    def _is_preview_heading(self, text: str) -> bool:
        """识别普通文本预览中的标题行。"""

        if len(text) > 60:
            return False
        prefixes = ("第", "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、")
        if text.startswith(prefixes):
            return True
        if text[:1].isdigit() and (". " in text or "、" in text):
            return True
        return False

    def _word_tag(self, name: str) -> str:
        """构造 WordprocessingML 命名空间标签。"""

        return f"{{{_WORD_NS}}}{name}"

    def _write_manifest(self, staged_doc_id: str, manifest: dict[str, Any]) -> None:
        """写入 manifest。"""

        self._manifest_path(staged_doc_id).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _manifest_path(self, staged_doc_id: str) -> Path:
        return self._staged_root(staged_doc_id) / "manifest.json"

    def _staged_root(self, staged_doc_id: str) -> Path:
        return Path(self._settings.storage_dir) / "_staged" / staged_doc_id

    def _resolve_source_type(self, extension: str) -> str:
        if extension == "pdf":
            return "pdf"
        if extension == "docx":
            return "docx"
        if extension in {"html", "htm"}:
            return "html"
        return "text"

    def _normalize_source_uri(self, source_uri: str | None) -> str | None:
        if source_uri is None:
            return None
        normalized = source_uri.strip()
        if not normalized:
            return None
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AppError(
                code=ErrorCode.VALIDATION_FAILED,
                message="文档来源链接格式不合法",
                detail={"field": "source_uri", "reason": "must_be_http_or_https"},
                status_code=400,
            )
        return normalized

    def _guess_media_type(self, suffix: str) -> str:
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".png":
            return "image/png"
        if suffix == ".gif":
            return "image/gif"
        return "application/octet-stream"

    def _is_valid_image_bytes(self, data: bytes, media_type: str) -> bool:
        """校验常见图片格式，避免损坏图片进入引用资产。"""

        if media_type == "image/png":
            return self._is_valid_png(data)
        if media_type == "image/jpeg":
            return data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")
        if media_type == "image/gif":
            return data.startswith((b"GIF87a", b"GIF89a"))
        return False

    def _is_valid_png(self, data: bytes) -> bool:
        """按 PNG chunk CRC 校验图片完整性。"""

        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return False
        offset = 8
        try:
            while offset + 12 <= len(data):
                length = int.from_bytes(data[offset : offset + 4], "big")
                chunk_type = data[offset + 4 : offset + 8]
                chunk_data_start = offset + 8
                chunk_data_end = chunk_data_start + length
                crc_start = chunk_data_end
                crc_end = crc_start + 4
                if crc_end > len(data):
                    return False
                expected_crc = int.from_bytes(data[crc_start:crc_end], "big")
                actual_crc = binascii.crc32(chunk_type + data[chunk_data_start:chunk_data_end])
                if actual_crc != expected_crc:
                    return False
                offset = crc_end
                if chunk_type == b"IEND":
                    return offset == len(data)
        except Exception:
            return False
        return False
