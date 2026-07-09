from .client import PrismaXClient


def list_scenarios(*, api_key=None, base_url=None, timeout=60):
    client = PrismaXClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        require_api_key=False,
    )
    tasks = client.list_tasks()
    scenarios = []
    seen = set()
    for task in tasks or []:
        scenario = str(task.get("scenario") or "").strip()
        if not scenario or scenario in seen:
            continue
        scenarios.append(scenario)
        seen.add(scenario)
    return scenarios
