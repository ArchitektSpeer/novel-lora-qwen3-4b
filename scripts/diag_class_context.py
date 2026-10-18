#!/usr/bin/env python3
"""从 02_clean 抽取指定残留类别的 ±40 字上下文并归一成模板，用于设计第五轮规则。
用法: python3 scripts/diag_class_context.py
"""
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "work" / "02_clean"

CLASSES = {
    "书海阁": r"书\s*海\s*阁|書\s*海\s*閣",
    "书客居": r"书客居|書客居",
    "秒记住": r"[0-9一二三]秒记住",
    "尖括号水印": r"<[一-鿿]{2,12}>",
    "作者感言": r"^(?:今天|明天|后天|周[一二三四五六日]|\d+月\d+日).{0,12}(?:加更|补更|爆更|请假|更新感言|二更|三更|四更|五更|第一更|第二更)",
    "题外话": r"－－－|---+＋+|题外话|盟主",
    "求票正文混排": r"换榜|收票员|推荐票好|月票好|求(?:张)?票",
    "无弹广告": r"无弹广告|无广告|无弹窗",
    "请收藏": r"请收藏",
    "搜狗": r"搜狗|索\s*狗",
    "SEO标题行": r"^[^，。\n]{0,20}第\d+章[^，。\n]{0,20}!$",
    "感叹号标题": r"第[\d一二三四五六七八九十百千]+章[^\n，。]{0,20}[!！]$",
}
DIGITS = re.compile(r"\d+")


def work(files):
    ctx = {k: Counter() for k in CLASSES}
    samples = {}
    pats = {k: re.compile(v) for k, v in CLASSES.items()}
    for f in files:
        text = Path(f).read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            for k, p in pats.items():
                for m in p.finditer(line):
                    lo, hi = max(0, m.start() - 24), min(len(line), m.end() + 24)
                    frag = re.sub(r"\s+", "", line[lo:hi])
                    ctx[k][DIGITS.sub("#", frag)] += 1
                    samples.setdefault(k, []).append((Path(f).name, line[max(0, m.start() - 40):m.end() + 40]))
    return ctx, samples


def main() -> None:
    files = sorted(str(p) for p in CLEAN.rglob("*.txt"))
    tot = {k: Counter() for k in CLASSES}
    ex = {}
    with ProcessPoolExecutor(12) as pool:
        for ctx, samples in pool.map(work, [files[i::12] for i in range(12)]):
            for k, c in ctx.items():
                tot[k] += c
            for k, rows in samples.items():
                ex.setdefault(k, []).extend(rows)
    for k in CLASSES:
        n = sum(tot[k].values())
        print(f"\n### {k}  命中 {n:,} 次 / 唯一模板 {len(tot[k]):,}")
        for tpl, c in tot[k].most_common(6):
            print(f"  {c:>6,}  {tpl[:70]}")
        seen = set()
        for book, s in ex.get(k, []):
            key = re.sub(r"\s+", "", s)[:60]
            if key in seen:
                continue
            seen.add(key)
            print(f"     例[{book}] {s.strip()[:100]}")
            if len(seen) >= 4:
                break


if __name__ == "__main__":
    main()
