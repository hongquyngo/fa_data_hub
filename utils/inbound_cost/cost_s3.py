# utils/inbound_cost/cost_s3.py
# Self-contained S3 manager for Inbound Logistic Cost module.
#
# KEY DIFFERENCE vs utils/s3_utils.py:
#   - config is imported LAZILY inside __init__() — never at module level.
#   - This breaks the circular import chain:
#       cost_dialogs → cost_s3 → config   (would fail at page load)
#   - Only inbound-cost-relevant methods included (no label / template helpers).
#
# S3 folder: inbound-cost-file/

import logging
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)

S3_FOLDER = "inbound-cost-file/"


class CostS3Manager:
    """
    S3 operations scoped to the Inbound Logistic Cost module.
    Config is resolved at first instantiation, not at import time.
    """

    def __init__(self):
        # ── Lazy config import ─────────────────────────────────────────────
        # Importing here (not at module top) means this file can be imported
        # freely without triggering config → dotenv → potential errors.
        try:
            from ..config import config as _cfg          # noqa: PLC0415
            aws = _cfg.aws_config
        except Exception as e:
            raise RuntimeError(f"CostS3Manager: cannot load AWS config — {e}") from e

        # ── Validate ───────────────────────────────────────────────────────
        missing = [k for k in ("access_key_id", "secret_access_key", "region", "bucket_name")
                   if not aws.get(k)]
        if missing:
            raise ValueError(f"CostS3Manager: missing AWS config keys: {missing}")

        # ── boto3 client ───────────────────────────────────────────────────
        try:
            import boto3                                 # noqa: PLC0415
            self._s3 = boto3.client(
                "s3",
                aws_access_key_id=aws["access_key_id"],
                aws_secret_access_key=aws["secret_access_key"],
                region_name=aws["region"],
            )
        except ImportError as e:
            raise RuntimeError("boto3 is not installed. Run: pip install boto3") from e

        self.bucket      = aws["bucket_name"]
        self.app_prefix  = aws.get("app_prefix", "streamlit-app")
        logger.info(f"CostS3Manager ready — bucket: {self.bucket}")

    # ======================================================================
    # CORE OPERATIONS
    # ======================================================================

    def upload_file(
        self,
        file_content: bytes,
        s3_key: str,
        content_type: str = "application/octet-stream",
    ) -> Tuple[bool, str]:
        """
        Upload bytes to S3.
        Returns (success, s3_key_or_error_message).
        """
        try:
            self._s3.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
            )
            logger.info(f"Uploaded: {s3_key}")
            return True, s3_key
        except Exception as e:
            err = f"Upload failed [{s3_key}]: {e}"
            logger.error(err)
            return False, err

    def download_file(self, s3_key: str) -> Optional[bytes]:
        """Download and return file bytes, or None on error."""
        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=s3_key)
            return resp["Body"].read()
        except Exception as e:
            logger.error(f"Download failed [{s3_key}]: {e}")
            return None

    def delete_file(self, s3_key: str) -> bool:
        """Delete a single object. Returns True on success."""
        try:
            self._s3.delete_object(Bucket=self.bucket, Key=s3_key)
            logger.info(f"Deleted: {s3_key}")
            return True
        except Exception as e:
            logger.error(f"Delete failed [{s3_key}]: {e}")
            return False

    def batch_delete(self, s3_keys: List[str]) -> Dict[str, List[str]]:
        """
        Delete up to 1 000 objects per call.
        Returns {"deleted": [...], "errors": [...]}.
        """
        result: Dict[str, List[str]] = {"deleted": [], "errors": []}
        if not s3_keys:
            return result
        try:
            for i in range(0, len(s3_keys), 1000):
                batch = s3_keys[i : i + 1000]
                resp = self._s3.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": k} for k in batch]},
                )
                result["deleted"].extend(o["Key"] for o in resp.get("Deleted", []))
                result["errors"].extend(
                    f"{e['Key']}: {e['Message']}" for e in resp.get("Errors", [])
                )
        except Exception as e:
            logger.error(f"Batch delete error: {e}")
            result["errors"].append(str(e))
        return result

    def get_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a pre-signed GET URL valid for `expiration` seconds (default 1 h).
        Returns None on error.
        """
        try:
            return self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": s3_key},
                ExpiresIn=expiration,
            )
        except Exception as e:
            logger.error(f"Presigned URL error [{s3_key}]: {e}")
            return None

    def file_exists(self, s3_key: str) -> bool:
        """Return True if the object exists in S3."""
        try:
            self._s3.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception:
            return False

    def get_file_info(self, s3_key: str) -> Optional[Dict]:
        """Return metadata dict for an object, or None on error."""
        try:
            resp = self._s3.head_object(Bucket=self.bucket, Key=s3_key)
            size = resp["ContentLength"]
            return {
                "size":          size,
                "size_mb":       round(size / 1024 / 1024, 2),
                "content_type":  resp.get("ContentType", "unknown"),
                "last_modified": resp["LastModified"],
                "etag":          resp.get("ETag", "").strip('"'),
            }
        except Exception as e:
            logger.error(f"get_file_info error [{s3_key}]: {e}")
            return None

    def list_files(self, prefix: str = "", max_keys: int = 1000) -> List[Dict]:
        """List objects under a prefix. Returns list of metadata dicts."""
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        try:
            resp = self._s3.list_objects_v2(
                Bucket=self.bucket, Prefix=prefix, MaxKeys=max_keys
            )
            files = []
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/") or key.endswith(".keep"):
                    continue
                files.append({
                    "key":           key,
                    "name":          key.split("/")[-1],
                    "size":          obj["Size"],
                    "size_mb":       round(obj["Size"] / 1024 / 1024, 2),
                    "last_modified": obj["LastModified"],
                })
            return files
        except Exception as e:
            logger.error(f"list_files error [{prefix}]: {e}")
            return []

    # ======================================================================
    # INBOUND COST–SPECIFIC HELPERS
    # ======================================================================

    def upload_cost_file(
        self,
        file_content: bytes,
        filename: str,
    ) -> Tuple[bool, str]:
        """
        Upload a cost-entry attachment.
        S3 key format: inbound-cost-file/<timestamp_ms>_<sanitised_filename>

        Returns (success, s3_key_or_error).
        """
        ts        = int(datetime.now().timestamp() * 1000)
        safe_name = filename.replace(" ", "_")
        s3_key    = f"{S3_FOLDER}{ts}_{safe_name}"
        ct        = self._content_type(filename)
        return self.upload_file(file_content, s3_key, ct)

    def batch_upload_cost_files(
        self,
        files: List[Tuple[bytes, str]],   # [(content, filename), ...]
    ) -> Dict[str, Any]:
        """
        Upload multiple cost-entry attachments.

        Returns:
            {
                "success":       bool,
                "uploaded":      [s3_key, ...],
                "failed":        [{"filename": ..., "error": ...}, ...],
                "total":         int,
                "success_count": int,
                "error_count":   int,
            }
        """
        result: Dict[str, Any] = {
            "success":       False,
            "uploaded":      [],
            "failed":        [],
            "total":         len(files),
            "success_count": 0,
            "error_count":   0,
        }
        if not files:
            result["success"] = True
            return result

        for idx, (content, filename) in enumerate(files, 1):
            ok, out = self.upload_cost_file(content, filename)
            if ok:
                result["uploaded"].append(out)
                result["success_count"] += 1
                logger.info(f"[{idx}/{len(files)}] OK  — {filename}")
            else:
                result["failed"].append({"filename": filename, "error": out})
                result["error_count"] += 1
                logger.error(f"[{idx}/{len(files)}] FAIL — {filename}: {out}")

        result["success"] = result["error_count"] == 0
        return result

    def delete_cost_file(self, s3_key: str) -> bool:
        """
        Delete a cost-entry attachment.
        Guards against accidentally deleting files outside S3_FOLDER.
        """
        if not s3_key.startswith(S3_FOLDER):
            logger.warning(f"delete_cost_file: key outside {S3_FOLDER} — refused ({s3_key})")
            return False
        return self.delete_file(s3_key)

    def get_cost_file_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """Pre-signed URL for a cost-entry attachment."""
        if not s3_key.startswith(S3_FOLDER):
            logger.warning(f"get_cost_file_url: key outside {S3_FOLDER} — refused ({s3_key})")
            return None
        return self.get_presigned_url(s3_key, expiration)

    def list_cost_files(self, max_keys: int = 1000) -> List[Dict]:
        """List all objects under inbound-cost-file/."""
        return self.list_files(prefix=S3_FOLDER, max_keys=max_keys)

    # ======================================================================
    # INTERNAL HELPERS
    # ======================================================================

    @staticmethod
    def _content_type(filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return {
            "pdf":  "application/pdf",
            "png":  "image/png",
            "jpg":  "image/jpeg",
            "jpeg": "image/jpeg",
        }.get(ext, "application/octet-stream")
