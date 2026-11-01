"""论文题录、学术路径数据与旧备份兼容测试。"""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import papers
from server import LibraryStore, validate_library
from test_practice import fixture


def paper_fixture():
    return {
        'id': 'p1', 'title': 'A Test Paper on Local Learning', 'authors': ['Ada Lovelace', 'Alan Turing'],
        'year': 2024, 'venue': 'Journal of Local Knowledge', 'doi': '10.1234/example.2024.1',
        'arxivId': '2401.12345', 'url': 'https://example.org/paper', 'pdfUrl': 'https://example.org/paper.pdf',
        'abstract': 'A synthetic abstract used only for tests.', 'keywords': ['learning', 'local'],
        'tags': ['核心'], 'categoryId': 'net', 'stage': 'included', 'readState': 'read', 'priority': 3,
        'source': 'Crossref', 'review': {'question': 'How does it work?', 'method': 'Experiment', 'data': 'N=10',
                                          'findings': 'A finding.', 'limitations': 'A limitation.', 'relevance': 'Useful.'},
        'notes': [{'id': 'n1', 'page': 3, 'quote': 'A quoted sentence.', 'text': 'My interpretation.', 'createdAt': '2026-11-01'}],
        'createdAt': '2026-11-01', 'updatedAt': '2026-11-01',
    }


def research_fixture():
    return {'question': 'How do local tools support research?', 'scope': 'Local first.', 'searchStrategy': 'Crossref',
            'inclusion': 'Peer reviewed.', 'exclusion': 'No abstract.', 'synthesis': 'A synthesis.', 'updatedAt': '2026-11-01'}


class PaperLookupTests(unittest.TestCase):
    def test_crossref_metadata_is_normalized(self):
        payload = {'message': {'title': ['A Crossref Paper'], 'author': [{'given': 'Ada', 'family': 'Lovelace'}],
                               'container-title': ['Journal'], 'issued': {'date-parts': [[2024, 1, 1]]},
                               'DOI': '10.1234/crossref', 'URL': 'https://publisher.example/paper',
                               'abstract': '<jats:p>An abstract.</jats:p>', 'subject': ['AI']}}
        with patch('papers.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as fetch:
            result = papers.lookup_paper('https://doi.org/10.1234/crossref')
        self.assertEqual(result['title'], 'A Crossref Paper')
        self.assertEqual(result['authors'], ['Ada Lovelace'])
        self.assertEqual(result['year'], 2024)
        self.assertEqual(result['abstract'], 'An abstract.')
        self.assertEqual(result['source'], 'Crossref')
        self.assertIn('api.crossref.org', fetch.call_args.args[0].full_url)

    def test_arxiv_metadata_and_pdf_link_are_normalized(self):
        xml = '''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
        <entry><id>https://arxiv.org/abs/2401.12345v1</id><title>An arXiv Paper</title>
        <summary>An abstract.</summary><published>2024-01-02T00:00:00Z</published>
        <author><name>Ada Lovelace</name></author><category term="cs.AI"/>
        <arxiv:doi>10.1234/arxiv</arxiv:doi></entry></feed>'''
        with patch('papers.urlopen', return_value=io.BytesIO(xml.encode())):
            result = papers.lookup_paper('https://arxiv.org/abs/2401.12345')
        self.assertEqual(result['title'], 'An arXiv Paper')
        self.assertEqual(result['arxivId'], '2401.12345v1')
        self.assertEqual(result['pdfUrl'], 'https://arxiv.org/pdf/2401.12345v1.pdf')
        self.assertEqual(result['doi'], '10.1234/arxiv')
        self.assertEqual(result['source'], 'arXiv')

    def test_arxiv_doi_prefix_is_routed_to_arxiv(self):
        with patch('papers.lookup_arxiv', return_value={'title': 'Routed'}) as lookup:
            result = papers.lookup_paper('10.48550/arXiv.2401.12345')
        self.assertEqual(result['title'], 'Routed')
        lookup.assert_called_once_with('2401.12345')

    def test_bad_identifier_does_not_call_network(self):
        with patch('papers.urlopen') as fetch:
            with self.assertRaises(papers.IntegrationError):
                papers.lookup_paper('not a DOI or arXiv id')
        fetch.assert_not_called()

    def test_invalid_metadata_json_is_reported(self):
        with patch('papers.urlopen', return_value=io.BytesIO(b'not json')):
            with self.assertRaises(papers.IntegrationError):
                papers.lookup_paper('10.1234/broken')


class PaperValidationTests(unittest.TestCase):
    def test_papers_and_research_survive_validation(self):
        library = copy.deepcopy(fixture())
        library['papers'] = [paper_fixture()]
        library['research'] = research_fixture()
        clean = validate_library(library)
        self.assertEqual(clean['papers'][0]['title'], 'A Test Paper on Local Learning')
        self.assertEqual(clean['papers'][0]['review']['method'], 'Experiment')
        self.assertEqual(clean['papers'][0]['notes'][0]['page'], 3)
        self.assertEqual(clean['research']['searchStrategy'], 'Crossref')

    def test_old_backup_gets_empty_papers_and_research(self):
        clean = validate_library(copy.deepcopy(fixture()))
        self.assertEqual(clean['papers'], [])
        self.assertEqual(clean['research']['question'], '')

    def test_invalid_stage_and_missing_category_are_rejected(self):
        library = copy.deepcopy(fixture())
        paper = paper_fixture()
        paper['stage'] = 'unknown'
        library['papers'] = [paper]
        with self.assertRaises(ValueError):
            validate_library(library)
        paper['stage'] = 'candidate'
        paper['categoryId'] = 'missing'
        with self.assertRaises(ValueError):
            validate_library(library)

    def test_store_preserves_papers_for_old_clients_that_omit_the_field(self):
        with tempfile.TemporaryDirectory() as temp:
            data = copy.deepcopy(fixture())
            data['papers'] = [paper_fixture()]
            data['research'] = research_fixture()
            path = Path(temp) / 'library.json'
            path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            store = LibraryStore(path)
            payload = store.read()
            payload.pop('papers')
            payload.pop('research')
            store.save(payload)
            restored = store.read()
            self.assertEqual(restored['papers'][0]['id'], 'p1')
            self.assertEqual(restored['research']['question'], 'How do local tools support research?')


if __name__ == '__main__':
    unittest.main()
