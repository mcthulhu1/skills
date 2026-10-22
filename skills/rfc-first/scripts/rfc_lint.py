#!/usr/bin/env python3
"""Structural hints for RFCs (Python 3.9+, stdlib only).

python3 rfc_lint.py [--config <rfc-lint.json>] <rfc.md> [<rfc.md> ...]
Exit 1: ERROR (no basic structure / a real spec link is broken / a bad config / I/O).
Exit 0: OK or WARN. A fixed set of sections and a next step are not required.
Exit 2: no file given (usage).
Section headings and header fields are matched in English, as in references/rfc-template.md,
plus the team's own words from rfc-lint.json next to the RFC or from --config (references/rfc-lint-config.md).
Parses ATX headings and plain Markdown links; not a full CommonMark parser.
Does not check what the evidence means, completeness of requirements or owner approval.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

CONFIG_NAME = 'rfc-lint.json'
CONFIG_KEYS = {
    'sections': ('goal', 'facts', 'next_step'),
    'fields': ('status', 'source'),
    'proof_column': None,
    'hedges': None,
}
# English words; the team's words from the config are added to them.
ENGLISH = {
    'goal': r"goal|scope|summary|problem|context|requirement|contract",
    'facts': r"fact|proof|evidence|current behavio|how .*works|diagnos",
    'next_step': r"next step",
    'status': r"(?:status|decision|implementation and verification)\b",
    'source': r"source(?: of requirements)?|requirements(?: verbatim)?|verbatim requirements|spec(?:ification)?",
    'proof_column': r"proof|evidence|source|verified by",
    'hedges': r"\b(?:probably|apparently|presumably|most likely|seems to|it seems)\b",
}
REQUIRED = {'goal/contract': 'goal', 'facts/proof': 'facts'}  # missing section name -> pattern key
COLON = '[:\uff1a]'  # the full-width colon is the norm in Chinese and Japanese
LINK = re.compile(r'(?<!!)\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+["\'][^\n]*?["\'])?\s*\)')
REF_DEF = re.compile(r'^\s{0,3}\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))')
INLINE_CODE = re.compile(r'(`+)(.*?)\1')


def load_config(path):
    """The team's words: {"sections": {"goal": [...]}, "fields": {...}, "proof_column": [...], "hedges": [...]}."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f'{path}: {exc}') from None
    words = {}

    def word_list(value, where):
        if not isinstance(value, list) or not value or not all(isinstance(w, str) and w.strip() for w in value):
            raise ValueError(f'{path}: {where} must be a non-empty list of non-empty strings')
        return [w.strip() for w in value]

    if not isinstance(data, dict):
        raise ValueError(f'{path}: the top level must be an object')
    for key, value in data.items():
        if key not in CONFIG_KEYS:
            raise ValueError(f'{path}: unknown key {key!r}; allowed: {", ".join(CONFIG_KEYS)}')
        subkeys = CONFIG_KEYS[key]
        if subkeys is None:
            words[key] = word_list(value, key)
            continue
        if not isinstance(value, dict):
            raise ValueError(f'{path}: {key} must be an object')
        for sub, sub_value in value.items():
            if sub not in subkeys:
                raise ValueError(f'{path}: unknown key {key}.{sub!r}; allowed: {", ".join(subkeys)}')
            words[sub] = word_list(sub_value, f'{key}.{sub}')
    return words


def patterns(words=None):
    """English words, then the team's words as plain substrings: CJK text has no word boundaries."""
    words = words or {}

    def any_of(key, english=None):
        return '|'.join(['(?:' + (english or ENGLISH[key]) + ')'] + [re.escape(w) for w in words.get(key, [])])

    source = any_of('source')
    return {
        'goal': re.compile(any_of('goal'), re.I),
        'facts': re.compile(any_of('facts'), re.I),
        'next_step': re.compile(any_of('next_step'), re.I),
        'hedges': re.compile(any_of('hedges'), re.I),
        'proof_column': re.compile(any_of('proof_column'), re.I),
        'status': re.compile(r"^\s*(?:\*\*)?(?:" + any_of('status') + ")", re.I | re.M),
        'source': re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:" + any_of('source', '(?:' + ENGLISH['source'] + r')\b')
                             + r")[^:\uff1a]*" + COLON, re.I),
        # Source field in the middle of a line: "Status: ... Spec: `docs/rfc/spec/X.md`".
        'source_inline': re.compile(r"(?<!\w)(?:" + source + r")[^:\uff1a`\n]{0,40}" + COLON
                                    + r"\s*(`+)([^`\n]+?)\1", re.I),
    }


DEFAULT = patterns()


def visible_lines(lines):
    """Mask fenced/indented code and HTML comments, preserving line positions."""
    result, fence = [], None
    for line in lines:
        if fence:
            close = re.match(r'^ {0,3}(' + re.escape(fence[0]) + r'{%d,})\s*$' % fence[1], line)
            if close:
                fence = None
            result.append("")
            continue
        opening = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if opening and not (opening[1][0] == '`' and '`' in opening[2]):
            fence = (opening[1][0], len(opening[1]))
            result.append("")
        elif line.startswith('    ') or line.startswith('\t'):
            result.append("")
        else:
            result.append(line)
    text = '\n'.join(result)
    text = re.sub(r'<!--[\s\S]*?(?:-->|\Z)', lambda m: re.sub(r'[^\n]', ' ', m[0]), text)
    return text.split('\n')


def headings(lines):
    found = []
    for i, line in enumerate(visible_lines(lines)):
        m = re.match(r'^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$', line)
        if m:
            found.append((i, len(m[1]), m[2].strip()))
    return found


def section_body(lines, heads, idx):
    start, level, _ = heads[idx]
    end = next((h[0] for h in heads[idx + 1:] if h[1] <= level), len(lines))
    return lines[start + 1:end]


def spec_references(lines, rx=DEFAULT):
    targets, definitions = set(), {}
    plain = [INLINE_CODE.sub('', line) for line in lines]
    for line in plain:
        d = REF_DEF.match(line)
        if d:
            definitions[d[1].strip().casefold()] = d[2] or d[3]
    for line, clean in zip(lines, plain):
        targets.update((a or b, 'markdown') for a, b in LINK.findall(clean))
        if not REF_DEF.match(clean):
            for label, ref in re.findall(r'\[([^\]]+)\]\[([^\]]*)\]', clean):
                key = (ref or label).strip().casefold()
                if key in definitions:
                    targets.add((definitions[key], 'markdown'))
        # RFCs often use an explicit source field with a backticked path.
        # An arbitrary inline-code example elsewhere is not a source link.
        if rx['source'].match(line):
            targets.update((m[2], 'source') for m in INLINE_CODE.finditer(line))
        targets.update((m[2].strip(), 'source') for m in rx['source_inline'].finditer(line))
    result = set()
    for target, kind in targets:
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        path = unquote(parsed.path)
        if re.search(r'(?:^|/)spec/', path) and path.lower().endswith('.md'):
            result.add((path, kind))
    return result


def spec_targets(lines, rx=DEFAULT):
    return {target for target, _ in spec_references(lines, rx)}


def table_cells(line):
    return [c.strip() for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]


def lint(path, config=None):
    """config: an explicit rfc-lint.json; by default the one next to the RFC, if any."""
    path = Path(path)
    errors, warns = [], []
    if config is None and (path.resolve().parent / CONFIG_NAME).is_file():
        config = path.resolve().parent / CONFIG_NAME
    try:
        rx = patterns(load_config(config)) if config is not None else DEFAULT
    except ValueError as exc:
        return [f'bad config {exc}'], []
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    visible = visible_lines(lines)
    heads = headings(lines)
    first = next((i for i, line in enumerate(visible) if line.strip()), None)
    if first is None or not any(i == first and level == 1 for i, level, _ in heads):
        errors.append("the document must start with a '# <ID/topic>' heading")
    header = '\n'.join(visible[:15])
    if not rx['status'].search(header):
        warns.append('the header has no short decision/implementation status')
    if not any(rx['source'].match(line) for line in visible) and not spec_targets(visible, rx):
        warns.append('no link to the verbatim spec (spec/<ID>.md); it is required when the task has written requirements')
    for target, kind in sorted(spec_references(visible, rx)):
        folder = path.resolve().parent  # relative CLI paths must still reveal docs/rfc and rfc/
        base = folder
        # Source fields may use a project-relative path; Markdown links do not.
        # Limit this convention to docs/rfc/ and rfc/ rather than searching unrelated parents.
        if (kind == 'source' and target.startswith('docs/rfc/spec/')
                and folder.name == 'rfc' and folder.parent.name == 'docs'):
            base = folder.parent.parent
        elif kind == 'source' and target.startswith('rfc/spec/') and folder.name == 'rfc':
            base = folder.parent
        if not (base / target).is_file():
            error = f'the spec link points to a missing file: {target}'
            if error not in errors:
                errors.append(error)
    titles = [title for _, level, title in heads if level >= 2]
    for name, key in REQUIRED.items():
        if not any(rx[key].search(title) for title in titles):
            hint = '' if config else f' (headings are matched in English; other languages need {CONFIG_NAME})'
            errors.append(f'missing section: {name}{hint}')
    for idx, (_, level, title) in enumerate(heads):
        body = section_body(visible, heads, idx)
        if level >= 2 and rx['next_step'].search(title):
            items = [re.match(r'^( *)(?:[-*]|\d+[.)])\s', b) for b in body]
            items = [m for m in items if m]
            if items:
                top = min(len(m[1]) for m in items)
                if sum(len(m[1]) == top for m in items) > 1:
                    warns.append(f"'{title}': several nearest steps; single out the first dependent one")
        if level < 2 or not rx['facts'].search(title):
            continue
        if not any(b.strip() for b in body):
            warns.append(f"'{title}': empty facts section")
        proof_column = None
        for k, b in enumerate(body):
            if rx['hedges'].search(b):
                warns.append(f"'{title}': check that a hypothesis is not presented as a fact: {b.strip()[:80]}")
            if not b.lstrip().startswith('|'):
                proof_column = None
                continue
            cells = table_cells(b)
            if re.match(r'^\s*\|[\s:|\-]+$', b):
                continue
            if k + 1 < len(body) and re.match(r'^\s*\|[\s:|\-]+$', body[k + 1]):
                proof_column = next((j for j, cell in enumerate(cells) if rx['proof_column'].search(cell)), None)
            elif proof_column is not None and (len(cells) <= proof_column or not cells[proof_column]):
                warns.append(f"'{title}': row without proof: {cells[0][:60]}")
    return errors, warns


def utf8_when_piped():
    """Agents read the output through a pipe; a legacy code page (cp1252 on English Windows) cannot encode quoted non-ASCII text."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure') and not stream.isatty():
            stream.reconfigure(encoding='utf-8')


def main(argv):
    utf8_when_piped()
    args, config = argv[1:], None
    if '--config' in args:
        i = args.index('--config')
        if i + 1 >= len(args):
            print(__doc__.strip())
            return 2
        config, args = args[i + 1], args[:i] + args[i + 2:]
    if not args:
        print(__doc__.strip())
        return 2
    failed = False
    for arg in args:
        path = Path(arg)
        try:
            errors, warns = lint(path, config)
        except (OSError, UnicodeError, ValueError) as exc:
            errors, warns = [f'cannot check the file: {exc}'], []
        status = 'FAIL' if errors else ('WARN' if warns else 'OK')
        print(f'{status} {path}')
        for e in errors:
            print(f'  ERROR {e}')
        for w in warns:
            print(f'  WARN  {w}')
        failed |= bool(errors)
    return int(failed)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
