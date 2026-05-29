# -*- coding: utf-8 -*-
"""
🔗 Data Consistency Analysis
Author: Qliker 2026-02-26
"""
# -------------------------------------------------
# 1. Path / Warning setup (Streamlit import 전)
# -------------------------------------------------
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from util.streamlit_warnings import setup_streamlit_warnings
setup_streamlit_warnings()

from util.Display import display_kpi_metrics
# -------------------------------------------------
# 2. Standard / Third-party imports
# -------------------------------------------------
import streamlit as st
import pandas as pd
from collections import defaultdict
from pathlib import Path
from datetime import datetime

# -------------------------------------------------------------------
# 폰트 크기 조정 및 색상 변경 (신규추가)
# -------------------------------------------------------------------
st.markdown("""<style> html, body, [class*="css"]  { font-size: 14px; } </style> """, unsafe_allow_html=True)
def load_css(file_name):
    path = Path(file_name)
    if not path.is_absolute():
        path = PROJECT_ROOT / file_name
    with open(path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css("styles/styles.css")
# -------------------------------------------------------------------
# 기본 앱 정보
# -------------------------------------------------------------------
# Image.MAX_IMAGE_PIXELS = None
OUTPUT_DIR = PROJECT_ROOT / "DS_Output"
CODE_MAPPING_FILE = OUTPUT_DIR / "CodeMapping.csv"

SOLUTION_NAME = "Data Consistency Analysis(데이터 일관성 분석)"
SOLUTION_KOR_NAME = "Data Consistency Analysis"
APP_NAME = "Data Consistency Analysis"
APP_DESC = """#### 데이터 일관성(Data Consistency)이란 데이터베이스 내의 데이터들이 서로 모순되지 않고 일관된 상태를 유지하는 것을 의미합니다. """
APP_DESC2 = """##### 컬럼별로 시스템 전체 일관성을 체크합니다. 동일한 이름 컬럼의 OracleType 또는 Format이 다른 경우 표시합니다. """


from util.Files_FunctionV20 import load_yaml_datasense, set_page_config
set_page_config(APP_NAME)


def display_metrics(df_cm):
    st.write("---")
    st.subheader("🧪 데이터 일관성 분석 요약 정보")

    if df_cm is None or df_cm.empty:
        st.warning("CodeMapping 데이터가 비어 있습니다.")
        return

    if "MasterType" in df_cm.columns:
        df_m = df_cm[df_cm["MasterType"] == "Master"].copy()
    else:
        df_m = df_cm.copy()

    if df_m.empty:
        st.warning("MasterType=Master 인 행이 없습니다.")
        return

    files = int(df_m["FileName"].nunique())
    columns = int(df_m["ColumnName"].nunique())

    if "HasBlank" in df_m.columns:
        df = df_m[df_m["HasBlank"] == 0].copy()
    else:
        df = df_m.copy()
    not_has_blank_columns = int(df["ColumnName"].nunique()) if len(df) else 0

    if "OracleType" in df.columns:
        oracle_type_cols = df.groupby("ColumnName")["OracleType"].nunique()
        oracle_type_cols_count = int((oracle_type_cols > 1).sum())
        oracle_type_1 = int((oracle_type_cols == 1).sum())
    else:
        oracle_type_cols_count = 0
        oracle_type_1 = 0

    if "Format" in df.columns:
        format_cols = df.groupby("ColumnName")["Format"].nunique()
        format_cols_count = int((format_cols > 1).sum())
        format_1 = int((format_cols == 1).sum())
    else:
        format_cols_count = 0
        format_1 = 0

    summary = {
        "전체 파일수": f"{files:,}",
        "전체 컬럼수": f"{columns:,}",
        "공백 없는 컬럼수": f"{not_has_blank_columns:,}",
        "OracleType 동일": f"{oracle_type_1:,}",
        "OracleType 상이": f"{oracle_type_cols_count:,}",
        "Format 동일": f"{format_1:,}",
        "Format 상이": f"{format_cols_count:,}",
    }

    metric_colors = {
        "전체 파일수": "#1f77b4",
        "전체 컬럼수": "#2ca02c",
        "공백 없는 컬럼수": "#ff7f0e",
        "OracleType 동일": "#1a9850",
        "OracleType 상이": "#d62728",
        "Format 동일": "#9467bd",
        "Format 상이": "#e377c2",
    }

    display_kpi_metrics(summary, metric_colors, "데이터 일관성 요약")
#-------------------------------------------------
# 2. 데이터 일관성 체크 함수
def consistency_analysis(df_cm):
    st.write("---")
    # --- UI: 데이터 모델 일관성 분석 (Group By 방식) ---
    st.subheader("🧪 데이터 일관성 분석")

    tmp_df = df_cm[df_cm['HasBlank'] == 0].copy()

    summary_df = tmp_df.groupby('ColumnName').agg(
        **{
            'File #': ('FileName', 'nunique'),
            'OracleType #': ('OracleType', 'nunique'),
            'Format #': ('Format', 'nunique') if 'Format' in tmp_df.columns else ('FileName', 'size'),
            'DetailDataType #': ('DetailDataType', 'nunique') if 'DetailDataType' in tmp_df.columns else ('FileName', 'size'),
            'Attribute #': ('Attribute', 'nunique') if 'Attribute' in tmp_df.columns else ('FileName', 'size'),
        }
    ).reset_index()

    if 'Format' not in tmp_df.columns:
        summary_df['Format #'] = 0

    # summary_df = summary_df[(summary_df['File #'] > 1) & (summary_df['OracleType #'] > 1) & (summary_df['Format #'] > 1)] 
    # summary_df 첫 컬럼에 select 컬럼 추가 
    summary_df.insert(0, 'Select', False)
    summary_df = summary_df.sort_values('OracleType #', ascending=False)

    _prog_cols = ['File #', 'OracleType #', 'Format #', 'DetailDataType #', 'Attribute #']
    for _c in _prog_cols:
        if _c in summary_df.columns:
            summary_df[_c] = pd.to_numeric(summary_df[_c], errors="coerce").fillna(0)

    def _consistency_prog_max(col: str) -> float:
        if col not in summary_df.columns:
            return 1.0
        m = summary_df[col].max()
        return max(float(m), 1.0) if pd.notna(m) else 1.0

    _cm = {c: _consistency_prog_max(c) for c in _prog_cols}

    edited_df = st.data_editor(
        summary_df,
        width='stretch',
        hide_index=True,
        height=600,
        column_config={
            'Select': st.column_config.CheckboxColumn('Select', help='컬럼 선택'),
            'ColumnName': st.column_config.TextColumn('ColumnName', help='물리 컬럼명'),
            'File #': st.column_config.ProgressColumn(
                'File #', help='파일 수(유니크)', min_value=0, max_value=_cm['File #'], format='%d',
            ),
            'OracleType #': st.column_config.ProgressColumn(
                'OracleType #', help='OracleType 유니크 개수', min_value=0, max_value=_cm['OracleType #'], format='%d',
            ),
            'Format #': st.column_config.ProgressColumn(
                'Format #', help='Format 유니크 개수', min_value=0, max_value=_cm['Format #'], format='%d',
            ),
            'DetailDataType #': st.column_config.ProgressColumn(
                'DetailDataType #', help='DetailDataType 유니크 개수', min_value=0, max_value=_cm['DetailDataType #'], format='%d',
            ),
            'Attribute #': st.column_config.ProgressColumn(
                'Attribute #', help='Attribute 유니크 개수', min_value=0, max_value=_cm['Attribute #'], format='%d',
            ),
        },
    )

    st.divider()
    selected_cols = edited_df[edited_df['Select'] == True]['ColumnName'].tolist()
    if len(selected_cols) > 0:
        st.write(f"Selected Columns: {selected_cols}")
        selected_df = df_cm[df_cm['ColumnName'].isin(selected_cols)]
        
        display_cols = ['ColumnName', 'FileName', 'OracleType', 'Format', 'FormatCnt', 'FormatTop10', 'FormatTopRate', 'DetailDataType', 'Attribute', 'LenCnt', 'LenMin', 'LenMax', 'ValueCnt', 'Null(%)', 'Unique(%)', 'HasBlank', 'Top10']
        df_display = selected_df[display_cols].sort_values(['ColumnName', 'OracleType', 'Format'])
       
        st.dataframe(df_display, width='stretch', hide_index=True, height=500)
    else:
        st.write("No columns selected")

    # return res_type, res_format
#-------------------------------------------------
# 3. 논리적 일관성 체크 함수
def consistency_analysis_logical(df_cm):
    st.write("---")
    # --- UI: 데이터 모델 일관성 분석 (Group By 방식) ---
    st.subheader("🧪 논리적 일관성 분석")
    st.write("##### 논리적 일관성 분석은 물리적 컬럼명 기준이 아니라 참조 컬럼명(Attribute) 기준으로 분석합니다.")

    # tmp_df = df_cm[df_cm['HasBlank'] == 0].copy()
    tmp_df = df_cm.copy()

    summary_df = tmp_df.groupby('Attribute', as_index=False).agg(
        **{
            'File #': ('FileName', 'nunique'),
            'OracleType #': ('OracleType', 'nunique'),
            'Format #': ('Format', 'nunique') if 'Format' in tmp_df.columns else ('FileName', 'size'),
            'DetailDataType #': ('DetailDataType', 'nunique') if 'DetailDataType' in tmp_df.columns else ('FileName', 'size'),
        }
    )

    summary_df = summary_df.sort_values('File #', ascending=False)

    if 'Format' not in tmp_df.columns:
        summary_df['Format #'] = 0

    colname_count = (
        tmp_df.drop_duplicates(['Attribute', 'FileName', 'ColumnName'])
              .groupby('Attribute')
              .size()
              .reset_index(name='ColumnName #')
    )
    summary_df = summary_df.merge(colname_count, on='Attribute', how='left')

    # summary_df = summary_df[(summary_df['File #'] > 1) & (summary_df['OracleType #'] > 1) & (summary_df['Format #'] > 1)] 
    # summary_df 첫 컬럼에 select 컬럼 추가 
    summary_df.insert(0, 'Select', False)

    _prog_cols_logical = ['File #', 'OracleType #', 'Format #', 'DetailDataType #']
    for _c in _prog_cols_logical:
        if _c in summary_df.columns:
            summary_df[_c] = pd.to_numeric(summary_df[_c], errors="coerce").fillna(0)

    def _logical_prog_max(col: str) -> float:
        if col not in summary_df.columns:
            return 1.0
        m = summary_df[col].max()
        return max(float(m), 1.0) if pd.notna(m) else 1.0

    _lm = {c: _logical_prog_max(c) for c in _prog_cols_logical}

    edited_df = st.data_editor(
        summary_df,
        width='stretch',
        hide_index=True,
        height=600,
        column_config={
            'Select': st.column_config.CheckboxColumn('Select', help='속성 선택'),
            'Attribute': st.column_config.TextColumn('Attribute', help='논리 속성명'),
            'File #': st.column_config.ProgressColumn(
                'File #', help='파일 수(유니크)', min_value=0, max_value=_lm['File #'], format='%d',
            ),
            'OracleType #': st.column_config.ProgressColumn(
                'OracleType #', help='OracleType 유니크 개수', min_value=0, max_value=_lm['OracleType #'], format='%d',
            ),
            'Format #': st.column_config.ProgressColumn(
                'Format #', help='Format 유니크 개수', min_value=0, max_value=_lm['Format #'], format='%d',
            ),
            'DetailDataType #': st.column_config.ProgressColumn(
                'DetailDataType #', help='DetailDataType 유니크 개수', min_value=0, max_value=_lm['DetailDataType #'], format='%d',
            ),
        },
    )

    st.divider()
    selected_cols = edited_df[edited_df['Select'] == True]['Attribute'].tolist()
    if len(selected_cols) > 0:
        st.write(f"##### Attributes: {selected_cols} 를 참조하는 모든 파일 정보를 출력합니다.")
        selected_df = df_cm[df_cm['Attribute'].isin(selected_cols)]
        
        display_cols = ['Attribute',  'FileName', 'ColumnName', 'Format', 
            'LenCnt', 'LenMin', 'LenMax', 'ValueCnt', 'Null(%)', 'Unique(%)', 'FormatCnt', 'HasBlank', 'Top10']
        df_display = selected_df[display_cols].sort_values('Attribute')
        st.dataframe(df_display, width='stretch', hide_index=True, height=500)
    else:
        st.write("No attributes selected")

def display_detail_info(df_cm, res_format):
    dis_cols = ['FileName', 'ColumnName', 'OracleType','FormatCnt', 'FormatTop10', 
        'Top10', 'Top10(%)','ValueCnt', 'MinString', 'MaxString', 'ModeString' ]
    if res_format is None or res_format.empty:
        st.info("표시할 Format 불일치 상세 정보가 없습니다.")
        return

    # res_format에서 컬럼을 선택 -> 해당 컬럼을 사용하는 모든 파일 정보 출력
    base_df = df_cm.copy()
    base_df['FileName'] = base_df['FileName'].astype(str).str.strip()
    selected_cols = [c for c in dis_cols if c in base_df.columns]
    selected_column_names = res_format['ColumnName'].dropna().unique().tolist()
    selected_column_names = sorted(selected_column_names)
    selected_column = st.selectbox('컬럼 선택', selected_column_names, key="consistency_column_select")
    diff_format_cols_df = base_df[
        base_df['ColumnName'] == selected_column
    ][selected_cols]
    st.dataframe(diff_format_cols_df, width='stretch', hide_index=True, height=500)

def load_data(file_path : Path) -> pd.DataFrame:
    extension = file_path.suffix.lower()
    encoding_list = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']
    if extension == '.csv':
        for encoding in encoding_list:
            try:
                return pd.read_csv(file_path, encoding=encoding)
            except Exception:
                continue
        return pd.DataFrame()
    elif extension == '.xlsx':
        for encoding in encoding_list:
            try:
                return pd.read_excel(file_path, encoding=encoding)
            except Exception:
                continue
        return pd.DataFrame()
    elif extension == '.pkl':
        return pd.read_pickle(file_path)
    else:
        st.error(f"지원하지 않는 파일 형식: {extension}")
        return pd.DataFrame()

#-------------------------------------------------
def main():
    st.title(SOLUTION_NAME)
    st.markdown(APP_DESC)
    st.caption(APP_DESC2)

    df_cm = load_data(CODE_MAPPING_FILE)

    display_metrics(df_cm)
    consistency_analysis(df_cm)

    consistency_analysis_logical(df_cm)

    # display_detail_info(df_cm, res_format)


if __name__ == "__main__":
    main() 