"""Manual image builds are human-only, never owner automation."""
from pathlib import Path

import yaml


def test_publish_is_manual_human_only():
    text = (Path(__file__).parents[1] / '.github/workflows/publish-image.yml').read_text()
    data = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(data['on']) == {'workflow_dispatch'}
    guard = data['jobs']['build']['if']
    assert "github.repository == 'reihlinstinct/geni-uploader'" in guard
    assert "github.event_name == 'workflow_dispatch'" in guard
    assert "github.actor == 'reihl'" in guard
    assert "github.triggering_actor == 'reihl'" in guard
    assert 'repository_owner' not in guard
