"""本地文字课程：保留普通文本和 Markdown 中的代码，不伪造视频链接。"""
import re
from pathlib import PurePosixPath

LOCAL_MATERIAL = re.compile(r'^studyatlas://material/[a-f0-9]{32}$')


def is_material_url(value):
    return isinstance(value, str) and bool(LOCAL_MATERIAL.fullmatch(value))


def parse_material(data):
    from integrations import IntegrationError
    title, content = data.get('title'), data.get('content')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 500:
        raise IntegrationError('请填写 1 至 500 字的课程标题')
    if not isinstance(content, str) or not 20 <= len(content) <= 3000000:
        raise IntegrationError('请导入 20 至 3000000 字符的资料，过长时按章节拆分')
    filename = data.get('filename') or '课堂资料.txt'
    if not isinstance(filename, str) or len(filename) > 255: raise IntegrationError('文件名不正确')
    filename = PurePosixPath(filename.replace('\\', '/')).name
    ext = PurePosixPath(filename).suffix.lower()
    if ext in {'.srt', '.vtt', '.json', '.json3'}:
        from transcript_sources import parse_transcript
        content = parse_transcript(content, ext)
    elif ext in {'.txt', '.md', '.markdown'}:
        content = content.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    else:
        raise IntegrationError('支持 TXT、Markdown、SRT、VTT、JSON3 文字资料；PDF 请先提取文字')
    if not 20 <= len(content.strip()) <= 3000000:
        raise IntegrationError('有效资料需要 20 至 3000000 个字符，请按章节导入')
    if type(data.get('generate', False)) is not bool: raise IntegrationError('自动整理选项不正确')
    return title.strip(), filename, content


def combine_material(existing, incoming, filename, mode='append'):
    """Append or replace a local supplement without silently dropping text.

    Returning ``added=False`` for an exact repeat lets callers avoid an AI call
    and prevents duplicated long transcripts.  APPEND keeps the existing source
    byte-for-byte, which also preserves reusable long-video chunk caches.
    """
    from integrations import IntegrationError
    if mode not in {'append', 'replace'}:
        raise IntegrationError('补充方式不正确')
    if not isinstance(existing, str) or not isinstance(incoming, str):
        raise IntegrationError('学习资料格式不正确')
    if mode == 'append' and incoming.strip() and incoming.strip() in existing:
        return existing, 0, True
    if mode == 'replace' and incoming.strip() == existing.strip():
        return existing, 0, True
    if not existing.strip():
        combined = incoming
    elif mode == 'replace':
        combined = incoming
    else:
        safe_name = re.sub(r'[\r\n\[\]]+', ' ', PurePosixPath(filename.replace('\\', '/')).name).strip()[:160] or '补充文件'
        marker = '\n\n[补充资料：%s]\n' % safe_name
        combined = existing.rstrip() + marker + incoming.strip()
    if len(combined) > 3000000:
        raise IntegrationError('现有资料与补充文件合计超过 300 万字符，请精简或分课程导入；原资料未覆盖')
    return combined, len(combined) - len(existing), False
