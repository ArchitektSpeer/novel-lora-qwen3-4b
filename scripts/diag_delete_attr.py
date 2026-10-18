#!/usr/bin/env python3
"""删除归因：对 01_utf8 原文逐行复算「整行删除」判据，把每条规则删掉的行取样输出。
用来抓假阳性——规则把正常叙事当广告删了。只读，不改任何文件。
用法: python scripts/diag_delete_attr.py [--json 输出路径]"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s2_clean as S  # noqa: E402
from chapter_heads import parse_header  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "01_utf8"

SENT = re.compile(r"[。！？…”]”?$")
CJK = re.compile(r"[一-鿿]")


def load():
    ad_rules = S.read_rules(S.PATTERNS_FILE)
    in_rules = S.read_rules(S.INLINE_FILE)
    ad_toxic = [(r["text"], re.compile(r["text"])) for r in ad_rules if r["toxic"]]
    in_toxic = [(r["text"], re.compile(r["text"])) for r in in_rules if r["toxic"]]
    ad_live = [(r["text"], re.compile(r["text"])) for r in ad_rules if not r["toxic"]]
    in_body = [(r["text"], re.compile(r["text"])) for r in in_rules if not r["toxic"]]
    return ad_toxic, in_toxic, ad_live, in_body


def scan_file(path: Path):
    ad_toxic, in_toxic, ad_live, in_body = load()
    rows = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return rows
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or parse_header(line) is not None:
            continue
        # 复算 s2 的判据顺序：括号广告块 -> 毒性整行 -> 片段擦除致空
        before = line
        stripped_block = S.RE_BRACKET_AD.sub("", line).strip()
        if stripped_block != before:
            kw = [k for k in ("下载", "电子书", "百度", "贴吧", "棉花糖", "天上掉馅饼", "公众号",
                              "首发", "小说网", "看书网", "奇书网", "整理提供", "全文字",
                              "无弹窗", "广告少", "最新章节", "TXT")
                  if k.lower() in "".join(S.RE_BRACKET_AD.findall(before))]
            rows.append(("bracket", ",".join(kw) or "?", path.name, before))
            line = stripped_block
            if not line:
                continue
        hit = None
        for tag, rules in (("ad-toxic", ad_toxic), ("inline-toxic", in_toxic)):
            if len(line) <= S.TOXIC_MAX and not S.RE_DIALOG.match(line):
                for label, pat in rules:
                    if pat.search(line):
                        hit = (tag, label)
                        break
            if hit:
                break
        if hit:
            rows.append((hit[0], hit[1], path.name, line))
            continue
        if line and len(line) <= 24:
            erased = line
            for label, pat in ad_live + in_body:
                erased = pat.sub("", erased)
            if not erased.strip() and erased.strip() != line:
                rows.append(("frag-empty", "-", path.name, line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "work" / "reports" / "delete_attr.json"))
    args = ap.parse_args()
    files = sorted(SRC.rglob("*.txt"))
    with ProcessPoolExecutor(max_workers=12) as ex:
        all_rows = [r for chunk in ex.map(scan_file, files) for r in chunk]

    by_rule = defaultdict(Counter)
    examples = defaultdict(list)
    for kind, label, book, line in all_rows:
        key = f"{kind}|{label}"
        by_rule[kind][key] += 1
        examples[key].append((book, line))

    out = {"total_deleted_lines": len(all_rows), "rules": {}}
    for kind, counter in by_rule.items():
        for key, n in counter.most_common():
            # 优先展示「像正文」的样本：长、有对话引号或句子结尾、无域名
            cand = sorted(examples[key], key=lambda r: -len(r[1]))
            prose_like = [c for c in cand if len(c[1]) >= 10 and SENT.search(c[1])][:6]
            out["rules"][key] = {"count": n, "samples": prose_like or cand[:3]}
    Path(args.json).write_text(
        re.sub(r"[\u0000-\u0008\u000b-\u001f]", "", __import__("json").dumps(out, ensure_ascii=False, indent=1)),
        encoding="utf-8")

    print(f"复算 01_utf8 {len(files)} 个文件，整行/片段致空删除共 {len(all_rows):,} 行\n")
    for kind in sorted(by_rule):
        print(f"== {kind} ==")
        for key, n in by_rule[kind].most_common(18):
            print(f"{n:>7}  {key[:70]}")
            for book, line in out["rules"][key]["samples"][:3]:
                print(f"          {book[:16]:<18}| {line[:74]}")
    print(f"\n明细: {args.json}")


if __name__ == "__main__":
    main()
