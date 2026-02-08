"""上传文件辅助工具。"""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.core.error_codes import ErrorCode
from app.core.errors import AppError


async def save_upload_file(
    upload: UploadFile, target_path: Path, max_bytes: int
) -> int:
    """保存上传文件并返回写入字节数。"""

    target_path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target_path.open("wb") as file_handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                file_handle.write(chunk)
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(
                        code=ErrorCode.FILE_TOO_LARGE,
                        message="文件大小超过限制",
                        detail={
                            "max_mb": max_bytes // (1024 * 1024),
                            "size_bytes": size,
                        },
                        status_code=400,
                    )
    except AppError:
        target_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        target_path.unlink(missing_ok=True)
        raise AppError(
            code=ErrorCode.UNEXPECTED_ERROR,
            message="保存上传文件失败",
            detail={"error": str(exc)},
            status_code=500,
        ) from exc
    return size
