from .common import *


def receive_non_ping(websocket):
    """Receive the next non-heartbeat websocket message."""
    message = websocket.receive_json()
    while message["type"] == "ping":
        websocket.send_json({"type": "pong"})
        message = websocket.receive_json()
    return message


def register_stage_websocket(websocket, stage_id: str, stage_name: str = "Projector"):
    """Subscribe and register a stage display websocket."""
    subscribe_websocket(websocket, "stage")
    clock_state = receive_non_ping(websocket)
    assert clock_state["type"] == "stage_clock_subscribers_update"
    websocket.send_json(
        {
            "type": "stage_presence_hello",
            "data": {"stage_id": stage_id, "stage_name": stage_name},
            "timestamp": 123,
        }
    )


def create_lyrics_preset(client, name: str = "TV Pink") -> int:
    """Create a shared lyrics preset and return its id."""
    response = client.post(
        "/api/lyrics-presets/",
        json={"name": name, "settings": {"sizeVw": 4.5, "lineWidthPct": 85}},
    )
    assert response.status_code == 200
    return response.json()["id"]



def test_websocket_connect_and_receive_connected_message(client):
    """WebSocket endpoint should accept connections and send initial connected payload."""
    with client.websocket_connect("/api/queue/ws") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "connected"
        assert "connection_count" in message["data"]
        assert "stage_state" in message["data"]
        assert message["data"]["stage_state"]["lyrics_enabled"] is True
        assert isinstance(message["data"]["stage_state"]["sync_version"], int)

def test_websocket_presence_hello_returns_snapshot(client):
    """Presence hello should register a queue viewer and return a snapshot."""
    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        websocket.send_json(
            {
                "type": "presence_hello",
                "data": {
                    "guest_id": "guest-1",
                    "display_name": "Alex",
                    "tab_id": "tab-1",
                    "page": "queue",
                },
            }
        )

        snapshot = websocket.receive_json()
        assert snapshot["type"] == "presence_snapshot"
        assert snapshot["data"]["users"][0]["display_name"] == "Alex"


def test_websocket_stage_presence_registers_and_queue_can_refresh(client):
    """Stage displays should be discoverable by queue clients."""
    with client.websocket_connect("/api/queue/ws") as queue_socket:
        assert queue_socket.receive_json()["type"] == "connected"
        subscribe_websocket(queue_socket, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            register_stage_websocket(stage_socket, "stage-tv", "TV")

            snapshot = receive_non_ping(queue_socket)
            assert snapshot["type"] == "stage_presence_snapshot"
            assert snapshot["data"]["stages"][0]["stage_id"] == "stage-tv"
            assert snapshot["data"]["stages"][0]["stage_name"] == "TV"

            queue_socket.send_json({"type": "stage_presence_request", "data": {}, "timestamp": 124})
            refreshed = receive_non_ping(queue_socket)
            assert refreshed["type"] == "stage_presence_snapshot"
            assert refreshed["data"]["stages"][0]["connection_count"] == 1


def test_websocket_stage_presence_falls_back_to_stage_id_label(client):
    """Unnamed stage displays should still expose a distinguishable fallback label."""
    with client.websocket_connect("/api/queue/ws") as queue_socket:
        assert queue_socket.receive_json()["type"] == "connected"
        subscribe_websocket(queue_socket, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            subscribe_websocket(stage_socket, "stage")
            stage_socket.send_json(
                {
                    "type": "stage_presence_hello",
                    "data": {"stage_id": "stage-tv-4f2a", "stage_name": "   "},
                    "timestamp": 123,
                }
            )

            snapshot = receive_non_ping(queue_socket)
            assert snapshot["type"] == "stage_presence_snapshot"
            assert snapshot["data"]["stages"][0]["stage_name"] == "Stage 4F2A"


def test_websocket_targeted_lyrics_settings_requires_admin(client):
    """Remote lyrics style application should be admin-only."""
    with client.websocket_connect("/api/queue/ws") as sender:
        assert sender.receive_json()["type"] == "connected"
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            register_stage_websocket(stage_socket, "stage-tv", "TV")
            receive_non_ping(sender)

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "apply_lyrics_settings",
                        "source": "queue",
                        "target_stage_id": "stage-tv",
                        "lyrics_enabled": True,
                        "background_media_enabled": False,
                        "size_vw": 4.5,
                        "line_width_pct": 85,
                    },
                    "timestamp": 123,
                }
            )

            error = receive_non_ping(sender)
            assert error["type"] == "error"
            assert error["data"]["detail"] == "Admin session required for lyrics settings"


def test_websocket_background_toggle_requires_admin(client):
    """Remote background toggles should be admin-only."""
    with client.websocket_connect("/api/queue/ws") as sender:
        assert sender.receive_json()["type"] == "connected"
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            register_stage_websocket(stage_socket, "stage-tv", "TV")
            receive_non_ping(sender)

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "set_background_media_enabled",
                        "source": "queue",
                        "target_stage_id": "stage-tv",
                        "background_media_enabled": False,
                    },
                    "timestamp": 123,
                }
            )

            error = receive_non_ping(sender)
            assert error["type"] == "error"
            assert error["data"]["detail"] == "Admin session required for background settings"


def test_websocket_targeted_lyrics_settings_auto_targets_single_stage(client):
    """A single connected stage can receive lyrics settings without explicit target id."""
    authenticate_admin_client(client)
    preset_id = create_lyrics_preset(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        assert sender.receive_json()["type"] == "connected"
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            register_stage_websocket(stage_socket, "stage-tv", "TV")
            receive_non_ping(sender)

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "apply_lyrics_settings",
                        "source": "queue",
                        "lyrics_enabled": False,
                        "background_media_enabled": False,
                        "preset_id": preset_id,
                        "override": False,
                    },
                    "timestamp": 123,
                }
            )

            command = receive_non_ping(stage_socket)
            assert command["type"] == "stage_control_command"
            assert command["data"]["command"] == "apply_lyrics_settings"
            assert command["data"]["target_stage_id"] == "stage-tv"
            assert command["data"]["lyrics_enabled"] is False
            assert command["data"]["background_media_enabled"] is False
            assert command["data"]["preset_id"] == preset_id
            assert command["data"]["override"] is False


def test_websocket_targeted_lyrics_settings_override_keeps_manual_values(client):
    """Override mode should forward the manual lyric sizing values."""
    authenticate_admin_client(client)
    preset_id = create_lyrics_preset(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        assert sender.receive_json()["type"] == "connected"
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            register_stage_websocket(stage_socket, "stage-tv", "TV")
            receive_non_ping(sender)

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "apply_lyrics_settings",
                        "source": "queue",
                        "lyrics_enabled": True,
                        "background_media_enabled": False,
                        "preset_id": preset_id,
                        "override": True,
                        "size_vw": 5.2,
                        "line_width_pct": 90,
                    },
                    "timestamp": 123,
                }
            )

            command = receive_non_ping(stage_socket)
            assert command["type"] == "stage_control_command"
            assert command["data"]["command"] == "apply_lyrics_settings"
            assert command["data"]["target_stage_id"] == "stage-tv"
            assert command["data"]["override"] is True
            assert command["data"]["background_media_enabled"] is False
            assert command["data"]["size_vw"] == 5.2
            assert command["data"]["line_width_pct"] == 90


def test_websocket_targeted_lyrics_settings_requires_target_for_multiple_stages(client):
    """Multiple connected stages should force explicit target selection."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        assert sender.receive_json()["type"] == "connected"
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as first_stage:
            assert first_stage.receive_json()["type"] == "connected"
            register_stage_websocket(first_stage, "stage-tv", "TV")
            receive_non_ping(sender)
            with client.websocket_connect("/api/queue/ws") as second_stage:
                assert second_stage.receive_json()["type"] == "connected"
                register_stage_websocket(second_stage, "stage-phone", "Phone")
                receive_non_ping(sender)

                sender.send_json(
                    {
                        "type": "stage_command",
                        "data": {
                            "command": "apply_lyrics_settings",
                            "source": "queue",
                            "lyrics_enabled": True,
                        },
                        "timestamp": 123,
                    }
                )

                error = receive_non_ping(sender)
                assert error["type"] == "error"
                assert error["data"]["detail"] == "Lyrics settings require a target stage"


def test_websocket_targeted_lyrics_settings_validates_payload(client):
    """Remote lyrics settings should reject invalid preset and sizing payloads."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        assert sender.receive_json()["type"] == "connected"
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            register_stage_websocket(stage_socket, "stage-tv", "TV")
            receive_non_ping(sender)

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "apply_lyrics_settings",
                        "source": "queue",
                        "target_stage_id": "stage-tv",
                        "preset_id": 9999,
                    },
                    "timestamp": 123,
                }
            )
            missing = receive_non_ping(sender)
            assert missing["type"] == "error"
            assert missing["data"]["detail"] == "Lyrics preset not found"

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "apply_lyrics_settings",
                        "source": "queue",
                        "target_stage_id": "stage-tv",
                        "size_vw": 99,
                    },
                    "timestamp": 124,
                }
            )
            bad_size = receive_non_ping(sender)
            assert bad_size["type"] == "error"
            assert bad_size["data"]["detail"] == "size_vw must be between 3.2 and 8.8"


def test_websocket_lyrics_settings_ack_forwards_to_queue_clients(client):
    """Stage acknowledgements should be forwarded to queue clients."""
    with client.websocket_connect("/api/queue/ws") as queue_socket:
        assert queue_socket.receive_json()["type"] == "connected"
        subscribe_websocket(queue_socket, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            register_stage_websocket(stage_socket, "stage-tv", "TV")
            receive_non_ping(queue_socket)

            stage_socket.send_json(
                {
                    "type": "lyrics_settings_ack",
                    "data": {
                        "stage_id": "stage-tv",
                        "ok": True,
                        "preset_id": 1,
                        "override": False,
                        "background_media_enabled": False,
                        "applied_settings": {"backgroundMediaEnabled": False},
                    },
                    "timestamp": 123,
                }
            )

            ack = receive_non_ping(queue_socket)
            assert ack["type"] == "lyrics_settings_ack"
            assert ack["data"]["stage_id"] == "stage-tv"
            assert ack["data"]["ok"] is True
            assert ack["data"]["preset_id"] == 1
            assert ack["data"]["override"] is False
            assert ack["data"]["background_media_enabled"] is False
            assert ack["data"]["applied_settings"]["backgroundMediaEnabled"] is False


def test_websocket_stage_command_set_background_media_enabled_broadcasts_target_command(client):
    """Background toggle should broadcast a targeted stage command."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        assert sender.receive_json()["type"] == "connected"
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as stage_socket:
            assert stage_socket.receive_json()["type"] == "connected"
            register_stage_websocket(stage_socket, "stage-tv", "TV")
            receive_non_ping(sender)

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "set_background_media_enabled",
                        "source": "queue",
                        "target_stage_id": "stage-tv",
                        "background_media_enabled": False,
                    },
                    "timestamp": 123,
                }
            )

            command = receive_non_ping(stage_socket)
            assert command["type"] == "stage_control_command"
            assert command["data"]["command"] == "set_background_media_enabled"
            assert command["data"]["target_stage_id"] == "stage-tv"
            assert command["data"]["background_media_enabled"] is False

def test_websocket_presence_join_update_and_leave(client):
    """Presence lifecycle events should broadcast to other queue viewers."""
    with client.websocket_connect("/api/queue/ws") as first:
        assert first.receive_json()["type"] == "connected"
        first.send_json(
            {
                "type": "presence_hello",
                "data": {
                    "guest_id": "guest-1",
                    "display_name": "Alex",
                    "tab_id": "tab-1",
                    "page": "queue",
                },
            }
        )
        assert first.receive_json()["type"] == "presence_snapshot"

        with client.websocket_connect("/api/queue/ws") as second:
            assert second.receive_json()["type"] == "connected"
            second.send_json(
                {
                    "type": "presence_hello",
                    "data": {
                        "guest_id": "guest-2",
                        "display_name": "Blair",
                        "tab_id": "tab-2",
                        "page": "queue",
                    },
                }
            )
            assert second.receive_json()["type"] == "presence_snapshot"

            joined = first.receive_json()
            while joined["type"] == "ping":
                first.send_json({"type": "pong"})
                joined = first.receive_json()
            assert joined["type"] == "user_joined"
            assert joined["data"]["display_name"] == "Blair"

            second.send_json(
                {
                    "type": "presence_update",
                    "data": {
                        "guest_id": "guest-2",
                        "display_name": "Blair Renamed",
                        "tab_id": "tab-2",
                        "page": "queue",
                    },
                }
            )

            assert second.receive_json()["type"] == "presence_snapshot"
            updated = first.receive_json()
            while updated["type"] == "ping":
                first.send_json({"type": "pong"})
                updated = first.receive_json()
            assert updated["type"] == "user_updated"
            assert updated["data"]["display_name"] == "Blair Renamed"

        left = first.receive_json()
        while left["type"] == "ping":
            first.send_json({"type": "pong"})
            left = first.receive_json()
        assert left["type"] == "user_left"
        assert left["data"]["guest_id"] == "guest-2"

def test_websocket_presence_deduplicates_multiple_tabs(client):
    """Same guest in two tabs should only leave after the final disconnect."""
    with client.websocket_connect("/api/queue/ws") as observer:
        assert observer.receive_json()["type"] == "connected"
        observer.send_json(
            {
                "type": "presence_hello",
                "data": {
                    "guest_id": "observer",
                    "display_name": "Observer",
                    "tab_id": "obs-1",
                    "page": "queue",
                },
            }
        )
        assert observer.receive_json()["type"] == "presence_snapshot"

        with client.websocket_connect("/api/queue/ws") as first_tab:
            assert first_tab.receive_json()["type"] == "connected"
            first_tab.send_json(
                {
                    "type": "presence_hello",
                    "data": {
                        "guest_id": "guest-1",
                        "display_name": "Alex",
                        "tab_id": "tab-1",
                        "page": "queue",
                    },
                }
            )
            assert first_tab.receive_json()["type"] == "presence_snapshot"
            joined = observer.receive_json()
            while joined["type"] == "ping":
                observer.send_json({"type": "pong"})
                joined = observer.receive_json()
            assert joined["type"] == "user_joined"

            with client.websocket_connect("/api/queue/ws") as second_tab:
                assert second_tab.receive_json()["type"] == "connected"
                second_tab.send_json(
                    {
                        "type": "presence_hello",
                        "data": {
                            "guest_id": "guest-1",
                            "display_name": "Alex",
                            "tab_id": "tab-2",
                            "page": "queue",
                        },
                    }
                )
                snapshot = second_tab.receive_json()
                assert snapshot["type"] == "presence_snapshot"
                guest = next(
                    user for user in snapshot["data"]["users"] if user["guest_id"] == "guest-1"
                )
                assert guest["connection_count"] == 2

            response = client.get("/api/queue/presence")
            assert response.status_code == 200
            users = response.json()["users"]
            guest = next(user for user in users if user["guest_id"] == "guest-1")
            assert guest["connection_count"] == 1

        left = observer.receive_json()
        while left["type"] == "ping":
            observer.send_json({"type": "pong"})
            left = observer.receive_json()
        assert left["type"] == "user_left"
        assert left["data"]["guest_id"] == "guest-1"

def test_websocket_broadcasts_queue_item_added_event(client):
    """Adding a queue item should broadcast queue_item_added to websocket clients."""
    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"
        subscribe_websocket(websocket, "queue")

        response = client.post(
            "/api/queue/",
            json={"youtube_id": "ws-add", "title": "WS Add", "is_karaoke": False},
        )
        assert response.status_code == 200
        item = response.json()

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "queue_item_added"
        assert event["data"]["id"] == item["id"]
        assert event["data"]["title"] == "WS Add"

def test_websocket_broadcasts_queue_item_removed_event(client):
    """Deleting a queue item should broadcast queue_item_removed."""
    authenticate_admin_client(client)
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-del", "title": "WS Remove", "is_karaoke": False},
    ).json()

    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"
        subscribe_websocket(websocket, "queue")

        response = client.delete(f"/api/queue/{created['id']}")
        assert response.status_code == 200

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "queue_item_removed"
        assert event["data"]["id"] == created["id"]

def test_websocket_broadcasts_queue_item_updated_on_move(client):
    """Reordering a queue item should broadcast queue_item_updated."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-move-1", "title": "WS Move 1", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-move-2", "title": "WS Move 2", "is_karaoke": False},
    ).json()
    third = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-move-3", "title": "WS Move 3", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        first_row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"
        subscribe_websocket(websocket, "queue")

        response = client.post(f"/api/queue/{third['id']}/move", json={"direction": "up"})
        assert response.status_code == 200

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "queue_item_updated"
        assert event["data"]["id"] == third["id"]
        assert event["data"]["position"] > first["position"]
        assert event["data"]["position"] < second["position"]

def test_websocket_broadcasts_current_item_changed_on_skip(client):
    """Skipping current item should broadcast current_item_changed."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-skip-1", "title": "WS Skip 1", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-skip-2", "title": "WS Skip 2", "is_karaoke": False},
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

    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"
        subscribe_websocket(websocket, "queue")

        response = client.post("/api/queue/skip")
        assert response.status_code == 200

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "current_item_changed"
        assert event["data"]["id"] == second["id"]
        assert event["data"]["previous_id"] == first["id"]

def test_websocket_broadcasts_queue_cleared(client):
    """Clearing queue should broadcast queue_cleared."""
    authenticate_admin_client(client)
    client.post(
        "/api/queue/",
        json={"youtube_id": "ws-clear-1", "title": "WS Clear 1", "is_karaoke": False},
    )
    client.post(
        "/api/queue/",
        json={"youtube_id": "ws-clear-2", "title": "WS Clear 2", "is_karaoke": False},
    )

    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"
        subscribe_websocket(websocket, "queue")

        response = client.post("/api/queue/clear")
        assert response.status_code == 200

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "queue_cleared"

def test_websocket_stage_command_pause_broadcasts_control_and_state(client):
    """Pause stage command should broadcast control command and paused state."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "pause", "source": "queue"},
                    "timestamp": 123,
                }
            )

            control_event = receiver.receive_json()
            if control_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                control_event = receiver.receive_json()
            assert control_event["type"] == "stage_control_command"
            assert control_event["data"]["command"] == "pause"
            assert control_event["data"]["source"] == "queue"

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["is_paused"] is True
            assert state_event["data"]["vocals_enabled"] is True
            assert state_event["data"]["vocals_volume"] == 1.0
            assert state_event["data"]["lyrics_enabled"] is True

def test_websocket_stage_command_set_lyrics_enabled_broadcasts_state(client):
    """Lyrics toggle should broadcast a stage state update."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "set_lyrics_enabled",
                        "source": "queue",
                        "lyrics_enabled": False,
                    },
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["lyrics_enabled"] is False
            assert state_event["data"]["vocals_enabled"] is True

def test_websocket_guest_cannot_control_other_guest_current_item(client):
    """Guest websocket stage commands should be denied for other guests' songs."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-guest-denied", "title": "WS Guest Denied", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    client.cookies.set("karaoke_guest_id", "guest-other")
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        sender.send_json(
            {
                "type": "stage_command",
                "data": {"command": "pause", "source": "queue"},
                "timestamp": 123,
            }
        )

        response = sender.receive_json()
        if response["type"] == "ping":
            sender.send_json({"type": "pong"})
            response = sender.receive_json()
        assert response["type"] == "error"
        assert response["data"]["detail"] == "Not allowed to control this stage item"

def test_websocket_guest_can_control_owned_current_item(client):
    """Guest websocket stage commands should be allowed for their own current song."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-guest-owned", "title": "WS Guest Owned", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "set_lyrics_enabled",
                        "source": "queue",
                        "lyrics_enabled": False,
                    },
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["lyrics_enabled"] is False

def test_websocket_delegated_guest_can_control_admin_queued_current_item(client):
    """A delegated guest should be authorized for websocket stage commands."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    first = client.post(
        "/api/queue/",
        json={
            "youtube_id": "ws-delegated-owned",
            "title": "WS Delegated Owned",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-owner",
        },
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    client.cookies.pop(ADMIN_SESSION_COOKIE, None)
    client.cookies.set("karaoke_guest_id", "guest-owner")
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "set_lyrics_enabled",
                        "source": "queue",
                        "lyrics_enabled": False,
                    },
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["lyrics_enabled"] is False

def test_websocket_stage_command_seek_broadcasts_control_and_state(client):
    """Seek stage command should broadcast target timestamp and paused state."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "seek",
                        "source": "queue",
                        "seek_time": 42.5,
                        "is_paused": False,
                    },
                    "timestamp": 123,
                }
            )

            control_event = receiver.receive_json()
            if control_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                control_event = receiver.receive_json()
            assert control_event["type"] == "stage_control_command"
            assert control_event["data"]["command"] == "seek"
            assert control_event["data"]["source"] == "queue"
            assert control_event["data"]["seek_time"] == 42.5
            assert control_event["data"]["is_paused"] is False

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["is_paused"] is False
            assert state_event["data"]["current_time"] == 42.5

def test_websocket_stage_time_update_broadcasts_only_to_lyrics_viewers(client):
    """Stage time updates should refresh lyrics viewers without noisy queue/stage fanout."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "stage")
        clock_state = receive_non_ping(sender)
        assert clock_state["type"] == "stage_clock_subscribers_update"
        assert clock_state["data"]["clock_enabled"] is False
        with client.websocket_connect("/api/queue/ws") as queue_receiver:
            queue_receiver.receive_json()
            subscribe_websocket(queue_receiver, "queue")
            with client.websocket_connect("/api/queue/ws") as lyrics_receiver:
                lyrics_receiver.receive_json()
                subscribe_websocket(lyrics_receiver, "lyrics_viewer")
                clock_state = receive_non_ping(sender)
                assert clock_state["type"] == "stage_clock_subscribers_update"
                assert clock_state["data"]["clock_enabled"] is True

                sender.send_json(
                    {
                        "type": "stage_time_update",
                        "data": {"current_time": 18.25, "is_paused": True, "source": "stage"},
                        "timestamp": 123,
                    }
                )
                sender.send_json(
                    {
                        "type": "stage_command",
                        "data": {"command": "pause", "source": "stage"},
                        "timestamp": 124,
                    }
                )

                queue_event = receive_non_ping(queue_receiver)
                assert queue_event["type"] == "stage_control_command"
                assert queue_event["data"]["command"] == "pause"

                stage_event = receive_non_ping(sender)
                assert stage_event["type"] == "stage_control_command"
                assert stage_event["data"]["command"] == "pause"

                lyrics_event = receive_non_ping(lyrics_receiver)
                assert lyrics_event["type"] == "stage_time_update"
                assert lyrics_event["data"]["current_time"] == 18.25
                assert lyrics_event["data"]["is_paused"] is True

def test_websocket_stage_clock_subscriber_updates_follow_lyrics_viewers(client):
    """Stage clients should know when steady playback clock ticks are useful."""
    with client.websocket_connect("/api/queue/ws") as stage_socket:
        assert stage_socket.receive_json()["type"] == "connected"
        subscribe_websocket(stage_socket, "stage")

        clock_state = receive_non_ping(stage_socket)
        assert clock_state["type"] == "stage_clock_subscribers_update"
        assert clock_state["data"] == {"lyrics_viewer_count": 0, "clock_enabled": False}

        with client.websocket_connect("/api/queue/ws") as lyrics_socket:
            assert lyrics_socket.receive_json()["type"] == "connected"
            subscribe_websocket(lyrics_socket, "lyrics_viewer")

            clock_state = receive_non_ping(stage_socket)
            assert clock_state["type"] == "stage_clock_subscribers_update"
            assert clock_state["data"] == {"lyrics_viewer_count": 1, "clock_enabled": True}

        clock_state = receive_non_ping(stage_socket)
        assert clock_state["type"] == "stage_clock_subscribers_update"
        assert clock_state["data"] == {"lyrics_viewer_count": 0, "clock_enabled": False}

def test_websocket_stage_time_update_requires_admin(client):
    """Guest clients should not be able to spoof authoritative stage time."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "stage")
        clock_state = receive_non_ping(sender)
        assert clock_state["type"] == "stage_clock_subscribers_update"
        sender.send_json(
            {
                "type": "stage_time_update",
                "data": {"current_time": 18.25, "is_paused": True, "source": "stage"},
                "timestamp": 123,
            }
        )

        response = sender.receive_json()
        if response["type"] == "ping":
            sender.send_json({"type": "pong"})
            response = sender.receive_json()
        assert response["type"] == "error"
        assert response["data"]["detail"] == "Admin session required for stage time updates"

def test_websocket_stage_command_seek_rejects_invalid_time(client):
    """Invalid seek_time values should return websocket error."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        sender.send_json(
            {
                "type": "stage_command",
                "data": {"command": "seek", "source": "queue", "seek_time": -1},
                "timestamp": 123,
            }
        )

        response = sender.receive_json()
        if response["type"] == "ping":
            sender.send_json({"type": "pong"})
            response = sender.receive_json()
        assert response["type"] == "error"
        assert "seek_time must be a non-negative finite number" in response["data"]["detail"]

def test_websocket_stage_command_seek_relative_broadcasts_control_only(client):
    """Relative seek commands should be resolved by the stage client."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "stage")
            clock_state = receive_non_ping(receiver)
            assert clock_state["type"] == "stage_clock_subscribers_update"

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "seek_relative",
                        "source": "queue",
                        "offset_seconds": 5,
                        "is_paused": False,
                    },
                    "timestamp": 123,
                }
            )

            control_event = receive_non_ping(receiver)
            assert control_event["type"] == "stage_control_command"
            assert control_event["data"]["command"] == "seek_relative"
            assert control_event["data"]["source"] == "queue"
            assert control_event["data"]["offset_seconds"] == 5
            assert control_event["data"]["is_paused"] is False

def test_websocket_stage_command_seek_relative_rejects_invalid_offset(client):
    """Relative seek commands should require a finite numeric offset."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        sender.send_json(
            {
                "type": "stage_command",
                "data": {"command": "seek_relative", "source": "queue", "offset_seconds": "5"},
                "timestamp": 123,
            }
        )

        response = receive_non_ping(sender)
        assert response["type"] == "error"
        assert response["data"]["detail"] == "seek_relative requires numeric offset_seconds"

def test_websocket_stage_command_resync_broadcasts_control(client):
    """Resync stage command should broadcast control command with a sync version."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "resync", "source": "queue"},
                    "timestamp": 123,
                }
            )

            control_event = receiver.receive_json()
            if control_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                control_event = receiver.receive_json()
            assert control_event["type"] == "stage_control_command"
            assert control_event["data"]["command"] == "resync"
            assert control_event["data"]["source"] == "queue"
            assert isinstance(control_event["data"]["sync_version"], int)

def test_websocket_stage_command_resync_accepts_optional_timeline(client):
    """Resync can carry a concrete timeline when sent by the stage client."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "stage")
        clock_state = receive_non_ping(sender)
        assert clock_state["type"] == "stage_clock_subscribers_update"
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "stage")
            clock_state = receive_non_ping(receiver)
            assert clock_state["type"] == "stage_clock_subscribers_update"
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "resync",
                        "source": "stage",
                        "seek_time": 12.75,
                        "is_paused": False,
                    },
                    "timestamp": 123,
                }
            )

            control_event = receiver.receive_json()
            if control_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                control_event = receiver.receive_json()
            assert control_event["type"] == "stage_control_command"
            assert control_event["data"]["command"] == "resync"
            assert control_event["data"]["source"] == "stage"
            assert control_event["data"]["seek_time"] == 12.75
            assert control_event["data"]["is_paused"] is False
            assert isinstance(control_event["data"]["sync_version"], int)

def test_websocket_stage_command_set_vocals_enabled_broadcasts_state(client):
    """Vocals enabled command should broadcast updated stage mix state."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "set_vocals_enabled", "source": "queue", "vocals_enabled": False},
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["vocals_enabled"] is False
            assert state_event["data"]["vocals_volume"] == 1.0

def test_websocket_stage_command_set_vocals_volume_broadcasts_state(client):
    """Vocals volume command should broadcast updated stage mix state."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "set_vocals_enabled", "source": "queue", "vocals_enabled": True},
                    "timestamp": 122,
                }
            )
            bootstrap_event = receiver.receive_json()
            if bootstrap_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                bootstrap_event = receiver.receive_json()
            assert bootstrap_event["type"] == "stage_state_update"
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "set_vocals_volume", "source": "queue", "vocals_volume": 0.35},
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["vocals_enabled"] is True
            assert state_event["data"]["vocals_volume"] == 0.35

def test_websocket_stage_command_set_vocals_volume_rejects_out_of_bounds(client):
    """Out-of-range vocals volume should return websocket error and not broadcast state."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        sender.send_json(
            {
                "type": "stage_command",
                "data": {"command": "set_vocals_volume", "source": "queue", "vocals_volume": 2.0},
                "timestamp": 123,
            }
        )

        response = sender.receive_json()
        if response["type"] == "ping":
            sender.send_json({"type": "pong"})
            response = sender.receive_json()
        assert response["type"] == "error"
        assert "vocals_volume must be between 0.0 and 1.0" in response["data"]["detail"]

def test_websocket_stage_command_skip_broadcasts_and_changes_current(client):
    """Skip stage command should advance queue and broadcast item change."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-stage-skip-1", "title": "WS Stage Skip 1", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-stage-skip-2", "title": "WS Stage Skip 2", "is_karaoke": False},
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

    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        subscribe_websocket(sender, "queue")
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            subscribe_websocket(receiver, "queue")
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "skip", "source": "queue"},
                    "timestamp": 123,
                }
            )

            stage_control_event = None
            current_changed_event = None
            for _ in range(6):
                event = receiver.receive_json()
                if event["type"] == "ping":
                    receiver.send_json({"type": "pong"})
                    continue
                if event["type"] == "stage_control_command":
                    stage_control_event = event
                if event["type"] == "current_item_changed":
                    current_changed_event = event
                if stage_control_event and current_changed_event:
                    break

            assert stage_control_event is not None
            assert stage_control_event["data"]["command"] == "skip"
            assert stage_control_event["data"]["source"] == "queue"
            assert current_changed_event is not None
            assert current_changed_event["data"]["id"] == second["id"]
            assert current_changed_event["data"]["previous_id"] == first["id"]

    current = client.get("/api/queue/current")
    assert current.status_code == 200
    current_payload = current.json()
    assert current_payload is not None
    assert current_payload["id"] == second["id"]
