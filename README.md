# PrismaX Python SDK

Minimal upload SDK for PrismaX data uploads.

## Quickstart

```bash
pip install prismax
export PRISMAX_API_KEY="pxa_your_api_key"
```

```python
import prismax

result = prismax.upload("./data", task_id=123, machine_id="machine_id")
print(result["upload_id"])
```

The SDK scans the folder, creates an upload session, uploads raw files to signed
Google Cloud URLs, generates episode manifests in memory, uploads manifests last,
and returns the upload summary.

## Expected Folder Structure

```text
data/
  1.mcap
  1/
    high.mp4
    left.mp4
    right.mp4
```

Each episode must contain one root `{episode}.mcap` file and exactly three MP4
files under `{episode}/`: one filename containing `left`, one containing `right`,
and one environment video filename containing neither.

## CLI

```bash
prismax upload ./data --task-id 123 --machine-id machine_id
prismax status 123
```
