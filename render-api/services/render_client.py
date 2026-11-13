import httpx
from config import RENDER_API_KEY, RENDER_BASE_URL

_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _render_headers():
    return {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}


async def list_services():
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{RENDER_BASE_URL}/services", headers=_render_headers())
    resp.raise_for_status()
    return resp.json()


async def trigger_deploy(service_id: str, branch: str = "main"):
    payload = {"branch": branch}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{RENDER_BASE_URL}/services/{service_id}/deploys", json=payload, headers=_render_headers()
        )
    if resp.status_code != 201:
        raise httpx.HTTPStatusError("Deploy failed", request=resp.request, response=resp)
    return resp.json()


async def get_deploy_status(deploy_id: str):
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{RENDER_BASE_URL}/deploys/{deploy_id}", headers=_render_headers())
    resp.raise_for_status()
    return resp.json()
