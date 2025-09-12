import os
import hashlib
import importlib.util

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

def to_long_path(p: str) -> str:
    r"""Long-path safe Windows path with \\?\ and \\?\UNC\ prefixes when needed."""
    if os.name != "nt":
        return p
    p = os.path.abspath(p)
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p

def human_size(n: int) -> str:
    x = float(n)
    for u in ("B","KB","MB","GB","TB"):
        if x < 1024 or u == "TB":
            return f"{x:.1f} {u}" if u != "B" else f"{int(x)} {u}"
        x /= 1024.0

def iter_files(folder: str):
    for root, _, files in os.walk(folder):
        for name in files:
            yield os.path.join(root, name)
