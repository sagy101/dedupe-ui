from concurrent.futures import ThreadPoolExecutor, as_completed

from hashing import file_digest

# ================== Stage 2 Verifier (hash on demand) ==================
class Verifier:
    """
    Given selected candidate rows, compute B hash, then compute A hash for each a_path until a match or exhaustion.
    Marks status MATCH (green) or DIFF (red). Skips any row that's already verified.
    """
    def __init__(self, algo: str, workers: int, ui_progress=None, ui_counter=None):
        self.algo = algo

        self.workers = max(1, workers)
        self.ui_progress = ui_progress or (lambda txt, pct: None)
        self.ui_counter = ui_counter or (lambda done, total, matches: None)

    def verify_rows(self, rows: list[dict]):
        pending = [r for r in rows if r.get("status") == "PENDING"]
        total = len(pending)
        if total == 0:
            self.ui_progress("Stage 2: nothing to verify (all selected rows already checked).", None)
            return 0, 0
        self.ui_progress(f"Stage 2: hashing {total} selected item(s) with {self.algo}…", 0.0)
        done = 0
        matches = 0

        # Hash helper using cache
        def _digest(path):
            d, _ = file_digest(path, self.algo)
            return d

        # Hash all B first (parallel)
        def _hash_b(row):
            try:
                hb = _digest(row["path_b"])
                return (row, hb, None)
            except Exception as e:
                return (row, None, f"hash_B: {e}")

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futures = [ex.submit(_hash_b, r) for r in pending]
            for fut in as_completed(futures):
                row, hb, err = fut.result()
                if err:
                    row["status"] = "ERROR"
                    row["hash_b"] = None
                    row["hash_algo"] = self.algo
                else:
                    row["hash_b"] = hb
                    row["hash_algo"] = self.algo

        # For each row, compute A hashes lazily until we find a match
        for row in pending:
            if row["status"] == "ERROR":
                done += 1
                self.ui_progress(f"Stage 2: verified {done}/{total}", done/max(1,total))
                self.ui_counter(done, total, matches)
                continue
            try:
                matched = False
                for ap in row["a_paths"]:
                    ha = _digest(ap)
                    row["hash_a"] = ha
                    if ha == row["hash_b"]:
                        matched = True
                        row["status"] = "MATCH"
                        matches += 1
                        # put this A path first (for display)
                        if row["a_paths"][0] != ap:
                            row["a_paths"].remove(ap)
                            row["a_paths"].insert(0, ap)
                        break
                if not matched:
                    row["status"] = "DIFF"
            except Exception:
                row["status"] = "ERROR"
            finally:
                done += 1
                self.ui_progress(f"Stage 2: verified {done}/{total}", done/max(1,total))
                self.ui_counter(done, total, matches)

        self.ui_progress(f"Stage 2: done. Verified {done} item(s), {matches} match(es).", 1.0)
        return done, matches
