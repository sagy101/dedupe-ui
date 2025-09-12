import os

from utils import iter_files, to_long_path

# ================== Stage 1 Scanner ==================
class Stage1Scanner:
    """
    Build an index of Folder A by (name_lower, size), then find candidate pairs in Folder B that share name+size.
    For each B candidate, store the list of possible A paths (all with the same name+size).
    No hashing here.
    """
    def __init__(self, folder_a: str, folder_b: str, ui_progress=None, ui_stats=None):
        self.A = folder_a
        self.B = folder_b
        self.ui_progress = ui_progress or (lambda txt, pct: None)
        self.ui_stats = ui_stats or (lambda d: None)
        self.errors = []
        self.a_total = 0
        self.a_done = 0
        self.candidates = 0

    def _prog(self, text: str, pct: float | None = None):
        self.ui_progress(text, pct)

    def _stats(self):
        self.ui_stats({"a_done": self.a_done, "a_total": self.a_total, "candidates": self.candidates})

    def run(self):
        # Index A by name+size
        a_map = {}  # name_lower -> {size -> [path_a,...]}
        files_a = list(iter_files(self.A))
        self.a_total = len(files_a); self.a_done = 0
        self._prog(f"Stage 1: indexing Folder A ({self.a_total} files)…", 0.0)
        self._stats()

        for p in files_a:
            try:
                sz = os.path.getsize(to_long_path(p))
                nl = os.path.basename(p).lower()
                a_map.setdefault(nl, {}).setdefault(sz, []).append(p)
            except Exception as e:
                self.errors.append((p, str(e)))
            finally:
                self.a_done += 1
                if self.a_done % 200 == 0 or self.a_done == self.a_total:
                    self._prog(f"Stage 1: indexed {self.a_done}/{self.a_total}", self.a_done/max(1,self.a_total))
                    self._stats()

        # Scan B for name+size matches
        results = []
        files_b = list(iter_files(self.B))
        total_b = len(files_b)
        done_b = 0
        self._prog(f"Stage 1: scanning Folder B for name+size matches ({total_b} files)…", 0.0)

        for p in files_b:
            try:
                nl = os.path.basename(p).lower()
                if nl not in a_map:
                    continue
                sz = os.path.getsize(to_long_path(p))
                a_paths = a_map[nl].get(sz)
                if not a_paths:
                    continue
                # candidate found; store all possible A paths for later hashing
                results.append({
                    "name": os.path.basename(p),
                    "size": sz,
                    "a_paths": list(a_paths),  # list of Folder-A paths with same name+size
                    "path_b": p,
                    "status": "PENDING",       # PENDING | MATCH | DIFF | ERROR | DELETED
                    "hash_algo": None,         # filled after verify
                    "hash_a": None,
                    "hash_b": None
                })
                self.candidates += 1
                self._stats()
            except Exception as e:
                self.errors.append((p, str(e)))
            finally:
                done_b += 1
                if done_b % 500 == 0 or done_b == total_b:
                    self._prog(f"Stage 1: scanned B {done_b}/{total_b}", done_b/max(1,total_b))
        self._prog(f"Stage 1: done. Found {len(results)} candidate(s).", 1.0)
        return results
