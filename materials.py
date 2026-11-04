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
    if not isinstance(content, str) or not 20 <= len(content) <= 3200000:
        raise IntegrationError('请导入 20 至 800000 字符的资料，过长时按章节拆分')
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
    if not 20 <= len(content.strip()) <= 800000:
        raise IntegrationError('有效资料需要 20 至 800000 个字符，请按章节导入')
    if type(data.get('generate', False)) is not bool: raise IntegrationError('自动整理选项不正确')
    return title.strip(), filename, content
