"""章节头识别，s2（豁免判定）与 s3（切分）共用，避免两处规则漂移。"""
import re

CN_NUM = "0-9０-９零一二三四五六七八九十百千两"
RE_CHAPTER = re.compile(
    rf"^(\d{{1,4}}[.、][ 　]?)?(第[{CN_NUM}]{{1,7}}[卷集篇部][ 　].{{1,15}}?[ 　])?"
    rf"第[{CN_NUM}]{{1,7}}[章节回][ 　:：．.、\-]?.{{0,30}}$"
)
RE_HASH_CHAPTER = re.compile(rf"^#{{1,4}}\s*第[{CN_NUM}]{{1,7}}[章节回卷部].{{0,30}}#{{0,4}}\s*$")
RE_SPECIAL = re.compile(r"^(序章|序|楔子|引子|前言|终章|尾声|番外.{0,20}|外传.{0,20})$")
RE_EQ = re.compile(r"^[-=]{2,}\s*(.{1,35}?)\s*[-=]{0,4}$")
RE_PREFIX_CHAPTER = re.compile(rf"^[一-鿿].{{0,10}}[ 　]第[{CN_NUM}]{{1,7}}章[ 　:：].{{0,25}}$")
RE_BRACKET = re.compile(r"^【\d{1,5}】.{0,25}$")
RE_NUM = re.compile(r"^\d{1,4}[.、][ 　]?.{1,25}$")
RE_VOL_NUM = re.compile(rf"^((第[{CN_NUM}]{{1,7}}卷|\d{{1,3}}) )?[一-鿿].{{0,12}} \d{{1,4}}$")
RE_CHAP_NUM = re.compile(rf"第([{CN_NUM}]{{1,7}})章")
RE_NUM_LEAD = re.compile(r"^(\d{1,4})[.、]")
RE_NUM_TAIL = re.compile(r" (\d{1,4})$")

_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000}


def cn_to_int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    t = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if t.isdigit():
        return int(t)
    total, cur = 0, 0
    for ch in s:
        if ch in _DIGITS:
            cur = _DIGITS[ch]
        elif ch in _UNITS:
            total += (cur if cur else 1) * _UNITS[ch]
            cur = 0
        else:
            return None
    return total + cur if (total or cur or s == "零") else None


RE_TITLE_SEP = re.compile(rf"^(第[{CN_NUM}]{{1,7}}[章节回卷])[ 　]*[.。，,、．\-—:：]+[ 　]*")
RE_TITLE_PREFIX = re.compile(r"^(正文卷?|卷首语?|分卷阅读)[ 　]+")


def clean_title(title: str) -> str:
    """把「第80章 .多余温柔」「正文 第47章 X」这类脏标题规整成「第80章 多余温柔」「第47章 X」"""
    title = RE_TITLE_PREFIX.sub("", title)
    title = RE_TITLE_SEP.sub(r"\1 ", title)
    return re.sub(r"[ 　]{2,}", " ", title).strip()


def parse_header(line: str) -> str | None:
    """是章节头则返回规范化标题，否则 None"""
    if len(line) > 40:
        return None
    if RE_CHAPTER.match(line) or RE_HASH_CHAPTER.match(line):
        return clean_title(re.sub(r"^章节目录\s*", "", line.strip("#").strip()))
    if RE_SPECIAL.match(line):
        return line
    m = RE_EQ.match(line)
    if m and re.search(rf"第[{CN_NUM}]+章", m.group(1)):
        return clean_title(m.group(1).strip())
    if RE_PREFIX_CHAPTER.match(line):
        return clean_title(re.sub(r"^章节目录\s*", "", line))
    if RE_BRACKET.match(line) or RE_NUM.match(line) or RE_VOL_NUM.match(line):
        return clean_title(line)
    return None


def extract_num(title: str) -> int | None:
    m = RE_CHAP_NUM.search(title)
    if m:
        return cn_to_int(m.group(1))
    m = RE_NUM_LEAD.match(title) or RE_NUM_TAIL.search(title)
    if m:
        return int(m.group(1))
    if RE_BRACKET.match(title):
        d = re.search(r"\d+", title)
        return int(d.group(0)) if d else None
    return None
