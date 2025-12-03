from datetime import datetime, timedelta, timezone
from typing import Optional, List
import os

from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

# =========================
# Configuración de seguridad
# (en prod usar variables de entorno)
# =========================
SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGE_ME_DEV_SECRET")
ALGORITHM = "HS256"
ACCESS_MIN = int(os.environ.get("ACCESS_MIN", "30"))       # Duración del access token en minutos
REFRESH_DAYS = int(os.environ.get("REFRESH_DAYS", "14"))   # Duración del refresh token en días

# =========================
# Configuración de cookies
# =========================
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", None)      # Ejemplo: "tu-dominio.com"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax") # "lax" | "strict" | "none"

# Contexto para manejo de contraseñas (hash/verify)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload(BaseModel):
    """
    Payload estándar de los JWT usados en la app.
    - sub: identificador del usuario (username)
    - scopes: lista de permisos/roles
    - exp: timestamp de expiración (segundos UNIX)
    - type: "refresh" para tokens de refresco, None para access tokens
    """
    sub: str
    scopes: List[str] = []
    exp: int
    type: Optional[str] = None  # "refresh" para tokens de refresco


def _now():
    """
    Devuelve la hora actual en UTC como datetime timezone-aware.
    Se usa para calcular expiraciones de tokens.
    """
    return datetime.now(timezone.utc)


def hash_password(plain: str) -> str:
    """
    Recibe una contraseña en texto plano y devuelve su hash usando bcrypt.
    """
    hashed = pwd.hash(plain)
    return hashed


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verifica que la contraseña en texto plano coincida con el hash almacenado.
    """
    return pwd.verify(plain, hashed)


def create_access_token(username: str, scopes: List[str]) -> str:
    """
    Crea un JWT de acceso (corto plazo) para el usuario dado.
    Incluye:
      - sub: username
      - scopes: lista de permisos
      - exp: expiración en minutos (ACCESS_MIN)
    """
    exp = _now() + timedelta(minutes=ACCESS_MIN)
    claims = {"sub": username, "scopes": scopes, "exp": int(exp.timestamp())}
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(username: str, scopes: List[str]) -> str:
    """
    Crea un JWT de refresco (largo plazo) para el usuario dado.
    Incluye:
      - sub: username
      - scopes: lista de permisos
      - type: "refresh"
      - exp: expiración en días (REFRESH_DAYS)
    """
    exp = _now() + timedelta(days=REFRESH_DAYS)
    claims = {"sub": username, "scopes": scopes, "type": "refresh", "exp": int(exp.timestamp())}
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """
    Decodifica un JWT y lo convierte a TokenPayload.
    Lanza JWTError si el token es inválido o está expirado.
    """
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenPayload(**data)
    except JWTError:
        # Se propaga el error para que la capa superior maneje la respuesta HTTP adecuada
        raise


def set_auth_cookies(response, access_token: str, refresh_token: Optional[str] = None):
    """
    Escribe en la respuesta HTTP las cookies de autenticación:
      - access_token: siempre
      - refresh_token: solo si se provee
    Configura flags de seguridad (httponly, secure, samesite, domain).
    """
    # Cookie para access token (vida corta)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        max_age=ACCESS_MIN * 60,
        path="/",
    )
    # Cookie para refresh token (vida larga)
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            domain=COOKIE_DOMAIN,
            max_age=REFRESH_DAYS * 24 * 3600,
            path="/auth",  # opcional: restringir solo a rutas /auth
        )


def clear_auth_cookies(response):
    """
    Elimina las cookies de autenticación (access_token y refresh_token)
    tanto en el path raíz "/" como en "/auth".
    """
    for k in ("access_token", "refresh_token"):
        response.delete_cookie(k, domain=COOKIE_DOMAIN, path="/")
        # también eliminar cualquier cookie en el path /auth
        response.delete_cookie(k, domain=COOKIE_DOMAIN, path="/auth")
