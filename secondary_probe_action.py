"""Explicitly approved secondary read-only Action. No write or refresh client."""
import json
import os
import subprocess
from pathlib import Path

from parent_probe import ReadOnly, collect, connection, encrypt
from people_core import Blocked, require


def run(environment):
    """All secrets stay in memory. Only age ciphertext is written."""
    require(environment.get('PROBE_CONFIRM') == 'READ_ONLY')
    require(environment.get('PROBE_RUN_ATTEMPT') == '1')  # never rerun a live attempt
    config = connection(json.loads(environment.get('SECONDARY_PROBE_CONNECTION_JSON', '')))
    recipient = environment.get('PROBE_RECIPIENT', '')
    choice = environment.get('PROBE_MERGE_POLICY', '')
    require(choice in ('STRICT', 'ALLOW_UNKNOWN_READ_ONLY'))
    token = environment.get('SECONDARY_PROBE_TOKEN', '')
    output = Path(environment.get('PROBE_OUTPUT_DIR', ''))
    require(output.is_absolute() and not output.exists())
    encrypt(recipient, b'preflight')
    output.mkdir(mode=0o700)
    # Only a token supplied under the secondary-specific name is accepted.
    result = collect(config, ReadOnly(token), allow_unknown_merge=choice == 'ALLOW_UNKNOWN_READ_ONLY')
    ciphertext = encrypt(recipient, json.dumps(result, ensure_ascii=False).encode())
    fd = os.open(output/'parent-evidence.age', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(ciphertext)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    try:
        run(os.environ)
        print('secondary read-only collection complete; encrypted artifact only; creation disabled')
        return 0
    except (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError,
            subprocess.SubprocessError):
        print('secondary read-only collection stopped; no retry; review protected setup')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
