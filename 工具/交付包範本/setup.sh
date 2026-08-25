#!/usr/bin/env bash
# CodePro 招生片 — 一鍵環境設定
#
#   ./setup.sh            全部跑（裝字型 → 檢查路徑 → 叫 AE 建字卡 → 打包）
#   ./setup.sh fonts      只安裝字型
#   ./setup.sh check      只檢查 XML 素材路徑狀態
#   ./setup.sh ae         只叫 After Effects 執行字卡腳本
#   ./setup.sh package    只把 .mogrt 收進交付封包並產生說明
#   ./setup.sh video-use  裝 video-use 剪輯環境（ffmpeg、Python 套件、.env）
#
# video-use 是「開工前」的環境準備，不在 all 流程裡 —— all 是交付封包的收尾。
# 這個子命令要在範本根目錄的 工具/交付包範本/setup.sh 執行，
# 複製進交付封包後的那一份找不到 skill/，會直接報錯。
#
# macOS 專用：字型安裝與 AppleScript 控制 AE 都是 macOS 的做法。
#
# 這支腳本是「你」用的，接收者不會碰到。他們拿到的是 premiere-export/ 資料夾。

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # _製作端/
PR_DIR="$(cd "$HERE/.." && pwd)"                       # premiere-export/ ＝ 交付封包
FONT_DST="$HOME/Library/Fonts"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
err()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ---- 字型 ------------------------------------------------------------
install_fonts() {
    section "安裝字型 → $FONT_DST"
    mkdir -p "$FONT_DST"
    local n=0 skip=0
    for f in "$PR_DIR"/fonts/*.ttf; do
        [ -e "$f" ] || { err "找不到字型檔，fonts/ 是空的"; return 1; }
        local base; base="$(basename "$f")"
        if [ -f "$FONT_DST/$base" ] && cmp -s "$f" "$FONT_DST/$base"; then
            skip=$((skip + 1))
        else
            cp "$f" "$FONT_DST/$base" && n=$((n + 1))
        fi
    done
    ok "新安裝 $n 個，已存在 $skip 個"
    [ $n -gt 0 ] && warn "AE／Premiere 若正開著，需重開才會看到新字型"
    return 0
}

# ---- Premiere 路徑 ---------------------------------------------------
# 已實測 Premiere 吃相對路徑，所以這裡只驗證、不改寫。
# 改寫成絕對路徑反而危險 —— 忘了轉回去就交付，對方會整包離線。
check_paths() {
    section "檢查 XML 素材路徑"
    local xml; xml="$(ls -1 "$PR_DIR"/*.xml 2>/dev/null | head -1)"
    if [ -z "$xml" ]; then
        err "找不到 .xml"
        return 1
    fi

    local total abs miss
    total="$(grep -c '<pathurl>' "$xml")"
    abs="$(grep -c '<pathurl>file://' "$xml" || true)"

    miss=0
    while IFS= read -r p; do
        # 只驗相對路徑；絕對路徑代表狀態已經不對，下面會另外報
        case "$p" in file://*) continue ;; esac
        # XML 裡是 percent-encoded，解碼後才能檢查檔案在不在
        local decoded
        decoded="$(printf '%b' "${p//%/\\x}")"
        [ -e "$PR_DIR/$decoded" ] || miss=$((miss + 1))
    done < <(sed -n 's/.*<pathurl>\(.*\)<\/pathurl>.*/\1/p' "$xml")

    ok "素材 $total 筆"
    if [ "$abs" -gt 0 ]; then
        warn "有 $abs 筆是絕對路徑 —— 交付前要轉回相對："
        warn "  python3 \"$HERE/rebind.py\" --relative"
        return 1
    fi
    if [ "$miss" -gt 0 ]; then
        err "有 $miss 筆找不到檔案，封包不完整"
        return 1
    fi
    ok "全部相對路徑且檔案齊全，可直接交付"
    return 0
}

# ---- After Effects ---------------------------------------------------
find_ae() {
    # 挑版本號最大的那個，避免同時裝多版時選到舊的
    ls -1 /Applications 2>/dev/null \
        | grep -i '^Adobe After Effects' \
        | sed 's/\.app$//' \
        | sort -V \
        | tail -1
}

run_ae() {
    section "叫 After Effects 建立字卡合成"
    local script="$HERE/make_ae_cards.jsx"
    if [ ! -f "$script" ]; then
        err "找不到 $script"
        return 1
    fi

    local app; app="$(find_ae)"
    if [ -z "$app" ]; then
        err "/Applications 裡找不到 After Effects"
        warn "有裝但放在別處的話，手動執行："
        warn "  AE → 檔案 > 指令碼 > 執行指令碼檔案… → $script"
        return 1
    fi
    ok "找到：$app"

    warn "第一次執行 macOS 會問「終端機要控制 After Effects」，請按允許"
    osascript <<EOF
tell application "$app"
    activate
    DoScriptFile "$script"
end tell
EOF
    local rc=$?
    if [ $rc -ne 0 ]; then
        err "AppleScript 呼叫失敗（可能是權限被拒或 AE 還在啟動）"
        warn "改成手動：AE → 檔案 > 指令碼 > 執行指令碼檔案… → $script"
        return 1
    fi
    ok "已送出。AE 那邊會跳對話框回報建立與 .mogrt 匯出結果"
    warn "若說沒權限寫檔：偏好設定 > 指令碼與運算式 > 勾「允許指令碼寫入檔案和存取網路」"
    return 0
}

# ---- 打包交付 --------------------------------------------------------
package() {
    section "整理交付封包 → premiere-export/"
    local dst="$PR_DIR/mogrt"

    if [ -d "$dst" ] && [ -n "$(ls -A "$dst" 2>/dev/null)" ]; then
        ok "$(ls -1 "$dst"/*.mogrt 2>/dev/null | wc -l | tr -d ' ') 個 .mogrt 已就位"
    else
        warn "還沒有 .mogrt —— 先跑 ./setup.sh ae 讓 AE 產生"
    fi

    check_paths || { err "路徑檢查沒過，先修好再交付"; return 1; }

    local size; size="$(du -sh "$PR_DIR" | cut -f1)"
    ok "封包大小 $size"
    printf '\n  交付：把整個 premiere-export/ 壓縮寄出\n'
    printf '  對方看 premiere-export/開始這裡.md 就好\n'
    return 0
}

# ---- video-use 剪輯環境 ----------------------------------------------
# 真正被 helpers/ import 的只有 requests / numpy / pillow。
# pyproject.toml 另外列了 librosa 與 matplotlib，但全庫沒有一處 import
# （timeline_view.py 還特地寫了純 wave 的 fallback），照著裝只是多背 300MB+
# 的 numba／scipy，這裡刻意不裝。
VU_PKGS=(requests numpy pillow)

# 從腳本位置往上找 skill/video-use。複製進交付封包的那一份會找不到，這是預期的。
find_video_use() {
    local d="$HERE"
    for _ in 1 2 3 4 5; do
        [ -f "$d/skill/video-use/SKILL.md" ] && { printf '%s\n' "$d/skill/video-use"; return 0; }
        d="$(dirname "$d")"
    done
    return 1
}

# 範本根目錄的辨識特徵。交付封包裡沒有 工具/，所以那一份找不到，正好用來區分。
find_template_root() {
    local d="$HERE"
    for _ in 1 2 3 4 5; do
        [ -f "$d/工具/新專案.py" ] && { printf '%s\n' "$d"; return 0; }
        d="$(dirname "$d")"
    done
    return 1
}

VU_REPO="https://github.com/browser-use/video-use"

install_video_use() {
    section "video-use 剪輯環境"

    local vu root
    vu="$(find_video_use)" || {
        # 從 GitHub clone 這個範本的人不會有 skill/video-use/ ——
        # 它自帶 .git，不能一起進版控。在範本根目錄就自己取回來。
        if root="$(find_template_root)" && command -v git >/dev/null 2>&1; then
            warn "skill/video-use/ 不在，從上游取得"
            if git clone "$VU_REPO" "$root/skill/video-use"; then
                vu="$root/skill/video-use"
                ok "已取得 skill/video-use/"
            else
                err "clone 失敗。手動跑：git clone ${VU_REPO} skill/video-use"
                return 1
            fi
        else
            err "往上找不到 skill/video-use/"
            warn "要在範本根目錄執行：工具/交付包範本/setup.sh video-use"
            warn "還沒取得 skill 的話：git clone ${VU_REPO} skill/video-use"
            return 1
        fi
    }
    ok "skill 位置：$vu"

    local fail=0

    # --- ffmpeg：硬需求，所有剪接動作都靠它 ---
    if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then
        ok "ffmpeg $(ffmpeg -version | sed -n '1s/.* version \([^ ]*\).*/\1/p')"
    elif command -v brew >/dev/null; then
        err "缺 ffmpeg／ffprobe"
        local a=""
        printf '  現在跑 brew install ffmpeg？[y/N] '
        read -r a
        case "$a" in
            [yY]*) brew install ffmpeg && ok "ffmpeg 裝好了" || { err "brew install 失敗"; fail=1; } ;;
            *)     warn "略過。之後自己跑：brew install ffmpeg"; fail=1 ;;
        esac
    else
        err "缺 ffmpeg／ffprobe，且沒有 brew 可用"
        warn "手動安裝：https://ffmpeg.org/download.html"
        fail=1
    fi

    # --- Python 套件 ---
    local py="python3"
    command -v "$py" >/dev/null || { err "找不到 python3"; return 1; }
    ok "python $("$py" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"

    local missing=() p mod
    for p in "${VU_PKGS[@]}"; do
        mod="$p"; [ "$p" = "pillow" ] && mod="PIL"
        "$py" -c "import $mod" 2>/dev/null || missing+=("$p")
    done

    if [ ${#missing[@]} -eq 0 ]; then
        ok "Python 套件齊全：${VU_PKGS[*]}"
    else
        warn "缺套件：${missing[*]}"
        # 先試 --user；PEP 668 的外部管理環境會擋，那就退回 skill 內的 venv
        if "$py" -m pip install --user --quiet "${missing[@]}" 2>/dev/null; then
            ok "已裝進使用者環境（pip --user）"
        else
            warn "--user 被擋（多半是 PEP 668 外部管理環境），改建 venv"
            if "$py" -m venv "$vu/.venv" \
               && "$vu/.venv/bin/pip" install --quiet --upgrade pip \
               && "$vu/.venv/bin/pip" install --quiet "${VU_PKGS[@]}"; then
                ok "venv 就緒：$vu/.venv"
                warn "之後跑 helpers 要用 $vu/.venv/bin/python，不是 python3"
            else
                err "Python 套件安裝失敗"
                fail=1
            fi
        fi
    fi

    # --- 轉錄金鑰：只建空殼，絕不寫入任何金鑰（這份範本是要給別人的）---
    if [ -f "$vu/.env" ] && grep -q '^ELEVENLABS_API_KEY=..' "$vu/.env"; then
        ok ".env 已有 ELEVENLABS_API_KEY"
    elif [ -n "${ELEVENLABS_API_KEY:-}" ]; then
        ok "環境變數 ELEVENLABS_API_KEY 已設定"
    else
        [ -f "$vu/.env" ] || { cp "$vu/.env.example" "$vu/.env" && chmod 600 "$vu/.env"; }
        warn "還沒有轉錄金鑰。到 https://elevenlabs.io/app/settings/api-keys 申請後填進："
        warn "  $vu/.env  →  ELEVENLABS_API_KEY=你的金鑰"
        warn "沒金鑰只是不能自動產逐字稿，其餘剪接功能照常"
    fi

    # --- 選配 ---
    command -v yt-dlp >/dev/null \
        && ok "yt-dlp（可從網址抓素材）" \
        || warn "沒有 yt-dlp。只有要從網址抓素材才需要：brew install yt-dlp"
    command -v node >/dev/null \
        && ok "node $(node -v)（HyperFrames 動畫用，需 22+）" \
        || warn "沒有 node。只有要用 HyperFrames 做動畫才需要"

    # --- 實際跑一次，不只檢查檔案在不在 ---
    local runner="$py"
    [ -x "$vu/.venv/bin/python" ] && runner="$vu/.venv/bin/python"
    if "$runner" "$vu/helpers/timeline_view.py" --help >/dev/null 2>&1; then
        # 變數後面接全形字要用 ${}：bash 3.2 在非 UTF-8 locale 下會把「）」的
        # 第一個位元組吃進變數名，變成 unbound variable
        ok "helpers 可執行（${runner}）"
    else
        err "helpers 跑不起來，看上面缺什麼"
        fail=1
    fi

    [ $fail -eq 0 ] && ok "video-use 環境就緒" || warn "有項目沒過，看上面的訊息"
    return $fail
}

# ---- 主流程 ----------------------------------------------------------
case "${1:-all}" in
    fonts)     install_fonts ;;
    check)     check_paths ;;
    ae)        run_ae ;;
    package)   package ;;
    video-use) install_video_use ;;
    all)
        fail=0
        install_fonts   || fail=1
        check_paths     || fail=1
        run_ae          || fail=1
        section "等 AE 跑完再按 Enter 繼續打包（AE 是非同步執行的）"
        read -r _
        package         || fail=1
        section "完成"
        if [ $fail -eq 0 ]; then
            ok "全部成功"
        else
            warn "有步驟沒過，看上面的訊息"
        fi
        printf '\n你自己用：\n'
        printf '  Premiere → 檔案 > 匯入 → %s/CodePro招生片.xml\n' "$PR_DIR"
        printf '  字幕     → 檔案 > 匯入 → %s/subtitles/master.srt\n' "$PR_DIR"
        printf '\n交付給別人：\n'
        printf '  壓縮整個 %s/ 寄出即可\n\n' "$PR_DIR"
        exit $fail
        ;;
    *)
        err "不認得的參數：$1"
        printf '用法：%s [all|fonts|check|ae|package|video-use]\n' "$(basename "$0")"
        exit 1
        ;;
esac
