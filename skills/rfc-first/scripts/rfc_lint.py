#!/usr/bin/env python3
"""Structural hints for RFCs (Python 3.9+, stdlib only).

python3 rfc_lint.py <rfc.md> [<rfc.md> ...]
Exit 1: ERROR (no basic structure / a real spec link is broken / I/O).
Exit 0: OK or WARN. A fixed set of sections and a next step are not required.
Exit 2: no file given (usage).
Section headings are matched in English, as in references/rfc-template.md.
Parses ATX headings and plain Markdown links; not a full CommonMark parser.
Does not check what the evidence means, completeness of requirements or owner approval.
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REQUIRED = {
    "goal/contract": r"goal|scope|summary|problem|context|requirement|contract",
    "facts/proof": r"fact|proof|evidence|current behavio|how .*works|diagnos",
}
NEXT_STEP = re.compile(r"next step", re.I)
HEDGE = re.compile(r"\b(probably|apparently|presumably|most likely|seems to|it seems)\b", re.I)
SOURCE_WORDS = r"source(?: of requirements)?|requirements(?: verbatim)?|verbatim requirements|spec(?:ification)?"
SOURCE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:" + SOURCE_WORDS + r")\b[^:]*:", re.I)
# Source field in the middle of a line: "Status: ... Spec: `docs/rfc/spec/X.md`".
SOURCE_INLINE = re.compile(r"(?<!\w)(?:" + SOURCE_WORDS + r")[^:`\n]{0,40}:\s*(`+)([^`\n]+?)\1", re.I)
STATUS = re.compile(r"^\s*(?:\*\*)?(?:status|decision|implementation and verification)\b", re.I | re.M)
PROOF_COLUMN = re.compile(r"proof|evidence|source|verified by", re.I)
LINK = re.compile(r'(?<!!)\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+["\'][^\n]*?["\'])?\s*\)')
REF_DEF = re.compile(r'^\s{0,3}\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))')
INLINE_CODE = re.compile(r'(`+)(.*?)\1')


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


def spec_references(lines):
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
        if SOURCE.match(line):
            targets.update((m[2], 'source') for m in INLINE_CODE.finditer(line))
        targets.update((m[2].strip(), 'source') for m in SOURCE_INLINE.finditer(line))
    result = set()
    for target, kind in targets:
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        path = unquote(parsed.path)
        if re.search(r'(?:^|/)spec/', path) and path.lower().endswith('.md'):
            result.add((path, kind))
    return result


def spec_targets(lines):
    return {target for target, _ in spec_references(lines)}


def table_cells(line):
    return [c.strip() for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]


def lint(path):
    path = Path(path)
    errors, warns = [], []
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    visible = visible_lines(lines)
    heads = headings(lines)
    first = next((i for i, line in enumerate(visible) if line.strip()), None)
    if first is None or not any(i == first and level == 1 for i, level, _ in heads):
        errors.append("the document must start with a '# <ID/topic>' heading")
    header = '\n'.join(visible[:15])
    if not STATUS.search(header):
        warns.append('the header has no short decision/implementation status')
    if not any(SOURCE.match(line) for line in visible) and not spec_targets(visible):
        warns.append('no link to the verbatim spec (spec/<ID>.md); it is required when the task has written requirements')
    for target, kind in sorted(spec_references(visible)):
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
    titles = [title.lower() for _, level, title in heads if level >= 2]
    for name, rx in REQUIRED.items():
        if not any(re.search(rx, title) for title in titles):
            errors.append(f'missing section: {name}')
    for idx, (_, level, title) in enumerate(heads):
        body = section_body(visible, heads, idx)
        if level >= 2 and NEXT_STEP.search(title):
            items = [re.match(r'^( *)(?:[-*]|\d+[.)])\s', b) for b in body]
            items = [m for m in items if m]
            if items:
                top = min(len(m[1]) for m in items)
                if sum(len(m[1]) == top for m in items) > 1:
                    warns.append(f"'{title}': several nearest steps; single out the first dependent one")
        if level < 2 or not re.search(REQUIRED['facts/proof'], title, re.I):
            continue
        if not any(b.strip() for b in body):
            warns.append(f"'{title}': empty facts section")
        proof_column = None
        for k, b in enumerate(body):
            if HEDGE.search(b):
                warns.append(f"'{title}': check that a hypothesis is not presented as a fact: {b.strip()[:80]}")
            if not b.lstrip().startswith('|'):
                proof_column = None
                continue
            cells = table_cells(b)
            if re.match(r'^\s*\|[\s:|\-]+$', b):
                continue
            if k + 1 < len(body) and re.match(r'^\s*\|[\s:|\-]+$', body[k + 1]):
                proof_column = next((j for j, cell in enumerate(cells) if PROOF_COLUMN.search(cell)), None)
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
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    failed = False
    for arg in argv[1:]:
        path = Path(arg)
        try:
            errors, warns = lint(path)
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
