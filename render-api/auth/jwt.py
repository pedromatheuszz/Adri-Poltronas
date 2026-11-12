import datetime

import jwt
from jwt import PyJWTError
from fastapi import HTTPException, status

from config import JWT_SECRET

ISSUER = "adri-render-api"
AUDIENCE = "adri-render-admin"

def generate_token(username: str, role: str = "user", expires_minutes: int = 60) -> str:
    """Generate a JWT token.

    Args:
        username: Identifier for the user.
        role: Must be 'admin'; tokens cannot be minted for ordinary users.
        expires_minutes: Token validity period.
    Returns:
        A signed JWT string.
    """
    if not isinstance(username, str) or not username.strip():
        raise ValueError("username deve ser informado")
    if role != "admin":
        raise ValueError("Somente tokens administrativos são permitidos")
    if not isinstance(expires_minutes, int) or not 1 <= expires_minutes <= 60:
        raise ValueError("A validade do token deve estar entre 1 e 60 minutos")

    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username.strip()[:80],
        "role": role,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=expires_minutes),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    # pyjwt <2 returns bytes, >=2 returns str
    return token if isinstance(token, str) else token.decode("utf-8")

def verify_token(token: str) -> dict:
    """Validate a JWT token and return its payload.

    Raises:
        HTTPException (401) if token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["sub", "role", "iss", "aud", "iat", "exp"]},
        )
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrative token required",
            )
        return payload
    except HTTPException:
        raise
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        ) from exc
