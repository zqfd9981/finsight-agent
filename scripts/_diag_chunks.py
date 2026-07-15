"""检查 TCL中环 RAG 解析产物的 section_path 分布，找出 chunks=0 的原因。"""
import json
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parents[1]
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__rag"

# 统计 element_type 和 section_path 分布
elements = []
with (doc_dir / "elements.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            elements.append(json.loads(line))

print(f"总 elements: {len(elements)}")

type_counter = Counter(e.get("element_type") for e in elements)
print(f"\n=== element_type 分布 ===")
for t, cnt in type_counter.most_common():
    print(f"  {t}: {cnt}")

# section_path 分布
path_counter = Counter(tuple(e.get("section_path", [])) for e in elements)
print(f"\n=== section_path 分布（前 10）===")
for path, cnt in path_counter.most_common(10):
    print(f"  {cnt:>3} | {list(path)}")

# 空section_path 占比
empty_path_count = sum(1 for e in elements if not e.get("section_path"))
print(f"\n空 section_path: {empty_path_count} / {len(elements)}")

# 切块器只接受 paragraph/list_item/table_caption/figure_caption 作为 child
# 但 MinerU 产出的是 paragraph，应该可以
# 问题在 _should_index_section 要求 section_path 非空
# 看 paragraph 类型有多少非空 section_path
para_with_path = sum(1 for e in elements if e.get("element_type") == "paragraph" and e.get("section_path"))
para_total = sum(1 for e in elements if e.get("element_type") == "paragraph")
print(f"\nparagraph 有 section_path: {para_with_path} / {para_total}")
