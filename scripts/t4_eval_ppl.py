#!/usr/bin/env python3
"""t4: 续写能力评估 —— 在 valid.jsonl 上对比 base 与 base+LoRA 的 PPL。"""
import argparse
import json
import math
import os
from collections import defaultdict

import torch
import t_common as T


def genre_of(rec):
    g = rec.get("genre", "?")
    if isinstance(g, (list, tuple)):
        g = "、".join(str(x) for x in g if x)
    return g or "?"


def load_valid(path, per_book, limit):
    by_book = defaultdict(list)
    genre_of_book = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            book = rec.get("book", "?")
            genre_of_book.setdefault(book, genre_of(rec))
            if len(by_book[book]) < per_book:
                by_book[book].append(rec["text"])
    out = [(b, genre_of_book[b], t) for b, ts in by_book.items() for t in ts]
    return out[:limit] if limit else out


def score(model, tokenizer, text, window):
    """teacher-forced：返回 (NLL 之和, token 数)。"""
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    nll, n = 0.0, 0
    for start in range(0, max(0, len(ids) - 1), window):
        seg = ids[start:start + window + 1]
        if len(seg) < 2:
            break
        x = torch.tensor([seg], device=model.device)
        with torch.no_grad():
            logits = model(x).logits[:, :-1, :].float()
        logp = torch.log_softmax(logits, dim=-1).gather(-1, x[:, 1:].unsqueeze(-1)).squeeze(-1)
        nll += -logp.sum().item()
        n += logp.numel()
    return nll, n


def run(label, path, adapter, samples, window, max_tokens):
    tokenizer, model = T.load(path, adapter)
    tot_nll = tot_n = 0.0
    per_genre = defaultdict(lambda: [0.0, 0.0])
    done = 0
    for book, genre, text in samples:
        ids = tokenizer(text, add_special_tokens=False)["input_ids"]
        if max_tokens and len(ids) > max_tokens:
            text = tokenizer.decode(ids[:max_tokens])
        nll, n = score(model, tokenizer, text, window)
        if n == 0:
            continue
        tot_nll += nll
        tot_n += n
        per_genre[genre][0] += nll
        per_genre[genre][1] += n
        done += 1
        if done % 20 == 0:
            print(f"[{label}] {done}/{len(samples)} ppl={math.exp(tot_nll / tot_n):.3f}", flush=True)
    T.unload(model)
    return {"label": label, "chunks": done, "ppl": math.exp(tot_nll / tot_n),
            "by_genre": {g: math.exp(v / n) for g, (v, n) in per_genre.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/Qwen3-4B-Instruct-2507")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--valid", default="work/05_dataset/valid.jsonl")
    ap.add_argument("--per-book", type=int, default=50)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--window", type=int, default=2048)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--out", default="work/08_eval/ppl_report.md")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    samples = load_valid(args.valid, args.per_book, args.limit)
    print(f"eval chunks: {len(samples)}")

    results = [run("base", args.model, None, samples, args.window, args.max_tokens)]
    if args.adapter:
        results.append(run("base+LoRA", args.model, args.adapter, samples, args.window, args.max_tokens))

    lines = ["# 续写 PPL 评估（valid.jsonl，teacher-forced，未计 loss mask）", ""]
    for r in results:
        lines += [f"## {r['label']}：PPL = {r['ppl']:.3f}（{r['chunks']} chunk）", "",
                  "| 题材 | PPL |", "|---|---|"]
        lines += [f"| {g} | {v:.3f} |" for g, v in sorted(r["by_genre"].items(), key=lambda kv: kv[1])]
        lines += [""]
    if len(results) == 2 and results[0]["ppl"]:
        delta = (results[0]["ppl"] - results[1]["ppl"]) / results[0]["ppl"] * 100
        lines.append(f"**LoRA 相对 base 的 PPL 下降：{delta:.1f}%**")
        print(f"LoRA PPL 相对下降 {delta:.1f}%")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("->", args.out)


if __name__ == "__main__":
    main()
