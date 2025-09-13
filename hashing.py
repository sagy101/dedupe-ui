import os
import json
import threading
from pathlib import Path

from platformdirs import user_cache_dir

from utils import to_long_path, new_hasher, READ_CHUNK


def _cache_path() -> Path:
    cache_dir = Path(user_cache_dir("DedupeUI"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "hash_cache.json"

# ================== Hash Cache ==================
class HashCache:
    """JSON cache keyed by (path,size,mtime_ns,algo)."""
    def __init__(self):
        self.path = _cache_path()
        self.data = {}
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    self.data = json.load(f)
        except Exception:
            self.data = {}
        self.lock = threading.Lock()
        self.version = 1

    def _key(self, path: str, size: int, mtime_ns: int, algo: str):
        return f"{path}|{size}|{mtime_ns}|{algo}|v{self.version}"

    def get(self, path: str, size: int, mtime_ns: int, algo: str):
        return self.data.get(self._key(path, size, mtime_ns, algo))

    def put(self, path: str, size: int, mtime_ns: int, algo: str, digest: str):
        with self.lock:
            self.data[self._key(path, size, mtime_ns, algo)] = digest

    def save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(self.data, f)
            tmp.replace(self.path)
        except Exception:
            pass

HASH_CACHE = HashCache()

def file_digest(path: str, algo: str) -> tuple[str, int]:
    """Return (hex_digest, size) with caching on (path,size,mtime,algo)."""
    lp = to_long_path(path)
    st = os.stat(lp)
    size = st.st_size
    mtime_ns = int(st.st_mtime_ns)
    cached = HASH_CACHE.get(lp, size, mtime_ns, algo)
    if cached:
        return cached, size
    h = new_hasher(algo)
    with open(lp, "rb", buffering=READ_CHUNK) as f:
        while True:
            b = f.read(READ_CHUNK)
            if not b:
                break
            h.update(b)
    digest = h.hexdigest().lower()
    HASH_CACHE.put(lp, size, mtime_ns, algo, digest)
    return digest, size
