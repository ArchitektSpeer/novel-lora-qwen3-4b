#!/usr/bin/env python3
"""第五轮规则补丁：把 60-chunk 模型复核回收的站点话术写进 ad_patterns / inline_patterns。
只改这两个规则文件；每条替换都带断言，打完做正则编译自检。
用法: python3 scripts/patch_rules6.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AD = ROOT / "scripts" / "ad_patterns.txt"
IN = ROOT / "scripts" / "inline_patterns.txt"

MARK = "第五轮"

# 分隔线类规则漏了全角连字符 －（U+FF0D），起点「－－－－－－题外话－－－－－－」因此存活
DASH_EDITS = [
    (r"^[-=*_~─━•·…．.\s]{5,}$", r"^[-=*_~─━•·…．.－\s]{5,}$"),
    (r"^[-*=~─━•·．._\s]{1,4}$", r"^[-*=~─━•·．._－\s]{1,4}$"),
    (r"^[―﹘‒–—]{2,}$", r"^[―﹘‒–—－]{2,}$"),
]

AD_NEW = r"""
!(?:[0-9]秒记住|[一二三]秒记住[：:])
!放心砸来
!月票已经掉到
!换榜(?![一-鿿])
!收票员
!(?:(?:二|三|四|五)更求票|最后一[次天]求票|继续求票)
!更新感言
!小爆发
!(?:站内无任何广告|无错章节将持续在|最新最快章节，请登陆|还请大家收藏和推荐|阅读是一种享受)
!请收藏本站
!(?:必应搜索|请必应)
^搜狗$
^[。，,、\s]*题外话[。，,、\s]*$
"""

IN_NEW = r"""
[0-9]秒记住[^，。\n]{0,16}
[-—－]?[<〈（(\[]?\s*[书書]\s+[海]\s*[阁閣]\s*[>〉）)\]]?[-—－]?\s*网?
(?:最新最快章节，请登陆|站内无任何广告|(?:无错|最新)章节将持续在[^，。\n]{0,10}更新|还请大家收藏和推荐[^，。\n]{0,10}|阅读是一种享受[，,]?建议您收藏)
(?:如果您?觉得)?还不错就请收藏本站[，,]?[^，。\n]{0,22}
(?:[a-zA-Z]{1,6}|器)[：:]无广告、全文字、更
无广告、全文字、更(?:新快)?
无弹窗广告全文字(?:txt下载)?
全文字无广告
无弹广告
请?收藏(?:网址|域名|地址)[^，。\n]{0,18}
(?<=[。！!？?”’])\s*搜狗(?=$|[\s”’])
(?<=[。，,])请收藏(?=[。，,])
[，,]?请?分享(?:给|到)[^，。\n]{0,8}(?:好友|书友|更多人)
"""


def new_lines(block: str) -> list[str]:
    out = []
    for l in block.strip("\n").splitlines():
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        body = s.lstrip("!@")
        if body.startswith("(?i)"):
            body = "(?i:" + body[4:] + ")"
        try:
            re.compile(body)
        except re.error as e:
            raise SystemExit(f"规则不可编译 {s!r}: {e}")
        out.append(s)
    return out


def patch(path: Path, edits, block: str) -> int:
    text = path.read_text(encoding="utf-8")
    assert MARK not in text, f"{path.name}: 已打过第五轮补丁"
    for old, new in edits:
        assert text.count(old) == 1, f"{path.name}: {old!r} 出现 {text.count(old)} 次"
        text = text.replace(old, new)
    lines = new_lines(block)
    comment = f"\n# --- {MARK}：60 chunk 模型复核回收的话术 ---\n"
    path.write_text(text.rstrip("\n") + "\n" + comment + "\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def main() -> None:
    n_ad = patch(AD, DASH_EDITS, AD_NEW)
    n_in = patch(IN, [], IN_NEW)
    print(f"ad_patterns +{n_ad} 条（含 3 处分隔线补漏），inline_patterns +{n_in} 条")
    sys.path.insert(0, str(ROOT / "scripts"))
    import s2_clean as S
    ad, inl = S.compile_rules(S.read_rules(AD)), S.compile_rules(S.read_rules(IN))
    print(f"编译通过：ad {len(S.read_rules(AD))} 条（毒性 {sum(r['toxic'] for r in S.read_rules(AD))}）"
          f" / inline {len(S.read_rules(IN))} 条（头安全 {sum(r['header_safe'] for r in S.read_rules(IN))}）")


if __name__ == "__main__":
    import sys
    main()
