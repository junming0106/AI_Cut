"""從 EDL + 逐字稿產生繁體中文字幕（輸出時間軸）。

不能用 render.py 的 build_master_srt，因為它是為英文設計的：
  - text.upper() 會把 Bloxels 變成 BLOXELS
  - " ".join() 會讓中文逐字 token 變成「大 家 好」
  - 每 2 個 token 一個 cue，中文等於每 2 個字換一次字幕

這裡改成語意斷句：標點斷行、每行上限 14 字、中文不插空格、
拉丁字與中文之間補一個空格。時間碼一律用輸出時間軸：
    output_time = word.start - segment_start + segment_offset   (Hard Rule 5)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import paths
from paths import BRAND, RAW

# 作用於日期最新的專案。要處理舊專案就先把它的日期改新，或直接改這行。
EDIT = paths.current()
MAX_CHARS = 14          # 單行上限（中文字計 1）
MIN_CHARS = 4           # 低於此長度不因標點斷開 —— 避免「我」這種 0.1 秒閃字
MIN_DUR = 0.85          # 最短顯示時間 —— 「會」這種單字回答要讀得到，上限為所在段落結尾
BREAK_PUNCT = "。！？，、；："
DROP_EDGE = "，、；：。！？"      # 前後兩端的標點都清掉 —— 斷句後常留下開頭逗號

LATIN = re.compile(r"[A-Za-z0-9]")


def is_latin(tok: str) -> bool:
    return bool(LATIN.search(tok))


def join_tokens(tokens: list[str]) -> str:
    """中文直接相接；只要接縫任一側是拉丁字就補空格。

    Scribe 把「Scratch JR」切成 ["Scratch", "JR。"] 兩個 token，
    不補空格會黏成 ScratchJR。
    """
    out = ""
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if not out:
            out = t
            continue
        gap = (is_latin(out[-1]) or is_latin(t[0])) and t[0] not in BREAK_PUNCT
        out += (" " if gap else "") + t
    # 收合「警-警察」這類截斷式口吃 → 「警察」。ASR 用 - 標記字被說一半，
    # 直接留著像錯字，只刪 - 又會變成「警警察」。
    out = re.sub(r"(.)-+\1", r"\1", out)
    out = re.sub(r"\s*-+\s*", "", out)
    return out


def visual_len(s: str) -> int:
    """中文計 1，拉丁字母計 0.5，取整。"""
    n = 0.0
    for ch in s:
        n += 0.5 if LATIN.match(ch) else 1.0
    return int(round(n))


def ass_ts(sec: float) -> str:
    """ASS 時間格式 h:mm:ss.cc（百分之一秒）。"""
    if sec < 0:
        sec = 0.0
    cs = int(round(sec * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{c:02d}"


# PlayRes 明確宣告成影片實際尺寸 —— 否則 libass 會用 384x288 預設值，
# 字級與邊界都會被當成那個座標系解讀，字幕會跑到畫面中間壓住人臉。
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans TC Bold,78,&H00FFFFFF,&H00FFFFFF,&H00701A00,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,64,64,168,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def chunk_words(words: list[dict]) -> list[list[dict]]:
    """依標點與長度上限切成字幕塊。"""
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        t = (w.get("text") or "").strip()
        if not t:
            continue
        cur.append(w)
        text = join_tokens([x["text"].strip() for x in cur])
        n = visual_len(text.strip(DROP_EDGE))
        hit_punct = t[-1] in BREAK_PUNCT and n >= MIN_CHARS
        if hit_punct or visual_len(text) >= MAX_CHARS:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def main(edl_path: Path, out_path: Path):
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    tdir = EDIT / "transcripts"

    # (開始, 結束, 文字, 所在段落在輸出時間軸上的結束點)
    entries: list[tuple[float, float, str, float]] = []
    offset = 0.0

    for r in edl["ranges"]:
        src = r["source"]
        s, e = float(r["start"]), float(r["end"])
        dur = e - s
        tp = tdir / f"{src}.json"

        # 字卡沒有逐字稿 —— 直接推進時間軸，字卡本身已有文字
        if not tp.exists():
            offset += dur
            continue

        tr = json.loads(tp.read_text(encoding="utf-8"))
        words = [
            w for w in tr.get("words", [])
            if w.get("type") == "word"
            and w.get("start") is not None
            and w["end"] > s and w["start"] < e
        ]

        for chunk in chunk_words(words):
            a = max(s, chunk[0]["start"]) - s + offset
            b = min(e, chunk[-1]["end"]) - s + offset
            if b <= a:
                b = a + 0.45
            text = join_tokens([w["text"].strip() for w in chunk])
            text = text.strip(DROP_EDGE).strip()
            if not text:
                continue
            entries.append((a, b, text, offset + dur))

        offset += dur

    entries.sort(key=lambda x: x[0])

    # 拉長過短的 cue，但不得越過所在段落結尾，也不得撞到下一條
    for i, (a, b, t, seg_end) in enumerate(entries):
        if b - a >= MIN_DUR:
            continue
        limit = seg_end
        if i + 1 < len(entries):
            limit = min(limit, entries[i + 1][0] - 0.05)
        entries[i] = (a, max(b, min(a + MIN_DUR, limit)), t, seg_end)

    # 避免相鄰 cue 重疊
    for i in range(len(entries) - 1):
        if entries[i][1] > entries[i + 1][0]:
            entries[i] = (entries[i][0], entries[i + 1][0] - 0.01, entries[i][2], entries[i][3])

    # 已由畫面上的大字承擔的區間，不再重複出字幕
    mute = [(float(m["from"]), float(m["to"])) for m in edl.get("subtitle_mute", [])]
    kept = [
        e for e in entries
        if not any(e[0] >= a - 0.01 and e[1] <= b + 0.01 for a, b in mute)
    ]
    dropped = len(entries) - len(kept)

    lines = [ASS_HEADER.rstrip("\n")]
    for a, b, t, _seg_end in kept:
        lines.append(f"Dialogue: 0,{ass_ts(a)},{ass_ts(b)},Default,,0,0,0,,{t}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    msg = f"字幕 → {out_path.name}（{len(kept)} 條，總時長 {offset:.2f}s）"
    if dropped:
        msg += f"　已略過 {dropped} 條（由大字呈現）"
    print(msg)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
