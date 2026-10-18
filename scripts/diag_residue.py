#!/usr/bin/env python3
"""残留挖掘：把 02_clean 里的短行归一成模板并计数，出现次数越多的模板越可能是批量水印/广告。
只读诊断，不改任何文件。"""
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "02_clean"

RE_HEAD = re.compile(r"^第[{0}]{{1,7}}[章节回]".format("0-9零一二三四五六七八九十百千两"))


def template(line: str) -> str:
    t = re.sub(r"[0-9０-９Ａ-Ｚａ-ｚA-Za-z]+", "#", line)
    return t


def main() -> None:
    counter: Counter[str] = Counter()
    where: dict[str, Counter[str]] = {}
    for f in sorted(SRC.rglob("*.txt")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for line in text.split("\n"):
            n = len(line)
            if n < 6 or n > 46:
                continue
            if line.count("　") == len(line):
                continue
            tpl = template(line)
            counter[tpl] += 1
            where.setdefault(tpl, Counter())[f.name] += 1

    print(f"扫描 {len(list(SRC.rglob('*.txt')))} 个清洗文件\n")
    print("重复度最高的短行模板（次数>=15，可能是残留水印/广告族）：")
    shown = 0
    for tpl, c in counter.most_common(400):
        if c < 15 or shown >= 45:
            break
        top = ", ".join(f"{b}:{k}" for b, k in where[tpl].most_common(3))
        print(f"{c:>7}  {tpl!r:<46}  {top[:78]}")
        shown += 1

    print("\n含网址/站点特征的短行（Top 25）：")
    web: Counter[str] = Counter()
    for tpl, c in counter.items():
        if re.search(r"#\.(com|net|cc|org|cn|xyz|top|vip)|www|http", tpl.lower()) and c >= 2:
            web[tpl] = c
    for tpl, c in web.most_common(25):
        print(f"{c:>7}  {tpl!r}")


if __name__ == "__main__":
    main()
