#!/usr/bin/env python3
"""t5: 校对能力评估 —— 在 test_holdout 上统计纠错率、字符准确率与误改率。"""
import argparse
import difflib
import json
import os
import random
from collections import defaultdict

import t_common as T


def error_spans(clean, dirty):
    """注入点在 clean 坐标系下的区间；tag 区分替换/删除与纯插入。"""
    spans = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, clean, dirty).get_opcodes():
        if tag == "equal":
            continue
        spans.append((i1, i2, clean[i1:i2], dirty[j1:j2]))
    return spans


def covered_flags(clean, model_out):
    """clean 每个字符是否被模型原样还原。"""
    flags = [False] * len(clean)
    for tag, i1, i2, _, _ in difflib.SequenceMatcher(None, clean, model_out).get_opcodes():
        if tag == "equal":
            for i in range(i1, i2):
                flags[i] = True
    return flags


def evaluate_sample(row, model_out):
    clean, dirty = row["output"], row["input"]
    flags = covered_flags(clean, model_out)
    matched = sum(flags)
    res = {
        "exact": model_out == clean,
        "char_acc": matched / max(1, len(clean)),
        "input_char_acc": sum(covered_flags(clean, dirty)) / max(1, len(clean)),
        "err_total": 0, "err_fixed": 0,
    }
    for i1, i2, ctext, dtext in error_spans(clean, dirty):
        if i1 == i2:
            continue
        res["err_total"] += 1
        if all(flags[i1:i2]):
            res["err_fixed"] += 1
    return res


def stratified(rows, limit, seed=20261017):
    by_density = defaultdict(list)
    for r in rows:
        by_density[r.get("density", "?")].append(r)
    rng = random.Random(seed)
    picked = []
    buckets = sorted(by_density)
    per = max(1, limit // len(buckets))
    for d in buckets:
        pool = by_density[d]
        rng.shuffle(pool)
        picked += pool[:per]
    rng.shuffle(picked)
    return picked[:limit] if len(picked) > limit else picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/Qwen3-4B-Instruct-2507")
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--holdout", default="work/06_sft/proofread/test_holdout.jsonl")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", default="work/08_eval/proofread_report.md")
    ap.add_argument("--dump", default="work/08_eval/proofread_samples.jsonl")
    args = ap.parse_args()

    random.seed(20261017)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    rows = [json.loads(l) for l in open(args.holdout, encoding="utf-8") if l.strip()]
    rows = stratified(rows, args.limit)
    print(f"eval samples: {len(rows)}")

    tokenizer, model = T.load(args.model, args.adapter)
    agg = defaultdict(lambda: defaultdict(float))
    dump = open(args.dump, "w", encoding="utf-8")
    for n, row in enumerate(rows, 1):
        prompt = T.render(tokenizer, row["instruction"], row["input"])
        budget = len(tokenizer(row["output"], add_special_tokens=False)["input_ids"]) + 32
        out = T.generate(tokenizer, model, prompt, max_new_tokens=min(1600, budget), temperature=0.0)
        m = evaluate_sample(row, out)
        d = row.get("density", "?")
        agg[d]["n"] += 1
        agg[d]["err_total"] += m["err_total"]
        agg[d]["err_fixed"] += m["err_fixed"]
        agg[d]["char_acc"] += m["char_acc"]
        agg[d]["input_char_acc"] += m["input_char_acc"]
        agg[d]["exact"] += 1 if m["exact"] else 0
        if d == "clean":
            agg[d]["false_change"] += 1 - m["char_acc"]
        dump.write(json.dumps({"density": d, "input": row["input"], "clean": row["output"],
                               "model": out, **m}, ensure_ascii=False) + "\n")
        if n % 20 == 0:
            print(f"[{n}/{len(rows)}] char_acc={agg[d]['char_acc']/agg[d]['n']:.4f}", flush=True)
    dump.close()

    lines = ["# 校对评估（test_holdout 分层抽样）", "",
             "| 密度 | 样本 | 注入点 | 纠错率 | 字符准确率 | 输入字符准确率 | 完全一致 | 误改率 |",
             "|---|---|---|---|---|---|---|---|"]
    tot = defaultdict(float)
    for d in ["light", "medium", "heavy", "clean"]:
        if d not in agg:
            continue
        a = agg[d]
        err_rate = a["err_fixed"] / a["err_total"] if a["err_total"] else float("nan")
        fc = a.get("false_change", 0.0) / a["n"] if d == "clean" else float("nan")
        lines.append(f"| {d} | {int(a['n'])} | {int(a['err_total'])} | {err_rate:.3f} | "
                     f"{a['char_acc']/a['n']:.4f} | {a['input_char_acc']/a['n']:.4f} | "
                     f"{a['exact']/a['n']:.3f} | {fc if d=='clean' else 0:.4f} |")
        for k in ("n", "err_total", "err_fixed", "char_acc"):
            tot[k] += a[k]
    lines.append(f"\n**总体纠错率 = {tot['err_fixed']/tot['err_total']:.3f}**；"
                 f"平均字符准确率 = {tot['char_acc']/tot['n']:.4f}")
    lines.append(f"\n明细样本见 {args.dump}（供人工抽检对拍）")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("->", args.out)


if __name__ == "__main__":
    main()
