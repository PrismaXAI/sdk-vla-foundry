import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlparse

import requests

from .errors import PrismaxApiError, PrismaxAuthError, PrismaxValidationError


DEFAULT_BASE_URL = (
    "https://app-prismax-data-pipeline-beta-1053158761087.us-west1.run.app"
)
DEFAULT_SESSION_TIMEOUT = 300
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
# Security Fix: Maximum concurrency (worker) count reduced to 10 to limit resource consumption.
MAX_CONCURRENCY = 10
MAX_RETRIES = 10
SDK_VERSION = "0.2.0"


def _sdk_version():
    try:
        return version("prismax")
    except PackageNotFoundError:
        return SDK_VERSION


def _validate_base_url(base_url):
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise PrismaxValidationError(
            f"base_url must start with https:// (got: {base_url!r})."
        )
    host = parsed.hostname or ""
    if not host:
        raise PrismaxValidationError("base_url must include a hostname.")
    if parsed.username or parsed.password:
        raise PrismaxValidationError("base_url must not include credentials.")
    if parsed.scheme != "https" and host not in LOCAL_HOSTS:
        raise PrismaxValidationError(
            "base_url must use https:// for non-local hosts "
            f"(got: {base_url!r}). Plain http is only allowed for localhost."
        )


def _validate_signed_url(signed_url):
    parsed = urlparse(str(signed_url or ""))
    if parsed.scheme != "https" or not parsed.hostname:
        raise PrismaxValidationError(
            "signed_url must be an absolute HTTPS URL with a hostname."
        )


def _is_retryable_status(status_code):
    return status_code == 429 or 500 <= status_code < 600


class PrismaXClient:
    def __init__(
        self,
        api_key=None,
        base_url=None,
        timeout=60,
        session_timeout=DEFAULT_SESSION_TIMEOUT,
        concurrency=5,
        retries=3,
        require_api_key=True,
    ):
        self.api_key = api_key or os.getenv("PRISMAX_API_KEY")
        if require_api_key and not self.api_key:
            raise PrismaxAuthError("api_key is required or PRISMAX_API_KEY must be set.")
        self.base_url = (
            base_url or os.getenv("PRISMAX_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        _validate_base_url(self.base_url)
        try:
            self.timeout = float(timeout)
            self.session_timeout = float(session_timeout)
            self.concurrency = int(concurrency)
            self.retries = int(retries)
        except (TypeError, ValueError):
            raise PrismaxValidationError(
                "timeout, session_timeout, concurrency, and retries must be numeric."
            ) from None
        if self.timeout <= 0 or self.session_timeout <= 0:
            raise PrismaxValidationError(
                "timeout and session_timeout must be greater than zero."
            )
        if not 1 <= self.concurrency <= MAX_CONCURRENCY:
            raise PrismaxValidationError(
                f"concurrency must be between 1 and {MAX_CONCURRENCY}."
            )
        if not 1 <= self.retries <= MAX_RETRIES:
            raise PrismaxValidationError(
                f"retries must be between 1 and {MAX_RETRIES}."
            )

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"prismax-sdk/{_sdk_version()}",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _request(self, method, path, *, request_timeout=None, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                timeout=self.timeout if request_timeout is None else request_timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise PrismaxApiError(f"PrismaX API request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {"success": False, "msg": response.text}

        if not isinstance(payload, dict):
            raise PrismaxApiError("PrismaX API returned an invalid JSON object.")
        if not response.ok or payload.get("success") is False:
            message = payload.get("msg") or payload.get("error") or f"PrismaX API request failed: {response.status_code}"
            if response.status_code in (401, 403):
                raise PrismaxAuthError(message)
            raise PrismaxApiError(message)
        return payload.get("data", payload)

    def create_upload_session(self, *, task_id, serial_number, files):
        return self._request(
            "POST",
            "/v1/data/upload-sessions",
            request_timeout=self.session_timeout,
            json={
                "task_id": task_id,
                "serial_number": serial_number,
                "files": files,
            },
        )

    def resume_upload_session(self, *, upload_id, files):
        return self._request(
            "POST",
            f"/v1/data/upload-sessions/{upload_id}/resume",
            request_timeout=self.session_timeout,
            json={"files": files},
        )

    def list_tasks(self):
        return self._request("GET", "/data/tasks")

    def get_upload(self, upload_id):
        return self._request("GET", f"/v1/data/uploads/{upload_id}")

    def list_uploads(self, *, limit=10):
        return self._request(
            "GET",
            "/v1/data/uploads",
            params={"limit": limit},
        )

    def upload_file_to_signed_url(self, *, signed_url, path, content_type, relative_path=None):
        _validate_signed_url(signed_url)
        display_path = relative_path or path
        for attempt in range(1, self.retries + 1):
            try:
                with open(path, "rb") as handle:
                    response = requests.put(
                        signed_url,
                        data=handle,
                        headers={"Content-Type": content_type or "application/octet-stream"},
                        timeout=self.timeout,
                    )
                if response.ok:
                    return
                message = f"Upload failed with status {response.status_code}: {response.text[:200]}"
                if not _is_retryable_status(response.status_code):
                    raise PrismaxApiError(f"Failed to upload {display_path}: {message}")
            except (OSError, requests.RequestException) as exc:
                message = str(exc)

            if attempt == self.retries:
                raise PrismaxApiError(f"Failed to upload {display_path}: {message}")
            time.sleep(min(2 ** attempt, 10))

    def upload_json_to_signed_url(self, *, signed_url, payload):
        _validate_signed_url(signed_url)
        body = json.dumps(payload, indent=2).encode("utf-8")
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.put(
                    signed_url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                if response.ok:
                    return
                message = f"Manifest upload failed with status {response.status_code}: {response.text[:200]}"
                if not _is_retryable_status(response.status_code):
                    raise PrismaxApiError(message)
            except requests.RequestException as exc:
                message = str(exc)

            if attempt == self.retries:
                raise PrismaxApiError(message)
            time.sleep(min(2 ** attempt, 10))

    def upload_files(self, upload_items, on_file_complete=None):
        if not upload_items:
            return
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {
                executor.submit(
                    self.upload_file_to_signed_url,
                    signed_url=item["signed_url"],
                    path=item["path"],
                    content_type=item["content_type"],
                    relative_path=item.get("relative_path"),
                ): item
                for item in upload_items
            }
            for future in as_completed(futures):
                future.result()
                if on_file_complete:
                    on_file_complete(futures[future])