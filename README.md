# Quickstart (Revised)

## Quickstart

### Step 1: Register your robot and become an Operator

Before you can create an upload API key, your account must be approved as an
**Operator**. This is a one-time setup:

1. Sign in at <https://app.prismax.ai> (create an account if you don't have one).
2. Open <https://app.prismax.ai/account> and go to **Robots**, then click
   **Register Robot**. Enter your robot's serial number, model, and hardware
   details. The serial number you register here is the same one you will pass
   to the SDK as `serial_number`.
3. On the same account page, click **Apply to Become an Operator** and submit
   the application. Operator status is required to upload data.
4. Wait for approval. You will be notified by email, and your account page
   will show your Operator status. Until you are approved, the **API Keys**
   section will not allow creating Operator / Upload keys.

### Step 2: Create an upload API key

Once your Operator application is approved:

- Open <https://app.prismax.ai/account>, go to **API Keys**, then create an
  **Operator / Upload** key (prefix `pxu_`). The key is shown once, so copy it
  when it is created.

Download API keys are not valid for uploads.

### Step 3: Install and configure the SDK

```bash
pip install prismax
export PRISMAX_API_KEY="pxu_your_upload_api_key"
```

The published SDK defaults to the PrismaX production data API. Internal test
environments can override the endpoint with `PRISMAX_BASE_URL`; an explicit
`base_url=` argument takes precedence over the environment variable. Keep beta
endpoint values in environment configuration rather than source code.

### Step 4: Find your task ID

Every upload targets a task. You can query the full task table directly from
the SDK or CLI — no need to browse the website UI. This does not require an
API key:

```bash
prismax scenarios
```

Example output:

```
  ID  Scenario                                      Status
----  --------------------------------------------  --------
   1  Pick and place packaged food items            active
   2  Fold and stack towels                         active
   3  Open drawer and retrieve utensil              active
   4  Sort objects by color into bins               active
   5  Wipe table surface                            active
```

Or in Python:

```python
import prismax

for task in prismax.list_scenarios():
    print(task["id"], task["scenario"], task["status"])
```

You can reference a task in either of two ways when uploading:

- `task_id=1` — the numeric database task ID from the table above. This is
  the most direct and unambiguous option.
- `scenario="Pick and place packaged food items"` — the task scenario/name.
  The SDK resolves this to the database task ID automatically using a
  case-insensitive match.

### Step 5: Upload

```python
import prismax

result = prismax.upload(
    "./data",
    task_id=1,  # or scenario="Pick and place packaged food items"
    serial_number="robot_serial_number",  # the serial you registered in Step 1
)
print(result["upload_id"])
```

The SDK scans the folder, creates an upload session, uploads raw files to
signed Google Cloud URLs, generates episode manifests in memory, uploads
manifests last, and returns the upload summary.

You can also pass the API key directly:

```python
import prismax

result = prismax.upload(
    "./data",
    task_id=1,
    serial_number="robot_serial_number",
    api_key="pxu_your_upload_api_key",
)
```

### Prerequisites summary

You need:

- an approved **Operator** account with a registered robot
  (<https://app.prismax.ai/account>)
- a PrismaX upload API key with the `pxu_` prefix
- a PrismaX task ID (query with `prismax scenarios`) or task scenario/name
- the robot serial number for the registered machine that produced the data
