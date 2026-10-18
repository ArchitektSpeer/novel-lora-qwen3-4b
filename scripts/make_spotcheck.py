#!/usr/bin/env python3
"""从最终训练集随机抽样，切成 3 份人工/QC 可读的批次：work/reports/spotcheck/batchN.txt"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAIN = ROOT / "work" / "05_dataset" / "train.jsonl"
OUT = ROOT / "work" / "reports" / "spotcheck"
N_PER_BATCH = 12
PER_STRATUM = 20
BATCHES = 5
SEED = 20261017


def main() -> None:
    lines = TRAIN.read_text(encoding="utf-8").splitlines()
    random.seed(SEED)
    # 分层：头/中/尾各抽一段，头尾最容易出现广告和切分问题
    picks = []
    for lo, hi in ((0, len(lines) // 3), (len(lines) // 3, len(lines) * 2 // 3), (len(lines) * 2 // 3, len(lines))):
        picks += random.sample(range(lo, hi), PER_STRATUM)
    picks.sort()
    OUT.mkdir(parents=True, exist_ok=True)
    for b in range(BATCHES):
        buf = []
        for i in picks[b * N_PER_BATCH:(b + 1) * N_PER_BATCH]:
            d = json.loads(lines[i])
            buf.append(f"{'=' * 70}\n# index={i} book={d['book']!r} author={d.get('author')!r} "
                       f"genre={d.get('genre')!r} quality={d.get('quality')!r} len={len(d['text'])}\n{'=' * 70}\n")
            buf.append(d["text"] + "\n\n")
        (OUT / f"batch{b + 1}.txt").write_text("".join(buf), encoding="utf-8")
        print(f"batch{b + 1}.txt: {len(buf) // 2} chunks")
    print(f"共 {len(picks)} chunks / {BATCHES} 批")


if __name__ == "__main__":
    main()
