"""Zero-token local extraction for DOCX and HTML uploads."""
import base64
import io
import unittest
import zipfile

from document_import import extract_document
from integrations import IntegrationError


def upload(filename, raw):
    return {'filename': filename, 'base64': base64.b64encode(raw).decode('ascii')}


def docx_bytes(paragraphs):
    namespace = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    body = ''.join(
        '<w:p><w:r><w:t>%s</w:t></w:r></w:p>' % text for text in paragraphs
    )
    xml = ('<w:document xmlns:w="%s"><w:body>%s</w:body></w:document>' % (namespace, body)).encode('utf-8')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', xml)
        archive.writestr('word/media/image1.png', b'not an interpreted image')
    return buffer.getvalue()


class DocumentImportTests(unittest.TestCase):
    def test_docx_extraction_keeps_paragraphs_and_marks_limits(self):
        result = extract_document(upload('网络讲义.docx', docx_bytes([
            '第一段：IP 地址用于网络寻址与主机标识。',
            '第二段：DHCP 自动分配地址，路由表决定下一跳。',
        ])))
        self.assertIn('第一段', result['content'])
        self.assertIn('第二段', result['content'])
        self.assertIn('\n\n', result['content'])
        self.assertEqual(result['filename'], '网络讲义.md')
        self.assertTrue(result['readLocally'])
        self.assertIn('图片', result['warning'])

    def test_html_extraction_drops_scripts_and_styles(self):
        html = '''<html><head><style>.hidden{display:none}</style><script>不应出现</script></head>
        <body><h1>网络基础</h1><p>TCP 提供确认与重传。</p><p>UDP 不保证可靠交付。</p></body></html>'''.encode('utf-8')
        result = extract_document(upload('课程.html', html))
        self.assertIn('网络基础', result['content'])
        self.assertIn('TCP 提供确认与重传。', result['content'])
        self.assertNotIn('不应出现', result['content'])
        self.assertNotIn('display:none', result['content'])
        self.assertTrue(result['readLocally'])

    def test_gb18030_text_is_read_locally_with_warning(self):
        raw = '网络课程使用 IP 进行寻址，DHCP 负责自动分配地址。'.encode('gb18030')
        result = extract_document(upload('说明.txt', raw))
        self.assertIn('DHCP', result['content'])
        self.assertIn('gb18030', result['warning'])

    def test_utf16_text_is_read_locally(self):
        raw = '网络课程中的 TCP 确认机制与 UDP 差异说明。'.encode('utf-16')
        result = extract_document(upload('utf16.txt', raw))
        self.assertIn('TCP', result['content'])
        self.assertIn('utf-16', result['warning'])

    def test_invalid_or_binary_files_are_rejected(self):
        for filename, raw in [('tool.exe', b'x'), ('empty.docx', b'not a zip')]:
            with self.assertRaises(IntegrationError):
                extract_document(upload(filename, raw))


if __name__ == '__main__':
    unittest.main()
