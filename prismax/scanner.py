import mimetypes
from dataclasses import dataclass
from pathlib import Path

from .errors import PrismaxValidationError


MANIFEST_FILENAME = "_MANIFEST.json"
REQUIRED_VIDEO_COUNT = 3


@dataclass(frozen=True)
class LocalFile:
    relative_path: str
    path: Path
    size_bytes: int
    content_type: str

    def as_api_payload(self):
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
        }


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".json":
        return "application/json"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _video_slot(file_name: str) -> str:
    normalized = file_name.lower()
    if "left" in normalized:
        return "left"
    if "right" in normalized:
        return "right"
    return "env"


def scan_folder(folder) -> list[LocalFile]:
    root = Path(folder).expanduser().resolve()
    if not root.exists():
        raise PrismaxValidationError(f"Folder does not exist: {root}")
    if not root.is_dir():
        raise PrismaxValidationError(f"Path must be a folder: {root}")

    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        if relative_path == ".DS_Store" or relative_path.endswith("/.DS_Store"):
            continue
        if relative_path == MANIFEST_FILENAME or relative_path.endswith(f"/{MANIFEST_FILENAME}"):
            continue
        files.append(LocalFile(
            relative_path=relative_path,
            path=path,
            size_bytes=path.stat().st_size,
            content_type=_content_type(path),
        ))

    if not files:
        raise PrismaxValidationError("No uploadable files found.")
    return files


def validate_mcap_mp4(files: list[LocalFile]) -> list[str]:
    errors = []
    stats = {}

    def ensure_episode(episode_key):
        if episode_key not in stats:
            stats[episode_key] = {
                "mcap_count": 0,
                "mp4_count": 0,
                "video_slots": {"env": 0, "left": 0, "right": 0},
            }
        return stats[episode_key]

    for item in files:
        relative_path = item.relative_path
        if "/" in relative_path:
            parts = relative_path.split("/")
            if len(parts) != 2:
                errors.append(f"Nested folders are not allowed: {relative_path}")
                continue
            folder_name, file_name = parts
            if not folder_name or not file_name:
                errors.append(f"Invalid path: {relative_path}")
                continue
            if folder_name.endswith(".mcap"):
                errors.append(f"Video folder name must not end with .mcap: {folder_name}")
                continue
            if not file_name.endswith(".mp4"):
                errors.append(f"Only .mp4 files are allowed inside episode folders: {relative_path}")
                continue
            episode_stats = ensure_episode(folder_name)
            episode_stats["mp4_count"] += 1
            episode_stats["video_slots"][_video_slot(file_name)] += 1
            continue

        if relative_path.endswith(".mcap"):
            episode_key = relative_path[:-5]
            if not episode_key:
                errors.append(f"Invalid .mcap filename at root: {relative_path}")
                continue
            ensure_episode(episode_key)["mcap_count"] += 1
            continue

        errors.append(f"Only .mcap files are allowed at root: {relative_path}")

    episode_keys = sorted(stats.keys())
    if not episode_keys:
        errors.append(
            "No valid episodes found. Expected {episode}.mcap at root and exactly "
            "3 .mp4 files under {episode}/."
        )

    for episode_key in episode_keys:
        episode_stats = stats[episode_key]
        if episode_stats["mcap_count"] != 1:
            errors.append(
                f"Episode {episode_key} must have exactly 1 .mcap file "
                f"(found {episode_stats['mcap_count']})."
            )
        if episode_stats["mp4_count"] != REQUIRED_VIDEO_COUNT:
            errors.append(
                f"Episode {episode_key} must have exactly {REQUIRED_VIDEO_COUNT} "
                f".mp4 files (found {episode_stats['mp4_count']})."
            )
        else:
            slots = episode_stats["video_slots"]
            if slots["left"] != 1 or slots["right"] != 1 or slots["env"] != 1:
                errors.append(
                    f"Episode {episode_key} must include one left MP4, one right MP4, "
                    'and one environment MP4. Use one filename containing "left", '
                    'one containing "right", and one containing neither.'
                )

    return errors


def episode_keys(files: list[LocalFile]) -> list[str]:
    keys = set()
    for item in files:
        path = item.relative_path
        if path.endswith(".mcap") and "/" not in path:
            keys.add(path[:-5])
        elif path.endswith(".mp4") and "/" in path:
            keys.add(path.split("/", 1)[0])
    return sorted(keys, key=lambda item: (len(item), item))
