#!/usr/bin/env python3
"""广告残留命中率：对固定毒词表统计 01_utf8 -> 02_clean 的存活量，量化清洗效果。
用法: python scripts/diag_hitrate.py"""
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "work" / "01_utf8"
CLEAN = ROOT / "work" / "02_clean"

LEXICON = {
    "域名/URL": r"(?i)www[.。．]|https?[:：]|[.。．](?:com|net|cc|org|cn|xyz|top|vip)(?![a-z0-9])",
    "手机版阅读网址": r"手机版阅读网址|手机用户请|阅读网址|浏览阅读地址|记住.{0,6}网址|首发域名|最新域名",
    "加入书签/推荐": r"加入书签|推荐本书|收藏本书|阅读记录|下次打开书架|向你的朋友",
    "翻页话术": r"点击下一页|下一页继续阅读|本小章还未完|这章没有结束|后面还有哦|后面更精彩",
    "最快更新/无弹窗": r"最快更新|无弹窗|无广告|全文字|页面清爽|文字首发",
    "求票话术": r"求[^，。\n]{0,6}(月票|推荐票|收藏|打赏|订阅|鲜花|评价票)"
              r"|(月票|推荐票)[^，。\n]{0,6}(加更|支持|砸|投)",
    "站名": r"笔趣阁|笔趣閣|頂點|顶点小说|奇书网|txt80|八零电子书|书客居|文学馆|精华书阁|书海阁|百书屋"
            r"|新笔阁|书掌柜|云来阁|138看书|看书网|看書网|零点看书|棉花糖小说网|书香门第小说网",
    "免责声明": r"知识产权|存储空间.{0,20}网络服务提供者|用户上传之内容|收集整理|版权归.{0,12}(作者|出版社)",
    "百度搜索导流": r"(百度|佰度)搜索|手机下载APP|公众号",
    "书评/报错/更新说明": r"发表书评|书评区|章节错误|章节报错|点此报送|报送后维护|重新刷新页面|更新时间[:：]",
    "未完待续模板": r"如欲知后事如何|支持正版阅读|章节更多",
    "分节阅读": r"分节阅读",
    "HTML实体/标签": r"&#x?[0-9A-Fa-f]{2,4};|</?(div|span|font|b|i)>",
    "转码/阅读导流": r"转码页面|阅读最新章节|最新章节全文阅读",
}
PATS = {k: re.compile(v) for k, v in LEXICON.items()}


def _scan_file(path_str: str) -> Counter:
    total: Counter = Counter()
    text = Path(path_str).read_text(encoding="utf-8", errors="ignore")
    for line in text.split("\n"):
        for k, p in PATS.items():
            if p.search(line):
                total[k] += 1
    return total


def count(root: Path) -> Counter:
    total: Counter = Counter()
    files = [str(f) for f in sorted(root.rglob("*.txt"))]
    with ProcessPoolExecutor(max_workers=12) as ex:
        for c in ex.map(_scan_file, files):
            total.update(c)
    return total


def main() -> None:
    raw = count(RAW)
    clean = count(CLEAN)
    print(f"{'类别':<18}{'清洗前(行)':>12}{'清洗后(行)':>12}{'残留率':>10}")
    for k in LEXICON:
        a, b = raw[k], clean[k]
        rate = f"{(b / a * 100):.2f}%" if a else "-"
        print(f"{k:<18}{a:>12,}{b:>12,}{rate:>10}")
    ta, tb = sum(raw.values()), sum(clean.values())
    print(f"\n命中行合计: {ta:,} -> {tb:,}（清除 {1 - tb / max(ta, 1):.1%}）")


if __name__ == "__main__":
    main()
