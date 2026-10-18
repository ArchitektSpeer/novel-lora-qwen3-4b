#!/usr/bin/env python3
"""对比 01_utf8 / 02_clean / 训练集里「行尾没有句末标点」的比例，
用来回答「是不是清洗吃掉了标点」这个问题。
用法: python3 scripts/diag_line_endings.py
"""
import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
END_OK = re.compile(r"[。！？…?”’』」）)】]$"

KEYS = ["总行", "无句末标点", "疑似误伤"]


def scan_lines(files):
    c = Counter()
    ex = []
    for f in files:
        p = Path(f)
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            s = line.strip()
            if len(s) < 8:
                continue
            c["总行"] += 1
            if not END_OK.search(s):
                c["无句末标点"] += 1
                if len(ex) < 3:
                    ex.append((p.name, s[-30:]))
    return c, ex


def scan_chunks(files):
    c = Counter()
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for row in fh:
                t = json.loads(row)["text"]
                for line in t.split("\n"):
                    s = line.strip()
                    if len(s) < 8:
                        continue
                    c["总行"] += 1
                    if not END_OK.search(s):
                        c["无句末标点"] += 1
    return c, []


def run(stage, fn, files):
    tot = Counter()
    ex = []
    with ProcessPoolExecutor(12) as pool:
        for c, rows in pool.map(fn, [files[i::12] for i in range(12)]):
            tot += c
            if len(ex) < 3:
                ex.extend(rows[:3 - len(ex)])
    n, bad = tot["总行"], tot["无句末标点"]
    print(f"{stage:<12} 有效行 {n:>12,}   行尾无句末标点 {bad:>10,}  ({bad / n * 100:.2f}%)")
    for name, s in ex:
        print(f"      例[{name}] …{s}")


def main() -> None:
    for stage in ("01_utf8", "02_clean"):
        files = sorted(str(p) for p in (ROOT / "work" / stage).rglob("*.txt"))
        run(stage, scan_lines, files)
    ds = [str(ROOT / "work" / "05_dataset" / n) for n in ("train.jsonl", "valid.jsonl")]
    run("05_dataset", scan_chunks, ds)


if __name__ == "__main__":
    main()
