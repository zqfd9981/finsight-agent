import json
from pathlib import Path
from collections import Counter

f = Path(r'var/data/parsed_filings/002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2/elements.jsonl')
types = Counter()
notes_elements = []
for line in f.open(encoding='utf-8'):
    el = json.loads(line)
    types[el.get('type')] += 1
    if el.get('page_start') == 187:
        notes_elements.append(el)

print(f'element types: {dict(types)}')
print(f'\np187 elements ({len(notes_elements)}):')
for el in notes_elements[:15]:
    print(f'  type={el.get("type")} text={el.get("text","")[:80]}')
