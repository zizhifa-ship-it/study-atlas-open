"""Local document text extraction for DOCX, HTML and text uploads.

The extractor runs on this machine and never sends file bytes to a model. The
returned text can be previewed before the user chooses whether to use AI.
"""
import base64
import binascii
import io
import re
import zlib
from html.parser import HTMLParser
from pathlib import PurePosixPath
from xml.etree import ElementTree

MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_DOCX_XML_BYTES = 32 * 1024 * 1024
TEXT_EXTENSIONS = {'.txt', '.md', '.markdown', '.srt', '.vtt', '.json', '.json3'}


class _HTMLText(HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'template', 'svg', 'canvas'}
    BLOCK = {'p', 'div', 'section', 'article', 'header', 'footer', 'main', 'aside',
             'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'br', 'hr',
             'pre', 'blockquote', 'table', 'ul', 'ol', 'dl', 'dt', 'dd'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP:
            self.skip += 1
        if tag in self.BLOCK:
            self.parts.append('\n')

    def handle_startendtag(self, tag, attrs):
        if tag.lower() in self.BLOCK:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag in self.BLOCK:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip and data:
            self.parts.append(data)

    def text(self):
        value = ''.join(self.parts).replace('\r\n', '\n').replace('\r', '\n')
        value = re.sub(r'[ \t]+\n', '\n', value)
        value = re.sub(r'\n[ \t]+', '\n', value)
        value = re.sub(r'\n{3,}', '\n\n', value)
        return value.strip()


def _filename(data):
    from integrations import IntegrationError
    filename = data.get('filename', '')
    if not isinstance(filename, str) or not filename or len(filename) > 255:
        raise IntegrationError('文件名不正确')
    filename = PurePosixPath(filename.replace('\\', '/')).name
    if not filename or filename in {'.', '..'}:
        raise IntegrationError('文件名不正确')
    return filename


def _decode_text(raw):
    from integrations import IntegrationError
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        try:
            return raw.decode('utf-16'), 'utf-16'
        except UnicodeDecodeError:
            raise IntegrationError('UTF-16 文字编码不完整，请另存为 UTF-8 后重试')
    if b'\x00' in raw[:4096]:
        raise IntegrationError('文件看起来不是可读取的文字文件')
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise IntegrationError('文字编码无法识别，请另存为 UTF-8 后重试')


def _extract_docx(raw):
    from integrations import IntegrationError
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise IntegrationError('Word 文件解压后过大，请按章节拆分')
            try:
                xml = archive.read('word/document.xml')
            except KeyError:
                raise IntegrationError('Word 文件缺少正文，请另存为 .docx 后重试')
            if len(xml) > MAX_DOCX_XML_BYTES:
                raise IntegrationError('Word 正文过大，请按章节拆分')
    except IntegrationError:
        raise
    except (OSError, ValueError, RuntimeError, EOFError, NotImplementedError, zipfile.BadZipFile, zlib.error):
        raise IntegrationError('无法读取 Word 文件，文件可能损坏或已加密')
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        raise IntegrationError('Word 正文格式无法识别，请另存为 .docx 后重试')
    namespace = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    paragraphs = []
    for paragraph in root.iter(namespace + 'p'):
        current = []
        for node in paragraph.iter():
            if node.tag == namespace + 't' and node.text:
                current.append(node.text)
            elif node.tag == namespace + 'tab':
                current.append('\t')
            elif node.tag in {namespace + 'br', namespace + 'cr'}:
                current.append('\n')
        text = ''.join(current).strip()
        if text:
            paragraphs.append(text)
    text = '\n\n'.join(paragraphs)
    if len(text.strip()) < 20:
        raise IntegrationError('Word 文件中没有读取到足够正文；图片和扫描内容需要先 OCR')
    return text


def _extract_html(raw):
    from integrations import IntegrationError
    text, _ = _decode_text(raw)
    parser = _HTMLText()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        raise IntegrationError('HTML 正文格式无法识别，请另存为 Markdown 后重试')
    content = parser.text()
    if len(content) < 20:
        raise IntegrationError('HTML 中没有读取到足够正文；可先另存为 Markdown 后导入')
    return content


def extract_document(data):
    """Return previewable text from a local upload; no model call is made."""
    from integrations import IntegrationError
    filename = _filename(data)
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in TEXT_EXTENSIONS | {'.docx', '.html', '.htm', '.pdf'}:
        raise IntegrationError('支持 PDF、DOCX、HTML、TXT、Markdown 与字幕文件')
    encoded = data.get('base64', '')
    if not isinstance(encoded, str) or not encoded:
        raise IntegrationError('文件内容为空')
    max_encoded = 4 * ((MAX_DOCUMENT_BYTES + 2) // 3)
    if len(encoded) > max_encoded:
        raise IntegrationError('文件最多 %d MB，请按章节拆分' % (MAX_DOCUMENT_BYTES // (1024 * 1024)))
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise IntegrationError('文件上传编码不正确')
    if not raw or len(raw) > MAX_DOCUMENT_BYTES:
        raise IntegrationError('文件最多 %d MB，请按章节拆分' % (MAX_DOCUMENT_BYTES // (1024 * 1024)))

    if suffix == '.pdf':
        from pdf_import import read_pdf_upload
        return read_pdf_upload(data)
    if suffix == '.docx':
        content = _extract_docx(raw)
        warning = '已在本机提取 Word 正文；图片、批注、公式和复杂表格版式未读取，请对照原件核对。'
        material_filename = PurePosixPath(filename).stem + '.md'
        title = PurePosixPath(filename).stem
    elif suffix in {'.html', '.htm'}:
        content = _extract_html(raw)
        warning = '已在本机提取网页正文并去除脚本、样式与图片；排版请对照原网页。'
        material_filename = PurePosixPath(filename).stem + '.md'
        title = PurePosixPath(filename).stem
    else:
        content, encoding = _decode_text(raw)
        warning = '' if encoding == 'utf-8-sig' else '文件按 %s 编码在本机读取，请核对特殊字符。' % encoding
        material_filename = filename
        title = PurePosixPath(filename).stem

    from materials import parse_material
    title, material_filename, content = parse_material({
        'title': title or '本地资料', 'filename': material_filename, 'content': content,
    })
    return {'content': content, 'filename': material_filename, 'originalFilename': filename,
            'title': title, 'warning': warning, 'readLocally': True}
