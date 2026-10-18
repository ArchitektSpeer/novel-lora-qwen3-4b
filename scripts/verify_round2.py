#!/usr/bin/env python3
"""验收：书头是否干净、作者是否纠正、章节头是否仍被误杀。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chapter_heads import parse_header

ROOT = Path(__file__).resolve().parent.parent
TRAIN = ROOT / "work" / "05_dataset" / "train.jsonl"
CH = ROOT / "work" / "03_chapters"
CLEAN = ROOT / "work" / "02_clean"
RAW = ROOT / "work" / "01_utf8"

BAD_HEAD = re.compile(r"txt80|笔趣阁|顶点|全集|校对版|电子书|www|\.com|八零|书客居|下载")


def main() -> None:
    n = 0
    bad_titles = Counter()
    authors = Counter()
    no_author = 0
    heads_missing = 0
    seen_books = set()
    lens = []
    no_head = mid_cut = total = 0
    with TRAIN.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            n += 1
            first = d["text"].split("\n")[0]
            if BAD_HEAD.search(first):
                bad_titles[first] += 1
            if d["book"] not in seen_books:
                seen_books.add(d["book"])
                authors[d["author"]] += 1
    print(f"train chunks: {n:,}  书: {len(seen_books)}")
    print(f"书头仍含站名/版本标记的书头行数: {sum(bad_titles.values()):,}")
    for t, c in bad_titles.most_common(10):
        print(f"   {c:>6}  {t}")
    print(f"\n作者覆盖: {sum(v for k, v in authors.items() if k)} 本有作者, {sum(v for k, v in authors.items() if not k)} 本缺失")
    for a, c in authors.most_common(12):
        print(f"   {c:>3}  {a or '(空)'}")

    print("\n== 全量书名体检 ==")
    flags = []
    for p in sorted(CH.glob("*.jsonl")):
        b = json.loads(p.open(encoding="utf-8").readline())["book"]
        why = []
        if BAD_HEAD.search(b):
            why.append("站名/版本标记")
        if re.fullmatch(r"[A-Za-z0-9._\-\s]+", b):
            why.append("纯ASCII(疑似假书名)")
        if len(b) > 24:
            why.append(f"过长({len(b)})")
        if re.search(r"[<>《》【】\[\]]|www|https?|\.txt|作者|著\s*$", b):
            why.append("残留符号")
        if why:
            flags.append((b, p.name, "/".join(why)))
    print(f"   疑似问题书名 {len(flags)} 本")
    for b, f, why in flags[:25]:
        print(f"   - {b!r:<30} <- {f}  [{why}]")

    print("\n== 抽查重点书的作者与书名 ==")
    want = ("吞噬星空", "仙逆", "超级掠食者系统", "次元诸天壁", "信仰造神", "学霸的黑科技系统", "超神制卡师", "灾厄纪元", "深空彼岸")
    for p in sorted(CH.glob("*.jsonl")):
        head = p.open(encoding="utf-8").readline()
        d = json.loads(head)
        if any(w in d["book"] or w in p.name for w in want):
            print(f"   book={d['book']!r:<26} author={d['author']!r:<14} chapters={sum(1 for _ in p.open(encoding='utf-8'))}")

    print("\n== 章节头保留率（01_utf8 里的标题 vs 03_chapters 产出的标题）==")
    targets = {"超级掠食者系统": "0_蚀月纯黑__超级掠食者系统.jsonl",
               "次元诸天壁": "1__次元诸天壁.jsonl",
               "信仰造神": "1__信仰造神.jsonl"}
    for name, jf in targets.items():
        src = list(RAW.rglob(f"*{name}*"))
        jpath = CH / jf
        if not src or not jpath.exists():
            print(f"   {name}: 找不到文件 src={bool(src)} json={jpath.name in [p.name for p in CH.glob('*.jsonl')]}")
            continue
        raw_heads = set()
        for sp in src:
            for line in sp.read_text(encoding="utf-8", errors="ignore").split("\n"):
                t = parse_header(line.strip())
                if t:
                    raw_heads.add(re.sub(r"\s+", "", t))
        got = set()
        for l in jpath.read_text(encoding="utf-8").splitlines():
            got.add(re.sub(r"\s+", "", json.loads(l)["chapter_title"]))
        lost = raw_heads - got
        print(f"   {name}: 原始唯一标题 {len(raw_heads)}  产出 {len(got)}  未命中 {len(lost)}  例: {sorted(lost)[:3]}")

    print("\n== chunk 形态与泄漏 ==")
    def shape(path: Path):
        ls, nh, mc, tot = [], 0, 0, 0
        books = set()
        for line in path.open(encoding="utf-8"):
            d = json.loads(line)
            tot += 1
            ls.append(len(d["text"]))
            books.add(d["book"])
            if not d["text"].startswith("《"):
                nh += 1
            if not re.search(r"[。！？…\"”’】）]$", d["text"].rstrip().split("\n")[-1].strip()):
                mc += 1
        return ls, nh, mc, tot, books
    tr_lens, tr_nh, tr_mc, tr_tot, tr_books = shape(TRAIN)
    va_lens, va_nh, va_mc, va_tot, va_books = shape(ROOT / "work" / "05_dataset" / "valid.jsonl")
    lens = sorted(tr_lens + va_lens)
    def pct(p):
        return lens[min(len(lens) - 1, int(len(lens) * p))]
    print(f"   长度 p1/p50/p99/max: {pct(.01):,} / {pct(.5):,} / {pct(.99):,} / {max(lens):,}")
    print(f"   <1500 字: {sum(1 for x in lens if x < 1500):,}   >7000 字: {sum(1 for x in lens if x > 7000):,}")
    print(f"   缺书头 chunk: {tr_nh + va_nh:,} / {tr_tot + va_tot:,}")
    print(f"   末尾非句末标点: {tr_mc + va_mc:,}（{(tr_mc + va_mc) / (tr_tot + va_tot) * 100:.1f}%，硬切/句中截断）")
    print(f"   train {tr_tot:,} chunk / {len(tr_books)} 本；valid {va_tot:,} chunk / {len(va_books)} 本")
    print(f"   train∩valid 书名: {sorted(tr_books & va_books) or '无（按书切分，无泄漏）'}")


if __name__ == "__main__":
    main()
