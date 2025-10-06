# auth_routes.py
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from jose import JWTError

from database import get_db
import models, schemas
from auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    set_auth_cookies, clear_auth_cookies
)

router = APIRouter(prefix="/auth", tags=["auth"])

# --------------------------
# Helpers / dependencies
# --------------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> schemas.UserResponse:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    username = payload.sub
    if not username:
        raise HTTPException(status_code=401, detail="Token inválido (sin sub)")
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return schemas.UserResponse.from_orm(user)

# --------------------------
# Routes
# --------------------------
@router.post("/register", response_model=schemas.UserResponse, status_code=201)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    # Conflict checks
    if db.query(models.User).filter(models.User.username == user_in.username).first():
        raise HTTPException(status_code=409, detail="Usuario ya existe")
    if user_in.email and db.query(models.User).filter(models.User.email == user_in.email).first():
        raise HTTPException(status_code=409, detail="Email ya existe")

    user = models.User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        scopes=",".join(user_in.scopes or []),
        full_name=user_in.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return schemas.UserResponse.from_orm(user)

@router.post("/login")
def login(body: schemas.LoginBody, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == body.username).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    scopes = [s for s in (user.scopes or "").split(",") if s]
    access = create_access_token(user.username, scopes)
    refresh = create_refresh_token(user.username, scopes)

    resp = JSONResponse({"message": "ok", "user": schemas.UserResponse.from_orm(user).model_dump()})
    set_auth_cookies(resp, access, refresh)
    return resp

@router.post("/refresh")
def refresh(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No hay refresh token")
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh inválido")

    if payload.type != "refresh":
        raise HTTPException(status_code=401, detail="Token no es refresh")

    user = db.query(models.User).filter(models.User.username == payload.sub).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    scopes = [s for s in (user.scopes or "").split(",") if s]
    access = create_access_token(user.username, scopes)

    resp = JSONResponse({"message": "refreshed"})
    # Only set new access (keep same refresh until it expires)
    set_auth_cookies(resp, access_token=access, refresh_token=None)
    return resp

@router.post("/logout")
def logout():
    resp = JSONResponse({"message": "logged out"})
    clear_auth_cookies(resp)
    return resp

@router.get("/me", response_model=schemas.UserResponse)
def me(current: schemas.UserResponse = Depends(get_current_user)):
    print(current)
    return current
