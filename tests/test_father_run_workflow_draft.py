"""Closed review scaffold only, never an installed workflow."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_draft_remains_outside_active_workflow_and_closed():
    path = ROOT / 'docs/father-run-workflow-draft.yml'
    doc = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert not (ROOT / '.github/workflows' / path.name).exists()
    assert list(doc['on']) == ['workflow_dispatch']
    assert doc['permissions'] == {}
    assert doc['concurrency']['cancel-in-progress'] == 'false'
    assert list(doc['jobs']) == ['protected-father']
    job = doc['jobs']['protected-father']
    assert job['if'] == "github.ref == 'refs/heads/master' && github.run_attempt == 1"
    assert job['environment'] == 'father-create'
    assert job['permissions'] == {'contents': 'read', 'id-token': 'write'}
    assert job['name'] == ('Approve plan ${{ inputs.plan_fingerprint }} risk '
                           '${{ inputs.risk_hash }} run ${{ github.run_id }} attempt 1')
    assert len(job['steps']) == 1
    assert job['steps'][0]['shell'] == 'bash'
    assert job['steps'][0]['run'].splitlines()[-1] == 'exit 1'
    assert 'secrets.' not in path.read_text()
