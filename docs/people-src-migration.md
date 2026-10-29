# Shared people core move (#459)

Depends on the package foundation (#457). Moves the shared implementation
byte-for-byte from people_core.py to src/geni_uploader/core/people.py. Root
people_core.py temporarily aliases the same module object, not copied globals or
star imports. Blocked, Journal, digest and monkeypatch identity remain shared.
Runtime root callers now import the canonical package; legacy test imports keep
exercising the facade. A fixed SHA256 byte comparison enforces the intact move.

Run `python -m pip install -r requirements-dev.txt` before checkout tests or root
offline commands. Editable installation is a development step; no runtime
sys.path mutation is introduced. The wheel includes core and is tested installed
outside the checkout with isolated Python. The package import still performs no
network requests, journal creation or credential lookup.

Offline source-release inventory now includes tracked Python files below
src/geni_uploader. Hash/dirty-content checks apply to those real implementations,
not only the root facade. Tests verify archive bytes/hashes and reject dirty,
file-symlink and parent-symlink src implementations. No archive is uploaded or
installed. A source inventory is not authenticated authority or a deploy.

Docker still carries only the existing source-upload scripts, which do not
import people core. Its COPY and entrypoints are unchanged and guarded by a
regression. Existing coverage targets remain the same two production uploader
files. The offline Node-test workflow now explicitly installs Python3.12 and the
project before its Python parity/validator subprocesses. It previously relied
on root-module imports, so Python suites alone could not catch that path gap.
All66isolated runtime suites remain required. Workflow permissions and Node
commands are unchanged. No secrets, permission changes, image publication, production gate,
Geni operation or deployment changes in this slice.

The temporary facade leaves one root filename until downstream entrypoints and
references are migrated. It will be removed in the final cleanup slice, not
claimed as a completed whole-repository layout here.
