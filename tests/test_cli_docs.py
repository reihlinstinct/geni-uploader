"""--help smoke tests, spec/help/man drift tests, and packaging tests (#515).

cli_spec.py is the single source of truth: geni_upload.py and source_details.py
build their --help text from it, and tools/build_man_pages.py renders the
committed man pages from it. These tests prove all three stay in sync.
"""

import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_man_pages as bmp

import cli_spec

UPLOAD = "geni_upload.py"
DETAILS = "source_details.py"
MAN_DIR = ROOT / "man" / "man1"


def help_output(script, *argv):
    """Run a shipped entrypoint's --help exactly as a user would."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / script), *argv, "--help"],
        capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout
    return proc.stdout


def norm(text):
    """Whitespace-normalized: argparse wraps help text at the terminal width,
    splitting long words after their hyphens ("geni-upload-\\nstate.json")."""
    return " ".join(text.split()).replace("- ", "-")


def flags_in(help_text):
    return set(re.findall(r"--[a-z][a-z-]+", help_text)) - {"--help"}


# -- --help smoke test for every real entrypoint -----------------------------

HELP_CASES = (
    [(UPLOAD,)]  # top level
    + [(UPLOAD, name) for name in cli_spec.UPLOAD_COMMANDS]
    + [(DETAILS,)]
    + [(DETAILS, mode) for mode in cli_spec.DETAILS_COMMANDS]
)


@pytest.mark.parametrize("argv", HELP_CASES, ids=["-".join(c) for c in HELP_CASES])
def test_help_smoke_every_shipped_entrypoint(argv):
    out = help_output(*argv)
    assert len(out.strip()) > len("usage:")


# -- drift: --help output vs cli_spec ----------------------------------------

def test_top_level_help_lists_every_upload_command():
    out = norm(help_output(UPLOAD))
    for cmd in cli_spec.UPLOAD_COMMANDS.values():
        assert cmd.name in out
        assert norm(cmd.summary) in out
    assert norm(cli_spec.TOKEN_FILE.help) in out


@pytest.mark.parametrize("name", sorted(cli_spec.UPLOAD_COMMANDS))
def test_upload_command_help_matches_spec(name):
    cmd = cli_spec.UPLOAD_COMMANDS[name]
    out = help_output(UPLOAD, name)
    flat = norm(out)
    assert norm(cmd.summary) in flat
    assert flags_in(out) == {opt.flag for opt in cmd.options}
    for opt in cmd.options:
        assert norm(opt.help) in flat


def test_details_help_matches_spec():
    out = help_output(DETAILS)
    flat = norm(out)
    assert flags_in(out) == {opt.flag for opt in cli_spec.DETAILS_OPTIONS}
    for opt in cli_spec.DETAILS_OPTIONS:
        assert norm(opt.help) in flat
    assert norm(cli_spec.DETAILS_MODE_HELP) in flat
    for mode in cli_spec.DETAILS_COMMANDS:
        assert mode in flat


def test_spec_help_texts_embed_no_other_flags():
    # A help text naming another --flag would corrupt the flag-set comparison.
    for cmd in cli_spec.UPLOAD_COMMANDS.values():
        for opt in cmd.options:
            assert "--" not in opt.help
    for opt in cli_spec.DETAILS_OPTIONS:
        assert "--" not in opt.help


def usage_block(script, *argv):
    out = help_output(script, *argv)
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("usage:"))
    block = [lines[start]]
    for line in lines[start + 1:]:
        if not line.startswith(" "):
            break
        block.append(line)
    return norm(" ".join(block))


def _bracketed(usage, flag, metavar):
    needle = f"{flag} {metavar}" if metavar else flag
    return f"[{needle}]" in usage


def _unbracketed(usage, flag, metavar):
    needle = f"{flag} {metavar}" if metavar else flag
    return needle in usage and f"[{needle}]" not in usage


@pytest.mark.parametrize("name", sorted(cli_spec.UPLOAD_COMMANDS))
def test_required_options_match_live_parser(name):
    """Spec-required == parser-required, plus documented runtime requirements."""
    cmd = cli_spec.UPLOAD_COMMANDS[name]
    usage = usage_block(UPLOAD, name)
    for opt in cmd.options:
        if opt.flag == "--confirm" and name == "run":
            # runtime-required: the parser accepts the omission, run refuses it
            assert opt.required
            assert _bracketed(usage, opt.flag, opt.metavar)
            assert "refuses" in opt.help
        elif opt.required:
            assert _unbracketed(usage, opt.flag, opt.metavar), (name, opt.flag)
        else:
            assert _bracketed(usage, opt.flag, opt.metavar), (name, opt.flag)


def test_details_required_options_match_live_parser():
    usage = usage_block(DETAILS)
    assert _unbracketed(usage, "--manifest", "MANIFEST")
    for opt in cli_spec.DETAILS_OPTIONS:
        if opt.flag != "--manifest":
            assert _bracketed(usage, opt.flag, opt.metavar)
    # per-mode runtime requirements only name real options
    known = {opt.flag for opt in cli_spec.DETAILS_OPTIONS}
    for mode, flags in cli_spec.DETAILS_REQUIRED.items():
        assert mode in cli_spec.DETAILS_COMMANDS
        assert set(flags) <= known
        assert "--manifest" in flags


def test_exit_status_scoped_to_commands_that_return_them():
    pages = bmp.render_all()
    for code in ("3", "4", "5", "6"):
        assert f".B {code}\n" in pages["geni-uploader-run.1"] or \
            f".B {code}" in pages["geni-uploader-run.1"]
        assert f".B {code}" in pages["geni-uploader.1"]
        for other in ("plan", "whoami", "contrast", "guidmap", "pguid",
                      "auth-url", "listing-shape"):
            assert f".B {code}\n" not in pages[f"geni-uploader-{other}.1"]
        for mode in cli_spec.DETAILS_COMMANDS:
            assert f".B {code}\n" not in pages[f"geni-uploader-details-{mode}.1"]
    assert "run command only" in pages["geni-uploader.1"]


# -- drift: committed man pages vs the generator ------------------------------

def test_committed_man_pages_match_generator():
    problems = bmp.check_pages(bmp.render_all(), MAN_DIR)
    assert problems == []


def test_generator_covers_every_shipped_command():
    pages = bmp.render_all()
    expected = {"geni-uploader.1"}
    expected |= {f"geni-uploader-{name}.1" for name in cli_spec.UPLOAD_COMMANDS}
    expected |= {f"geni-uploader-details-{mode}.1" for mode in cli_spec.DETAILS_COMMANDS}
    assert set(pages) == expected


# -- man page structure --------------------------------------------------------

def test_man_pages_have_required_sections():
    for name, text in bmp.render_all().items():
        assert text.startswith(bmp.HEADER_COMMENT), name
        assert f'.TH "{name[:-2].upper().replace("-", chr(92) + "-")}"' in text, name
        for section in ("NAME", "SYNOPSIS", "DESCRIPTION", "EXIT STATUS", "SEE ALSO"):
            assert f".SH {section}" in text, f"{name} missing {section}"
        if name == "geni-uploader.1":
            for section in ("COMMANDS", "ENVIRONMENT", "FILES"):
                assert f".SH {section}" in text, f"{name} missing {section}"
        else:
            assert ".SH OPTIONS" in text, f"{name} missing OPTIONS"
        assert ".SH NAME\ngeni" in text, name


def test_man_pages_name_lines_carry_summaries():
    pages = bmp.render_all()
    for cmd in cli_spec.UPLOAD_COMMANDS.values():
        page = pages[f"geni-uploader-{cmd.name}.1"]
        assert f"\\- {bmp.esc(cmd.summary)}" in page
    for mode, cmd in cli_spec.DETAILS_COMMANDS.items():
        page = pages[f"geni-uploader-details-{mode}.1"]
        assert f"\\- {bmp.esc(cmd.summary)}" in page


# -- spec integrity ------------------------------------------------------------

def test_spec_version_matches_pyproject():
    match = re.search(r'^version = "([^"]+)"',
                      (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
                      re.MULTILINE)
    assert match, "pyproject version not found"
    assert cli_spec.VERSION == match.group(1)


def test_spec_covers_entrypoint_dispatch():
    """The container entrypoint's details-* arms must match the spec exactly."""
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
    match = re.search(r"(details-[a-z|-]+)\)", entrypoint)
    assert match, "entrypoint details dispatch not found"
    dispatched = {arm.split("-", 1)[1] for arm in match.group(1).split("|")}
    assert dispatched == set(cli_spec.DETAILS_COMMANDS)


def test_dockerfile_ships_every_parser_dependency():
    """geni_upload.py imports cli_spec; the image must carry both."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for shipped in ("geni_upload.py", "source_details.py", "cli_spec.py"):
        assert f"COPY {shipped} /opt/{shipped}" in dockerfile


# -- packaging ------------------------------------------------------------------

def test_check_mode_accepts_fresh_and_refuses_stale(tmp_path):
    assert bmp.main(["--dir", str(tmp_path)]) == 0  # writes
    assert bmp.main(["--check", "--dir", str(tmp_path)]) == 0
    stale = tmp_path / "geni-uploader.1"
    stale.write_text(stale.read_text(encoding="utf-8") + "stale\n", encoding="utf-8")
    assert bmp.main(["--check", "--dir", str(tmp_path)]) == 1
    (tmp_path / "geni-uploader-ghost.1").write_text(".TH GHOST 1\n", encoding="utf-8")
    assert bmp.main(["--check", "--dir", str(tmp_path)]) == 1


def test_write_pages_removes_only_marked_stale_pages(tmp_path):
    bmp.write_pages(bmp.render_all(), tmp_path)
    stale_generated = tmp_path / "geni-uploader-ghost.1"
    stale_generated.write_text(bmp.HEADER_COMMENT + "\n.TH GHOST 1\n", encoding="utf-8")
    foreign_ours = tmp_path / "geni-uploader-notes.1"  # our namespace, not ours
    foreign_ours.write_text(".TH NOTES 1\n", encoding="utf-8")
    unrelated = tmp_path / "ls.1"
    unrelated.write_text(".TH LS 1\n", encoding="utf-8")
    notes = bmp.write_pages(bmp.render_all(), tmp_path)
    assert not stale_generated.exists()
    assert any("ghost" in note for note in notes)
    assert foreign_ours.exists() and unrelated.exists()
    # check ignores pages outside our namespace entirely
    problems = bmp.check_pages(bmp.render_all(), tmp_path)
    assert not any("ls.1" in problem for problem in problems)


def test_tarball_is_deterministic_and_complete(tmp_path):
    first = bmp.main(["--dir", str(tmp_path / "m"), "--tarball", str(tmp_path / "a.tar.gz")])
    second = bmp.main(["--dir", str(tmp_path / "m"), "--tarball", str(tmp_path / "b.tar.gz")])
    assert first == 0 and second == 0
    assert (tmp_path / "a.tar.gz").read_bytes() == (tmp_path / "b.tar.gz").read_bytes()
    with tarfile.open(tmp_path / "a.tar.gz") as tar:
        names = tar.getnames()
    base = f"{cli_spec.PROGRAM}-{cli_spec.VERSION}/man/man1"
    assert sorted(names) == sorted(f"{base}/{name}" for name in bmp.render_all())


def test_install_script_installs_every_page(tmp_path):
    proc = subprocess.run(
        ["sh", str(ROOT / "tools" / "install_man_pages.sh")],
        capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin", "PREFIX": str(tmp_path)})
    assert proc.returncode == 0, proc.stderr
    installed = sorted(p.name for p in (tmp_path / "share" / "man" / "man1").glob("*.1"))
    assert installed == sorted(bmp.render_all())
