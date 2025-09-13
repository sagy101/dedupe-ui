import os
import hashlib
import importlib.util
from pathlib import Path

# ================== Config ==================
READ_CHUNK = 8 * 1024 * 1024  # 8MB
DEFAULT_WORKERS = min(16, max(4, (os.cpu_count() or 4) * 2))

def has_blake3() -> bool:
    try:
        return importlib.util.find_spec("blake3") is not None
    except Exception:
        return False

def new_hasher(algo: str):
    """Lazy hasher factory (imports blake3 only if selected and available)."""
    a = algo.lower()
    if a == "blake3":
        import blake3  # type: ignore
        return blake3.blake3()
    return hashlib.new("sha256")

def to_long_path(p: str | Path) -> str:
    r"""Return a path string with Windows long-path prefixes when needed."""
    path_str = str(p)
    if os.name != "nt":
        return path_str
    path_str = os.path.abspath(path_str)
    if path_str.startswith("\\\\?\\"):
        return path_str
    if path_str.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_str[2:]
    return "\\\\?\\" + path_str

def human_size(n: int) -> str:
    x = float(n)
    for u in ("B","KB","MB","GB","TB"):
        if x < 1024 or u == "TB":
            return f"{x:.1f} {u}" if u != "B" else f"{int(x)} {u}"
        x /= 1024.0

def iter_files(folder: str | Path):
    for path in Path(folder).rglob("*"):
        if path.is_file():
            yield str(path)
