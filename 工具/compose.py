"""最終合成：base → overlays（PTS 位移）→ 字幕（最後）→ loudnorm。

為什麼不直接用 render.py 的合成：
  1. WebM VP9 的 alpha 存在副資料流，預設解碼器會丟掉它 —— 必須在每個
     overlay 輸入前加 -vcodec libvpx-vp9，否則透明背景變成不透明黑色。
  2. render.py 的 SUB_FORCE_STYLE 是英文 bold-overlay 樣式（模組常數，
     CLI 無法覆寫），中文需要不同的字型、行高與邊界。

流程仍遵守硬規則：逐段擷取 → 無損串接（交給 render.py）→ overlay 用
setpts 位移 → 字幕最後套用 → 響度正規化。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import paths
from paths import BRAND, RAW

# 作用於日期最新的專案。要處理舊專案就先把它的日期改新，或直接改這行。
EDIT = paths.current()
REPO = Path("/Users/huangjunming/Developer/video-use")
FONTS = BRAND

# 字幕樣式定義在 build_subs.py 產生的 .ass 標頭裡（含 PlayRes 1080x1920）


def run(cmd: list[str], quiet: bool = True):
    r = subprocess.run(
        cmd, stdout=subprocess.DEVNULL if quiet else None, stderr=subprocess.PIPE
    )
    if r.returncode != 0:
        print(r.stderr.decode()[-2500:], file=sys.stderr)
        raise SystemExit(f"失敗: {' '.join(cmd[:6])}...")


def esc(p: Path) -> str:
    return str(p.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def main():
    preview = "--preview" in sys.argv
    out = EDIT / ("preview.mp4" if preview else "final.mp4")

    edl = json.loads((EDIT / "edl.json").read_text(encoding="utf-8"))
    overlays = edl.get("overlays") or []
    srt = EDIT / (edl.get("subtitles") or "master.srt")

    # 1) 交給 render.py 做逐段擷取 + 無損串接（不含 overlay / 字幕 / loudnorm）
    base_edl = {k: v for k, v in edl.items() if k not in ("overlays", "subtitles")}
    tmp_edl = EDIT / "_edl_base.json"
    tmp_edl.write_text(json.dumps(base_edl, ensure_ascii=False, indent=2), encoding="utf-8")
    base = EDIT / "base_nofx.mp4"
    print("1/3  逐段擷取 + 串接")
    cmd = [
        "uv", "run", "python", str(REPO / "helpers" / "render.py"),
        str(tmp_edl), "-o", str(base), "--no-subtitles", "--no-loudnorm",
    ]
    if preview:
        cmd.append("--preview")
    r = subprocess.run(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        print(r.stderr.decode()[-2500:], file=sys.stderr)
        raise SystemExit("擷取失敗")
    tmp_edl.unlink(missing_ok=True)

    # 2) overlay（PTS 位移，Hard Rule 4）+ 字幕（最後，Hard Rule 1）
    print(f"2/3  合成 {len(overlays)} 個圖層 + 字幕")
    inputs: list[str] = ["-i", str(base)]
    for ov in overlays:
        p = EDIT / ov["file"]
        # WebM VP9 必須強制 libvpx-vp9 解碼才拿得到 alpha
        if p.suffix == ".webm":
            inputs += ["-vcodec", "libvpx-vp9"]
        inputs += ["-i", str(p)]

    parts: list[str] = []
    for i, ov in enumerate(overlays, 1):
        t = float(ov["start_in_output"])
        parts.append(f"[{i}:v]setpts=PTS-STARTPTS+{t}/TB[a{i}]")
    cur = "[0:v]"
    for i, ov in enumerate(overlays, 1):
        t = float(ov["start_in_output"])
        end = t + float(ov["duration"])
        parts.append(
            f"{cur}[a{i}]overlay=enable='between(t,{t:.3f},{end:.3f})':eof_action=pass[v{i}]"
        )
        cur = f"[v{i}]"
    # 用 ass filter：樣式與 PlayRes 都寫在 .ass 裡，字級與邊界即真實像素。
    # （subtitles filter 走 SRT 時會套用 384x288 的預設 PlayRes，字幕會跑到畫面中央）
    parts.append(f"{cur}ass='{esc(srt)}':fontsdir='{esc(FONTS)}'[outv]")

    composed = EDIT / "_composed.mp4"
    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(parts),
        "-map", "[outv]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium" if preview else "slow",
        "-crf", "22" if preview else "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", str(composed),
    ])

    # 3) 響度正規化到社群標準
    print("3/3  響度正規化 (-14 LUFS / -1 dBTP)")
    run([
        "ffmpeg", "-y", "-i", str(composed),
        "-af", "loudnorm=I=-14:TP=-1:LRA=11",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", str(out),
    ])
    composed.unlink(missing_ok=True)

    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(out)],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"\n完成 → {out.name}  ({float(dur):.2f}s, {out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
