"""Bounded, local PDF text extraction. Never executes attachments or fetches URLs."""
import base64
import binascii
import json
import os
import subprocess
import sys
import threading
from pathlib import Path, PurePosixPath

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_PAGES = 300
MAX_TEXT = 800000
IMPORT_LOCK = threading.Lock()


def read_pdf_upload(data):
    """Run the native parser in a time-bounded worker, isolated from web threads."""
    from integrations import IntegrationError
    if not IMPORT_LOCK.acquire(blocking=False):
        raise IntegrationError('正在读取另一份 PDF，请稍后重试')
    try:
        root = Path(__file__).resolve().parent
        candidates = [root / '.venv/Scripts/python.exe', root / '.venv/bin/python', Path(sys.executable),
                      Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3']
        if os.environ.get('STUDY_ATLAS_PDF_PYTHON'):
            candidates.insert(0, Path(os.environ['STUDY_ATLAS_PDF_PYTHON']))
        for executable in dict.fromkeys(candidates):
            if not executable.is_file(): continue
            check = subprocess.run([str(executable), '-c', 'import pypdfium2'], capture_output=True, timeout=10)
            if check.returncode: continue
            result = subprocess.run([str(executable), str(root / 'pdf_import.py'), '--worker'],
                                    input=json.dumps(data, ensure_ascii=False).encode(), capture_output=True, timeout=60)
            if result.returncode:
                raise IntegrationError('PDF 读取未完成，请检查文件或按章节拆分')
            response = json.loads(result.stdout)
            if response.get('error'): raise IntegrationError(response['error'])
            return response
        raise IntegrationError('尚未安装 PDF 读取组件，请运行 python3 -m pip install -r requirements.txt')
    except subprocess.TimeoutExpired:
        raise IntegrationError('PDF 读取超时，请按章节拆分后导入')
    except (OSError, ValueError) as error:
        if isinstance(error, IntegrationError): raise
        raise IntegrationError('PDF 读取失败，请检查依赖和文件')
    finally:
        IMPORT_LOCK.release()


def extract_pdf(data):
    from integrations import IntegrationError
    filename = data.get('filename', '')
    encoded = data.get('base64', '')
    if not isinstance(filename, str) or len(filename) > 255:
        raise IntegrationError('PDF 文件名不正确')
    filename = PurePosixPath(filename.replace('\\', '/')).name
    if not filename.lower().endswith('.pdf'):
        raise IntegrationError('请选择 PDF 文件')
    if not isinstance(encoded, str) or not encoded or len(encoded) > 4 * ((MAX_PDF_BYTES + 2) // 3):
        raise IntegrationError('PDF 最多 8 MB，请按章节拆分')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise IntegrationError('PDF 上传编码不正确')
    if len(raw) > MAX_PDF_BYTES or not raw.startswith(b'%PDF-'):
        raise IntegrationError('文件不是有效 PDF，或超过 8 MB')
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise IntegrationError('尚未安装 PDF 读取组件，请运行 python3 -m pip install -r requirements.txt')
    document = None
    try:
        document = pdfium.PdfDocument(raw)
        count = len(document)
        if not 1 <= count <= MAX_PAGES:
            raise IntegrationError('PDF 最多 300 页，请按章节拆分')
        parts, empty, size = [], [], 0
        for index in range(count):
            page = document[index]
            textpage = None
            try:
                textpage = page.get_textpage()
                # Check before extraction to avoid allocating an unbounded string.
                if textpage.count_chars() > MAX_TEXT - size:
                    raise IntegrationError('PDF 正文超过 80 万字符，请按章节拆分')
                text = textpage.get_text_bounded().replace('\x00', '').strip()
            finally:
                if textpage is not None: textpage.close()
                page.close()
            if not text:
                empty.append(index + 1)
                continue
            part = '[PDF 第 %d 页]\n%s' % (index + 1, text)
            size += len(part) + 2
            if size > MAX_TEXT:
                raise IntegrationError('PDF 正文超过 80 万字符，请按章节拆分')
            parts.append(part)
        if sum(len(p.split('\n', 1)[1]) for p in parts) < 20:
            raise IntegrationError('未读取到足够正文：扫描版 PDF 请先 OCR，或导入可选择文字的 PDF；不会依据文件名编造笔记')
        warning = ('有 %d 页未读取到文字，可能是空白、图片或扫描页；这些页面需要 OCR 后补充，AI 不会理解其中的图表。' % len(empty)) if empty else '已读取文字；PDF 中的图片、公式和表格排版请对照原件核对。'
        return {'content': '\n\n'.join(parts), 'filename': PurePosixPath(filename).stem + '.md',
                'originalFilename': filename, 'title': PurePosixPath(filename).stem,
                'pages': count, 'emptyPages': empty, 'warning': warning}
    except IntegrationError:
        raise
    except Exception:
        raise IntegrationError('无法读取 PDF，文件可能损坏或有密码；请解锁后重新导入')
    finally:
        if document is not None: document.close()


if __name__ == '__main__':
    try:
        result = extract_pdf(json.load(sys.stdin))
    except ValueError as error:
        result = {'error': str(error)}
    print(json.dumps(result, ensure_ascii=False))
