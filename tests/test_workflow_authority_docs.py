"""Pin docs reconciliation, not proof of live settings or permission."""
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path,expected', [
    ('README.md', '41ba01f3bb4e7a856d984bc86bb11f9ceed802fa52ed3e124e3224d6a3ae21f0'), ('docs/usage.md', '24869d6255babdd444baa7cfe097c063c14248feeef3cc4546c82edd7ad3c90d'),
    ('docs/privacy.md', '7e43f24316a9927213d6a43fa88b4613b838de4742f7fab81b99f390c160b65a'), ('PRIVACY.md', '7e43f24316a9927213d6a43fa88b4613b838de4742f7fab81b99f390c160b65a'),
    ('docs/workflow-authority.md', '94840e83d1c1b95cd8044a9b631311ad5f9bdc24bc6007acd74f2a17b20c545a')])
def test_workflow_authority_doc_whole_file_pin(path, expected):
    assert hashlib.sha256(' '.join((ROOT/path).read_text().split()).encode()).hexdigest() == expected
