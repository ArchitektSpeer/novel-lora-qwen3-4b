#!/usr/bin/env python3
"""QC 辅助：把 chunk 里命中站点话术的原句连上下文挖出来并归一成模板，
用来决定哪些残留需要「行内擦除」（长正文行里粘着的广告，整行删除策略碰不到）。只读诊断。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DS = ROOT / "work" / "05_dataset"

sys.path.insert(0, str(ROOT / "scripts"))
from diag_chunk_adrate import CATEGORIES  # noqa: E402

COMPILED = {k: re.compile(v) for k, v in CATEGORIES.items()}


def norm(s: str) -> str:
    s = re.sub(r"[0-9０-９A-Za-zａ-ｚＡ-Ｚ]+", "#", s)
    return re.sub(r"\s+", " ", s)


def main() -> None:
    tpl: dict[str, Counter[str]] = {c: Counter() for c in COMPILED}
    raw: dict[str, str] = {}
    total = 0
    for name in ("train.jsonl", "valid.jsonl"):
        p = DS / name
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                total += 1
                text = d["text"]
                for cat, pat in COMPILED.items():
                    for m in pat.finditer(text):
                        lo = max(0, m.start() - 45)
                        hi = min(len(text), m.end() + 45)
                        seg = text[lo:hi].replace("\n", "⏎")
                        t = norm(seg)
                        tpl[cat][t] += 1
                        raw.setdefault(f"{cat}|{t}", f"{d['book']}: {seg}")

    print(f"扫描 {total} 个 chunk\n")
    for cat in COMPILED:
        c = tpl[cat]
        if not c:
            continue
        print(f"########## {cat}  命中片段 {sum(c.values())}，去重模板 {len(c)} ##########")
        for t, n in c.most_common(12):
            print(f"  {n:>5}  {t[:150]}")
            print(f"         eg {raw[f'{cat}|{t}'][:170]}")
        print()


if __name__ == "__main__":
    main()
