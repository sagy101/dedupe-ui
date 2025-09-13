import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QMimeData, Qt, QPointF, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest

# Ensure a single QApplication instance
app = QApplication.instance() or QApplication([])

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from gui import App
import file_ops


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

    called = {}

    def fake_send(path):
        called["path"] = path
        os.remove(path)

    monkeypatch.setattr(file_ops, "send_to_recycle_bin", fake_send)
    win.delete_selected_matches()
    assert called["path"] == str(p)
    assert not p.exists()
    assert win.progress_bar.value() == 100
    assert "Deletion complete" in win.status_label.text()


def test_quarantine_progress(tmp_path, monkeypatch):
    win = App()
    p = tmp_path / "file.txt"
    p.write_text("x")
    qdir = tmp_path / "Q"
    qdir.mkdir()
    win.entry_q.setText(str(qdir))
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
    win.quarantine_selected_matches()
    dest = qdir / "file.txt"
    assert dest.exists() and not p.exists()
    assert win.progress_bar.value() == 100
    assert "Quarantine complete" in win.status_label.text()


def test_drag_and_drop_folder_selection(tmp_path):
    win = App()
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(a))])
    event = QDropEvent(QPointF(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    win.entry_a.dragEnterEvent(event)
    win.entry_a.dropEvent(event)
    assert win.entry_a.text() == str(a)

    mime2 = QMimeData()
    mime2.setUrls([QUrl.fromLocalFile(str(b))])
    event2 = QDropEvent(QPointF(), Qt.CopyAction, mime2, Qt.LeftButton, Qt.NoModifier)
    win.entry_b.dragEnterEvent(event2)
    win.entry_b.dropEvent(event2)
    assert win.entry_b.text() == str(b)


def test_pause_and_log_panel(tmp_path, monkeypatch):
    import stage1
    orig_iter = stage1.iter_files

    def slow_iter(path):
        for p in orig_iter(path):
            import time
            time.sleep(0.01)
            yield p

    monkeypatch.setattr(stage1, "iter_files", slow_iter)

    win = App()
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()
    for i in range(5):
        (a / f"f{i}.txt").write_text("x")
        (b / f"f{i}.txt").write_text("x")

    win.entry_a.setText(str(a))
    win.entry_b.setText(str(b))
    win.log_box.setChecked(True)
    win.start_stage1()
    win.toggle_pause()
    QTest.qWait(50)
    assert win.btn_pause.text() == "Resume"
    assert win.log_view.toPlainText() == ""
    win.toggle_pause()
    for _ in range(20):
        if win.log_view.toPlainText():
            break
        QTest.qWait(50)
    assert win.log_view.toPlainText() != ""
    win.stop_current()
    win.stage1_thread.wait()
    win.log_box.setChecked(False)
    assert not win.log_view.isVisible()
