"""公开学术元数据查询：只访问 Crossref / arXiv，不发送笔记或凭据。"""
import html
import json
import re
import xml.etree.ElementTree as ET
from functools import partial
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request

from integrations import IntegrationError
from security import public_urlopen

urlopen = partial(public_urlopen, domains=['crossref.org', 'arxiv.org'])
ARXIV_NS = {'a': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
MAX_METADATA = 2 * 1024 * 1024


def _text(value):
    if value is None:
        return ''
    value = re.sub(r'<[^>]+>', ' ', str(value))
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()


def _year(value):
    match = re.search(r'(?:^|\D)((?:19|20)\d{2})(?:\D|$)', str(value or ''))
    return int(match.group(1)) if match else None


def _https(value):
    value = str(value or '').strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ''
    return value if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password else ''


def normalize_doi(raw):
    value = str(raw or '').strip()
    value = re.sub(r'^doi:\s*', '', value, flags=re.I)
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value, flags=re.I)
    value = value.strip().rstrip('.,;')
    return value if re.fullmatch(r'10\.\d{4,9}/\S+', value) else ''


def normalize_arxiv(raw):
    value = str(raw or '').strip()
    match = re.search(r'arxiv\.org/(?:abs|pdf)/([^?#\s]+)', value, flags=re.I)
    candidate = match.group(1) if match else value
    candidate = re.sub(r'^arxiv:\s*', '', candidate, flags=re.I).strip().strip('/')
    candidate = re.sub(r'\.pdf$', '', candidate, flags=re.I)
    pattern = r'(?:\d{4}\.\d{4,5}|[A-Za-z-]+(?:\.[A-Za-z]{2})?/\d{7})(?:v\d+)?'
    return candidate if re.fullmatch(pattern, candidate) else ''


def _fetch(url):
    try:
        request = Request(url, headers={'User-Agent': 'StudyAtlas/1.0 (local research library)'})
        with urlopen(request, timeout=25) as response:
            raw = response.read(MAX_METADATA + 1)
        if len(raw) > MAX_METADATA:
            raise ValueError('metadata too large')
        return raw
    except (HTTPError, URLError, OSError, ValueError):
        raise IntegrationError('暂时无法从 Crossref / arXiv 读取元数据，可手动填写论文信息')


def lookup_doi(raw):
    doi = normalize_doi(raw)
    if not doi:
        raise IntegrationError('DOI 格式不正确')
    try:
        data = json.loads(_fetch('https://api.crossref.org/works/' + quote(doi, safe='')))
    except (ValueError, TypeError):
        raise IntegrationError('Crossref 返回的元数据格式不正确')
    message = data.get('message') if isinstance(data, dict) else None
    if not isinstance(message, dict):
        raise IntegrationError('Crossref 没有返回可识别的论文元数据')
    titles = message.get('title') or []
    title = _text(titles[0] if isinstance(titles, list) and titles else '')
    if not title:
        raise IntegrationError('Crossref 没有返回论文标题，可手动填写')
    authors = []
    for author in message.get('author') or []:
        if not isinstance(author, dict):
            continue
        name = ' '.join(part for part in [author.get('given'), author.get('family')] if part).strip() or str(author.get('name') or '').strip()
        if name and name not in authors:
            authors.append(name[:200])
    containers = message.get('container-title') or []
    venue = _text(containers[0] if isinstance(containers, list) and containers else message.get('publisher', ''))
    published = message.get('issued') or message.get('published-print') or message.get('published-online') or {}
    parts = (published.get('date-parts') or [[None]]) if isinstance(published, dict) else [[None]]
    year = parts[0][0] if parts and isinstance(parts[0], list) and parts[0] else None
    links = message.get('link') or []
    pdf_url = next((item.get('URL') for item in links if isinstance(item, dict) and 'pdf' in str(item.get('content-type', '')).lower()), '')
    return {
        'title': title[:500], 'authors': authors[:50], 'year': _year(year),
        'venue': venue[:300], 'doi': normalize_doi(message.get('DOI') or doi),
        'arxivId': '', 'url': _https(message.get('URL')) or 'https://doi.org/' + quote(doi, safe=''),
        'pdfUrl': _https(pdf_url), 'abstract': _text(message.get('abstract'))[:30000],
        'keywords': list(dict.fromkeys(_text(item)[:60] for item in (message.get('subject') or []) if _text(item)))[:30],
        'source': 'Crossref',
    }


def lookup_arxiv(raw):
    arxiv_id = normalize_arxiv(raw)
    if not arxiv_id:
        raise IntegrationError('arXiv 编号格式不正确')
    try:
        root = ET.fromstring(_fetch('https://export.arxiv.org/api/query?id_list=' + quote(arxiv_id, safe='')))
    except ET.ParseError:
        raise IntegrationError('arXiv 返回的元数据格式不正确')
    entry = root.find('a:entry', ARXIV_NS)
    if entry is None:
        raise IntegrationError('arXiv 没有返回可识别的论文元数据')
    title = _text(entry.findtext('a:title', default='', namespaces=ARXIV_NS))
    if not title:
        raise IntegrationError('arXiv 没有返回论文标题，可手动填写')
    authors = []
    for author in entry.findall('a:author', ARXIV_NS):
        name = _text(author.findtext('a:name', default='', namespaces=ARXIV_NS))
        if name and name not in authors:
            authors.append(name[:200])
    published = entry.findtext('a:published', default='', namespaces=ARXIV_NS)
    categories = []
    for category in entry.findall('a:category', ARXIV_NS):
        term = _text(category.get('term'))
        if term and term not in categories:
            categories.append(term[:60])
    journal_ref = _text(entry.findtext('arxiv:journal_ref', default='', namespaces=ARXIV_NS))
    doi = normalize_doi(entry.findtext('arxiv:doi', default='', namespaces=ARXIV_NS))
    identifier = _text(entry.findtext('a:id', default='', namespaces=ARXIV_NS)).rstrip('/').split('/')[-1] or arxiv_id
    return {
        'title': title[:500], 'authors': authors[:50], 'year': _year(published),
        'venue': (journal_ref or 'arXiv preprint')[:300], 'doi': doi,
        'arxivId': identifier[:100], 'url': 'https://arxiv.org/abs/' + identifier,
        'pdfUrl': 'https://arxiv.org/pdf/' + identifier + '.pdf',
        'abstract': _text(entry.findtext('a:summary', default='', namespaces=ARXIV_NS))[:30000],
        'keywords': categories[:30], 'source': 'arXiv',
    }


def lookup_paper(raw):
    """Resolve a DOI/arXiv identifier without fetching arbitrary URLs or private data."""
    query = str(raw or '').strip()
    if not query or len(query) > 3000:
        raise IntegrationError('请输入 DOI、arXiv 编号或对应链接')
    result = None
    doi = normalize_doi(query)
    if doi and doi.lower().startswith('10.48550/arxiv.'):
        result = lookup_arxiv(re.split(r'arxiv\.', doi, maxsplit=1, flags=re.I)[1])
    elif doi:
        result = lookup_doi(query)
    elif normalize_arxiv(query):
        result = lookup_arxiv(query)
    if result is None:
        raise IntegrationError('无法识别这个标识，请输入 DOI 或 arXiv 编号')
    if not result.get('title'):
        raise IntegrationError('没有取得论文标题，可手动填写')
    return result
