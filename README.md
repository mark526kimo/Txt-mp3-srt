# txt-mp3-srt

旁白稿批次轉 MP3 + SRT 字幕（ElevenLabs）。

純前端單一網頁：直接用瀏覽器開啟 `index.html` 即可使用，不需安裝或架伺服器。

## 功能
- 選擇資料夾或多個 `.txt`，依檔名自然排序批次轉換
- 支援 Eleven v4 Turbo / v4 / v3 / Multilingual v2 / Flash v2.5
- **音色下拉選單**：填入 API Key 後自動載入帳號裡的音色，用名稱選擇；也可以直接輸入 Voice ID
- **聲音調整**：語速（0.7–1.2）、穩定度、相似度、風格強度。預設沿用音色在 ElevenLabs 上的設定，動過滑桿才會套用，按「重設」回到音色設定
- **試聽**：正式轉換前先轉一小段（預設取第一個檔案的開頭一兩句，可自行修改）確認聲音，只扣這一小段的額度
- 超過約 9,000 字自動分段，再合併成一個 MP3
- 使用 ElevenLabs `with-timestamps` 時間軸自動產生 `.srt`（不額外扣額度）
  - 句號／問號／驚嘆號／換行一定斷句，逗號依長度斷句
  - 可設定每行最多字數（中文建議 14–20，英文建議 35–45）
  - 可選擇去除句尾標點或保留
  - 自動去除 `[excited]`、`[whispers]` 這類語氣標籤（語音照樣有效果，字幕不顯示）
  - 轉完後改字幕設定，下載時直接套用，不必重新轉換
- 可選擇輸出資料夾直接存檔（Chrome / Edge），或下載單檔 / 全部 ZIP
- 顯示 ElevenLabs 剩餘額度（方案、剩餘 / 上限、重置日期），每個檔案轉完自動更新；開始前若選取的字數超過剩餘額度會先提醒
  - API Key 需有 **User（讀取）** 權限才查得到額度；沒有權限時只是不顯示，轉換照常
  - 「約需字數」是以字元數估算，部分模型每字扣的額度較少，實際扣除以 ElevenLabs 為準

API Key 只從瀏覽器直接送到 ElevenLabs，勾選「記住」才會存在本機 localStorage。

## Python 指令列版本（`txt2mp3srt.py`）

功能與網頁版相同，字幕斷句規則一致。只用 Python 3 標準函式庫，不需 `pip install`。

```bash
export ELEVENLABS_API_KEY=你的key

# 轉整個資料夾（含子資料夾），MP3 / SRT 存在 txt 旁邊
python3 txt2mp3srt.py 旁白稿資料夾

# 指定輸出資料夾、模型、字幕長度
python3 txt2mp3srt.py a.txt b.txt -o 輸出 -m eleven_v3 --max-len 16

# 用音色名稱、放慢語速，先試聽一小段
python3 txt2mp3srt.py 旁白稿資料夾 -v "我的旁白" --speed 0.9 --preview

# 不滿意字幕斷句？只重做 SRT，不呼叫 API、不扣額度
python3 txt2mp3srt.py 旁白稿資料夾 -o 輸出 --srt-only --max-len 20 --keep-punct
```

| 參數 | 說明 |
|---|---|
| `-o, --out` | 輸出資料夾（預設與 txt 同一個資料夾） |
| `-k, --api-key` / `-v, --voice` | 未指定時讀 `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID`；Voice 預設 `B5GGvFKlvZE2sF6uc1zX` |
| `-m, --model` | `eleven_v4_turbo`（預設）、`eleven_v4`、`eleven_v3`、`eleven_multilingual_v2`、`eleven_flash_v2_5` |
| `-f, --format` | `mp3_44100_128`（預設）、`mp3_44100_192`、`mp3_44100_64` |
| `--max-len` | 每行字幕最多字數（預設 18） |
| `--keep-punct` | 字幕保留原文標點 |
| `--no-srt` | 只產生 MP3 |
| `--srt-only` | 依 `.align/` 裡存的時間軸重做 SRT |
| `--force` | 已存在的 MP3 也重新轉換（預設會跳過） |
| `--list-voices` | 列出帳號裡的音色名稱與 ID |
| `--preview [文字]` | 試聽：只轉一小段存成 `試聽.mp3`（不給文字就取第一個 txt 的開頭一兩句） |
| `--speed` / `--stability` / `--similarity` / `--style` | 聲音調整；沒指定的項目沿用音色在 ElevenLabs 上的設定 |

- txt 編碼自動判斷（UTF-8 / UTF-16 / Big5 / GB18030）
- 遇到 429 / 5xx 自動重試，API Key 錯誤（401）立即停止，按 Ctrl+C 可中斷
- 有失敗的檔案時結束碼為 1，方便排程或腳本判斷
- 開始前與結束後會印出剩餘額度；額度不足時，在終端機互動執行會詢問是否繼續，排程（非互動）執行則只顯示警告並繼續

## 桌面應用程式（`app.py`）

有視窗介面的版本，功能與網頁版相同（含音色選單、聲音調整、試聽；試聽會用系統預設的播放器播放），另有「只重做字幕（不扣額度）」按鈕。設定會存在 `~/.txt2mp3srt.json`（API Key 需勾選「記住」才會存）。

**下載打包好的程式**：GitHub repo 的 **Actions → Build app** → 最新一次執行 → 頁面下方 Artifacts：
- `txt2mp3srt-windows.zip`：解壓縮後雙擊 `txt2mp3srt.exe`
- `txt2mp3srt-macos.zip`：解壓縮後得到 `txt2mp3srt.app`（Apple Silicon M 系列晶片）

正式版請到 repo 右側的 **Releases** 下載。要發布新版本：**Actions → Build app → Run workflow**，填入版本號（例如 `v1.1`）即可，會自動打包並建立 Release（推送 `v*` tag 也可以）。

程式沒有經過程式碼簽章，第一次開啟時：
- Windows 若出現「Windows 已保護您的電腦」：按「其他資訊」→「仍要執行」
- macOS 若出現「無法打開」：在 app 上按右鍵 →「打開」→ 再按「打開」

**自己打包**（需要在目標作業系統上執行）：
```bash
pip install pyinstaller certifi
pyinstaller --onefile --windowed --name txt2mp3srt --hidden-import certifi app.py   # Windows
pyinstaller --windowed --name txt2mp3srt --hidden-import certifi app.py             # macOS
```
直接執行原始碼：`python3 app.py`
