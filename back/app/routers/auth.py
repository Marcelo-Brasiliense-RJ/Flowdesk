"""Authentication routes: email/password login -> JWT."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, is_admin, is_dev, verify_password
from ..database import get_db
from ..models import User
from ..ratelimit import _client_ip, enforce
from ..schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.is_admin = is_admin(user)
    out.is_dev = is_dev(user)
    return out


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # Anti brute-force: por conta (protege o alvo sem travar o escritório atrás do
    # mesmo NAT) e um teto por IP (força distribuída de um mesmo host).
    email = (body.email or "").strip().lower()
    enforce(f"login:email:{email}", 10, 300, context=f"ip={_client_ip(request)}")
    enforce(f"login:ip:{_client_ip(request)}", 50, 300)
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    token = create_access_token(user.email)
    return TokenResponse(access_token=token, user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return _user_out(current)
