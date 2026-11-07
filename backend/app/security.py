"""Password hashing, JWT issue/verify, role guards and a small in-memory rate limiter."""
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expire_minutes)
    return jwt.encode({"sub": user.id, "role": user.role, "exp": exp}, s.jwt_secret, algorithm="HS256")


def current_user_optional(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User | None:
    if not creds:
        return None
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return db.get(User, payload.get("sub"))


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


class RateLimiter:
    """Sliding-window limiter per client IP + bucket (in-memory; use Redis behind multiple workers)."""

    def __init__(self, limit: int, window_seconds: int, bucket: str):
        self.limit, self.window, self.bucket = limit, window_seconds, bucket
        self.hits: dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request):
        key = f"{self.bucket}:{request.client.host if request.client else 'anon'}"
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, please slow down")
        q.append(now)

    def reset(self):
        self.hits.clear()


auth_limiter = RateLimiter(20, 60, "auth")
upload_limiter = RateLimiter(60, 60, "upload")
payment_limiter = RateLimiter(20, 60, "payment")
voice_limiter = RateLimiter(20, 60, "voice")
