#!/usr/bin/env python3
"""毒性词误伤体检：对 01_utf8 里会被「短行整行删」命中的行，按关键词分组打印样本，
用来判断某个毒性词是该保留、该加框，还是该降级成行内擦除。
用法: python3 scripts/diag_toxic_collateral.py [关键词 ...]
"""
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "work" / "01_utf8"
TOXIC_MAX = 120

DEFAULT_KEYS = ["无广告", "全文字", "纯文字", "更新快", "最快更新", "无弹窗", "一秒记住", "换榜", "小爆发",
                "放心砸来", "收票员", "更新感言", "请收藏本站", "阅读是一种享受"]

AD_HINT = re.compile(
    r"(?:www|http|[.。](?:com|net|cc|org|cn|xyz|top|vip)|笔趣阁|奇书网|顶点|书海阁|书客居|手机版|电脑"
    r"|客户端|收藏|推荐|月票|推荐票|打赏|章节|域名|网址|搜索|无弹窗|最快|本站|txt|TXT)")


def work(files):
    cnt = Counter()
    coll = defaultdict(list)
    for f in files:
        p = Path(f)
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            s = line.strip()
            if not s or len(s) > TOXIC_MAX:
                continue
            for k in KEYS:
                if k in s:
                    cnt[k] += 1
                    if not AD_HINT.search(s):
                        coll[k].append((p.name, s))
                    break
    return cnt, coll


KEYS = [k for k in (sys.argv[1:] or DEFAULT_KEYS)]


def main() -> None:
    files = sorted(str(p) for p in RAW.rglob("*.txt"))
    total = Counter()
    pool_coll = defaultdict(list)
    with ProcessPoolExecutor(12) as pool:
        for cnt, coll in pool.map(work, [files[i::12] for i in range(12)]):
            total += cnt
            for k, rows in coll.items():
                pool_coll[k].extend(rows)
    print(f"扫描 {len(files)} 文件，毒性词 ≤{TOXIC_MAX} 字短行命中：\n")
    for k in KEYS:
        n = total[k]
        c = len(pool_coll[k])
        print(f"### {k}  命中 {n:,}  其中「不像广告」（无站点线索词）{c:,}" + (f"  → 疑似误伤 {c / n * 100:.0f}%" if n else ""))
        for name, s in pool_coll[k][:6]:
            print(f"     ? [{name}] {s[:80]}")
        print()


if __name__ == "__main__":
    main()
