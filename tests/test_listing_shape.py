"""No values, arbitrary key names, writes or pagination in structural probe."""
import argparse
import json
from unittest.mock import patch

from test_geni_upload import MANIFEST, _manifest_file

import geni_upload as g


def test_shape_never_emits_values_or_unknown_keys():
    response = {'results': [{'id': '123', 'title': 'ZZPRIVATE', 'ZZKEYPII': 'ZZSECRET'},
                            'ZZSTRINGPII', None], 'ZZTOPPII': 'ZZTOKEN',
                'next_page': 'https://example.invalid/ZZPRIVATE'}
    result = json.dumps(g.listing_shape(response))
    assert 'ZZ' not in result
    assert 'unknown_keys' in result
    assert g.listing_shape(response)['results']['count'] == 3


def test_probe_only_first_page_get_no_status_writes(capsys):
    args = argparse.Namespace(manifest=_manifest_file(MANIFEST), token_file=None)
    with patch.object(g, 'get_token', return_value='ZZTOKEN'), \
            patch.object(g, 'verify_profile', return_value=('123', 'ZZPRIVATE')), \
            patch.object(g, 'execute', return_value={'results': 'ZZPII', 'next_page': 'ZZURL'}) as call, \
            patch.object(g, 'save_status') as save:
        assert g.cmd_listing_shape(args) == 0
    assert call.call_count == 1 and call.call_args.args[0] == 'GET'
    save.assert_not_called()
    assert 'ZZ' not in capsys.readouterr().out


def test_probe_stops_on_throttle():
    import pytest
    args = argparse.Namespace(manifest=_manifest_file(MANIFEST), token_file=None)
    with patch.object(g, 'get_token', return_value='ZZ'), \
            patch.object(g, 'verify_profile', side_effect=g.ThrottledError('429')), \
            patch.object(g, 'execute') as call, pytest.raises(g.ThrottledError):
        g.cmd_listing_shape(args)
    call.assert_not_called()


def test_nested_tags_no_values_or_unknown_key_names():
    response = {'id': '123', 'tags': [{'id': '456', 'ZZNAME': 'ZZPERSON'}, 'ZZURL', None]}
    shape = g.listing_shape(response)
    assert 'ZZ' not in json.dumps(shape)
    assert shape['tags_samples'][0]['entry_types'] == {'NoneType': 1, 'dict': 1, 'str': 1}
