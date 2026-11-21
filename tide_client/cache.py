"""Optional local disk cache.

The cache lives in the transport (see transport.py); this module only
holds the small helpers a caller needs: where the cache lives and how
to clear it. Nothing here downloads or stores data by itself.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def default_cache_dir() -> Path:
    """Default cache location under the user's home directory."""
    return Path.home() / ".cache" / "tide-client"


def clear_cache(cache_dir: str | Path | None = None) -> int:
    """Delete cached response files. Returns the number of files removed."""
    directory = Path(cache_dir) if cache_dir else default_cache_dir()
    if not directory.exists():
        return 0
    count = sum(1 for _ in directory.iterdir() if _.is_file())
    shutil.rmtree(directory)
    return count
