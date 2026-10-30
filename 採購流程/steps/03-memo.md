# 步驟 3 招標文件核定簽呈

讀：`templates/03-approval-memo.md`（已複製到階段資料夾）、`reference/舊檔/` 內的已核定簽呈、`01-intake/01-summary.md`、`02-judgement/02-judgement.md`、STATE.md。

1. 以範本為骨架，保持舊檔的段落順序、用語與標點，只替換本案資料。條件段落依 02-judgement.md 取捨並重新編號。非最有利標案依範本「條件與注意」整組改寫。
2. 缺資料處填 `【待補：…】`，不得沿用舊案數值（日期、文號、金額、人名尤其不可）。
3. 把欄位值整理成 `03-approval-memo/values.json`，執行
   `python3 採購流程/scripts/fill_template.py <階段資料夾>/03-approval-memo.md <階段資料夾>/values.json <階段資料夾>/03-approval-memo.txt`
   再檢查編號與條件段落，必要時直接修 txt。
4. 執行 `python3 採購流程/scripts/build_memo_docx.py <階段資料夾>/03-approval-memo.txt <階段資料夾>/03-approval-memo.docx`。
5. 填 `03-diff.md`「與舊檔差異對照表」：每處替換的欄位、舊值、新值、來源。
6. `procure.py submit`，結束回合，請承辦人逐段確認；收到修改意見後只改該部分並重產 docx。
