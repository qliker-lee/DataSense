"""PII 샘플 카탈로그 마크다운 테이블 → CSV 변환."""

from __future__ import annotations

import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SOURCE_FILE = BASE_DIR / "pii_sample_catalog.md"
OUTPUT_CSV = BASE_DIR / "pii_sample_catalog.csv"


def parse_markdown_table(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or ":---" in line or line.startswith("| ID |"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 5:
            continue
        subtype = parts[2].rstrip("|").strip()
        rows.append([parts[0], parts[1], subtype, parts[3], parts[4]])
    return rows


def write_csv(rows: list[list[str]], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Data_Type", "Sub_Type", "Raw_Sample_Value", "Description"])
        writer.writerows(rows)


def main() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"소스 파일이 없습니다: {SOURCE_FILE}")
    rows = parse_markdown_table(SOURCE_FILE)
    write_csv(rows, OUTPUT_CSV)
    print(f"생성 완료: {OUTPUT_CSV} ({len(rows)}행)")


if __name__ == "__main__":
    main()
