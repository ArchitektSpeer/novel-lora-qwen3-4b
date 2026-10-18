#!/usr/bin/env python3
"""阶段三：章节切分 + 分卷合并去重。work/02_clean/ -> work/03_chapters/<book>.jsonl

- 同目录下「书名+数字」的分卷（仙逆1/仙逆2/仙逆）自动归为一组，按文件名序处理，
  章节按标题与内容哈希双重去重，取并集
- 每行输出: {book, author, source, chapter_idx, chapter_title, text, char_count}
- 报告: work/reports/s3_report.jsonl（章节数异常、序号断档、去重数量）
"""
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "02_clean"
OUT = ROOT / "work" / "03_chapters"
REPORT = ROOT / "work" / "reports" / "s3_report.jsonl"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chapter_heads import extract_num, parse_header  # noqa: E402

RE_VOL_SUFFIX = re.compile(r"[(（]\d+[)）]$|[0-9０-９]+$")
# 采集站爱在文件名里塞版本/站名标记，书名会原样进每个 chunk 的书头，必须擦干净
RE_BOOK_JUNK = re.compile(
    r"[《》]|[(（\[][^\r\n]{0,12}(校对版|全集|全本|完结|完本|精校|修订|番外|无错)"
    r"|(?i:txt80)|(?i:[a-z0-9_\-]*[.\-_]?(?:com|net|cc|org|cn|la|vip|xyz|top)(?![a-z]))"
    r"|笔趣阁|顶点小说|电子书|下载"
)
RE_BOOK_VER_TAIL = re.compile(
    r"(全集|合集|全本|完本|完结版|完结|精校版|精校|校对版|校对|修订版|修订|无错版|无错|番外版|番外)+\s*$"
)
RE_AUTHOR_LINE = re.compile(
    r"^\s*[^:：\n]{0,20}?作\s*者\s*[:：]\s*(\S.{0,23}?)\s*$"
    r"|^\s*([一-鿿·]{2,12})\s*著\s*$"
)
RE_SECTION_ONLY = re.compile(r"^(?:.{0,14}\s)?分节阅读\s*\d+$")


def clean_book_name(name: str, author: str | None = None) -> str:
    out = RE_BOOK_JUNK.sub("", name)
    out = re.sub(r"[-_\s]*(作者|著)[:：]?\s*[\u4e00-\u9fffA-Za-z]{1,12}\s*$", "", out)
    if author:
        out = re.sub(rf"\s*[(（]\s*{re.escape(author)}\s*[）)]\s*$", "", out)
    # 「学霸的黑科技系统-晨星LL」把作者缀在书名后；哪一段认得出作者就留另一段
    if "-" in out:
        head, _, tail = out.rpartition("-")
        h, t = head.strip(), tail.strip()
        if author and t == author:
            out = h
        elif author and h == author:
            out = t
        elif head and re.fullmatch(r"[一-鿿A-Za-z]{1,12}", t):
            out = h
    out = RE_BOOK_VER_TAIL.sub("", out)
    return out.strip(" -_—·\t()（）[]【】") or name


def head_author_hint(files: list[Path]) -> str | None:
    """书名净化要先知道作者（判断连字符/括号里是书名还是作者），只读书档头 20K 字"""
    for f in files:
        with f.open(encoding="utf-8", errors="ignore") as fh:
            head = fh.read(20000)
        # 「会说话的肘子-英雄联盟之灾变时代」：正文里被《》包住的那段是书名，另一段就是作者
        stem = f.stem
        if "-" in stem:
            a, _, t = stem.rpartition("-")
            if a.strip() and t.strip() and re.search(rf"《{re.escape(t.strip())}》", head) \
                    and not re.search(rf"《{re.escape(a.strip())}》", head):
                return a.strip()
        name = infer_author(head, f.relative_to(SRC))
        if name:
            return name
    return None


def infer_author(text: str, rel: Path) -> str | None:
    """优先用书里的署名行，目录名只是兜底（爱叫目录常是错的「我爱吃西红柿」）
    窗口取头 200 行 + 尾 120 行：《书名》作者：X 这类署名有时出现在卷首/后记"""
    lines = text.split("\n")
    for line in lines[:200] + lines[-120:]:
        s = line.strip()
        if not s or s[0] in "“”\"『「":
            continue
        m = RE_AUTHOR_LINE.match(s)
        if not m:
            continue
        raw = m.group(1) or m.group(2)
        if raw is None:
            continue
        name = re.sub(r"[《》「」【】\[\]]", "", raw).strip(" \t:：.。、-—")
        name = re.split(r"[\s　]", name)[0][:16]
        if not (1 < len(name) <= 16) or re.search(r"[，。！？;；:：]|全集|TXT|txt|下载|小说网|电子书|作者", name):
            continue
        return name
    parts = rel.parts
    if parts[0] == "0" and len(parts) >= 3:
        return parts[1]
    return None  # 1/ 目录结构不可靠，留给阶段四标注补全


def merge_section_chapters(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """「分节阅读 12」多数是章内小节标记，合并回上一章；
    但如果一本书绝大多数标题就是分节阅读（蚀月纯黑/次元诸天壁那类），它就是真章节号，保留。"""
    if not items:
        return items
    n_sec = sum(1 for t, _ in items if RE_SECTION_ONLY.match(t))
    if n_sec == 0 or n_sec > len(items) * 0.5:
        return items
    merged: list[list[str]] = []
    for title, body in items:
        if RE_SECTION_ONLY.match(title) and merged:
            merged[-1][1].append(body)
        else:
            merged.append([title, [body]])
    return [(t, "\n".join(x for x in b if x)) for t, b in merged]


def split_chapters(text: str) -> list[tuple[str, str]]:
    """返回 [(章节标题, 正文)]，卷首无标题内容记为 ('卷首', ...)（过短则丢弃）"""
    chapters: list[tuple[str, list[str]]] = []
    cur_title: str | None = None
    cur_lines: list[str] = []
    for line in text.split("\n"):
        title = parse_header(line.strip())
        if title is not None:
            if cur_title is not None or cur_lines:
                chapters.append((cur_title or "卷首", cur_lines))
            cur_title = title
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_title is not None or cur_lines:
        chapters.append((cur_title or "卷首", cur_lines))
    result = []
    for title, lines in chapters:
        body = "\n".join(l for l in lines if l.strip())
        if title == "卷首" and len(body) < 200:
            continue
        result.append((title, body))
    return result


def norm_hash(text: str) -> str:
    norm = re.sub(r"\s+", "", text)
    return hashlib.md5(norm.encode("utf-8")).hexdigest()


def group_key(rel: Path) -> tuple[str, str]:
    stem = rel.stem
    stem = re.sub(r"[(（]\d+[)）]$", "", stem)
    stripped = RE_VOL_SUFFIX.sub("", stem)
    if len(stripped) < 2:
        stripped = stem
    return (str(rel.parent), stripped)


def main() -> None:
    if not SRC.exists():
        sys.exit("先运行 s2_clean.py")
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for f in sorted(SRC.rglob("*.txt")):
        groups[group_key(f.relative_to(SRC))].append(f)

    stats = {
        "books": 0, "chapters": 0, "chars": 0,
        "dup_chapters": 0, "anomaly_books": [],
    }
    with REPORT.open("w", encoding="utf-8") as rep:
        for (parent, book_raw), files in sorted(groups.items()):
            # 文件名进书头，会污染每一个 chunk；但 out_name 仍用原始名，保证 04_meta 能对上
            hint = head_author_hint(files)
            book = clean_book_name(book_raw, hint)
            seen_title: set[str] = set()
            seen_content: set[str] = set()
            out_name = re.sub(r'[\\/:*?"<>|]', "_", f"{parent}__{book_raw}") + ".jsonl"
            out_path = OUT / out_name
            n_ch = n_dup = total_chars = 0
            chap_nums: list[int] = []
            author = hint
            with out_path.open("w", encoding="utf-8") as out:
                for f in sorted(files, key=lambda p: p.stem):
                    rel = f.relative_to(SRC)
                    text = f.read_text(encoding="utf-8")
                    author = author or infer_author(text, rel)
                    for title, body in merge_section_chapters(split_chapters(text)):
                        key_title = re.sub(r"\s+", "", title)
                        h = norm_hash(body)
                        if key_title in seen_title or h in seen_content:
                            n_dup += 1
                            continue
                        seen_title.add(key_title)
                        seen_content.add(h)
                        n_ch += 1
                        total_chars += len(body)
                        num = extract_num(title)
                        if num is not None:
                            chap_nums.append(num)
                        out.write(
                            json.dumps(
                                {
                                    "book": book,
                                    "author": author,
                                    "source": str(rel),
                                    "chapter_idx": n_ch,
                                    "chapter_title": title,
                                    "text": body,
                                    "char_count": len(body),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
            if n_ch == 0:
                out_path.unlink()
                continue
            gaps = 0
            if chap_nums:
                s = sorted(set(chap_nums))
                gaps = sum(1 for a, b in zip(s, s[1:]) if b - a > 1)
            anomaly = n_ch < 10 or n_ch > 5000 or total_chars < 20000
            if anomaly:
                stats["anomaly_books"].append(f"{parent}/{book}: {n_ch}章 {total_chars}字")
            stats["books"] += 1
            stats["chapters"] += n_ch
            stats["chars"] += total_chars
            stats["dup_chapters"] += n_dup
            rep.write(
                json.dumps(
                    {
                        "book": book, "dir": parent, "author": author,
                        "files": [str(f.relative_to(SRC)) for f in files],
                        "chapters": n_ch, "chars": total_chars,
                        "dup_chapters_skipped": n_dup,
                        "chapter_num_gaps": gaps,
                        "anomaly": anomaly,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"切分完成: {stats['books']} 本书, {stats['chapters']} 章, 共 {stats['chars']:,} 字")
    print(f"分卷合并去重跳过: {stats['dup_chapters']} 章")
    print(f"输出: {OUT}")
    if stats["anomaly_books"]:
        print(f"\n异常书籍 {len(stats['anomaly_books'])} 本（章节<10 或 >5000 或总字<2万）:")
        for a in stats["anomaly_books"][:30]:
            print(f"  - {a}")


if __name__ == "__main__":
    main()
