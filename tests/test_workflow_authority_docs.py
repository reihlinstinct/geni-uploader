"""Pin docs reconciliation, not proof of live settings or permission."""
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path,expected', [
    ('README.md', 'e9de7c92a8f1a7f4a0124ff6d74fa5db8c5d23292199fbdedd1dacecf7389fa6'), ('docs/usage.md', '8aa02ad42babeb0a5397a0aa47b1cc4ebd10e6e24e327734a905db2e883d7197'),
    ('docs/privacy.md', '3167a8dc34bf25bccb0ad55c14a1294003d1772f37fc0373bf6dd3dfaa27419c'), ('PRIVACY.md', '3167a8dc34bf25bccb0ad55c14a1294003d1772f37fc0373bf6dd3dfaa27419c'),
    ('docs/workflow-authority.md', '2617778c855ea988300bd1f07987ba189acb0bc20b1da650d50288d8013127eb')])
def test_workflow_authority_doc_whole_file_pin(path, expected):
    assert hashlib.sha256(' '.join((ROOT/path).read_text().split()).encode()).hexdigest() == expected
