"""把 edl.json 轉成完整的 Premiere 交付封包。

輸出 Final Cut Pro 7 XML（XMEML v5）—— Premiere 官方支援這個，
不吃 FCPX 的 .fcpxml。時間單位是影格。

一個指令做完整包：XMEML、素材、字型、過濾後字幕、修復工具、給收件人的說明。

用法：
    python3 工具/make_premiere_xml.py
    python3 工具/make_premiere_xml.py --absolute   # 絕對路徑，只在自己機器用

三個關鍵決定，改動前先讀，都是實測踩出來的：

1. 素材複製進封包、pathurl 走相對路徑。絕對路徑一交接就全部離線。
   已實測 Premiere 吃相對路徑。

2. 時間軸用 clips_graded 的實際檔案長度累加，不是 edl.json 的秒數。
   兩者因影格量化差數十毫秒，用秒數會在段落交界出現黑格。
   疊加層時間點依同一份 remap() 重算，否則整條軌相對主軌漂移。

3. 主軌一視同仁走 clips_graded —— 字卡段（CARD_*）也在裡面。
   不要為了「讓文字可編輯」把它換成純色底板，那會讓成品變空白畫面。
   可編輯性靠 .mogrt 提供。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import paths
from paths import BRAND, TEMPLATE

# 都在 main() 依 --project 決定
WORK = EXPORT = MEDIA = PRORES = Path()
PORTABLE = True
W = H = FPS = 0          # 由 detect_canvas() 依素材偵測


def f(sec: float) -> int:
    return int(round(sec * FPS))


def stage(p: Path) -> Path:
    """自足模式下把素材複製進 media/，回傳封包內的路徑。"""
    if not PORTABLE or EXPORT in p.parents:
        return p
    MEDIA.mkdir(parents=True, exist_ok=True)
    dst = MEDIA / p.name
    if not dst.exists() or dst.stat().st_size != p.stat().st_size:
        shutil.copy2(p, dst)
    return dst


def url(p: Path) -> str:
    if PORTABLE:
        return urllib.parse.quote(str(p.resolve().relative_to(EXPORT.resolve())))
    return "file://" + urllib.parse.quote(str(p.resolve()))


def probe(p: Path):
    """回傳 (秒, 寬, 高, 有無音訊, fps)。"""
    d = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height,codec_type,r_frame_rate",
         "-show_entries", "format=duration", "-of", "json", str(p)],
        capture_output=True, text=True, check=True).stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    has_a = any(s["codec_type"] == "audio" for s in d["streams"])
    num, den = v.get("r_frame_rate", "24/1").split("/")
    return (float(d["format"].get("duration", 0) or 0),
            int(v["width"]), int(v["height"]), has_a, float(num) / float(den or 1))


def detect_canvas(sample: Path):
    """畫布規格跟著素材走 —— 換直式／橫式專案不必改程式。"""
    global W, H, FPS
    _, W, H, _, fps = probe(sample)
    FPS = int(round(fps))


# ---- XML 基礎元件 ------------------------------------------------------
def sub(parent, tag, text=None):
    e = ET.SubElement(parent, tag)
    if text is not None:
        e.text = str(text)
    return e


def rate(parent):
    r = sub(parent, "rate")
    sub(r, "timebase", FPS)
    sub(r, "ntsc", "FALSE")


def samplechar(parent, w, h):
    sc = sub(parent, "samplecharacteristics")
    rate(sc)
    sub(sc, "width", w)
    sub(sc, "height", h)
    sub(sc, "anamorphic", "FALSE")
    sub(sc, "pixelaspectratio", "square")
    sub(sc, "fielddominance", "none")
    sub(sc, "colordepth", 24)


class Files:
    """file 元素只完整定義一次，之後靠 id 引用 —— XMEML 的規矩。"""

    def __init__(self):
        self.seen: dict[str, str] = {}
        self.n = 0

    def emit(self, parent, path: Path, frames, w, h, has_audio):
        path = stage(path)
        key = str(path)
        el = sub(parent, "file")
        if key in self.seen:
            el.set("id", self.seen[key])
            return el
        self.n += 1
        fid = f"file-{self.n}"
        self.seen[key] = fid
        el.set("id", fid)
        sub(el, "name", path.name)
        sub(el, "pathurl", url(path))
        rate(el)
        sub(el, "duration", frames)
        m = sub(el, "media")
        v = sub(m, "video")
        sub(v, "duration", frames)
        samplechar(v, w, h)
        if has_audio:
            a = sub(m, "audio")
            sc = sub(a, "samplecharacteristics")
            sub(sc, "depth", 16)
            sub(sc, "samplerate", 48000)
            sub(a, "channelcount", 2)
        return el


class Builder:
    def __init__(self):
        self.files = Files()
        self.n = 0

    def _base(self, track, path, start, end, src_in, src_out, file_frames):
        self.n += 1
        cid = f"clip-{self.n}"
        ci = sub(track, "clipitem")
        ci.set("id", cid)
        sub(ci, "name", path.name)
        sub(ci, "enabled", "TRUE")
        sub(ci, "duration", file_frames)
        rate(ci)
        sub(ci, "start", start)
        sub(ci, "end", end)
        sub(ci, "in", src_in)
        sub(ci, "out", src_out)
        return ci, cid

    def video(self, track, path, start, end, src_in, src_out, file_frames,
              w, h, has_audio, alpha=False):
        ci, cid = self._base(track, path, start, end, src_in, src_out, file_frames)
        self.files.emit(ci, path, file_frames, w, h, has_audio)
        sub(ci, "compositemode", "normal")
        if alpha:
            sub(ci, "alphatype", "straight")   # ProRes 4444 的透明通道
        return ci, cid

    def audio(self, track, path, start, end, src_in, src_out, file_frames,
              w, h, channel):
        ci, cid = self._base(track, path, start, end, src_in, src_out, file_frames)
        self.files.emit(ci, path, file_frames, w, h, True)
        st = sub(ci, "sourcetrack")
        sub(st, "mediatype", "audio")
        sub(st, "trackindex", channel)
        return ci, cid


def link_group(members):
    """把同一素材的 video/audio clipitem 綁成一組。

    XMEML 要求每個成員都帶完整的 link 清單（含指向自己那筆），
    Premiere 才會把影音當成一個片段一起選取、一起搬動。
    """
    for el, _, _, _, _ in members:
        for _, cid, mtype, tidx, cidx in members:
            l = sub(el, "link")
            sub(l, "linkclipref", cid)
            sub(l, "mediatype", mtype)
            sub(l, "trackindex", tidx)
            sub(l, "clipindex", cidx)


# ---- 字幕 --------------------------------------------------------------
def parse_srt(p: Path):
    def t2s(t):
        h, m, rest = t.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    out = []
    for blk in re.split(r"\n\s*\n", p.read_text(encoding="utf-8").strip()):
        lines = [l for l in blk.strip().splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        m = re.match(r"([\d:,]+)\s*-->\s*([\d:,]+)", lines[1])
        if m:
            out.append((t2s(m.group(1)), t2s(m.group(2)), lines[1],
                        "\n".join(lines[2:])))
    return out


def filter_srt(src: Path, dst: Path, mute: list):
    """濾掉與疊加大字重複的字幕。

    用重疊比例而非「完全落在區間內」—— 跨邊界的短字幕也要濾掉，
    但長句子只是開頭碰到就必須保留，那是不同內容。
    """
    kept, dropped = [], []
    for a, b, tc, txt in parse_srt(src):
        dur = max(b - a, 1e-6)
        ratio = max((max(0.0, min(b, m["to"]) - max(a, m["from"])) / dur
                     for m in mute), default=0.0)
        (dropped if ratio > 0.5 else kept).append((tc, txt))

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        "\n\n".join(f"{i}\n{tc}\n{txt}" for i, (tc, txt) in enumerate(kept, 1))
        + "\n", encoding="utf-8")
    return len(kept), [t for _, t in dropped]


# ---- 主組裝 ------------------------------------------------------------
def build(edl: dict, seq_name: str):
    clips_dir = WORK / "clips_graded"

    # 主軌：一視同仁走 clips_graded，字卡段也在裡面
    main, cursor, edl_cursor = [], 0, 0.0
    for i, r in enumerate(edl["ranges"]):
        p = next(clips_dir.glob(f"seg_{i:02d}_*"), None)
        if p is None:
            raise SystemExit(f"缺少 seg_{i:02d}_* —— clips_graded 不完整")
        dur, w, h, has_a, _ = probe(p)
        n = f(dur)
        main.append({"path": p, "start": cursor, "frames": n, "w": w, "h": h,
                     "audio": has_a, "edl_start": edl_cursor,
                     "edl_dur": r["end"] - r["start"]})
        cursor += n
        edl_cursor += r["end"] - r["start"]
    total = cursor

    def remap(t: float) -> int:
        """edl 秒 → 實際時間軸影格。"""
        for m in main:
            if m["edl_start"] <= t < m["edl_start"] + m["edl_dur"] + 1e-6:
                off = (t - m["edl_start"]) / m["edl_dur"] if m["edl_dur"] else 0
                return m["start"] + int(round(off * m["frames"]))
        return f(t)

    root = ET.Element("xmeml", {"version": "5"})
    seq = sub(root, "sequence")
    seq.set("id", "sequence-1")
    sub(seq, "name", seq_name)
    sub(seq, "duration", total)
    rate(seq)
    tc = sub(seq, "timecode")
    rate(tc)
    sub(tc, "string", "00:00:00:00")
    sub(tc, "frame", 0)
    sub(tc, "displayformat", "NDF")
    media = sub(seq, "media")
    video = sub(media, "video")
    samplechar(sub(video, "format"), W, H)

    b = Builder()
    v_tracks = [sub(video, "track") for _ in range(3)]
    audio = sub(media, "audio")
    sub(audio, "numOutputChannels", 2)
    asc = sub(sub(audio, "format"), "samplecharacteristics")
    sub(asc, "depth", 16)
    sub(asc, "samplerate", 48000)
    a_tracks = [sub(audio, "track") for _ in range(2)]

    # V1 + A1/A2
    v_idx = a_idx = 0
    for m in main:
        v_idx += 1
        v_el, v_id = b.video(v_tracks[0], m["path"], m["start"],
                             m["start"] + m["frames"], 0, m["frames"],
                             m["frames"], m["w"], m["h"], m["audio"])
        if not m["audio"]:
            continue
        a_idx += 1
        members = [(v_el, v_id, "video", 1, v_idx)]
        for c in range(2):
            a_el, a_id = b.audio(a_tracks[c], m["path"], m["start"],
                                 m["start"] + m["frames"], 0, m["frames"],
                                 m["frames"], m["w"], m["h"], c + 1)
            members.append((a_el, a_id, "audio", c + 1, a_idx))
        link_group(members)

    # V2 B-roll（疊加、靜音 —— voice bridge 靠底層旁白延續）
    n_broll = 0
    for ov in edl.get("overlays", []):
        p = WORK / ov["file"]
        if p.suffix != ".mp4" or not p.exists():
            continue
        dur, w, h, _, _ = probe(p)
        st, n = remap(ov["start_in_output"]), f(ov["duration"])
        b.video(v_tracks[1], p, st, st + n, 0, n, f(dur), w, h, False)
        n_broll += 1

    # V3 ProRes 圖卡（保留原動畫、透明背景）
    n_card = 0
    for ov in edl.get("overlays", []):
        if not ov["file"].endswith(".webm"):
            continue
        p = PRORES / (Path(ov["file"]).stem + ".mov")
        if not p.exists():
            continue
        dur, w, h, _, _ = probe(p)
        st, n = remap(ov["start_in_output"]), f(ov["duration"])
        b.video(v_tracks[2], p, st, st + n, 0, min(n, f(dur)), f(dur), w, h,
                False, alpha=True)
        n_card += 1

    for t in v_tracks:
        sub(t, "enabled", "TRUE")
        sub(t, "locked", "FALSE")
    for i, t in enumerate(a_tracks):
        sub(t, "enabled", "TRUE")
        sub(t, "locked", "FALSE")
        sub(t, "outputchannelindex", i + 1)

    return root, total, n_broll, n_card, main


def indent(e, level=0):
    pad = "\n" + "  " * level
    if len(e):
        if not (e.text or "").strip():
            e.text = pad + "  "
        for c in e:
            indent(c, level + 1)
        if not (c.tail or "").strip():
            c.tail = pad
    if level and not (e.tail or "").strip():
        e.tail = pad


def stage_logo(dst_dir: Path):
    """把品牌 Logo 備到 AE 腳本旁邊。

    AE 讀不了 WebP，一律轉成 PNG。用 ffmpeg 而不是 PIL —— 整個流程本來
    就依賴 ffmpeg，少一個 Python 套件依賴。
    """
    src = next((p for ext in ("*.png", "*.webp", "*.jpg")
                for p in sorted(BRAND.glob(ext))), None)
    if src is None:
        print("    ! 素材/品牌素材/ 裡沒有 Logo，AE 片尾卡會略過")
        return
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "logo.png"
    if src.suffix.lower() == ".png":
        shutil.copy2(src, dst)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        str(dst)], check=True)
    print(f"    Logo {src.name} → _製作端/assets/logo.png")


def write_timeline(main, edl, total):
    def tc(fr):
        return f"{fr // (FPS * 60):02d}:{(fr // FPS) % 60:02d}:{fr % FPS:02d}"

    rows = ["# 時間軸對照表", "",
            f"序列 {W}×{H} @ {FPS}fps，總長 {tc(total)}（{total / FPS:.2f}s）",
            "", "## V1 主軌", "",
            "| # | 進點 | 時長 | 素材 | Beat | 台詞 |", "|---|---|---|---|---|---|"]
    for i, (m, r) in enumerate(zip(main, edl["ranges"])):
        q = (r.get("quote") or "").replace("|", "／")
        rows.append(f"| {i:02d} | {tc(m['start'])} | {m['frames'] / FPS:.2f}s | "
                    f"`{m['path'].name}` | {r.get('beat', '')} | {q} |")
    (EXPORT / "TIMELINE.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main():
    global PORTABLE, WORK, EXPORT, MEDIA, PRORES
    ap = argparse.ArgumentParser()
    ap.add_argument("--absolute", action="store_true",
                    help="絕對路徑、素材不複製（只在自己機器上用）")
    ap.add_argument("--name", help="序列名稱，預設取專案資料夾名（去掉日期）")
    paths.add_argument(ap)
    a = ap.parse_args()
    PORTABLE = not a.absolute

    WORK = paths.current(a.project)
    EXPORT = WORK / "premiere-export"
    MEDIA = EXPORT / "media"
    PRORES = EXPORT / "overlays_prores"
    print(f"專案 {WORK.name}")

    edl_path = WORK / "edl.json"
    if not edl_path.exists():
        raise SystemExit(f"找不到 {edl_path}\n先完成剪輯流程產生 edl.json")
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    seq_name = a.name or edl.get("project_name") or paths.title_of(WORK)

    sample = next((WORK / "clips_graded").glob("seg_00_*"), None)
    if sample is None:
        raise SystemExit("clips_graded/ 是空的 —— 先完成剪輯流程")
    detect_canvas(sample)

    EXPORT.mkdir(parents=True, exist_ok=True)
    root, total, n_broll, n_card, main_segs = build(edl, seq_name)
    indent(root)
    out = EXPORT / f"{seq_name}.xml"
    out.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
                   + ET.tostring(root, encoding="unicode"), encoding="utf-8")

    print(f"  {out.name}")
    print(f"    {W}×{H} @ {FPS}fps ｜ {total} 影格 / {total / FPS:.2f}s")
    print(f"    V1 {len(main_segs)} 段 ｜ V2 B-roll {n_broll} ｜ V3 圖卡 {n_card}")

    write_timeline(main_segs, edl, total)

    fonts_dst = EXPORT / "fonts"
    fonts_dst.mkdir(exist_ok=True)
    n_font = sum(1 for ttf in BRAND.glob("*.ttf")
                 if shutil.copy2(ttf, fonts_dst / ttf.name))
    print(f"    字型 {n_font} 個")

    srt = WORK / "master.srt"
    if srt.exists():
        n_kept, dropped = filter_srt(srt, EXPORT / "subtitles" / "master.srt",
                                     edl.get("subtitle_mute", []))
        shutil.copy2(srt, EXPORT / "subtitles" / "master-完整版.srt")
        print(f"    字幕 {n_kept} 條"
              + (f"（濾掉 {len(dropped)}：{'、'.join(dropped)}）" if dropped else ""))
    else:
        print("    ! 找不到 master.srt，字幕未打包")

    prod = EXPORT / "_製作端"
    prod.mkdir(exist_ok=True)
    for name in ("setup.sh", "rebind.py"):
        src = TEMPLATE / name
        if src.exists():
            shutil.copy2(src, prod / name)
            if name.endswith(".sh"):
                (prod / name).chmod(0o755)
    jsx = paths.ROOT / "工具" / "make_ae_cards.jsx"
    if jsx.exists():
        shutil.copy2(jsx, prod / jsx.name)
        stage_logo(prod / "assets")
    for name in ("修復素材連結.command", "開始這裡.md"):
        src = TEMPLATE / name
        if src.exists():
            shutil.copy2(src, EXPORT / name)
            if name.endswith(".command"):
                (EXPORT / name).chmod(0o755)

    size = subprocess.run(["du", "-sh", str(EXPORT)],
                          capture_output=True, text=True).stdout.split()[0]
    print(f"    封包 {size}")
    print("完成 →", EXPORT)


if __name__ == "__main__":
    main()
