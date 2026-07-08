# PrismaX Python SDK

Minimal upload SDK for PrismaX data uploads.

## License

This SDK is source-available for noncommercial use under the PolyForm
Noncommercial License 1.0.0. Commercial use is not permitted unless PrismaX
grants a separate commercial license.

## Quickstart

```bash
pip install prismax
export PRISMAX_API_KEY="pxu_your_upload_api_key"
```

Use a PrismaX upload API key with the `pxu_` prefix. Download API keys are not
valid for uploads.

```python
import prismax

result = prismax.upload("./data", task_id=123, serial_number="robot_serial_number")
print(result["upload_id"])
```

The SDK scans the folder, creates an upload session, uploads raw files to signed
Google Cloud URLs, generates episode manifests in memory, uploads manifests last,
and returns the upload summary.

You can also pass the API key directly:

```python
import prismax

result = prismax.upload(
    "./data",
    task_id=123,
    serial_number="robot_serial_number",
    api_key="pxu_your_upload_api_key",
)
```

## Expected Folder Structure

```text
data/
  1.mcap
  1/
    high.mp4
    left.mp4
    right.mp4
    high2.mp4
    left2.mp4
    right2.mp4
```

Each episode must contain one root `{episode}.mcap` file and at least three MP4
files under `{episode}/`: one primary filename containing `left`, one containing
`right`, and one environment/high video filename containing neither. Additional
MP4 files are uploaded as raw files, included in downloads, and checked for
duration consistency. A duration mismatch across any episode videos can fail the
upload. Only the primary three videos are processed for derived previews, QA,
and duplicate detection.

Use lowercase `.mp4` extensions. Uppercase variants such as `.MP4` are rejected
so client validation, worker processing, and download manifests choose the same
primary videos. Hidden files are ignored, including macOS metadata files such as
`.DS_Store` and `._left.mp4`.

## CLI

```bash
prismax upload ./data --task-id 123 --serial-number robot_serial_number
prismax status 123
```

Use `--wait` to wait for the worker to finish. The default maximum wait time is
30 minutes.

```bash
prismax upload ./data --task-id 123 --serial-number robot_serial_number --wait
prismax upload ./data --task-id 123 --serial-number robot_serial_number --wait --max-wait 3600
```

Useful CLI options:

```bash
prismax upload ./data --task-id 123 --serial-number robot_serial_number --timeout 120 --retries 5
prismax upload ./data --task-id 123 --serial-number robot_serial_number --wait --poll-interval 5 --max-poll-errors 3
```

## Status and Resume

```python
import prismax

upload_status = prismax.status(123)

resume_result = prismax.resume(
    123,
    "./data",
)
```

```bash
prismax status 123
prismax resume 123 ./data
```

Resume expects the same complete upload folder/file list, not only the files
that are missing from cloud storage. The SDK will ask the API which files still
need signed upload URLs. Backend resume is only allowed while the upload is
still in `UPLOADING` status; once the worker has started or the upload reaches a
terminal status, create a new upload instead.

Deployment note for SDK/client maintainers: deploy backend and worker support
for additional videos before releasing clients that allow more than three MP4s
per episode.

## Custom API Base URL

The SDK defaults to the PrismaX production data API. For beta or local testing,
pass `base_url` explicitly. It must use `https://`; plain `http://` is only
allowed for `localhost` / `127.0.0.1`.

```python
import prismax

prismax.upload(
    "./data",
    task_id=123,
    serial_number="robot_serial_number",
    base_url="http://127.0.0.1:8082",
)
```

## Error Handling

```python
import prismax

try:
    prismax.upload("./data", task_id=123, serial_number="robot_serial_number")
except prismax.PrismaxValidationError as exc:
    print(f"Invalid upload folder: {exc}")
except prismax.PrismaxAuthError as exc:
    print(f"API key or permission error: {exc}")
except prismax.PrismaxApiError as exc:
    print(f"PrismaX API error: {exc}")
```

If raw file upload fails after the session is created, the SDK error includes
the upload ID and a `prismax resume <upload_id> <folder>` command.
