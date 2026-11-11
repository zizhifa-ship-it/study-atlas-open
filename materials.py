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

AI_DIGEST_LIMIT = 24000
_PRIMARY_MARKER = re.compile(
    r'^[ \t]*(?:P\d+\s+Lecture\s+\d+[^\n]{0,100}|Lecture\s+\d+[^\n]{0,100}|'
    r'#{1,6}\s+[^\n]{1,100}|第\s*[0-9一二三四五六七八九十]+\s*[讲章课][^\n]{0,100}|'
    r'Chapter\s+\d+[^\n]{0,100}|Week\s+\d+[^\n]{0,100})[ \t]*$',
    re.IGNORECASE | re.MULTILINE,
)
_FALLBACK_MARKER = re.compile(
    r'^[ \t]*(?:内容摘要|核心结论|章节导航|课程目标|学习目标|总结)[ \t]*$',
    re.IGNORECASE | re.MULTILINE,
)


def build_ai_digest(text, budget=AI_DIGEST_LIMIT):
    """Build a bounded, local outline for AI without sending the full source.

    PDF/TXT exports often start with a course summary and then repeat one
    ``内容摘要`` / ``要点`` block per lecture.  This extractor keeps that front
    matter, one bounded block around each detected section heading, a few
    evenly spaced samples and the tail.  It runs locally and costs zero model
    tokens.  The returned metadata explicitly records the reduced coverage.
    """
    from integrations import IntegrationError
    if not isinstance(text, str) or len(text.strip()) < 20:
        raise IntegrationError('辅助资料没有足够正文')
    normalized = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    original = len(normalized)
    if original <= budget:
        return normalized, {'method': 'local-outline-v1', 'originalCharacters': original,
                            'digestCharacters': len(normalized), 'coverage': 'full'}
    def marker_starts(pattern, minimum_gap):
        found = []
        for match in pattern.finditer(normalized):
            start = match.start()
            if start < 5000:
                continue
            line_end = normalized.find('\n', start)
            line = normalized[start:line_end if line_end >= 0 else len(normalized)]
            if len(line) > 100:
                continue
            if any(abs(start - previous) < minimum_gap for previous in found):
                continue
            found.append(start)
            if len(found) >= 14:
                break
        return found
    markers = marker_starts(_PRIMARY_MARKER, 800)
    if len(markers) < 2:
        markers = marker_starts(_FALLBACK_MARKER, 800)
    front = normalized[:6000]
    tail = normalized[-1200:]
    section_budget = max(700, (budget - len(front) - len(tail) - 900) // max(1, len(markers)))
    parts = ['[开头与总览]\n' + front]
    for index, start in enumerate(markers, 1):
        block = normalized[start:start + min(2600, section_budget)]
        cut = block.find('全文文稿')
        if cut >= 240:
            block = block[:cut]
        parts.append('[章节线索 %d/%d]\n%s' % (index, len(markers), block.rstrip()))
    used = sum(len(part) + 2 for part in parts)
    if used < budget - 1800:
        remaining = budget - used
        bands = 4
        size = max(250, min(900, remaining // (bands + 1)))
        for index in range(bands):
            start = min(max(0, original - size - 1), int(original * index / bands))
            parts.append('[全篇抽样 %d/%d]\n%s' % (index + 1, bands, normalized[start:start + size]))
    if sum(len(part) + 2 for part in parts) < budget - 1000:
        parts.append('[结尾]\n' + tail)
    header = ('【本地辅助结构摘录】原文 %d 字符；为节省 token，仅发送本机抽取的开头、章节摘要、'
              '抽样与结尾，不是全文。不得把未出现在摘录中的细节写成课程原文。\n\n' % original)
    digest = header + '\n\n'.join(parts)
    if len(digest) > budget:
        digest = digest[:budget - 1].rstrip() + '…'
    return digest, {'method': 'local-outline-v1', 'originalCharacters': original,
                    'digestCharacters': len(digest), 'coverage': 'outline'}
