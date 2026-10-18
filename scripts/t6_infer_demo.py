#!/usr/bin/env python3
"""t6: 推理演示 —— 各跑一次自动补全和一次校对。"""
import argparse
import difflib
import json
import random

import t_common as T
from demo_proofread import INSTRUCTION


def pick_continuation(valid_path, frac=0.6):
    rows = [json.loads(l) for l in open(valid_path, encoding="utf-8") if l.strip()]
    row = random.choice(rows)
    text = row["text"]
    cut = int(len(text) * frac)
    nl = text.find("\n", cut)
    head = text[:nl + 1] if nl != -1 else text[:cut]
    return row.get("genre", ""), head, text[nl + 1:] if nl != -1 else text[cut:]


def make_proofread_case(holdout_path):
    """从校对 holdout 随机取一条（脏文本, 标准答案, 注入点数）。"""
    rows = [json.loads(l) for l in open(holdout_path, encoding="utf-8") if l.strip()]
    row = random.choice([r for r in rows if r.get("density") == "medium"] or rows)
    dirty, clean = row["input"], row["output"]
    n = sum(1 for op in difflib.SequenceMatcher(None, clean, dirty, autojunk=False).get_opcodes()
            if op[0] != "equal")
    return dirty, clean, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/Qwen3-4B-Instruct-2507")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--mode", choices=["both", "continue", "proofread"], default="both")
    ap.add_argument("--prompt-file", default=None, help="自备上文，跳过随机抽样")
    ap.add_argument("--proofread-file", default=None, help="自备待校对文本，跳过 holdout 抽样")
    ap.add_argument("--holdout", default="work/06_sft/proofread/test_holdout.jsonl")
    ap.add_argument("--max-new", type=int, default=400)
    args = ap.parse_args()

    random.seed(20261017)
    tokenizer, model = T.load(args.model, args.adapter)

    if args.mode in ("both", "continue"):
        if args.prompt_file:
            genre, head, tail = "", open(args.prompt_file, encoding="utf-8").read(), ""
        else:
            genre, head, tail = pick_continuation("work/05_dataset/valid.jsonl")
        prompt = T.render(tokenizer, f"这是一部{genre}小说，请续写下面的片段，保持文风一致。", head)
        out = T.generate(tokenizer, model, prompt, max_new_tokens=args.max_new, temperature=0.8, top_p=0.9,
                         repetition_penalty=1.08, no_repeat_ngram_size=8)
        print("=" * 30, "续写", "=" * 30)
        print("【上文结尾】", head[-160:].strip())
        print("\n【模型续写】", out[:1200])
        if tail:
            print("\n【真实下文】", tail[:240].strip())

    if args.mode in ("both", "proofread"):
        if args.proofread_file:
            dirty, clean, n_err = open(args.proofread_file, encoding="utf-8").read(), "", 0
        else:
            dirty, clean, n_err = make_proofread_case(args.holdout)
        prompt = T.render(tokenizer, INSTRUCTION, dirty)
        out = T.generate(tokenizer, model, prompt,
                         max_new_tokens=min(1600, len(tokenizer(dirty, add_special_tokens=False)["input_ids"]) + 32),
                         temperature=0.0)
        print("\n" + "=" * 30, f"校对（注入 {n_err} 处错误）" if clean else "校对", "=" * 30)
        print("【脏文本】", dirty[:220])
        print("\n【模型输出】", out[:220])
        if not clean:
            return
        print("\n【标准答案】", clean[:220])
        print("\n完全一致:", out.strip() == clean.strip())
        if out.strip() != clean.strip():
            sm = difflib.SequenceMatcher(None, clean.strip(), out.strip())
            print("相似度:", round(sm.ratio(), 5))
            shown = 0
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag != "equal" and shown < 5:
                    print(f"  {tag} @{i1}: 标准={clean.strip()[i1:i2]!r} 模型={out.strip()[j1:j2]!r}")
                    shown += 1


if __name__ == "__main__":
    main()
