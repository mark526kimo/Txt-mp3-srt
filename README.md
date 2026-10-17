# txt-mp3-srt

旁白稿批次轉 MP3 + SRT 字幕（ElevenLabs）。

純前端單一網頁：直接用瀏覽器開啟 `index.html` 即可使用，不需安裝或架伺服器。

## 功能
- 選擇資料夾或多個 `.txt`，依檔名自然排序批次轉換
- 支援 Eleven v4 / v3 / Multilingual v2 / Flash v2.5
- 超過約 9,000 字自動分段，再合併成一個 MP3
- 使用 ElevenLabs `with-timestamps` 時間軸自動產生 `.srt`（不額外扣額度）
  - 句號／問號／驚嘆號／換行一定斷句，逗號依長度斷句
  - 可設定每行最多字數（中文建議 14–20，英文建議 35–45）
  - 可選擇去除句尾標點或保留
  - 轉完後改字幕設定，下載時直接套用，不必重新轉換
- 可選擇輸出資料夾直接存檔（Chrome / Edge），或下載單檔 / 全部 ZIP

API Key 只從瀏覽器直接送到 ElevenLabs，勾選「記住」才會存在本機 localStorage。
