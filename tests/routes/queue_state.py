from .common import *



def test_skip_current_promotes_next_ready(client):
    """Test skip endpoint removes current item and promotes next."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "first", "title": "First", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "second", "title": "Second", "is_karaoke": True},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        second_row = db.query(QueueItem).filter(QueueItem.id == second["id"]).first()
        first_row.status = QueueStatus.PLAYING
        second_row.status = QueueStatus.READY
        db.commit()
    finally:
        db.close()

    response = client.post("/api/queue/skip")
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data["id"] == second["id"]
    assert data["status"] == "playing"

    db = TestingSessionLocal()
    try:
        assert db.query(QueueItem).filter(QueueItem.id == first["id"]).first() is None
    finally:
        db.close()

def test_skip_current_without_next_returns_none(client):
    """Test skip endpoint when only current playing exists."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "only", "title": "Only", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        first_row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    response = client.post("/api/queue/skip")
    assert response.status_code == 200
    assert response.json() is None

def test_guest_cannot_skip_other_guest_current_item(client):
    """Guest users should not be able to skip a current song they did not queue."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-rest-skip-denied", "title": "Guest Rest Skip Denied", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    client.cookies.set("karaoke_guest_id", "guest-other")
    response = client.post("/api/queue/skip")

    assert response.status_code == 403
    assert response.json()["detail"] == "Not allowed to control this stage item"
    with TestingSessionLocal() as db:
        assert db.query(QueueItem).filter(QueueItem.id == first["id"]).first() is not None

def test_guest_can_skip_owned_current_item(client):
    """Guest users may skip their own currently playing song."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-rest-skip-owned", "title": "Guest Rest Skip Owned", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    response = client.post("/api/queue/skip")

    assert response.status_code == 200
    assert response.json() is None
    with TestingSessionLocal() as db:
        assert db.query(QueueItem).filter(QueueItem.id == first["id"]).first() is None

def test_delegated_guest_can_skip_admin_queued_current_item(client):
    """A delegated guest should control the admin-queued current item."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    client.cookies.set("karaoke_queue_tab_id", "tab-admin-device")
    created = client.post(
        "/api/queue/",
        json={
            "youtube_id": "delegated-rest-skip-owned",
            "title": "Delegated REST Skip Owned",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-owner",
        },
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    client.cookies.pop(ADMIN_SESSION_COOKIE, None)
    client.cookies.set("karaoke_guest_id", "guest-owner")
    response = client.post("/api/queue/skip")

    assert response.status_code == 200
    assert response.json() is None

def test_complete_current_requires_admin(client):
    """Guests should not be able to complete the current stage item."""
    response = client.post("/api/queue/complete-current")
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"

def test_complete_current_promotes_next_ready(client):
    """Test complete-current endpoint removes current item and promotes next."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "first-c", "title": "First C", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "second-c", "title": "Second C", "is_karaoke": True},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        second_row = db.query(QueueItem).filter(QueueItem.id == second["id"]).first()
        first_row.status = QueueStatus.PLAYING
        second_row.status = QueueStatus.READY
        db.commit()
    finally:
        db.close()

    response = client.post("/api/queue/complete-current")
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data["id"] == second["id"]
    assert data["status"] == "playing"

    db = TestingSessionLocal()
    try:
        assert db.query(QueueItem).filter(QueueItem.id == first["id"]).first() is None
    finally:
        db.close()

def test_complete_current_without_next_returns_none(client):
    """Test complete-current endpoint when only current playing exists."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "only-c", "title": "Only C", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        first_row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    response = client.post("/api/queue/complete-current")
    assert response.status_code == 200
    assert response.json() is None

def test_move_queue_item_requires_admin(client):
    """Guest users should not be able to reorder queue items."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-move", "title": "Guest Move", "is_karaoke": False},
    ).json()

    response = client.post(
        f"/api/queue/{created['id']}/move",
        json={"direction": "up"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"

def test_move_queue_item_reorders_queue_for_admin(client):
    """Admin reorder requests should update queue positions and ordering."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-move-1", "title": "Admin First", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-move-2", "title": "Admin Second", "is_karaoke": False},
    ).json()
    third = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-move-3", "title": "Admin Third", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        first_row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/queue/{third['id']}/move", json={"direction": "up"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == third["id"]
    assert payload["position"] > first["position"]
    assert payload["position"] < second["position"]

    response = client.get("/api/queue/")
    assert [item["title"] for item in response.json()] == ["Admin First", "Admin Third", "Admin Second"]


def test_drag_reorder_route_is_not_available(client):
    """Queue reordering is intentionally limited to the move-arrow endpoint."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "no-drag", "title": "No Drag", "is_karaoke": False},
    ).json()

    response = client.post(
        f"/api/queue/{created['id']}/reorder",
        json={"before_item_id": None},
    )

    assert response.status_code == 404


def test_queue_clear_route_requires_admin(client):
    """Guest users should not be able to clear queue items."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-del", "title": "Guest Delete", "is_karaoke": False},
    ).json()

    clear_response = client.post("/api/queue/clear")

    assert clear_response.status_code == 403
    assert clear_response.json()["detail"] == "Admin session required"

def test_get_queue_marks_can_remove_for_guest_owner(client):
    """Queue list should expose guest removal permissions per item."""
    client.cookies.set("karaoke_guest_id", "guest-123")
    own_item = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-own-api", "title": "Guest Own API", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-999")
    other_item = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-other-api", "title": "Guest Other API", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-123")
    response = client.get("/api/queue/")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    assert items[own_item["id"]]["can_remove"] is True
    assert items[other_item["id"]]["can_remove"] is False

def test_get_queue_marks_delegated_owner_permissions(client):
    """Queue list permissions should follow delegated guest ownership."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    delegated = client.post(
        "/api/queue/",
        json={
            "youtube_id": "delegated-queue-list",
            "title": "Delegated Queue List",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-target",
        },
    ).json()

    client.cookies.pop(ADMIN_SESSION_COOKIE, None)
    client.cookies.set("karaoke_guest_id", "guest-target")
    response = client.get("/api/queue/")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    assert items[delegated["id"]]["can_remove"] is True

    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    response = client.get("/api/queue/")
    items = {item["id"]: item for item in response.json()}
    assert items[delegated["id"]]["can_remove"] is False

def test_get_queue_marks_can_remove_for_admin(client):
    """Admin queue list should allow removal of all non-playing items."""
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-can-remove-1", "title": "Admin First", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-can-remove-2", "title": "Admin Second", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        playing = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        playing.status = QueueStatus.PLAYING
        db.commit()

    authenticate_admin_client(client)
    response = client.get("/api/queue/")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    assert items[first["id"]]["can_remove"] is False
    assert items[second["id"]]["can_remove"] is True

def test_guest_can_remove_owned_queue_item(client):
    """Guest users should be able to remove their own non-playing queue items."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-remove-own", "title": "Guest Remove Own", "is_karaoke": False},
    ).json()

    response = client.delete(f"/api/queue/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"status": "removed", "item_id": created["id"]}

def test_delegated_guest_can_remove_admin_queued_item(client):
    """A delegated guest should remove the admin-queued non-playing item."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    created = client.post(
        "/api/queue/",
        json={
            "youtube_id": "delegated-remove-own",
            "title": "Delegated Remove Own",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-owner",
        },
    ).json()

    client.cookies.pop(ADMIN_SESSION_COOKIE, None)
    client.cookies.set("karaoke_guest_id", "guest-owner")
    response = client.delete(f"/api/queue/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"status": "removed", "item_id": created["id"]}

def test_guest_cannot_remove_other_guest_queue_item(client):
    """Guest users should not be able to remove another guest's queue items."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-remove-other", "title": "Guest Remove Other", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-other")
    response = client.delete(f"/api/queue/{created['id']}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Not allowed to remove this queue item"

def test_guest_cannot_remove_owned_playing_queue_item(client):
    """Guest users should not be able to remove their own currently playing queue item."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-remove-playing", "title": "Guest Remove Playing", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        item = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        item.status = QueueStatus.PLAYING
        db.commit()

    response = client.delete(f"/api/queue/{created['id']}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot remove currently playing item"

def test_get_queue_presence_route_returns_users(client):
    """Presence route should expose the current in-memory roster."""
    from routes.queue import manager

    manager._queue_presence = {
        "guest-1": {
            "display_name": "Alex",
            "joined_at": "2026-05-07T00:00:00",
            "tab_ids": {"tab-1"},
        }
    }
    try:
        response = client.get("/api/queue/presence")
        assert response.status_code == 200
        payload = response.json()
        assert payload["users"][0]["guest_id"] == "guest-1"
        assert payload["users"][0]["display_name"] == "Alex"
        assert payload["users"][0]["connection_count"] == 1
    finally:
        manager._queue_presence.clear()
