#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把範本中的 {{欄位}} 與 [若 條件]…[/若] 條件段落套用成純文字。
用法：python3 scripts/fill_template.py <範本.md> <values.json> <輸出.txt>

values.json 範例：
{
  "案名": "…", "案號": "11507", "預算金額大寫": "伍佰玖拾貳萬貳仟壹佰陸拾柒",
  "條件": ["預算金額逾500萬元"],
  "可選段落": {"未保留後續擴充權利": true}
}
- `[若 X] … [/若]`：X 在 values["條件"] 內才保留，否則整段刪除。
- `[文字]` 方括號內的可選片段（如範本說明三）：以 values["可選段落"] 的鍵為前綴判斷；未指定一律保留並印警告。
- 未提供的 {{欄位}} 會換成 【待補：欄位】並在最後列出。
- 範本頂端的 Markdown 標題、HTML 註解與 `---` 之後的「條件與注意」都不會輸出。
- 「一、二、…」編號不會自動重排，請由 Claude 檢查後重新編號。
"""
import json
import re
import sys
from pathlib import Path


def main(tpl: str, values_file: str, out: str):
    text = Path(tpl).read_text(encoding="utf-8")
    values = json.loads(Path(values_file).read_text(encoding="utf-8"))
    conds = set(values.get("條件", []))
    optional = values.get("可選段落", {})

    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = text.split("\n---\n")[0]
    text = re.sub(r"^# .*\n", "", text, count=1)

    def cond(m):
        return m.group(2) if m.group(1).strip() in conds else ""
    text = re.sub(r"\[若\s*([^\]]+)\]\n?(.*?)\[/若\]\n?", cond, text, flags=re.S)

    warnings = []
    def opt(m):
        inner = m.group(1)
        for k, keep in optional.items():
            if inner.startswith(k):
                return inner if keep else ""
        warnings.append(f"可選片段未指定，已保留：[{inner[:20]}…]")
        return inner
    text = re.sub(r"\[(?!若)([^\[\]]+?)\]", opt, text)

    missing = []
    def fill(m):
        k = m.group(1)
        if k in values and values[k] not in (None, ""):
            return str(values[k])
        missing.append(k)
        return f"【待補：{k}】"
    text = re.sub(r"\{\{([^}]+)\}\}", fill, text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    Path(out).write_text(text, encoding="utf-8")
    print(f"已輸出 {out}")
    for w in warnings:
        print("警告：" + w)
    if missing:
        print("待補欄位：" + "、".join(dict.fromkeys(missing)))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
