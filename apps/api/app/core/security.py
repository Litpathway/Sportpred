import hashlib
import secrets
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import User, utcnow

password_hasher = PasswordHash.recommended()
DUMMY_HASH = password_hasher.hash(secrets.token_hex(32))


def issue_token(user: User) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(32)
    token = jwt.encode({
        "sub": str(user.id), "csrf": csrf, "iss": "sportpredict", "aud": "sportpredict-admin",
        "exp": utcnow() + timedelta(minutes=get_settings().token_minutes), "iat": utcnow(),
    }, get_settings().jwt_secret, algorithm="HS256")
    return token, csrf


def require_role(*roles: str):
    def dependency(request: Request, db: Session = Depends(get_db)) -> User:
        token = request.cookies.get("sp_session")
        if not token:
            raise HTTPException(401, "Admin sign-in required")
        try:
            claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"],
                                issuer="sportpredict", audience="sportpredict-admin",
                                options={"require": ["exp", "iat", "sub", "csrf"]})
            user = db.get(User, int(claims["sub"]))
        except (jwt.InvalidTokenError, ValueError, TypeError):
            raise HTTPException(401, "Session expired") from None
        if not user or not user.active:
            raise HTTPException(401, "Account unavailable")
        if user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin not in get_settings().origins:
                raise HTTPException(403, "Origin not allowed")
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), claims["csrf"]):
                raise HTTPException(403, "Invalid CSRF token")
        return user
    return dependency


reader = require_role("viewer", "operator", "admin")
operator = require_role("operator", "admin")
administrator = require_role("admin")


def login_identity(request: Request, email: str) -> str:
    # Never trust a forwarded IP unless a trusted proxy is configured in deployment.
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"{host}:{email.casefold()}".encode()).hexdigest()
