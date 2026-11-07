"""Build the source ZIP and print its SHA-256 (manual release helper).

Usage:  python tools/build_release.py [--out release_web/downloads]
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {".git", ".venv", "__pycache__", "release", "release_web",
                "build", "dist", ".github"}


def iter_source_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in EXCLUDE_DIRS:
            continue
        if "__pycache__" in rel.parts:
            continue
        yield path, rel


def build(out_dir: Path | None = None) -> Path:
    from vocaloidtts import __version__

    target_dir = out_dir or (ROOT / "release_web" / "downloads")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"VocaloidTTS_v{__version__}_source.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, rel in iter_source_files(ROOT):
            archive.write(path, rel.as_posix())
    return target


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    target = build(args.out)
    print(f"built: {target}")
    print(f"size:  {target.stat().st_size / 1024:.0f} KB")
    print(f"sha256: {sha256(target)}")


if __name__ == "__main__":
    main()
