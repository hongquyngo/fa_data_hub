# utils/s3_utils.py
"""
S3 Utilities for File Operations

Version: 2.0.0
Changes:
- Thread-safe singleton pattern
- Extracted retry logic to decorator
- Generic file upload/download (not just PDF)
- Improved error handling
"""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from functools import wraps
import os
from io import BytesIO
import threading
import time

from .config import config

logger = logging.getLogger(__name__)


# ==================== RETRY DECORATOR ====================

def with_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for automatic retry with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ClientError as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"{func.__name__} attempt {attempt + 1} failed, retrying in {current_delay}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
            
            raise last_exception
        return wrapper
    return decorator


# ==================== S3 MANAGER CLASS ====================

class S3Manager:
    """
    Manager for S3 operations with thread-safe singleton
    
    Usage:
        s3 = get_s3_manager()
        result = s3.upload_file(content, filename, folder="uploads")
        url = s3.generate_presigned_url(s3_key)
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        aws_config = config.get_aws_config()
        
        self.bucket_name = aws_config.get('bucket_name', 'prostech-erp-dev')
        self.app_prefix = aws_config.get('app_prefix', 'streamlit-app')
        self.region = aws_config.get('region', 'ap-southeast-1')
        
        try:
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=aws_config.get('access_key_id'),
                aws_secret_access_key=aws_config.get('secret_access_key')
            )
            
            self._test_connection()
            logger.info(f"✅ S3 client initialized: {self.bucket_name}")
            self._initialized = True
            
        except NoCredentialsError:
            logger.error("❌ AWS credentials not found")
            raise ValueError("AWS credentials not configured")
        except Exception as e:
            logger.error(f"❌ Failed to initialize S3: {e}")
            raise
    
    def _test_connection(self):
        """Verify bucket exists and is accessible"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                raise ValueError(f"Bucket '{self.bucket_name}' not found")
            elif error_code == 403:
                raise ValueError(f"Access denied to bucket '{self.bucket_name}'")
            raise
    
    # ==================== CORE OPERATIONS ====================
    
    @with_retry(max_retries=3)
    def upload_file(
        self,
        content: Union[bytes, BytesIO],
        filename: str,
        folder: str = "uploads",
        content_type: str = None,
        metadata: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Upload file to S3
        
        Args:
            content: File content as bytes or BytesIO
            filename: Destination filename
            folder: S3 folder path
            content_type: MIME type (auto-detected if None)
            metadata: Additional metadata
            
        Returns:
            Dict with upload details including URLs
        """
        # Handle BytesIO
        if isinstance(content, BytesIO):
            content = content.getvalue()
        
        # Auto-detect content type
        if content_type is None:
            content_type = self._detect_content_type(filename)
        
        # Build S3 key with date folder
        date_folder = datetime.now().strftime('%Y/%m/%d')
        s3_key = f"{self.app_prefix}/{folder}/{date_folder}/{filename}"
        
        # Prepare metadata
        upload_metadata = {
            'upload_timestamp': datetime.now().isoformat(),
            'content_type': content_type,
            'original_filename': filename
        }
        if metadata:
            upload_metadata.update(metadata)
        
        # Upload
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=content,
            ContentType=content_type,
            Metadata=upload_metadata,
            ServerSideEncryption='AES256'
        )
        
        logger.info(f"✅ Uploaded: {s3_key} ({len(content)} bytes)")
        
        return {
            'success': True,
            'bucket': self.bucket_name,
            'key': s3_key,
            'filename': filename,
            'size': len(content),
            'presigned_url': self.generate_presigned_url(s3_key),
            'upload_time': datetime.now().isoformat()
        }
    
    @with_retry(max_retries=3)
    def download_file(self, s3_key: str) -> Optional[bytes]:
        """
        Download file from S3
        
        Args:
            s3_key: S3 object key
            
        Returns:
            File content as bytes, or None if failed
        """
        response = self.s3_client.get_object(
            Bucket=self.bucket_name,
            Key=s3_key
        )
        
        content = response['Body'].read()
        logger.info(f"✅ Downloaded: {s3_key} ({len(content)} bytes)")
        
        return content
    
    def delete_file(self, s3_key: str) -> bool:
        """
        Delete file from S3
        
        Args:
            s3_key: S3 object key
            
        Returns:
            True if successful
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            logger.info(f"✅ Deleted: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete {s3_key}: {e}")
            return False
    
    def generate_presigned_url(self, s3_key: str, expiry_days: int = 7) -> Optional[str]:
        """
        Generate presigned URL for S3 object
        
        Args:
            s3_key: S3 object key
            expiry_days: Days until URL expires
            
        Returns:
            Presigned URL string
        """
        try:
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiry_days * 24 * 60 * 60
            )
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None
    
    # ==================== QUERY OPERATIONS ====================
    
    def list_files(
        self,
        prefix: str = None,
        max_items: int = 100,
        file_extension: str = None
    ) -> List[Dict]:
        """
        List files in S3
        
        Args:
            prefix: S3 prefix filter
            max_items: Maximum items to return
            file_extension: Filter by extension (e.g., '.pdf')
            
        Returns:
            List of file info dictionaries
        """
        try:
            if prefix is None:
                prefix = f"{self.app_prefix}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_items
            )
            
            if 'Contents' not in response:
                return []
            
            files = []
            for obj in response['Contents']:
                # Filter by extension if specified
                if file_extension and not obj['Key'].endswith(file_extension):
                    continue
                
                files.append({
                    'key': obj['Key'],
                    'filename': os.path.basename(obj['Key']),
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                })
            
            return files
            
        except ClientError as e:
            logger.error(f"Failed to list files: {e}")
            return []
    
    def file_exists(self, s3_key: str) -> bool:
        """Check if file exists in S3"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Error checking file: {e}")
            return False
    
    def get_file_metadata(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """Get metadata for S3 object"""
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            return {
                'content_type': response.get('ContentType'),
                'content_length': response.get('ContentLength'),
                'last_modified': response.get('LastModified').isoformat() if response.get('LastModified') else None,
                'metadata': response.get('Metadata', {}),
                'etag': response.get('ETag')
            }
        except ClientError as e:
            logger.error(f"Failed to get metadata: {e}")
            return None
    
    # ==================== HELPER METHODS ====================
    
    def _detect_content_type(self, filename: str) -> str:
        """Detect MIME type from filename"""
        extension_map = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.txt': 'text/plain',
        }
        
        ext = os.path.splitext(filename)[1].lower()
        return extension_map.get(ext, 'application/octet-stream')


# ==================== SINGLETON ACCESS ====================

_s3_manager = None
_s3_lock = threading.Lock()


def get_s3_manager() -> S3Manager:
    """Get S3Manager singleton instance (thread-safe)"""
    global _s3_manager
    
    if _s3_manager is None:
        with _s3_lock:
            if _s3_manager is None:
                _s3_manager = S3Manager()
    
    return _s3_manager


def reset_s3_manager():
    """Reset S3Manager singleton (for reconnection)"""
    global _s3_manager
    
    with _s3_lock:
        _s3_manager = None
    
    logger.info("🔄 S3 manager reset")


# ==================== CONVENIENCE FUNCTIONS ====================

def upload_pdf(
    pdf_bytes: bytes,
    filename: str,
    folder: str = "production/documents",
    metadata: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Upload PDF to S3 (convenience function)
    
    Args:
        pdf_bytes: PDF content
        filename: Filename
        folder: S3 folder
        metadata: Additional metadata
        
    Returns:
        Upload result dictionary
    """
    s3 = get_s3_manager()
    return s3.upload_file(
        content=pdf_bytes,
        filename=filename,
        folder=folder,
        content_type='application/pdf',
        metadata=metadata
    )


def upload_image(
    image_bytes: bytes,
    filename: str,
    folder: str = "images",
    metadata: Dict[str, str] = None
) -> Dict[str, Any]:
    """Upload image to S3"""
    s3 = get_s3_manager()
    return s3.upload_file(
        content=image_bytes,
        filename=filename,
        folder=folder,
        metadata=metadata
    )


def get_company_logo(company_id: int, logo_path: str = None) -> Optional[bytes]:
    """
    Get company logo from S3 with fallback strategies
    
    Args:
        company_id: Company ID
        logo_path: Known logo path (optional)
        
    Returns:
        Logo bytes or None
    """
    s3 = get_s3_manager()
    
    # Try direct path first
    if logo_path:
        # Clean path
        clean_path = logo_path.lstrip('/')
        paths_to_try = [
            clean_path,
            f"company-logo/{clean_path}" if not clean_path.startswith('company-logo/') else clean_path,
            f"company-logo/{os.path.basename(clean_path)}",
        ]
        
        for path in paths_to_try:
            if s3.file_exists(path):
                return s3.download_file(path)
    
    # Search by pattern
    files = s3.list_files(prefix="company-logo/", max_items=500)
    
    for file_info in files:
        filename = file_info['filename'].lower()
        if str(company_id) in filename:
            return s3.download_file(file_info['key'])
    
    logger.warning(f"Logo not found for company {company_id}")
    return None


def validate_s3_connection() -> bool:
    """Validate S3 connection"""
    try:
        s3 = get_s3_manager()
        s3._test_connection()
        return True
    except Exception as e:
        logger.error(f"S3 validation failed: {e}")
        return False


# ==================== EXPORTS ====================

__all__ = [
    'S3Manager',
    'get_s3_manager',
    'reset_s3_manager',
    'upload_pdf',
    'upload_image',
    'get_company_logo',
    'validate_s3_connection',
    'with_retry',
]
