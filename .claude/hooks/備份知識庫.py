#!/usr/bin/env python3
"""PostToolUse hook：知識庫變動後自動 commit + push 到 AI_Cut。

只在改到「下一支影片會用到的規則」時觸發 —— 敘事規範、視覺規範、
專案說明。改工具腳本、素材、工作區產物都不算，那些本來就不進 repo。

**只 add 白名單內的路徑**，不用 `git add -A`。.gitignore 已經是白名單式，
這裡再收一次是雙保險：AI_Cut 是公開 repo，而這個資料夾裡有 ElevenLabs
金鑰和受訪者姓名，外洩不可逆。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMOTE = "https://github.com/junming0106/AI_Cut.git"

# 改到這些才備份。同時也是唯一會被 add 的路徑。
知識庫 = ("CLAUDE.md", "README.md", "skill/interview-video-story-editor",
          ".claude/settings.json", ".claude/hooks")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(("git", "-C", str(ROOT)) + args,
                          capture_output=True, text=True)


def 通知(訊息: str) -> None:
    json.dump({"systemMessage": 訊息}, sys.stdout, ensure_ascii=False)
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    改到的檔 = (data.get("tool_response", {}).get("filePath")
                or data.get("tool_input", {}).get("file_path") or "")
    if not 改到的檔:
        sys.exit(0)

    try:
        相對 = Path(改到的檔).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        sys.exit(0)          # 不在這個專案裡
    if not any(相對 == k or 相對.startswith(k + "/") for k in 知識庫):
        sys.exit(0)

    if not (ROOT / ".git").exists():
        sys.exit(0)

    git("add", "--", *知識庫)
    if not git("diff", "--cached", "--quiet").returncode:
        sys.exit(0)          # 暫存區沒東西，內容其實沒變

    訊息 = f"docs: 更新剪輯知識庫（{Path(相對).name}）"
    r = git("commit", "-m", 訊息)
    if r.returncode:
        通知(f"知識庫 commit 失敗：{(r.stderr or r.stdout).strip()[:200]}")

    # 遠端沒設好就只留本機 commit，不要讓 hook 變成阻礙
    if git("remote", "get-url", "origin").returncode:
        git("remote", "add", "origin", REMOTE)

    r = git("push", "-u", "origin", "main")
    if r.returncode:
        通知(f"知識庫已 commit，但 push 失敗（本機紀錄安全）：\n"
             f"{(r.stderr or r.stdout).strip()[:300]}")
    通知(f"知識庫已備份到 AI_Cut：{訊息}")


if __name__ == "__main__":
    main()
