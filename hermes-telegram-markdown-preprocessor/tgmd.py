"""Pure-function Markdown normalizer for Telegram's rich-message parser. Every rule was checked
against Telegram itself (sendRichMessage): the input shape mis-parses, the output shape parses."""
from __future__ import annotations

import re

FENCE = re.compile(r'^(\s{0,3})(`{3,}|~{3,})(.*)$')
TABLE_RULE = re.compile(r'^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$')
HR = re.compile(r'^\s{0,3}([-*_])(\s*\1){2,}\s*$')
BULLET = re.compile(r'^\s{0,3}[-*+]\s+\S')
ORDERED = re.compile(r'^\s{0,3}\d{1,3}[.)]\s+\S')
QUOTE = re.compile(r'^\s{0,3}>')
HEADING = re.compile(r'^\s{0,3}#{1,6}(\s|$)')
HASH_START = re.compile(r'^(\s{0,3})#(?=[^\s#])')
TAG = re.compile(r'<(/?)([A-Za-z][\w:.-]*)([^<>\n]*)>')
DUNDER = re.compile(r'(?<![\w\\])__([a-z][a-z0-9_]*?)__(?!\w)')
LONE_STAR = re.compile(r'(?<=\S) \* (?=\S)')
CODE_SPAN = re.compile(r'(`+)(.+?)\1')
PROTECTED = re.compile(r'(`+).+?\1|https?://\S+|\[[^\]\n]*\]\([^)\n]*\)')
# Inline tags Telegram renders; anything else between <> is stripped silently, so it gets escaped.
KNOWN_TAGS = {'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'code', 'pre', 'sub', 'sup', 'mark',
              'a', 'br', 'details', 'summary', 'tg-spoiler', 'tg-emoji', 'blockquote', 'span', 'kbd', 'img'}


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    return re.split(r'(?<!\\)\|', CODE_SPAN.sub(lambda m: m.group(0).replace('|', '\0'), s))


def _rule_for(header: str, rule: str) -> str:
    n = len(_cells(header))
    old = [c.strip() for c in _cells(rule)]
    if len(old) == n:
        return rule
    cols = [old[i] if i < len(old) and old[i] else '---' for i in range(n)]
    return '| ' + ' | '.join(cols) + ' |'


def _inline(text: str) -> str:
    """Escape <placeholders>, dunder names and lone asterisks outside code spans."""
    out, pos = [], 0
    for m in PROTECTED.finditer(text):
        out.append(_inline_plain(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_inline_plain(text[pos:]))
    return ''.join(out)


def _inline_plain(s: str) -> str:
    def tag(m):
        name, rest = m.group(2).lower(), m.group(3)
        if name in KNOWN_TAGS or '://' in m.group(0) or '@' in m.group(0) or name in ('http', 'https', 'mailto'):
            return m.group(0)
        return '&lt;' + m.group(0)[1:-1] + '&gt;'
    s = TAG.sub(tag, s)
    s = DUNDER.sub(lambda m: '`' + m.group(0) + '`', s)
    return LONE_STAR.sub(' \\* ', s)


def _blank(out: list[str]) -> None:
    if out and out[-1].strip():
        out.append('')


def normalize(text: str) -> str:
    lines = text.replace('\r\n', '\n').split('\n')
    out: list[str] = []
    fence = None          # (char, length) while inside a fenced block
    block = None          # 'table' | 'list' | 'quote' | None: the open block a plain line would leak into
    gap = False           # a divider was just written: the next non-blank line needs a blank line above it
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ''
        m = FENCE.match(line)
        if fence:
            if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= fence[1] and not m.group(3).strip():
                line = m.group(1) + '`' * max(3, fence[1]) if fence[0] == '~' else line
                fence = None
            out.append(line)
            i += 1
            continue
        if m:
            fence = (m.group(2)[0], len(m.group(2)))
            if block == 'list' and not line.startswith(' '):
                _blank(out)
            block = None
            out.append(m.group(1) + '`' * max(3, fence[1]) + m.group(3) if fence[0] == '~' else line)
            i += 1
            continue
        stripped = line.strip()
        if gap and stripped:
            _blank(out)
        gap = False
        if not stripped:
            block = None
            out.append(line)
            i += 1
            continue
        if '|' in line and TABLE_RULE.match(nxt) and block != 'table':
            _blank(out)
            out.append(_inline(line))
            out.append(_rule_for(line, nxt))
            block = 'table'
            i += 2
            continue
        if block == 'table':
            if '|' in line and not HR.match(line):
                out.append(_inline(line))
                i += 1
                continue
            _blank(out)
            block = None
        if HR.match(line) and not (stripped.startswith(('-', '*', '+')) and BULLET.match(line)):
            _blank(out)
            out.append(stripped)
            gap, block = True, None
            i += 1
            continue
        if BULLET.match(line) or ORDERED.match(line):
            prev = out[-1] if out else ''
            # Only an ordered list that starts above 1 fails to interrupt a paragraph ("Шаги:\n2. второй").
            late_start = ORDERED.match(line) and ORDERED.match(nxt) and not re.match(r'^\s{0,3}1[.)]\s', line)
            if prev.strip() and block not in ('list', 'quote') and late_start:
                _blank(out)
            if block == 'quote':
                _blank(out)
            block = 'list'
            out.append(_inline(line))
            i += 1
            continue
        if QUOTE.match(line):
            if block == 'list':
                _blank(out)
            block = 'quote'
            out.append(_inline(line))
            i += 1
            continue
        line = HASH_START.sub(r'\1\\#', line)  # "#89 closed" is an issue ref, not a heading
        if block in ('list', 'quote') and not line.startswith((' ', '\t')):
            _blank(out)
            block = None
        elif block == 'list':
            pass
        out.append(_inline(line))
        i += 1
    if fence:
        out.append('```')
    return '\n'.join(out)
