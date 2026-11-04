"""Pin docs reconciliation, not proof of live settings or permission."""
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path,expected', [
    ('README.md', '6b7caa86ca314550adb39dbdf8ebc2f4945e9dc8bc100e09959902a09e7368e3'), ('docs/usage.md', '6685074d5ae9118b7c7150060a93bf37d083b966ba5500a64c546c67dba3caad'),
    ('docs/privacy.md', '7778830154e2a00a10a983d2fdc2e87f5255ae1d901b587683096211f028e9eb'), ('PRIVACY.md', '7778830154e2a00a10a983d2fdc2e87f5255ae1d901b587683096211f028e9eb'),
    ('docs/workflow-authority.md', '4e217d8771ca19b67942552108bc6d1ad66575165d37a4e747675c1a907120c8')])
def test_workflow_authority_doc_whole_file_pin(path, expected):
    assert hashlib.sha256(' '.join((ROOT/path).read_text().split()).encode()).hexdigest() == expected
