"""Synthetic masked payload/export and encrypted-retention boundaries."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from test_source_plan_guards import MANIFEST

import geni_upload as g
import visual_plan as v


def test_masked_payload_no_private_fields(tmp_path, monkeypatch):
    path = tmp_path / 'visual.json'
    monkeypatch.setenv('GENI_VISUAL_PLAN', str(path))
    with patch.object(g, 'load_manifest', return_value=copy.deepcopy(MANIFEST)), \
            patch.object(g, 'get_token', return_value='ZZTOKEN'), \
            patch.object(g, 'verify_profile', return_value=('991234567890', 'ZZFirst ZZLast')), \
            patch.object(g, 'list_tagged', return_value=[]):
        assert g.cmd_plan(argparse.Namespace(manifest=str(tmp_path / 'manifest'))) == 0
    raw = path.read_text()
    assert 'ZZ' not in raw and '991234' not in raw and 'http' not in raw
    data = json.loads(raw)
    assert data['complete'] and data['profiles'][0]['sources'][0]['verdict'] == 'new'
    assert path.stat().st_mode & 0o777 == 0o600
    assert 'living/unknown, private' in v.render(data)


def test_no_payload_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv('GENI_VISUAL_PLAN', raising=False)
    v.save(v.new())
    assert list(tmp_path.iterdir()) == []


def test_incomplete_replaces_stale_plan(tmp_path, monkeypatch):
    path = tmp_path / 'visual.json'
    path.write_text('ZZstale')
    monkeypatch.setenv('GENI_VISUAL_PLAN', str(path))
    data = v.new()
    assert not path.exists()
    v.profile(data)
    v.save(data)
    assert 'INCOMPLETE: do not upload' in v.render(json.loads(path.read_text()))


@pytest.mark.parametrize('status', ['living', 'unknown', None])
def test_labels_cannot_show_living_or_unknown_people(status):
    data = v.new()
    v.source(v.profile(data), 'documents', 'blocked')
    labels = {'1': {'life_status': status, 'name': 'ZZPrivate', 'evidence': 'ZZproof',
                    'reviewed_no_living_details': True, 'source_labels': {'1': 'ZZTitle'}}}
    assert 'ZZ' not in v.render(data, labels)


def test_deceased_label_requires_evidence_and_separate_review():
    data = v.new()
    v.source(v.profile(data), 'documents', 'skip')
    label = {'life_status': 'deceased', 'name': 'ZZDeceased <script>',
             'source_labels': {'1': 'ZZReviewedSource'}}
    assert 'ZZ' not in v.render(data, {'1': label})
    label.update(evidence='ZZEvidence', reviewed_no_living_details=True)
    result = v.render(data, {'1': label})
    assert 'ZZDeceased &lt;script&gt;' in result and 'ZZReviewedSource' in result
    assert '<script>' not in result


def test_reject_extra_fields():
    data = v.new()
    v.profile(data)['name'] = 'ZZPrivate'
    with pytest.raises(ValueError):
        v.render(data)


def test_ciphertext_only_workflow_and_no_mail():
    root = Path(__file__).parents[1]
    workflow = (root / '.github/workflows/geni-upload.yml').read_text()
    assert 'VISUAL_PLAN_IMAGE_READY: "no"' in workflow
    assert 'default: false' in workflow.split('visual_review:', 1)[1].split('confirm:', 1)[0]
    assert 'age -r "$RECIPIENT" -o "$RUNNER_TEMP/visual-plan.age"' in workflow
    assert 'logs/visual-plan-run${GITHUB_RUN_NUMBER}-attempt${GITHUB_RUN_ATTEMPT}.age' in workflow
    assert 'cp "$RUNNER_TEMP/plan-report/visual.json"' not in workflow
    assert 'upload-artifact' not in workflow
    assert 'smtp' not in (root / 'visual_plan.py').read_text().lower()
    assert 'COPY visual_plan.py /opt/visual_plan.py' in (root / 'Dockerfile').read_text()


def test_optional_visual_error_preserves_plan_outcome(tmp_path, monkeypatch):
    path = tmp_path / 'visual.json'
    monkeypatch.setenv('GENI_VISUAL_PLAN', str(path))
    with patch.object(g, 'load_manifest', return_value=copy.deepcopy(MANIFEST)), \
            patch.object(g, 'get_token', return_value='ZZTOKEN'), \
            patch.object(g, 'verify_profile', return_value=('991234567890', 'ZZFirst ZZLast')), \
            patch.object(g, 'list_tagged', return_value=[]), \
            patch.object(v, 'source', side_effect=ValueError('ZZprivate')):
        assert g.cmd_plan(argparse.Namespace(manifest=str(tmp_path / 'manifest'))) == 0
    assert json.loads(path.read_text())['complete'] is False


@pytest.mark.parametrize('labels', ['{broken', '[]', '{"1": "ZZPrivate"}'])
def test_malformed_labels_clean_error(tmp_path, monkeypatch, capsys, labels):
    path = tmp_path / 'payload'
    path.write_text(json.dumps(v.new()))
    label = tmp_path / 'labels'
    label.write_text(labels)
    output = tmp_path / 'output'
    monkeypatch.setattr('sys.argv', ['visual_plan', str(path), '--html', str(output),
                                     '--labels', str(label)])
    with pytest.raises(SystemExit) as error:
        v.main()
    assert error.value.code == 2
    assert capsys.readouterr().err == 'Private visual input is invalid; review payload and labels.\n'
    assert not output.exists()
