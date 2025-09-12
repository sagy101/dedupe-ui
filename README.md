# win-dedupe-ui

Two-stage Windows GUI to find and remove duplicates from **Folder B** that have an identical file in **Folder A**.

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

- Windows 11 **Tkinter** UI (no external UI deps)
- Two-stage flow (name+size → selective hashing)
- Optional **BLAKE3** hasher (much faster than SHA-256 if installed)
- Parallel hashing with adjustable worker count
- Hash cache on disk: `%LOCALAPPDATA%\DedupeUI\hash_cache.json`
- Long path support (`\\?\` prefix)
- Delete **only** from Folder B; Folder A is never touched
- Clear progress text + counters

## Quick start

### Option A — run with Python

1. Install Python 3.11+ (3.12 OK).
2. (Optional) Install **BLAKE3** for speed:
   ```powershell
   python -m pip install -U blake3
   ```
3. Run the app:
   ```powershell
   python .\dedupe_ui_stage2.py
   ```
4. In the app:
   - Pick **Folder A (keep)** and **Folder B (dedupe target)**.
   - Click **Stage 1: Find name+size candidates**.
   - Select rows and click **Stage 2: Verify hash (selected)** (or verify all pending).
   - Only **green (MATCH)** rows are true duplicates; select them and click **Delete Selected from Folder B**.

> If the hasher dropdown only shows `sha256`, it means `blake3` isn’t installed for the Python you’re running.
> Install it in the same interpreter.

### Option B — single-file EXE (no Python needed)

Bundle with PyInstaller:

```powershell
python -m pip install -U pyinstaller
# include blake3 if you want BLAKE3 available inside the EXE
python -m pip install -U blake3

pyinstaller --onefile --noconsole --name WinDedupeUI ^
  --hidden-import blake3 ^
  .\dedupe_ui_stage2.py
# EXE is in .\dist\WinDedupeUI.exe
```

Why `--hidden-import blake3`? The app imports BLAKE3 lazily; this flag ensures PyInstaller bundles it.

### Option C — simple runner (.bat)

Create `run.bat` next to the script:

```bat
@echo off
python "%~dp0\dedupe_ui_stage2.py"
pause
```

Double-click `run.bat` to launch with your system Python.

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

## Roadmap / Nice-to-haves

- “Send to **Recycle Bin**” (instead of permanent delete)
- **Quarantine (Move)** to a review folder
- **CSV export** of results
- **Stop scan** button
- Drag-and-drop folder selection

## Project layout

- `dedupe_ui_stage2.py` — app entry point (UI + logic)
- `README.md` — this file

## License

MIT
