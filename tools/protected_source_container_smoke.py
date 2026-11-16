"""No secrets/network to Geni: verify production-image uid and mount permissions."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from geni_uploader.runners.protected_source_approval import IMAGE


def main():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        root.chmod(0o700)
        token = root / 'ZZ-token'; token.write_text('ZZ-inert-token'); token.chmod(0o600)
        plan = root / 'ZZ-plan'; plan.mkdir(mode=0o700)
        # Pull is registry-only. Execution has no network and no real endpoints.
        subprocess.run(['docker', 'pull', IMAGE], check=True)
        subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--user', '0:0',
                        '-v', str(token) + ':/run/ZZ-token:ro',
                        '-v', str(plan) + ':/run/ZZ-plan', '--entrypoint', 'python', IMAGE,
                        '-c', ('from pathlib import Path; import os; assert os.getuid()==0; '
                        'assert Path("/run/ZZ-token").read_text()=="ZZ-inert-token"; '
                        'Path("/run/ZZ-plan/report.json").write_text("ZZ-offline"); '
                        'print("offline pinned-container mounts verified")')], check=True)
        assert (plan / 'report.json').read_text() == 'ZZ-offline'


if __name__ == '__main__':
    main()
