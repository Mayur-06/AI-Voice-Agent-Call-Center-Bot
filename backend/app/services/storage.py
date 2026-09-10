from app.config import settings
from app.models.database import get_storage_admin
import uuid
import asyncio


def _ensure_bucket(bucket_name: str) -> None:
    storage = get_storage_admin()
    try:
        buckets = storage.list_buckets()
        if not any(getattr(b, "name", None) == bucket_name for b in buckets):
            storage.create_bucket(bucket_name, options={"public": False})
    except Exception:
        pass


def ensure_recordings_bucket() -> None:
    _ensure_bucket("recordings")


def ensure_documents_bucket() -> None:
    _ensure_bucket("documents")


async def upload_document(file_bytes: bytes, filename: str, content_type: str) -> str:
    safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    storage_path = f"documents/{uuid.uuid4()}_{safe_filename}"
    storage = get_storage_admin()

    def _do_upload():
        storage.from_("documents").upload(storage_path, file_bytes, {"content-type": content_type})

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _do_upload)
    return storage_path


async def upload_recording(file_bytes: bytes, session_id: str, content_type: str = "audio/wav") -> str:
    storage_path = f"recordings/{session_id}.wav"
    storage = get_storage_admin()

    def _do_upload():
        storage.from_("recordings").upload(storage_path, file_bytes, {"content-type": content_type})

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _do_upload)
    return storage_path
