# 步驟 4 交叉核對

依 `references/checklist.md` A～G 全部逐項核對，涵蓋簽呈、招標資訊一覽表、公告稿（若已有）、投標須知、契約書、評選須知與評比表、標單、預算書、圖說、自檢表。

每項輸出：一致／不一致／來源缺漏，附兩邊原文與出處。日期用 `scripts/schedule.py` 重算（含星期、假日），不心算。
寫入 `04-crosscheck/04-crosscheck.md`，不一致項依嚴重度排最前面。
`procure.py submit`，結束回合，請承辦人決定每一項怎麼處理。承辦人的決定用 `procure.py decide "…"` 記下。
