"""Synthetic value-free URL mismatch diagnostics never weaken strict checks."""
import copy

import pytest
from test_source_details import ITEM

import source_details as s


@pytest.mark.parametrize('observed,flag', [
    (' http://example.invalid/ZZsecret/path?q=ZZsecret ', 'url_trim_equal'),
    ('https://example.invalid/ZZsecret/path?q=ZZsecret', 'url_scheme_only'),
    ('http://example.invalid/ZZsecret/path/?q=ZZsecret', 'url_trailing_slash_only')])
def test_normalization_hints_never_override_expectations(observed, flag):
    item = copy.deepcopy(ITEM)
    item['expect'] = {'source_url': 'http://example.invalid/ZZsecret/path?q=ZZsecret'}
    if flag == 'url_trim_equal':
        item['expect']['source_url'] = observed.strip()
    obj = {'source_url': observed}
    assert s.source_url_diagnostics(obj, item)[flag]
    assert not s.matches_expect(obj, item)


@pytest.mark.parametrize('obj', [{}, {'source_url': None}, {'source_url': 12},
    {'source_url': {'ZZPrivateKey': 'ZZPrivateValue'}}, {'source_url': 'http://[ZZPrivate'},
    {'source_url': 'http://[ZZPrivateNetloc]/ZZPrivatePath'}])
def test_missing_malformed_and_wrong_types_are_fixed_booleans(obj, capsys):
    item = copy.deepcopy(ITEM)
    output = s.source_url_diagnostics(obj, item)
    assert all(type(v) is bool for v in output.values())
    for key, passed in output.items():
        s.diagnostic(key, 'true' if passed else 'false')
    text = capsys.readouterr().out
    assert 'ZZPrivate' not in text
    assert 'example.invalid' not in text


def test_checked_plan_logs_only_fixed_hints_and_stops_before_targets(monkeypatch, capsys):
    item = copy.deepcopy(ITEM)
    monkeypatch.setattr(s, 'object_read', lambda *args: {
        'source_url': 'https://ZZPrivateHost.invalid/ZZPrivatePath?ZZPrivateQuery'})
    def forbidden(*args, **kwargs):
        raise AssertionError('target lookup must not happen')
    monkeypatch.setattr(s, 'deceased_target', forbidden)
    with pytest.raises(s.api.ApiError, match='precondition'):
        s.checked_plan([item], 'ZZtoken')
    text = capsys.readouterr().out
    assert 'stage=url_present result=true' in text
    assert 'stage=preconditions result=fail' in text
    assert 'ZZPrivate' not in text
    assert item['expect']['source_url'] not in text


@pytest.mark.parametrize('observed,flag', [
    ('http://example.invalid/ZZPrivatePath#ZZPrivateFragment', 'url_fragment_equal'),
    ('HTTP://example.invalid/ZZPrivatePath', 'url_raw_scheme_equal')])
def test_fragment_and_raw_scheme_mismatch_hints_do_not_leak_or_relax(observed, flag, capsys):
    item = copy.deepcopy(ITEM)
    item['expect'] = {'source_url': 'http://example.invalid/ZZPrivatePath'}
    obj = {'source_url': observed}
    hints = s.source_url_diagnostics(obj, item)
    assert hints[flag] is False
    assert hints['url_host_equal'] and hints['url_path_equal'] and hints['url_query_equal']
    assert not s.matches_expect(obj, item)
    for key, value in hints.items():
        s.diagnostic(key, 'true' if value else 'false')
    text = capsys.readouterr().out
    assert f'stage={flag} result=false' in text
    assert 'ZZPrivate' not in text and 'example.invalid' not in text


def test_equal_fragment_and_raw_scheme_are_true():
    item = copy.deepcopy(ITEM)
    obj = {'source_url': item['expect']['source_url']}
    hints = s.source_url_diagnostics(obj, item)
    assert hints['url_fragment_equal'] is True
    assert hints['url_raw_scheme_equal'] is True
