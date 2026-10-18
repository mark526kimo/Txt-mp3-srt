#!/usr/bin/env python3
"""旁白稿批次轉 MP3 + SRT（ElevenLabs）指令列版本。

只用 Python 標準函式庫，不需 pip install。

範例：
  export ELEVENLABS_API_KEY=xxxx
  python3 txt2mp3srt.py 旁白稿資料夾
  python3 txt2mp3srt.py a.txt b.txt -v VOICE -o 輸出 --max-len 16
  python3 txt2mp3srt.py 旁白稿資料夾 -o 輸出 --srt-only --max-len 20   # 只依已存時間軸重做字幕，不扣額度
"""
import argparse
import base64
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_CHARS = 9000  # v4 單次上限約 10,000 字元，留餘裕
ALIGN_DIR = ".align"  # 存放時間軸，供 --srt-only 重做字幕
RETRY_STATUS = {429, 500, 502, 503}
DEFAULT_VOICE = "B5GGvFKlvZE2sF6uc1zX"

try:  # 打包成應用程式時沒有系統憑證，改用 certifi
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = None


# ---------- 切段（送 API 用） ----------
def split_text(text):
    if len(text) <= MAX_CHARS:
        return [text]
    chunks, buf = [], ""

    def push(p):
        nonlocal buf
        if len(buf) + len(p) + 1 > MAX_CHARS and buf:
            chunks.append(buf)
            buf = ""
        buf += p + "\n"

    for para in text.split("\n"):
        if len(para) <= MAX_CHARS:
            push(para)
            continue
        cur = ""
        for ch in para:
            cur += ch
            if ch in "。！？.!?" and len(cur) > MAX_CHARS * 0.6:
                push(cur)
                cur = ""
        if cur:
            push(cur)
    if buf.strip():
        chunks.append(buf)
    return chunks


# ---------- 呼叫 API ----------
class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(f"{status} {msg}"[:200])
        self.status = status


def tts(text, voice, key, model, fmt, with_ts, voice_settings=None):
    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(voice, safe='')}"
           + ("/with-timestamps" if with_ts else "") + f"?output_format={fmt}")
    payload = {"text": text, "model_id": model}
    if voice_settings:
        payload["voice_settings"] = voice_settings
    body = json.dumps(payload).encode()
    for attempt in range(1, 6):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "xi-api-key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600, context=SSL_CTX) as res:
                data = res.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUS and attempt < 5:
                time.sleep(2 * attempt)
                continue
            detail = ""
            try:
                j = json.loads(e.read())
                d = j.get("detail", j)
                detail = d.get("message") if isinstance(d, dict) and d.get("message") else json.dumps(d, ensure_ascii=False)
            except Exception:
                pass
            raise ApiError(e.code, detail)
        except urllib.error.URLError as e:
            if attempt < 5:
                time.sleep(2 * attempt)
                continue
            raise ApiError("網路錯誤", str(e.reason))
        if not with_ts:
            return data, None
        j = json.loads(data)
        return base64.b64decode(j["audio_base64"]), j.get("alignment") or j.get("normalized_alignment")


# ---------- 音色 ----------
VOICE_SETTING_KEYS = ("speed", "stability", "similarity_boost", "style")
DEFAULT_VOICE_SETTINGS = {"speed": 1.0, "stability": 0.5, "similarity_boost": 0.75, "style": 0.0}


def _get_json(path, key):
    req = urllib.request.Request("https://api.elevenlabs.io" + path, headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            d = json.loads(e.read()).get("detail", {})
            detail = (d.get("status") or d.get("message") or "") if isinstance(d, dict) else str(d)
        except Exception:
            pass
        if e.code == 401 and "permission" in detail.lower():
            raise ApiError(e.code, "此 Key 沒有這項權限")
        raise ApiError(e.code, "API Key 無效" if e.code == 401 else (detail or "查詢失敗"))
    except urllib.error.URLError as e:
        raise ApiError("網路錯誤", str(e.reason))


def list_voices(key):
    """帳號可用的音色，回傳 [{"id", "name", "category"}]，依名稱排序。"""
    j = _get_json("/v1/voices", key)
    voices = [{"id": v["voice_id"], "name": v.get("name") or v["voice_id"], "category": v.get("category") or ""}
              for v in j.get("voices", [])]
    return sorted(voices, key=lambda v: v["name"].lower())


def get_voice_settings(key, voice):
    """音色在 ElevenLabs 上儲存的設定；缺的欄位用 API 預設值補上。"""
    j = _get_json(f"/v1/voices/{urllib.parse.quote(voice, safe='')}/settings", key)
    return {k: float(j[k]) if j.get(k) is not None else DEFAULT_VOICE_SETTINGS[k] for k in VOICE_SETTING_KEYS}


def resolve_voice(key, voice):
    """-v 可以給音色名稱：在帳號音色中找同名者（不分大小寫），找不到就當作 ID。"""
    if re.fullmatch(r"[A-Za-z0-9]{20}", voice):  # 已經是 Voice ID
        return voice
    try:
        for v in list_voices(key):
            if v["name"].lower() == voice.lower():
                return v["id"]
    except Exception:  # 查不到清單就當作 ID
        pass
    return voice


def preview_text(text, limit=150):
    """取開頭一兩句當試聽文字（約 limit 字內，在句尾切開）。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = max((text.rfind(p, 0, limit) for p in "。！？!?\n"), default=-1)
    if cut < limit * 0.3:
        cut = max((text.rfind(p, 0, limit) for p in "，,、；; "), default=-1)
    return text[:cut + 1].strip() if cut > 0 else text[:limit]


# ---------- 剩餘額度 ----------
def get_quota(key):
    """查詢 ElevenLabs 本期額度，回傳 {tier, limit, used, left, reset}；失敗時丟出 ApiError。"""
    req = urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as res:
            j = json.loads(res.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            d = json.loads(e.read()).get("detail", {})
            detail = (d.get("status") or d.get("message") or "") if isinstance(d, dict) else str(d)
        except Exception:
            pass
        if e.code == 401 and "permission" in detail.lower():
            raise ApiError(e.code, "此 Key 沒有讀取額度的權限（轉換不受影響）")
        raise ApiError(e.code, "API Key 無效，無法查詢額度" if e.code == 401 else "無法查詢額度")
    except urllib.error.URLError as e:
        raise ApiError("網路錯誤", f"無法查詢額度（{e.reason}）")
    limit, used = j.get("character_limit") or 0, j.get("character_count") or 0
    return {"tier": j.get("tier") or "", "limit": limit, "used": used, "left": max(0, limit - used),
            "reset": j.get("next_character_count_reset_unix")}


def format_quota(q):
    s = (f"方案：{q['tier']}｜" if q["tier"] else "") + f"剩餘 {q['left']:,} / {q['limit']:,}（已用 {q['used']:,}）"
    if q["reset"]:
        t = time.localtime(q["reset"])
        s += f"｜{t.tm_mon}/{t.tm_mday} 重置"
    return s


# ---------- MP3 長度（讓分段後的字幕時間能正確接續） ----------
_BITRATES = {
    (1, 1): [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    (1, 2): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    (1, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (2, 1): [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
    (2, 2): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_BITRATES[(2, 3)] = _BITRATES[(2, 2)]
_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_duration(data):
    """逐一掃描 MP3 frame 計算長度（秒），失敗回傳 None。"""
    i, n, total = 0, len(data), 0.0
    if data[:3] == b"ID3" and n > 10:
        i = 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))
    frames = 0
    while i + 4 <= n:
        h = data[i:i + 4]
        if h[0] != 0xFF or (h[1] & 0xE0) != 0xE0:
            i += 1
            continue
        ver_bits, layer_bits = (h[1] >> 3) & 3, (h[1] >> 1) & 3
        br_idx, sr_idx, pad = h[2] >> 4, (h[2] >> 2) & 3, (h[2] >> 1) & 1
        if ver_bits == 1 or layer_bits == 0 or br_idx in (0, 15) or sr_idx == 3:
            i += 1
            continue
        ver = 1 if ver_bits == 3 else 2
        layer = 4 - layer_bits
        br = _BITRATES[(ver, layer)][br_idx] * 1000
        sr = _RATES[ver_bits][sr_idx]
        if layer == 1:
            samples, size = 384, (12 * br // sr + pad) * 4
        else:
            samples = 576 if (layer == 3 and ver == 2) else 1152
            size = samples // 8 * br // sr + pad
        if size <= 0:
            i += 1
            continue
        if not (frames == 0 and (b"Xing" in data[i:i + size] or b"Info" in data[i:i + size])):
            total += samples / sr  # 第一個 frame 若是 Xing/Info 標頭則不算長度
        frames += 1
        i += size
    return total if frames else None


# ---------- 產生 SRT ----------
STRONG = "。！？!?；;…"
WEAK = "，,、：:"
CLOSERS = "」』”’）)】》\"'"


def _is_space(c):
    return c.isspace()


def _is_sentence_end(chars, i):
    ch = chars[i]
    if ch in STRONG:
        return True
    if ch == ".":  # 避免把 3.5 切開
        return i + 1 >= len(chars) or chars[i + 1].isspace()
    return False


def strip_tags(align):
    """去除 [excited]、[whispers] 這類語氣標籤（語音會照標籤表現，但字幕不顯示）。"""
    c = align["chars"]
    out = {"chars": [], "starts": [], "ends": []}
    i = 0
    while i < len(c):
        if c[i] == "[":
            j = i + 1
            while j < len(c) and j - i <= 40 and c[j] not in "]\n[":
                j += 1
            inner = "".join(c[i + 1:j])
            if j < len(c) and c[j] == "]" and inner and all(ch.isalpha() or ch in " '-" for ch in inner):
                i = j + 1
                continue
        out["chars"].append(c[i])
        out["starts"].append(align["starts"][i])
        out["ends"].append(align["ends"][i])
        i += 1
    return out


def build_cues(align, max_len):
    a = strip_tags(align)
    chars, starts, ends = a["chars"], a["starts"], a["ends"]
    cues, cur = [], []  # cur: [(ch, s, e)]

    def vis(arr):
        return sum(1 for c in arr if not _is_space(c[0]))

    def flush():
        nonlocal cur
        t = [c for c in cur if not _is_space(c[0])]
        if t:
            text = re.sub(r"\s+", " ", "".join(c[0] for c in cur)).strip()
            cues.append({"text": text, "start": t[0][1], "end": t[-1][2]})
        cur = []

    pending = False
    for i, ch in enumerate(chars):
        if pending:
            if ch in CLOSERS or ch in STRONG:
                cur.append((ch, starts[i], ends[i]))
                continue
            flush()
            pending = False
        if ch == "\n":
            flush()
            continue
        if not cur and _is_space(ch):
            continue
        cur.append((ch, starts[i], ends[i]))
        if _is_sentence_end(chars, i):
            pending = True
            continue
        length = vis(cur)
        if ch in WEAK and length >= max_len * 0.6:
            flush()
            continue
        if length > max_len:
            # 超過長度：往回找逗號或空白斷開，找不到就硬切
            cut = -1
            for j in range(len(cur) - 2, 0, -1):
                if cur[j][0] in WEAK or _is_space(cur[j][0]):
                    if vis(cur[:j + 1]) >= max_len * 0.3:
                        cut = j
                    break
            if cut < 0:
                cut = len(cur) - 2
            rest = cur[cut + 1:]
            cur = cur[:cut + 1]
            flush()
            cur = rest
    flush()
    # 避免時間重疊、長度為零
    for i, c in enumerate(cues):
        if i + 1 < len(cues) and c["end"] > cues[i + 1]["start"]:
            c["end"] = cues[i + 1]["start"]
        if c["end"] <= c["start"]:
            c["end"] = c["start"] + 0.3
    return cues


def clean_text(t, keep_punct):
    if keep_punct:
        return t
    t = re.sub(r"[，、,；;：:]+(?=.)", " ", t)
    t = re.sub(r"[。，、,．.；;：:]+([」』”’）)】》\"']*)$", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def srt_time(sec):
    ms = max(0, round(sec * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build_srt(align, max_len, keep_punct):
    out = []
    for c in build_cues(align, max(6, max_len)):
        text = clean_text(c["text"], keep_punct)
        if text:
            out.append(f"{len(out) + 1}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{text}\n")
    return "\n".join(out)


# ---------- 主流程 ----------
def natural_key(p):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", p.name)]


def collect_files(inputs):
    files = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            files += [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() == ".txt"]
        elif p.is_file() and p.suffix.lower() == ".txt":
            files.append(p)
        else:
            print(f"略過：{inp}（不是 .txt 或資料夾）", file=sys.stderr)
    seen, uniq = set(), []
    for f in sorted(files, key=natural_key):
        if f.resolve() not in seen:
            seen.add(f.resolve())
            uniq.append(f)
    return uniq


def read_text(path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "big5", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def write_srt(path, align, args):
    path.write_text("﻿" + build_srt(align, args.max_len, args.keep_punct), encoding="utf-8")


class Stopped(Exception):
    pass


def convert(f, out_dir, key, args, log=print, should_stop=None):
    text = read_text(f)
    if not text:
        raise ValueError("空檔")
    with_ts = not args.no_srt
    parts = []
    align = {"chars": [], "starts": [], "ends": []} if with_ts else None
    offset = 0.0
    chunks = split_text(text)
    for k, chunk in enumerate(chunks, 1):
        if should_stop and should_stop():
            raise Stopped("已停止")
        if len(chunks) > 1:
            log(f"    第 {k}/{len(chunks)} 段…")
        audio, a = tts(chunk, args.voice, key, args.model, args.format, with_ts,
                       getattr(args, "voice_settings", None))
        parts.append(audio)
        if align is not None:
            if not a:
                raise ValueError("API 未回傳時間軸，無法產生字幕")
            n = len(a["characters"])
            align["chars"] += a["characters"]
            align["starts"] += [s + offset for s in a["character_start_times_seconds"]]
            align["ends"] += [e + offset for e in a["character_end_times_seconds"]]
            align["chars"].append("\n")  # 段落分隔
            align["starts"].append(offset)
            align["ends"].append(offset)
            dur = mp3_duration(audio)
            offset += dur if dur is not None else (a["character_end_times_seconds"][-1] if n else 0)

    (out_dir / f"{f.stem}.mp3").write_bytes(b"".join(parts))
    if align is not None:
        adir = out_dir / ALIGN_DIR
        adir.mkdir(exist_ok=True)
        (adir / f"{f.stem}.json").write_text(json.dumps(align, ensure_ascii=False), encoding="utf-8")
        write_srt(out_dir / f"{f.stem}.srt", align, args)
    return len(text)


def main():
    ap = argparse.ArgumentParser(description="旁白稿批次轉 MP3 + SRT（ElevenLabs）")
    ap.add_argument("inputs", nargs="*", help="txt 檔或資料夾（資料夾會包含子資料夾）")
    ap.add_argument("-o", "--out", help="輸出資料夾（預設：與 txt 同一個資料夾）")
    ap.add_argument("-k", "--api-key", help="API Key（預設讀環境變數 ELEVENLABS_API_KEY）")
    ap.add_argument("-v", "--voice", help=f"音色名稱或 Voice ID（預設：環境變數 ELEVENLABS_VOICE_ID，或 {DEFAULT_VOICE}）")
    ap.add_argument("--list-voices", action="store_true", help="列出帳號裡的音色名稱與 ID")
    ap.add_argument("-m", "--model", default="eleven_v4_turbo",
                    help="eleven_v4_turbo（預設）/ eleven_v4 / eleven_v3 / eleven_multilingual_v2 / eleven_flash_v2_5")
    ap.add_argument("-f", "--format", default="mp3_44100_128",
                    help="mp3_44100_128（預設）/ mp3_44100_192 / mp3_44100_64")
    ap.add_argument("--max-len", type=int, default=18, help="每行字幕最多字數（預設 18，英文建議 35–45）")
    ap.add_argument("--keep-punct", action="store_true", help="字幕保留原文標點（預設去除句尾標點、逗號改空格）")
    ap.add_argument("--no-srt", action="store_true", help="只產生 MP3")
    ap.add_argument("--srt-only", action="store_true", help="只依已存的時間軸重做 SRT，不呼叫 API、不扣額度")
    ap.add_argument("--force", action="store_true", help="已存在的 MP3 也重新轉換")
    vs = ap.add_argument_group("聲音調整（沒指定的項目沿用音色在 ElevenLabs 上的設定）")
    vs.add_argument("--speed", type=float, help="語速 0.7–1.2（1.0 為正常）")
    vs.add_argument("--stability", type=float, help="穩定度 0–1（越高越平穩，越低越有起伏）")
    vs.add_argument("--similarity", type=float, help="相似度 0–1（越高越貼近原音色）")
    vs.add_argument("--style", type=float, help="風格強度 0–1（越高情緒越誇張）")
    ap.add_argument("--preview", nargs="?", const="", metavar="文字",
                    help="試聽：只轉一小段存成「試聽.mp3」。不給文字就取第一個 txt 的開頭一兩句")
    args = ap.parse_args()

    key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")

    if args.list_voices:
        if not key:
            sys.exit("請提供 API Key（-k 或 ELEVENLABS_API_KEY）")
        try:
            for v in list_voices(key):
                print(f"{v['id']}  {v['name']}" + (f"（{v['category']}）" if v["category"] else ""))
        except ApiError as e:
            sys.exit(f"無法取得音色清單：{str(e).split(' ', 1)[-1]}")
        return

    files = collect_files(args.inputs)
    if not files and not (args.preview is not None and args.preview):
        sys.exit("找不到任何 .txt 檔")

    def out_dir_for(f):
        d = Path(args.out) if args.out else f.parent
        d.mkdir(parents=True, exist_ok=True)
        return d

    if args.srt_only:
        ok = 0
        for f in files:
            j = out_dir_for(f) / ALIGN_DIR / f"{f.stem}.json"
            if not j.exists():
                print(f"✘ {f.name}：找不到時間軸 {j}")
                continue
            write_srt(out_dir_for(f) / f"{f.stem}.srt", json.loads(j.read_text(encoding="utf-8")), args)
            print(f"✔ {f.stem}.srt")
            ok += 1
        print(f"完成 {ok} / {len(files)}")
        return

    args.voice = args.voice or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    if not key or not args.voice:
        sys.exit("請提供 API Key（-k 或 ELEVENLABS_API_KEY）與 Voice ID（-v 或 ELEVENLABS_VOICE_ID）")
    args.voice = resolve_voice(key, args.voice)

    overrides = {"speed": args.speed, "stability": args.stability,
                 "similarity_boost": args.similarity, "style": args.style}
    overrides = {k: v for k, v in overrides.items() if v is not None}
    args.voice_settings = None
    if overrides:
        try:
            base = get_voice_settings(key, args.voice)
        except Exception:
            base = dict(DEFAULT_VOICE_SETTINGS)
        args.voice_settings = {**base, **overrides}
        print("聲音調整：" + "、".join(f"{k}={v:g}" for k, v in args.voice_settings.items()))

    if args.preview is not None:
        text = args.preview or preview_text(read_text(files[0]))
        out = Path(args.out) if args.out else (files[0].parent if files else Path.cwd())
        out.mkdir(parents=True, exist_ok=True)
        print(f"試聽（{len(text)} 字）：{text}")
        try:
            audio, _ = tts(text, args.voice, key, args.model, args.format, False, args.voice_settings)
        except ApiError as e:
            sys.exit(f"試聽失敗：{e}")
        path = out / "試聽.mp3"
        path.write_bytes(audio)
        print(f"已存成 {path}")
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
        except Exception:
            pass
        return

    total_chars = sum(len(read_text(f)) for f in files)
    print(f"共 {len(files)} 個檔案、約 {total_chars:,} 字元（會依字元數扣 ElevenLabs 額度）")
    need = sum(len(read_text(f)) for f in files
               if args.force or not (out_dir_for(f) / f"{f.stem}.mp3").exists())
    try:
        q = get_quota(key)
        print(format_quota(q))
        if need > q["left"]:
            print(f"⚠ 這批約需 {need:,} 字元，超過剩餘額度（部分模型每字扣的額度較少，實際可能足夠）")
            if sys.stdin.isatty() and input("仍要開始轉換嗎？[y/N] ").strip().lower() not in ("y", "yes"):
                sys.exit("已取消")
    except ApiError as e:
        print(f"額度：{str(e).split(' ', 1)[-1]}")
    except Exception:  # 查不到額度不影響轉換
        print("額度：無法查詢")

    done = skipped = 0
    errors = []
    try:
        for i, f in enumerate(files, 1):
            out_dir = out_dir_for(f)
            if not args.force and (out_dir / f"{f.stem}.mp3").exists():
                print(f"[{i}/{len(files)}] 略過（已存在）：{f.stem}.mp3")
                skipped += 1
                continue
            print(f"[{i}/{len(files)}] 轉換中：{f.name}", flush=True)
            try:
                convert(f, out_dir, key, args)
                print(f"    ✔ 完成：{f.stem}.mp3" + ("" if args.no_srt else f" + {f.stem}.srt"))
                done += 1
            except (ApiError, ValueError, OSError) as e:
                print(f"    ✘ 失敗：{e}")
                errors.append((f.name, str(e)))
                if isinstance(e, ApiError) and e.status == 401:
                    print("API Key 無效，停止。")
                    break
    except KeyboardInterrupt:
        print("\n已停止。")

    print(f"\n完成 {done}、略過 {skipped}、失敗 {len(errors)}（共 {len(files)}）")
    if done:
        try:
            print(format_quota(get_quota(key)))
        except Exception:
            pass
    for name, msg in errors:
        print(f"  {name}：{msg}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
