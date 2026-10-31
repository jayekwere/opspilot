"""Refresh artifact hashes for already pinned dependency versions from PyPI."""

import concurrent.futures
import json
import re
import urllib.request
from pathlib import Path


def hashed(line: str) -> str:
    name, version = line.split("==")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name + version):
        raise ValueError("unexpected package pin")
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=20) as response:  # nosec B310
        data = json.load(response)
    hashes = sorted({entry["digests"]["sha256"] for entry in data["urls"]})
    if not hashes:
        raise ValueError("no distribution hashes")
    return line + "".join(" \\\n    --hash=sha256:" + digest for digest in hashes) + "\n"


def refresh(path: Path) -> None:
    pins = [
        line.strip().rstrip(" \\")
        for line in path.read_text().splitlines()
        if "==" in line and not line.lstrip().startswith("#")
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        output = list(pool.map(hashed, pins))
    path.write_text(
        "# Pinned distributions with PyPI SHA-256 hashes. Refresh with scripts/lock_hashes.py.\n"
        + "\n".join(output)
    )


if __name__ == "__main__":
    refresh(Path("requirements.lock"))
    refresh(Path("requirements-dev.lock"))
