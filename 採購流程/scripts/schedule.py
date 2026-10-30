#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
招標日程試算（用程式算，不心算）。
用法：
  python3 scripts/schedule.py --announce 2026-03-02 --days 14 [--open-offset 1]
  python3 scripts/schedule.py --deadline 2026-03-16 --days 14   （反推公告日）

輸出：公告日、廠商提問截止、機關最後答覆日、截止投標日、開標日，皆含星期與假日警示。
規則：
  - 等標期自公告日「次日」起算（招標期限標準第 2 條：公告日及截止投標日不計入 → 截止投標日 = 公告日 + 等標期 + 1？
    實務：等標期之計算自公告日起至截止投標日止，公告日不計、截止日計入 → 截止投標日 = 公告日 + 等標期）。
    本程式採「截止投標日 = 公告日 + 等標期」，並列出兩種算法供核對，請以機關慣例為準。
  - 廠商提問截止 = 公告日 + ceil(等標期/4)（投標須知第 12 點，尾數進位）。
  - 機關答覆：最後答覆日的次日起算至截止投標日，天數 ≥ ceil(等標期/4)（施行細則第 43 條）。
  - 開標日 = 截止投標日 + open-offset（預設次日；可設 0 為同日）。
假日表：references/holidays.txt（每行 YYYY-MM-DD；請依人事行政總處行事曆維護）。
"""
import argparse
import datetime as dt
import math
from pathlib import Path

HOLIDAY_FILE = Path(__file__).resolve().parent.parent / "references" / "holidays.txt"
WEEK = "一二三四五六日"


def load_holidays() -> set[dt.date]:
    out = set()
    if HOLIDAY_FILE.exists():
        for line in HOLIDAY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                try:
                    out.add(dt.date.fromisoformat(line))
                except ValueError:
                    pass
    return out


def roc(d: dt.date) -> str:
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def show(label: str, d: dt.date, holidays: set[dt.date]) -> str:
    flag = ""
    if d.weekday() >= 5:
        flag = "　⚠ 週末"
    if d in holidays:
        flag = "　⚠ 假日"
    return f"{label:12s} {d.isoformat()}（{roc(d)}，週{WEEK[d.weekday()]}）{flag}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--announce", help="公告日 YYYY-MM-DD")
    ap.add_argument("--deadline", help="截止投標日 YYYY-MM-DD（反推）")
    ap.add_argument("--days", type=int, required=True, help="等標期（日曆天）")
    ap.add_argument("--open-offset", type=int, default=1, help="開標日距截止投標日天數（預設 1）")
    a = ap.parse_args()
    if not a.announce and not a.deadline:
        ap.error("請給 --announce 或 --deadline")
    holidays = load_holidays()
    if a.announce:
        ann = dt.date.fromisoformat(a.announce)
        deadline = ann + dt.timedelta(days=a.days)
    else:
        deadline = dt.date.fromisoformat(a.deadline)
        ann = deadline - dt.timedelta(days=a.days)
    q = math.ceil(a.days / 4)
    ask_by = ann + dt.timedelta(days=q)
    reply_by = deadline - dt.timedelta(days=q + 1)
    open_day = deadline + dt.timedelta(days=a.open_offset)

    print(f"等標期 {a.days} 日　釋疑日數 ceil({a.days}/4) = {q} 日")
    print(show("公告日", ann, holidays))
    print(show("廠商提問截止", ask_by, holidays))
    print(show("機關最後答覆", reply_by, holidays) + f"　（答覆次日起至截止投標：{(deadline - reply_by).days - 1} 日 ≥ {q}）")
    print(show("截止投標日", deadline, holidays))
    print(show("開標日", open_day, holidays))
    print()
    print("核對：若機關慣例為「公告日次日起算、截止投標日計入」，截止投標日同上；")
    print(f"　　　若為「公告日與截止日皆不計」，截止投標日應為 {deadline + dt.timedelta(days=1)}。請依投標須知與工程會函釋確認。")
    if not holidays:
        print("提醒：references/holidays.txt 無資料，未檢查國定假日。")


if __name__ == "__main__":
    main()
