"""Pin actual runtime coverage for the major Python base update (#598)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_matrix_and_container_job_are_required_by_summary():
    s = (ROOT / '.github/workflows/ci.yml').read_text()
    assert 'python-version: ["3.11", "3.12", "3.13", "3.15"]' in s
    assert 'needs: [changes, test, coverage, container-smoke]' in s
    assert 'docker build --pull -t zz-uploader-smoke .' in s
    assert 'bash scripts/ci/container_smoke.sh zz-uploader-smoke' in s


def test_smoke_is_offline_uncredentialed_and_checks_all_runtime_bytes():
    s = (ROOT / 'scripts/ci/container_smoke.sh').read_text()
    for token in ['--network none', 'sha256sum', 'diff -u', 'cli_spec.py',
                  'geni_upload.py', 'source_details.py', 'plan_report.py',
                  'visual_plan.py', 'entrypoint.sh', 'sys.version_info[:2] == (3, 15)',
                  'error: set GENI_UPLOAD_REPO', '[ "$status" -eq 1 ]']:
        assert token in s
    assert 'docker login' not in s and 'docker push' not in s
