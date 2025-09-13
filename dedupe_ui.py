#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Two-stage de-dupe UI for Windows:
1) Stage 1 (fast): list candidates that share the SAME FILENAME (case-insensitive) AND SAME SIZE across Folder A and Folder B.
2) Stage 2 (on demand): verify content equality by hashing ONLY the selected rows. Matching rows turn green; non-matching turn red.

Only files in Folder B can be deleted, and only when they are verified matches (green).
Optional BLAKE3 (if installed) for faster hashing; otherwise uses SHA-256.

Fixes included:
- BLAKE3 detection via importlib.util.find_spec (no deprecation warnings)
- Raw-string docstrings to silence unicode-escape warnings
"""

from gui import main
import os

if __name__ == "__main__":
    if os.name == "nt":
        try:
            import ctypes  # DPI awareness for sharper UI on Windows
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    main()
