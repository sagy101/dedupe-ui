import os
import shutil
from send2trash import send2trash
from utils import to_long_path


def send_to_recycle_bin(path: str) -> None:
    """Move file at path to the OS recycle bin."""
    send2trash(to_long_path(path))


def quarantine_file(path: str, dest_dir: str) -> str:
    """Move file to a quarantine directory, avoiding name collisions.

    Returns the destination path.
    """
    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(path)
    base, ext = os.path.splitext(name)
    dest = os.path.join(dest_dir, name)
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(dest_dir, f"{base}_{counter}{ext}")
        counter += 1
    shutil.move(to_long_path(path), to_long_path(dest))
    return dest
