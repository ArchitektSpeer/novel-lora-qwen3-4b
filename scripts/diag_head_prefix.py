#!/usr/bin/env python3
"""统计「广告前缀粘在章节头前面」的行有多少：这类行 parse_header 认不出来，
会被毒性规则整行删掉，等于丢章。用法: python3 scripts/diag_head_prefix.py
"""
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "work" / "01_utf8"
sys.path.insert(0, str(ROOT / "scripts"))
from chapter_heads import parse_header  # noqa: E402

AD_HINT = re.compile(r"无广告|全文字|无弹窗|纯文字|最快|更新|收藏|txt|TXT|下载|www|http|网")
# 章节头前的广告前缀：不带句末标点、不含 第N章、长度有限
PREFIX = re.compile(r"^[^，。！？;；\n]{0,16}?(?=第[一二三四五六七八九十百千零〇两0-9０-９]{1,14}[章节回])")


def work(files):
    c = Counter()
    ex = []
    for f in files:
        p = Path(f)
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or len(s) > 120 or parse_header(s) is not None:
                continue
            m = PREFIX.match(s)
            if not m:
                continue
            rest = s[m.end():]
            if m.group(0) and parse_header(rest) is not None and AD_HINT.search(m.group(0)):
                c["广告前缀遮蔽章节头"] += 1
                c[m.group(0)[:12]] += 1
                if len(ex) < 12:
                    ex.append((p.name, s[:60]))
    return c, ex


def main() -> None:
    files = sorted(str(p) for p in RAW.rglob("*.txt"))
    tot = Counter()
    ex = []
    with ProcessPoolExecutor(12) as pool:
        for c, rows in pool.map(work, [files[i::12] for i in range(12)]):
            tot += c
            ex.extend(rows)
    print(f"01_utf8 {len(files)} 文件")
    print(f"广告前缀遮蔽章节头(毒性规则会连标题一起删): {tot['广告前缀遮蔽章节头']:,} 行")
    for k, v in tot.most_common(14):
        if k == "广告前缀遮蔽章节头":
            continue
        print(f"   {v:>6,}  {k!r}")
    for name, s in ex[:10]:
        print(f"     例[{name}] {s}")


if __name__ == "__main__":
    main()
