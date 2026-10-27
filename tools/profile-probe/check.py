"""One user-run own-profile GET, encrypted allowlisted report, no plaintext logs."""

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://www.geni.com/api/profile?fields=id,guid,name,public,is_alive"
MAX_RESPONSE = 65536
PADDED_SIZE = 16384
RECIPIENT_SHA256 = "bb7113c1aa1593a27dc033731d2ba7cfe7db8364a0c4c15ce558160e8dc43504"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def selected_fields(data):
    if not isinstance(data, dict) or not data or "error" in data:
        raise ValueError("unknown response")
    selected = {}
    for field, limit in (("id", 512), ("guid", 256), ("name", 4096)):
        value = data.get(field)
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value) > limit
        ):
            raise ValueError("invalid field")
        selected[field] = value
    # At least one actual profile identifier must be present, not /api/user shape.
    if selected["id"] is None and selected["guid"] is None:
        raise ValueError("missing profile identifier")
    for field in ("public", "is_alive"):
        value = data.get(field)
        if value is not None and type(value) is not bool:
            raise ValueError("invalid boolean")
        selected[field] = value
    # Never save extra fields, even if the provider ignores fields filtering.
    return selected


def probe(token, recipient, age_binary, output_dir, tool_sha, opener=None):
    if (
        not isinstance(token, str)
        or not 1 <= len(token) <= 8192
        or any(not 33 <= ord(c) <= 126 for c in token)
        or token.startswith(("http:", "https:"))
        or "access_token=" in token
    ):
        return "STOP_INVALID_TOKEN_INPUT", 1
    if hashlib.sha256(recipient.encode()).hexdigest() != RECIPIENT_SHA256:
        return "STOP_UNAPPROVED_RECIPIENT", 1
    if not re.fullmatch("[0-9a-f]{40}", tool_sha):
        return "STOP_UNVERIFIED_TOOL_SHA", 1
    if not Path(age_binary).is_file():
        return "STOP_ENCRYPTION_UNAVAILABLE", 1
    directory = Path(output_dir)
    if directory.exists():
        return "STOP_OUTPUT_PATH_EXISTS", 1
    try:
        # Prepare isolated output location BEFORE any private read. No plaintext file.
        directory.mkdir(mode=0o700)
        if opener is None:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(
            URL,
            method="GET",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                return "STOP_HTTP_RESPONSE", 1
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            return "STOP_RESPONSE_TOO_LARGE", 1
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        report = {
            "schema_version": 1,
            "requested_fields": ["id", "guid", "name", "public", "is_alive"],
            "source_endpoint": URL,
            "tool_sha": tool_sha,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Python3.10 offline tests
            "profile": selected_fields(data),
            "owner_identity": "NOT_VERIFIED",
            "geni_writes": 0,
            "missing_fields": [
                key for key, value in selected_fields(data).items() if value is None
            ],
        }
        plaintext = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode()
        if len(plaintext) > PADDED_SIZE:
            return "STOP_REPORT_TOO_LARGE", 1
        plaintext = plaintext.ljust(PADDED_SIZE, b" ")
        # Private report is passed only through stdin. Suppress all age diagnostics.
        encrypted = subprocess.run(
            [age_binary, "--encrypt", "--recipient", recipient],
            input=plaintext,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
            env={"PATH": "/usr/bin:/bin"},
        )
        if (
            encrypted.returncode != 0
            or not encrypted.stdout.startswith(b"age-encryption.org/v1\n")
            or not PADDED_SIZE < len(encrypted.stdout) < PADDED_SIZE + 4096
        ):
            return "STOP_ENCRYPTION_FAILED", 1
        # Artifact uploader sees only this ciphertext; never upload the parent temp dir.
        with (directory / "profile-report.age").open("xb") as destination:
            os.chmod(destination.name, 0o600)
            destination.write(encrypted.stdout)
        return "ENCRYPTED_PROFILE_REPORT_READY", 0
    except urllib.error.HTTPError as error:
        error.close()
        return ("STOP_RATE_LIMIT_NO_RETRY" if error.code == 429 else "STOP_HTTP_RESPONSE"), 1
    except Exception:  # noqa: BLE001 - no private exception/body enters public output
        return "STOP_UNVERIFIABLE_NO_RETRY", 1


def main():
    token = os.environ.pop("TOKEN_PROBE_CREDENTIAL", "")
    recipient = os.environ.pop("PROFILE_REPORT_RECIPIENT", "")
    verdict, code = probe(
        token,
        recipient,
        os.environ.get("PROFILE_AGE_BINARY", ""),
        os.environ.get("PROFILE_OUTPUT_DIR", ""),
        os.environ.get("GITHUB_SHA", ""),
    )
    print(verdict)
    print("GENI_WRITES=0; OWNER_IDENTITY=NOT_VERIFIED")
    return code


if __name__ == "__main__":
    sys.exit(main())
