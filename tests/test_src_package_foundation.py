"""Installed-wheel foundation, not a checkout import-path workaround."""
import json
import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wheel_is_explicit_and_imports_outside_checkout_without_network(tmp_path):
    wheels = tmp_path / "wheels"
    environment = dict(os.environ, PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
         "--wheel-dir", str(wheels), str(ROOT)],
        check=True, env=environment, capture_output=True, text=True,
    )
    wheel, = wheels.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        modules = sorted(name for name in archive.namelist() if not ".dist-info/" in name)
    assert modules == ['geni_offline/__init__.py', 'geni_uploader/__init__.py', 'geni_uploader/cli/__init__.py', 'geni_uploader/cli/parent_output.py', 'geni_uploader/cli/parent_plan.py', 'geni_uploader/core/__init__.py', 'geni_uploader/core/father_once.py', 'geni_uploader/core/intent.py', 'geni_uploader/core/outcome.py', 'geni_uploader/core/parent_contract.py', 'geni_uploader/core/people.py', 'geni_uploader/core/proof_requirements.py', 'geni_uploader/core/proposal_review.py', 'geni_uploader/core/snapshot.py', 'geni_uploader/evidence/__init__.py', 'geni_uploader/evidence/approval.py', 'geni_uploader/evidence/ciphertext.py', 'geni_uploader/evidence/envelope.py', 'geni_uploader/evidence/github_review.py', 'geni_uploader/evidence/parent.py', 'geni_uploader/evidence/profile_result.py', 'geni_uploader/evidence/single_human_approval.py', 'geni_uploader/evidence/workflow_content.py', 'geni_uploader/presentation/__init__.py', 'geni_uploader/presentation/plan_report.py', 'geni_uploader/presentation/visual_plan.py', 'geni_uploader/resources/human-parent-release-gates.json', 'geni_uploader/workflow/__init__.py', 'geni_uploader/workflow/consumption.py', 'geni_uploader/workflow/father_executor.py', 'geni_uploader/workflow/protected_father_job.py', 'geni_uploader/workflow/release_gate.py', 'geni_uploader/workflow/release_package.py', 'geni_uploader/workflow/runner.py', 'geni_uploader/workflow/secondary_probe.py']
    installed = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True).create(installed)
    python = installed / "bin/python"
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)],
        check=True, env=environment, capture_output=True, text=True,
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    # A planted cwd module must not override the installed package with -I.
    (outside / "geni_uploader.py").write_text("raise RuntimeError('ZZ planted cwd')")
    code = '''
import json, sys
blocked = []
def audit(event, args):
    if event.startswith(('socket.', 'urllib.', 'http.client.', 'subprocess.')):
        blocked.append(event)
        raise RuntimeError('ZZ network forbidden')
sys.addaudithook(audit)
import geni_uploader, geni_offline
import geni_uploader.core.people
import geni_uploader.core.proof_requirements, geni_uploader.core.proposal_review
import geni_uploader.core.intent, geni_uploader.core.parent_contract
import geni_uploader.core.snapshot, geni_uploader.core.outcome
import geni_uploader.evidence.envelope, geni_uploader.workflow.consumption
from geni_uploader.workflow import release_gate
import geni_uploader.core.father_once
import geni_uploader.workflow.runner, geni_uploader.workflow.father_executor
import geni_uploader.workflow.protected_father_job, geni_uploader.workflow.release_package
try:
    release_gate.require_production_release()
except geni_uploader.core.people.Blocked as error:
    assert "creation disabled" in str(error)
else:
    raise AssertionError("ZZ gate opened")
resource = release_gate.CONTRACT
resource_path = __import__("pathlib").Path(str(resource))
original = resource_path.read_bytes()
for replacement in [b"{}", None]:
    if replacement is None:
        resource_path.unlink()
    else:
        resource_path.write_bytes(replacement)
    try:
        release_gate.require_production_release()
    except geni_uploader.core.people.Blocked as error:
        assert "unavailable or changed" in str(error)
    else:
        raise AssertionError("ZZ gate opened")
resource_path.write_bytes(original)
import geni_uploader.evidence.approval
import geni_uploader.evidence.ciphertext
import geni_uploader.evidence.github_review
import geni_uploader.evidence.workflow_content
import geni_uploader.evidence.parent
import geni_uploader.evidence.profile_result
import geni_uploader.evidence.single_human_approval
print(json.dumps({'paths':[geni_uploader.__file__,geni_offline.__file__,geni_uploader.core.people.__file__],
                  'blocked':blocked}))
'''
    result = subprocess.run(
        [str(python), "-I", "-c", code], cwd=outside,
        check=True, env=environment, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    assert data["blocked"] == []
    for path in data["paths"]:
        assert Path(path).is_relative_to(installed)
        assert "site-packages" in path
        assert not Path(path).is_relative_to(ROOT)
