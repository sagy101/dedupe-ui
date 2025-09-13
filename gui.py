import os
import sys

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils import human_size, to_long_path, has_blake3, DEFAULT_WORKERS
from stage1 import Stage1Scanner
from verifier import Verifier
from hashing import HASH_CACHE


# -------------------- Worker Threads --------------------
class Stage1Worker(QObject):
    progress = Signal(str, float)
    stats = Signal(dict)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, folder_a: str, folder_b: str):
        super().__init__()
        self.folder_a = folder_a
        self.folder_b = folder_b

    def run(self):
        try:
            scanner = Stage1Scanner(
                self.folder_a,
                self.folder_b,
                ui_progress=lambda t, p: self.progress.emit(t, p),
                ui_stats=lambda d: self.stats.emit(d),
            )
            results = scanner.run()
            self.finished.emit(results)
        except Exception as e:  # pragma: no cover - safety
            self.error.emit(str(e))


class Stage2Worker(QObject):
    progress = Signal(str, float)
    counter = Signal(int, int, int)
    finished = Signal(int, int)
    error = Signal(str)

    def __init__(self, algo: str, workers: int, rows: list[dict]):
        super().__init__()
        self.algo = algo
        self.workers = workers
        self.rows = rows

    def run(self):
        try:
            verifier = Verifier(
                self.algo,
                self.workers,
                ui_progress=lambda t, p: self.progress.emit(t, p),
                ui_counter=lambda d, t, m: self.counter.emit(d, t, m),
            )
            done, matches = verifier.verify_rows(self.rows)
            self.finished.emit(done, matches)
        except Exception as e:  # pragma: no cover - safety
            self.error.emit(str(e))


# -------------------- Main Window --------------------
class App(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Two-Stage De-dupe (name+size → on-demand hash)")
        self.resize(1300, 780)
        self.setMinimumSize(1100, 600)

        self.algos = ["blake3", "sha256"] if has_blake3() else ["sha256"]
        self.candidates: list[dict] = []

        # -------------------- Layout --------------------
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top controls
        top_widget = QWidget(self)
        top = QGridLayout(top_widget)
        layout.addWidget(top_widget)

        top.addWidget(QLabel("Folder A (keep):"), 0, 0)
        self.entry_a = QLineEdit()
        top.addWidget(self.entry_a, 0, 1)
        btn_browse_a = QPushButton("Browse…")
        btn_browse_a.clicked.connect(self.browse_a)
        top.addWidget(btn_browse_a, 0, 2)

        top.addWidget(QLabel("Folder B (dedupe target):"), 1, 0)
        self.entry_b = QLineEdit()
        top.addWidget(self.entry_b, 1, 1)
        btn_browse_b = QPushButton("Browse…")
        btn_browse_b.clicked.connect(self.browse_b)
        top.addWidget(btn_browse_b, 1, 2)

        top.addWidget(QLabel("Hasher:"), 2, 0)
        self.algo_combo = QComboBox()
        self.algo_combo.addItems(self.algos)
        top.addWidget(self.algo_combo, 2, 1)

        top.addWidget(QLabel("Workers:"), 2, 2)
        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, 64)
        self.spin_workers.setValue(DEFAULT_WORKERS)
        top.addWidget(self.spin_workers, 2, 3)
        top.setColumnStretch(1, 1)

        # Actions
        actions = QHBoxLayout()
        layout.addLayout(actions)

        self.btn_stage1 = QPushButton("Stage 1: Find name+size candidates")
        self.btn_stage1.clicked.connect(self.start_stage1)
        actions.addWidget(self.btn_stage1)

        self.btn_verify_sel = QPushButton("Stage 2: Verify hash (selected)")
        self.btn_verify_sel.setEnabled(False)
        self.btn_verify_sel.clicked.connect(self.verify_selected)
        actions.addWidget(self.btn_verify_sel)

        self.btn_verify_all = QPushButton("Stage 2: Verify hash (all pending)")
        self.btn_verify_all.setEnabled(False)
        self.btn_verify_all.clicked.connect(self.verify_all_pending)
        actions.addWidget(self.btn_verify_all)

        self.btn_delete = QPushButton(
            "Delete Selected from Folder B (only verified matches)"
        )
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self.delete_selected_matches)
        actions.addWidget(self.btn_delete)

        # Progress & status
        status_layout = QHBoxLayout()
        layout.addLayout(status_layout)
        self.status_label = QLabel("Ready.")
        status_layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        status_layout.addWidget(self.progress_bar)

        # Stats
        stats_box = QGroupBox("Stats")
        layout.addWidget(stats_box)
        stats = QGridLayout(stats_box)

        self.label_a_done = QLabel("0")
        self.label_a_total = QLabel("0")
        self.label_candidates = QLabel("0")
        self.label_v_done = QLabel("0")
        self.label_v_total = QLabel("0")
        self.label_v_matches = QLabel("0")

        def row(r: int, label: str, *widgets):
            stats.addWidget(QLabel(label), r, 0)
            c = 1
            for w in widgets:
                if isinstance(w, str):
                    stats.addWidget(QLabel(w), r, c)
                else:
                    stats.addWidget(w, r, c)
                c += 1

        row(0, "A indexed:", self.label_a_done, "/", self.label_a_total)
        row(1, "Candidates (name+size):", self.label_candidates)
        row(
            2,
            "Verified this round:",
            self.label_v_done,
            "/",
            self.label_v_total,
            "   Matches:",
            self.label_v_matches,
        )
        for c in range(1, 8):
            stats.setColumnStretch(c, 1)

        # Search & filter controls
        filter_layout = QHBoxLayout()
        layout.addLayout(filter_layout)
        filter_layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        filter_layout.addWidget(self.search_box)
        filter_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "PENDING", "MATCH", "DIFF", "ERROR"])
        filter_layout.addWidget(self.status_filter)
        filter_layout.addStretch()

        self.search_box.textChanged.connect(self.refresh_table)
        self.status_filter.currentTextChanged.connect(self.refresh_table)

        # Table
        self.table = QTableWidget(0, 7)
        headers = [
            "Status",
            "Name",
            "Size",
            "Hash Algo",
            "Hash B",
            "Path A (first match if many)",
            "Path B",
        ]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.table.itemSelectionChanged.connect(self._on_selection_change)
        self.displayed_rows: list[int] = []

    # -------------------- Helpers --------------------
    def set_status(self, text: str, pct: float | None = None):
        self.status_label.setText(text)
        if pct is not None:
            self.progress_bar.setValue(int(max(0.0, min(1.0, pct)) * 100))
        QApplication.processEvents()

    def refresh_table(self):
        search = self.search_box.text().lower()
        status = self.status_filter.currentText()
        filtered = []
        for idx, r in enumerate(self.candidates):
            if status != "All" and r["status"] != status:
                continue
            if search and search not in r["name"].lower():
                continue
            filtered.append(idx)
        self.displayed_rows = filtered
        self.table.setRowCount(len(filtered))
        color_map = {
            "MATCH": QColor("#d9f7be"),
            "DIFF": QColor("#ffd6d6"),
            "ERROR": QColor("#ffe7ba"),
        }
        for row, idx in enumerate(filtered):
            r = self.candidates[idx]
            a_first = r["a_paths"][0] if r["a_paths"] else ""
            hash_b_short = (r["hash_b"][:16] + "…") if r.get("hash_b") else ""
            values = [
                r["status"],
                r["name"],
                human_size(r["size"]),
                r.get("hash_algo") or "",
                hash_b_short,
                a_first,
                r["path_b"],
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if r["status"] in color_map:
                    item.setBackground(color_map[r["status"]])
                self.table.setItem(row, col, item)
        self._on_selection_change()

    def _on_selection_change(self):
        rows = self.table.selectionModel().selectedRows()
        indices = [self.displayed_rows[r.row()] for r in rows]
        enable_verify = bool(indices) and bool(self.candidates)
        self.btn_verify_sel.setEnabled(enable_verify)
        any_match = any(self.candidates[i]["status"] == "MATCH" for i in indices)
        self.btn_delete.setEnabled(any_match)

    def browse_a(self):
        p = QFileDialog.getExistingDirectory(self, "Select Folder A (keep)")
        if p:
            self.entry_a.setText(p)

    def browse_b(self):
        p = QFileDialog.getExistingDirectory(self, "Select Folder B (dedupe target)")
        if p:
            self.entry_b.setText(p)

    def _stage1_stats_cb(self, d: dict):
        if "a_done" in d:
            self.label_a_done.setText(str(d["a_done"]))
        if "a_total" in d:
            self.label_a_total.setText(str(d["a_total"]))
        if "candidates" in d:
            self.label_candidates.setText(str(d["candidates"]))

    def _stage1_progress_cb(self, text, pct):
        self.set_status(text, pct)

    # -------------------- Stage 1 --------------------
    def start_stage1(self):
        fa, fb = self.entry_a.text().strip(), self.entry_b.text().strip()
        if not fa or not fb:
            QMessageBox.critical(self, "Missing folders", "Please choose both Folder A and Folder B.")
            return
        if not os.path.isdir(fa) or not os.path.isdir(fb):
            QMessageBox.critical(self, "Invalid path", "One or both selected paths are not folders.")
            return
        if os.path.abspath(fa) == os.path.abspath(fb):
            QMessageBox.critical(self, "Same folder", "Folder A and Folder B must be different.")
            return

        # Clear table and state
        self.candidates.clear()
        self.search_box.clear()
        self.status_filter.setCurrentIndex(0)
        self.refresh_table()
        self.label_v_done.setText("0")
        self.label_v_total.setText("0")
        self.label_v_matches.setText("0")
        self.progress_bar.setValue(0)
        self.btn_verify_sel.setEnabled(False)
        self.btn_verify_all.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self.set_status("Stage 1: preparing…", 0.0)

        worker = Stage1Worker(fa, fb)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._stage1_progress_cb)
        worker.stats.connect(self._stage1_stats_cb)
        worker.finished.connect(lambda res: self._stage1_finished(res, thread, worker))
        worker.error.connect(lambda msg: self._stage1_error(msg, thread, worker))
        thread.start()
        self.stage1_thread = thread
        self.stage1_worker = worker

    def _stage1_finished(self, results: list[dict], thread: QThread, worker: QObject):
        thread.quit()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()

        self.set_status(f"Stage 1 complete: {len(results)} candidate(s).", 1.0)
        self.candidates = results
        self.refresh_table()
        enable = bool(results)
        self.btn_verify_sel.setEnabled(False)
        self.btn_verify_all.setEnabled(enable)

    def _stage1_error(self, msg: str, thread: QThread, worker: QObject):
        thread.quit()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()
        QMessageBox.critical(self, "Stage 1 failed", msg)

    # -------------------- Stage 2 --------------------
    def _stage2_progress_cb(self, text, pct):
        self.set_status(text, pct)

    def _stage2_counter_cb(self, done, total, matches):
        self.label_v_done.setText(str(done))
        self.label_v_total.setText(str(total))
        self.label_v_matches.setText(str(matches))

    def verify_selected(self):
        rows = sorted({self.displayed_rows[r.row()] for r in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        to_verify = [self.candidates[i] for i in rows]
        self._run_verifier(to_verify, rows)

    def verify_all_pending(self):
        pending_indices = [i for i, r in enumerate(self.candidates) if r.get("status") == "PENDING"]
        if not pending_indices:
            self.set_status("Nothing to verify: no pending rows.", None)
            return
        rows = [self.candidates[i] for i in pending_indices]
        self._run_verifier(rows, None)

    def _run_verifier(self, rows_to_verify: list[dict], update_indices: list[int] | None):
        self.btn_verify_sel.setEnabled(False)
        self.btn_verify_all.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self.set_status(
            f"Stage 2: starting verify (algo={self.algo_combo.currentText()}, workers={self.spin_workers.value()})…",
            0.0,
        )

        worker = Stage2Worker(self.algo_combo.currentText(), self.spin_workers.value(), rows_to_verify)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._stage2_progress_cb)
        worker.counter.connect(self._stage2_counter_cb)
        worker.finished.connect(lambda d, m: self._stage2_finished(d, m, update_indices, thread, worker))
        worker.error.connect(lambda msg: self._stage2_error(msg, thread, worker))
        thread.start()
        self.stage2_thread = thread
        self.stage2_worker = worker

    def _stage2_finished(
        self,
        done: int,
        matches: int,
        update_indices: list[int] | None,
        thread: QThread,
        worker: QObject,
    ):
        thread.quit()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()

        self.refresh_table()

        self.set_status(f"Stage 2 complete: verified {done}, matches {matches}.", 1.0)
        self.btn_verify_all.setEnabled(True)
        HASH_CACHE.save()

    def _stage2_error(self, msg: str, thread: QThread, worker: QObject):
        thread.quit()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()
        QMessageBox.critical(self, "Stage 2 failed", msg)

    # -------------------- Deletion --------------------
    def delete_selected_matches(self):
        rows = sorted({self.displayed_rows[r.row()] for r in self.table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        to_delete = []
        for idx in rows:
            r = self.candidates[idx]
            if r["status"] == "MATCH":
                to_delete.append((idx, r["path_b"]))
        if not to_delete:
            QMessageBox.information(
                self,
                "Nothing to delete",
                "Select verified MATCH rows (green) to delete from Folder B.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Confirm deletion",
            f"Delete {len(to_delete)} file(s) from Folder B?\nThis action is PERMANENT.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        errors = []
        deleted = 0
        total = len(to_delete)
        for i, (idx, path_b) in enumerate(to_delete, start=1):
            try:
                os.remove(to_long_path(path_b))
                deleted += 1
                self.candidates.pop(idx)
            except Exception as e:  # pragma: no cover - filesystem issues
                errors.append((path_b, str(e)))
            self.set_status(f"Deleting {i}/{total}", i / total)
        msg = f"Deleted {deleted} file(s)."
        if errors:
            msg += f" {len(errors)} error(s) occurred."
        self.refresh_table()
        QMessageBox.information(self, "Deletion complete", msg)
        self.set_status("Deletion complete.", 1.0)


def main():  # pragma: no cover - UI entry point
    app = QApplication(sys.argv)
    win = App()
    win.show()
    app.exec()


if __name__ == "__main__":  # pragma: no cover - manual launch
    main()

