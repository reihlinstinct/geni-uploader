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
    {'source_url': {'ZZPrivateKey': 'ZZPrivateValue'}}, {'source_url': 'http://[ZZPrivate'}])
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
