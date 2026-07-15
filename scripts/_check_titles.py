import json
from pathlib import Path

f = Path(r'var/data/parsed_filings/002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2/elements.jsonl')
titles = []
notes_start = []
for line in f.open(encoding='utf-8'):
    el = json.loads(line)
    if el.get('type') == 'title':
        titles.append(el)
    if '财务报表主要项目注释' in (el.get('text') or ''):
        notes_start.append(el)

print(f'titles: {len(titles)}')
print(f'notes_start: {len(notes_start)}')
for t in titles[:20]:
    print(f'  p{t["page_start"]}: {t["text"][:60]}')
print('...')
for t in notes_start:
    print(f'  NOTES START p{t["page_start"]}: {t["text"][:60]}')
