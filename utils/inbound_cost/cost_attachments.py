# utils/inbound_cost/cost_attachments.py
# File validation, S3 upload helpers, and DB media record management.
# Pattern mirrors utils/vendor_invoice/invoice_attachments.py
# S3Manager is imported lazily (inside functions) to avoid circular import
# via s3_utils → config at module load time.

import re
import time
import logging
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = ["pdf", "png", "jpg", "jpeg"]
MAX_FILE_MB        = 10
MAX_FILE_BYTES     = MAX_FILE_MB * 1024 * 1024
MAX_FILES          = 10
S3_FOLDER_PREFIX   = "inbound-cost-file/"


# ============================================================================
# VALIDATION
# ============================================================================

def validate_uploaded_files(files) -> Tuple[bool, List[str], List[Dict]]:
    """
    Validate uploaded files for type, size, and count.

    Returns:
        (is_valid, error_messages, validated_metadata)
    """
    if not files:
        return True, [], []

    errors   = []
    metadata = []
    seen     = set()

    if len(files) > MAX_FILES:
        return False, [f"❌ Max {MAX_FILES} files allowed (got {len(files)})"], []

    for idx, file in enumerate(files, 1):
        fname  = file.name
        fsize  = file.size
        fext   = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        ferrs  = []

        if fext not in ALLOWED_EXTENSIONS:
            ferrs.append(f"Invalid type '.{fext}' (allowed: {', '.join(ALLOWED_EXTENSIONS)})")
        if fsize > MAX_FILE_BYTES:
            ferrs.append(f"Too large ({fsize/1024/1024:.1f} MB > {MAX_FILE_MB} MB)")
        if fname in seen:
            ferrs.append("Duplicate filename")
        if not _valid_filename(fname):
            ferrs.append("Filename contains special characters")

        seen.add(fname)

        if ferrs:
            errors.append(f"File #{idx} ({fname}): {', '.join(ferrs)}")
        else:
            metadata.append({
                "index":       idx,
                "filename":    fname,
                "size":        fsize,
                "size_mb":     round(fsize / 1024 / 1024, 2),
                "ext":         fext.upper(),
                "file_object": file,
            })

    return len(errors) == 0, errors, metadata


def _valid_filename(name: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9\s_\-\.]+$", name))


# ============================================================================
# FILE PREPARATION
# ============================================================================

def prepare_files_for_upload(files) -> List[Dict[str, Any]]:
    """
    Read file bytes and build S3 key for each file.
    Returns list of dicts ready to pass to S3Manager.upload_file().
    """
    prepared = []
    base_ts  = int(time.time() * 1000)

    for idx, file in enumerate(files):
        file.seek(0)
        content = file.read()
        sname   = _sanitize(file.name)
        s3_key  = f"{S3_FOLDER_PREFIX}{base_ts + idx}_{sname}"

        prepared.append({
            "original_name": file.name,
            "sanitized_name": sname,
            "s3_key":         s3_key,
            "content":        content,
            "size":           file.size,
            "content_type":   _content_type(file.name),
        })

    return prepared


def _sanitize(filename: str) -> str:
    s = filename.replace(" ", "_")
    s = re.sub(r"[^a-zA-Z0-9._\-]", "", s).lower()
    if "." in s:
        name, ext = s.rsplit(".", 1)
        s = f"{name[:100]}.{ext}"
    return s


def _content_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "pdf":  "application/pdf",
        "png":  "image/png",
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")


# ============================================================================
# S3 UPLOAD  (lazy import of S3Manager to avoid circular import)
# ============================================================================

def _get_s3():
    """Instantiate CostS3Manager lazily — avoids config import at module load."""
    from .cost_s3 import CostS3Manager   # intra-package, always safe
    return CostS3Manager()


def upload_files_to_s3(prepared_files: List[Dict]) -> Tuple[List[str], List[str]]:
    """
    Upload prepared files to S3 using CostS3Manager.
    Returns (successful_s3_keys, failed_filenames).
    """
    try:
        s3 = _get_s3()
    except Exception as e:
        logger.error(f"Cannot initialise CostS3Manager: {e}")
        return [], [f["original_name"] for f in prepared_files]

    uploaded: List[str] = []
    failed:   List[str] = []

    for f in prepared_files:
        ok, out = s3.upload_file(
            file_content=f["content"],
            s3_key=f["s3_key"],
            content_type=f["content_type"],
        )
        if ok:
            uploaded.append(f["s3_key"])
            logger.info(f"Uploaded {f['s3_key']}")
        else:
            logger.error(f"S3 upload failed for {f['original_name']}: {out}")
            failed.append(f["original_name"])

    return uploaded, failed


def cleanup_failed_uploads(s3_keys: List[str]) -> None:
    """Delete S3 objects uploaded before a DB transaction failure."""
    if not s3_keys:
        return
    try:
        s3 = _get_s3()
        for key in s3_keys:
            if s3.delete_file(key):
                logger.info(f"Cleaned up: {key}")
            else:
                logger.error(f"Cleanup failed: {key}")
    except Exception as e:
        logger.error(f"Could not initialise CostS3Manager for cleanup: {e}")


def get_presigned_url(s3_key: str) -> Optional[str]:
    """Generate a pre-signed GET URL for a single S3 key."""
    try:
        return _get_s3().get_presigned_url(s3_key)
    except Exception as e:
        logger.error(f"Presigned URL error [{s3_key}]: {e}")
        return None


# ============================================================================
# DISPLAY HELPERS
# ============================================================================

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    return f"{size_bytes/1024/1024:.1f} MB"


def get_file_icon(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {"pdf": "📄", "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️"}.get(ext, "📎")


def summarize_files(metadata: List[Dict]) -> Dict[str, Any]:
    if not metadata:
        return {"count": 0, "total_size": 0, "total_size_formatted": "0 B", "types": []}
    total = sum(f["size"] for f in metadata)
    return {
        "count":                len(metadata),
        "total_size":           total,
        "total_size_formatted": format_file_size(total),
        "types":                list({f["ext"] for f in metadata}),
    }