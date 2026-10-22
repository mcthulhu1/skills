#!/usr/bin/env python3
"""Checks the plugin manifests, skill front matter and icon (Python 3.9+, stdlib only).

python3 scripts/check_manifests.py   # from the repository root; exit 1 on any problem
"""
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def front_matter(skill_md):
    text = skill_md.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None
    name = re.search(r'^name:\s*(\S+)\s*$', m[1], re.M)
    desc = re.search(r'^description:\s*>-\n((?:  .*\n?)+)', m[1] + '\n', re.M)
    return (name[1] if name else None, ' '.join(desc[1].split()) if desc else None)


def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])


def main():
    problems = []
    plugin = json.loads((ROOT / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
    market = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
    if not re.fullmatch(r'\d+\.\d+\.\d+', plugin.get('version', '')):
        problems.append('plugin.json: version must be MAJOR.MINOR.PATCH')
    if [p.get('name') for p in market.get('plugins', [])] != [plugin.get('name')]:
        problems.append('marketplace.json must list exactly the plugin named in plugin.json')
    for entry in market.get('plugins', []):
        if not (ROOT / entry.get('source', '') / '.claude-plugin/plugin.json').is_file():
            problems.append(f"marketplace.json: source {entry.get('source')!r} has no plugin.json")
    listed = set()
    for rel in plugin.get('skills', []):
        skill_dir = (ROOT / rel).resolve()
        listed.add(skill_dir)
        fm = front_matter(skill_dir / 'SKILL.md') if (skill_dir / 'SKILL.md').is_file() else None
        if fm is None:
            problems.append(f'{rel}: no SKILL.md with front matter')
            continue
        name, desc = fm
        if name != skill_dir.name:
            problems.append(f'{rel}: front matter name {name!r} must match the directory name')
        if not desc or len(desc) > 1024:
            problems.append(f'{rel}: description must be 1..1024 characters')
    for skill_md in (ROOT / 'skills').glob('*/SKILL.md'):
        if skill_md.parent.resolve() not in listed:
            problems.append(f'{skill_md.parent.name}: skill is not listed in plugin.json')
    icon = ROOT / plugin.get('icon', '')
    size = png_size(icon) if icon.is_file() else None
    if not size or size[0] != size[1] or not 512 <= size[0] <= 2048 or icon.stat().st_size > 2 * 1024 * 1024:
        problems.append('icon: must be a square PNG of 512-2048 px under 2 MB')
    for p in problems:
        print(f'ERROR {p}')
    print('FAIL' if problems else 'OK')
    return int(bool(problems))


if __name__ == '__main__':
    sys.exit(main())
