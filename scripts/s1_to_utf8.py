#!/usr/bin/env python3
"""阶段一：编码统一。0/ 1/ -> work/01_utf8/，输出 work/reports/s1_report.jsonl"""
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIRS = [ROOT / "0", ROOT / "1"]
OUT = ROOT / "work" / "01_utf8"
REPORT = ROOT / "work" / "reports" / "s1_report.jsonl"


def decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None:
            enc = str(best.encoding)
            return str(best), enc
    except ImportError:
        pass
    return raw.decode("gb18030", errors="replace"), "gb18030(fallback)"


def mojibake_ratio(text: str) -> float:
    if not text:
        return 0.0
    bad = sum(
        1
        for c in text
        if c == "" or (unicodedata.category(c) == "Cc" and c not in "\n\t")
    )
    return bad / len(text)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    quarantine = []
    n = 0
    with REPORT.open("w", encoding="utf-8") as rep:
        for src in SRC_DIRS:
            for f in sorted(src.rglob("*.txt")):
                rel = f.relative_to(ROOT)
                raw = f.read_bytes()
                text, enc = decode(raw)
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                ratio = mojibake_ratio(text)
                status = "ok" if ratio <= 0.001 else "quarantine"
                if status == "quarantine":
                    quarantine.append(str(rel))
                dst = OUT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(text, encoding="utf-8")
                rep.write(
                    json.dumps(
                        {
                            "file": str(rel),
                            "encoding": enc,
                            "chars": len(text),
                            "mojibake_ratio": round(ratio, 6),
                            "status": status,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                n += 1
    print(f"转换完成: {n} 个文件 -> {OUT}")
    print(f"报告: {REPORT}")
    if quarantine:
        print(f"乱码率超标 {len(quarantine)} 个（需人工检查）:")
        for q in quarantine:
            print(f"  - {q}")


if __name__ == "__main__":
    sys.exit(main())
