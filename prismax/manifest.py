from datetime import datetime, timezone

from .scanner import LocalFile


def manifest_placeholder(episode_key: str) -> dict:
    return {
        "relative_path": f"{episode_key}/_MANIFEST.json",
        "size_bytes": None,
        "content_type": "application/json",
    }


def build_manifest_payload(
    *,
    episode_key: str,
    upload_id,
    machine_id,
    task_id,
    files: list[LocalFile],
) -> dict:
    episode_files = []
    for item in files:
        relative_path = item.relative_path
        if relative_path == f"{episode_key}.mcap" or relative_path.startswith(f"{episode_key}/"):
            episode_files.append(item.as_api_payload())

    return {
        "manifest_version": 1,
        "upload_id": upload_id,
        "episode_key": episode_key,
        "machine_id": machine_id,
        "task_id": task_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": episode_files,
    }
