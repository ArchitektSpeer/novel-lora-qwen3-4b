#!/usr/bin/env python3
"""QC：对最终 train/valid chunk 统计站点话术残留率（chunk 级命中率，验收线 <2%）。
按类目输出命中数与样例，只读诊断。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DS = ROOT / "work" / "05_dataset"

CATEGORIES = {
    "站名": r"笔趣阁|笔趣閣|顶点小说|奇书网|138看书|看书网|看书冈|全文字下载|文字首发"
            r"|八零\s*电子\s*书|棉花糖小说网|书香门第小说网|云来阁|新笔阁|书海阁|txt80|7017k",
    "域名/URL": r"(?i)www\.|https?[:：]|[\w.]+\.(com|net|cc|org|cn|xyz|top|vip|club)\b",
    "手机版/下载导流": r"手机版[^，。\n]{0,10}(?:阅读|网址|地址|下载)|手机站[^，。\n]{0,8}(?:阅读|地址|网址)"
                      r"|app下载|下载app|txt下载|电子书下载|转码页面|客户端[^，。\n]{0,8}(?:阅读|更新最快)",
    "更新/无弹窗话术": r"最快更新|无弹窗|最新章节全文阅读|更新最快的是|首发[^，。\n]{0,6}网站|阅读最新章节",
    "求票话术": r"求月票|求推荐票|求订阅|求收藏|求鲜花|打赏支持|月票支持|保底月票|投一次票"
              r"|首订.{0,6}(冲|拜|求)|求个收藏|求张票",
    "百度搜索导流": r"百度搜索|搜索引擎|搜索.{0,12}(?:小说网|本站|这本书|最新章节)|(?:记住|本站).{0,12}(?:网址|域名)",
    "免责声明": r"(?:本站|网站|网盘|用户上传)[^，。\n]{0,16}知识产权|版权归[^，。\n]{0,10}(作者|出版社).{0,8}所有"
              r"|收集(?:并)?整理自网络|仅作学习交流使用|免责(?:声明)?|用户上传之内容|本站不.{0,10}(承担|负责)",
    "翻页话术": r"点击下一页|下一页继续阅读|后面还有哦|后面更精彩|最新章节请(?:到|访问)",
    "加入书签/推荐": r"加入书签|收藏本站|推荐给朋友|顶部按钮",
    "书评/报错/更新说明": r"章节错误,?报错|点此举报|书评区|作者的话|作者感言|求点评|这段话不用看|凑够字数",
    "未完待续模板": r"(?m:[（(]?(?:未完待续|本章完|连载中)[)）]?[。！!，,]?$)|全文.{0,6}(?:完结|下载到)"
                 r"|(?:未完待续|小说更好)[^，。\n]{0,8}(?:请搜索|更新更快)",
    "HTML实体/标签": r"(?i)&[a-z#0-9]{2,7};|</?[a-z][a-z0-9]{0,9}\b[^>]{0,24}>",
    "VIP章节标记残留": r"(?i:vip)最\s*新\s*章\s*节",
}
COMPILED = {k: re.compile(v) for k, v in CATEGORIES.items()}


def scan(path: Path):
    total = 0
    hits = Counter()
    cats = Counter()
    samples = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            total += 1
            text = d["text"]
            matched = [c for c, pat in COMPILED.items() if pat.search(text)]
            if matched:
                hits[d["book"]] += 1
                for c in matched:
                    cats[c] += 1
                if len(samples) < 25:
                    frag = next(m.group(0) for pat in COMPILED.values() if (m := pat.search(text)))
                    head = text.split("\n")[1 if text.startswith("《") else 0][:60]
                    samples.append((matched, d["book"], frag, head))
    return total, cats, samples, hits


def main() -> None:
    files = [p for p in (DS / "train.jsonl", DS / "valid.jsonl") if p.exists()]
    if not files:
        print(f"找不到 {DS} 下的 jsonl，先跑 s5")
        sys.exit(1)
    all_total = 0
    all_cats: Counter = Counter()
    all_books: Counter = Counter()
    samples = []
    for p in files:
        total, cats, s, books = scan(p)
        all_total += total
        all_cats.update(cats)
        all_books.update(books)
        samples.extend(s)
    n_bad = sum(all_books.values())
    print(f"{','.join(p.name for p in files)} 共 {all_total:,} chunk，含站点话术的 chunk {n_bad:,}"
          f"（{n_bad / all_total:.2%}）\n")
    for c, n in all_cats.most_common():
        print(f"{n:>7}  {c}")
    print("\n== 残留最多的书 Top 15 ==")
    for b, n in all_books.most_common(15):
        print(f"{n:>6}  {b}")
    print("\n== 命中样例 ==")
    for matched, book, frag, head in samples[:20]:
        print(f"   {matched} | {book} | 命中 {frag!r} | {head}")


if __name__ == "__main__":
    main()
