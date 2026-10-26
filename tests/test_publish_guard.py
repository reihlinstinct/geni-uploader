"""Manual image builds allow explicit actors; source upload stays human-only."""
from pathlib import Path

import yaml


def test_publish_is_manual_explicit_actors_only():
    text = (Path(__file__).parents[1] / '.github/workflows/publish-image.yml').read_text()
    data = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(data['on']) == {'workflow_dispatch'}
    guard = data['jobs']['build']['if']
    assert "github.repository == 'reihlinstinct/geni-uploader'" in guard
    assert "github.event_name == 'workflow_dispatch'" in guard
    assert "github.actor == 'reihl'" in guard
    assert "github.triggering_actor == 'reihl'" in guard
    assert 'repository_owner' not in guard

    assert "github.actor == 'reihlinstinct'" in guard
    assert "github.triggering_actor == 'reihlinstinct'" in guard
    apply = (Path(__file__).parents[1] / '.github/workflows/geni-upload.yml').read_text()
    apply_guard = yaml.load(apply, Loader=yaml.BaseLoader)['jobs']['upload']['if']
    assert "github.actor == 'reihl'" in apply_guard
    assert "github.triggering_actor == 'reihl'" in apply_guard
    assert "github.actor == 'reihlinstinct'" not in apply_guard
