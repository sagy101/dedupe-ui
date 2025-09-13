# DedupeUI

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-blue" /></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green" /></a>
</p>

Two-stage cross-platform GUI (Windows, macOS, Linux) to find and remove duplicates from **Folder B** that have an identical file in **Folder A**.

**Identity rule:** same **filename** (case-insensitive) **and** same **content hash**.  
**Deletion safety:** only files in **Folder B** can be deleted—and only after an **explicit hash match** (green).

## Why two stages?

- **Stage 1 – Fast filter:** find candidates by **name + size** (no hashing).
- **Stage 2 – On-demand verify:** hash only the rows you select.
  - **MATCH** → row turns green (identical content).
  - **DIFF** → row turns red (different content).
  - Unchecked rows remain neutral.
  - Already-verified rows are automatically skipped on re-runs.

This avoids hashing everything, keeps the UI responsive, and lets you control what to verify.

## Features

- **Qt (PySide6)** UI
- Two-stage flow (name+size → selective hashing)
- Optional **BLAKE3** hasher (much faster than SHA-256 if installed)
- Parallel hashing with adjustable worker count
- Hash cache on disk using the OS-specific cache directory
- Long path support (`\\?\` prefix)
- Delete **only** from Folder B; Folder A is never touched
- Clear progress text + counters

## Quick start

DedupeUI can be used in two ways.

### 1. Run from source

1. Install Python 3.11+.
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
   (Optional) Install **BLAKE3** for faster hashing:
   ```bash
   python -m pip install blake3
   ```
3. Launch:
   ```bash
   python ./dedupe_ui.py
   ```
4. In the app:
   - Pick **Folder A (keep)** and **Folder B (dedupe target)**.
   - Click **Stage 1: Find name+size candidates**.
   - Select rows and click **Stage 2: Verify hash (selected)**.
   - Only **green (MATCH)** rows are true duplicates; select them and click **Delete Selected from Folder B**.

### 2. Run a release file

Download a pre-built executable from the [releases page](../../releases/latest) and run it. No Python installation is required.

## Build a release (optional)

Bundle your own single-file executable with PyInstaller:

```powershell
python -m pip install -U pyinstaller
python -m pip install -U blake3  # optional, for BLAKE3 support

pyinstaller --onefile --noconsole --name DedupeUI ^
  --hidden-import blake3 ^
  .\dedupe_ui.py
# Executable is in .\dist\DedupeUI.exe
```

Why `--hidden-import blake3`? The app imports BLAKE3 lazily; this flag ensures PyInstaller bundles it.

## Safety notes

- **Back up Folder B** before deleting.
- Only **Path B** is ever deleted; logic never touches Folder A.
- The **Delete** button works only on **green (MATCH)** rows that you select.
- Long or locked paths: the app uses the Windows `\\?\` long-path prefix and reports permission/lock errors without stopping the whole run.

## Performance tips

- Use **BLAKE3** if available (set in the dropdown).
- Tweak **Workers**:
  - USB/SD: 4–8
  - SSD/NVMe: 8–16
- Stage 1 is fast; in Stage 2, verify only the rows you care about.
- The hash cache accelerates repeats if files haven’t changed.

## Troubleshooting

- **blake3 not in dropdown:** install for the same Python:
  ```powershell
  python -m pip install blake3
  ```
- **Getting stuck mid-scan:** this two-stage flow avoids whole-tree hashing—use Stage 2 to hash selected rows only.
- **Anti-virus slowdowns:** exclude the target folders temporarily while scanning (remember to re-enable).
- **Permissions:** run PowerShell as admin if needed for protected paths.

## Project layout

- `dedupe_ui_backup.py` — original single-file version
- `dedupe_ui.py` — app entry point
- `utils.py`, `hashing.py`, `stage1.py`, `verifier.py`, `gui.py` — split modules by responsibility
- `README.md` — this file

## License

MIT
