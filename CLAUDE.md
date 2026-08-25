# 採訪影片專案

從素材到 Premiere 交付包的完整流程。剪輯靠兩個 skill，分工不重疊：

| skill | 角色 | 負責 |
|---|---|---|
| [video-use](skill/video-use/SKILL.md) | **執行引擎** | 轉錄、切點、調色、疊加動畫、字幕、輸出 |
| [interview-video-story-editor](skill/interview-video-story-editor/SKILL.md) | **決策依據** | 敘事結構、A/B-roll、轉場、字卡、字幕樣式、聲音、品牌收尾 |

video-use 明講「除了 Hard Rules 之外都是藝術自由」，那片留白就由
interview-video-story-editor 補上。動手剪之前兩份都要讀：
**怎麼剪看 interview-video-story-editor，怎麼跑看 video-use。**

### 給 Agent 的執行守則

1. **一律以 video-use 為執行主體。** 轉錄、切片、調色、疊加、字幕、合成、輸出，
   全部呼叫 `skill/video-use/helpers/` 底下的 helper。不要自寫 ffmpeg 管線、
   不要用其他剪輯 skill 取代它——Hard Rules 都寫在那些 helper 裡，
   繞過去容易踩到字幕被疊加層蓋掉、段落交界爆音這類**不會報錯**的失敗。
2. **interview-video-story-editor 只供決策，不執行。** 它決定敘事結構、
   A/B-roll 比例、轉場、字卡層級、字幕樣式、聲音層級；產出的是
   `edl.json` 的內容，不是另一條輸出路徑。
3. **兩者衝突時，video-use 的 Hard Rules 優先。** 那是技術正確性的底線。
   要覆寫 video-use 的**預設行為**（非 Hard Rules）就寫進
   interview-video-story-editor，並註明是「相對 video-use 的調整」——
   不要改 `skill/video-use/`，那是上游 repo。
4. 動工前兩份 SKILL.md 都讀完再開始，不要只讀一份就下刀。

## 開始新專案

### 首次設定（每台機器一次）

```bash
工具/交付包範本/setup.sh video-use
```

檢查並補齊 ffmpeg、Python 套件、`skill/video-use/.env`，最後實際跑一次 helper 驗證。

**金鑰不隨範本附帶**——腳本只會建出空的 `.env`，請自己到
<https://elevenlabs.io/app/settings/api-keys> 申請後填進 `ELEVENLABS_API_KEY=`。
沒填只是不能自動產逐字稿，其餘剪接功能照常。

### 每支新影片

使用者只需要做兩件事：

1. 把訪談影片放進 `素材/影片原檔/`
2. 確認 `素材/品牌素材/` 裡有 Logo 與字型（跨專案共用，通常不必動）

然後說「幫我剪一支 OO 影片」即可。**開工前先建立專案資料夾**：

```bash
python3 工具/新專案.py 專案名稱
```

建出 `工作區/yyyy-mm-dd_專案名稱/` 與標準子目錄。這個範本會累積多支影片，
所有工具腳本**預設處理日期最新的專案**，要處理舊的就加 `--project 資料夾名`。

## 目錄

```text
.claude/
└── hooks/檢查流程.py   PreToolUse hook，擋掉三種不會報錯的失敗（見下）
素材/
├── 影片原檔/        使用者放這裡，不要改寫或移動原檔
└── 品牌素材/        Logo、字型。Logo 任何格式都行，會自動轉 PNG 給 AE 用
skill/
├── video-use/       上游剪輯引擎（clone 自 browser-use/video-use，不要改）
└── interview-video-story-editor/   影片敘事與視覺規範（自己維護）
工具/                生成腳本
├── paths.py         專案定位，所有腳本共用
├── 新專案.py        建立 yyyy-mm-dd_專案名/
└── 交付包範本/      會被複製進交付包的工具與說明
工作區/
├── 2026-08-21_CodePro招生片/
└── 2026-09-01_品牌故事片/     一支影片一個資料夾
```

`素材/` 是共用輸入，`工作區/` 底下各專案獨立。中間產物一律寫進專案資料夾，
不要寫進 `素材/`，也不要跨專案共用 `clips_graded/`。

### 自動防線（`.claude/hooks/檢查流程.py`）

跑 Bash 前自動檢查，擋的都是**不會報錯**的失敗，被擋下時照訊息修正即可：

| 情況 | 反應 |
|---|---|
| `transcribe_batch.py`／`pack_transcripts.py` 少了 `--edit-dir` | deny — 否則產物寫進共用素材 |
| 目標專案缺 `project.md`（不是 `新專案.py` 建的空殼） | deny — 否則產物靜靜寫進空殼 |
| 要出交付包但 `final.mp4` 不存在 | deny |
| 要出交付包但 ProRes 疊加層沒轉 | deny — `make_premiere_xml.py` 會靜默跳過，字卡軌整條消失 |
| 交付包前置都齊了 | **ask** — 由使用者確認 `final.mp4` 才放行 |

hook 判斷不了對話狀態，所以最後那道只能問、不能自動放行。這是刻意的。

---

## 流程

### 階段一：剪輯

先依 [interview-video-story-editor](skill/interview-video-story-editor/SKILL.md)
判斷模式（分析／規劃／製作），定出敘事與視覺；**製作模式的實際執行交給
[video-use](skill/video-use/SKILL.md)**，照它的 Hard Rules 跑，不要自己另寫一套 ffmpeg 管線。

video-use 預設把產物寫進 `<素材資料夾>/edit/`。本範本不用那個位置——
**`transcribe_batch.py` 與 `pack_transcripts.py` 要加 `--edit-dir` 指向專案資料夾**，
讓專案資料夾直接當它的 edit 目錄。只有這兩支吃 `--edit-dir`，其餘 helper 沒有這個參數，
加了會 argparse 報錯：`render.py` 以 `edl.json` 的所在資料夾為 edit 目錄（自動對齊），
`timeline_view.py` 與 `grade.py` 是單進單出，用 `-o` 指定輸出即可。

兩邊檔名本來就對得上（`edl.json`、`clips_graded/`、`animations/`、`master.srt`、
`final.mp4`、`project.md`），對齊之後階段二的 `make_premiere_xml.py` 不必改任何路徑。

```bash
P=工作區/2026-08-21_專案名
H=skill/video-use/helpers

python3 $H/transcribe_batch.py 素材/影片原檔 --edit-dir "$P"   # 逐字稿，要金鑰，有快取
python3 $H/pack_transcripts.py --edit-dir "$P"                 # → takes_packed.md，讀這份決定切點
python3 $H/timeline_view.py <影片> <起秒> <迄秒>                # 只在決策點用，不是掃描工具
python3 $H/render.py "$P/edl.json" -o "$P/final.mp4" --build-subtitles
```

製作模式產出，以下路徑都相對於專案資料夾 `工作區/yyyy-mm-dd_專案名/`：

| 檔案 | 內容 |
|---|---|
| `edl.json` | 剪輯決策：`ranges`（切點）、`overlays`（疊加層）、`subtitle_mute` |
| `clips_graded/` | 逐段切好的素材，命名 `seg_00_*` ~ `seg_NN_*`，**含字卡段** |
| `animations/` | 字卡與 B-roll。全畫面卡 `.mp4`，透明疊加層 `.webm`（VP9 alpha） |
| `master.srt` | 字幕，時間碼走輸出時間軸 |
| `final.mp4` | 成品 |
| `project.md` | 決策紀錄與踩過的工具限制（`新專案.py` 會建空白範本） |

`工具/` 裡的 `make_cards.py`、`make_broll.py`、`build_subs.py`、`compose.py`
是**上一個專案的範本**，文字內容與時間點都寫死了，每個新專案要照著改。
它們一律作用於日期最新的專案。

`make_premiere_xml.py` 相反 —— 完全由 `edl.json` 驅動，不必改，支援 `--project`。

這幾支腳本和 video-use 的 `render.py`／animation slot 功能重疊。取捨是：
**合成與輸出一律走 `render.py`**（Hard Rules 都在它裡面，自己重寫容易踩到字幕被
疊加層蓋掉、段落交界爆音這類無聲失敗）；`make_cards.py`／`make_broll.py` 只留著
生**單張字卡與 B-roll 素材**，因為它們已經套好本專案的品牌色與字型。

### 階段二：交付包

**`final.mp4` 給使用者確認過再進入本階段。** 不要剪完就自動往下跑。
交付包一產出，`edl.json` 就等於凍結——中途要改就得整包重出，而 ProRes 轉檔
加上素材完整複製，一支 60 秒的片約 100MB 起跳，白跑一次成本不低。

正確順序：交出 `final.mp4` → 等使用者確認 → **主動問「要出 Premiere 交付包嗎」**
→ 得到肯定才開始。字卡 `.mogrt`（AE）同理，使用者沒提就不做。

```bash
P=工作區/2026-08-21_專案名        # 換成實際的專案資料夾

# 1. 疊加圖層轉 ProRes 4444（WebM 的 alpha 在副資料流，-vcodec 必須放 -i 前面）
mkdir -p "$P/premiere-export/overlays_prores"
for f in "$P"/animations/*.webm; do
  n=$(basename "$f" .webm)
  ffmpeg -y -vcodec libvpx-vp9 -i "$f" -c:v prores_ks -profile:v 4444 \
    -pix_fmt yuva444p10le -alpha_bits 16 -vendor apl0 \
    "$P/premiere-export/overlays_prores/$n.mov"
done

# 2. 生成完整交付包（XMEML、素材、字型、字幕、修復工具、收件人說明）
python3 工具/make_premiere_xml.py            # 最新專案
python3 工具/make_premiere_xml.py --project 2026-08-21_專案名   # 指定專案

# 3. 驗證
"$P/premiere-export/_製作端/setup.sh" check
```

序列名稱預設取專案資料夾名去掉日期前綴，要改用 `--name`。

字卡要能被收件人改字時，再跑：

```bash
"$P/premiere-export/_製作端/setup.sh" ae
```

它會用 AppleScript 叫 After Effects 執行 `make_ae_cards.jsx`，
建出可編輯的字卡合成並匯出 `.mogrt` 到封包根層。
`make_ae_cards.jsx` 的文字內容也是寫死的，新專案要改。

### 交付

整個 `<專案>/premiere-export/` 壓縮寄出。收件人只看 `開始這裡.md`：
裝字型 → 匯入 XML → 匯入 SRT。`_製作端/` 是製作端工具，他們不會碰到。

---

## 已驗證的關鍵決策

改動前先讀，這些都是實測或踩過才確定的：

| 決策 | 原因 |
|---|---|
| 格式用 **XMEML**（FCP7 XML） | Premiere 官方只吃這個；FCPX 的 `.fcpxml` 要第三方轉 |
| 素材**複製進封包**、pathurl 走**相對路徑** | 絕對路徑一交接就全部離線。已實測 Premiere 吃相對路徑 |
| 時間軸用**檔案實際長度**累加，不是 `edl.json` 的秒數 | 兩者因影格量化差數十毫秒，用秒數會在段落交界出現黑格 |
| 疊加層時間點用同一份 `remap()` 重算 | 否則整條疊加軌相對主軌漂移 |
| 主軌**一視同仁走 clips_graded** | 字卡段也在裡面。曾為了「讓文字可編輯」換成純色底板，結果問題卡變空白畫面。可編輯性靠 `.mogrt` 提供，不是把成品挖空 |
| 不另開琥珀線軌之類的裝飾軌 | 全畫面卡的 `.mp4` 裡本來就畫了，疊上去會變兩條 |
| 交付的 SRT **濾掉與大字重複的字幕** | 用重疊比例 > 50% 判斷。跨邊界的短字幕要濾掉，但長句子只是開頭碰到就得保留 |
| 字型要帶**完整字重的靜態實例** | 可變字型（如 Noto Sans TC）預設實例常是 Thin，AE 與 Premiere 直接指定會變細體。用 `fontTools.varLib.instancer` 產生 |
| 收件端修復工具用 **Perl** 不用 Python | macOS 沒有預設安裝 Python 3 |
| shell 腳本不要有叫 `head` 的函式 | 會遮蔽 coreutils 的 `head`，管線裡的 `head -1` 會呼叫到自己 |
| **只有** `transcribe_batch.py`／`pack_transcripts.py` 加 `--edit-dir` 指向專案資料夾 | 不加預設會寫進 `素材/影片原檔/edit/`，污染共用輸入，多支影片還會互相覆蓋。其餘 helper 沒有這個參數，加了直接報 unrecognized arguments：`render.py` 靠 `edl.json` 的位置自動對齊，`timeline_view.py`／`grade.py` 用 `-o` |
| **不裝 librosa 與 matplotlib** | `pyproject.toml` 有列，但全庫沒有一處 import（`timeline_view.py` 另寫了純 `wave` 的 fallback）。照著裝會拖進 numba／scipy 共 300MB 以上 |
| `skill/video-use/` **保留 `.git` 但不改內容** | 它是上游 repo，改了就無法 `git pull --ff-only` 更新。要客製就寫進 interview-video-story-editor |
| shell 字串裡變數後面接全形字要寫 `${var}` | macOS 內建 bash 3.2 在非 UTF-8 locale 下會把「）」的第一個位元組吃進變數名，變成 unbound variable |

---

## 改良閉環：剪輯經驗回寫 skill

使用者提出**影片剪輯、敘事或視覺上的優化建議**時，先照做，
完成後**主動詢問是否寫入 skill**。不要默默實作完就結束。

### 觸發條件

使用者針對下列任一項給出偏好、修正或新做法：

- 敘事結構、段落順序、鉤子設計、片長節奏
- A-roll／B-roll 比例、voice bridge、J-cut／L-cut 用法
- 轉場語言、切點時機
- 字卡層級、姓名條、問題卡、關鍵字、片尾
- 字幕斷句、樣式、可讀性
- 色彩、字體、動畫速度與緩動
- 聲音處理、音樂與環境音層級

單次的內容改動不算（「把這句改成那句」「這段剪掉」）。
**會影響下一支影片怎麼做**的才算。

### 詢問方式

指出具體要寫進哪個檔案的哪一節，讓使用者一句話就能決定：

> 你剛才說「姓名條不要用品牌色色塊，畫面已經有太多藍色」。
> 要不要寫進 `references/visual-style.md` 的〈人物姓名條〉？
> 這樣下次做採訪片會直接套用。

### 寫入位置

| 建議類型 | 寫入 |
|---|---|
| 敘事、結構、A/B-roll、聲音、模式判斷 | `skill/interview-video-story-editor/SKILL.md` |
| 色彩、字體、字卡、轉場、文字動畫、字幕樣式 | `skill/interview-video-story-editor/references/visual-style.md` |
| 工具鏈、格式、交付流程的教訓 | 本文件的〈已驗證的關鍵決策〉 |
| 本專案獨有、不通用的決定 | `<專案>/project.md` |

**不要寫進 `skill/video-use/`。** 那是上游 repo，改了下次 `git pull --ff-only`
就會衝突。需要覆寫它預設行為的規則，一律寫進 interview-video-story-editor，
並註明是「相對 video-use 的調整」。

### 寫入原則

- 寫成**下次可直接套用的規則**，不是這次做了什麼的紀錄
- 附上原因，特別是違反直覺的（例如為什麼不用品牌色）
- 與既有條目衝突時，指出衝突並問要取代還是並存
- 使用者說不用寫就不寫，不要重複詢問同一件事
