"""Shared route authentication dependencies."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from services.auth_service import ADMIN_SESSION_COOKIE, AuthService

auth_service = AuthService()


def get_admin_user(request: Request, db: Session = Depends(get_db)):
    """Return the current admin user, or None for guests."""
    return auth_service.get_admin_for_session(
        db, request.cookies.get(ADMIN_SESSION_COOKIE)
    )


def require_admin_user(request: Request, db: Session = Depends(get_db)):
    """Require a valid admin session."""
    admin = get_admin_user(request, db)
    if admin is None:
        raise HTTPException(status_code=403, detail="Admin session required")
    return admin
