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
UPLOAD_API_KEY_ENV = "PRISMAX_UPLOAD_API_KEY"
DOWNLOAD_API_KEY_ENV = "PRISMAX_DOWNLOAD_API_KEY"


def _sdk_version():
    try:
        return version("prismax")
    except PackageNotFoundError:
        return "0.1.0"


def _validate_base_url(base_url):
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise PrismaxValidationError(
            f"base_url must start with https:// (got: {base_url!r})."
        )
    host = parsed.hostname or ""
    if parsed.scheme != "https" and host not in LOCAL_HOSTS:
        raise PrismaxValidationError(
            "base_url must use https:// for non-local hosts "
            f"(got: {base_url!r}). Plain http is only allowed for localhost."
        )


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
        api_key_env=None,
        api_key_prefix=None,
    ):
        self.api_key = api_key or (os.getenv(api_key_env) if api_key_env else None)
        if require_api_key and not self.api_key:
            env_hint = f" or {api_key_env} must be set" if api_key_env else ""
            raise PrismaxAuthError(f"api_key is required{env_hint}.")
        if self.api_key and api_key_prefix and not self.api_key.startswith(api_key_prefix):
            raise PrismaxAuthError(
                f"This operation requires a {api_key_prefix} API key."
            )
        self.base_url = (
            base_url or os.getenv("PRISMAX_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        _validate_base_url(self.base_url)
        self.timeout = timeout
        self.session_timeout = session_timeout
        self.concurrency = max(1, int(concurrency))
        self.retries = max(1, int(retries))

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

        if not response.ok or payload.get("success") is False:
            message = payload.get("msg") or payload.get("error") or f"PrismaX API request failed: {response.status_code}"
            if response.status_code in (401, 403):
                raise PrismaxAuthError(message)
            raise PrismaxApiError(message)
        return payload.get("data", payload)

    def create_upload_session(self, *, task_id, serial_number, files, job_id=None):
        body = {
            "task_id": task_id,
            "serial_number": serial_number,
            "files": files,
        }
        if job_id is not None:
            body["job_id"] = job_id
        return self._request(
            "POST",
            "/v1/data/upload-sessions",
            request_timeout=self.session_timeout,
            json=body,
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

    def list_jobs(self):
        return self._request("GET", "/v1/data/jobs")

    def get_upload(self, upload_id):
        return self._request("GET", f"/v1/data/uploads/{upload_id}")

    def list_uploads(self, *, limit=10):
        return self._request(
            "GET",
            "/v1/data/uploads",
            params={"limit": limit},
        )

    def create_download_session(self, *, package_id):
        return self._request(
            "POST",
            "/v1/data/download-sessions",
            request_timeout=self.session_timeout,
            json={"package_id": package_id},
        )

    def upload_file_to_signed_url(self, *, signed_url, path, content_type, relative_path=None):
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
            except (OSError, requests.RequestException) as exc:
                message = str(exc)

            if attempt == self.retries:
                raise PrismaxApiError(f"Failed to upload {display_path}: {message}")
            time.sleep(min(2 ** attempt, 10))

    def upload_json_to_signed_url(self, *, signed_url, payload):
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

    def download_file_from_cdn(self, *, url, cookie_header, destination, relative_path=None):
        display_path = relative_path or str(destination)
        for attempt in range(1, self.retries + 1):
            try:
                with requests.get(
                    url,
                    headers={"Cookie": cookie_header},
                    stream=True,
                    timeout=self.timeout,
                ) as response:
                    response.raise_for_status()
                    with open(destination, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                handle.write(chunk)
                return
            except (OSError, requests.RequestException) as exc:
                message = str(exc)

            if attempt == self.retries:
                raise PrismaxApiError(f"Failed to download {display_path}: {message}")
            time.sleep(min(2 ** attempt, 10))

    def download_files(self, download_items, on_file_complete=None):
        if not download_items:
            return
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {
                executor.submit(
                    self.download_file_from_cdn,
                    url=item["url"],
                    cookie_header=item["cookie_header"],
                    destination=item["destination"],
                    relative_path=item.get("relative_path"),
                ): item
                for item in download_items
            }
            for future in as_completed(futures):
                future.result()
                if on_file_complete:
                    on_file_complete(futures[future])
