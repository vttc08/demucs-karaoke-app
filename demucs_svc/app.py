import gc
import os
import json
import logging
import multiprocessing
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Literal
from html import escape

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import ValidationError

try:
    from .demucs_runner import (
        _build_command,
        build_expected_output_paths,
        parse_progress_line,
        prepare_job_input,
        run_demucs_on_file,
    )
    from .jobs import DemucsJobState, DemucsJobStore, utc_now
    from .models import (
        DemucsJobArtifactDeleteResponse,
        DemucsJobCreateResponse,
        DemucsIoCleanupResponse,
        DemucsIoUsageResponse,
        DemucsGarbageCollectionResponse,
        DemucsMetricsJobResponse,
        DemucsMetricsResponse,
        DemucsJobStatusResponse,
        SeparateConfig,
        SeparateMetaResponse,
        TransferUploadResponse,
        WhisperXPreloadResponse,
    )
    from .settings import (
        DEMUCS_GC_INTERVAL_SECONDS,
        DEMUCS_GC_LOW_FREE_VRAM_BYTES,
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_OUTPUT_FORMAT,
        DEFAULT_WHISPERX_ALIGN_LANGUAGE,
        DEFAULT_WHISPERX_DETECT_LANGUAGE,
        DEFAULT_WHISPERX_PRELOAD_MODELS,
        DEFAULT_WHISPERX_TRANSCRIPTION_MODEL,
        DEFAULT_WHISPERX_USE_SYNCED_LYRICS,
        INCOMING_ROOT,
        JOB_OUTPUT_TAIL_LINES,
        JOB_RETENTION_SECONDS,
        OUTPUT_ROOT,
    )
    from .whisperx_pipeline import (
        align_lyrics,
        dump_aligned_lyrics_json,
        preload_models,
        unload_models,
        whisperx_available,
    )
except ImportError:
    from demucs_runner import (
        _build_command,
        build_expected_output_paths,
        parse_progress_line,
        prepare_job_input,
        run_demucs_on_file,
    )
    from jobs import DemucsJobState, DemucsJobStore, utc_now
    from models import (
        DemucsJobArtifactDeleteResponse,
        DemucsJobCreateResponse,
        DemucsIoCleanupResponse,
        DemucsIoUsageResponse,
        DemucsGarbageCollectionResponse,
        DemucsMetricsJobResponse,
        DemucsMetricsResponse,
        DemucsJobStatusResponse,
        SeparateConfig,
        SeparateMetaResponse,
        TransferUploadResponse,
        WhisperXPreloadResponse,
    )
    from settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_OUTPUT_FORMAT,
        DEFAULT_WHISPERX_ALIGN_LANGUAGE,
        DEFAULT_WHISPERX_DETECT_LANGUAGE,
        DEFAULT_WHISPERX_PRELOAD_MODELS,
        DEFAULT_WHISPERX_TRANSCRIPTION_MODEL,
        DEFAULT_WHISPERX_USE_SYNCED_LYRICS,
        INCOMING_ROOT,
        JOB_OUTPUT_TAIL_LINES,
        JOB_RETENTION_SECONDS,
        DEMUCS_GC_INTERVAL_SECONDS,
        DEMUCS_GC_LOW_FREE_VRAM_BYTES,
        OUTPUT_ROOT,
    )
    from whisperx_pipeline import (
        align_lyrics,
        dump_aligned_lyrics_json,
        preload_models,
        unload_models,
        whisperx_available,
    )

app = FastAPI(title="Demucs Service", version="0.2.0")
job_store = DemucsJobStore(tail_limit=JOB_OUTPUT_TAIL_LINES)
logger = logging.getLogger(__name__)
TRANSFER_CACHE_ROOT = Path(__file__).resolve().parent / ".cache" / "transfer"
TRANSFER_RANDOM_FILENAME = "random-25mb.bin"
TRANSFER_RANDOM_FILE_SIZE_BYTES = 25 * 1024 * 1024
_gc_lock = threading.Lock()
_gc_scheduler_stop_event = threading.Event()
_gc_scheduler_thread: threading.Thread | None = None
_gc_state_lock = threading.Lock()
_gc_state = {
    "last_gc_at": None,
    "last_gc_mode": None,
    "last_gc_detail": None,
}


def _cuda_available() -> bool:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import torch;print('1' if torch.cuda.is_available() else '0')",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return probe.returncode == 0 and probe.stdout.strip() == "1"


def _cuda_memory_snapshot() -> tuple[int | None, int | None]:
    try:
        import torch  # type: ignore
    except Exception:
        return None, None

    try:
        if not torch.cuda.is_available():
            return None, None
        free_vram, total_vram = torch.cuda.mem_get_info()
    except Exception:
        return None, None
    return int(free_vram), int(total_vram)


def _clear_cuda_memory() -> tuple[bool, bool]:
    try:
        import torch  # type: ignore
    except Exception:
        return False, False

    if not torch.cuda.is_available():
        return False, False

    cuda_cache_cleared = False
    cuda_ipc_cleared = False

    try:
        torch.cuda.synchronize()
    except Exception:
        pass

    try:
        torch.cuda.empty_cache()
        cuda_cache_cleared = True
    except Exception:
        pass

    ipc_collect = getattr(torch.cuda, "ipc_collect", None)
    if callable(ipc_collect):
        try:
            ipc_collect()
            cuda_ipc_cleared = True
        except Exception:
            pass

    return cuda_cache_cleared, cuda_ipc_cleared


def _record_gc_state(*, finished_at: str, mode: str, detail: str) -> None:
    with _gc_state_lock:
        _gc_state["last_gc_at"] = finished_at
        _gc_state["last_gc_mode"] = mode
        _gc_state["last_gc_detail"] = detail


def _current_gc_state() -> dict[str, str | None]:
    with _gc_state_lock:
        return dict(_gc_state)


def _transfer_random_file_path() -> Path:
    return TRANSFER_CACHE_ROOT / TRANSFER_RANDOM_FILENAME


def _generate_random_transfer_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    remaining = TRANSFER_RANDOM_FILE_SIZE_BYTES
    chunk_size = 1024 * 1024

    with temp_path.open("wb") as handle:
        while remaining > 0:
            write_size = min(chunk_size, remaining)
            handle.write(os.urandom(write_size))
            remaining -= write_size

    os.replace(temp_path, path)


def _ensure_random_transfer_file() -> Path:
    path = _transfer_random_file_path()
    if path.exists() and path.stat().st_size == TRANSFER_RANDOM_FILE_SIZE_BYTES:
        return path

    _generate_random_transfer_file(path)
    return path


def _transfer_request_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _transfer_page_html(*, request: Request) -> str:
    base_url = escape(_transfer_request_base_url(request))
    download_url_raw = str(request.url_for("transfer_random_download"))
    multipart_upload_url_raw = str(request.url_for("transfer_upload"))
    raw_upload_url_raw = str(request.url_for("transfer_upload_raw"))
    download_url = escape(download_url_raw)
    multipart_upload_url = escape(multipart_upload_url_raw)
    raw_upload_url = escape(raw_upload_url_raw)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Demucs Transfer Bench</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0f172a;
      --panel: #111827;
      --panel-soft: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #22c55e;
      --accent-strong: #16a34a;
      --border: rgba(148, 163, 184, 0.25);
      --shadow: 0 16px 48px rgba(0, 0, 0, 0.24);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 16px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(34, 197, 94, 0.16), transparent 32%),
        radial-gradient(circle at 80% 0%, rgba(59, 130, 246, 0.14), transparent 24%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    main {{
      width: min(1100px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }}
    .hero {{
      display: grid;
      gap: 12px;
      margin-bottom: 20px;
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{
      font-size: clamp(2rem, 4vw, 3.4rem);
      line-height: 1.05;
      letter-spacing: -0.04em;
    }}
    .lede {{
      max-width: 70ch;
      color: var(--muted);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 16px;
    }}
    .card {{
      grid-column: span 12;
      background: linear-gradient(180deg, rgba(17, 24, 39, 0.94), rgba(15, 23, 42, 0.94));
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 20px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    @media (min-width: 900px) {{
      .card.upload {{ grid-column: span 7; }}
      .card.download, .card.commands {{ grid-column: span 5; }}
    }}
    .section-title {{
      font-size: 1.1rem;
      margin-bottom: 10px;
    }}
    .muted {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .stack {{
      display: grid;
      gap: 12px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }}
    .button {{
      appearance: none;
      border: 0;
      border-radius: 999px;
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      color: #04130a;
      font-weight: 700;
      padding: 0.8rem 1rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
    }}
    .button.secondary {{
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
    }}
    .field {{
      display: grid;
      gap: 8px;
    }}
    input[type="file"] {{
      width: 100%;
      padding: 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.02);
      color: var(--text);
    }}
    progress {{
      width: 100%;
      height: 18px;
      border-radius: 999px;
      overflow: hidden;
    }}
    progress::-webkit-progress-bar {{
      background: rgba(148, 163, 184, 0.12);
    }}
    progress::-webkit-progress-value {{
      background: linear-gradient(90deg, #34d399, #22c55e);
    }}
    progress::-moz-progress-bar {{
      background: linear-gradient(90deg, #34d399, #22c55e);
    }}
    pre {{
      margin: 0;
      padding: 16px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border);
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .status {{
      min-height: 1.5em;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .result {{
      padding: 12px 14px;
      border-radius: 12px;
      background: rgba(34, 197, 94, 0.12);
      border: 1px solid rgba(34, 197, 94, 0.3);
      color: #dcfce7;
      min-height: 3rem;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.92em;
    }}
    label {{
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>Demucs Transfer Bench</h1>
      <p class="lede">
        Admin throughput test page for the standalone Demucs service.
        Use it to measure upload, download, and round-trip latency between your browser or CLI
        tools and the Demucs host without invoking separation or alignment work.
      </p>
      <p class="muted">Service base: <code>{base_url}</code></p>
    </section>

    <section class="grid">
      <article class="card upload">
        <div class="stack">
          <div>
            <h2 class="section-title">Upload test</h2>
            <p class="muted">
              Multipart upload for browser testing. The server reads the bytes, counts them, and
              discards them immediately.
            </p>
          </div>
          <form id="transfer-upload-form" class="stack" action="{multipart_upload_url}" method="post" enctype="multipart/form-data">
            <div class="field">
              <label for="transfer-upload-file">Choose any file</label>
              <input id="transfer-upload-file" name="file" type="file" required>
            </div>
            <div class="actions">
              <button class="button" type="submit">Upload selected file</button>
              <a class="button secondary" href="{raw_upload_url}">Raw upload endpoint</a>
            </div>
          </form>
          <progress id="transfer-upload-progress" value="0" max="100"></progress>
          <div id="transfer-upload-status" class="status">Idle.</div>
          <div id="transfer-upload-speed" class="muted">Transfer speed will appear here during upload.</div>
          <div id="transfer-upload-result" class="result">Waiting for an upload.</div>
        </div>
      </article>

      <article class="card download">
        <div class="stack">
          <div>
            <h2 class="section-title">Download test</h2>
            <p class="muted">
              Downloads a cached 25 MiB random file. The first request creates the payload; later
              requests reuse the same file.
            </p>
          </div>
          <div class="actions">
            <a class="button" href="{download_url}">Download 25 MiB file</a>
          </div>
          <p class="muted">
            The browser or your CLI client can measure transfer time, throughput, and completion.
          </p>
        </div>
      </article>

      <article class="card commands">
        <div class="stack">
          <div>
            <h2 class="section-title">curl / wget</h2>
            <p class="muted">Use these when you want a simple command-line throughput check.</p>
          </div>
          <pre><code>curl -F "file=@/path/to/media.bin" "{multipart_upload_url}"
curl -X POST --data-binary "@/path/to/media.bin" "{raw_upload_url}"
curl -OJ "{download_url}"
wget --method=POST --body-file=/path/to/media.bin -O - "{raw_upload_url}"
wget -O random-25mb.bin "{download_url}"</code></pre>
        </div>
      </article>
    </section>
  </main>
  <script>
    (() => {{
      const form = document.getElementById("transfer-upload-form");
      const fileInput = document.getElementById("transfer-upload-file");
      const progress = document.getElementById("transfer-upload-progress");
      const status = document.getElementById("transfer-upload-status");
      const speed = document.getElementById("transfer-upload-speed");
      const result = document.getElementById("transfer-upload-result");
      const uploadUrl = {json.dumps(multipart_upload_url_raw)};

      function formatBytes(bytes) {{
        const units = ["B", "KB", "MB", "GB"];
        let value = bytes;
        let unitIndex = 0;
        while (value >= 1024 && unitIndex < units.length - 1) {{
          value /= 1024;
          unitIndex += 1;
        }}
        return `${{value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)}} ${{units[unitIndex]}}`;
      }}

      form.addEventListener("submit", (event) => {{
        event.preventDefault();
        const file = fileInput.files && fileInput.files[0];
        if (!file) {{
          status.textContent = "Choose a file first.";
          return;
        }}

        const start = performance.now();
        let timer = null;
        const xhr = new XMLHttpRequest();
        const data = new FormData();
        data.append("file", file, file.name);

        progress.removeAttribute("value");
        progress.max = 1;
        progress.value = 0;
        status.textContent = "Starting upload...";
        speed.textContent = "Measuring transfer speed...";
        result.textContent = "Uploading...";

        xhr.open("POST", uploadUrl, true);
        xhr.responseType = "json";

        let lastSampleAt = start;
        let lastSampleLoaded = 0;
        let smoothedRate = 0;

        function updateSpeed(now = performance.now()) {{
          const loaded = progress.hasAttribute("value") ? progress.value : 0;
          const elapsedSeconds = (now - start) / 1000;
          const sampleSeconds = (now - lastSampleAt) / 1000;
          const sampleLoaded = loaded - lastSampleLoaded;
          const instantRate = sampleSeconds > 0 && sampleLoaded > 0 ? sampleLoaded / sampleSeconds : 0;

          if (instantRate > 0) {{
            smoothedRate = smoothedRate > 0 ? (smoothedRate * 0.75) + (instantRate * 0.25) : instantRate;
            lastSampleAt = now;
            lastSampleLoaded = loaded;
          }}

          const total = progress.hasAttribute("max") ? progress.max : 0;
          const speedText = smoothedRate > 0 ? ` at ${{formatBytes(smoothedRate)}}/s` : "";
          if (total) {{
            status.textContent = `${{formatBytes(loaded)}} / ${{formatBytes(total)}} uploaded`;
          }} else {{
            status.textContent = `${{formatBytes(loaded)}} uploaded`;
          }}
          speed.textContent = elapsedSeconds > 0 || loaded > 0 ? `Estimated transfer speed${{speedText}}` : "Measuring transfer speed...";
        }}

        xhr.upload.onprogress = (event) => {{
          if (event.lengthComputable) {{
            progress.max = event.total;
            progress.value = event.loaded;
          }} else {{
            progress.removeAttribute("max");
            progress.value = event.loaded;
          }}
          updateSpeed();
        }};

        xhr.onloadstart = () => {{
          timer = window.setInterval(() => {{
            updateSpeed();
          }}, 250);
        }};

        xhr.onerror = () => {{
          window.clearInterval(timer);
          status.textContent = "Upload failed.";
          result.textContent = "The request failed before the server responded.";
        }};

        xhr.onload = () => {{
          window.clearInterval(timer);
          const elapsedMs = performance.now() - start;
          const payload = xhr.response || {{}};
          if (xhr.status >= 200 && xhr.status < 300) {{
            const received = payload.received_bytes ?? file.size;
            status.textContent = `Completed in ${{(elapsedMs / 1000).toFixed(2)}}s.`;
            speed.textContent = `Average transfer speed ${{formatBytes(received / Math.max(elapsedMs / 1000, 0.001))}}/s`;
            result.textContent = `Server received ${{formatBytes(received)}} and discarded it.`;
            progress.max = received || 1;
            progress.value = received || 1;
          }} else {{
            status.textContent = `Upload failed with HTTP ${{xhr.status}}.`;
            speed.textContent = "Transfer speed unavailable.";
            result.textContent = payload.detail || "The server rejected the upload.";
          }}
        }};

        xhr.onloadend = () => {{
          window.clearInterval(timer);
        }};

        xhr.send(data);
      }});
    }})();
  </script>
</body>
</html>"""


async def _drain_upload_file(upload_file: UploadFile, *, chunk_size: int = 1024 * 1024) -> int:
    total_bytes = 0
    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
    return total_bytes


def _health_snapshot() -> dict[str, object]:
    checks = {
        "incoming_writable": INCOMING_ROOT.exists() and INCOMING_ROOT.is_dir(),
        "output_writable": OUTPUT_ROOT.exists() and OUTPUT_ROOT.is_dir(),
    }

    try:
        probe = subprocess.run(
            [sys.executable, "-m", "demucs.separate", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        checks["demucs_cli_available"] = probe.returncode == 0
    except Exception:
        checks["demucs_cli_available"] = False

    healthy = all(checks.values())
    return {
        "status": "ok" if healthy else "degraded",
        "service": "demucs",
        "model": DEFAULT_DEMUCS_MODEL,
        "device": DEFAULT_DEMUCS_DEVICE,
        "detail": "ready" if healthy else "One or more readiness checks failed",
        "checks": checks,
        "active_jobs": sum(1 for job in job_store.all() if job.status in {"queued", "running"}),
        "running_jobs": sum(1 for job in job_store.all() if job.status == "running"),
    }


def _build_stems_zip(result) -> bytes:
    stem_ext = "mp3" if result.output_format == "mp3" else "wav"
    metadata = {
        "job_id": result.job_id,
        "model": result.model,
        "device": result.device,
        "output_format": result.output_format,
        "mp3_bitrate": result.mp3_bitrate,
        "duration_ms": result.duration_ms,
        "files": {
            "no_vocals": f"no_vocals.{stem_ext}",
            "vocals": f"vocals.{stem_ext}",
        },
    }
    if getattr(result, "aligned_lyrics_path", None):
        metadata["files"]["aligned_lyrics"] = "aligned_lyrics.json"

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(result.no_vocals_path, arcname=f"no_vocals.{stem_ext}")
        archive.write(result.vocals_path, arcname=f"vocals.{stem_ext}")
        if getattr(result, "aligned_lyrics_path", None):
            archive.write(result.aligned_lyrics_path, arcname="aligned_lyrics.json")
        archive.writestr("metadata.json", json.dumps(metadata, separators=(",", ":")))
    return buffer.getvalue()


def _job_to_status_response(job: DemucsJobState) -> DemucsJobStatusResponse:
    data = job.to_dict()
    for key in ("created_at", "started_at", "finished_at"):
        value = data[key]
        data[key] = value.isoformat() if value is not None else None
    return DemucsJobStatusResponse(**data)


def _job_to_metrics_response(job: DemucsJobState) -> DemucsMetricsJobResponse:
    data = job.to_dict()
    for key in ("created_at", "started_at"):
        value = data[key]
        data[key] = value.isoformat() if value is not None else None
    return DemucsMetricsJobResponse(
        job_id=data["job_id"],
        status=data["status"],
        job_kind=data["job_kind"],
        progress_percent=data["progress_percent"],
        progress_message=data["progress_message"],
        model=data["model"],
        device=data["device"],
        output_format=data["output_format"],
        mp3_bitrate=data["mp3_bitrate"],
        original_filename=data["original_filename"],
        created_at=data["created_at"],
        started_at=data["started_at"],
        cancel_requested=data["cancel_requested"],
        stdout_tail=data["output_tail"],
    )


def _current_runtime_snapshot() -> dict[str, object]:
    active_jobs = [
        job
        for job in job_store.all()
        if job.status in {"queued", "running"}
    ]
    active_jobs.sort(key=lambda job: (job.created_at.timestamp(), job.job_id))
    status_counts = Counter(job.status for job in active_jobs)
    kind_counts = Counter(job.job_kind for job in active_jobs)
    free_vram_bytes, total_vram_bytes = _cuda_memory_snapshot()
    gc_state = _current_gc_state()
    running_job_count = sum(1 for job in active_jobs if job.status == "running")
    return {
        "active_jobs": active_jobs,
        "active_job_count": len(active_jobs),
        "running_job_count": running_job_count,
        "active_job_counts_by_status": dict(sorted(status_counts.items())),
        "active_job_counts_by_kind": dict(sorted(kind_counts.items())),
        "free_vram_bytes": free_vram_bytes,
        "total_vram_bytes": total_vram_bytes,
        "last_gc_at": gc_state["last_gc_at"],
        "last_gc_mode": gc_state["last_gc_mode"],
        "last_gc_detail": gc_state["last_gc_detail"],
    }


def _job_paths(job_id: str) -> tuple[Path, Path]:
    return INCOMING_ROOT / job_id, OUTPUT_ROOT / job_id


def _cleanup_job_files(job_id: str) -> None:
    incoming_dir, output_dir = _job_paths(job_id)
    for path in (incoming_dir, output_dir):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _process_is_running(process) -> bool:
    if process is None:
        return False
    poll = getattr(process, "poll", None)
    if callable(poll):
        return poll() is None
    is_alive = getattr(process, "is_alive", None)
    if callable(is_alive):
        return bool(is_alive())
    return False


def _wait_for_process(process, timeout: float | None = None):
    wait = getattr(process, "wait", None)
    if callable(wait):
        return wait(timeout=timeout) if timeout is not None else wait()
    join = getattr(process, "join", None)
    if callable(join):
        join(timeout)
        exitcode = getattr(process, "exitcode", None)
        return 0 if exitcode is None else exitcode
    return None


def _terminate_process(process, *, grace_seconds: float = 5.0) -> None:
    if process is None or not _process_is_running(process):
        return

    terminate = getattr(process, "terminate", None)
    if callable(terminate):
        terminate()

    try:
        _wait_for_process(process, timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        pass

    if not _process_is_running(process):
        return

    kill = getattr(process, "kill", None)
    if callable(kill):
        kill()
        try:
            _wait_for_process(process, timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass


def _folder_usage(path: Path) -> tuple[int, int]:
    total_bytes = 0
    file_count = 0
    if not path.exists():
        return total_bytes, file_count

    for child in path.rglob("*"):
        if not child.is_file():
            continue
        try:
            stat_result = child.stat()
        except OSError:
            continue
        total_bytes += int(stat_result.st_size)
        file_count += 1
    return total_bytes, file_count


def _io_usage_snapshot() -> DemucsIoUsageResponse:
    incoming_bytes, incoming_files = _folder_usage(INCOMING_ROOT)
    output_bytes, output_files = _folder_usage(OUTPUT_ROOT)
    active_jobs = [job for job in job_store.all() if job.status in {"queued", "running"}]
    terminal_job_count = sum(1 for job in job_store.all() if job.status not in {"queued", "running"})
    io_root = INCOMING_ROOT.parent
    total_bytes = incoming_bytes + output_bytes
    total_files = incoming_files + output_files
    return DemucsIoUsageResponse(
        io_root=str(io_root),
        incoming_root=str(INCOMING_ROOT),
        output_root=str(OUTPUT_ROOT),
        total_bytes=total_bytes,
        incoming_bytes=incoming_bytes,
        output_bytes=output_bytes,
        total_files=total_files,
        incoming_files=incoming_files,
        output_files=output_files,
        active_job_count=len(active_jobs),
        running_job_count=sum(1 for job in active_jobs if job.status == "running"),
        terminal_job_count=terminal_job_count,
        detail="Current Demucs IO footprint",
    )


def _cleanup_io() -> DemucsIoCleanupResponse:
    active_jobs = [job for job in job_store.all() if job.status in {"queued", "running"}]
    if active_jobs:
        raise HTTPException(
            status_code=409,
            detail="Active jobs are still running; wait before cleaning the IO folder",
        )

    usage = _io_usage_snapshot()
    terminal_jobs = [
        job for job in job_store.all() if job.status not in {"queued", "running"}
    ]
    for job in terminal_jobs:
        job_store.delete(job.job_id)

    io_root = INCOMING_ROOT.parent
    shutil.rmtree(io_root, ignore_errors=True)
    INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    return DemucsIoCleanupResponse(
        io_root=usage.io_root,
        deleted_bytes=usage.total_bytes,
        deleted_files=usage.total_files,
        deleted_job_count=len(terminal_jobs),
        active_job_count=usage.active_job_count,
        running_job_count=usage.running_job_count,
        detail="Deleted Demucs IO scratch files",
    )


def _cleanup_expired_jobs() -> None:
    cutoff = time.time() - JOB_RETENTION_SECONDS
    for job in job_store.all():
        if job.status in {"queued", "running"}:
            continue
        finished_at = job.finished_at.timestamp() if job.finished_at is not None else None
        if finished_at is None or finished_at > cutoff:
            continue
        job_store.delete(job.job_id)
        _cleanup_job_files(job.job_id)


def _active_jobs_snapshot() -> DemucsMetricsResponse:
    snapshot = _current_runtime_snapshot()
    return DemucsMetricsResponse(
        service="demucs",
        snapshot_at=utc_now().isoformat(),
        active_job_count=snapshot["active_job_count"],
        running_job_count=snapshot["running_job_count"],
        active_job_counts_by_status=snapshot["active_job_counts_by_status"],
        active_job_counts_by_kind=snapshot["active_job_counts_by_kind"],
        free_vram_bytes=snapshot["free_vram_bytes"],
        total_vram_bytes=snapshot["total_vram_bytes"],
        last_gc_at=snapshot["last_gc_at"],
        last_gc_mode=snapshot["last_gc_mode"],
        last_gc_detail=snapshot["last_gc_detail"],
        active_jobs=[_job_to_metrics_response(job) for job in snapshot["active_jobs"]],
    )


def _select_gc_mode(snapshot: dict[str, object]) -> str:
    running_job_count = int(snapshot["running_job_count"])
    free_vram_bytes = snapshot["free_vram_bytes"]
    if running_job_count == 0:
        return "full"
    if isinstance(free_vram_bytes, int) and free_vram_bytes < DEMUCS_GC_LOW_FREE_VRAM_BYTES:
        return "cuda"
    return "partial"


def _run_garbage_collection(
    *,
    requested_mode: Literal["adaptive", "partial", "cuda", "full"] = "adaptive",
    triggered_by: Literal["manual", "scheduled", "job_completion", "cancellation"] = "manual",
) -> DemucsGarbageCollectionResponse:
    if not _gc_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Garbage collection already in progress")

    started_at = utc_now()
    try:
        snapshot = _current_runtime_snapshot()
        active_job_count = int(snapshot["active_job_count"])
        running_job_count = int(snapshot["running_job_count"])
        free_vram_bytes = snapshot["free_vram_bytes"]
        total_vram_bytes = snapshot["total_vram_bytes"]
        executed_mode = (
            _select_gc_mode(snapshot)
            if requested_mode == "adaptive"
            else requested_mode
        )
        detail_parts: list[str] = []

        if executed_mode == "full" and running_job_count > 0:
            executed_mode = "cuda" if isinstance(free_vram_bytes, int) else "partial"
            detail_parts.append("Full unload skipped because jobs are still running")

        python_gc_collected = 0
        whisperx_unloaded: dict[str, int] = {}
        cuda_cache_cleared = False
        cuda_ipc_cleared = False

        if executed_mode == "full":
            whisperx_unloaded = unload_models()
            python_gc_collected = gc.collect()
            cuda_cache_cleared, cuda_ipc_cleared = _clear_cuda_memory()
            detail_parts.append("Released WhisperX caches and CUDA memory")
        elif executed_mode == "cuda":
            python_gc_collected = gc.collect()
            cuda_cache_cleared, cuda_ipc_cleared = _clear_cuda_memory()
            detail_parts.append("Released Python and CUDA cache memory")
        else:
            executed_mode = "partial"
            python_gc_collected = gc.collect()
            detail_parts.append("Collected unreachable Python objects")

        finished_at = utc_now()
        detail = "; ".join(detail_parts) if detail_parts else "Garbage collection completed"
        _record_gc_state(
            finished_at=finished_at.isoformat(),
            mode=executed_mode,
            detail=detail,
        )
        return DemucsGarbageCollectionResponse(
            requested_mode=requested_mode,
            executed_mode=executed_mode,
            triggered_by=triggered_by,
            detail=detail,
            active_job_count=active_job_count,
            running_job_count=running_job_count,
            free_vram_bytes=free_vram_bytes,
            total_vram_bytes=total_vram_bytes,
            python_gc_collected=python_gc_collected,
            whisperx_unloaded=whisperx_unloaded,
            cuda_cache_cleared=cuda_cache_cleared,
            cuda_ipc_cleared=cuda_ipc_cleared,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
        )
    finally:
        _gc_lock.release()


def _run_background_gc() -> None:
    try:
        _run_garbage_collection(requested_mode="adaptive", triggered_by="scheduled")
    except HTTPException:
        return
    except Exception:
        logger.exception("Scheduled Demucs garbage collection failed")


def _gc_scheduler_loop() -> None:
    while not _gc_scheduler_stop_event.wait(DEMUCS_GC_INTERVAL_SECONDS):
        _run_background_gc()


def _ensure_gc_scheduler_started() -> None:
    global _gc_scheduler_thread
    if _gc_scheduler_thread is not None and _gc_scheduler_thread.is_alive():
        return
    _gc_scheduler_stop_event.clear()
    _gc_scheduler_thread = threading.Thread(
        target=_gc_scheduler_loop,
        name="demucs-gc-scheduler",
        daemon=True,
    )
    _gc_scheduler_thread.start()


def _update_job_progress(job_id: str, *, percent: int | None = None, message: str | None = None) -> None:
    changes = {}
    if percent is not None:
        changes["progress_percent"] = max(0, min(99, percent))
    if message:
        changes["progress_message"] = message
    if changes:
        job_store.update(job_id, **changes)


def _preload_whisperx_models(config: SeparateConfig) -> None:
    preload_models(
        config.whisperx_preload_models or DEFAULT_WHISPERX_PRELOAD_MODELS,
        device=config.device,
        compute_type=config.compute_type,
    )


def _align_lyrics(
    *,
    config: SeparateConfig,
    vocals_path: Path,
    output_dir: Path,
) -> Path | None:
    lyrics_text = config.lyrics_text
    if not lyrics_text:
        return None

    aligned_segments = align_lyrics(
        vocals_path,
        lyrics_text,
        lyrics_format=config.lyrics_format,
        transcription_model=config.transcription_model,
        align_language=config.align_language,
        detect_language=config.detect_language,
        use_synced_lyrics=config.use_synced_lyrics,
        process_lyrics_lines=config.process_lyrics_lines,
        max_line_length=config.max_line_length,
        max_line_length_cjk=config.max_line_length_cjk,
        device=config.device,
        compute_type=config.compute_type,
    )
    aligned_path = output_dir / "aligned_lyrics.json"
    aligned_path.write_text(dump_aligned_lyrics_json(aligned_segments), encoding="utf-8")
    return aligned_path


class _JobCanceled(Exception):
    """Internal sentinel used when a remote job is canceled cooperatively."""


def _alignment_child_entry(
    config: SeparateConfig,
    vocals_path_raw: str,
    output_dir_raw: str,
    error_path_raw: str,
) -> None:
    try:
        _preload_whisperx_models(config)
        _align_lyrics(
            config=config,
            vocals_path=Path(vocals_path_raw),
            output_dir=Path(output_dir_raw),
        )
    except Exception as error:
        Path(error_path_raw).write_text(str(error), encoding="utf-8")
        raise


def _align_lyrics_in_child_process(
    job_id: str,
    *,
    config: SeparateConfig,
    vocals_path: Path,
    output_dir: Path,
) -> Path | None:
    if not config.lyrics_text:
        return None

    aligned_path = output_dir / "aligned_lyrics.json"
    error_path = output_dir / "alignment_error.txt"
    if error_path.exists():
        error_path.unlink()

    process = multiprocessing.Process(
        target=_alignment_child_entry,
        args=(config, str(vocals_path), str(output_dir), str(error_path)),
        daemon=True,
        name=f"demucs-align-worker-{job_id}",
    )
    process.start()
    job_store.update(job_id, process=process)

    while _process_is_running(process):
        job = job_store.require(job_id)
        if job.cancel_requested:
            _terminate_process(process)
            raise _JobCanceled()
        time.sleep(0.25)

    job = job_store.require(job_id)
    if job.cancel_requested or job.status == "canceled":
        raise _JobCanceled()

    exitcode = getattr(process, "exitcode", 0)
    if exitcode not in (0, None):
        detail = (
            error_path.read_text(encoding="utf-8").strip()
            if error_path.exists()
            else f"WhisperX alignment exited with status {exitcode}"
        )
        raise RuntimeError(detail)
    if not aligned_path.exists():
        raise RuntimeError("Aligned lyrics were not created")
    return aligned_path


def _run_job(job_id: str, input_path: Path, config: SeparateConfig) -> None:
    start = time.time()
    output_dir = OUTPUT_ROOT / job_id
    job = job_store.require(job_id)
    if job.cancel_requested or job.status == "canceled":
        job_store.update(
            job_id,
            status="canceled",
            finished_at=utc_now(),
            duration_ms=0,
            progress_message="Canceled",
            process=None,
        )
        _cleanup_job_files(job_id)
        return
    cmd = _build_command(input_path, output_dir, config)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    job_store.update(
        job_id,
        status="running",
        started_at=utc_now(),
        progress_percent=0,
        progress_message="Starting Demucs",
        process=process,
    )

    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            job_store.append_output(job_id, line)
            percent, message = parse_progress_line(line)
            _update_job_progress(job_id, percent=percent, message=message)

            job = job_store.require(job_id)
            if job.cancel_requested:
                _terminate_process(process)
                break

        return_code = _wait_for_process(process)
        duration_ms = int((time.time() - start) * 1000)
        job = job_store.require(job_id)
        no_vocals_path, vocals_path = build_expected_output_paths(job_id, input_path, config)

        if job.cancel_requested:
            job_store.update(
                job_id,
                status="canceled",
                finished_at=utc_now(),
                duration_ms=duration_ms,
                progress_message="Canceled",
                process=None,
            )
            _cleanup_job_files(job_id)
            return

        if return_code != 0:
            raise RuntimeError(f"Demucs exited with status {return_code}")
        if not no_vocals_path.exists() or not vocals_path.exists():
            raise RuntimeError("Demucs output files were not created")

        aligned_lyrics_path = None
        if config.lyrics_text:
            job_store.update(
                job_id,
                progress_percent=95,
                progress_message="Aligning lyrics",
            )
            aligned_lyrics_path = _align_lyrics_in_child_process(
                job_id,
                config=config,
                vocals_path=vocals_path,
                output_dir=output_dir,
            )

        job_store.update(
            job_id,
            status="completed",
            finished_at=utc_now(),
            duration_ms=duration_ms,
            progress_percent=100,
            progress_message="Completed",
            no_vocals_path=str(no_vocals_path),
            vocals_path=str(vocals_path),
            aligned_lyrics_path=str(aligned_lyrics_path) if aligned_lyrics_path else None,
            process=None,
        )
    except _JobCanceled:
        duration_ms = int((time.time() - start) * 1000)
        job_store.update(
            job_id,
            status="canceled",
            finished_at=utc_now(),
            duration_ms=duration_ms,
            progress_message="Canceled",
            process=None,
        )
        _cleanup_job_files(job_id)
    except Exception as error:
        duration_ms = int((time.time() - start) * 1000)
        job_store.update(
            job_id,
            status="failed",
            finished_at=utc_now(),
            duration_ms=duration_ms,
            error_detail=str(error),
            progress_message="Failed",
            process=None,
        )
    finally:
        try:
            _run_garbage_collection(requested_mode="adaptive", triggered_by="job_completion")
        except HTTPException:
            pass
        except Exception:
            logger.exception("Post-job Demucs garbage collection failed")
        _cleanup_expired_jobs()


def _start_job(payload: bytes, original_filename: str, config: SeparateConfig) -> DemucsJobState:
    _cleanup_expired_jobs()
    job_id, _incoming_dir, _output_dir, input_path = prepare_job_input(payload, original_filename)
    job = job_store.create(
        DemucsJobState(
            job_id=job_id,
            model=config.model,
            device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
            original_filename=original_filename,
            job_kind="separation_with_lyrics" if config.lyrics_text else "separation",
        )
    )
    worker = threading.Thread(
        target=_run_job,
        args=(job_id, input_path, config),
        daemon=True,
        name=f"demucs-job-{job_id}",
    )
    worker.start()
    return job


def _run_alignment_job(job_id: str, input_path: Path, config: SeparateConfig) -> None:
    start = time.time()
    output_dir = OUTPUT_ROOT / job_id
    try:
        job = job_store.require(job_id)
        if job.cancel_requested or job.status == "canceled":
            raise _JobCanceled()
        job_store.update(
            job_id,
            status="running",
            started_at=utc_now(),
            progress_percent=5,
            progress_message="Aligning lyrics",
        )
        if not config.lyrics_text:
            raise RuntimeError("lyrics_text is required for alignment")
        aligned_lyrics_path = _align_lyrics_in_child_process(
            job_id,
            config=config,
            vocals_path=input_path,
            output_dir=output_dir,
        )
        if aligned_lyrics_path is None or not aligned_lyrics_path.exists():
            raise RuntimeError("Aligned lyrics were not created")
        duration_ms = int((time.time() - start) * 1000)
        job_store.update(
            job_id,
            status="completed",
            finished_at=utc_now(),
            duration_ms=duration_ms,
            progress_percent=100,
            progress_message="Completed",
            aligned_lyrics_path=str(aligned_lyrics_path),
            process=None,
        )
    except _JobCanceled:
        duration_ms = int((time.time() - start) * 1000)
        job_store.update(
            job_id,
            status="canceled",
            finished_at=utc_now(),
            duration_ms=duration_ms,
            progress_message="Canceled",
            process=None,
        )
    except Exception as error:
        duration_ms = int((time.time() - start) * 1000)
        job_store.update(
            job_id,
            status="failed",
            finished_at=utc_now(),
            duration_ms=duration_ms,
            error_detail=str(error),
            progress_message="Failed",
            process=None,
        )
    finally:
        try:
            _run_garbage_collection(requested_mode="adaptive", triggered_by="job_completion")
        except HTTPException:
            pass
        except Exception:
            logger.exception("Post-alignment Demucs garbage collection failed")
        _cleanup_expired_jobs()


def _start_alignment_job(payload: bytes, original_filename: str, config: SeparateConfig) -> DemucsJobState:
    _cleanup_expired_jobs()
    job_id, _incoming_dir, _output_dir, input_path = prepare_job_input(payload, original_filename)
    job = job_store.create(
        DemucsJobState(
            job_id=job_id,
            model=config.model,
            device=config.device,
            output_format=config.output_format,
            mp3_bitrate=config.mp3_bitrate,
            original_filename=original_filename,
            job_kind="lyrics_alignment",
        )
    )
    worker = threading.Thread(
        target=_run_alignment_job,
        args=(job_id, input_path, config),
        daemon=True,
        name=f"demucs-align-job-{job_id}",
    )
    worker.start()
    return job


@app.on_event("startup")
def _startup_preload_whisperx_models() -> None:
    try:
        preload_models(DEFAULT_WHISPERX_PRELOAD_MODELS, device=DEFAULT_DEMUCS_DEVICE)
    except Exception:
        logger.exception(
            "WhisperX preload failed during Demucs startup model=%s device=%s",
            DEFAULT_WHISPERX_PRELOAD_MODELS,
            DEFAULT_DEMUCS_DEVICE,
        )
    startup_health = _health_snapshot()
    if startup_health["status"] == "ok":
        logger.info(
            "Demucs startup healthy model=%s device=%s detail=%s checks=%s",
            startup_health["model"],
            startup_health["device"],
            startup_health["detail"],
            startup_health["checks"],
        )
    else:
        logger.error(
            "Demucs startup degraded model=%s device=%s detail=%s checks=%s",
            startup_health["model"],
            startup_health["device"],
            startup_health["detail"],
            startup_health["checks"],
        )
    _ensure_gc_scheduler_started()


@app.on_event("shutdown")
def _shutdown_gc_scheduler() -> None:
    _gc_scheduler_stop_event.set()


def _validated_config(
    model: str,
    device: Literal["cuda", "cpu"],
    output_format: Literal["wav", "mp3"],
    mp3_bitrate: int | None,
    lyrics_text: str | None = None,
    lyrics_format: str | None = None,
    transcription_model: str = DEFAULT_WHISPERX_TRANSCRIPTION_MODEL,
    align_language: str | None = DEFAULT_WHISPERX_ALIGN_LANGUAGE,
    detect_language: bool = DEFAULT_WHISPERX_DETECT_LANGUAGE,
    use_synced_lyrics: bool = DEFAULT_WHISPERX_USE_SYNCED_LYRICS,
    whisperx_preload_models: str | None = None,
    process_lyrics_lines: bool = False,
    max_line_length: int = 36,
    max_line_length_cjk: int = 12,
    compute_type: str | None = None,
) -> SeparateConfig:
    try:
        config = SeparateConfig(
            model=model,
            device=device,
            output_format=output_format,
            mp3_bitrate=mp3_bitrate,
            lyrics_text=lyrics_text,
            lyrics_format=lyrics_format,
            transcription_model=transcription_model,
            align_language=align_language,
            detect_language=detect_language,
            use_synced_lyrics=use_synced_lyrics,
            whisperx_preload_models=whisperx_preload_models,
            process_lyrics_lines=process_lyrics_lines,
            max_line_length=max_line_length,
            max_line_length_cjk=max_line_length_cjk,
            compute_type=compute_type,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error

    if config.device == "cuda" and not _cuda_available():
        raise HTTPException(
            status_code=503,
            detail="CUDA requested but unavailable on Demucs host",
        )
    return config


def _wait_for_terminal_job(job_id: str, *, timeout_seconds: float = 600.0) -> DemucsJobState:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = job_store.require(job_id)
        if job.status in {"completed", "failed", "canceled"}:
            return job
        time.sleep(0.25)
    raise HTTPException(status_code=504, detail="Timed out waiting for Demucs job")


@app.get("/health")
def health():
    return _health_snapshot()


@app.get("/transfer", response_class=HTMLResponse)
def transfer_page(request: Request):
    return HTMLResponse(_transfer_page_html(request=request))


@app.post("/transfer/upload", response_model=TransferUploadResponse)
async def transfer_upload(file: UploadFile = File(...)):
    received_bytes = 0
    try:
        received_bytes = await _drain_upload_file(file)
    finally:
        await file.close()
    return TransferUploadResponse(
        transfer_mode="multipart",
        received_bytes=received_bytes,
        received_filename=file.filename,
        detail="Multipart upload received and discarded",
    )


@app.post("/transfer/upload/raw", response_model=TransferUploadResponse)
async def transfer_upload_raw(request: Request):
    received_bytes = 0
    async for chunk in request.stream():
        received_bytes += len(chunk)
    return TransferUploadResponse(
        transfer_mode="raw",
        received_bytes=received_bytes,
        detail="Raw upload received and discarded",
    )


@app.get("/transfer/download/random-25mb", name="transfer_random_download")
def transfer_random_download():
    path = _ensure_random_transfer_file()
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=TRANSFER_RANDOM_FILENAME,
    )


@app.get("/metrics", response_model=DemucsMetricsResponse)
def metrics():
    return _active_jobs_snapshot()


@app.post("/whisperx/preload", response_model=WhisperXPreloadResponse)
def preload_whisperx(
    whisperx_preload_models: str | None = Form(DEFAULT_WHISPERX_PRELOAD_MODELS),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    compute_type: str | None = Form(None),
):
    if not whisperx_preload_models or not whisperx_preload_models.strip():
        raise HTTPException(status_code=400, detail="whisperx_preload_models cannot be empty")
    if not whisperx_available():
        raise HTTPException(status_code=503, detail="WhisperX is not installed in this environment")

    loaded_entries = preload_models(
        whisperx_preload_models,
        device=device,
        compute_type=compute_type,
    )
    detail = f"Preloaded {len(loaded_entries)} WhisperX model entr" + ("y" if len(loaded_entries) == 1 else "ies")
    return WhisperXPreloadResponse(
        requested_models=whisperx_preload_models.strip(),
        device=device,
        compute_type=compute_type,
        loaded_entries=loaded_entries,
        detail=detail,
    )


@app.post("/jobs", response_model=DemucsJobCreateResponse, status_code=202)
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
    lyrics_text: str | None = Form(None),
    lyrics_format: str | None = Form(None),
    transcription_model: str = Form(DEFAULT_WHISPERX_TRANSCRIPTION_MODEL),
    align_language: str | None = Form(DEFAULT_WHISPERX_ALIGN_LANGUAGE),
    detect_language: bool = Form(DEFAULT_WHISPERX_DETECT_LANGUAGE),
    use_synced_lyrics: bool = Form(DEFAULT_WHISPERX_USE_SYNCED_LYRICS),
    whisperx_preload_models: str | None = Form(DEFAULT_WHISPERX_PRELOAD_MODELS),
    process_lyrics_lines: bool = Form(False),
    max_line_length: int = Form(36),
    max_line_length_cjk: int = Form(12),
    compute_type: str | None = Form(None),
):
    config = _validated_config(
        model,
        device,
        output_format,
        mp3_bitrate,
        lyrics_text=lyrics_text,
        lyrics_format=lyrics_format,
        transcription_model=transcription_model,
        align_language=align_language,
        detect_language=detect_language,
        use_synced_lyrics=use_synced_lyrics,
        whisperx_preload_models=whisperx_preload_models,
        process_lyrics_lines=process_lyrics_lines,
        max_line_length=max_line_length,
        max_line_length_cjk=max_line_length_cjk,
        compute_type=compute_type,
    )
    payload = await file.read()
    job = _start_job(payload, file.filename or "input.wav", config)
    base = str(request.base_url).rstrip("/")
    return DemucsJobCreateResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        progress_message=job.progress_message,
        status_url=f"{base}/jobs/{job.job_id}",
        result_url=f"{base}/jobs/{job.job_id}/result",
        cancel_url=f"{base}/jobs/{job.job_id}",
    )


@app.post("/align-jobs", response_model=DemucsJobCreateResponse, status_code=202)
async def create_alignment_job(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
    lyrics_text: str | None = Form(None),
    lyrics_format: str | None = Form(None),
    transcription_model: str = Form(DEFAULT_WHISPERX_TRANSCRIPTION_MODEL),
    align_language: str | None = Form(DEFAULT_WHISPERX_ALIGN_LANGUAGE),
    detect_language: bool = Form(DEFAULT_WHISPERX_DETECT_LANGUAGE),
    use_synced_lyrics: bool = Form(DEFAULT_WHISPERX_USE_SYNCED_LYRICS),
    whisperx_preload_models: str | None = Form(DEFAULT_WHISPERX_PRELOAD_MODELS),
    process_lyrics_lines: bool = Form(False),
    max_line_length: int = Form(36),
    max_line_length_cjk: int = Form(12),
    compute_type: str | None = Form(None),
):
    config = _validated_config(
        model,
        device,
        output_format,
        mp3_bitrate,
        lyrics_text=lyrics_text,
        lyrics_format=lyrics_format,
        transcription_model=transcription_model,
        align_language=align_language,
        detect_language=detect_language,
        use_synced_lyrics=use_synced_lyrics,
        whisperx_preload_models=whisperx_preload_models,
        process_lyrics_lines=process_lyrics_lines,
        max_line_length=max_line_length,
        max_line_length_cjk=max_line_length_cjk,
        compute_type=compute_type,
    )
    if not config.lyrics_text:
        raise HTTPException(status_code=422, detail="lyrics_text is required for alignment")
    payload = await file.read()
    job = _start_alignment_job(payload, file.filename or "vocals.wav", config)
    base = str(request.base_url).rstrip("/")
    return DemucsJobCreateResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        progress_message=job.progress_message,
        status_url=f"{base}/jobs/{job.job_id}",
        result_url=f"{base}/align-jobs/{job.job_id}/result",
        cancel_url=f"{base}/jobs/{job.job_id}",
    )


@app.get("/jobs/{job_id}", response_model=DemucsJobStatusResponse)
def get_job(job_id: str):
    try:
        job = job_store.require(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error
    return _job_to_status_response(job)


@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str):
    try:
        job = job_store.require(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    if job.status == "failed":
        raise HTTPException(status_code=409, detail=job.error_detail or "Job failed")
    if job.status == "canceled":
        raise HTTPException(status_code=409, detail="Job was canceled")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Job is not complete")

    no_vocals_path = Path(job.no_vocals_path or "")
    vocals_path = Path(job.vocals_path or "")
    if not no_vocals_path.exists() or not vocals_path.exists():
        raise HTTPException(status_code=500, detail="Job outputs are unavailable")

    result = type(
        "DemucsResult",
        (),
        {
            "job_id": job.job_id,
            "no_vocals_path": no_vocals_path,
            "vocals_path": vocals_path,
            "duration_ms": job.duration_ms,
            "model": job.model,
            "device": job.device,
            "output_format": job.output_format,
            "mp3_bitrate": job.mp3_bitrate,
            "aligned_lyrics_path": Path(job.aligned_lyrics_path) if job.aligned_lyrics_path else None,
        },
    )()
    zip_payload = _build_stems_zip(result)
    headers = {
        "X-Job-Id": job.job_id,
        "X-Model": job.model,
        "X-Device": job.device,
        "X-Output-Format": job.output_format,
        "X-Duration-Ms": str(job.duration_ms or 0),
        "X-Vocals-Path": str(vocals_path),
        "X-Response-Format": "zip",
    }
    if job.mp3_bitrate is not None:
        headers["X-Mp3-Bitrate"] = str(job.mp3_bitrate)
    return Response(content=zip_payload, media_type="application/zip", headers=headers)


@app.get("/align-jobs/{job_id}/result")
def get_alignment_job_result(job_id: str):
    try:
        job = job_store.require(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    if job.status == "failed":
        raise HTTPException(status_code=409, detail=job.error_detail or "Job failed")
    if job.status == "canceled":
        raise HTTPException(status_code=409, detail="Job was canceled")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Job is not complete")
    if job.job_kind != "lyrics_alignment":
        raise HTTPException(status_code=409, detail="Job is not a lyrics alignment job")

    aligned_lyrics_path = Path(job.aligned_lyrics_path or "")
    if not aligned_lyrics_path.exists():
        raise HTTPException(status_code=500, detail="Aligned lyrics output is unavailable")
    headers = {
        "X-Job-Id": job.job_id,
        "X-Model": job.model,
        "X-Device": job.device,
        "X-Duration-Ms": str(job.duration_ms or 0),
    }
    return Response(
        content=aligned_lyrics_path.read_bytes(),
        media_type="application/json",
        headers=headers,
    )


@app.delete("/jobs/{job_id}", status_code=202)
def cancel_job(job_id: str):
    try:
        job = job_store.require(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    if job.status in {"completed", "failed", "canceled"}:
        return {"job_id": job_id, "status": job.status}

    started_at = job.started_at or utc_now()
    duration_ms = int((utc_now() - started_at).total_seconds() * 1000)
    job_store.update(
        job_id,
        cancel_requested=True,
        status="canceled",
        finished_at=utc_now(),
        duration_ms=max(0, duration_ms),
        progress_message="Canceled",
    )
    process = job.process
    _terminate_process(process)
    job_store.update(job_id, process=None)
    _cleanup_job_files(job_id)
    try:
        _run_garbage_collection(requested_mode="adaptive", triggered_by="cancellation")
    except HTTPException:
        pass
    except Exception:
        logger.exception("Post-cancel Demucs garbage collection failed job_id=%s", job_id)
    return {"job_id": job_id, "status": "canceled"}


@app.delete("/jobs/{job_id}/artifacts", response_model=DemucsJobArtifactDeleteResponse)
def delete_job_artifacts(job_id: str):
    try:
        job = job_store.require(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    if job.status in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail="Job is still active; cancel it before deleting artifacts",
        )

    job_store.delete(job_id)
    _cleanup_job_files(job_id)
    return DemucsJobArtifactDeleteResponse(
        job_id=job_id,
        status=job.status,
        detail="Deleted Demucs job input/output artifacts",
    )


@app.get("/io", response_model=DemucsIoUsageResponse)
def get_io_usage():
    return _io_usage_snapshot()


@app.delete("/io", response_model=DemucsIoCleanupResponse)
def cleanup_io():
    response = _cleanup_io()
    _cleanup_expired_jobs()
    return response


@app.post("/separate")
async def separate(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
    lyrics_text: str | None = Form(None),
    lyrics_format: str | None = Form(None),
    transcription_model: str = Form(DEFAULT_WHISPERX_TRANSCRIPTION_MODEL),
    align_language: str | None = Form(DEFAULT_WHISPERX_ALIGN_LANGUAGE),
    detect_language: bool = Form(DEFAULT_WHISPERX_DETECT_LANGUAGE),
    use_synced_lyrics: bool = Form(DEFAULT_WHISPERX_USE_SYNCED_LYRICS),
    whisperx_preload_models: str | None = Form(DEFAULT_WHISPERX_PRELOAD_MODELS),
    process_lyrics_lines: bool = Form(False),
    max_line_length: int = Form(36),
    max_line_length_cjk: int = Form(12),
    compute_type: str | None = Form(None),
):
    config = _validated_config(
        model,
        device,
        output_format,
        mp3_bitrate,
        lyrics_text=lyrics_text,
        lyrics_format=lyrics_format,
        transcription_model=transcription_model,
        align_language=align_language,
        detect_language=detect_language,
        use_synced_lyrics=use_synced_lyrics,
        whisperx_preload_models=whisperx_preload_models,
        process_lyrics_lines=process_lyrics_lines,
        max_line_length=max_line_length,
        max_line_length_cjk=max_line_length_cjk,
        compute_type=compute_type,
    )
    payload = await file.read()
    job = _start_job(payload, file.filename or "input.wav", config)
    terminal_job = _wait_for_terminal_job(job.job_id)
    if terminal_job.status == "failed":
        raise HTTPException(status_code=500, detail=f"Demucs failed: {terminal_job.error_detail}")
    if terminal_job.status == "canceled":
        raise HTTPException(status_code=500, detail="Demucs job was canceled")
    return get_job_result(job.job_id)


@app.post("/separate-meta", response_model=SeparateMetaResponse)
async def separate_meta(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_DEMUCS_MODEL),
    device: Literal["cuda", "cpu"] = Form(DEFAULT_DEMUCS_DEVICE),
    output_format: Literal["wav", "mp3"] = Form(DEFAULT_OUTPUT_FORMAT),
    mp3_bitrate: int | None = Form(None),
    lyrics_text: str | None = Form(None),
    lyrics_format: str | None = Form(None),
    transcription_model: str = Form(DEFAULT_WHISPERX_TRANSCRIPTION_MODEL),
    align_language: str | None = Form(DEFAULT_WHISPERX_ALIGN_LANGUAGE),
    detect_language: bool = Form(DEFAULT_WHISPERX_DETECT_LANGUAGE),
    use_synced_lyrics: bool = Form(DEFAULT_WHISPERX_USE_SYNCED_LYRICS),
    whisperx_preload_models: str | None = Form(DEFAULT_WHISPERX_PRELOAD_MODELS),
    process_lyrics_lines: bool = Form(False),
    max_line_length: int = Form(36),
    max_line_length_cjk: int = Form(12),
    compute_type: str | None = Form(None),
):
    config = _validated_config(
        model,
        device,
        output_format,
        mp3_bitrate,
        lyrics_text=lyrics_text,
        lyrics_format=lyrics_format,
        transcription_model=transcription_model,
        align_language=align_language,
        detect_language=detect_language,
        use_synced_lyrics=use_synced_lyrics,
        whisperx_preload_models=whisperx_preload_models,
        process_lyrics_lines=process_lyrics_lines,
        max_line_length=max_line_length,
        max_line_length_cjk=max_line_length_cjk,
        compute_type=compute_type,
    )

    try:
        payload = await file.read()
        result = run_demucs_on_file(payload, file.filename or "input.wav", config)
        aligned_lyrics_path = None
        if config.lyrics_text:
            aligned_lyrics_path = _align_lyrics(
                config=config,
                vocals_path=Path(result.vocals_path),
                output_dir=Path(result.vocals_path).parent,
            )
    except subprocess.CalledProcessError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Demucs failed: {error.stderr}",
        ) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return SeparateMetaResponse(
        job_id=result.job_id,
        no_vocals_path=str(result.no_vocals_path),
        vocals_path=str(result.vocals_path),
        model=result.model,
        device=result.device,
        output_format=result.output_format,
        mp3_bitrate=result.mp3_bitrate,
        duration_ms=result.duration_ms,
        status="completed",
        aligned_lyrics_path=str(aligned_lyrics_path) if aligned_lyrics_path else None,
    )

@app.post("/gc", response_model=DemucsGarbageCollectionResponse)
def trigger_garbage_collection(
    mode: Literal["adaptive", "partial", "cuda", "full"] = "adaptive",
):
    response = _run_garbage_collection(requested_mode=mode, triggered_by="manual")
    _cleanup_expired_jobs()
    return response
