#!/usr/bin/env python3
"""一次性诊断：统计 QC 报告的每个疑似泄漏在语料里的真实规模，用于决定要不要写规则。"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "01_utf8"

CHECKS = {
    "html_hex_entity": re.compile(r"&#x[0-9A-Fa-f]{2,4};"),
    "cjk_dot_cjk": re.compile(r"(?<=[一-鿿])\.(?=[一-鿿])"),
    "cjk_pipe_cjk": re.compile(r"(?<=[一-鿿])\|(?=[一-鿿])"),
    "quote_then_fw_punct": re.compile(r"(?<=[一-鿿])['\"](?=[，。！？；：、])"),
    "cjk_then_dot_punct": re.compile(r"(?<=[一-鿿])\*(?=[，。！？；：、])"),
    "dash2015_run": re.compile(r"―{2,}|(?<=[一-鿿])―(?!―)"),
    "tilde_ff5e_run": re.compile(r"～{2,}"),
    "ascii_ellipsis": re.compile(r"\.{3,}"),
    "dup_period": re.compile(r"。{2,}"),
    "leading_bare_q": re.compile(r"^\?\s+\S", re.M),
    "comma_period": re.compile(r"，。"),
    "authored_xiaoshuo": re.compile(r"(?i)(txt80|笔趣阁|飘天|顶点小说|69hz|biquge)"),
}

CJK = re.compile(r"[一-鿿]")
CIPHER = ["自勺", "修土", "灵姓", "摹然", "一曰", "交锚", "大6", "鞋峰", "罗命"]

tot = Counter()
files = Counter()
per_book = defaultdict(Counter)
cipher_files = defaultdict(Counter)

paths = sorted(SRC.rglob("*.txt"))
for p in paths:
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        continue
    book = "/".join(p.relative_to(SRC).parts[:2])
    for name, pat in CHECKS.items():
        n = len(pat.findall(text))
        if n:
            tot[name] += n
            files[name] += 1
            per_book[book][name] += n
    for w in CIPHER:
        n = text.count(w)
        if n >= 20:
            cipher_files[w][book] = n

print(f"扫描 {len(paths)} 个文件\n")
print(f"{'泄漏特征':<22}{'命中次数':>10}{'涉及文件':>10}")
for name, n in tot.most_common():
    print(f"{name:<22}{n:>10}{files[name]:>10}")

print("\n== 形近字/防盗替换词（>=20 次的书）==")
for w, books in sorted(cipher_files.items(), key=lambda x: -sum(x[1].values())):
    total = sum(books.values())
    top = ", ".join(f"{b}:{c}" for b, c in books.most_common(4))
    print(f"{w:<6} 共{total:>7}  书数{len(books):>3}  {top}")

print("\n== 每类泄漏 Top4 书 ==")
for name in tot:
    top = sorted((per_book[b][name] for b in per_book), reverse=True)
    best = max(per_book.items(), key=lambda kv: kv[1][name])
    print(f"{name:<22} 峰值 {best[0]} = {best[1][name]}")
