"""Behavioral workflow -> entrypoint -> CLI parser matrix for every dispatch mode (#99).

For each `mode` option of .github/workflows/geni-upload.yml this runs, offline:
1. the workflow's real argument-selection shell (extracted verbatim),
2. the entrypoint's real routing `case` block (extracted verbatim, with a
   recording `python` stub on PATH), and
3. the real argparse parser of the routed script, with every command
   function / loader replaced by a recorder so nothing past parsing runs.

Invalid modes, misplaced top-level options and missing required flags must be
rejected by the parser (exit 2) before any command function runs. No
credentials, no network, no workflow dispatch.
"""
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import geni_upload as g
import source_details as s

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/geni-upload.yml").read_text()
ENTRYPOINT = (ROOT / "entrypoint.sh").read_text()
pytestmark = pytest.mark.skipif(not (shutil.which("bash") and shutil.which("sh")),
                                reason="needs bash and sh")

# mode -> (routed script, parsed command, expects --confirm, expects --manifest)
MATRIX = {
    "plan": ("/opt/geni_upload.py", "plan", False, True),
    "run": ("/opt/geni_upload.py", "run", True, True),
    "details-plan": ("/opt/source_details.py", "plan", False, True),
    "details-repair": ("/opt/source_details.py", "repair", True, True),
    "selftest": ("/opt/geni_upload.py", "plan", False, True),
    "whoami": ("/opt/geni_upload.py", "whoami", False, False),
    "contrast": ("/opt/geni_upload.py", "contrast", False, True),
    "guidmap": ("/opt/geni_upload.py", "guidmap", False, True),
    "pguid": ("/opt/geni_upload.py", "pguid", False, True),
    "listing-shape": ("/opt/geni_upload.py", "listing-shape", False, True),
}
GENI_COMMANDS = {"plan": "cmd_plan", "run": "cmd_run", "whoami": "cmd_whoami",
                 "contrast": "cmd_contrast", "guidmap": "cmd_guidmap",
                 "pguid": "cmd_pguid", "listing-shape": "cmd_listing_shape"}


def workflow_modes():
    on = yaml.load(WORKFLOW, Loader=yaml.BaseLoader)["on"]
    return on["workflow_dispatch"]["inputs"]["mode"]["options"]


def workflow_args(mode, tmp_path):
    start = WORKFLOW.index('            if [ "$MODE" = "selftest" ]; then\n              # Inert:')
    end = WORKFLOW.index('            if [[ "$MODE" == details-* ]]', start)
    shell = textwrap.dedent(WORKFLOW[start:end]) + '\nprintf "%s\\n" "${ARGS[@]}"\n'
    env = {**os.environ, "MODE": mode, "CONFIRM": "YES",
           "MANIFEST_PATH": "ZZ-manifest.yaml", "RUNNER_TEMP": str(tmp_path)}
    result = subprocess.run(["bash", "-c", shell], env=env, check=True,
                            capture_output=True, text=True)
    return result.stdout.splitlines()


def entrypoint_route(args, tmp_path):
    start = ENTRYPOINT.index('case "${1:-}" in')
    end = ENTRYPOINT.index("esac", start) + len("esac")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "python"
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    stub.chmod(0o755)
    shell = "set -eu\n" + ENTRYPOINT[start:end] + "\n"
    result = subprocess.run(["sh", "-c", shell, "entrypoint", *args],
                            env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
                            check=True, capture_output=True, text=True)
    routed = result.stdout.splitlines()
    return routed[0], routed[1:]


class Ran(Exception):
    pass


def parse_geni(argv):
    """Run geni_upload.main's real parser; return (command, namespace)."""
    seen = {}

    def recorder(name):
        def fn(args):
            seen["cmd"], seen["args"] = name, args
            raise Ran
        return fn

    patches = [patch.object(g, attr, recorder(cmd)) for cmd, attr in GENI_COMMANDS.items()]
    with patch.object(sys, "argv", ["geni_upload.py", *argv]):
        for p in patches:
            p.start()
        try:
            with pytest.raises(Ran):
                g.main()
        finally:
            for p in patches:
                p.stop()
    return seen["cmd"], seen["args"]


def parse_details(argv):
    """Run source_details.main's real parser; stop at the first post-parse step."""
    seen = {}

    def load(path):
        seen["manifest"] = path
        raise Ran

    with patch.object(sys, "argv", ["source_details.py", *argv]), \
            patch.object(s, "load_records", load), \
            patch.object(s.api, "get_token", side_effect=AssertionError("network")), \
            pytest.raises(Ran):
        s.main()
    return seen["manifest"]


def test_matrix_covers_every_workflow_mode():
    assert sorted(workflow_modes()) == sorted(MATRIX)


@pytest.mark.parametrize("mode", sorted(MATRIX))
def test_mode_reaches_the_right_parser_command(mode, tmp_path):
    script, command, wants_confirm, wants_manifest = MATRIX[mode]
    args = workflow_args(mode, tmp_path)
    routed_script, routed_args = entrypoint_route(args, tmp_path)
    assert routed_script == script
    if script.endswith("source_details.py"):
        assert routed_args[0] == command
        assert parse_details(routed_args) == "ZZ-manifest.yaml"
        return
    cmd, ns = parse_geni(routed_args)
    assert cmd == command
    assert ns.token_file == "/run/geni-token"
    if wants_manifest:
        expected = ("/work/selftest/manifest.yaml" if mode == "selftest"
                    else "ZZ-manifest.yaml")
        assert ns.manifest == expected
    else:
        assert not hasattr(ns, "manifest")
    assert (getattr(ns, "confirm", None) == "YES") == wants_confirm


@pytest.mark.parametrize("argv", [
    ["--token-file", "t", "upload", "--manifest", "m"],         # unknown mode
    ["--token-file", "t", "details-plan", "--manifest", "m"],   # details-* is entrypoint-only
    ["plan", "--token-file", "t", "--manifest", "m"],           # top-level option after mode
    ["--token-file", "t", "plan"],                              # missing --manifest
    ["--token-file", "t", "run", "--manifest", "m", "--sync-state"],  # details-only flag
    ["--token-file", "t", "whoami", "--manifest", "m"],         # whoami takes no manifest
])
def test_geni_parser_rejects_before_any_command(argv, capsys):
    called = []
    patches = [patch.object(g, attr, lambda *_a, **_k: called.append(1))
               for attr in GENI_COMMANDS.values()]
    with patch.object(sys, "argv", ["geni_upload.py", *argv]):
        for p in patches:
            p.start()
        try:
            with pytest.raises(SystemExit) as exc:
                g.main()
        finally:
            for p in patches:
                p.stop()
    assert exc.value.code == 2
    assert called == []
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["upload", "--manifest", "m"],                  # unknown mode
    ["details-plan", "--manifest", "m"],            # the entrypoint strips "details-"
    ["plan"],                                       # missing --manifest
    ["plan", "--manifest", "m", "--smoke"],         # geni_upload-only flag
])
def test_details_parser_rejects_before_loading(argv, capsys):
    with patch.object(sys, "argv", ["source_details.py", *argv]), \
            patch.object(s, "load_records", side_effect=AssertionError("loaded")), \
            pytest.raises(SystemExit) as exc:
        s.main()
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_unknown_details_mode_is_routed_to_details_cli_only_if_listed(tmp_path):
    # "details-validate"/"details-snapshot" route in the entrypoint but are not
    # workflow options; anything else with a details- prefix goes to
    # geni_upload.py, whose parser rejects it.
    script, _ = entrypoint_route(["details-bogus", "--manifest", "m"], tmp_path)
    assert script == "/opt/geni_upload.py"
    for mode in ("details-validate", "details-snapshot"):
        script, args = entrypoint_route([mode, "--manifest", "m"], tmp_path)
        assert script == "/opt/source_details.py" and args[0] == mode.split("-", 1)[1]
