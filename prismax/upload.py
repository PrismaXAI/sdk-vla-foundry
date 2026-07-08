import time

from .client import PrismaXClient
from .errors import PrismaxApiError, PrismaxValidationError
from .manifest import build_manifest_payload, manifest_placeholder
from .scanner import scan_folder, validate_mcap_mp4, episode_keys


TERMINAL_STATUSES = {
    "DERIVED_READY",
    "DERIVED_VALIDATION_FAILED",
    "FAILED",
    "DERIVED_PARTIALLY_READY",
}
DEFAULT_POLL_ERROR_LIMIT = 3


def _build_files_payload(files, keys):
    payload = [item.as_api_payload() for item in files]
    payload.extend(manifest_placeholder(key) for key in keys)
    return payload


def upload(
    folder,
    *,
    task_id,
    serial_number,
    api_key=None,
    base_url=None,
    wait=False,
    poll_interval=10,
    max_wait=1800,
    max_poll_errors=DEFAULT_POLL_ERROR_LIMIT,
    timeout=60,
    concurrency=5,
    retries=3,
):
    if task_id is None:
        raise PrismaxValidationError("task_id is required.")
    if not serial_number:
        raise PrismaxValidationError("serial_number is required.")
    client = PrismaXClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        concurrency=concurrency,
        retries=retries,
    )
    files = scan_folder(folder)
    errors = validate_mcap_mp4(files)
    if errors:
        raise PrismaxValidationError("; ".join(errors))

    keys = episode_keys(files)
    session = client.create_upload_session(
        task_id=task_id,
        serial_number=serial_number,
        files=_build_files_payload(files, keys),
    )
    resolved_machine_id = session.get("machine_id")
    try:
        _upload_session_files(
            client=client,
            session=session,
            files=files,
            episode_keys_value=keys,
            task_id=task_id,
            machine_id=resolved_machine_id,
        )
    except PrismaxApiError as exc:
        upload_id = session.get("upload_id")
        raise PrismaxApiError(
            f"Upload {upload_id} was created but file upload failed. "
            f"Resume with: prismax resume {upload_id} {folder}. Original error: {exc}"
        ) from exc

    if wait:
        return wait_for_upload(
            session["upload_id"],
            api_key=api_key,
            base_url=base_url,
            poll_interval=poll_interval,
            max_wait=max_wait,
            max_poll_errors=max_poll_errors,
            timeout=timeout,
            retries=retries,
        )
    return _public_session_result(session)


def resume(
    upload_id,
    folder,
    *,
    api_key=None,
    base_url=None,
    wait=False,
    poll_interval=10,
    max_wait=1800,
    max_poll_errors=DEFAULT_POLL_ERROR_LIMIT,
    timeout=60,
    concurrency=5,
    retries=3,
):
    client = PrismaXClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        concurrency=concurrency,
        retries=retries,
    )
    files = scan_folder(folder)
    errors = validate_mcap_mp4(files)
    if errors:
        raise PrismaxValidationError("; ".join(errors))

    keys = episode_keys(files)
    session = client.resume_upload_session(
        upload_id=upload_id,
        files=_build_files_payload(files, keys),
    )
    try:
        _upload_session_files(
            client=client,
            session=session,
            files=files,
            episode_keys_value=keys,
            task_id=session.get("task_id"),
            machine_id=session.get("machine_id"),
        )
    except PrismaxApiError as exc:
        raise PrismaxApiError(
            f"Resume for upload {upload_id} failed while uploading files. "
            f"Retry with: prismax resume {upload_id} {folder}. Original error: {exc}"
        ) from exc

    if wait:
        return wait_for_upload(
            upload_id,
            api_key=api_key,
            base_url=base_url,
            poll_interval=poll_interval,
            max_wait=max_wait,
            max_poll_errors=max_poll_errors,
            timeout=timeout,
            retries=retries,
        )
    return _public_session_result(session)


def status(upload_id, *, api_key=None, base_url=None, timeout=60, retries=3):
    client = PrismaXClient(api_key=api_key, base_url=base_url, timeout=timeout, retries=retries)
    return client.get_upload(upload_id)


def wait_for_upload(
    upload_id,
    *,
    api_key=None,
    base_url=None,
    poll_interval=10,
    max_wait=1800,
    timeout=60,
    retries=3,
    max_poll_errors=DEFAULT_POLL_ERROR_LIMIT,
):
    client = PrismaXClient(api_key=api_key, base_url=base_url, timeout=timeout, retries=retries)
    started_at = time.monotonic()
    last_status = None
    poll_errors = 0
    while True:
        try:
            current = client.get_upload(upload_id)
            poll_errors = 0
            last_status = str(current.get("status") or "").upper()
            if last_status in TERMINAL_STATUSES:
                return current
        except PrismaxApiError as exc:
            poll_errors += 1
            if max_poll_errors is not None and poll_errors >= int(max_poll_errors):
                raise PrismaxApiError(
                    f"Failed to poll upload {upload_id} status after {poll_errors} consecutive errors: {exc}"
                ) from exc
        if max_wait is not None and time.monotonic() - started_at >= int(max_wait):
            raise PrismaxApiError(
                f"Timed out waiting for upload {upload_id} after {int(max_wait)} seconds "
                f"(last status: {last_status or 'unknown'})."
            )
        time.sleep(max(1, int(poll_interval)))


def _upload_session_files(*, client, session, files, episode_keys_value, task_id, machine_id):
    signed_urls = session.get("signed_urls") or []
    signed_url_by_path = {
        item.get("relative_path"): item
        for item in signed_urls
        if item.get("relative_path") and item.get("signed_url")
    }

    raw_uploads = []
    local_file_by_relative_path = {item.relative_path: item for item in files}
    for local_file in files:
        signed_item = signed_url_by_path.get(local_file.relative_path)
        if not signed_item:
            continue
        raw_uploads.append({
            "signed_url": signed_item["signed_url"],
            "relative_path": local_file.relative_path,
            "path": local_file.path,
            "content_type": local_file.content_type,
        })
    client.upload_files(raw_uploads)

    upload_id = session.get("upload_id")
    for episode_key in episode_keys_value:
        manifest_path = f"{episode_key}/_MANIFEST.json"
        signed_item = signed_url_by_path.get(manifest_path)
        if not signed_item:
            continue
        payload = build_manifest_payload(
            episode_key=episode_key,
            upload_id=upload_id,
            machine_id=machine_id,
            task_id=task_id,
            files=list(local_file_by_relative_path.values()),
        )
        client.upload_json_to_signed_url(
            signed_url=signed_item["signed_url"],
            payload=payload,
        )


def _public_session_result(session):
    hidden = {"signed_urls"}
    return {
        key: value
        for key, value in session.items()
        if key not in hidden
    }
