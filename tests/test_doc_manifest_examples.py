"""Getting-started manifests must satisfy the offline loader contract."""
import re
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from geni_uploader.client import upload

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('document', ['README.md', 'docs/usage.md'])
def test_getting_started_manifest_loads_offline(document, tmp_path):
    text = (ROOT / document).read_text(encoding='utf-8')
    if document == 'README.md':
        # Extract the first YAML fence, without depending on example values.
        example = re.search(r'```yaml\n(.*?)```', text, re.DOTALL).group(1)
    else:
        section = text.split('## 4. The manifest and packaging assets', 1)[1]
        example = textwrap.dedent(section.split('    targets:', 1)[1]
                                  .split('Rules enforced', 1)[0])
        example = 'targets:' + example
    data = yaml.safe_load(example)
    for target in data['targets']:
        for kind in ('documents', 'photos'):
            for item in target.get(kind, []):
                if 'file' in item:
                    (tmp_path / item['file']).write_bytes(b'synthetic offline asset')
    manifest = tmp_path / 'manifest.yaml'
    manifest.write_text(yaml.safe_dump(data), encoding='utf-8')
    with patch.object(upload, 'execute') as network:
        loaded = upload.load_manifest(manifest)
    assert loaded['targets']
    network.assert_not_called()
