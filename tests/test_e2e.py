import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from stage1 import Stage1Scanner
from verifier import Verifier


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def make_large_file(path, size, first_byte=b"\0"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(first_byte)
        if size > 1:
            f.seek(size - 1)
            f.write(b"\0")


def test_end_to_end(tmp_path):
    a = tmp_path / 'A'
    b = tmp_path / 'B'
    a.mkdir()
    b.mkdir()

    write_file(a / 'duplicate.txt', 'same')
    write_file(b / 'duplicate.txt', 'same')
    write_file(a / 'different.txt', 'abc')
    write_file(b / 'different.txt', 'xyz')
    write_file(b / 'only_b.txt', 'zzz')

    scanner = Stage1Scanner(str(a), str(b))
    rows = scanner.run()
    assert len(rows) == 2

    verifier = Verifier('sha256', workers=2)
    done, matches = verifier.verify_rows(rows)
    assert done == 2
    assert matches == 1
    statuses = {r['name']: r['status'] for r in rows}
    assert statuses['duplicate.txt'] == 'MATCH'
    assert statuses['different.txt'] == 'DIFF'


def test_case_insensitive_matching(tmp_path):
    a = tmp_path / 'A'
    b = tmp_path / 'B'
    a.mkdir()
    b.mkdir()

    # Same content, name differs only by case
    write_file(a / 'FILE.TXT', 'case')
    write_file(b / 'file.txt', 'case')

    scanner = Stage1Scanner(str(a), str(b))
    rows = scanner.run()

    if os.path.normcase('A') == os.path.normcase('a'):
        # Case-insensitive file system (e.g., Windows)
        assert len(rows) == 1
        verifier = Verifier('sha256', workers=1)
        done, matches = verifier.verify_rows(rows)
        assert done == 1
        assert matches == 1
        assert rows[0]['status'] == 'MATCH'
    else:
        # Case-sensitive: names differ, so no candidates found
        assert len(rows) == 0


def test_verifier_reorders_a_paths(tmp_path):
    a = tmp_path / 'A'
    b = tmp_path / 'B'
    (a / 'dir1').mkdir(parents=True)
    (a / 'dir2').mkdir(parents=True)
    b.mkdir()

    # Two A files with same name+size but different content
    write_file(a / 'dir1' / 'x.txt', 'aaa')
    write_file(a / 'dir2' / 'x.txt', 'bbb')
    write_file(b / 'x.txt', 'bbb')  # matches dir2/x.txt

    scanner = Stage1Scanner(str(a), str(b))
    rows = scanner.run()
    assert len(rows) == 1
    assert len(rows[0]['a_paths']) == 2

    verifier = Verifier('sha256', workers=1)
    done, matches = verifier.verify_rows(rows)
    assert done == 1
    assert matches == 1
    row = rows[0]
    assert row['status'] == 'MATCH'
    # Matched path from dir2 should be first
    assert row['a_paths'][0] == str(a / 'dir2' / 'x.txt')
    assert row['hash_a'] == row['hash_b']


def test_missing_files_handled_as_error(tmp_path):
    a = tmp_path / 'A'
    b = tmp_path / 'B'
    a.mkdir()
    b.mkdir()

    # Present in both
    write_file(a / 'present.txt', 'same')
    write_file(b / 'present.txt', 'same')

    # Will delete from A after scanning
    write_file(a / 'missing_in_a.txt', 'same')
    write_file(b / 'missing_in_a.txt', 'same')

    # Will delete from B after scanning
    write_file(a / 'missing_in_b.txt', 'same')
    write_file(b / 'missing_in_b.txt', 'same')

    scanner = Stage1Scanner(str(a), str(b))
    rows = scanner.run()
    assert len(rows) == 3

    # Delete one A file and one B file before verification
    os.remove(a / 'missing_in_a.txt')
    os.remove(b / 'missing_in_b.txt')

    verifier = Verifier('sha256', workers=1)
    done, matches = verifier.verify_rows(rows)
    assert done == 3
    assert matches == 1

    status = {r['name']: r['status'] for r in rows}
    assert status['present.txt'] == 'MATCH'
    assert status['missing_in_a.txt'] == 'ERROR'
    assert status['missing_in_b.txt'] == 'ERROR'

    # Ensure hash_b missing for missing_in_b and hash_a missing for missing_in_a
    for r in rows:
        if r['name'] == 'missing_in_b.txt':
            assert r['hash_b'] is None
        if r['name'] == 'missing_in_a.txt':
            assert r['hash_a'] is None


def test_verify_rows_skip_verified(tmp_path):
    a = tmp_path / 'A'
    b = tmp_path / 'B'
    a.mkdir()
    b.mkdir()

    write_file(a / 'dup.txt', 'same')
    write_file(b / 'dup.txt', 'same')

    scanner = Stage1Scanner(str(a), str(b))
    rows = scanner.run()

    verifier = Verifier('sha256', workers=1)
    done, matches = verifier.verify_rows(rows)
    assert (done, matches) == (1, 1)
    assert rows[0]['status'] == 'MATCH'

    # Second run should skip since status is not PENDING
    done2, matches2 = verifier.verify_rows(rows)
    assert (done2, matches2) == (0, 0)


def test_full_workflow_large_dataset(tmp_path):
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()

    small_same = 300
    small_diff = 300
    b_only = 400
    big_size = 64 * 1024 * 1024  # 64MB to simulate large files

    for i in range(small_same):
        name = f"same_{i}.txt"
        content = f"dup_{i}"
        write_file(a / name, content)
        write_file(b / name, content)

    for i in range(small_diff):
        name = f"diff_{i}.txt"
        write_file(a / name, "A")
        write_file(b / name, "B")

    for i in range(b_only):
        write_file(b / f"only_{i}.txt", "only")

    make_large_file(a / "big_same.bin", big_size, b"Z")
    make_large_file(b / "big_same.bin", big_size, b"Z")
    make_large_file(a / "big_diff.bin", big_size, b"A")
    make_large_file(b / "big_diff.bin", big_size, b"B")

    scanner = Stage1Scanner(str(a), str(b))
    rows = scanner.run()
    assert len(rows) == small_same + small_diff + 2

    subset = [r for r in rows if r["name"].startswith("same_")][:50]
    subset += [r for r in rows if r["name"].startswith("diff_")][:50]

    verifier = Verifier("sha256", workers=2)
    done1, matches1 = verifier.verify_rows(subset)
    assert done1 == len(subset)
    subset_status = {r["status"] for r in subset}
    assert "MATCH" in subset_status and "DIFF" in subset_status

    pending = [r for r in rows if r["status"] == "PENDING"]
    done2, matches2 = verifier.verify_rows(pending)
    assert done2 == len(pending)

    statuses = {r["name"]: r["status"] for r in rows}
    assert statuses["big_same.bin"] == "MATCH"
    assert statuses["big_diff.bin"] == "DIFF"

    match_paths = [r["path_b"] for r in rows if r["status"] == "MATCH"][:5]
    for p in match_paths:
        os.remove(p)
    for p in match_paths:
        assert not os.path.exists(p)


def test_stage1_size_mismatch_not_candidate(tmp_path):
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()

    write_file(a / "same.txt", "abc")
    write_file(b / "same.txt", "abcd")  # different size

    scanner = Stage1Scanner(str(a), str(b))
    rows = scanner.run()
    assert len(rows) == 0


def test_verifier_skips_missing_a_path(tmp_path):
    a = tmp_path / "A"
    b = tmp_path / "B"
    (a / "dir1").mkdir(parents=True)
    (a / "dir2").mkdir(parents=True)
    b.mkdir()

    write_file(a / "dir1" / "x.txt", "same")
    write_file(a / "dir2" / "x.txt", "same")
    write_file(b / "x.txt", "same")

    scanner = Stage1Scanner(str(a), str(b))
    rows = scanner.run()
    assert len(rows) == 1
    assert len(rows[0]["a_paths"]) == 2

    removed = rows[0]["a_paths"][0]
    os.remove(removed)

    verifier = Verifier("sha256", workers=1)
    done, matches = verifier.verify_rows(rows)
    assert (done, matches) == (1, 1)
    row = rows[0]
    assert row["status"] == "MATCH"
    assert row["a_paths"][0] != removed
    assert os.path.exists(row["a_paths"][0])
