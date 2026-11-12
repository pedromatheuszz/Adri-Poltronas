import os
from pathlib import Path
from dotenv import load_dotenv

SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent

# Local development uses the project-wide credential so the wrapper and the
# rest of the project cannot silently drift onto different Render keys.
# The service-local file is still read for its JWT secret and for standalone
# deployments. Existing process environment values retain highest priority.
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(SERVICE_DIR / ".env", override=False)

RENDER_API_KEY = (os.getenv("KEY_RENDER") or os.getenv("RENDER_API_KEY") or "").strip()
RENDER_BASE_URL = "https://api.render.com/v1"
JWT_SECRET = (os.getenv("JWT_SECRET") or "").strip()

if len(RENDER_API_KEY) < 20:
    raise RuntimeError("KEY_RENDER (local) ou RENDER_API_KEY (deploy) precisa estar configurada.")
if len(JWT_SECRET) < 32 or JWT_SECRET.casefold() in {"super-secreto", "changeme", "secret"}:
    raise RuntimeError("JWT_SECRET deve ser um segredo aleatório com ao menos 32 caracteres.")
