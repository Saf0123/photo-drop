"""Storage backends. LocalBackend runs anywhere; GcpBackend uses Cloud Storage + Firestore."""
import json
import os
from datetime import datetime
from pathlib import Path


class LocalBackend:
    """Files on disk. Used for local development and tests (no cloud account needed)."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, image_id, data, meta):
        (self.root / f"{image_id}.bin").write_bytes(data)
        stored = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in meta.items()}
        (self.root / f"{image_id}.json").write_text(json.dumps(stored))

    def get(self, image_id):
        try:
            meta = json.loads((self.root / f"{image_id}.json").read_text())
            data = (self.root / f"{image_id}.bin").read_bytes()
        except FileNotFoundError:
            return None
        for key in ("created_at", "expires_at"):
            meta[key] = datetime.fromisoformat(meta[key])
        return data, meta


class GcpBackend:
    """Image bytes in Cloud Storage, metadata in Firestore. Auth comes from the Cloud Run service account."""

    def __init__(self, bucket_name):
        from google.cloud import firestore, storage

        self.bucket = storage.Client().bucket(bucket_name)
        self.docs = firestore.Client().collection("images")

    def put(self, image_id, data, meta):
        self.bucket.blob(f"images/{image_id}").upload_from_string(data, content_type=meta["content_type"])
        self.docs.document(image_id).set(meta)  # expires_at is a Firestore TTL field

    def get(self, image_id):
        from google.api_core.exceptions import NotFound

        snap = self.docs.document(image_id).get()
        if not snap.exists:
            return None
        try:
            data = self.bucket.blob(f"images/{image_id}").download_as_bytes()
        except NotFound:
            return None
        return data, snap.to_dict()


def make_backend():
    if os.environ.get("BACKEND", "local") == "gcp":
        return GcpBackend(os.environ["BUCKET"])
    return LocalBackend(os.environ.get("LOCAL_DIR", "./data"))
