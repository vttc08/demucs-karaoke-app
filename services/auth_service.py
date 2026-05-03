"""Authentication service for server-managed admin accounts."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import AdminSession, AdminUser


ADMIN_SESSION_COOKIE = "karaoke_admin_session"
PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 32
SESSION_TOKEN_BYTES = 32
SESSION_DAYS = 30


class AuthService:
    """Create and verify admin credentials and sessions."""

    def create_or_update_admin(
        self, db: Session, username: str, password: str
    ) -> AdminUser:
        """Create an admin user or replace its password hash."""
        normalized_username = self._normalize_username(username)
        self._validate_password(password)
        salt = secrets.token_bytes(SALT_BYTES)
        password_hash = self._hash_password(password, salt, PBKDF2_ITERATIONS)

        admin = (
            db.query(AdminUser)
            .filter(AdminUser.username == normalized_username)
            .first()
        )
        if admin is None:
            admin = AdminUser(username=normalized_username)
            db.add(admin)

        admin.password_salt = base64.b64encode(salt).decode("ascii")
        admin.password_hash = base64.b64encode(password_hash).decode("ascii")
        admin.password_iterations = PBKDF2_ITERATIONS
        admin.updated_at = _utc_now()
        db.commit()
        db.refresh(admin)
        return admin

    def authenticate_admin(
        self, db: Session, username: str, password: str | None
    ) -> AdminUser | None:
        """Return the admin user when credentials are valid."""
        if not password:
            return None
        normalized_username = self._normalize_username(username)
        admin = (
            db.query(AdminUser)
            .filter(AdminUser.username == normalized_username)
            .first()
        )
        if admin is None:
            return None

        try:
            salt = base64.b64decode(admin.password_salt.encode("ascii"))
            expected_hash = base64.b64decode(admin.password_hash.encode("ascii"))
        except ValueError:
            return None

        candidate_hash = self._hash_password(
            password, salt, admin.password_iterations
        )
        if not hmac.compare_digest(candidate_hash, expected_hash):
            return None
        return admin

    def create_admin_session(self, db: Session, admin: AdminUser) -> tuple[str, datetime]:
        """Create a persisted session and return the raw cookie token."""
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        expires_at = _utc_now() + timedelta(days=SESSION_DAYS)
        db.add(
            AdminSession(
                admin_user_id=admin.id,
                token_hash=self._hash_session_token(token),
                expires_at=expires_at,
            )
        )
        db.commit()
        return token, expires_at

    def get_admin_for_session(self, db: Session, token: str | None) -> AdminUser | None:
        """Resolve a cookie token to an admin user when the session is active."""
        if not token:
            return None
        session = (
            db.query(AdminSession)
            .filter(AdminSession.token_hash == self._hash_session_token(token))
            .first()
        )
        if session is None:
            return None
        if session.expires_at <= _utc_now():
            db.delete(session)
            db.commit()
            return None
        return session.admin_user

    def delete_admin_session(self, db: Session, token: str | None) -> None:
        """Delete an admin session by raw cookie token."""
        if not token:
            return
        session = (
            db.query(AdminSession)
            .filter(AdminSession.token_hash == self._hash_session_token(token))
            .first()
        )
        if session is None:
            return
        db.delete(session)
        db.commit()

    def count_admins(self, db: Session) -> int:
        """Return number of configured admin users."""
        return db.query(AdminUser).count()

    @staticmethod
    def _hash_password(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac(
            PBKDF2_ALGORITHM,
            password.encode("utf-8"),
            salt,
            iterations,
        )

    @staticmethod
    def _hash_session_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_username(username: str) -> str:
        normalized = username.strip().casefold()
        if not normalized:
            raise ValueError("Username is required")
        return normalized

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters")


def _utc_now() -> datetime:
    """Return a naive UTC datetime for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
