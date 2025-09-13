from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

from hashing import file_digest

# ================== Stage 2 Verifier (hash on demand) ==================
class Verifier:
    """
    Given selected candidate rows, compute B hash, then compute A hash for each a_path until a match or exhaustion.
    Marks status MATCH (green) or DIFF (red). Skips any row that's already verified.
    """
    def __init__(
        self,
        algo: str,
        workers: int,
        ui_progress=None,
        ui_counter=None,
        ui_log=None,
        stop_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
    ):
        self.algo = algo

        self.workers = max(1, workers)
        self.ui_progress = ui_progress or (lambda txt, pct: None)
        self.ui_counter = ui_counter or (lambda done, total, matches: None)
        self.ui_log = ui_log or (lambda msg: None)
        self.stop_event = stop_event or threading.Event()
        self.pause_event = pause_event or threading.Event()

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
                if self.stop_event.is_set():
                    break
                while self.pause_event.is_set():
                    time.sleep(0.1)
                row, hb, err = fut.result()
                if err:
                    row["status"] = "ERROR"
                    row["hash_b"] = None
                    row["hash_algo"] = self.algo
                else:
                    row["hash_b"] = hb
                    row["hash_algo"] = self.algo
                self.ui_log(f"Hashed B: {row['path_b']}")

        # For each row, compute A hashes lazily until we find a match
        for row in pending:
            if self.stop_event.is_set():
                break
            while self.pause_event.is_set():
                time.sleep(0.1)

            if row["status"] == "ERROR":
                done += 1
                self.ui_progress(f"Stage 2: verified {done}/{total}", done/max(1,total))
                self.ui_counter(done, total, matches)
                continue

            matched = False
            hashed_any = False
            for ap in row["a_paths"]:
                if self.stop_event.is_set():
                    break
                while self.pause_event.is_set():
                    time.sleep(0.1)
                try:
                    ha = _digest(ap)
                    hashed_any = True
                    self.ui_log(f"Hashed A: {ap}")
                except Exception:
                    continue

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

            if matched:
                pass
            elif hashed_any:
                row["status"] = "DIFF"
            else:
                row["status"] = "ERROR"

            done += 1
            self.ui_progress(f"Stage 2: verified {done}/{total}", done/max(1,total))
            self.ui_counter(done, total, matches)

        if self.stop_event.is_set():
            self.ui_progress("Stage 2: stopped.", None)
        else:
            self.ui_progress(f"Stage 2: done. Verified {done} item(s), {matches} match(es).", 1.0)
        return done, matches
