from .upload import _build_client


def list_jobs(*, api_key=None, base_url=None, timeout=60):
    client = _build_client(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    return client.list_jobs()
