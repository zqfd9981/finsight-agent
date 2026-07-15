import json
from pathlib import Path

f = Path(r'var/data/parsed_filings/002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2/elements.jsonl')
# 看 p187-p190 的所有元素
for line in f.open(encoding='utf-8'):
    el = json.loads(line)
    if el.get('page_start') in (187, 188, 189, 190):
        text = (el.get('text') or '')[:80]
        etype = el.get('element_type')
        print(f'  p{el["page_start"]} type={etype} text={text}')
