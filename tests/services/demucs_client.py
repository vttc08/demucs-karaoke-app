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


def test_demucs_client_separate_vocals_sends_remote_cancel_when_event_set(tmp_path, monkeypatch):
    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"audio")
    cancel_event = threading.Event()
    fake_client = _FakeAsyncClient(cancel_event=cancel_event)
    monkeypatch.setattr(
        "services.demucs_client.httpx.AsyncClient",
        lambda **_: fake_client,
    )

    client = DemucsClient(api_url="http://demucs.local", poll_interval_seconds=0)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client.separate_vocals(audio_path, cancel_event=cancel_event))

    assert fake_client.deleted_jobs == ["remote-job"]


def test_demucs_client_align_lyrics_sends_remote_cancel_on_asyncio_cancellation(tmp_path, monkeypatch):
    vocals_path = tmp_path / "vocals.wav"
    vocals_path.write_bytes(b"audio")
    fake_client = _FakeAsyncClient(raise_cancel_on_get=True)
    monkeypatch.setattr(
        "services.demucs_client.httpx.AsyncClient",
        lambda **_: fake_client,
    )

    client = DemucsClient(api_url="http://demucs.local", poll_interval_seconds=0)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            client.align_lyrics(
                vocals_path,
                lyrics_text="hello",
                lyrics_format="txt",
            )
        )

    assert fake_client.deleted_jobs == ["remote-job"]
