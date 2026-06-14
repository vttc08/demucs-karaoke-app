from .common import *



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
    first_salt = first.password_salt

    updated = service.create_or_update_admin(
        db_session, "ADMIN", "another correct password"
    )

    assert updated.id == first.id
    assert updated.password_salt != first_salt
    assert db_session.query(AdminUser).count() == 1
    assert service.authenticate_admin(
        db_session, "admin", "another correct password"
    )
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
