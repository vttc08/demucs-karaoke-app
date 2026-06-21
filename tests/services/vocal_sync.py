from .common import *

import importlib
import sys
import wave
from io import BytesIO

from services import vocal_sync_service as vocal_sync_module
from services.vocal_sync_service import VocalSyncService


def _write_impulse_wav(path: Path, impulse_index: int, *, frame_count: int = 200, sample_rate: int = 100):
    samples = [0] * frame_count
    samples[impulse_index] = 16000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(int(value).to_bytes(2, "little", signed=True) for value in samples))


def test_vocal_sync_module_does_not_import_numpy_or_scipy_at_startup():
    sys.modules.pop("numpy", None)
    sys.modules.pop("scipy", None)
    importlib.reload(vocal_sync_module)

    assert "numpy" not in sys.modules
    assert "scipy" not in sys.modules


def test_estimate_offset_sign_convention(tmp_path):
    reference = tmp_path / "reference.wav"
    target_late = tmp_path / "target-late.wav"
    target_early = tmp_path / "target-early.wav"
    _write_impulse_wav(reference, 50)
    _write_impulse_wav(target_late, 75)
    _write_impulse_wav(target_early, 25)

    assert VocalSyncService.estimate_offset_seconds(reference, target_late) == pytest.approx(0.25)
    assert VocalSyncService.estimate_offset_seconds(reference, target_early) == pytest.approx(-0.25)


def test_commit_session_installs_vocals_sidecar(db_session, tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    session_id = "11111111-1111-1111-1111-111111111111"
    session_dir = cache_root / "vocal_sync" / session_id
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)
    media_root.mkdir()
    media_file = media_root / "song.mp4"
    vocals_file = session_dir / "review_vocals.wav"
    media_file.write_bytes(b"video")
    vocals_file.write_bytes(b"vocals")
    media = MediaItem(
        title="Song",
        artist="Artist",
        file_stem="song",
        media_path="/media/song.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    task = ProcessingTask(
        task_type="media_vocal_sync_prepare_upload",
        source_kind="upload",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.DONE.value,
        stage="ready",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    manifest = {
        "session_id": session_id,
        "media_item_id": media.id,
        "media_url": "/media/song.mp4",
        "media_path": str(media_file),
        "vocals_path": str(vocals_file),
        "background_path": str(session_dir / "review_background.wav"),
        "karaoke_wav_path": str(session_dir / "karaoke_mono.wav"),
        "background_wav_path": str(session_dir / "background_mono.wav"),
        "estimated_offset_seconds": 0.2,
        "method": "scipy_cross_correlation",
        "source_kind": "upload",
        "source_ref": "source.wav",
        "title": "Song",
        "artist": "Artist",
    }
    VocalSyncService._write_manifest(session_id, manifest)
    VocalSyncService.write_task_manifest(
        task.id,
        {
            "task_id": task.id,
            "media_item_id": media.id,
            "source_kind": "upload",
            "source_filename": "source.wav",
            "source_path": None,
            "session_id": session_id,
        },
    )

    service = VocalSyncService()

    def fake_render(*, vocals_path, karaoke_path, output_path, offset_seconds):
        assert vocals_path == vocals_file
        assert karaoke_path == media_file
        assert offset_seconds == pytest.approx(0.35)
        output_path.write_bytes(b"aligned vocals")
        return output_path

    monkeypatch.setattr(service, "render_aligned_vocals", fake_render)

    session = service.commit_session(db_session, media.id, session_id, 0.35)

    db_session.refresh(media)
    assert session.session_id == session_id
    assert media.vocals_path == "/media/song.vocals.wav"
    assert (media_root / "song.vocals.wav").read_bytes() == b"aligned vocals"
    assert not session_dir.exists()
    assert not (cache_root / "vocal_sync_tasks" / f"{task.id}.json").exists()


def test_delete_review_session_removes_session_and_task_manifest(db_session, tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    session_id = "55555555-5555-5555-5555-555555555555"
    session_dir = cache_root / "vocal_sync" / session_id
    session_dir.mkdir(parents=True)
    vocals_file = session_dir / "review_vocals.wav"
    vocals_file.write_bytes(b"vocals")
    monkeypatch.setattr(settings, "cache_path", cache_root)
    media = MediaItem(
        title="Song",
        artist="Artist",
        media_path="/media/song.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    task = ProcessingTask(
        task_type="media_vocal_sync_prepare_youtube",
        source_kind="youtube",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.DONE.value,
        stage="ready",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    VocalSyncService._write_manifest(
        session_id,
        {
            "session_id": session_id,
            "media_item_id": media.id,
            "media_url": "/media/song.mp4",
            "vocals_path": str(vocals_file),
            "estimated_offset_seconds": 0.2,
            "method": "scipy_cross_correlation",
            "source_kind": "youtube",
            "title": "Song",
            "artist": "Artist",
        },
    )
    VocalSyncService.write_task_manifest(
        task.id,
        {
            "task_id": task.id,
            "media_item_id": media.id,
            "source_kind": "youtube",
            "youtube_id": "abcdefghijk",
            "session_id": session_id,
        },
    )

    VocalSyncService().delete_review_session(db_session, media.id, session_id)

    assert not session_dir.exists()
    assert not (cache_root / "vocal_sync_tasks" / f"{task.id}.json").exists()


def test_active_vocal_sync_prepare_task_spans_source_kinds(db_session):
    media = MediaItem(title="Song", artist="Artist", media_path="/media/song.mp4", missing=False)
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    youtube_task = ProcessingTask(
        task_type="media_vocal_sync_prepare_youtube",
        source_kind="youtube",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="download",
    )
    upload_task = ProcessingTask(
        task_type="media_vocal_sync_prepare_upload",
        source_kind="upload",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.FAILED.value,
        stage="failed",
    )
    db_session.add_all([youtube_task, upload_task])
    db_session.commit()

    active = processing_task_service.get_active_media_vocal_sync_prepare_task(db_session, media.id)

    assert active.id == youtube_task.id


def test_latest_ready_review_skips_stale_sessions(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_path", tmp_path)
    media = MediaItem(title="Song", artist="Artist", media_path="/media/song.mp4", missing=False)
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    ready_task = ProcessingTask(
        task_type="media_vocal_sync_prepare_upload",
        source_kind="upload",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.DONE.value,
        stage="ready",
    )
    stale_task = ProcessingTask(
        task_type="media_vocal_sync_prepare_youtube",
        source_kind="youtube",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.DONE.value,
        stage="ready",
    )
    db_session.add_all([ready_task, stale_task])
    db_session.commit()
    db_session.refresh(stale_task)
    db_session.refresh(ready_task)

    stale_session_id = "33333333-3333-3333-3333-333333333333"
    ready_session_id = "44444444-4444-4444-4444-444444444444"
    VocalSyncService.create_youtube_prepare_task_manifest(
        stale_task.id,
        media_item_id=media.id,
        youtube_id="abcdefghijk",
    )
    VocalSyncService.update_task_manifest_session(stale_task.id, stale_session_id)
    VocalSyncService.create_upload_prepare_task_manifest(
        ready_task.id,
        media_item_id=media.id,
        source_filename="source.mp3",
        source_file=BytesIO(b"audio"),
    )
    VocalSyncService.update_task_manifest_session(ready_task.id, ready_session_id)
    ready_dir = tmp_path / "vocal_sync" / ready_session_id
    ready_dir.mkdir(parents=True)
    vocals_file = ready_dir / "review_vocals.wav"
    vocals_file.write_bytes(b"vocals")
    VocalSyncService._write_manifest(
        ready_session_id,
        {
            "session_id": ready_session_id,
            "media_item_id": media.id,
            "media_url": "/media/song.mp4",
            "vocals_path": str(vocals_file),
            "estimated_offset_seconds": 0.5,
            "method": "scipy_cross_correlation",
            "source_kind": "upload",
            "title": "Song",
            "artist": "Artist",
        },
    )

    result = VocalSyncService().latest_ready_review_for_media(
        db_session,
        media.id,
        task_types=processing_task_service.VOCAL_SYNC_PREPARE_TASK_TYPES,
    )

    assert result is not None
    task, session = result
    assert task.id == ready_task.id
    assert session.session_id == ready_session_id


def test_render_aligned_vocals_uses_positive_delay(tmp_path, monkeypatch):
    commands = []
    service = VocalSyncService()
    monkeypatch.setattr(service.ffmpeg, "probe_media", lambda _path: {"duration": 12.0})

    def fake_run(cmd, check, capture_output, text):
        commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"wav")
        return Mock(returncode=0)

    monkeypatch.setattr(vocal_sync_module.subprocess, "run", fake_run)

    output = service.render_aligned_vocals(
        vocals_path=tmp_path / "vocals.wav",
        karaoke_path=tmp_path / "song.mp4",
        output_path=tmp_path / "out.wav",
        offset_seconds=1.25,
    )

    assert output.exists()
    assert "adelay=1250:all=1" in " ".join(commands[0])


def test_render_aligned_vocals_uses_negative_trim(tmp_path, monkeypatch):
    commands = []
    service = VocalSyncService()
    monkeypatch.setattr(service.ffmpeg, "probe_media", lambda _path: {"duration": 12.0})

    def fake_run(cmd, check, capture_output, text):
        commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"wav")
        return Mock(returncode=0)

    monkeypatch.setattr(vocal_sync_module.subprocess, "run", fake_run)

    service.render_aligned_vocals(
        vocals_path=tmp_path / "vocals.wav",
        karaoke_path=tmp_path / "song.mp4",
        output_path=tmp_path / "out.wav",
        offset_seconds=-0.75,
    )

    assert "atrim=start=0.750000" in " ".join(commands[0])
