#!/usr/bin/env python3
"""阶段二：规则清洗。work/01_utf8/ -> work/02_clean/，输出 work/reports/s2_report.jsonl

逐行处理：
1. 解 HTML 数字实体（&#x767E;度、&#183;），盗版站用它绕过关键词过滤；
2. 章节头行受保护：只跑标注 @ 的行内规则，擦完为空则回退原行，绝不丢标题；
3. 其余行按「片段擦除」：ad_patterns + inline_patterns 命中只删命中片段，累计擦除量；
4. 擦除量 >=4 字且（占比 >=50% 或只剩 <=24 字）判定整行是广告 -> 删行；否则保留正文；
5. 标注 ! 的毒性词：短行整行删；>120 字的行多半正文为主，只擦片段。
清洗后做空文件与 md5 去重。
"""
import hashlib
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from fnmatch import fnmatch
from pathlib import Path

from chapter_heads import parse_header

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "01_utf8"
OUT = ROOT / "work" / "02_clean"
REPORT = ROOT / "work" / "reports" / "s2_report.jsonl"
PATTERNS_FILE = ROOT / "scripts" / "ad_patterns.txt"
INLINE_FILE = ROOT / "scripts" / "inline_patterns.txt"
EXCLUDE_FILE = ROOT / "scripts" / "exclude.txt"
CIPHER_FILE = ROOT / "scripts" / "cipher_fix.txt"

TOXIC_MAX = 120  # 毒性词行整行删除的长度上限
DROP_MIN = 4     # 至少擦掉这么多字才可能判定整行是广告
SALVAGE_MIN_HEAD = 40  # 毒性词落在行尾时，前面够长且干净的正文只砍尾巴不整行删
CJK_END = re.compile(r"[一-鿿”』」]$")


def load_exclude() -> set[str]:
    if not EXCLUDE_FILE.exists():
        return set()
    return {
        l.strip()
        for l in EXCLUDE_FILE.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    }


def normalize_flags(text: str) -> str:
    """行首 (?i) 放进 union 的 (?:...) 里会报 global flag 位置错，改成局部分支 (?i:...)"""
    if text.startswith("(?i)"):
        return "(?i:" + text[4:] + ")"
    if text.startswith("(?is)"):
        return "(?is:" + text[5:] + ")"
    return text


def read_rules(path: Path) -> list[dict]:
    """行首标志：@ 对章节头也生效；! 毒性词（短行整行删）。
    注意正则自身不要以 ! 或 @ 开头，需要负向前瞻时用 (?:!) 包一层。"""
    if not path.exists():
        return []
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        flags = set()
        while line[:1] in ("@", "!"):
            flags.add(line[0])
            line = line[1:]
        line = normalize_flags(line)
        rules.append({"text": line, "header_safe": "@" in flags, "toxic": "!" in flags})
    return rules


def compile_rules(rules: list[dict]):
    """-> (普通规则 union, [(标签, 编译式)], 章节头安全 union, 毒性词 union)

    毒性词只做「整行判定」，绝不当片段擦除用：像「书友」这种词嵌在长正文里，
    擦掉会损坏句子，所以长行遇到毒性词一律保留原文。
    """
    normal = [(r["text"], re.compile(r["text"])) for r in rules if not r["toxic"]]
    union = re.compile("|".join(f"(?:{p.pattern})" for _, p in normal)) if normal else None
    safe_live = [re.compile(r["text"]) for r in rules if r["header_safe"] and not r["toxic"]]
    safe_union = (
        re.compile("|".join(f"(?:{p.pattern})" for p in safe_live)) if safe_live else None
    )
    toxic = [re.compile(r["text"]) for r in rules if r["toxic"]]
    toxic_union = (
        re.compile("|".join(f"(?:{p.pattern})" for p in toxic)) if toxic else None
    )
    return union, normal, safe_union, toxic_union


def load_cipher() -> list[tuple[str, re.Pattern, str]]:
    """cipher_fix.txt: glob<TAB>正则<TAB>替换（形近字/数字防盗替换的逐书修复）"""
    if not CIPHER_FILE.exists():
        return []
    fixes = []
    for line in CIPHER_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        fixes.append((parts[0], re.compile(parts[1]), parts[2]))
    return fixes


# 数字字符实体：&#x767E; / &#26360;，盗版站用它藏站名
RE_ENTITY = re.compile(r"&#(x[0-9A-Fa-f]{1,6}|\d{1,6});?")
# 双向隔离符：藏水印用，解完实体才会露出来
RE_BIDI = re.compile("[\u00ad\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\ufeff\ufffe]")
RE_DOTRUN = re.compile(r"(?<![0-9A-Za-z])\.{2,}(?![0-9A-Za-z])")
RE_DUP_PERIOD = re.compile(r"。{2,}")
RE_LEAD_BARE_Q = re.compile(r"^\?\s+")
# 防盗/机翻痕迹：中文之间用半角标点还跟一个空格（"总监, 森野太郎"），归一成全角
RE_HALF_PUNCT = re.compile(r"(?<=[一-鿿。！？，；：、])[.!?:;,\s]*([,:;])[.!?:;,\s]*(?=[一-鿿])")
HALF_TO_FULL = {",": "，", ":": "：", ";": "；"}
# 摘完广告常留下「，。」「。」这类标点相撞；只留前一个
RE_PUNCT_CLASH = re.compile(r"。，|，。")
# 「第288章初战异端者」补上书名头统一用的空格
RE_HEAD_SPACE = re.compile(r"(第[0-9０-９零一二三四五六七八九十百千两]{1,9}章)(?=[一-鿿])")
# 「第一百五十三章 1368」「第三百二十一章 18」= 盗版站把页号/编号挂在标题位（实测全库 12 处，去尾后不与同卷章号相撞）
RE_HEAD_NUM_TAIL = re.compile(r"(?<=章)[\s 　]+[0-9０-９]{2,}$")
# 站点前缀粘在章节头前面（`全文字无广告第一千二百五十章跨界战`）：parse_header 认不出整行，
# 毒性规则会把标题连同广告一起删掉，所以先剥前缀再认一次
RE_HEAD_PREFIX = re.compile(r"^[^，。！？;；\n]{0,14}?(?=第[0-9０-９零一二三四五六七八九十百千两]{1,12}[章节回])")
AD_PREFIX_HINT = re.compile(r"全文字|无广告|无弹窗|纯文字|手打|百书屋|看书网|小说网|138看书|笔趣阁|更新")
# 括号广告块：正文行尾常挂一整块站点话术，先摘掉这块再判毒性词，否则整行正文会被连带删掉
RE_BRACKET_AD = re.compile(
    r"[(（【\[][^\)）】\n]{0,140}?"
    r"(?:首发|小说网|最新章节|广告少|无弹窗|更新最快|更新快|最快更新|页面清爽|想看的书|全文字"
    r"|一定要好评|百度|贴吧|棉花糖|[Tt][Xx][Tt]|电子书|下载|看书网|奇书网|整理提供|文字首发"
    r"|[0-9]{2,4}看书[.。_\-]|天上掉馅饼|炫酷手机|微信添加朋友|公众号|独家故事|超多好看"
    r"|未完待续|本章完|投推荐票|求月票)"
    r"[^\)）】\n]{0,140}[)）】\]]"
)
# 盗版站常把广告块的上括号留着、下括号被换行吃掉（" [看本书最新章节请到$>>>棉_._.花_._.糖"）
RE_OPEN_AD = re.compile(
    r"[(（【\[]\s*[^\n]{0,140}?"
    r"(?:小说网|看书网|奇书网|最新章节|最快更新|更新最快|无弹窗|广告少|页面清爽|全文字|文字首发"
    r"|整理提供|电子书|txt下载|TXT下载|一定要好评|百度搜索|请收藏|记住本站)"
    r"[^\n，。！？]{0,40}$"
)


def decode_entities(line: str) -> tuple[str, int]:
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        s = m.group(1)
        try:
            cp = int(s[1:], 16) if s[0] in "xX" else int(s)
        except ValueError:
            return m.group(0)
        if not 0 < cp < 0x110000:
            return m.group(0)
        ch = chr(cp)
        n += 1
        return "" if unicodedata.category(ch) in ("Cc", "Cf") else ch

    return RE_ENTITY.sub(repl, line), n


# 采集站把域名写成 "ＷwＷ。xｘｘ。ＣＯＭ" / "w w w . t x t 8 0. c c" / "www。し" 这类
# 全角+插空格的形式来绕过关键词过滤，所以先按「非中文片段」切出候选，
# 再把片段做 NFKC 归一并去空格，认出域名/URL 才删除原片段。
URL_RUN = re.compile(
    "[A-Za-z0-9０-９Ａ-Ｚａ-ｚ"
    "\u3000 。．，、,.~/!@#$%&*()（）\\[\\]<>‘’'\"`?:：_^-]{4,}"
)
TLD_RE = re.compile(r"[a-z0-9]\.(com|net|cc|vip|org|cn|la|me|top|xyz|info)(?![a-z0-9])")


def looks_like_domain(collapsed: str) -> bool:
    if "http" in collapsed or "www" in collapsed:
        return True
    return bool(TLD_RE.search(collapsed))


RE_HEADISH = re.compile(r"^(第[0-9０-９零一二三四五六七八九十百千两]{1,7}[章节卷篇部]|【\d{1,5}】|\d{1,4}[.、])")
HAS_ALNUM = re.compile(r"[A-Za-z0-9０-９Ａ-Ｚａ-ｚ]")
RE_DIALOG = re.compile(r'^["“」』《〈]')
# 正文行被擦掉尾巴之后通常仍是完整句子；广告碎片擦完只剩个话术短句，用这个区分两者
RE_SENT_END = re.compile(r"[。！？…”』」』»]$")
RE_LEAD_PUNCT = re.compile(r"^[，。、；：,.!?！？…—·\-\*\"'“”‘’（）()\[\]【】<>《》「」『」]")
# 正常正文允许的字符：汉字、字母数字、空白、中文全角标点。
# 其余（半角标点、Ω┡∟．★ 等）在水印乱码行里才会成串出现。
PROSE_OK = re.compile(
    "[一-鿿A-Za-z0-9 \t"
    "，。！？；：、（）“”‘’…—·《》【】〈〉「」『』｛｝￥％]"
)


def is_low_info_line(line: str) -> bool:
    """水印行特征：含字母数字，且堆了 3 个以上正文不该出现的符号"""
    if len(line) >= 60 or RE_HEADISH.match(line):
        return False
    if not HAS_ALNUM.search(line):
        return False
    odd = len(line) - len(PROSE_OK.findall(line))
    return odd >= 3


def scrub_domains(line: str) -> tuple[str, int]:
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        collapsed = unicodedata.normalize("NFKC", m.group(0))
        collapsed = re.sub("[。，、`,·＿]+", ".", collapsed)
        collapsed = re.sub(r"\s+", "", collapsed)
        collapsed = re.sub(r"[^a-z0-9.]+", "", collapsed.lower())
        if len(collapsed) >= 6 and looks_like_domain(collapsed):
            n += 1
            return ""
        return m.group(0)

    return URL_RUN.sub(repl, line), n


STRAY_CLOSERS = (("）", "（"), (")", "("), ("】", "【"), ("」", "「"), ("』", "『"))
STRAY_OPENERS = (("（", "）"), ("(", ")"), ("【", "】"), ("「", "」"), ("『", "』"), ("[", "]"))


def fix_stray_closers(line: str) -> str:
    """广告块套在正文行里时，摘完常剩一只没人配对的括号（两侧都可能是广告残留）；正文句末标点留着"""
    changed = True
    while changed and len(line) > 1:
        changed = False
        for closer, opener in STRAY_CLOSERS:
            if line and line[-1] == closer and line.count(opener) < line.count(closer):
                line = line[:-1].rstrip()
                if line.endswith("."):  # 采集站残留的「观.」尾巴
                    line = line[:-1].rstrip()
                changed = True
        for opener, closer in STRAY_OPENERS:
            if line and line[-1] == opener and line.count(opener) > line.count(closer):
                line = line[:-1].rstrip()
                changed = True
    return line


def clean_text(text, ad, inline, cipher, rel: str) -> tuple[str, dict, int]:
    ad_union, ad_live, _, ad_toxic = ad
    in_union, _, in_safe, in_toxic = inline
    hits: dict[str, int] = {}
    kept = []
    removed = 0

    for glob, pat, rep in cipher:
        if fnmatch(rel, glob) or fnmatch(Path(rel).name, glob):
            text, n_sub = pat.subn(rep, text)
            if n_sub:
                hits[f"cipher:{pat.pattern}->{rep}"] = hits.get(f"cipher:{pat.pattern}->{rep}", 0) + n_sub

    for raw_line in text.split("\n"):
        line = raw_line.strip().replace("　", " ").strip()
        if not line:
            continue
        line, n_ent = decode_entities(line)
        if n_ent:
            hits["entity:numeric-decoded"] = hits.get("entity:numeric-decoded", 0) + n_ent
        n_bidi = len(RE_BIDI.findall(line))
        if n_bidi:
            line = RE_BIDI.sub("", line)
            hits["ctrl:bidi/zero-width"] = hits.get("ctrl:bidi/zero-width", 0) + n_bidi
        line = line.strip()
        if not line:
            continue

        header = parse_header(line) is not None
        if not header:
            m = RE_HEAD_PREFIX.match(line)
            if m and AD_PREFIX_HINT.search(m.group(0)) and parse_header(line[m.end():]) is not None:
                hits["rescue:ad-prefixed-header"] = hits.get("rescue:ad-prefixed-header", 0) + 1
                line = line[m.end():].strip()
                header = True
        head_src = line
        gone = 0

        if header:
            # 章节头只跑 @ 标注过的行内规则（求票括注类），其余规则一律跳过
            if in_safe:
                before = len(line)
                line, n = in_safe.subn("", line)
                gone += before - len(line)
                if n:
                    hits["inline:header-safe"] = hits.get("inline:header-safe", 0) + n
            if HAS_ALNUM.search(line):
                line, _n = scrub_domains(line)
            line = line.strip()
            if not line:  # 绝不让章节头消失
                line = head_src
            elif RE_HEAD_SPACE.search(line):
                line = RE_HEAD_SPACE.sub(r"\1 ", line)
                hits["title:space-after-chapter"] = hits.get("title:space-after-chapter", 0) + 1
            n_tail = len(RE_HEAD_NUM_TAIL.findall(line))
            if n_tail:
                line = RE_HEAD_NUM_TAIL.sub("", line).strip()
                hits["title:numeric-tail"] = hits.get("title:numeric-tail", 0) + n_tail
            hits["guard:chapter_header"] = hits.get("guard:chapter_header", 0) + 1
            kept.append(line)
            continue

        before = len(line)
        line = RE_BRACKET_AD.sub("", line).strip()
        line = RE_OPEN_AD.sub("", line).strip()
        gone = before - len(line)
        if gone:
            hits["ad:bracket-block"] = hits.get("ad:bracket-block", 0) + gone
            if not line:
                removed += 1
                continue
        # 毒性词 + 行不够长 => 整行是站点话术；长行以正文为主，原样保留
        toxic_hit = None
        for tag, u in (("ad", ad_toxic), ("inline", in_toxic)):
            if u:
                m = u.search(line)
                if m and len(line) <= TOXIC_MAX and not RE_DIALOG.match(line):
                    toxic_hit = (f"{tag}:{m.group(0)[:20]}", m)
                    break
        if toxic_hit:
            label, m = toxic_hit
            # 广告整段挂在行尾时，前半截往往是真正文：位置够靠后且前面干净就只砍尾巴
            head = line[: m.start()].strip()
            # 广告尾巴常差半句（"…的山。一秒记住本站地址"）：往前找最近的句末标点，只留完整的一句
            cut = max(head.rfind(ch) for ch in "。！？…")
            if cut + 1 >= 12 and len(head) - cut - 1 <= 12 and not HAS_ALNUM.search(head[: cut + 1]):
                head = head[: cut + 1]
            clean_end = bool(CJK_END.search(head) or RE_SENT_END.search(head))
            long_enough = (
                len(head) >= SALVAGE_MIN_HEAD
                or (len(head) >= 12 and bool(RE_SENT_END.search(head)))
            )
            # 广告自成一个句子（正文以句号收尾后另起）时，不必再要求行够长、位置过半
            sent_boundary = len(head) >= 12 and head[-1] in "。！？…" and not HAS_ALNUM.search(head)
            if not HAS_ALNUM.search(head) and (
                    sent_boundary
                    or (len(line) >= 60 and m.start() >= len(line) * 0.55
                        and clean_end and long_enough)):
                hits["salvage:toxic-tail"] = hits.get("salvage:toxic-tail", 0) + 1
                gone += len(line) - len(head)
                line = head
            else:
                hits["toxic-line"] = hits.get("toxic-line", 0) + 1
                hits[f"toxic:{label}"] = hits.get(f"toxic:{label}", 0) + 1
                removed += 1
                continue

        if HAS_ALNUM.search(line):
            before = len(line)
            line, n_dom = scrub_domains(line)
            if n_dom:
                hits["domain:spaced/fullwidth"] = hits.get("domain:spaced/fullwidth", 0) + n_dom
                gone += before - len(line)

        if ad_union and line:
            for label, pat in ad_live:
                before = len(line)
                line, n = pat.subn("", line)
                if n:
                    hits[f"ad:{label}"] = hits.get(f"ad:{label}", 0) + n
                    gone += before - len(line)
                if not line:
                    break
        if in_union and line:
            before = len(line)
            line, n = in_union.subn("", line)
            if n:
                hits["inline:union"] = hits.get("inline:union", 0) + n
                gone += before - len(line)
            # 防盗插字的括号广告块（(奇*书*网…整*理*提*供)）要等 * 被剥掉后才露出关键词
            before = len(line)
            line = RE_BRACKET_AD.sub("", line).strip()
            line = RE_OPEN_AD.sub("", line).strip()
            if len(line) != before:
                hits["ad:bracket-block-after-unwrap"] = hits.get("ad:bracket-block-after-unwrap", 0) + 1
                gone += before - len(line)

        line = line.strip()
        if not line:
            removed += 1
            continue
        # 残渣以标点开头 = 广告摘完剩下的半截话；成句、不以标点开头、或剥出章节标题 = 正文，留住
        prose_residue = (
            RE_SENT_END.search(line) and not RE_LEAD_PUNCT.match(line)
        ) or parse_header(line) is not None
        if gone >= DROP_MIN and not RE_DIALOG.match(line) and not prose_residue and (
            gone >= len(line) or len(line) <= 24
        ):
            hits["drop:ad-dominant"] = hits.get("drop:ad-dominant", 0) + 1
            removed += 1
            continue
        line = RE_LEAD_BARE_Q.sub("", line)
        line = RE_DOTRUN.sub("……", line)
        line = RE_DUP_PERIOD.sub("。", line).strip()
        n_half = len(RE_HALF_PUNCT.findall(line))
        if n_half:
            hits["punct:halfwidth->fullwidth"] = hits.get("punct:halfwidth->fullwidth", 0) + n_half
            line = RE_HALF_PUNCT.sub(lambda m: HALF_TO_FULL[m.group(1)], line)
        n_clash = len(RE_PUNCT_CLASH.findall(line))
        if n_clash:
            hits["punct:clash->single"] = hits.get("punct:clash->single", 0) + n_clash
            line = RE_PUNCT_CLASH.sub("，", line)
        line = fix_stray_closers(line)
        if not line:
            removed += 1
            continue
        if is_low_info_line(line):
            hits["rule:low_info_line"] = hits.get("rule:low_info_line", 0) + 1
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept) + "\n", hits, removed


_WORKER: dict = {}


def _init_worker() -> None:
    _WORKER["ad"] = compile_rules(read_rules(PATTERNS_FILE))
    _WORKER["in"] = compile_rules(read_rules(INLINE_FILE))
    _WORKER["cipher"] = load_cipher()


def _process_one(rel_str: str) -> dict:
    rel = Path(rel_str)
    text = (SRC / rel).read_text(encoding="utf-8")
    cleaned, hits, removed = clean_text(
        text, _WORKER["ad"], _WORKER["in"], _WORKER["cipher"], rel_str
    )
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(cleaned, encoding="utf-8")
    return {
        "file": str(rel),
        "md5": hashlib.md5(cleaned.encode("utf-8")).hexdigest(),
        "chars_out": len(cleaned),
        "lines_removed": removed,
        "hits": hits,
    }


def main() -> None:
    if not SRC.exists():
        sys.exit("先运行 s1_to_utf8.py")
    excluded = load_exclude()
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    rels = [str(f.relative_to(SRC)) for f in sorted(SRC.rglob("*.txt"))]
    skipped = [r for r in rels if r in excluded]
    todo = [r for r in rels if r not in excluded]

    workers = min(12, (os.cpu_count() or 2))
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as pool:
        results = list(pool.map(_process_one, todo, chunksize=1))

    seen_md5: dict[str, str] = {}
    dup_files = short_files = 0
    total_removed = 0
    pattern_totals: dict[str, int] = {}
    with REPORT.open("w", encoding="utf-8") as rep:
        for r in skipped:
            rep.write(json.dumps({"file": r, "status": "excluded"}, ensure_ascii=False) + "\n")
        for res in results:
            total_removed += res["lines_removed"]
            for k, v in res["hits"].items():
                pattern_totals[k] = pattern_totals.get(k, 0) + v
            status = "ok"
            if res["md5"] in seen_md5:
                status = f"dup_of:{seen_md5[res['md5']]}"
                dup_files += 1
                (OUT / res["file"]).unlink(missing_ok=True)
            elif res["chars_out"] < 1000:
                status = "too_short"
                short_files += 1
                (OUT / res["file"]).unlink(missing_ok=True)
            else:
                seen_md5[res["md5"]] = res["file"]
            rep.write(json.dumps({**res, "status": status}, ensure_ascii=False) + "\n")

    print(f"清洗完成: {len(results)} 个文件（{workers} 进程）, 共删 {total_removed} 行")
    print(f"重复文件: {dup_files}, 过短剔除: {short_files}, 排除: {len(skipped)}")
    print(f"输出: {OUT}")
    print("\n各规则命中排行:")
    for label, cnt in sorted(pattern_totals.items(), key=lambda x: -x[1])[:30]:
        print(f"  {cnt:>8}  {label}")


if __name__ == "__main__":
    main()
