from .common import *
from concurrent.futures import ThreadPoolExecutor
from services.login_attempt_service import LoginAttemptLimiter


def test_login_attempt_limiter_counts_ip_and_account_before_verification(monkeypatch):
    limiter = LoginAttemptLimiter()
    monkeypatch.setattr("services.login_attempt_service.time.monotonic", lambda: 100.0)

    for index in range(limiter.IP_LIMIT):
        assert limiter.reserve("192.0.2.1", f"user-{index}") == 0
    assert limiter.reserve("192.0.2.1", "another-user") == 60

    for index in range(limiter.ACCOUNT_LIMIT):
        assert limiter.reserve(f"192.0.2.{index + 2}", "ADMIN") == 0
    assert limiter.reserve("198.51.100.1", "admin") == 300

    monkeypatch.setattr("services.login_attempt_service.time.monotonic", lambda: 401.0)
    assert limiter.reserve("192.0.2.1", "admin") == 0


def test_login_attempt_limiter_bounds_stored_keys(monkeypatch):
    limiter = LoginAttemptLimiter()
    limiter.MAX_KEYS = 2
    monkeypatch.setattr("services.login_attempt_service.time.monotonic", lambda: 100.0)

    assert limiter.reserve("192.0.2.1", "admin") == 0
    assert limiter.reserve("198.51.100.1", "other") == limiter.IP_WINDOW_SECONDS
    assert len(limiter._attempts) == 2


def test_login_attempt_limiter_reservations_are_atomic(monkeypatch):
    limiter = LoginAttemptLimiter()
    monkeypatch.setattr("services.login_attempt_service.time.monotonic", lambda: 100.0)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda index: limiter.reserve("192.0.2.1", f"user-{index}"), range(20)))

    assert results.count(0) == limiter.IP_LIMIT
    assert results.count(60) == 10


def test_blocked_ip_is_rejected_before_account_key_work(monkeypatch):
    limiter = LoginAttemptLimiter()
    monkeypatch.setattr("services.login_attempt_service.time.monotonic", lambda: 100.0)
    for _ in range(limiter.IP_LIMIT):
        assert limiter.reserve("192.0.2.1", "admin") == 0

    with patch("services.login_attempt_service.hashlib.sha256", side_effect=AssertionError("account hashed")):
        assert limiter.reserve("192.0.2.1", "unexpected name") == 60


def test_logout_token_is_bound_to_admin_session():
    service = AuthService()
    token = service.logout_csrf_token("session-one")

    assert token
    assert token != "session-one"
    assert service.valid_logout_csrf_token("session-one", token)
    assert not service.valid_logout_csrf_token("session-two", token)
    assert not service.valid_logout_csrf_token(None, token)



def test_auth_service_stores_salted_password_hash(db_session):
    """Admin passwords should be stored as salted hashes, not plaintext."""
    service = AuthService()

    admin = service.create_or_update_admin(
        db_session, "Admin", "correct horse battery staple"
    )

    assert admin.username == "admin"
    assert admin.password_hash != "correct horse battery staple"
    assert admin.password_salt
    assert admin.password_iterations >= 600_000
    assert service.authenticate_admin(
        db_session, "ADMIN", "correct horse battery staple"
    ).id == admin.id
    assert service.authenticate_admin(db_session, "admin", "wrong password") is None

def test_auth_service_rotates_salt_when_password_changes(db_session):
    """Password updates should replace the salt and invalidate the old password."""
    service = AuthService()
    first = service.create_or_update_admin(
        db_session, "admin", "correct horse battery staple"
    )
    old_token, _ = service.create_admin_session(db_session, first)
    first_salt = first.password_salt

    updated = service.create_or_update_admin(
        db_session, "ADMIN", "another correct password"
    )

    assert updated.id == first.id
    assert updated.password_salt != first_salt
    assert db_session.query(AdminUser).count() == 1
    assert service.get_admin_for_session(db_session, old_token) is None
    assert service.authenticate_admin(
        db_session, "admin", "another correct password"
    )
    new_token, _ = service.create_admin_session(db_session, updated)
    assert service.get_admin_for_session(db_session, new_token).id == updated.id
    assert service.authenticate_admin(
        db_session, "admin", "correct horse battery staple"
    ) is None

def test_auth_service_resolves_and_expires_sessions(db_session):
    """Admin sessions should resolve by token and support explicit deletion."""
    service = AuthService()
    admin = service.create_or_update_admin(
        db_session, "admin", "correct horse battery staple"
    )
    token, _ = service.create_admin_session(db_session, admin)

    assert service.get_admin_for_session(db_session, token).id == admin.id
    service.delete_admin_session(db_session, token)
    assert service.get_admin_for_session(db_session, token) is None
