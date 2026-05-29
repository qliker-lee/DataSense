# -*- coding: utf-8 -*-
"""
📊 DataSense PII Integrated Analyzer
Author: qliker 2026-04-30
"""

import sys
from pathlib import Path
from difflib import SequenceMatcher
import pandas as pd

import streamlit as st

# -------------------------------------------------------------------
# 1. 환경 설정 및 경로
# -------------------------------------------------------------------
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from util.streamlit_warnings import setup_streamlit_warnings
    setup_streamlit_warnings()
except ImportError:
    pass

# -------------------------------------------------------------------
# 2. 상수 및 경로 (DS_Output)
# -------------------------------------------------------------------
OUTPUT_DIR = PROJECT_ROOT / "DS_Output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PII_LIST_PATH = OUTPUT_DIR / "PII_Column_list.csv"
PII_COLUMNS_PATH = OUTPUT_DIR / "PII_Columns.csv"
CODE_MAPPING_PATH = OUTPUT_DIR / "CodeMapping.csv"

APP_NAME = "PII(Personally Identifiable Information) Analyzer (개인정보 컬럼 분석)"
APP_DESC = "#### 데이터에 개인정보(PII) 값이 포함된 컬럼을 자동으로 식별합니다."

# 값 기반 자동 식별 Label 과 비교할 기본 키워드(쉼표 구분). UI 표시·is_default 판정에 동일하게 사용.
_DEFAULT_PII_KEYWORDS = """ADDRESS, NAME_KOR, EMAIL, CELLPHONE, TEL, FOREIGN_RN, DRIVER_LICENSE, 
PASSPORT, RRN, RRN_FORMAT, CARD_NUMBER, BANK_ACCOUNT, ADID"""


# -------------------------------------------------------------------
# 3. Label 생성 함수  (DS_15_Find_Label)
# -------------------------------------------------------------------
from collections import Counter
import ast

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

# -------------------------------------------------------------------
# 폰트 / 공통 스타일 / 페이지 설정"
# -------------------------------------------------------------------
st.markdown(
    """<style> html, body, [class*="css"]  { font-size: 14px; } </style> """,
    unsafe_allow_html=True,
)


def load_css(file_name: str) -> None:
    path = Path(file_name)
    if not path.is_absolute():
        path = PROJECT_ROOT / file_name
    with open(path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css("styles/styles.css")

from util.Files_FunctionV20 import set_page_config
set_page_config(APP_NAME)

from util.Display import display_kpi_metrics
# -------------------------------------------------------------------
# 3. 유틸리티
# -------------------------------------------------------------------
def calculate_similarity(a, b) -> float:
    """두 문자열 사이의 유사도 계산 (0.0 ~ 1.0)"""
    return SequenceMatcher(None, str(a).upper(), str(b).upper()).ratio()


def save_pii_list(text: str) -> None:
    with open(PII_LIST_PATH, "w", encoding="utf-8-sig") as f:
        f.write(text)


def load_pii_list_default() -> str:
    if PII_LIST_PATH.exists():
        with open(PII_LIST_PATH, "r", encoding="utf-8-sig") as f:
            return f.read()
    return ""


def read_codemapping(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    return pd.DataFrame()

def default_pii_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """
    CodeMapping Top10 기반 값 라벨 분석 (`DS_Find_Label_Gemini.analyze_codemapping_label`).

    호출 전 `df`는 이미 `MasterType == 'Master'` 로 필터된 상태여야
    `DS_Find_Label_Gemini.main()` 과 행 단위 결과가 일치합니다.
    """
    from util.DS_15_Find_Label import analyze_codemapping_label

    result_df = analyze_codemapping_label(df, include_value_summary=True)
    # Streamlit(Arrow) 호환: 미신뢰 라벨은 빈 문자열 → nullable
    if "Label" in result_df.columns:
        result_df["Label"] = (
            result_df["Label"].replace("", pd.NA).astype("string")
        )
    if "Cnt" in result_df.columns:
        result_df["Cnt"] = pd.to_numeric(result_df["Cnt"], errors="coerce").astype("Int64")
    return result_df

# -------------------------------------------------------------------
# 1st Step: PII 분석 Key word 정의
# -------------------------------------------------------------------
def define_pii_keyword() -> list[str]:
    """데이터 값 기준 및 컬럼명 기준 PII Key word 정의"""
    st.subheader("1. PII 분석 Key word 정의")
    col1, col2 = st.columns(2, gap="medium", vertical_alignment="top")
    with col1:
        st.markdown("###### 1.1 데이터 값 기준 PII Key word (자동 정의)")
        st.markdown(
            "자동 정의 PII Key word는 데이터의 값 기준으로 "
            "<strong style='color:#c0392b;font-weight:700'>식별된</strong> "
            "결과입니다.",
            unsafe_allow_html=True,
        )
        st.text_area("데이터 값 기준 PII Key word", value=_DEFAULT_PII_KEYWORDS, height=100)

    with col2:
        st.markdown("###### 1.2 컬럼명 기준 PII Key word (사용자 정의)")
        pii_keywords = define_pii_column_name_keyword()

    return pii_keywords
# -------------------------------------------------------------------
# 4. PII 분석 함수
# -------------------------------------------------------------------

def _default_pii_keyword_set() -> set[str]:
    return {k.strip().upper() for k in _DEFAULT_PII_KEYWORDS.split(",") if k.strip()}


def _most_frequent_nonempty(series: pd.Series) -> str:
    s = series.dropna().astype(str)
    s = s[s.str.strip() != ""]
    if s.empty:
        return ""
    vc = s.value_counts()
    max_cnt = vc.iloc[0]
    top_vals = sorted(vc[vc == max_cnt].index.astype(str).tolist())
    return top_vals[0] if top_vals else ""


def build_pii_columns_df(
    df_default_pii: pd.DataFrame,
    pii_keywords: list[str],
) -> pd.DataFrame:
    pii_default_set = _default_pii_keyword_set()
    work = df_default_pii.dropna(subset=["ColumnName"])
    # Label 은 _DEFAULT_PII_KEYWORDS 에 정의된 값(대소문자 무시)만 반영해 is_abs 판단
    _d = work[["ColumnName", "Label", "Cnt"]].copy()

    _d["_lbl_u"] = _d["Label"].fillna("").astype(str).str.strip().str.upper()
    _d_default_only = _d[_d["_lbl_u"].isin(pii_default_set)].copy()
    _d_default_only["_cn"] = _d_default_only["ColumnName"].astype(str).str.strip()
    cols_with_default_label = set(_d_default_only["_cn"].unique())

    unique_cols = work["ColumnName"].unique()

    results = []
    for col in unique_cols:
        col_upper = str(col).upper()
        cn = str(col).strip()
        is_user_defined = False
        max_sim = 0.0
        for kw in pii_keywords:
            if kw == col_upper:
                is_user_defined = True
            # sim = calculate_similarity(kw, col_upper)
            # if sim > max_sim:
            #     max_sim = sim
        is_abs = cn in cols_with_default_label
        is_pii_flag = is_user_defined or (max_sim > 0.9) or is_abs
        results.append({
            "ColumnName": col,
            "is_user_defined": is_user_defined,
            # "similarity": round(max_sim, 3),
            "is_PII": is_pii_flag,
        })
    return pd.DataFrame(results)


def define_pii_column_name_keyword() -> list[str]:
    """사용자 정의 컬럼명 기준  PII Key word 정의"""
    pii_list_content = load_pii_list_default()
    st.markdown(
        "사용자 정의(컬럼명 기반) PII Key word는 "
        "<strong style='color:#c0392b;font-weight:700'>컬럼명 기준으로</strong> "
        "사용자가 지정한 컬럼명입니다.",
        unsafe_allow_html=True,
    )
    new_pii_list = st.text_area(
        "사용자 정의(컬럼명 기반) PII Key word를 입력하세요.",
        value=pii_list_content,
        height=100,
        help="컬럼명에 이 리스트 단어가 포함되면 PII로 간주될 확률이 높아집니다.",
    )

    if st.button("사용자 정의 PII Key word 저장"):
        save_pii_list(new_pii_list)
        st.success("사용자 정의 PII Key word 리스트가 저장되었습니다.")

    pii_keywords = [k.strip().upper() for k in new_pii_list.split(",") if k.strip()]
    return pii_keywords

def pii_column_analysis(
    df_mapping_pii: pd.DataFrame,
    pii_keywords: list[str],
    PII_COLUMNS_PATH: Path,
) -> pd.DataFrame:
    st.divider()
    st.subheader("2. PII 컬럼 최종 정의")
    st.write(
        "PII 컬럼 최종 정의는 사용자가 컬럼명 기준으로 정의합니다. "
        "아래 테이블에서 `is_PII` 필드값을 True(체크)로 설정하면 해당 컬럼은 PII 컬럼으로 식별됩니다."
    )

    work = df_mapping_pii.dropna(subset=["ColumnName"]) if not df_mapping_pii.empty else pd.DataFrame()
    if work.empty:
        st.warning("`df_mapping_pii` 에 유효한 `ColumnName` 이 없습니다.")
        return pd.DataFrame()

    # CodeMapping 기반 분석의 모든 컬럼을 행으로 포함 (초기 표시 기준)
    df_built = build_pii_columns_df(df_mapping_pii, pii_keywords)
    # st.dataframe(df_built, hide_index=True, width="stretch", height=500)
    if df_built.empty:
        st.warning("분석할 컬럼이 없습니다.")
        return pd.DataFrame()

    df_col_info = df_built.copy()
    df_col_info["ColumnName"] = df_col_info["ColumnName"].astype(str).str.strip()

    work_cn = work["ColumnName"].astype(str).str.strip()
    filecnt_map = work.assign(_cn=work_cn).groupby("_cn")["FileName"].nunique()
    pii_default_set = _default_pii_keyword_set()
    _m = work[["ColumnName", "Label"]].copy()
    _m["ColumnName"] = _m["ColumnName"].astype(str).str.strip()
    _m["_lbl_u"] = _m["Label"].fillna("").astype(str).str.strip().str.upper()
    _m_default_only = _m[_m["_lbl_u"].isin(pii_default_set)].copy()
    _m_default_only["ColumnName"] = _m_default_only["ColumnName"].astype(str).str.strip()
    cols_hit_set = set(_m_default_only["ColumnName"].unique())
    # Label 표시: _DEFAULT_PII_KEYWORDS 에 해당하는 라벨만으로 최빈값
    label_map = _m_default_only.groupby("ColumnName")["Label"].apply(_most_frequent_nonempty)

    df_col_info["FileCnt"] = df_col_info["ColumnName"].map(filecnt_map).fillna(0).astype(int)
    df_col_info["is_default"] = df_col_info["ColumnName"].isin(cols_hit_set)
    df_col_info["Label"] = df_col_info["ColumnName"].map(label_map).fillna("")

    df_pii_saved: pd.DataFrame | None = None
    if PII_COLUMNS_PATH.exists():
        try:
            df_pii_saved = pd.read_csv(PII_COLUMNS_PATH, encoding="utf-8-sig")
        except Exception as e:
            st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
            return pd.DataFrame()
        if not df_pii_saved.empty and "ColumnName" in df_pii_saved.columns:
            ds = df_pii_saved.copy()
            ds["ColumnName"] = ds["ColumnName"].astype(str).str.strip()
            ds = ds.drop_duplicates(subset=["ColumnName"], keep="last").set_index("ColumnName")
            for col in ("is_PII", "is_user_defined"):
                if col in ds.columns:
                    mapped = df_col_info["ColumnName"].map(ds[col])
                    df_col_info[col] = mapped.combine_first(df_col_info[col])
            # CSV에만 있는 추가 열(예: 메모) — 매핑에 있는 행에만 붙임
            skip = {"ColumnName", "is_PII", "is_user_defined", "FileCnt", "is_default", "Label"}
            for ec in df_pii_saved.columns:
                if ec in skip or ec not in ds.columns:
                    continue
                df_col_info[ec] = df_col_info["ColumnName"].map(ds[ec])

    if "is_PII" not in df_col_info.columns:
        df_col_info["is_PII"] = df_col_info["is_default"]
    else:
        na_pii = df_col_info["is_PII"].isna()
        if na_pii.any():
            df_col_info.loc[na_pii, "is_PII"] = df_col_info.loc[na_pii, "is_default"]
    df_col_info["is_PII"] = _mask_is_pii_true(df_col_info["is_PII"].astype(object))

    df_col_info["is_user_defined"] = df_col_info.get("is_user_defined", False)
    df_col_info["is_user_defined"] = df_col_info["is_user_defined"].fillna(False).astype(bool)
    # df_col_info["similarity"] = pd.to_numeric(df_col_info.get("similarity", 0), errors="coerce").fillna(0.0)

    df_col_info = df_col_info.sort_values(
        by=["is_default", "is_user_defined"],
        ascending=[False, False],
        kind="mergesort",
    )

    fixed_cols = ["ColumnName", "is_PII", "is_default"]
    rest_cols = [c for c in df_col_info.columns if c not in fixed_cols]
    df_col_info = df_col_info[fixed_cols + rest_cols]

    st.info("`is_PII` 컬럼을 수정 후 하단 저장 버튼을 클릭하세요.")

    _filecnt_max = int(df_col_info["FileCnt"].max() if not df_col_info.empty else 1)
    edited_df = st.data_editor(
        df_col_info,
        width="stretch",
        num_rows="dynamic",
        column_config={
            "is_PII": st.column_config.CheckboxColumn("is_PII", help="최종 PII 여부 선택"),
            "FileCnt": st.column_config.ProgressColumn(
                "File #",
                help="컬럼이 등장한 파일 수",
                min_value=0,
                max_value=max(1, _filecnt_max),
                format="%d",
            ),
            "is_default": st.column_config.CheckboxColumn(
                "자동 정의",
                help="데이터 값 기반으로 자동으로 정의한 PII Key word",
                disabled=True,
            ),
            "is_user_defined": st.column_config.CheckboxColumn(
                "사용자 정의",
                help="사용자가 정의한 컬럼명",
                disabled=True,
            ),
            "Label": st.column_config.TextColumn(
                "자동 PII Key word",
                help="자동으로 매칭된 PII Key word",
                disabled=True,
            ),
        },
        height=500,
        disabled=["ColumnName", "FileCnt", "Label", "is_user_defined",  "is_default"],
        key="pii_editor",
    )

    col1, col2, col3 = st.columns([1, 3, 1], gap="medium")
    with col1:
        if st.button("저장", type="primary"):
            edited_df.to_csv(PII_COLUMNS_PATH, index=False, encoding="utf-8-sig")
            st.success("PII 설정이 저장되었습니다.")
            return edited_df

    with col2:
        if not PII_COLUMNS_PATH.exists():
            st.warning("분석된 PII 컬럼 결과 파일이 없습니다. 최초 생성을 진행해 주세요.")
            if st.button("PII 분석 결과 최초 생성"):
                df_result = build_pii_columns_df(df_mapping_pii, pii_keywords)
                if not df_result.empty:
                    df_result.to_csv(PII_COLUMNS_PATH, index=False, encoding="utf-8-sig")
                    st.success("PII 분석 파일이 생성되었습니다.")
                    st.rerun()
                else:
                    st.error("분석할 데이터가 없습니다.")

    with col3:
        with st.expander("초기화 및 재생성"):
            if st.button("PII 분석 결과 초기화 및 재생성", help="기존 설정을 모두 삭제하고 다시 분석합니다."):
                if PII_COLUMNS_PATH.exists():
                    PII_COLUMNS_PATH.unlink()
                df_result = build_pii_columns_df(df_mapping_pii, pii_keywords)
                if not df_result.empty:
                    df_result.to_csv(PII_COLUMNS_PATH, index=False, encoding="utf-8-sig")
                    st.session_state.pop("pii_editor", None)
                    st.success("모든 설정이 초기화되고 새로 생성되었습니다.")
                    st.rerun()
                else:
                    st.error("분석할 데이터가 없습니다.")

    return pd.DataFrame()

def _comma_join_unique_files(s: pd.Series) -> str:
    return ", ".join(sorted(s.dropna().astype(str).unique()))


def _mask_is_pii_true(series: pd.Series) -> pd.Series:
    """PII_Columns.csv 등에서 읽은 is_PII: bool / 문자열 / 0·1 혼용을 True 마스크로 통일."""
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    num = pd.to_numeric(series, errors="coerce")
    t = series.astype(str).str.strip().str.lower()
    return (num == 1) | t.isin(("true", "1", "yes", "y", "t"))


def pii_analysis_summary(df_mapping: pd.DataFrame, df_pii: pd.DataFrame) -> None:
    st.divider()

    df_pii_true = df_pii.loc[_mask_is_pii_true(df_pii["is_PII"])].copy()
    if df_pii_true.empty:
        st.info("is_PII 가 True 인 컬럼이 없습니다.")
        return

    total_files = df_mapping["FileName"].nunique() if "FileName" in df_mapping.columns else 0
    total_columns = df_mapping["ColumnName"].nunique() if "ColumnName" in df_mapping.columns else 0
    df_pii_columns = df_pii_true["ColumnName"].dropna().astype(str).str.strip().unique()
    _cm = df_mapping["ColumnName"].astype(str).str.strip()
    tmp_df = df_mapping[_cm.isin(set(df_pii_columns))].copy()
    total_pii_files = tmp_df["FileName"].nunique() if "FileName" in tmp_df.columns else 0
    total_pii_columns = int(len(df_pii_columns))
    # (FileName, ColumnName) 조합의 고유 개수
    if "FileName" in tmp_df.columns and "ColumnName" in tmp_df.columns:
        total_pii_files_columns = int(tmp_df[["FileName", "ColumnName"]].dropna().drop_duplicates().shape[0])
    else:
        total_pii_files_columns = 0

    summary = {
        "Total Files": f"{total_files:,}",
        "Total Columns": f"{total_columns:,}",
        "Total PII Columns": f"{total_pii_columns:,}",
        "Total PII Files": f"{total_pii_files:,}",
        "Total PII Files Columns": f"{total_pii_files_columns:,}",
    }
    metric_colors = {
        "Total Files": "#1f77b4",
        "Total Columns": "#2ca02c",
        "Total PII Columns": "#9467bd",
        "Total PII Files": "#ff7f0e",
        "Total PII Files Columns": "#9467bd",
    }
    display_kpi_metrics(summary, metric_colors, "3. PII Analysis Summary")

    st.divider()
    st.subheader("3.1 PII 컬럼별 파일 분포 분석")
    # ColumnName 별 FileName 고유 개수(FileCnt), FileName 을 컴마로 연결(FileList)
    if tmp_df.empty or "FileName" not in tmp_df.columns or "ColumnName" not in tmp_df.columns:
        return
    df_pii_summary = (
        tmp_df.groupby("ColumnName", as_index=False)
        .agg(
            FileCnt=("FileName", "nunique"),
            FileList=("FileName", _comma_join_unique_files),
        )
        .sort_values(by="FileCnt", ascending=False)
    )
    # 컬럼별 FileCnt는 파일 수를 넘을 수 없음. 쌍 개수를 max로 쓰면 진행률이 과소 표시됨.
    _filecnt_cap = max(1, int(total_pii_files), int(df_pii_summary["FileCnt"].max()) if not df_pii_summary.empty else 0)
    st.dataframe(df_pii_summary, 
        column_config={
            "ColumnName": st.column_config.TextColumn("ColumnName", help="ColumnName", width="small"),
            "FileCnt": st.column_config.ProgressColumn("FileCnt", help="ColumnName이 등장한 파일 수", min_value=0, max_value=_filecnt_cap, format="%d", width="small"),
            "FileList": st.column_config.TextColumn("FileList", help="FileName 리스트", width="large"),
        },
        hide_index=True, width="stretch", height=500)

def pii_file_analysis_summary(df_mapping: pd.DataFrame, df_pii: pd.DataFrame) -> None:
    """`df_pii`에서 `is_PII=True`인 컬럼명 기준으로 `df_mapping`을 거른 뒤, 파일별 컬럼 수·PII 수·PII 목록을 출력."""
    st.divider()
    st.markdown("#### 4.1 파일별 PII 컬럼 분포 분석")


    if df_mapping.empty or "FileName" not in df_mapping.columns or "ColumnName" not in df_mapping.columns:
        st.warning("`CodeMapping` 에 `FileName` / `ColumnName` 이 없습니다.")
        return

    pii_col_set = set(df_pii["ColumnName"].dropna().astype(str).str.strip())
    pii_col_set.discard("")
    if not pii_col_set:
        st.info("`is_PII=True` 행에 유효한 `ColumnName` 이 없습니다.")
        return

    _cm = df_mapping["ColumnName"].astype(str).str.strip()
    df_hit = df_mapping.loc[_cm.isin(pii_col_set)].copy()
    if df_hit.empty:
        st.info("매핑 데이터에서 위 PII 컬럼명과 일치하는 행이 없습니다.")
        return

    fn_series = df_hit["FileName"].dropna().astype(str).str.strip()
    file_names = sorted(fn_series[fn_series != ""].unique())

    rows_out: list[dict] = []
    for fn in file_names:
        mask_map = df_mapping["FileName"].astype(str).str.strip() == fn
        total_unique_cols = int(df_mapping.loc[mask_map, "ColumnName"].dropna().astype(str).str.strip().nunique())

        mask_hit = df_hit["FileName"].astype(str).str.strip() == fn
        pii_cols = sorted(df_hit.loc[mask_hit, "ColumnName"].dropna().astype(str).str.strip().unique())
        pii_cols = [c for c in pii_cols if c]
        rows_out.append(
            {
                "FileName": fn,
                "전체컬럼수": total_unique_cols,
                "PII컬럼수": len(pii_cols),
                "PII컬럼목록": ", ".join(pii_cols),
            }
        )

    df_out = pd.DataFrame(rows_out)
    _h = min(500, max(120, 38 * (len(df_out) + 2)))
    _cap_total = max(1, int(df_out["전체컬럼수"].max()))
    _cap_pii = max(1, int(df_out["PII컬럼수"].max()))
    df_out = df_out.sort_values(by=["PII컬럼수", "FileName"], ascending=[False, True])
    st.dataframe(
        df_out,
        column_config={
            "FileName": st.column_config.TextColumn("FileName", width="medium"),
            "전체컬럼수": st.column_config.ProgressColumn(
                "전체 컬럼 수",
                help="파일의 컬럼 개수",
                min_value=0,
                max_value=_cap_total,
                format="%d",
                width="small",
            ),
            "PII컬럼수": st.column_config.ProgressColumn(
                "PII 컬럼 수",
                help="PII 값을 갖고 있는 컬럼의 수",
                min_value=0,
                max_value=_cap_pii,
                format="%d",
                width="small",
            ),
            "PII컬럼목록": st.column_config.TextColumn(
                "PII 컬럼 목록",
                help="위 PII 컬럼 수에 해당하는 컬럼명 목록",
                width="large",
            ),
        },
        hide_index=True,
        width="stretch",
        height=_h,
    )


def pii_file_analysis(df_mapping: pd.DataFrame, df_pii: pd.DataFrame) -> None:
    st.divider()
    st.markdown("#### 4.2 파일별 PII 컬럼의 상세 정보 분석")

    _cols = df_pii["ColumnName"].dropna().astype(str).str.strip().unique()
    # ColumnName별 매핑에 등장하는 FileName 고유 개수 (CodeMapping 기준)
    _dm = df_mapping.copy()
    _dm["_cn"] = _dm["ColumnName"].astype(str).str.strip()
    filecnt_by_col = _dm.groupby("_cn")["FileName"].nunique()

    df_pii_file = pd.merge(df_mapping, df_pii, on="ColumnName", how="left")
    df_pii_file = df_pii_file[df_pii_file["ColumnName"].astype(str).str.strip().isin(set(_cols))]
    _cn_rows = df_pii_file["ColumnName"].astype(str).str.strip()
    df_pii_file["FileCnt"] = _cn_rows.map(filecnt_by_col).fillna(0).astype(int)
    df_pii_file = df_pii_file.sort_values(by=["FileCnt", "FileName", "ColumnName"], ascending=[False, True, True])

    cols = [
        "FileName",
        "ColumnName",
        "RecordCnt",
        "ValueCnt",
        "Null(%)",
        "Unique(%)",
        "FormatCnt",
        "Format",
        "Top10",
        "Label",
        "Matched_List",
        "Match_Rate",
        "Target_Tolerance",
        "Value_Label_Summary",
        "FileCnt",
    ]
    show_cols = [c for c in cols if c in df_pii_file.columns]
    st.dataframe(df_pii_file[show_cols], hide_index=True, width="stretch", height=500)

# -------------------------------------------------------------------
# 4. 메인 UI
# -------------------------------------------------------------------
def _load_pii_columns_file() -> pd.DataFrame | None:
    """저장된 PII_Columns.csv 를 읽는다. 없거나 오류 시 None."""
    if not PII_COLUMNS_PATH.exists():
        return None
    try:
        return pd.read_csv(PII_COLUMNS_PATH, encoding="utf-8-sig")
    except Exception as e:
        st.error(f"PII_Columns.csv 읽기 오류: {e}")
        return None


def main() -> None:
    st.title(f"🛡️ {APP_NAME}")
    st.markdown(APP_DESC)

    if not CODE_MAPPING_PATH.exists():
        st.error("CodeMapping 파일이 없습니다. (Data Analyzer (Profiling) 을 수행한 후 작업하세요)")
        return

    df_mapping = read_codemapping(CODE_MAPPING_PATH)
    if df_mapping.empty:
        st.error("CodeMapping 파일을 읽을 수 없습니다.")
        return
    if "MasterType" in df_mapping.columns:
        df_mapping = df_mapping[df_mapping["MasterType"] == "Master"].copy()

    df_mapping_pii = default_pii_analysis(df_mapping)

    pii_keywords = define_pii_keyword()
    pii_column_analysis(df_mapping_pii, pii_keywords, PII_COLUMNS_PATH)

    # 요약·상세 분석은 저장된 PII_Columns.csv 기준 (편집기에서 저장 후 반영)
    df_pii = _load_pii_columns_file()
    if df_pii is None:
        st.info(
            "PII 컬럼 정의를 완료한 뒤 **「설정한 PII 컬럼으로 결과 저장」** 또는 "
            "**「PII 분석 결과 최초 생성」** 을 실행하세요."
        )
        return
    if df_pii.empty:
        st.warning("PII_Columns.csv 가 비어 있습니다.")
        return

    df_pii_true = df_pii.loc[_mask_is_pii_true(df_pii["is_PII"])].copy()
    if df_pii_true.empty:
        st.info("is_PII 가 True 인 컬럼이 없습니다. 상단 편집기에서 PII 컬럼을 지정하고 저장하세요.")
        return

    pii_analysis_summary(df_mapping, df_pii_true)
    pii_file_analysis_summary(df_mapping, df_pii_true)
    pii_file_analysis(df_mapping, df_pii_true)

    st.divider()


if __name__ == "__main__":
    main()
