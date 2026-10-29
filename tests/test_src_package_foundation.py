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
    assert modules == [
        "geni_offline/__init__.py", "geni_uploader/__init__.py",
        "geni_uploader/core/__init__.py", "geni_uploader/core/people.py",
    ]
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
