#!/usr/bin/env python3
"""PreToolUse hook：擋掉本專案幾種不會報錯的失敗。

三件事都是實際踩過或讀原始碼確認過會靜默出錯的：

1. `paths.current()` 選到手動建的空殼資料夾 —— 產物寫進去，不報錯
2. helper 少了 `--edit-dir` —— 產物寫進共用的 `素材/影片原檔/edit/`，多支片互蓋
3. 交付包缺 ProRes 疊加層 —— make_premiere_xml.py 第 325 行是 continue，
   字卡軌整條消失，XML 照樣產出

判斷不了「使用者確認過 final.mp4 沒有」（hook 讀不到對話），
所以交付包那步一律回 ask，讓使用者自己按。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "工作區"
NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_.+$")

# 這些腳本沒給 --project 時會自己抓「日期最新」的專案
用最新專案的腳本 = ("make_cards.py", "make_broll.py", "compose.py",
                    "build_subs.py", "make_premiere_xml.py")


def 回應(決定: str, 理由: str) -> None:
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": 決定,
        "permissionDecisionReason": 理由,
    }}, sys.stdout, ensure_ascii=False)
    sys.exit(0)


def 最新專案() -> Path | None:
    if not WORK.exists():
        return None
    ps = sorted((p for p in WORK.iterdir() if p.is_dir() and NAME_RE.match(p.name)),
                key=lambda p: p.name)
    return ps[-1] if ps else None


def main() -> None:
    try:
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except Exception:
        sys.exit(0)          # 讀不到就別擋路
    if not cmd or "工具/" not in cmd and "helpers/" not in cmd:
        sys.exit(0)

    # --- 規則 2：helper 少了 --edit-dir -------------------------------
    for helper in ("transcribe_batch.py", "pack_transcripts.py"):
        if helper in cmd and "--edit-dir" not in cmd:
            回應("deny",
                 f"{helper} 少了 --edit-dir。\n"
                 f"不加的話產物會寫進 素材/影片原檔/edit/，"
                 f"污染共用素材而且多支影片互相覆蓋。\n"
                 f"補上 --edit-dir \"工作區/日期_專案名\" 再跑。\n"
                 f"（只有這兩支 helper 吃 --edit-dir，render.py 靠 edl.json "
                 f"的位置自動對齊，加了反而報錯）")

    # --- 規則 1：目標專案是不是 新專案.py 建的 ------------------------
    if any(s in cmd for s in 用最新專案的腳本) and "--project" not in cmd:
        proj = 最新專案()
        if proj is None:
            回應("deny",
                 "工作區/ 裡沒有專案資料夾。\n"
                 "先跑：python3 工具/新專案.py 專案名稱")
        if not (proj / "project.md").exists():
            回應("deny",
                 f"「{proj.name}」缺 project.md，看起來不是 新專案.py 建的。\n"
                 f"但它日期最新，會被當成目標專案，產物就靜靜寫進這個空殼。\n"
                 f"刪掉它，或用 --project 指定真正要處理的專案。")

    # --- 規則 3：交付包 ----------------------------------------------
    if "make_premiere_xml.py" in cmd:
        proj = 最新專案()
        if proj is None:
            sys.exit(0)      # 上面已經擋過，這裡只是防呆

        if not (proj / "final.mp4").exists():
            回應("deny",
                 f"{proj.name}/final.mp4 還不存在，剪輯還沒完成。\n"
                 f"交付包要等 final.mp4 定稿才做——先產出成品給使用者看。")

        # ProRes 缺了不會報錯，字卡軌會整條消失
        edl = proj / "edl.json"
        if edl.exists():
            try:
                overlays = json.loads(edl.read_text(encoding="utf-8")).get("overlays", [])
            except Exception:
                overlays = []
            prores = proj / "premiere-export" / "overlays_prores"
            缺 = [Path(ov["file"]).stem for ov in overlays
                  if str(ov.get("file", "")).endswith(".webm")
                  and not (prores / (Path(ov["file"]).stem + ".mov")).exists()]
            if 缺:
                回應("deny",
                     f"少了 {len(缺)} 個 ProRes 疊加層：{'、'.join(缺[:5])}"
                     f"{'…' if len(缺) > 5 else ''}\n"
                     f"make_premiere_xml.py 找不到 .mov 會直接跳過（第 325 行的 "
                     f"continue），XML 照樣產出但字卡軌整條消失，不會報錯。\n"
                     f"先跑 CLAUDE.md 階段二第 1 步的 ProRes 轉檔迴圈。")

        回應("ask",
             f"要為「{proj.name}」產生 Premiere 交付包了。\n"
             f"final.mp4 使用者確認過了嗎？交付包一產出 edl.json 就等於凍結，"
             f"之後要改就得整包重出。")

    sys.exit(0)


if __name__ == "__main__":
    main()
