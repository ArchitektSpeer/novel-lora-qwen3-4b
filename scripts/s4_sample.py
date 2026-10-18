#!/usr/bin/env python3
"""阶段四辅助：为每本书抽 5 章样本（首/尾/1/3/1/2/2/3），每章截前 1500 字，
写到 work/04_meta/pending/<book>.txt，供小模型标注。
标注结果应存为 work/04_meta/<book_key>.json，字段见 PLAN.md 阶段四。
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "03_chapters"
OUT = ROOT / "work" / "04_meta" / "pending"
PER_CHAPTER = 1500


def main() -> None:
    if not SRC.exists():
        sys.exit("先运行 s3_split_chapters.py")
    OUT.mkdir(parents=True, exist_ok=True)
    random.seed(42)
    n = 0
    for f in sorted(SRC.glob("*.jsonl")):
        chapters = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()]
        if not chapters:
            continue
        idxs = {0, len(chapters) - 1}
        for frac in (1 / 3, 1 / 2, 2 / 3):
            idxs.add(min(int(len(chapters) * frac), len(chapters) - 1))
        parts = [f"书名: {chapters[0]['book']}\t作者: {chapters[0]['author'] or '未知'}"]
        for i in sorted(idxs):
            ch = chapters[i]
            parts.append(
                f"\n=== 第{ch['chapter_idx']}章 《{ch['chapter_title']}》（共{ch['char_count']}字，以下为开头{PER_CHAPTER}字）===\n"
                + ch["text"][:PER_CHAPTER]
            )
        (OUT / f.name.replace(".jsonl", ".txt")).write_text(
            "\n".join(parts), encoding="utf-8"
        )
        n += 1
    print(f"抽样完成: {n} 本书 -> {OUT}")
    print("把每个 txt 喂给小模型（prompt 见 PLAN.md 阶段四），结果存 work/04_meta/<同名>.json")


if __name__ == "__main__":
    main()
