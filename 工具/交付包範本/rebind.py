"""把 XML 裡的素材路徑重新綁定到這台機器。

製作端工具。接收者請改用封包根層的「修復素材連結.command」——
那支只依賴 macOS 內建的 Perl，不需要裝 Python。

用法（在哪個目錄執行都可以）：
    python3 rebind.py              # 相對 → 本機絕對路徑
    python3 rebind.py --relative   # 絕對 → 相對，交接前還原用

會就地改寫 XML，原檔備份成 *.xml.bak。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

# 腳本住在 _製作端/，XML 與素材在它的上層（＝交付封包根層）
HERE = Path(__file__).resolve().parent.parent
PATHURL = re.compile(r"(<pathurl>)(.*?)(</pathurl>)", re.S)


def to_absolute(raw: str) -> str | None:
    if raw.startswith("file://"):
        return None                      # 已是絕對路徑
    p = (HERE / urllib.parse.unquote(raw)).resolve()
    if not p.exists():
        return None
    return p.as_uri()


def to_relative(raw: str) -> str | None:
    if not raw.startswith("file://"):
        return None                      # 已是相對路徑
    p = Path(urllib.parse.unquote(raw[7:]))
    try:
        rel = p.resolve().relative_to(HERE)
    except ValueError:
        return None                      # 素材不在封包內，動不了
    return urllib.parse.quote(str(rel))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--relative", action="store_true", help="轉回相對路徑")
    a = ap.parse_args()
    convert = to_relative if a.relative else to_absolute
    direction = "絕對 → 相對" if a.relative else "相對 → 本機絕對"

    xmls = list(HERE.glob("*.xml"))
    if not xmls:
        sys.exit("這個資料夾裡沒有 .xml")

    for xml in xmls:
        text = xml.read_text(encoding="utf-8")
        n_ok = n_skip = 0
        missing: list[str] = []

        def repl(m: re.Match) -> str:
            nonlocal n_ok, n_skip
            raw = m.group(2)
            new = convert(raw)
            if new is None:
                n_skip += 1
                # 相對路徑指不到檔案才是真的有問題，要回報
                if not a.relative and not raw.startswith("file://"):
                    missing.append(raw)
                return m.group(0)
            n_ok += 1
            return m.group(1) + new + m.group(3)

        out = PATHURL.sub(repl, text)
        if n_ok:
            shutil.copy2(xml, xml.with_suffix(".xml.bak"))
            xml.write_text(out, encoding="utf-8")

        print(f"{xml.name}  [{direction}]")
        print(f"  轉換 {n_ok} 筆，略過 {n_skip} 筆")
        if missing:
            print(f"  找不到 {len(missing)} 個素材：")
            for m in dict.fromkeys(missing):
                print(f"    {m}")
            print("  → media/ 或 plates/ 可能沒跟著複製過來")
        elif n_ok:
            print(f"  備份：{xml.with_suffix('.xml.bak').name}")


if __name__ == "__main__":
    main()
