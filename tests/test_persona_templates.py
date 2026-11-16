"""Persona-rendered documents render deterministically and fail on drift (#733).

Pins tools/render_persona_docs.py against docs/persona-template-design.md:
canonical substitution in prose and code fences, escaped braces, one-pass
replacement, unknown/malformed token rejection, strict manifest paths
(traversal, symlinks, duplicates, overlap), Unicode/newline normalization,
byte determinism, drift detection (direct edits, stale persona values), a
check mode that never writes, and a write flag refused in CI. Fixture trees
are built under tmp_path from synthetic/personas.json only.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools" / "render_persona_docs.py"
PERSONAS = json.loads((ROOT / "synthetic" / "personas.json").read_text(encoding="utf-8"))
SOURCE = "docs/templates/sample.md.in"
OUTPUT = "docs/sample.md"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_persona_docs", RENDERER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load_renderer()


def persona(key):
    return next(p for p in PERSONAS["personas"] if p["key"] == key)


P = persona("primary")
S = persona("spouse")


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS")}
    env.update(extra)
    return env


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def make_tree(tmp_path, template="{persona.primary.first_name}\n", documents=None,
              personas=None, manifest_text=None, render_outputs=True):
    root = tmp_path / "repo"
    write(root / "synthetic" / "personas.json", json.dumps(personas or PERSONAS))
    if documents is None:
        documents = [{"source": SOURCE, "output": OUTPUT}]
    manifest = {"version": 1, "documents": documents}
    write(root / R.MANIFEST, manifest_text if manifest_text is not None else json.dumps(manifest))
    if template is not None:
        write(root / SOURCE, template)
    if render_outputs:
        assert run(root, write=True)[0] == 0
    return root


def run(root, write=False, environ=None):
    out, err = io.StringIO(), io.StringIO()
    code = R.run(root, write=write, environ=clean_env() if environ is None else environ,
                 out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def render_text(template, personas=None, forbidden=()):
    people = {p["key"]: {k: v for k, v in p.items() if isinstance(v, str)}
              for p in (personas or PERSONAS)["personas"]}
    return R.substitute(template, people, forbidden)


def output_bytes(root):
    return (root / OUTPUT).read_bytes()


def notice(source=SOURCE):
    return R.NOTICE.format(source=source)


# --- substitution -------------------------------------------------------------------------


def test_canonical_substitution_in_prose(tmp_path):
    root = make_tree(tmp_path, "Name: {persona.primary.first_name} {persona.primary.last_name}; "
                               "spouse {persona.spouse.first_name}.\n")
    expected = f"Name: {P['first_name']} {P['last_name']}; spouse {S['first_name']}.\n"
    assert output_bytes(root) == (notice() + expected).encode("utf-8")
    assert run(root) == (0, "persona docs OK: 1 document(s)\n", "")


def test_code_fence_tokens_render_identically_to_prose(tmp_path):
    token = "{persona.primary.profile_id} {persona.primary.he_first_name}"
    root = make_tree(tmp_path, f"{token}\n\n```json\n{token}\n```\n\n~~~\n{token}\n~~~\n")
    lines = output_bytes(root).decode("utf-8").splitlines()
    value = f"{P['profile_id']} {P['he_first_name']}"
    assert lines[1] == lines[4] == lines[8] == value


def test_escaped_braces_are_literal_in_prose_and_fences():
    template = '{{"a": "{persona.primary.first_name}"}} and `{{persona.KEY.FIELD}}`\n```\n{{}}\n```\n'
    assert render_text(template) == (
        '{"a": "' + P["first_name"] + '"} and `{persona.KEY.FIELD}`\n```\n{}\n```\n')


@pytest.mark.parametrize("value", [
    "{persona.spouse.first_name}",
    "{{persona.spouse.first_name}}",
    "{persona.spouse.first_name} {{ }",
])
def test_inserted_values_are_not_reparsed(value):
    people = copy.deepcopy(PERSONAS)
    people["personas"][0]["first_name"] = value
    assert render_text("[{persona.primary.first_name}]", people) == f"[{value}]"


@pytest.mark.parametrize("template, message", [
    ("{persona.nobody.first_name}", "unknown persona key: nobody"),
    ("{persona.primary.no_such_field}", "unknown string field: primary.no_such_field"),
    ("{persona.primary.invalidity}", "unknown string field: primary.invalidity"),
])
def test_unknown_keys_and_fields_are_rejected(template, message):
    with pytest.raises(R.RenderError, match=message):
        render_text("ok\n" + template)


@pytest.mark.parametrize("template", [
    "{persona.primary.first_name",
    "persona.primary.first_name}",
    "{persona.primary}",
    "{persona.Primary.first_name}",
    "{ persona.primary.first_name }",
    "{persona.primary.first_name.extra}",
    "{persona.primary.first_name:>20}",
    "{persona.primary.first_name!r}",
    "{persona.primary.__class__}",
    "{persona[primary].first_name}",
    "{0}",
    "{}",
    "{persona.primary.first_name}}",
    "{env.HOME}",
    "{include:docs/x.md}",
])
def test_malformed_tokens_and_lone_braces_are_rejected(template):
    with pytest.raises(R.RenderError, match="malformed brace"):
        render_text(template)


def test_errors_name_positions_not_values(tmp_path):
    root = make_tree(tmp_path, "line one {persona.primary.first_name}\n  {persona.ghost.first_name}\n",
                     render_outputs=False)
    code, out, err = run(root)
    assert code == 2 and out == ""
    assert f"{SOURCE}:2:3: unknown persona key: ghost" in err
    assert P["first_name"] not in err


@pytest.mark.parametrize("template", [
    "{persona.primary.national_id}\n",
    "```\n{persona.spouse.national_id}\n```\n",
])
def test_forbidden_field_token_is_rejected_in_prose_and_fences(tmp_path, template):
    docs = [{"source": SOURCE, "output": OUTPUT, "forbidden_fields": ["national_id"]}]
    root = make_tree(tmp_path, template, documents=docs, render_outputs=False)
    code, _, err = run(root, write=True)
    assert code == 2 and "field forbidden in this output" in err
    assert not (root / OUTPUT).exists()


def test_forbidden_field_literal_value_is_rejected_even_in_fences(tmp_path):
    docs = [{"source": SOURCE, "output": OUTPUT, "forbidden_fields": ["phone"]}]
    root = make_tree(tmp_path, f"```\n{S['phone']}\n```\n", documents=docs, render_outputs=False)
    code, _, err = run(root, write=True)
    assert code == 2 and "forbidden field spouse.phone appears literally" in err
    assert S["phone"] not in err


# --- manifest -----------------------------------------------------------------------------


Q_SOURCE, Q_OUTPUT = json.dumps(SOURCE), json.dumps(OUTPUT)
ENTRY = json.dumps({"source": SOURCE, "output": OUTPUT})


def entry_with(extra):
    return '{"source": ' + Q_SOURCE + ', "output": ' + Q_OUTPUT + ", " + extra + "}"


@pytest.mark.parametrize("manifest_text, message", [
    ('{"version": 1, "documents": [], "extra": 1}', "unknown key"),
    ('{"documents": []}', "missing key"),
    ('{"version": 2, "documents": [' + ENTRY + "]}", "unsupported version"),
    ('{"version": true, "documents": [' + ENTRY + "]}", "unsupported version"),
    ('{"version": "1", "documents": [' + ENTRY + "]}", "unsupported version"),
    ('{"version": 1, "documents": []}', "non-empty list"),
    ('{"version": 1, "version": 1, "documents": []}', "duplicate JSON key: version"),
    ('{"version": 1, "documents": [' + entry_with('"source": ' + Q_SOURCE) + "]}",
     "duplicate JSON key: source"),
    ('{"version": 1, "documents": [' + entry_with('"mode": "x"') + "]}", "keys must be"),
    ('{"version": 1, "documents": [{"source": ' + Q_SOURCE + "}]}", "keys must be"),
    ('{"version": 1, "documents": [' + entry_with('"forbidden_fields": ["x"]') + "]}",
     "unknown field: x"),
    ('{"version": 1, "documents": [' + entry_with('"forbidden_fields": ["phone", "phone"]')
     + "]}", "unique strings"),
    ("[1]", "expected an object"),
    ('{"version": 1, ', "invalid JSON"),
])
def test_manifest_schema_is_strict(tmp_path, manifest_text, message):
    root = make_tree(tmp_path, manifest_text=manifest_text, render_outputs=False)
    code, _, err = run(root)
    assert code == 2 and message in err


@pytest.mark.parametrize("field, path", [
    ("source", "../outside/sample.md.in"),
    ("source", "docs/templates/../../x.md.in"),
    ("source", "/etc/sample.md.in"),
    ("source", "docs\\templates\\sample.md.in"),
    ("source", "docs//templates/sample.md.in"),
    ("source", "./docs/templates/sample.md.in"),
    ("source", "docs/templates/.hidden.md.in"),
    ("source", "docs/sample.md.in"),
    ("source", "docs/templates/sample.md"),
    ("output", "../sample.md"),
    ("output", "docs/../../sample.md"),
    ("output", "/tmp/sample.md"),
    ("output", "C:/sample.md"),
    ("output", "docs/sample.txt"),
    ("output", "docs/templates/sample.md"),
    ("output", SOURCE),
    ("output", "synthetic/sample.md"),
    ("output", ".github/sample.md"),
    ("output", "docs//sample.md"),
    ("output", "docs/./sample.md"),
    ("output", "docs/../docs/sample.md"),
    ("output", "docs/a\nb.md"),
    ("source", "docs/templates/a\tb.md.in"),
    ("output", ""),
])
def test_manifest_rejects_escaping_and_misplaced_paths(tmp_path, field, path):
    entry = {"source": SOURCE, "output": OUTPUT, field: path}
    root = make_tree(tmp_path, documents=[entry], render_outputs=False)
    code, _, err = run(root, write=True)
    assert code == 2 and f"documents[0].{field}" in err
    assert not (tmp_path / "sample.md").exists() and not (tmp_path / "outside").exists()


@pytest.mark.parametrize("rel", ["../x.md", "docs/../../x.md", "docs/../.."])
def test_containment_rejects_paths_resolving_outside_the_root(tmp_path, rel):
    root = make_tree(tmp_path).resolve()
    with pytest.raises(R.RenderError, match="escapes the repository"):
        R.contained(root, rel, "probe")


def test_manifest_rejects_duplicate_outputs_and_sources(tmp_path):
    other = "docs/templates/other.md.in"
    root = make_tree(tmp_path, documents=[{"source": SOURCE, "output": OUTPUT},
                                          {"source": other, "output": OUTPUT}],
                     render_outputs=False)
    write(root / other, "x\n")
    code, _, err = run(root, write=True)
    assert code == 2 and "duplicate output: docs/sample.md" in err
    assert not (root / OUTPUT).exists()
    root2 = make_tree(tmp_path / "b", documents=[{"source": SOURCE, "output": OUTPUT},
                                                 {"source": SOURCE, "output": "docs/b.md"}],
                      render_outputs=False)
    code, _, err = run(root2)
    assert code == 2 and "duplicate source" in err


def test_only_listed_documents_render(tmp_path):
    root = make_tree(tmp_path)
    write(root / "docs" / "templates" / "unlisted.md.in", "{persona.primary.first_name}\n")
    write(root / "docs" / "templates" / "broken.md.in", "{persona.nobody.x}\n")
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    assert run(root, write=True)[0] == 0
    assert run(root)[0] == 0
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == before


# --- symlinks and containment -------------------------------------------------------------


def _symlink(link, target, **kwargs):
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, **kwargs)
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            raise
        pytest.skip("symlinks need extra privileges on Windows")


def test_symlinked_source_is_rejected(tmp_path):
    root = make_tree(tmp_path, template=None, render_outputs=False)
    write(tmp_path / "elsewhere.md.in", "{persona.primary.first_name}\n")
    _symlink(root / SOURCE, tmp_path / "elsewhere.md.in")
    code, _, err = run(root, write=True)
    assert code == 2 and "symlink in path" in err
    assert not (root / OUTPUT).exists()


def test_symlinked_template_directory_is_rejected(tmp_path):
    root = make_tree(tmp_path, template=None, render_outputs=False)
    outside = tmp_path / "outside"
    write(outside / "sample.md.in", "{persona.primary.first_name}\n")
    shutil.rmtree(root / "docs" / "templates", ignore_errors=True)
    _symlink(root / "docs" / "templates", outside, target_is_directory=True)
    code, _, err = run(root)
    assert code == 2 and "symlink in path" in err


def test_symlinked_output_is_rejected_and_target_untouched(tmp_path):
    root = make_tree(tmp_path, render_outputs=False)
    target = tmp_path / "target.md"
    write(target, "keep\n")
    _symlink(root / OUTPUT, target)
    for write_flag in (False, True):
        code, _, err = run(root, write=write_flag)
        assert code == 2 and "symlink in path" in err
    assert target.read_bytes() == b"keep\n"
    assert (root / OUTPUT).is_symlink()


def test_symlinked_output_directory_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = make_tree(tmp_path, documents=[{"source": SOURCE, "output": "out/sample.md"}],
                     render_outputs=False)
    _symlink(root / "out", outside, target_is_directory=True)
    code, _, err = run(root, write=True)
    assert code == 2 and "symlink in path" in err
    assert list(outside.iterdir()) == []


def test_symlinked_manifest_and_personas_are_rejected(tmp_path):
    root = make_tree(tmp_path)
    for rel in (R.MANIFEST, R.PERSONAS):
        real = tmp_path / ("copy-" + Path(rel).name)
        shutil.move(str(root / rel), real)
        _symlink(root / rel, real)
        code, _, err = run(root)
        assert code == 2 and "symlink in path" in err
        (root / rel).unlink()
        shutil.move(str(real), root / rel)
    assert run(root)[0] == 0


# --- Unicode, newlines and determinism ----------------------------------------------------


def test_unicode_values_render_as_exact_utf8(tmp_path):
    root = make_tree(tmp_path, "{persona.primary.he_first_name} {persona.child.he_last_name}\n")
    child = persona("child")
    assert output_bytes(root) == (
        notice() + f"{P['he_first_name']} {child['he_last_name']}\n").encode("utf-8")


def test_unicode_paths_stay_single_paths(tmp_path):
    source, output = "docs/templates/דוגמה-zz.md.in", "docs/דוגמה-zz.md"
    root = make_tree(tmp_path, template=None, documents=[{"source": source, "output": output}],
                     render_outputs=False)
    write(root / source, "{persona.primary.first_name}\n")
    code, out, _ = run(root, write=True)
    assert code == 0 and f"persona render wrote: {output}\n" in out
    assert (root / output).read_bytes() == (notice(source) + P["first_name"] + "\n").encode()
    assert run(root)[0] == 0


@pytest.mark.parametrize("raw", [
    "a\r\nb\r\n", "a\rb\r", "a\nb", "a\nb\n\n\n", "a\r\nb\n\r\n",
])
def test_newlines_normalize_to_lf_with_one_final_newline(tmp_path, raw):
    root = make_tree(tmp_path, raw)
    assert output_bytes(root) == (notice() + "a\nb\n").encode("utf-8")


@pytest.mark.parametrize("data, message", [
    (b"\xff\xfe broken", "not valid UTF-8"),
    ("\ufeff{persona.primary.first_name}\n".encode("utf-8"), "byte-order mark"),
])
def test_undecodable_templates_are_rejected(tmp_path, data, message):
    root = make_tree(tmp_path, data, render_outputs=False)
    code, _, err = run(root)
    assert code == 2 and message in err


def test_control_characters_in_persona_values_are_rejected(tmp_path):
    people = copy.deepcopy(PERSONAS)
    people["personas"][0]["first_name"] = P["first_name"] + "\n"
    root = make_tree(tmp_path, personas=people, render_outputs=False)
    code, _, err = run(root)
    assert code == 2 and "control character in primary.first_name" in err


def test_render_is_byte_deterministic(tmp_path):
    template = "{persona.primary.first_name}\n```\n{persona.primary.he_last_name}\n```\n"
    first = output_bytes(make_tree(tmp_path / "a", template))
    second = output_bytes(make_tree(tmp_path / "b", template))
    root = tmp_path / "a" / "repo"
    entry = {"source": SOURCE, "output": OUTPUT, "forbidden": ()}
    people = R.load_personas(root.resolve())
    assert first == second == R.render(root.resolve(), entry, people)
    assert first.endswith(b"\n") and not first.endswith(b"\n\n") and b"\r" not in first


# --- drift checks -------------------------------------------------------------------------


def test_direct_output_edit_is_drift(tmp_path):
    root = make_tree(tmp_path)
    edited = output_bytes(root).replace(P["first_name"].encode(), b"Edited-0000")
    (root / OUTPUT).write_bytes(edited)
    code, out, err = run(root)
    assert code == 1 and out == ""
    assert err == (f"persona render drift: {OUTPUT} differs from {SOURCE} "
                   "(edit the template, then run with --write)\n")
    assert output_bytes(root) == edited


@pytest.mark.parametrize("mutate", [
    lambda b: b + b"\n",
    lambda b: b.rstrip(b"\n"),
    lambda b: b.replace(b"\n", b"\r\n"),
    lambda b: b.split(b"\n", 1)[1],
])
def test_whitespace_and_notice_edits_are_drift(tmp_path, mutate):
    root = make_tree(tmp_path)
    (root / OUTPUT).write_bytes(mutate(output_bytes(root)))
    assert run(root)[0] == 1


def test_stale_persona_value_is_drift(tmp_path):
    root = make_tree(tmp_path)
    people = copy.deepcopy(PERSONAS)
    people["personas"][0]["first_name"] = P["first_name"] + "-zz"
    write(root / "synthetic" / "personas.json", json.dumps(people))
    assert run(root)[0] == 1
    assert run(root, write=True)[0] == 0
    assert (P["first_name"] + "-zz").encode() in output_bytes(root)
    assert run(root)[0] == 0


def test_template_change_and_missing_output_are_drift(tmp_path):
    root = make_tree(tmp_path)
    write(root / SOURCE, "{persona.spouse.first_name}\n")
    assert run(root)[0] == 1
    (root / OUTPUT).unlink()
    code, _, err = run(root)
    assert code == 1 and f"drift: {OUTPUT}" in err


def test_check_mode_never_writes(tmp_path):
    root = make_tree(tmp_path)
    write(root / SOURCE, "{persona.spouse.first_name}\n")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    assert run(root)[0] == 1
    (root / OUTPUT).unlink()
    del before[root / OUTPUT]
    assert run(root)[0] == 1
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    assert after == before


def test_write_updates_only_drifted_outputs(tmp_path):
    other = "docs/templates/other.md.in"
    root = make_tree(tmp_path, documents=[{"source": SOURCE, "output": OUTPUT},
                                          {"source": other, "output": "docs/other.md"}],
                     render_outputs=False)
    write(root / other, "{persona.parent.first_name}\n")
    assert run(root, write=True)[0] == 0
    stamp = (root / "docs" / "other.md").stat().st_mtime_ns
    write(root / SOURCE, "{persona.spouse.first_name}\n")
    code, out, _ = run(root, write=True)
    assert code == 0 and out == ("persona render wrote: docs/sample.md\n"
                                 "persona docs OK: 2 document(s)\n")
    assert (root / "docs" / "other.md").stat().st_mtime_ns == stamp
    assert not list(root.rglob(".render-*"))
    assert run(root)[0] == 0


def test_write_is_atomic_when_any_document_fails(tmp_path):
    other = "docs/templates/other.md.in"
    root = make_tree(tmp_path, documents=[{"source": SOURCE, "output": OUTPUT},
                                          {"source": other, "output": "docs/other.md"}],
                     render_outputs=False)
    write(root / other, "{persona.nobody.first_name}\n")
    assert run(root, write=True)[0] == 2
    assert not (root / OUTPUT).exists()


@pytest.mark.parametrize("env", [{"GITHUB_ACTIONS": "true"}, {"CI": "true"}])
def test_write_is_refused_in_ci(tmp_path, env):
    root = make_tree(tmp_path)
    write(root / SOURCE, "{persona.spouse.first_name}\n")
    stale = output_bytes(root)
    code, out, err = run(root, write=True, environ=clean_env(**env))
    assert code == 2 and out == "" and "--write is refused in CI" in err
    assert output_bytes(root) == stale
    assert run(root, environ=clean_env(**env))[0] == 1


# --- CLI and the real tree ----------------------------------------------------------------


def cli(*args, env=None):
    return subprocess.run([sys.executable, str(RENDERER), *args], check=False,
                          capture_output=True, text=True, env=env or clean_env())


def test_cli_exit_codes_and_flags(tmp_path):
    root = make_tree(tmp_path)
    assert cli("--root", str(root)).returncode == 0
    (root / OUTPUT).write_bytes(b"edited\n")
    assert cli("--root", str(root)).returncode == 1
    assert cli("--root", str(root), "--write", env=clean_env(CI="true")).returncode == 2
    assert cli("--root", str(root), "--write").returncode == 0
    assert cli("--root", str(root)).returncode == 0
    assert cli("--root", str(tmp_path / "missing")).returncode == 2


def test_real_tree_check_passes():
    result = cli("--root", str(ROOT))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "persona docs OK: 1 document(s)\n" and result.stderr == ""


def test_real_manifest_adopts_the_first_example_pair():
    manifest = json.loads((ROOT / R.MANIFEST).read_text(encoding="utf-8"))
    assert manifest == {"version": 1, "documents": [{
        "source": "docs/templates/persona-template-example.md.in",
        "output": "docs/persona-template-example.md",
        "forbidden_fields": ["national_id", "phone", "phone_us"],
    }]}
    output = (ROOT / "docs" / "persona-template-example.md").read_text(encoding="utf-8")
    assert output.startswith(notice("docs/templates/persona-template-example.md.in"))
    fence = output.split("```json\n", 1)[1].split("```", 1)[0]
    for value in (P["first_name"], P["last_name"], P["profile_id"]):
        assert value in fence and value in output.split("```", 1)[0]
    for p in PERSONAS["personas"]:
        for field in ("national_id", "phone", "phone_us"):
            assert p[field] not in output
    assert "{persona." in output and "{{" not in output
