import pandas as pd
import ast
import os
import sys
from pathlib import Path
from collections import Counter

# 이 파일 위치: .../QDQM/util/DS_Find_Label_Gemini.py
UTIL = Path(__file__).resolve().parent
ROOT = UTIL.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from util.dq_validate import (
    find_attribute,
    column_label_trust_decision,
    validator_priority,
)


class DS_Attribute:
    @staticmethod
    def get_column_summary(top_10_values):
        """
        Top N 값 각각에 대해 find_attribute 후보(통과한 검증기 전부)를 세어,

        컬럼 단위 요약 문자열을 만든다. 예: "YYYYMMDD:8, TEL:2, NULL:1"
        (한 값이 여러 검증을 동시에 통과하면 레이블별 건수 합이 샘플 수보다 클 수 있음)
        """
        if not top_10_values:
            return ""
        total_label_counts: Counter = Counter()
        for val in top_10_values:
            _best, _score, candidates = find_attribute(val)
            for label, _prio in candidates:
                total_label_counts[label] += 1
        items = sorted(
            total_label_counts.items(),
            key=lambda kv: (-kv[1], -validator_priority(kv[0]), kv[0]),
        )
        parts = [f"{label}:{count}" for label, count in items]
        return ", ".join(parts)
 
    @staticmethod
    def format_score_compact(mapping_report: list) -> str:
        """mapping_report 항목을 'TEL:6, ZIP_CODE:1' 형식 문자열로."""
        if not mapping_report:
            return ""
        parts = []
        for row in mapping_report:
            lbl = row.get("Label", "")
            cnt = row.get("Cnt", 0)
            parts.append(f"{lbl}:{cnt}")
        return ", ".join(parts)  

    def match_label(self, top_10_values):
        """컬럼 단위 집계. 반환: (label, label_cnt, mapping_report)."""
        label_hit_counts = Counter()

        num_values = len(top_10_values)
        if num_values == 0:
            return "", 0, []

        for val in top_10_values:
            _best_label, _best_score, candidates = find_attribute(val)
            if not candidates:
                continue
            for label, _score in candidates:
                label_hit_counts[label] += 1

        mapping_report = []
        for label, hit_count in label_hit_counts.items():
            mapping_report.append({
                "Label": label,
                "Rate": (hit_count / num_values) * 100.0,
                "Cnt": hit_count,
            })

        # Rate·Cnt 동률이면 VALIDATOR_CONFIG['priority']가 큰 라벨이 먼저
        mapping_report.sort(
            key=lambda x: (
                -x["Rate"],
                -x["Cnt"],
                -validator_priority(x["Label"]),
                x["Label"],
            )
        )
        label = mapping_report[0]["Label"] if mapping_report else ""
        label_cnt = mapping_report[0]["Cnt"] if mapping_report else 0
        return label, label_cnt, mapping_report


def _parse_top10_list(top10_str) -> list:
    """CodeMapping `Top10` 셀 문자열 → 값 리스트."""
    if top10_str is None or (isinstance(top10_str, float) and pd.isna(top10_str)):
        return []
    try:
        top10_list = ast.literal_eval(str(top10_str))
        return top10_list if isinstance(top10_list, list) else []
    except (ValueError, SyntaxError, TypeError):
        return []


def analyze_codemapping_label(
    df: pd.DataFrame,
    *,
    include_value_summary: bool = False,
) -> pd.DataFrame:
    """CodeMapping 행 단위 Top10 값 → 라벨·신뢰도 집계 (Streamlit/배치 공용)."""
    processor = DS_Attribute()
    results = []

    for _, row in df.iterrows():
        top10_str = row.get("Top10", "")
        top10_list = _parse_top10_list(top10_str)
        top10_cnt = len(top10_list)

        label, label_cnt, label_list = processor.match_label(top10_list)
        match_rate = label_cnt / top10_cnt if top10_cnt > 0 else 0.0
        is_trusted, target_tolerance = column_label_trust_decision(
            label, match_rate=match_rate, sample_size=top10_cnt
        )

        out = {
            "FilePath": row.get("FilePath", ""),
            "FileName": row.get("FileName", ""),
            "ColumnName": row.get("ColumnName", ""),
            "Top10": top10_str,
            "Top10_Cnt": top10_cnt,
            "Label": label if is_trusted else "",
            "Cnt": label_cnt if is_trusted else "",
            "Matched_List": DS_Attribute.format_score_compact(label_list),
            "Match_Rate": f"{match_rate:.1%}",
            "Target_Tolerance": f"{target_tolerance:.1%}",
        }
        if include_value_summary:
            out["Value_Label_Summary"] = processor.get_column_summary(top10_list)
        results.append(out)

    return pd.DataFrame(results)


def main():
    """Streamlit `41_PII Integrated Analyzer` 와 동일 조건으로 배치 실행."""
    input_path = ROOT / "DS_Output" / "CodeMapping.csv"
    output_path = ROOT / "DS_Output" / "FileLabel.csv"

    if not input_path.exists():
        print(f"Error: {input_path} 파일이 존재하지 않습니다.")
        return

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    if "MasterType" in df.columns:
        df = df[df["MasterType"] == "Master"].copy()

    result_df = analyze_codemapping_label(df, include_value_summary=True)
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Success: {len(result_df)}행 → {output_path}")

if __name__ == "__main__":
    main()