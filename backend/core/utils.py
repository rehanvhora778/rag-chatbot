import hashlib
import logging
import uuid
from pathlib import Path
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def generate_unique_filename(original_filename: str) -> str:
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip('.')


def compute_file_hash(file_obj) -> str:
    """SHA-256 of an upload — used to reject the same file twice."""
    hasher = hashlib.sha256()
    file_obj.seek(0)
    for chunk in iter(lambda: file_obj.read(8192), b''):
        hasher.update(chunk)
    file_obj.seek(0)
    return hasher.hexdigest()


def get_user_upload_dir(user_id) -> Path:
    path = Path(settings.MEDIA_ROOT) / 'documents' / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_file_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def serialize_mongo_doc(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    result = {}
    for key, value in doc.items():
        if type(value).__name__ == 'ObjectId':
            result[key] = str(value)
        elif isinstance(value, dict):
            result[key] = serialize_mongo_doc(value)
        elif isinstance(value, list):
            result[key] = [
                serialize_mongo_doc(v) if isinstance(v, dict)
                else str(v) if type(v).__name__ == 'ObjectId'
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result
