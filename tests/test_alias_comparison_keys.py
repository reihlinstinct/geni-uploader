"""Synthetic comparison-only alias collisions; no network or text rewriting."""
import copy

import pytest

from geni_uploader.runners import bounded_alias_append as core
from tests.test_alias_append import plan


@pytest.mark.parametrize('old,new', [
    ('ZZ Re\u0301ne', 'ZZ R\u00e9ne'),
    ('ZZ\u00a0Old2', 'ZZ Old2'),
    ('ZZ  Old2', 'ZZ Old2'),
    ('ZZ Rene', 'ZZ RENE'),
    ('ZZ Stra\u00dfe', 'ZZ Strasse')])
def test_equivalent_existing_alias_blocks_before_effect(old, new):
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = [new]
    before = copy.deepcopy(c)
    with pytest.raises(core.Blocked): core.plan(c)
    assert c == before


@pytest.mark.parametrize('old', ['ZZ Re\u0301ne', 'ZZ\u00a0Old2', 'ZZ  Old2'])
def test_distinct_append_preserves_stored_alias_bytes(old):
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = ['ZZ Different']
    before = copy.deepcopy(c)
    approved = core.plan(c)
    assert c == before
    assert approved['expected']['nicknames'] == [old]
    assert approved['append'] == ['ZZ Different']
    assert core.payload(approved) == {'nicknames': old + ',ZZ Different'}


@pytest.mark.parametrize('old', [
    ['ZZ Re\u0301ne', 'ZZ R\u00e9ne'],
    ['ZZ\u00a0Old2', 'ZZ Old2'],
    ['ZZ  Old2', 'ZZ Old2']])
def test_existing_only_comparison_collision_still_blocks(old):
    c = plan(); c['expected']['nicknames'] = old; c['append'] = ['ZZ Different']
    with pytest.raises(core.Blocked): core.plan(c)
