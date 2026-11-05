"""Synthetic per-locale collision regressions. Refs #788. No vendor access."""
import copy
import unicodedata

import pytest

from tests.test_bounded_parent_pair_batch import config, m


def collision(locale, variant='exact'):
    c = config(); g = c['groups'][0]
    pinned = g['profiles'][next(iter(g['profiles']))]
    pinned_locale = 'en-US' if locale == 'en' else locale
    fields = pinned['names'][pinned_locale]
    fields.update(first_name='ZZ-Caf\u00e9', last_name='ZZ-Family')
    for entry in g['entries'] + [g['sibling']]:
        for key in ('en', 'he'):
            entry['payload']['names'][key].update(
                first_name='ZZ-Other-' + entry['key'] + key, last_name='ZZ-Different')
        entry['payload'].update(entry['payload']['names']['en'])
    target = g['sibling']['payload']
    match = copy.deepcopy(fields)
    if variant == 'case': match = {k: v.swapcase() for k, v in match.items()}
    if variant == 'trim': match = {k: '  ' + v + '  ' for k, v in match.items()}
    if variant == 'nfd': match = {k: unicodedata.normalize('NFD', v) for k, v in match.items()}
    target['names'][locale].update(match)
    target.update(target['names']['en'])
    return c


@pytest.mark.parametrize('locale', ['he', 'en'])
@pytest.mark.parametrize('variant', ['exact', 'case', 'trim', 'nfd'])
def test_any_matching_locale_stops_before_execution(locale, variant):
    with pytest.raises(m.Blocked):
        m.plan(collision(locale, variant))


@pytest.mark.parametrize('field', ['first_name', 'last_name'])
def test_different_name_pair_is_not_a_collision(field):
    c = collision('en'); target = c['groups'][0]['sibling']['payload']
    target['names']['en'][field] = 'ZZ-Unrelated'
    target.update(target['names']['en'])
    assert m.plan(c) == c


def test_middle_name_does_not_hide_same_first_last_pair():
    c = collision('en'); target = c['groups'][0]['sibling']['payload']
    target['names']['en']['middle_name'] = 'ZZ-Extra'
    target.update(target['names']['en'])
    with pytest.raises(m.Blocked): m.plan(c)


def test_absent_pinned_name_map_is_not_inferred_from_top_level():
    c = collision('en')
    for profile in c['groups'][0]['profiles'].values(): profile.pop('names', None)
    assert m.plan(c) == c
