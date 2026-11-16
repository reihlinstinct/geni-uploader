"""Evidence-matrix consistency only (#474), not proof of any account fact."""
import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[1]
        / 'docs/father-free-runtime-evidence-matrix.md').read_text()
OFFICIAL = ('https://developers.cloudflare.com/', 'https://www.rfc-editor.org/')


def _rows():
    table = TEXT.split('## Evidence matrix\n', 1)[1].split('\n## ', 1)[0]
    lines = [line for line in table.splitlines() if line.startswith('| ')]
    return [[cell.strip() for cell in line.strip('|').split(' | ')] for line in lines[2:]]


def _flat(section):
    return ' '.join(TEXT.split('## ' + section + '\n', 1)[1].split('\n## ', 1)[0].split())


def test_every_row_has_status_official_source_proof_and_gap():
    rows = _rows()
    assert [int(row[0]) for row in rows] == list(range(1, len(rows) + 1))
    for row in rows:
        assert len(row) == 5, row[0]
        number, fact, source, proof, gap = row
        assert fact and proof and gap, number
        assert re.match(r'(documented|conflict|unknown|conflict / unknown|documented \(index only\)):',
                        source), number
        urls = re.findall(r'\]\((https://[^)]+)\)', source)
        assert urls and all(url.startswith(OFFICIAL) for url in urls), number


def test_checked_date_and_account_boundary_are_stated():
    intro = TEXT.split('## Evidence matrix', 1)[0]
    flat = ' '.join(intro.split())
    assert 'checked 2026-10-29' in flat
    assert 'Product limits are not this account\'s entitlement or usage' in flat
    assert 'Unknown stays unknown; it is never read as supported.' in flat


def test_unknown_and_conflicting_rows_are_not_resolved_optimistically():
    rows = {int(row[0]): row for row in _rows()}
    assert rows[7][2].startswith('conflict / unknown') and '10 ms' in rows[7][4]
    assert rows[12][2].startswith('unknown') and '10 ms' in rows[12][4]
    assert 'blocker' in rows[13][4]
    assert rows[15][2].startswith('conflict')
    assert 'not described as narrow' in rows[19][4]


def test_wall_clock_and_read_only_checks_keep_their_limits():
    wall = _flat('Why local wall clock is not provider CPU')
    assert 'I/O waiting' in wall and 'separately approved benchmark' in wall
    checks = _flat('Minimal next read-only checks (not run)')
    assert 'None is requested here.' in checks
    assert 'no write' in checks
    blockers = _flat('Blockers that stay open')
    assert 'Nothing here creates, changes or approves' in blockers
