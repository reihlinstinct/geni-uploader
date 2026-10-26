"""Functional CLI test using a real loopback-only fake server."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def test_cli_repair_real_transport_loopback(tmp_path):
    obj = {"id": "document-101", "source_url": "https://example.invalid/ZZsource",
           "description": "ZZ old", "tags": []}
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if "/profile-" in self.path:
                value = {"id": "profile-201", "display_name": "ZZPerson ZZTest",
                         "is_alive": False}
            else:
                value = obj
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_POST(self):
            from urllib.parse import parse_qs
            calls.append(self.path)
            fields = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            if self.path.endswith("/update"):
                obj.update({k: v[0] for k, v in fields.items()})
            else:
                obj["tags"].append("profile-201")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(obj).encode())
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    manifest = tmp_path / "items.json"
    manifest.write_text(json.dumps({"schema_version": 1, "items": [{
        "key": "ZZsource", "kind": "document", "object_id": "101",
        "expect": {"source_url": "https://example.invalid/ZZsource"},
        "set": {"description_en": "ZZ new source description", "date": "1933-01-04"},
        "targets": [{"profile_id": "201", "expect_name": "ZZPerson ZZTest"}],
        "manual_facts": []}]}))
    token = tmp_path / "token"
    token.write_text("ZZdummy")
    env = {**os.environ, "GENI_UPLOAD_E2E": "1",
           "GENI_API_BASE": f"http://127.0.0.1:{server.server_port}"}
    try:
        result = subprocess.run([
            sys.executable, str(Path(__file__).parents[1] / "source_details.py"),
            "repair", "--manifest", str(manifest), "--token-file", str(token),
            "--confirm", "YES", "--state", str(tmp_path / "state")], check=False, env=env,
            capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "manual" in result.stdout
        assert "ZZ new" not in result.stdout
        assert obj["description"] == "ZZ new source description"
        assert obj["tags"] == ["profile-201"]
        assert calls == ["/document-101/update", "/document-101/tag/profile-201"]
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_actual_workflow_argument_order_selects_metadata_entrypoint():
    """Execute the workflow's real argument-selection shell, without a service."""
    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/geni-upload.yml").read_text()
    start = workflow.index('            if [ "$MODE" = "selftest" ]; then\n              # Inert:')
    end = workflow.index('            if [[ "$MODE" == details-* ]]', start)
    import textwrap
    # YAML removes its block indentation before bash sees the heredoc.
    shell = textwrap.dedent(workflow[start:end]) + '\nprintf "%s\\n" "${ARGS[@]}"\n'
    for mode in ("details-plan", "details-repair", "plan", "run"):
        result = subprocess.run(["bash", "-c", shell], check=True,
                                env={**os.environ, "MODE": mode, "CONFIRM": "YES",
                                     "MANIFEST_PATH": "ZZ-records.json"},
                                capture_output=True, text=True)
        args = result.stdout.splitlines()
        if mode.startswith("details-"):
            assert args[:3] == [mode, "--token-file", "/run/geni-token"]
            entrypoint = (root / "entrypoint.sh").read_text()
            assert 'case "${1:-}" in' in entrypoint
            assert 'exec python /opt/source_details.py "$MODE" "$@"' in entrypoint
        else:
            assert args[:3] == ["--token-file", "/run/geni-token", mode]
        assert ("--sync-state" in args) == (mode == "details-repair")
        assert ("--confirm" in args) == (mode in ("run", "details-repair"))
