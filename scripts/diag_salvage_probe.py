#!/usr/bin/env python3
"""毒性整行删除的"可救率"测量：对 01_utf8 里每一条被毒性规则整行删掉的行，
按第一个毒性命中点切开，统计前半段（head）像不像正文。只读诊断，不改任何文件。"""
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s2_clean as S  # noqa: E402
from chapter_heads import parse_header  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "01_utf8"
MIN_HEAD = 40

_AD = S.compile_rules(S.read_rules(S.PATTERNS_FILE))
_IN = S.compile_rules(S.read_rules(S.INLINE_FILE))
AD_TOXIC, IN_TOXIC = _AD[3], _IN[3]


def worker(path_str: str):
    p = Path(path_str)
    text = p.read_text(encoding="utf-8", errors="ignore")
    out = []
    for raw_line in text.split("\n"):
        line = raw_line.strip().replace("　", " ").strip()
        if not line or len(line) < 6 or len(line) > S.TOXIC_MAX:
            continue
        line = S.RE_BIDI.sub("", S.decode_entities(line)[0]).strip()
        if parse_header(line) is not None or S.RE_DIALOG.match(line):
            continue
        line = S.RE_BRACKET_AD.sub("", line).strip()
        if not line:
            continue
        m = None
        for u in (AD_TOXIC, IN_TOXIC):
            if u:
                cand = u.search(line)
                if cand:
                    m = cand
                    break
        if not m:
            continue
        head = line[: m.start()].strip()
        tail = line[m.end():].strip()
        if len(head) < MIN_HEAD or not S.CJK_END.search(head) or S.HAS_ALNUM.search(head):
            continue
        out.append((p.name, m.group(0)[:16], len(head), len(tail),
                    head[-26:], round(m.start() / max(len(line), 1), 2)))
    return out


def main() -> None:
    files = [str(f) for f in sorted(SRC.rglob("*.txt"))]
    rows = []
    with ProcessPoolExecutor(max_workers=10) as ex:
        for r in ex.map(worker, files):
            rows.extend(r)

    cur = sum(1 for r in rows if r[5] >= 0.55)
    print(f"毒性行切分后 head≥{MIN_HEAD} 且结尾是中文、无字母数字的行：{len(rows)}")
    print(f"  当前 55% 位置阈值可救回：{cur}")
    print(f"  放宽到任意位置可多救：{len(rows) - cur}")

    print("\n触发毒性词 Top 20（切后仍可救）：")
    for w, c in Counter(r[1] for r in rows).most_common(20):
        print(f"  {c:>6}  {w}")

    random.seed(7)
    print("\n随机 40 例（head 结尾 … «触发词» 剩余 tail 长度 / 命中位置比）：")
    for r in random.sample(rows, min(40, len(rows))):
        print(f"  [{r[0][:16]:<16}] …{r[4]} «{r[1]}» tail={r[3]} pos={r[5]}")

    Path(ROOT / "work/reports/salvage_probe.json").write_text(
        json.dumps({"total": len(rows), "current_ok": cur, "rows": rows}, ensure_ascii=False),
        encoding="utf-8")


if __name__ == "__main__":
    main()
