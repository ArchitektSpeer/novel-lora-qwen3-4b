#!/usr/bin/env python3
"""章节标题污染体检：扫描 03_chapters 的 chapter_title，按话术形态分类计数并给样本。
用法: python3 scripts/diag_title_pollution.py
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CH = ROOT / "work" / "03_chapters"

LEX = {
    "括注里的求票/收藏": r"[（(【\[][^）)】\n]{0,14}(?:收藏|推荐|月票|推荐票|投票|打赏|首订|追读|保底|加更|求票)[^）)】\n]{0,14}[)）】\]]",
    "标题尾巴话术": r"(?:更新完毕|更新时间[:：]?|求月票|求推荐|求收藏|月票|推荐票|打赏|求订阅|请收藏|收藏本站|请分享)$",
    "站点/域名痕迹": r"(?i)www|https?|[.。](?:com|net|cc|org|vip|top)|小说网|看书网|笔趣阁|书海阁|书客居|顶点小说|(?<![0-9章])[0-9]{2,4}看书|txt",
    "作者留言块": r"(?:新书|上架|完结|完本|感言|请假条)[^，。]{0,10}(?:通告|首秀|爆更|五更|四更|三更|求票)?|今天[一二三四五六]?更|附[^，。]{0,6}通告",
    "HTML/乱码符号": r"(?i)<[^>]{1,20}>|&[a-z]{2,5};|&#\d+;|[＿□■※∷]{1,2}",
}
PATS = {k: re.compile(v) for k, v in LEX.items()}


def main() -> None:
    total = 0
    books = 0
    cnt = Counter()
    examples = {}
    worst = Counter()
    for p in sorted(CH.rglob("*.jsonl")):
        books += 1
        with p.open(encoding="utf-8") as fh:
            for row in fh:
                d = json.loads(row)
                t = d.get("chapter_title") or ""
                total += 1
                for k, pat in PATS.items():
                    if pat.search(t):
                        cnt[k] += 1
                        worst[d["book"]] += 1
                        examples.setdefault(k, []).append((d["book"], t))
                        break
    print(f"{books} 本 / {total:,} 个章节标题，带污染形态的 {sum(cnt.values()):,} 个"
          f"（{sum(cnt.values())/total*100:.2f}%）\n")
    for k in LEX:
        print(f"{cnt[k]:>7,}  {k}")
        for b, t in examples.get(k, [])[:4]:
            print(f"         [{b}] {t[:56]}")
    print("\n按书统计（标题形态可疑条数 Top 12）")
    for b, c in worst.most_common(12):
        print(f"   {c:>6}  {b}")


if __name__ == "__main__":
    main()
