#!/bin/bash
# 素材顯示「離線」時，雙擊這個檔案。
#
# 它會把專案檔裡的素材位置改成這台電腦上的實際位置。
# 只依賴 macOS 內建的 Perl，不需要另外安裝任何東西。

cd "$(dirname "$0")" || exit 1

printf '\n\033[1mCodePro 招生片 — 修復素材連結\033[0m\n\n'
printf '資料夾位置：%s\n\n' "$PWD"

XML="$(ls -1 ./*.xml 2>/dev/null | head -1)"
if [ -z "$XML" ]; then
    printf '\033[31m找不到專案檔（.xml）\033[0m\n'
    printf '請確認這個檔案跟 CodePro招生片.xml 放在同一個資料夾裡。\n\n'
    printf '按 Enter 關閉…'; read -r _; exit 1
fi

cp "$XML" "$XML.bak"

DIR="$PWD" perl -i -pe '
    BEGIN {
        $dir = $ENV{"DIR"};
        $ok = 0; $miss = 0;
        # 逐 byte 做 percent-encoding，中文路徑才不會壞
        sub enc {
            my $s = shift;
            $s =~ s/([^A-Za-z0-9\-_.~\/])/sprintf("%%%02X", ord($1))/ge;
            return $s;
        }
        sub dec {
            my $s = shift;
            $s =~ s/%([0-9A-Fa-f]{2})/chr(hex($1))/ge;
            return $s;
        }
    }
    s{<pathurl>([^<]+)</pathurl>}{
        my $raw = $1;
        my $rel = $raw;
        # 已經是絕對路徑的，先抽出檔案在封包內的相對位置
        if ($rel =~ m{^file://}) {
            $rel = dec($rel);
            $rel =~ s{^file://}{};
            if ($rel =~ m{/((?:media|plates|overlays_prores|mogrt)/[^/]+)$}) {
                $rel = $1;
            }
        } else {
            $rel = dec($rel);
        }
        my $abs = "$dir/$rel";
        if (-e $abs) { $ok++; } else { $miss++; }
        "<pathurl>file://" . enc($abs) . "</pathurl>";
    }ge;
    END { print STDERR "$ok $miss\n"; }
' "$XML" 2> /tmp/_rebind_count

read -r OK MISS < /tmp/_rebind_count
rm -f /tmp/_rebind_count

printf '\033[32m完成\033[0m\n'
printf '  已連結：%s 個素材\n' "$OK"
if [ "${MISS:-0}" -gt 0 ]; then
    printf '  \033[31m找不到：%s 個\033[0m\n' "$MISS"
    printf '\n  這通常表示資料夾不完整。\n'
    printf '  請確認 media、plates、overlays_prores 三個資料夾都在。\n'
else
    printf '  原始檔已備份為 %s\n' "$(basename "$XML").bak"
fi

printf '\n\033[1m接下來：\033[0m\n'
printf '  回到 Premiere，重新匯入一次 %s\n' "$(basename "$XML")"
printf '  （先把專案面板裡舊的那個序列刪掉）\n\n'
printf '按 Enter 關閉…'
read -r _
