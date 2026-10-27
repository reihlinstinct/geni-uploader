import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "profile_probe", Path(__file__).parents[1] / "tools/profile-probe/check.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
TOKEN = "ZZ_SYNTHETIC_TOKEN"
RECIPIENT = "ZZ_SYNTHETIC_RECIPIENT"
SHA = "a" * 40
RAW = b'{"id":"ZZ_SYNTHETIC_ID","guid":"ZZ_SYNTHETIC_GUID","name":"ZZ_SYNTHETIC_NAME","public":false,"is_alive":true,"email":"ZZ_DROP_THIS"}'


class Response:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return self.raw[:size]


class Opener:
    def __init__(self, raw=RAW, error=None):
        self.raw, self.error, self.calls = raw, error, []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return Response(self.raw)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.binary = Path(self.tmp.name) / "age"
        self.binary.write_text("synthetic placeholder")
        self.out = str(Path(self.tmp.name) / "out")
        self.pin = patch.object(
            probe, "RECIPIENT_SHA256", hashlib.sha256(RECIPIENT.encode()).hexdigest()
        )
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def call(self, opener=None, **kwargs):
        args = {
            "token": TOKEN,
            "recipient": RECIPIENT,
            "age_binary": str(self.binary),
            "output_dir": self.out,
            "tool_sha": SHA,
            "opener": opener or Opener(),
        }
        args.update(kwargs)
        return probe.probe(**args)

    def encrypted(self, *args, **kwargs):
        self.plaintext = kwargs["input"]
        self.encryption_args = args[0]
        self.assertEqual(len(self.plaintext), probe.PADDED_SIZE)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertNotIn("TOKEN_PROBE_CREDENTIAL", kwargs["env"])
        return subprocess.CompletedProcess(args[0], 0, b"age-encryption.org/v1\n" + b"Z" * 17000)

    def test_one_fixed_get_allowlist_padding_ciphertext_only(self):
        o = Opener()
        with patch.object(probe.subprocess, "run", side_effect=self.encrypted):
            self.assertEqual(self.call(o), ("ENCRYPTED_PROFILE_REPORT_READY", 0))
        self.assertEqual(len(o.calls), 1)
        request, timeout = o.calls[0]
        self.assertEqual(
            (request.full_url, request.method, request.data, timeout), (probe.URL, "GET", None, 20)
        )
        report = json.loads(self.plaintext)
        self.assertEqual(set(report["profile"]), {"id", "guid", "name", "public", "is_alive"})
        self.assertNotIn("ZZ_DROP_THIS", self.plaintext.decode())
        self.assertNotIn(TOKEN, self.plaintext.decode())
        self.assertEqual(report["tool_sha"], SHA)
        self.assertEqual([p.name for p in Path(self.out).iterdir()], ["profile-report.age"])
        self.assertNotIn(b"ZZ_SYNTHETIC_NAME", (Path(self.out) / "profile-report.age").read_bytes())

    def test_preflight_no_request(self):
        for kwargs in (
            {"token": ""},
            {"token": "x\ny"},
            {"token": "https://zz.invalid"},
            {"recipient": "ZZ_WRONG"},
            {"tool_sha": "bad"},
            {"age_binary": "/ZZ_NOT_FOUND"},
        ):
            o = Opener()
            self.assertEqual(self.call(o, **kwargs)[1], 1)
            self.assertEqual(o.calls, [])

    def test_existing_output_refused(self):
        Path(self.out).mkdir()
        o = Opener()
        self.assertEqual(self.call(o)[1], 1)
        self.assertEqual(o.calls, [])

    def test_bad_shapes_no_encryption(self):
        for raw in (
            b"{}",
            b"[]",
            b"null",
            b'{"name":"ZZ"}',
            b'{"id":123}',
            b'{"id":"ZZ","public":"false"}',
            b'{"id":"ZZ","is_alive":1}',
            b'{"id":"ZZ","error":"ZZ"}',
            b'{"id":"ZZ","id":"YY"}',
            b"\xff",
            b"x" * 65537,
        ):
            with (
                tempfile.TemporaryDirectory() as temp,
                patch.object(probe.subprocess, "run") as encrypt,
            ):
                self.assertEqual(self.call(Opener(raw), output_dir=temp + "/out")[1], 1)
                encrypt.assert_not_called()

    def test_missing_fields_stay_unknown(self):
        self.assertEqual(probe.selected_fields({"guid": "ZZ"})["public"], None)
        self.assertEqual(probe.selected_fields({"guid": "ZZ"})["name"], None)

    def test_errors_no_retry(self):
        for code in (301, 302, 307, 401, 403, 429, 500, 503):
            with tempfile.TemporaryDirectory() as temp:
                o = Opener(
                    error=urllib.error.HTTPError(
                        probe.URL, code, TOKEN, {}, io.BytesIO(TOKEN.encode())
                    )
                )
                verdict, result = self.call(o, output_dir=temp + "/out")
                self.assertEqual(result, 1)
                self.assertEqual(len(o.calls), 1)
                self.assertNotIn(TOKEN, verdict)
                self.assertFalse((Path(temp) / "out/profile-report.age").exists())

    def test_encrypt_failure_no_artifact(self):
        for result in (
            subprocess.CompletedProcess([], 1, b"ZZ_PRIVATE"),
            subprocess.CompletedProcess([], 0, b"bad"),
        ):
            with (
                tempfile.TemporaryDirectory() as temp,
                patch.object(probe.subprocess, "run", return_value=result),
            ):
                self.assertEqual(self.call(output_dir=temp + "/out")[1], 1)
                self.assertEqual(list((Path(temp) / "out").iterdir()), [])

    def test_stdout_is_fixed(self):
        with (
            patch.dict(
                os.environ, {"TOKEN_PROBE_CREDENTIAL": TOKEN, "PROFILE_REPORT_RECIPIENT": RECIPIENT}
            ),
            patch.object(probe, "probe", return_value=("ENCRYPTED_PROFILE_REPORT_READY", 0)),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(probe.main(), 0)
            self.assertEqual(
                output.getvalue(),
                "ENCRYPTED_PROFILE_REPORT_READY\nGENI_WRITES=0; OWNER_IDENTITY=NOT_VERIFIED\n",
            )
            self.assertNotIn("TOKEN_PROBE_CREDENTIAL", os.environ)

    def test_redirect_proxy_disabled(self):
        self.assertIsNone(probe.NoRedirect().redirect_request())
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(probe.urllib.request, "build_opener", return_value=Opener()) as build,
            patch.object(probe.subprocess, "run", side_effect=self.encrypted),
        ):
            probe.probe(TOKEN, RECIPIENT, str(self.binary), temp + "/out", SHA)
            self.assertEqual(build.call_args.args[0].proxies, {})
            self.assertIsInstance(build.call_args.args[1], probe.NoRedirect)

    @unittest.skipUnless(
        os.environ.get("PROFILE_TEST_AGE_DIR"),
        "real age roundtrip requires explicit local binary directory",
    )
    def test_real_age_roundtrip_synthetic_only(self):
        age_dir = Path(os.environ["PROFILE_TEST_AGE_DIR"])
        identity = Path(self.tmp.name) / "synthetic-key"
        subprocess.run(
            [str(age_dir / "age-keygen"), "-o", str(identity)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        recipient = (
            subprocess.check_output([str(age_dir / "age-keygen"), "-y", str(identity)])
            .decode()
            .strip()
        )
        with patch.object(
            probe, "RECIPIENT_SHA256", hashlib.sha256(recipient.encode()).hexdigest()
        ):
            self.assertEqual(self.call(recipient=recipient, age_binary=str(age_dir / "age"))[1], 0)
        ciphertext = Path(self.out) / "profile-report.age"
        plain = subprocess.check_output(
            [str(age_dir / "age"), "-d", "-i", str(identity), str(ciphertext)]
        )
        self.assertEqual(len(plain), probe.PADDED_SIZE)
        report = json.loads(plain)
        self.assertEqual(report["profile"]["name"], "ZZ_SYNTHETIC_NAME")
        self.assertNotIn(TOKEN.encode(), plain)
        self.assertNotIn(b"ZZ_DROP_THIS", plain)
        self.assertNotIn(b"ZZ_SYNTHETIC_NAME", ciphertext.read_bytes())
        self.assertEqual(set(Path(self.out).iterdir()), {ciphertext})

    def test_workflow_security(self):
        root = Path(__file__).parents[1]
        s = (root / ".github/workflows/profile-probe.yml").read_text()
        for required in (
            "github.actor == 'reihl'",
            "github.triggering_actor == 'reihl'",
            "github.ref == 'refs/heads/master'",
            "inputs.confirm == 'TEST'",
            "environment: token-probe",
            "contents: read",
            "persist-credentials: false",
            "python3 -I",
            "retention-days: 1",
            "compression-level: 0",
            "if-no-files-found: error",
        ):
            self.assertIn(required, s)
        self.assertEqual(s.count("secrets.TOKEN_PROBE_CREDENTIAL"), 1)
        self.assertIn("PROFILE_REPORT_RECIPIENT: ${{ vars.PROFILE_REPORT_RECIPIENT }}", s)
        self.assertNotIn("schedule:", s)
        self.assertNotIn("pull_request:", s)
        self.assertIn("path: ${{ runner.temp }}/profile-ciphertext/profile-report.age", s)
        self.assertIn("/tools/profile-probe/ @reihl", (root / ".github/CODEOWNERS").read_text())


if __name__ == "__main__":
    unittest.main()
