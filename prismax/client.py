import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .errors import PrismaxApiError, PrismaxAuthError


DEFAULT_BASE_URL = "https://data.prismaxserver.com"


class PrismaXClient:
    def __init__(self, api_key=None, base_url=None, timeout=60, concurrency=5, retries=3):
        self.api_key = api_key or os.getenv("PRISMAX_API_KEY")
        if not self.api_key:
            raise PrismaxAuthError("api_key is required or PRISMAX_API_KEY must be set.")
        self.base_url = (base_url or os.getenv("PRISMAX_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.concurrency = max(1, int(concurrency))
        self.retries = max(1, int(retries))

    def _headers(self):
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"
        response = requests.request(
            method,
            url,
            headers=self._headers(),
            timeout=self.timeout,
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"success": False, "msg": response.text}

        if not response.ok or payload.get("success") is False:
            message = payload.get("msg") or payload.get("error") or f"PrismaX API request failed: {response.status_code}"
            raise PrismaxApiError(message)
        return payload.get("data", payload)

    def create_upload_session(self, *, task_id, machine_id, files):
        return self._request(
            "POST",
            "/v1/data/upload-sessions",
            json={
                "task_id": task_id,
                "machine_id": machine_id,
                "files": files,
            },
        )

    def resume_upload_session(self, *, upload_id, files):
        return self._request(
            "POST",
            f"/v1/data/upload-sessions/{upload_id}/resume",
            json={"files": files},
        )

    def get_upload(self, upload_id):
        return self._request("GET", f"/v1/data/uploads/{upload_id}")

    def upload_file_to_signed_url(self, *, signed_url, path, content_type):
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
            except requests.RequestException as exc:
                message = str(exc)

            if attempt == self.retries:
                raise PrismaxApiError(message)
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

    def upload_files(self, upload_items):
        if not upload_items:
            return
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = [
                executor.submit(
                    self.upload_file_to_signed_url,
                    signed_url=item["signed_url"],
                    path=item["path"],
                    content_type=item["content_type"],
                )
                for item in upload_items
            ]
            for future in as_completed(futures):
                future.result()
