#!/usr/bin/env python3
"""阶段五：组装训练集。work/03_chapters/ + work/04_meta/*.json -> work/05_dataset/

- 有 meta 且 quality<=2 的整本剔除；缺 meta 的保留但 meta 字段为 null（标注后可重跑）
- 跨文件去重：同一本书的多份拷贝（合订本/分卷/改名重存）只保留一份
- chunk：同书内按章聚合到 3000~6000 字；超长章或超长段按段落/句子切，不留超长 chunk
- 每个 chunk 开头带书头： 《书名》 作者：X\n第N章 标题\n\n
- train/valid = 99:1，按书划分
"""
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "03_chapters"
META = ROOT / "work" / "04_meta"
OUT = ROOT / "work" / "05_dataset"
MIN_CHUNK = 3000
MAX_CHUNK = 6000
MAX_SEG = MAX_CHUNK - 400  # 段内切分留出书头与合并余量，避免拼回后又超长
MIN_TAIL = MIN_CHUNK // 2  # 低于这个长度的零头不单独立块，并进下一段
MIN_CHAPTER = 500  # 断章剔除阈值
MIN_DUP = 200      # 跨书去重只看这个长度以上的章，避免误删「第1章 试读」那类短章
RE_SENT_END = re.compile(r"(?<=[。！？…])")


def load_meta(book_file: str) -> dict | None:
    p = META / book_file.replace(".jsonl", ".json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def header(book: str, author: str | None, title: str) -> str:
    a = f" 作者：{author}" if author else ""
    return f"《{book}》{a}\n{title}\n\n"


def hard_split(par: str, limit: int) -> list[str]:
    """整行没有换行的超长段（神秘之旅那种 9900 字一行）按句子边界再切"""
    if len(par) <= limit:
        return [par]
    out, cur = [], ""
    for s in RE_SENT_END.split(par):
        while len(s) > limit:  # 无标点超长句兜底，宁可切断也不能超长
            if cur:
                out.append(cur)
                cur = ""
            out.append(s[:limit])
            s = s[limit:]
        if len(cur) + len(s) > limit and cur:
            out.append(cur)
            cur = s
        else:
            cur += s
    if cur:
        out.append(cur)
    return out


def split_long_chapter(text: str) -> list[str]:
    """超长章按段落边界切成 <=MAX_SEG 的段"""
    paras: list[str] = []
    for p in text.split("\n"):
        paras.extend(hard_split(p, MAX_SEG))
    chunks, cur, cur_len = [], [], 0
    for p in paras:
        if cur_len + len(p) + 1 > MAX_SEG and cur:
            chunks.append("\n".join(cur))
            cur, cur_len = [], 0
        cur.append(p)
        cur_len += len(p) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def build_chunks(chapters: list[dict], author: str | None = None) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for ch in chapters:
        if ch["char_count"] < MIN_CHAPTER:
            continue
        head = header(ch["book"], author or ch["author"], ch["chapter_title"])
        segs = split_long_chapter(ch["text"]) if len(ch["text"]) + len(head) > MAX_CHUNK else [ch["text"]]
        for seg in segs:
            # 切开后的每一段都重新带书头，补全时才知道自己在哪本书哪一章
            piece = head + seg
            if buf and buf_len + len(piece) + 2 > MAX_CHUNK and buf_len >= MIN_TAIL:
                chunks.append("\n\n".join(buf))
                buf, buf_len = [], 0
            buf.append(piece)
            buf_len += len(piece) + 2
    if buf and buf_len >= MIN_TAIL:  # 书尾允许半长 chunk
        chunks.append("\n\n".join(buf))
    return chunks


def norm_hash(text: str) -> str:
    return hashlib.blake2b(re.sub(r"\s+", "", text).encode("utf-8"), digest_size=12).hexdigest()


def junk_name(book: str) -> bool:
    """采集站把整本书改名成 z1/a13 这种，去重时要让真书名那一份胜出"""
    return bool(re.fullmatch(r"[A-Za-z0-9._\-\s]+", book))


def main() -> None:
    if not SRC.exists():
        sys.exit("先运行 s3_split_chapters.py")
    OUT.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    books = []
    for f in sorted(SRC.glob("*.jsonl")):
        chapters = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()]
        if not chapters:
            continue
        meta = load_meta(f.name)
        if meta and isinstance(meta.get("quality"), (int, float)) and meta["quality"] <= 2:
            continue
        books.append((f.name, chapters, meta))

    # 跨文件去重：合订本 + 分卷拼本、或同一本书换个文件名再存一份，只保留信息最好的那份
    hashes = {
        key: [norm_hash(c["text"]) if c["char_count"] >= MIN_DUP else "" for c in chapters]
        for key, chapters, _ in books
    }
    claim: dict[str, str] = {}
    for key, chapters, _ in sorted(
        books,
        key=lambda b: (junk_name(b[1][0]["book"]), -sum(c["char_count"] for c in b[1]), b[0]),
    ):
        for h in hashes[key]:
            if h:
                claim.setdefault(h, key)
    dup_chapters = dup_chars = 0
    dup_books: list[str] = []
    deduped = []
    for key, chapters, meta in books:
        kept = [
            ch
            for ch, h in zip(chapters, hashes[key])
            if not h or claim[h] == key
        ]
        if len(chapters) > 50 and len(kept) * 5 < len(chapters):
            # 整本都是另一份拷贝的残留（章节边界对不齐漏下的几章），留着头会顶着《z1》这种假书名进训练集
            dup_books.append(f"{chapters[0]['book']} ({len(chapters) - len(kept)}/{len(chapters)} 章)")
            kept = []
        dup_chapters += len(chapters) - len(kept)
        dup_chars += sum(c["char_count"] for c in chapters) - sum(c["char_count"] for c in kept)
        if kept:
            deduped.append((key, kept, meta))
    books = deduped

    random.shuffle(books)
    # 按字数配额选 valid 的书（整本不跨集），只看本数会抽到只剩 100 chunk 的小书
    total_in = sum(c["char_count"] for _, chs, _ in books for c in chs)
    acc = 0
    valid_keys: set[str] = set()
    for key, chapters, _ in books:
        if valid_keys and acc >= total_in * 0.01:
            break
        valid_keys.add(key)
        acc += sum(c["char_count"] for c in chapters)

    n_train = n_valid_chunks = n_valid_chars = 0
    genre_counter: Counter = Counter()
    dropped = 0
    with (OUT / "train.jsonl").open("w", encoding="utf-8") as tr, \
         (OUT / "valid.jsonl").open("w", encoding="utf-8") as va:
        for key, chapters, meta in books:
            author = chapters[0]["author"] or (meta or {}).get("author")
            chunks = build_chunks(chapters, author)
            if not chunks:
                dropped += 1
                continue
            genre = (meta or {}).get("genre") or ["未知"]
            genre_counter[genre[0]] += 1
            sink = va if key in valid_keys else tr
            for c in chunks:
                sink.write(
                    json.dumps(
                        {
                            "text": c,
                            "book": chapters[0]["book"],
                            "author": author,
                            "genre": genre,
                            "pov": (meta or {}).get("pov"),
                            "style": (meta or {}).get("style"),
                            "quality": (meta or {}).get("quality"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            if key in valid_keys:
                n_valid_chunks += len(chunks)
                n_valid_chars += sum(len(c) for c in chunks)
            else:
                n_train += len(chunks)

    total_chars = 0
    for name in ("train.jsonl", "valid.jsonl"):
        for line in (OUT / name).read_text(encoding="utf-8").splitlines():
            total_chars += len(json.loads(line)["text"])

    stats = [
        "# 数据集统计",
        f"- 入选书籍: {len(books) - dropped}（因无有效 chunk 丢弃 {dropped}）",
        f"- 跨书重复剔除: {dup_chapters} 章 / {dup_chars:,} 字",
        *(
            [f"- 其中整本拷贝剔除 {len(dup_books)} 本: " + "；".join(dup_books)]
            if dup_books else []
        ),
        f"- train chunks: {n_train}",
        f"- valid chunks: {n_valid_chunks}（{len(valid_keys)} 本书, {n_valid_chars:,} 字）",
        f"- 总字数: {total_chars:,}",
        "\n## 题材分布（按书，取首个 genre）",
    ]
    for g, c in genre_counter.most_common():
        stats.append(f"- {g}: {c}")
    (OUT / "stats.md").write_text("\n".join(stats) + "\n", encoding="utf-8")
    print("\n".join(stats))
    print(f"\n输出: {OUT}")


if __name__ == "__main__":
    main()
