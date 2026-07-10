from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

from .separation.sherpa_spleeter import MODEL_DIRECTORIES, MODEL_FILES
from .settings import settings


RELEASE_BASE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/source-separation-models"
)


def _archive_name(variant: str) -> str:
    return f"{MODEL_DIRECTORIES[variant]}.tar.bz2"


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.getmembers():
        if member.issym() or member.islnk():
            raise RuntimeError(f"Archive links are not allowed: {member.name}")
        target = (destination / member.name).resolve()
        if target != destination_resolved and destination_resolved not in target.parents:
            raise RuntimeError(f"Unsafe archive path: {member.name}")
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not member.isfile():
            raise RuntimeError(f"Unsupported archive member: {member.name}")
        source = archive.extractfile(member)
        if source is None:
            raise RuntimeError(f"Unable to read archive member: {member.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def install_variant(variant: str, model_root: Path) -> Path:
    if variant not in MODEL_FILES:
        raise ValueError(f"Unsupported variant: {variant}")

    model_root.mkdir(parents=True, exist_ok=True)
    archive_name = _archive_name(variant)
    with tempfile.TemporaryDirectory(prefix="sherpa-spleeter-") as temp_raw:
        temp_dir = Path(temp_raw)
        archive_path = temp_dir / archive_name
        with urlopen(f"{RELEASE_BASE_URL}/{archive_name}", timeout=120) as response:
            with archive_path.open("wb") as output:
                shutil.copyfileobj(response, output)

        extract_root = temp_dir / "extract"
        extract_root.mkdir()
        with tarfile.open(archive_path, mode="r:bz2") as archive:
            _safe_extract(archive, extract_root)

        source_dir = extract_root / MODEL_DIRECTORIES[variant]
        expected = [source_dir / name for name in MODEL_FILES[variant]]
        missing = [path.name for path in expected if not path.is_file() or path.stat().st_size == 0]
        if missing:
            raise RuntimeError(f"Downloaded archive is missing model files: {', '.join(missing)}")

        target_dir = model_root / MODEL_DIRECTORIES[variant]
        staged_dir = model_root / f".{MODEL_DIRECTORIES[variant]}.tmp"
        backup_dir = model_root / f".{MODEL_DIRECTORIES[variant]}.old"
        shutil.rmtree(staged_dir, ignore_errors=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.copytree(source_dir, staged_dir)
        if target_dir.exists():
            target_dir.replace(backup_dir)
        try:
            staged_dir.replace(target_dir)
        except Exception:
            if backup_dir.exists() and not target_dir.exists():
                backup_dir.replace(target_dir)
            raise
        shutil.rmtree(backup_dir, ignore_errors=True)
        return target_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Sherpa+Spleeter ONNX models")
    parser.add_argument(
        "--variant",
        choices=["fp16", "int8", "fp32", "all"],
        default="fp16",
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=settings.sherpa_spleeter_model_root,
    )
    args = parser.parse_args()
    variants = list(MODEL_FILES) if args.variant == "all" else [args.variant]
    for variant in variants:
        installed = install_variant(variant, args.model_root.expanduser().resolve())
        print(f"Installed {variant}: {installed}")


if __name__ == "__main__":
    main()
