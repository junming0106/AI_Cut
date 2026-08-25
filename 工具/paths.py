"""專案路徑解析。所有工具腳本共用。

工作區底下每支影片一個資料夾，命名 `yyyy-mm-dd_專案名`。
腳本預設處理**日期最新**的那個，也可以用 --project 指定：

    python3 工具/make_premiere_xml.py
    python3 工具/make_premiere_xml.py --project 2026-08-22_CodePro招生片
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "工作區"
BRAND = ROOT / "素材" / "品牌素材"
RAW = ROOT / "素材" / "影片原檔"
TEMPLATE = ROOT / "工具" / "交付包範本"

NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")

# 一支影片的標準子目錄
SUBDIRS = ("clips_graded", "animations", "transcripts")


def list_projects() -> list[Path]:
    """依日期排序，最舊在前。"""
    if not WORK.exists():
        return []
    return sorted((p for p in WORK.iterdir()
                   if p.is_dir() and NAME_RE.match(p.name)),
                  key=lambda p: p.name)


def title_of(p: Path) -> str:
    """去掉日期前綴，當序列名稱用。"""
    m = NAME_RE.match(p.name)
    return m.group(2) if m else p.name


def current(name: str | None = None) -> Path:
    """定位要處理的專案。指定 name 就找它，否則取最新的。"""
    projects = list_projects()
    if name:
        for p in projects:
            if p.name == name or title_of(p) == name:
                return p
        avail = "\n".join(f"  {p.name}" for p in projects) or "  （沒有任何專案）"
        sys.exit(f"找不到專案「{name}」。目前有：\n{avail}")

    if not projects:
        sys.exit(
            "工作區/ 裡沒有專案。\n"
            "先建立一個：python3 工具/新專案.py 專案名稱")
    return projects[-1]


def add_argument(parser):
    """給各腳本掛上統一的 --project 參數。"""
    parser.add_argument("--project", metavar="資料夾名",
                        help="指定專案，預設取日期最新的那個")
