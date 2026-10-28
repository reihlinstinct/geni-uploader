"""The CI coverage report counts production files only and gates per file (#98)."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "coverage_report", ROOT / ".github/coverage_report.py"
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def data(**files):
    return {
        "files": {
            name: {"summary": {"covered_lines": c, "num_statements": n}}
            for name, (c, n) in files.items()
        }
    }


def run(tmp_path, payload, *flags):
    p = tmp_path / "coverage.json"
    p.write_text(json.dumps(payload))
    return report.main([str(p), "--floor", "80", *flags])


def test_per_file_floor_fails_even_when_combined_total_passes(tmp_path, capsys):
    # combined 870/1000 = 87%, but source_details alone is 70%.
    payload = data(**{"geni_upload.py": (800, 900), "source_details.py": (70, 100)})
    assert run(tmp_path, payload) == 0  # measure-only
    assert run(tmp_path, payload, "--fail-under") == 1
    out = capsys.readouterr().out
    assert "Below floor: source_details.py" in out
    assert "| **combined** | 870 | 1000 | 87.00% |" in out


def test_all_files_at_floor_pass(tmp_path, capsys):
    payload = data(**{"geni_upload.py": (80, 100), "source_details.py": (90, 100)})
    assert run(tmp_path, payload, "--fail-under") == 0
    out = capsys.readouterr().out
    assert "tests are excluded" in out and "entrypoint.sh" in out


@pytest.mark.parametrize(
    "files",
    [
        {"geni_upload.py": (1, 1)},
        {"geni_upload.py": (1, 1), "source_details.py": (1, 1), "tests/test_x.py": (1, 1)},
    ],
)
def test_denominator_must_be_exactly_production(tmp_path, files):
    with pytest.raises(SystemExit):
        run(tmp_path, data(**files))


def test_ci_measures_production_only_and_gates_behind_variable():
    job = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["coverage"]
    steps = {step.get("name"): step for step in job["steps"]}
    measure = steps["Measure production coverage"]["run"]
    assert "--include=geni_upload.py,source_details.py" in measure
    gate = [s for s in job["steps"] if "--fail-under" in s.get("run", "")]
    assert len(gate) == 1 and gate[0]["if"] == "vars.COVERAGE_GATE == 'on'"
    assert "--fail-under" not in steps["Coverage summary"]["run"]
    assert float((ROOT / ".github/coverage-floor.txt").read_text()) >= 80
    assert set(report.PRODUCTION) == {"geni_upload.py", "source_details.py"}
