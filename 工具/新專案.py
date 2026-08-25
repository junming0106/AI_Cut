"""建立一支新影片的工作資料夾。

    python3 工具/新專案.py CodePro招生片
    python3 工具/新專案.py 品牌故事 --date 2026-09-01

建出 `工作區/yyyy-mm-dd_專案名/` 與標準子目錄。之後所有工具腳本
預設就會處理這個最新的專案。
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys

import paths

TEMPLATE_MD = """# {title}

建立日期：{date}

## 決策紀錄

記錄非顯而易見的判斷 —— 為什麼這樣剪、為什麼不用那個素材、
踩到什麼工具限制。下次重跑或交接時靠這份。

## 素材

## Outstanding
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("名稱", help="專案名稱，不含日期")
    ap.add_argument("--date", help="覆寫日期，格式 yyyy-mm-dd，預設今天")
    a = ap.parse_args()

    date = a.date or dt.date.today().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        sys.exit(f"日期格式要是 yyyy-mm-dd，收到「{date}」")

    # 資料夾名稱會進路徑與 XML，擋掉會出事的字元
    title = a.名稱.strip()
    if not title or re.search(r'[/\\:*?"<>|]', title):
        sys.exit("專案名稱不能空白，也不能含 / \\ : * ? \" < > |")

    proj = paths.WORK / f"{date}_{title}"
    if proj.exists():
        sys.exit(f"已經存在：{proj}")

    for d in paths.SUBDIRS:
        (proj / d).mkdir(parents=True)
    (proj / "project.md").write_text(
        TEMPLATE_MD.format(title=title, date=date), encoding="utf-8")

    print(f"建立 {proj.relative_to(paths.ROOT)}")
    for d in paths.SUBDIRS:
        print(f"  {d}/")
    print("  project.md")

    others = [p for p in paths.list_projects() if p != proj]
    if others:
        print(f"\n工作區裡還有 {len(others)} 個舊專案，"
              f"工具腳本預設處理最新的這個。")
        print("要指定舊專案時加 --project 資料夾名。")


if __name__ == "__main__":
    main()
