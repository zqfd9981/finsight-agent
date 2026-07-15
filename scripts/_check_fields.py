import json
from pathlib import Path

f = Path(r'var/data/parsed_filings/002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2/elements.jsonl')
line = f.open(encoding='utf-8').readline()
el = json.loads(line)
print('keys:', list(el.keys()))
print('full:', json.dumps(el, ensure_ascii=False, indent=2)[:500])
