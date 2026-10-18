#!/usr/bin/env python3
"""量化抽检新发现的残留类别：分别统计 01_utf8 / 02_clean / train+valid chunk 的命中量。
用法: python3 scripts/diag_spotcheck_classes.py
"""
import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEX = {
    "书海阁(含空格)": r"书\s*海\s*阁|書\s*海\s*閣|书海閣",
    "书客居": r"书客居|書客居",
    "1秒记住": r"[1一]秒记住",
    "换榜/收票员": r"换榜|收票员|月票好重要|推荐票好重要",
    "作者感言块": r"^(?:今天|明天|后天|周[一二三四五六日]).{0,8}(?:加更|请假|更新感言|缓冲|养伤|上架|爆更|补更)",
    "br&gt 残留": r"(?i)br\s*&?\s*gt\s*;?|&gt;|&lt;",
    "<+汉字水印": r"<\s*[一-鿿]|[一-鿿]\s*<",
    "题外话/盟主块": r"题外话|欠(?:另外)?[一-鿿]{0,4}盟主|盟主.{0,6}(?:加更|一章)",
    "SEO 重复标题行": r"^[^，。\n]{0,20}第\d+章[^，。\n]{0,20}!$",
    "空格分享话术": r"请?分享(?:给|到)|分享.{0,6}(?:好友|书友)",
}
PATS = {k: re.compile(v) for k, v in LEX.items()}


def scan_lines(files):
    c = Counter()
    ex = {}
    for f in files:
        text = Path(f).read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            for k, p in PATS.items():
                m = p.search(line)
                if m:
                    c[k] += 1
                    ex.setdefault(k, (Path(f).name, line.strip()[:70]))
    return c, ex


def scan_chunks(files):
    c = Counter()
    ex = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for idx, row in enumerate(fh):
                d = json.loads(row)
                for line in d["text"].splitlines():
                    for k, p in PATS.items():
                        if p.search(line):
                            c[k] += 1
                            ex.setdefault(k, (d.get("book", "?"), line.strip()[:70]))
                            break
    return c, ex


def report(title, total, counter, examples):
    print(f"== {title} ({total:,} 行/条)")
    for k in LEX:
        name, line = examples.get(k, ("-", "-"))
        print(f"  {counter[k]:>7,}  {k:<14} 例[{name}] {line}")


def main() -> None:
    for stage in ("01_utf8", "02_clean"):
        files = sorted(str(p) for p in (ROOT / "work" / stage).rglob("*.txt"))
        tot = Counter()
        exs = {}
        with ProcessPoolExecutor(12) as pool:
            for c, ex in pool.map(scan_lines, [files[i::12] for i in range(12)]):
                tot += c
                for k, v in ex.items():
                    exs.setdefault(k, v)
        report(f"{stage} {len(files)} 文件", sum(tot.values()), tot, exs)

    ds = [str(ROOT / "work" / "05_dataset" / n) for n in ("train.jsonl", "valid.jsonl")]
    tot = Counter()
    exs = {}
    with ProcessPoolExecutor(12) as pool:
        for c, ex in pool.map(scan_chunks, [ds[i::12] for i in range(12)]):
            tot += c
            for k, v in ex.items():
                exs.setdefault(k, v)
    n_chunk = sum(1 for f in ds for _ in open(f, encoding="utf-8"))
    report(f"train+valid {n_chunk:,} chunk", sum(tot.values()), tot, exs)


if __name__ == "__main__":
    main()
