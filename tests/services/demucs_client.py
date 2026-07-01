from .common import *


class _FakeAsyncResponse:
    def __init__(self, payload=None, content: bytes = b""):
        self._payload = payload or {}
        self.content = content
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeStreamResponse:
    def __init__(self, lines, *, status_code=200):
        self._lines = list(lines)
        self.status_code = status_code
        self.content = b""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeAsyncClient:
    def __init__(self, *, cancel_event=None, raise_cancel_on_get=False):
        self.cancel_event = cancel_event
        self.raise_cancel_on_get = raise_cancel_on_get
        self.deleted_jobs = []
        self.get_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        return _FakeAsyncResponse(
            {
                "job_id": "remote-job",
                "status": "queued",
                "progress_percent": 0,
                "progress_message": "Queued",
            }
        )

    async def get(self, url, **kwargs):
        self.get_calls += 1
        if self.raise_cancel_on_get:
            raise asyncio.CancelledError()
        if self.cancel_event is not None:
            self.cancel_event.set()
        return _FakeAsyncResponse(
            {
                "status": "running",
                "progress_percent": 5,
                "progress_message": "Running",
                "output_tail": [],
            }
        )

    async def delete(self, url, **kwargs):
        self.deleted_jobs.append(url.rsplit("/", 1)[-1])
        return _FakeAsyncResponse({"status": "canceled"})


def test_demucs_client_includes_api_key_on_sync_requests(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs.get("headers")
        return _FakeAsyncResponse({"status": "ok"})

    monkeypatch.setattr("services.demucs_client.httpx.get", fake_get)

    client = DemucsClient(api_url="http://demucs.local", api_key="shared-secret")
    result = client.health_check()

    assert seen["url"] == "http://demucs.local/health"
    assert seen["headers"]["X-API-Key"] == "shared-secret"
    assert result.healthy is True


def test_demucs_client_includes_api_key_on_async_requests(tmp_path, monkeypatch):
    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"audio")

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("no_vocals.wav", b"no-vocals")
        archive.writestr("vocals.wav", b"vocals")
    zip_payload = zip_buffer.getvalue()

    class RecordingAsyncClient:
        def __init__(self, **_):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            self.calls.append(("POST", url, kwargs))
            return _FakeAsyncResponse(
                {
                    "job_id": "remote-job",
                    "status": "queued",
                    "progress_percent": 0,
                    "progress_message": "Queued",
                }
            )

        def stream(self, method, url, **kwargs):
            self.calls.append(("STREAM", method, url, kwargs))
            running_event = (
                'data: {"job_id":"remote-job","status":"running","progress_percent":5,'
                '"progress_message":"Running","output_tail":[],"sequence":1,"updated_at":"2026-01-01T00:00:00+00:00"}'
            )
            completed_event = (
                'data: {"job_id":"remote-job","status":"completed","progress_percent":100,'
                '"progress_message":"Completed","output_tail":[],"sequence":2,"updated_at":"2026-01-01T00:00:00+00:00"}'
            )
            return _FakeStreamResponse(
                [
                    "id: 1",
                    "event: job",
                    running_event,
                    "",
                    "id: 2",
                    "event: job",
                    completed_event,
                    "",
                ]
            )

        async def get(self, url, **kwargs):
            self.calls.append(("GET", url, kwargs))
            if url.endswith("/result"):
                return _FakeAsyncResponse(content=zip_payload)
            raise AssertionError(f"Unexpected GET {url}")

    fake_client = RecordingAsyncClient()
    monkeypatch.setattr(
        "services.demucs_client.httpx.AsyncClient",
        lambda **_: fake_client,
    )

    client = DemucsClient(api_url="http://demucs.local", api_key="shared-secret", poll_interval_seconds=0)

    result = asyncio.run(client.separate_vocals(audio_path))

    assert result.no_vocals_path.endswith("no_vocals.wav")
    assert result.vocals_path.endswith("vocals.wav")
    for call in fake_client.calls:
        if call[0] not in {"POST", "STREAM", "GET"}:
            continue
        kwargs = call[-1]
        headers = kwargs.get("headers") or {}
        assert headers["X-API-Key"] == "shared-secret"


def test_demucs_client_falls_back_to_polling_when_stream_is_unavailable(tmp_path, monkeypatch):
    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"audio")

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("no_vocals.wav", b"no-vocals")
        archive.writestr("vocals.wav", b"vocals")
    zip_payload = zip_buffer.getvalue()

    class PollFallbackClient:
        def __init__(self):
            self.calls = []
            self.status_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            self.calls.append(("POST", url, kwargs))
            return _FakeAsyncResponse(
                {
                    "job_id": "remote-job",
                    "status": "queued",
                    "progress_percent": 0,
                    "progress_message": "Queued",
                }
            )

        def stream(self, method, url, **kwargs):
            self.calls.append(("STREAM", method, url, kwargs))
            return _FakeStreamResponse([], status_code=404)

        async def get(self, url, **kwargs):
            self.calls.append(("GET", url, kwargs))
            if url.endswith("/result"):
                return _FakeAsyncResponse(content=zip_payload)
            self.status_calls += 1
            if self.status_calls == 1:
                return _FakeAsyncResponse(
                    {
                        "status": "running",
                        "progress_percent": 12,
                        "progress_message": "Running",
                        "output_tail": [],
                    }
                )
            return _FakeAsyncResponse(
                {
                    "status": "completed",
                    "progress_percent": 100,
                    "progress_message": "Completed",
                    "output_tail": [],
                }
            )

    fake_client = PollFallbackClient()
    monkeypatch.setattr(
        "services.demucs_client.httpx.AsyncClient",
        lambda **_: fake_client,
    )

    client = DemucsClient(api_url="http://demucs.local", poll_interval_seconds=0)
    result = asyncio.run(client.separate_vocals(audio_path))

    assert result.no_vocals_path.endswith("no_vocals.wav")
    assert result.vocals_path.endswith("vocals.wav")
    assert any(call[0] == "STREAM" for call in fake_client.calls)
    assert sum(1 for call in fake_client.calls if call[0] == "GET" and not call[1].endswith("/result")) >= 2


def test_demucs_client_separate_vocals_sends_remote_cancel_when_event_set(tmp_path, monkeypatch):
    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"audio")
    cancel_event = threading.Event()

    class CancelStreamingClient:
        def __init__(self):
            self.deleted_jobs = []
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            self.calls.append(("POST", url, kwargs))
            return _FakeAsyncResponse(
                {
                    "job_id": "remote-job",
                    "status": "queued",
                    "progress_percent": 0,
                    "progress_message": "Queued",
                }
            )

        def stream(self, method, url, **kwargs):
            self.calls.append(("STREAM", method, url, kwargs))

            class _Response:
                status_code = 200
                content = b""

                async def __aenter__(self_inner):
                    return self_inner

                async def __aexit__(self_inner, exc_type, exc, tb):
                    return False

                async def aiter_lines(self_inner):
                    yield "id: 1"
                    yield "event: job"
                    yield (
                        'data: {"job_id":"remote-job","status":"running","progress_percent":5,'
                        '"progress_message":"Running","output_tail":[],"sequence":1,"updated_at":"2026-01-01T00:00:00+00:00"}'
                    )
                    yield ""
                    cancel_event.set()
                    yield ": keep-alive"

            return _Response()

        async def get(self, url, **kwargs):
            self.calls.append(("GET", url, kwargs))
            raise AssertionError(f"Unexpected GET {url}")

        async def delete(self, url, **kwargs):
            self.deleted_jobs.append(url.rsplit("/", 1)[-1])
            return _FakeAsyncResponse({"status": "canceled"})

    fake_client = CancelStreamingClient()
    monkeypatch.setattr(
        "services.demucs_client.httpx.AsyncClient",
        lambda **_: fake_client,
    )

    client = DemucsClient(api_url="http://demucs.local", poll_interval_seconds=0)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client.separate_vocals(audio_path, cancel_event=cancel_event))

    assert fake_client.deleted_jobs == ["remote-job"]


def test_demucs_client_align_lyrics_uses_stream_and_fetches_result(tmp_path, monkeypatch):
    vocals_path = tmp_path / "vocals.wav"
    vocals_path.write_bytes(b"audio")

    class StreamingAlignClient:
        def __init__(self):
            self.deleted_jobs = []
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            self.calls.append(("POST", url, kwargs))
            return _FakeAsyncResponse(
                {
                    "job_id": "remote-job",
                    "status": "queued",
                    "progress_percent": 0,
                    "progress_message": "Queued",
                }
            )

        def stream(self, method, url, **kwargs):
            class _Response:
                status_code = 200
                content = b""

                async def __aenter__(self_inner):
                    return self_inner

                async def __aexit__(self_inner, exc_type, exc, tb):
                    return False

                async def aiter_lines(self_inner):
                    yield "id: 1"
                    yield "event: job"
                    yield (
                        'data: {"job_id":"remote-job","status":"running","progress_percent":5,'
                        '"progress_message":"Aligning lyrics","output_tail":[],"sequence":1,"updated_at":"2026-01-01T00:00:00+00:00"}'
                    )
                    yield ""
                    yield "id: 2"
                    yield "event: job"
                    yield (
                        'data: {"job_id":"remote-job","status":"completed","progress_percent":100,'
                        '"progress_message":"Completed","output_tail":[],"sequence":2,"updated_at":"2026-01-01T00:00:00+00:00"}'
                    )
                    yield ""

            return _Response()

        async def get(self, url, **kwargs):
            self.calls.append(("GET", url, kwargs))
            if url.endswith("/result"):
                return _FakeAsyncResponse(content=b'[{"start":1.0,"end":2.0,"text":"hello"}]')
            raise AssertionError(f"Unexpected GET {url}")

        async def delete(self, url, **kwargs):
            self.deleted_jobs.append(url.rsplit("/", 1)[-1])
            return _FakeAsyncResponse({"status": "canceled"})

    fake_client = StreamingAlignClient()
    monkeypatch.setattr(
        "services.demucs_client.httpx.AsyncClient",
        lambda **_: fake_client,
    )

    client = DemucsClient(api_url="http://demucs.local", poll_interval_seconds=0)

    result_path, job_id = asyncio.run(
        client.align_lyrics(
            vocals_path,
            lyrics_text="hello",
            lyrics_format="txt",
        )
    )

    assert result_path.name == "vocals_remote-job_aligned_lyrics.json"
    assert job_id == "remote-job"
    assert fake_client.deleted_jobs == []
