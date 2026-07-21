"""Storage backend abstraction: local filesystem for dev, Cloudflare R2 (S3-compatible) for prod.

Selected via STORAGE_BACKEND env var so switching later needs no application code changes.
"""
import shutil
from pathlib import Path

from . import config


class LocalStorage:
    """Serves files from storage/videos/ via a Flask route (see routes.serve_video)."""

    backend_name = "local"

    def __init__(self):
        self.root = config.STORAGE_DIR

    def save_file(self, local_path, key):
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        return key

    def url_for(self, key):
        # Handled by the /media/<path:key> route in routes.py
        return f"/media/{key}"

    def local_path_for(self, key):
        return self.root / key


class R2Storage:
    """Cloudflare R2 via the S3-compatible API (boto3)."""

    backend_name = "r2"

    def __init__(self):
        import boto3

        cfg = config.r2_config()
        self.bucket = cfg["bucket_name"]
        self.public_base_url = cfg["public_base_url"].rstrip("/")
        endpoint = f"https://{cfg['account_id']}.r2.cloudflarestorage.com"
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=cfg["access_key_id"],
            aws_secret_access_key=cfg["secret_access_key"],
            region_name="auto",
        )

    def save_file(self, local_path, key):
        self.client.upload_file(str(local_path), self.bucket, key)
        return key

    def url_for(self, key):
        return f"{self.public_base_url}/{key}"


def get_storage():
    if config.storage_backend() == "r2":
        return R2Storage()
    return LocalStorage()
