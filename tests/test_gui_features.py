import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

# Ensure a single QApplication instance
app = QApplication.instance() or QApplication([])

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from gui import App


def test_search_and_filter():
    win = App()
    win.candidates = [
        {
            "status": "MATCH",
            "name": "same.txt",
            "size": 1,
            "a_paths": ["a"],
            "path_b": "b",
            "hash_algo": "sha256",
            "hash_a": "",
            "hash_b": "h1",
        },
        {
            "status": "DIFF",
            "name": "different.txt",
            "size": 1,
            "a_paths": ["a"],
            "path_b": "b2",
            "hash_algo": "sha256",
            "hash_a": "",
            "hash_b": "h2",
        },
    ]
    win.refresh_table()
    assert win.table.rowCount() == 2
    win.status_filter.setCurrentText("MATCH")
    assert win.table.rowCount() == 1
    assert win.table.item(0, 1).text() == "same.txt"
    win.status_filter.setCurrentText("All")
    win.search_box.setText("diff")
    assert win.table.rowCount() == 1
    assert win.table.item(0, 1).text() == "different.txt"


def test_deletion_progress(tmp_path, monkeypatch):
    win = App()
    p = tmp_path / "file.txt"
    p.write_text("x")
    win.candidates = [
        {
            "status": "MATCH",
            "name": "file.txt",
            "size": 1,
            "a_paths": ["a"],
            "path_b": str(p),
            "hash_algo": "sha256",
            "hash_a": "",
            "hash_b": "h",
        }
    ]
    win.refresh_table()
    win.table.selectRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    win.delete_selected_matches()
    assert not p.exists()
    assert win.progress_bar.value() == 100
    assert "Deletion complete" in win.status_label.text()
