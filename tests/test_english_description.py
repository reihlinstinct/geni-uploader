"""Synthetic offline description contract: no external calls."""
import copy
from unittest.mock import patch

import pytest
from test_geni_upload import MANIFEST, _manifest_file

import geni_upload as g


@pytest.mark.parametrize('english', [None, '', '   ', 123, 'תיאור מקור בעברית בלבד',
                                     'https://example.invalid/ZZsource'])
@pytest.mark.parametrize('kind', ['documents', 'photos'])
def test_missing_english_rejected_locally(tmp_path, english, kind):
    data = copy.deepcopy(MANIFEST)
    item = data['targets'][0]['documents'][0]
    item['description_en'] = english
    item['description'] = 'תיאור מקור בעברית בלבד'
    if kind == 'photos':
        asset = tmp_path / 'ZZscan.jpg'
        asset.write_bytes(b'ZZ synthetic bytes')
        item['file'] = str(asset)
        data['targets'][0]['photos'] = [item]
        data['targets'][0]['documents'] = []
        # Put manifest beside the synthetic asset to respect containment.
        import yaml
        manifest = tmp_path / 'ZZmanifest.yaml'
        manifest.write_text(yaml.safe_dump(data))
    else:
        manifest = _manifest_file(data)
    with patch.object(g, 'execute') as network, pytest.raises(g.ApiError, match='description_en'):
        g.load_manifest(manifest)
    network.assert_not_called()


def test_english_first_and_optional_original_preserved_payload():
    item = {'title': 'ZZ source', 'description_en': 'ZZ source catalogue entry.',
            'description': 'תיאור מקור בעברית\nOriginal: ZZ Quelle'}
    payload = g.upload_payload(item, 'documents')
    assert payload['description'] == ('ZZ source catalogue entry.\n\n'
                                      'תיאור מקור בעברית\nOriginal: ZZ Quelle')
    assert 'description_en' not in payload
    assert g.upload_payload({'title': 'ZZ source', 'description_en': 'ZZ source catalogue entry.'},
                            'photos')['description'] == 'ZZ source catalogue entry.'


def test_legacy_description_alone_never_satisfies_requirement():
    with pytest.raises(g.ApiError, match='description_en'):
        g.upload_payload({'title': 'ZZ source', 'description': 'ZZ English-looking source text.'},
                         'documents')


@pytest.mark.parametrize('extra', ['', 123, {}])
def test_bad_supplementary_text_rejected(extra):
    with pytest.raises(g.ApiError, match='supplementary'):
        g.render_description({'description_en': 'ZZ source catalogue entry.', 'description': extra})
