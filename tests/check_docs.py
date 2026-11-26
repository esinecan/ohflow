"""Check documentation links, skill length, the five glossary lessons, the glossary sync,
the CONTRIBUTING.md test case count of each test matrix and the preflight check table."""
from pathlib import Path
from types import SimpleNamespace
import json
import re
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'docs'))
sys.path.insert(0, str(ROOT / 'scripts'))
import glossary_sync  # noqa: E402
from ohflow import preflight  # noqa: E402
from ohflow.rollcall import MATRICES  # noqa: E402


def preflight_check_names():
    """Every check name a `FAIL` line of `preflight` can print, a harness executor's as
    `<name> harness executor`."""
    no_workflow = SimpleNamespace(all_workspaces=lambda: [], steps=lambda: [], worktrees=[])
    checks = [preflight.bash_check(), preflight.workflow_load_check(''),
              *preflight.workflow_checks(no_workflow, None),
              *preflight.harness_executor_checks(['<name>'], None)]
    return [check.need for check in checks]


def preflight_table_errors(reference):
    """The check table of `preflight` in references/ohflow.md has a row for every check
    preflight.py builds, and no other row."""
    section = re.search(r'(?ms)^`preflight` runs each check as data.*?\n\n(\|.*?)(?=\n\n|\Z)', reference)
    rows = re.findall(r'(?m)^\| `([^`]+)` \|', section[1] if section else '')
    if not rows:
        return ['references/ohflow.md: no check table follows "`preflight` runs each check as data"']
    names = preflight_check_names()
    errors = [f'references/ohflow.md: the preflight check table has no row for `{name}`'
              for name in names if name not in rows]
    errors += [f'references/ohflow.md: the preflight check table names `{row}`, '
               f'which preflight.py does not build' for row in rows if row not in names]
    return errors


def matrix_count_errors(readme):
    """The Matrices table of CONTRIBUTING.md names every test matrix with its number of test cases."""
    section = re.search(r'(?ms)^### Matrices\n(.*?)(?=^#{1,6} |\Z)', readme)
    rows = dict(re.findall(r'(?m)^\| `([\w-]+)` \| (\d+) \|', section[1] if section else ''))
    errors = []
    for name, cases in MATRICES.items():
        if name not in rows:
            errors.append(f'CONTRIBUTING.md: the Matrices table has no row for `{name}`')
        elif int(rows[name]) != len(cases):
            errors.append(f'CONTRIBUTING.md: the Matrices table gives `{name}` {rows[name]} test cases; '
                          f'MATRICES holds {len(cases)}')
    for name in rows:
        if name not in MATRICES:
            errors.append(f'CONTRIBUTING.md: the Matrices table names `{name}`, which MATRICES does not hold')
    return errors


def check():
    errors = []
    files = [ROOT / 'SKILL.md', ROOT / 'README.md', ROOT / 'CONTRIBUTING.md', ROOT / 'CONTEXT.md', ROOT / 'docs/glossary.md',
             *sorted((ROOT / 'references').glob('*.md'))]
    links = 0
    for file in files:
        text = file.read_text(encoding='utf-8')
        # Source examples are not document navigation.
        text = re.sub(r'(?ms)^```.*?^```[^\n]*', '', text)
        for match in re.finditer(r'\[[^\]\n]*\]\(([^)\n]+)\)', text):
            ref = match[1].strip().split(' "', 1)[0].strip('<>')
            if re.match(r'^[a-zA-Z][\w+.-]*:', ref) or ref.startswith(('~/', '/', '<')):
                continue
            target, _, anchor = unquote(ref).partition('#')
            path = file.parent / target if target else file
            links += 1
            if not path.exists():
                errors.append(f'{file.relative_to(ROOT)}: missing {ref}')
            elif anchor and path.suffix == '.md':
                headings = re.findall(r'(?m)^#{1,6} +(.+)$', path.read_text(encoding='utf-8'))
                slugs = [re.sub(r'[^\w\- ]', '', h.lower()).replace(' ', '-') for h in headings]
                if anchor not in slugs:
                    errors.append(f'{file.relative_to(ROOT)}: missing heading {ref}')
    words = len((ROOT / 'SKILL.md').read_text(encoding='utf-8').split())
    if words >= 900:
        errors.append(f'SKILL.md has {words} words; must be below 900')
    text = (ROOT / 'docs/glossary-map.html').read_text(encoding='utf-8')
    data = json.loads(re.search(r'<script type="application/json" id="graph-data">(.*?)</script>', text, re.S)[1])
    names = {n['name'] for n in data['nodes']}
    lessons = data.get('lessons', [])
    if len(lessons) != 5:
        errors.append(f'Expected five lessons, found {len(lessons)}')
    for i, lesson in enumerate(lessons, 1):
        for key in ('title', 'lead', 'contrast', 'prompt', 'answer', 'terms'):
            if not lesson.get(key):
                errors.append(f'Lesson {i} lacks {key}')
        for term in lesson['terms']:
            if term['name'] not in names or not term['example']:
                errors.append(f'Lesson {i}: undefined term or missing example: {term}')
    for edge in data['edges']:
        if edge['from'] not in names or edge['to'] not in names:
            errors.append(f'Map edge references an undefined term: {edge}')
    errors += matrix_count_errors((ROOT / 'CONTRIBUTING.md').read_text(encoding='utf-8'))
    errors += preflight_table_errors((ROOT / 'references/ohflow.md').read_text(encoding='utf-8'))
    errors += glossary_sync.run(write=False)
    return errors, links, words, len(lessons)


if __name__ == '__main__':
    errors, links, words, lessons = check()
    for error in errors:
        print('FAIL', error)
    print(f'{"FAIL" if errors else "PASS"}: {links} relative links, {words} skill words, {lessons} glossary lessons')
    raise SystemExit(bool(errors))
