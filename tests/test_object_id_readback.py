"""Synthetic target-list proof, never a standalone object-existence check."""
from unittest.mock import Mock, patch

import pytest

import geni_upload as g


@pytest.mark.parametrize('kind,base', [('documents', 'document'), ('photos', 'photo')])
@pytest.mark.parametrize('prefixed', [False, True])
def test_id_proves_tag_without_metadata(kind, base, prefixed):
    value = base + '-123' if prefixed else '123'
    with patch.object(g, 'execute', return_value={'results': [{'id': value}]}):
        assert g.verify_linkage('ZZ', '456', kind, ('object-id', base, '123'), Mock())


@pytest.mark.parametrize('value', [None, 'photo-123', 'document-document-123', 'ZZ', '１２３', '124'])
def test_missing_wrong_or_malformed_id_does_not_match(value):
    item = {'id': value, 'title': 'ZZ same', 'source_url': 'https://example.invalid'}
    with patch.object(g, 'execute', return_value={'results': [item]}), patch.object(g, '_sleep'):
        assert not g.verify_linkage('ZZ', '456', 'documents', ('object-id', 'document', '123'), Mock())


def test_documented_next_page_followed_on_same_target():
    responses = [{'results': [], 'next_page': '?page=2'}, {'results': [{'id': 'document-123'}]}]
    with patch.object(g, 'execute', side_effect=responses) as call:
        assert ('object-id', 'document', '123') in g.list_tagged('ZZ', '456', 'documents')
        assert call.call_args.args[2] == g.API_BASE + '/profile-456/documents?page=2'


@pytest.mark.parametrize('link', ['https://example.invalid/steal', '/api/profile-999/documents?page=2',
                                 '/api/document-123', 2])
def test_untrusted_pagination_never_routes_token_elsewhere(link):
    with patch.object(g, 'execute', return_value={'results': [], 'next_page': link}) as call:
        with pytest.raises(g.ApiError):
            g.list_tagged('ZZ', '456', 'documents')
        assert call.call_count == 1


def test_incomplete_listing_cannot_prove_match():
    reply = {'results': [{'id': '123'}], 'next_page': '?page=2'}
    with patch.object(g, 'execute', return_value=reply):
        assert g.list_tagged('ZZ', '456', 'documents') is None


def test_array_listing_and_wrong_target_no_proof():
    with patch.object(g, 'execute', return_value=[{'id': 'document-123'}]) as call:
        assert ('object-id', 'document', '123') in g.list_tagged('ZZ', '456', 'documents')
        assert call.call_args.args[2].endswith('/profile-456/documents')
    with patch.object(g, 'execute', return_value={'results': []}), patch.object(g, '_sleep'):
        assert not g.verify_linkage('ZZ', '789', 'documents', ('object-id', 'document', '123'), Mock())


def singleton(**changes):
    row = {'id': 'document-123', 'guid': '456', 'title': 'ZZ',
           'url': 'https://example.invalid', 'tags': []}
    row.update(changes)
    return row


@pytest.mark.parametrize('response', [{'results': []}, {'results': [{'id': '123'}]},
                                     {'results': [{'id': '123'}, {'id': '124'}]}, singleton()])
def test_zero_one_many_singleton_normalized(response):
    assert isinstance(g.source_listing_rows(response, 'documents'), list)


@pytest.mark.parametrize('response', [{}, {'error': 'ZZ'}, singleton(error='ZZ'),
                                     singleton(id='photo-123'), singleton(tags='ZZ'),
                                     singleton(url=None), singleton(results=None)])
def test_invalid_singleton_never_accepted(response):
    with pytest.raises(g.ApiError):
        g.source_listing_rows(response, 'documents')


def test_singleton_exact_id_and_target_endpoint_proof():
    with patch.object(g, 'execute', return_value=singleton()) as call:
        assert g.verify_linkage('ZZ', '789', 'documents', ('object-id', 'document', '123'), Mock())
        assert call.call_args.args[2].endswith('/profile-789/documents')
    with patch.object(g, 'execute', return_value=singleton(id='document-124')), patch.object(g, '_sleep'):
        assert not g.verify_linkage('ZZ', '789', 'documents', ('object-id', 'document', '123'), Mock())
