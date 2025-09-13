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
