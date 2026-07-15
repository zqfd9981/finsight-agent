"""检查 p103-105 在 MinerU 输出里的完整内容（elements + full.md）。"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"

# 1. 看 p103-105 的所有 elements
print("=== p103-105 的所有 elements ===")
with (doc_dir / "elements.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            elem = json.loads(line)
            page = elem.get("page_start", 0)
            if page in (103, 104, 105):
                etype = elem.get("element_type", "")
                text = (elem.get("text") or "")[:200]
                print(f"  p{page} [{etype:>10}] {text}")

# 2. 看 full.md 里 p103-105 的内容
print("\n=== full.md 里 p103-105 的内容 ===")
md_path = doc_dir / "full.md"
if md_path.exists():
    content = md_path.read_text(encoding="utf-8")
    # 按 page marker 分割
    import re
    # MinerU 的 full.md 通常没有明确分页标记，搜索关键字
    for keyword in ["四、本期期末余额", "（六）其他", "三、公司基本情况"]:
        idx = content.find(keyword)
        if idx >= 0:
            print(f"\n关键字 '{keyword}' 出现在位置 {idx}:")
            print(f"  上下文: ...{content[max(0,idx-50):idx+200]}...")
