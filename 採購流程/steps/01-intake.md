# 步驟 1 收件

輸入資料在 `cases/<案號>/00-input/`。

1. 轉出文字到 `01-intake/extract/`：PDF 用 `pdftotext -layout`；doc/docx/odt 用 `soffice --headless --convert-to txt`（UTF-8）或 python-docx；xlsx/ods 用 openpyxl 或 soffice 轉出。掃描檔（轉出文字近乎空白）逐頁以影像讀取，不得假裝讀過。沒有工具就直接讀原檔，並在摘要註明用了什麼方式。
2. 讀 `reference/舊檔/` 中同類案件（若有），記下格式與用語。
3. 以 `references/field-mapping.md` 的欄位為準，填 `01-intake/01-summary.md` 的案件摘要表。每個值附來源檔與位置。
4. 列「缺漏」（業務簽提到卻沒收到的附件、`references/checklist.md` F 項）與「疑點」（來源檔互相不一致，附兩邊原文）。
5. 能確定的基本資料用 `procure.py set` 寫回（案名、業務單位、採購類別、預算金額、決標方式）。
6. `procure.py submit`，結束回合，請承辦人確認：摘要是否正確、缺漏由誰補。
