import re

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from auth.jwt import verify_token
from services.render_client import list_services, trigger_deploy, get_deploy_status

app = FastAPI(title="Render API Wrapper")
security = HTTPBearer(auto_error=False)

class DeployRequest(BaseModel):
    service_id: str = Field(min_length=8, max_length=64, pattern=r"^srv-[A-Za-z0-9]+$")
    branch: str = Field(default="main", min_length=1, max_length=128,
                        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

async def exigir_administrador(
    token: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
):
    if token is None or token.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrative bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    verify_token(token.credentials)


@app.get("/services")
async def list_services_endpoint(_admin=Depends(exigir_administrador)):  # noqa: B008
    return await list_services()

@app.post("/deploy")
async def trigger_deploy_endpoint(
    request: DeployRequest,
    _admin=Depends(exigir_administrador),  # noqa: B008
):
    if ".." in request.branch or "//" in request.branch:
        raise HTTPException(status_code=400, detail="Invalid branch")
    return await trigger_deploy(request.service_id, request.branch)

@app.get("/deploys/{deploy_id}")
async def get_deploy_status_endpoint(
    deploy_id: str,
    _admin=Depends(exigir_administrador),  # noqa: B008
):
    if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", deploy_id):
        raise HTTPException(status_code=400, detail="Invalid deploy ID")
    return await get_deploy_status(deploy_id)
