from app.config import settings
from app.models.database import get_storage_admin


def ensure_recordings_bucket() -> None:
    storage = get_storage_admin()
    try:
        buckets = storage.list_buckets()
        if not any(getattr(b, "name", None) == "recordings" for b in buckets):
            storage.create_bucket("recordings", options={"public": False})
    except Exception:
        pass
