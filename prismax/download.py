import sys
from pathlib import Path, PurePosixPath

from .client import (
    DEFAULT_SESSION_TIMEOUT,
    DOWNLOAD_API_KEY_ENV,
    PrismaXClient,
)
from .errors import PrismaxApiError, PrismaxValidationError


def _build_client(
    *, api_key, base_url, timeout, session_timeout, concurrency, retries
):
    return PrismaXClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        session_timeout=session_timeout,
        concurrency=concurrency,
        retries=retries,
        api_key_env=DOWNLOAD_API_KEY_ENV,
        api_key_prefix="pxa_",
    )


def create_download_session(
    package_id,
    *,
    api_key=None,
    base_url=None,
    timeout=60,
    session_timeout=DEFAULT_SESSION_TIMEOUT,
    concurrency=5,
    retries=3,
):
    package_id = str(package_id or "").strip()
    if not package_id:
        raise PrismaxValidationError("package_id is required.")
    client = _build_client(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        session_timeout=session_timeout,
        concurrency=concurrency,
        retries=retries,
    )
    return client.create_download_session(package_id=package_id)


def _safe_destination(output, relative_path):
    normalized = str(relative_path or "").replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise PrismaxValidationError(
            f"Invalid download relative_path: {relative_path!r}."
        )
    return output.joinpath(*path.parts)


def _download_items(session, output):
    items = []
    destinations = set()
    for sample in session.get("samples") or []:
        assets = sample.get("assets") or {}
        ordered_assets = [
            assets.get("mcap"),
            assets.get("env"),
            assets.get("left"),
            assets.get("right"),
            *(sample.get("additional_videos") or []),
        ]
        for asset in ordered_assets:
            if not asset:
                continue
            relative_path = asset.get("relative_path")
            url = str(asset.get("url") or "").strip()
            cookie_header = str(
                (asset.get("auth") or {}).get("cookie_header") or ""
            ).strip()
            if not relative_path or not url or not cookie_header:
                raise PrismaxApiError(
                    "Download session returned an asset without relative_path, URL, or CDN cookie."
                )
            destination = _safe_destination(output, relative_path)
            destination_key = str(destination)
            if destination_key in destinations:
                raise PrismaxValidationError(
                    f"Download session contains duplicate path: {relative_path}."
                )
            destinations.add(destination_key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            items.append(
                {
                    "url": url,
                    "cookie_header": cookie_header,
                    "destination": destination,
                    "relative_path": str(relative_path),
                }
            )
    if not items:
        raise PrismaxApiError("Download session did not include any files.")
    return items


def download(
    package_id,
    output,
    *,
    api_key=None,
    base_url=None,
    progress=True,
    timeout=60,
    session_timeout=DEFAULT_SESSION_TIMEOUT,
    concurrency=5,
    retries=3,
):
    package_id = str(package_id or "").strip()
    if not package_id:
        raise PrismaxValidationError("package_id is required.")

    output_path = Path(output).expanduser()
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PrismaxValidationError(
            f"Could not create output directory {output_path}: {exc}"
        ) from exc

    client = _build_client(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        session_timeout=session_timeout,
        concurrency=concurrency,
        retries=retries,
    )
    session = client.create_download_session(package_id=package_id)
    items = _download_items(session, output_path)
    completed = 0

    def file_completed(item):
        nonlocal completed
        completed += 1
        if progress:
            print(
                f"Download {completed}/{len(items)}: {item['relative_path']}",
                file=sys.stderr,
                flush=True,
            )

    client.download_files(items, on_file_complete=file_completed)
    return {
        "download_id": session.get("download_id"),
        "package_id": session.get("package_id") or package_id,
        "episode_count": len(session.get("samples") or []),
        "file_count": len(items),
        "output": str(output_path),
    }
