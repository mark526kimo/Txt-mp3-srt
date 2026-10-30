# 採購流程（Claude Code 自動化）

臺北市政府公務人員訓練處總務組採購承辦人用。從業務單位送來簽與招標文件開始，到驗收結案，每一步由 Claude 做完草稿，**停下來等您確認**，確認後才進下一步。

## 使用方式

1. 用 Claude Code 開啟本 repo。
2. 新案：建 `採購流程/cases/<案號>/00-input/`，把業務單位的簽與全部附件放進去（或直接輸入 `/bid-run <案號>`，它會建好資料夾再請您放檔）。
3. 輸入 `/bid-run <案號>`。Claude 會做目前這一步，然後列出成果與待確認事項並停下。
4. 您回覆：
   - `確認`（或 OK）→ 記錄確認，**自動進下一步**並做完再停。
   - `修改：…` → 只改指出的部分，重新請您確認。
   - `跳過` → 略過本步。
   - `契變`／`後續擴充`／`分期驗收` → 履約期間插入臨時階段。
   - `暫停`／`狀態` → 不動、看進度。
5. 進度在 `cases/<案號>/STATE.md`；中途關掉再開，再 `/bid-run <案號>` 即可接續。
6. `/bid-run <案號> 匯出` 把各階段 Markdown 轉成 Word（標楷體 A4），放在 `cases/<案號>/_word/`。

## 流程與確認點

| # | 階段 | 產出 | 您確認什麼 |
|---|---|---|---|
| 1 | 收件 | 案件摘要、缺漏、疑點 | 摘要正確？缺漏誰補？ |
| 2 | 判斷 | 級距、招標／決標方式、等標期、保證金、委員會 | 各項判斷與法條；確認後載入後續階段 |
| 3 | 招標文件核定簽呈 | 簽呈 txt＋docx、與舊檔差異表 | 全文逐段 |
| 4 | 交叉核對 | 簽呈、一覽表、公告稿、投標須知、契約、標單互核 | 每項不一致怎麼處理 |
| 5 | 公告欄位 | 電子採購網欄位與日程試算 | 欄位與日期 |
| 6 | 招標文件歸檔 | 統一檔名、索引、待辦 | 歸檔清單 |
| 7 | 公告與等標期 | 公告紀錄、釋疑／更正 | 是否需另簽 |
| 8 | 開標 | 開標紀錄、資格審查表、開標結果簽 | 紀錄與簽呈 |
| 9 | 評選／評審 | 委員會簽、評選會議紀錄、評選結果簽 | 紀錄與簽呈 |
| 10 | 議價 | 底價簽、議價／比減價格紀錄 | 底價與紀錄 |
| 11 | 決標 | 決標簽、決標紀錄、決標公告欄位 | 簽呈與欄位 |
| 12 | 簽約 | 簽約簽、契約填寫對照、保證金核對 | 簽呈與契約內容 |
| 13 | 履約管理 | 履約紀錄；可插入 A1 契約變更／A2 後續擴充／A3 分期驗收 | 是否插入臨時階段 |
| 14 | 驗收 | 驗收紀錄、驗收簽 | 紀錄與簽呈 |
| 15 | 結案歸檔 | 結案付款簽、全案索引、Word 匯出 | 完成 |

階段序列依招標方式不同（`python3 採購流程/procure.py profiles` 列出）：最有利標走 8→9→11；最低標走 8→10→11；公開評選走 8→9→10→11；限制性招標直接議價走 3→10→11。判斷步驟確認後自動套用。

## 目錄

```
採購流程/
├── procure.py            狀態機（new/status/start/submit/confirm/revise/skip/add/replan/set/decide/todo/export）
├── config.json           機關預設值（機關名稱、採購單位、分機、主持人、代辦門檻）
├── steps/                每一步給 Claude 的作業指示
├── templates/            各階段文件範本（03-approval-memo 依 11506 案已核定簽呈整理）
├── references/           field-mapping.md 欄位來源、checklist.md 核對規則、holidays.txt 假日表
├── reference/舊檔/        您放的歷史案件（格式與用語依據）
├── scripts/
│   ├── build_memo_docx.py  簽呈純文字 → 標楷體 docx
│   ├── fill_template.py    範本套填（{{欄位}} 與 [若 …] 條件段落）
│   └── schedule.py         等標期、釋疑、開標日程試算（含星期與假日）
└── cases/<案號>/
    ├── 00-input/           業務單位簽、招標文件（原件複本）
    ├── STATE.md  case.json 進度
    ├── 01-intake/ 02-judgement/ 03-approval-memo/ … 15-closeout/
    ├── A1-change-1/ A2-expansion-1/ …（臨時階段）
    └── _word/              匯出的 Word
```

## 需要的工具

- Python 3（必要）；`pip install python-docx`（產生 Word；沒有時改用 pandoc）。
- `pdftotext`（poppler）、LibreOffice `soffice`：讀 PDF／doc／ods。沒有時 Claude 會直接讀檔並註明。

## 手動指令（Claude 平常會自己叫）

```bash
python3 採購流程/procure.py new 11507 --title "○○工程" --budget 5922167 --unit 業務組
python3 採購流程/procure.py status
python3 採購流程/procure.py confirm --note "摘要正確"
python3 採購流程/procure.py revise "說明三金額改為施工費"
python3 採購流程/procure.py replan 公開招標_最有利標
python3 採購流程/procure.py add 契變
python3 採購流程/procure.py export
```

## 注意

- 產出的簽呈是草稿，檔號、文號、意見欄由公文系統產生。
- 電子採購網的登入、上傳、送出公告由承辦人自行操作。
- `cases/` 內含人名與文號，若 repo 會推到外部，請評估是否將 `採購流程/cases/` 與 `reference/舊檔/` 加入 `.gitignore`。
- `references/holidays.txt` 是推估的假日表，請依人事行政總處行事曆核對。
