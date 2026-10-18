#!/usr/bin/env python3
"""网文校对 demo：长文本按段落切成训练时的长度（≤1200 字）逐段校对，输出修正文本与改动清单。

用法（在项目根目录执行）：
  命令行：./venv-train/bin/python scripts/demo_proofread.py --input dirty.txt --output fixed.txt
  管道：  cat dirty.txt | ./venv-train/bin/python scripts/demo_proofread.py
  网页：  ./venv-train/bin/python scripts/demo_proofread.py --web [--port 7860]   # 需 pip install gradio
"""
import argparse
import difflib
import html
import re
import sys

import t_common as T

# 训练时校对样本最常用的指令（三选一中的第一条）
INSTRUCTION = "请校对以下小说文本，修正其中的错别字、乱码和标点错误，输出修正后的完整原文。不要解释，不要增删内容。"
SEG_MAX = 1200          # 训练样本正文 700~1500 字，切段落在这个区间内效果最好
MAX_LEN_DRIFT = 0.15    # 输出长度偏离输入超过 15% 视为模型跑偏，该段保留原文
SENT_END = re.compile(r"(?<=[。！？…”』」])")


def split_long_line(line, limit):
    """超长单行（源文件粘段）按句末标点再切，实在切不开就硬切。"""
    parts, buf = [], ""
    for sent in SENT_END.split(line):
        while len(sent) > limit:
            parts.append(buf + sent[:limit - len(buf)])
            sent, buf = sent[limit - len(buf):], ""
        if buf and len(buf) + len(sent) > limit:
            parts.append(buf)
            buf = ""
        buf += sent
    if buf:
        parts.append(buf)
    return parts


def segment(text, limit=SEG_MAX):
    """按行聚合成 ≤limit 字的段，段与段之间不丢、不加任何字符（含换行）。"""
    segs, buf = [], ""
    for line in text.splitlines(keepends=True):
        pieces = split_long_line(line, limit) if len(line) > limit else [line]
        for p in pieces:
            if buf and len(buf) + len(p) > limit:
                segs.append(buf)
                buf = ""
            buf += p
    if buf:
        segs.append(buf)
    return segs


class Proofreader:
    def __init__(self, model_path, adapter):
        self.tokenizer, self.model = T.load(model_path, adapter)

    def fix_segment(self, seg):
        body = seg.strip("\n")
        if not body.strip():
            return seg, False
        lead = seg[:len(seg) - len(seg.lstrip("\n"))]
        tail = seg[len(seg.rstrip("\n")):]
        prompt = T.render(self.tokenizer, INSTRUCTION, body)
        budget = len(self.tokenizer(body, add_special_tokens=False)["input_ids"]) + 64
        out = T.generate(self.tokenizer, self.model, prompt, max_new_tokens=budget, temperature=0.0)
        if abs(len(out) - len(body)) > MAX_LEN_DRIFT * len(body):
            return seg, True
        return lead + out + tail, False

    def run(self, text, progress=None):
        segs = segment(text)
        fixed, skipped = [], 0
        for i, seg in enumerate(segs):
            out, bad = self.fix_segment(seg)
            skipped += bad
            fixed.append(out)
            if progress:
                progress(i + 1, len(segs))
        return "".join(fixed), skipped, len(segs)


def changes(src, dst, ctx=6):
    """逐处改动：(位置, 原文片段, 修正片段, 上下文)。"""
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, src, dst, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        around = src[max(0, i1 - ctx):i1] + "【" + src[i1:i2] + "→" + dst[j1:j2] + "】" + src[i2:i2 + ctx]
        out.append((i1, src[i1:i2], dst[j1:j2], around.replace("\n", "⏎")))
    return out


def diff_html(src, dst):
    parts = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, src, dst, autojunk=False).get_opcodes():
        a, b = html.escape(src[i1:i2]), html.escape(dst[j1:j2])
        if tag == "equal":
            parts.append(a)
            continue
        if a:
            parts.append(f'<del style="background:#fdd;color:#a00">{a}</del>')
        if b:
            parts.append(f'<ins style="background:#dfd;color:#060;text-decoration:none">{b}</ins>')
    body = "".join(parts).replace("\n", "<br>")
    return f'<div style="line-height:1.9;font-size:15px;white-space:pre-wrap">{body}</div>'


def run_cli(pr, args):
    text = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
    fixed, skipped, total = pr.run(
        text, lambda i, n: print(f"[{i}/{n}]", file=sys.stderr, flush=True))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(fixed)
    else:
        sys.stdout.write(fixed)
    diff = changes(text, fixed)
    print(f"\n共 {total} 段，改动 {len(diff)} 处，跑偏回退 {skipped} 段", file=sys.stderr)
    for pos, _, _, around in diff[:args.show]:
        print(f"  @{pos}: {around}", file=sys.stderr)
    if len(diff) > args.show:
        print(f"  …其余 {len(diff) - args.show} 处略", file=sys.stderr)


def run_web(pr, args):
    import gradio as gr

    def proofread(text, progress=gr.Progress()):
        if not text.strip():
            return "", "", "请输入文本"
        fixed, skipped, total = pr.run(text, lambda i, n: progress(i / n, desc=f"第 {i}/{n} 段"))
        diff = changes(text, fixed)
        info = f"共 {total} 段，改动 {len(diff)} 处" + (f"，{skipped} 段输出跑偏已保留原文" if skipped else "")
        return fixed, diff_html(text, fixed), info

    with gr.Blocks(title="网文校对") as ui:
        gr.Markdown("## 网文校对（Qwen3-4B + LoRA）\n修正错别字、标点、防盗插字、拼音替字、`**` 屏蔽等。长文本自动分段。")
        with gr.Row():
            src = gr.Textbox(label="待校对文本", lines=20)
            dst = gr.Textbox(label="校对结果", lines=20)
        btn = gr.Button("校对", variant="primary")
        info = gr.Markdown()
        view = gr.HTML(label="改动对照")
        btn.click(proofread, inputs=src, outputs=[dst, view, info])
    ui.queue(default_concurrency_limit=1).launch(server_name=args.host, server_port=args.port)


def main():
    ap = argparse.ArgumentParser(description="网文校对 demo")
    ap.add_argument("--model", default="models/Qwen3-4B-Instruct-2507")
    ap.add_argument("--adapter", default="work/07_train/std")
    ap.add_argument("--input", help="待校对文本文件，缺省读 stdin")
    ap.add_argument("--output", help="写出修正文本，缺省打到 stdout")
    ap.add_argument("--show", type=int, default=30, help="命令行模式最多列出多少处改动")
    ap.add_argument("--web", action="store_true", help="启动 Gradio 网页界面")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7860)
    args = ap.parse_args()

    pr = Proofreader(args.model, args.adapter)
    run_web(pr, args) if args.web else run_cli(pr, args)


if __name__ == "__main__":
    main()
