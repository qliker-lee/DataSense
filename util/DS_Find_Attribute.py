# -*- coding: utf-8 -*-
"""
DS_Find_Attribute.py
- DS_Output/FileFormat.csv 를 읽어 FilePath, FileName, ColumnName, Top10 기준으로
  Top10 값 개수(Top10Cnt)와 값별 문자 패턴(Top10Pattern)을 계산해
  DS_Output/FileAttribute.csv 로 저장합니다.

Top10 컬럼 예: ["제조,도소매", "도소매", ...]  (JSON 배열 문자열)
패턴 규칙: DS_Columnprofiler.ColumnProfiler._get_pattern_custom 의 transform 과 동일
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "DS_Output" / "FileFormat.csv"
DEFAULT_OUTPUT = ROOT / "DS_Output" / "FileAttribute.csv"


def _strip_decimal_zero(val: object) -> str:
    """ColumnProfiler._strip_decimal_zero 와 동일: '.0' 접미 제거."""
    s = str(val)
    if s.endswith(".0"):
        return s[:-2]
    return s


def value_to_pattern(value: object) -> str:
    """사용자 작성 get_pattern 로직 (n, K, A, a 등 변환), 앞 20자만."""
    try:
        text = _strip_decimal_zero(value)[:20]
        p: list[str] = []
        for ch in text:
            if ch.isdigit():
                p.append("n")
            elif "가" <= ch <= "힣":
                p.append("K")
            elif ch.isupper():
                p.append("A")
            elif ch.islower():
                p.append("a")
            elif ch in "(){}[]-=. :@/":
                p.append(ch)
            else:
                p.append("s")
        return "".join(p)
    except Exception:
        return ""


def parse_top10_values(raw: object) -> list[str]:
    """Top10 셀 → 문자열 값 리스트."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none", ""}:
        return []

    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, dict):
            return [str(k) for k in v.keys()]
    except json.JSONDecodeError:
        pass

    try:
        v = ast.literal_eval(s)
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, dict):
            return [str(k) for k in v.keys()]
    except (ValueError, SyntaxError):
        pass

    return []


def build_file_attribute(df: pd.DataFrame) -> pd.DataFrame:
    required = {"FilePath", "FileName", "ColumnName", "Top10"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"FileFormat.csv 에 필요한 컬럼이 없습니다: {sorted(missing)}")

    rows: list[dict] = []
    for _, r in df.iterrows():
        top_list = parse_top10_values(r.get("Top10"))
        patterns = [value_to_pattern(v) for v in top_list]
        rows.append(
            {
                "FilePath": r.get("FilePath", ""),
                "FileName": r.get("FileName", ""),
                "ColumnName": r.get("ColumnName", ""),
                "Top10": r.get("Top10", "") if not isinstance(r.get("Top10"), float) or not pd.isna(r.get("Top10")) else "",
                "Top10Cnt": len(top_list),
                "Top10Pattern": json.dumps(patterns, ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FileFormat Top10 → 패턴 요약 (FileAttribute.csv)")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="입력 FileFormat.csv")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="출력 FileAttribute.csv")
    args = p.parse_args(argv)

    in_path = args.input.resolve()
    out_path = args.output.resolve()
    if not in_path.is_file():
        print(f"[오류] 입력 파일 없음: {in_path}", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(in_path, dtype=str, encoding="utf-8-sig", low_memory=False)
    out_df = build_file_attribute(df)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[완료] {len(out_df)} 행 → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
