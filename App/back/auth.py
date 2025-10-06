# auth.py
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import os

from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

# =========================
# Settings (use env in prod)
# =========================
SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGE_ME_DEV_SECRET")
ALGORITHM = "HS256"
ACCESS_MIN = int(os.environ.get("ACCESS_MIN", "30"))       # 30 min
REFRESH_DAYS = int(os.environ.get("REFRESH_DAYS", "14"))   # 14 days

# Cookies
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", None)      # e.g. "tu-dominio.com"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax") # "lax" | "strict" | "none"

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload(BaseModel):
    sub: str
    scopes: List[str] = []
    exp: int
    type: Optional[str] = None  # "refresh" for refresh tokens

def _now():
    return datetime.now(timezone.utc)

def hash_password(plain: str) -> str:
    hashed = pwd.hash(plain)
    return hashed

def verify_password(plain: str, hashed: str) -> bool:
    return pwd.verify(plain, hashed)

def create_access_token(username: str, scopes: List[str]) -> str:
    exp = _now() + timedelta(minutes=ACCESS_MIN)
    claims = {"sub": username, "scopes": scopes, "exp": int(exp.timestamp())}
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(username: str, scopes: List[str]) -> str:
    exp = _now() + timedelta(days=REFRESH_DAYS)
    claims = {"sub": username, "scopes": scopes, "type": "refresh", "exp": int(exp.timestamp())}
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenPayload(**data)
    except JWTError:
        raise

def set_auth_cookies(response, access_token: str, refresh_token: Optional[str] = None):
    # Access token cookie
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
    # Refresh token cookie
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            domain=COOKIE_DOMAIN,
            max_age=REFRESH_DAYS * 24 * 3600,
            path="/auth",  # scope it to /auth if you wish
        )

def clear_auth_cookies(response):
    for k in ("access_token", "refresh_token"):
        response.delete_cookie(k, domain=COOKIE_DOMAIN, path="/")
        # also clear scoped path
        response.delete_cookie(k, domain=COOKIE_DOMAIN, path="/auth")
