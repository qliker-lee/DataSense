# -*- coding: utf-8 -*-
"""
2026.03.11  Qliker 
📊 Data Logical Relationship
"""
import sys
from pathlib import Path
import streamlit as st
# import subprocess

import pandas as pd
import numpy as np  
from dataclasses import dataclass
from typing import Dict, Any, Optional
import ast
import plotly.express as px
import plotly.graph_objects as go
from graphviz import Digraph
from difflib import SequenceMatcher # 문자열 유사도 계산 모듈
import ast # 문자열을 리스트로 변환 모듈

import itertools # 모든 조합을 계산하는 모듈
import logging

# sentence_transformers → torch 로드. WinError 1114(c10.dll) 시 상단 import만으로도 크래시하므로 지연 로드.
_ST_EMBED = None  # (SentenceTransformer, util) 또는 로드 실패 시 False
_ST_EMBED_ERR = None
# Streamlit 경고 억제
logging.getLogger('streamlit.runtime.scriptrunner.script_run_context').setLevel(logging.ERROR)

# ------------------------------------------------------------
# 프로젝트 경로 & 기본 YAML 경로/파일 설정
# ------------------------------------------------------------
CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# # 폰트 크기 조정
# st.markdown("""<style> html, body, [class*="css"]  { font-size: 16px; } </style> """, unsafe_allow_html=True)
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
# App Config
# -------------------------------------------------------------------
def _get_sentence_transformers():
    """PyTorch DLL 오류 등으로 실패해도 페이지 나머지는 동작하도록 지연 import."""
    global _ST_EMBED, _ST_EMBED_ERR
    if _ST_EMBED is False:
        return None, None, _ST_EMBED_ERR
    if _ST_EMBED is not None:
        return _ST_EMBED[0], _ST_EMBED[1], None
    try:
        import importlib.util

        if importlib.util.find_spec("sentence_transformers") is None:
            _ST_EMBED = False
            _ST_EMBED_ERR = "sentence_transformers 모듈이 설치되지 않았습니다."
            return None, None, _ST_EMBED_ERR

        from sentence_transformers import SentenceTransformer, util as st_util

        _ST_EMBED = (SentenceTransformer, st_util)
        return SentenceTransformer, st_util, None
    except Exception as e:
        _ST_EMBED = False
        _ST_EMBED_ERR = str(e)
        return None, None, _ST_EMBED_ERR


def _difflib_name_similarity(a: str, b: str) -> float:
    """PyTorch 미사용 시 ColumnName 문자열 유사도 (mapping_verify의 get_similarity와 동일 규칙)."""
    x = str(a).replace(" ", "").lower()
    y = str(b).replace(" ", "").lower()
    return round(SequenceMatcher(None, x, y).ratio(), 4)


# -------------------------------------------------------------------
# 1. 경로 및 설정
# -------------------------------------------------------------------
CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from util.streamlit_warnings import setup_streamlit_warnings
setup_streamlit_warnings()

from util.Files_FunctionV20 import load_yaml_datasense, set_page_config
from util.DS_31_Quality_Rule import DataQualityAnalysisClass, DataQualityReportClass
from util.Display import display_kpi_metrics
# -------------------------------------------------------------------
# 기본 앱 정보
# -------------------------------------------------------------------
APP_NAME = "Data Relationship Analysis (데이터 관계 분석)"
APP_DESC = "#### 모든 파일의 각 컬럼들에 대한 물리적/논리적 관계를 분석합니다. "
OUTPUT_DIR = PROJECT_ROOT / "DS_Output"

set_page_config(APP_NAME)

dataqualityanalysis = DataQualityAnalysisClass()
dataqualityreport = DataQualityReportClass()

# Color Define (그래프 색상 정의)
BLACK = "#000000" # 검정색
BLUE = "#1f77b4" # 파랑색
GREEN = "#2ca02c" # 초록색
AMBER = "#ff7f0e" # 앰버
PINK = "#9467bd" # 분홍
GRAY = "#808080" # 회색
SKYBLUE = "#87CEEB" # 하늘색
# -------------------------------------------------------------------
# [NEW] 시각화 및 스타일링 유틸리티
# -------------------------------------------------------------------
def merge_codemapping(codemapping_df: pd.DataFrame, codemapping_6th_df: pd.DataFrame) -> pd.DataFrame:
    """코드 매핑 병합"""
    # 소스 데이터 컬럼
    source_cols = ['FilePath', 'FileName', 'ColumnName', 'LenCnt', 'LenMin', 'LenMax', 'LenAvg', 'LenMode', 'RecordCnt',
     'ValueCnt', 'Null(%)', 'Unique(%)', 'FormatCnt', 'Format', 'Format(%)', 
     'HasBlank', 'HasKor', 'HasAlpha', 'HasOnlyAlpha', 'HasOnlyNum', 'HasOnlyKor', 'HasOnlyAlphanum']
    source_df = codemapping_df[source_cols].copy()

    # 매핑 데이터 컬럼
    mapping_df = codemapping_6th_df.copy()
    merged_df = pd.merge(mapping_df, source_df, on=['FilePath', 'FileName', 'ColumnName'], how='left')

    # 마스터 데이터 컬럼
    master_cols = ['FilePath', 'FileName', 'ColumnName', 'LenCnt', 'LenMin', 'LenMax', 'LenAvg', 'LenMode', 'RecordCnt',
     'ValueCnt', 'Null(%)', 'Unique(%)', 'FormatCnt', 'Format', 'Format(%)', 
     'HasBlank', 'HasKor', 'HasAlpha', 'HasOnlyAlpha', 'HasOnlyNum', 'HasOnlyKor', 'HasOnlyAlphanum']
    master_df = codemapping_df[master_cols].copy()

    master_df.rename(columns={
        'FilePath': 'MasterFilePath',
        'FileName': 'MasterFile',
        'ColumnName': 'MasterColumn',
        'LenCnt': 'M_LenCnt',
        'LenMin': 'M_LenMin',
        'LenMax': 'M_LenMax',
        'LenAvg': 'M_LenAvg',
        'LenMode': 'M_LenMode',
        'RecordCnt': 'M_RecordCnt',
        'ValueCnt': 'M_ValueCnt',
        'Null(%)': 'M_Null(%)',
        'Unique(%)': 'M_Unique(%)',
        'FormatCnt': 'M_FormatCnt',
        'Format': 'M_Format',
        'Format(%)': 'M_Format(%)',
        'HasBlank': 'M_HasBlank',
        'HasKor': 'M_HasKor',
        'HasAlpha': 'M_HasAlpha',
        'HasOnlyAlpha': 'M_HasOnlyAlpha',
        'HasOnlyNum': 'M_HasOnlyNum',
        'HasOnlyKor': 'M_HasOnlyKor',
        'HasOnlyAlphanum': 'M_HasOnlyAlphanum',
    }, inplace=True)

    merged_df = pd.merge(merged_df, master_df, on=['MasterFilePath', 'MasterFile', 'MasterColumn'], how='left')
    merged_df = merged_df.drop(columns=['MasterType', 'MasterFilePath', 'ReferenceMasterType', 'CompareLength'])

    return merged_df


def mapping_verify(df: pd.DataFrame) -> pd.DataFrame:
    """코드 매핑 검증"""
    def get_similarity(str1, str2):
        """ 두 문자열의 유사도를 0.0과 1.0 사이의 값으로 리턴합니다.  1.0에 가까울수록 일치도가 높습니다.  """
        # 공백 제거 및 소문자화 (비교 정확도를 높이기 위함)
        str1_clean = str1.replace(" ", "").lower()
        str2_clean = str2.replace(" ", "").lower()
        
        ratio = SequenceMatcher(None, str1_clean, str2_clean).ratio() # 유사도 계산
        
        return round(ratio, 2)

    def _parse_list(value):
        if pd.isna(value):
            return None
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = ast.literal_eval(value)
                return parsed if isinstance(parsed, list) else None
            except Exception:
                return None
        return None

    def _top_index_by_rate(rate_list, threshold=95.0):
        if not rate_list:
            return None
        cum = 0.0
        idx_pos = None
        for i, rate in enumerate(rate_list):
            try:
                cum += float(rate)
            except Exception:
                return None
            if cum >= threshold:
                idx_pos = i + 1  # 1-based position per 요구사항 예시
                break
        if idx_pos is None:
            idx_pos = len(rate_list)
        return idx_pos

    def _top_list_by_rate(rate_list, value_list, threshold=95.0):
        if not rate_list or not value_list:
            return None
        idx_pos = _top_index_by_rate(rate_list, threshold=threshold)
        if idx_pos is None:
            return None
        return value_list[:idx_pos]

    def _compare_row(row):
        fmt_rates = _parse_list(row.get("FormatTopRate"))
        fmt_values = _parse_list(row.get("FormatTop10"))
        mst_rates = _parse_list(row.get("MasterFormatTopRate"))
        mst_values = _parse_list(row.get("MasterFormatTop10"))

        fmt_top = _top_list_by_rate(fmt_rates, fmt_values)
        mst_top = _top_list_by_rate(mst_rates, mst_values)
        if fmt_top is None or mst_top is None:
            return False
        return sorted(fmt_top) == sorted(mst_top)


    df["S_Index"] = df["FormatTopRate"].apply(
        lambda v: _top_index_by_rate(_parse_list(v))
    )

    df["S_List"] = df.apply(
        lambda row: _top_list_by_rate(
            _parse_list(row.get("FormatTopRate")),
            _parse_list(row.get("FormatTop10")),
        ),
        axis=1,
    )

    df["M_Index"] = df["MasterFormatTopRate"].apply(
        lambda v: _top_index_by_rate(_parse_list(v))
    )

    df["M_List"] = df.apply(
        lambda row: _top_list_by_rate(
            _parse_list(row.get("MasterFormatTopRate")),
            _parse_list(row.get("MasterFormatTop10")),
        ),
        axis=1,
    )

    df["verify"] = df.apply(_compare_row, axis=1)
    df["similarity"] = df.apply(lambda row: get_similarity(row["ColumnName"], row["MasterColumn"]), axis=1)

    return df

def mapping_verify_2nd(df: pd.DataFrame) -> pd.DataFrame:
    """코드 매핑 검증 2단계"""
    df = df.copy()

    # pandas Series 비교는 벡터 연산으로 처리
    match_100 = df["MatchRate(%)"] == 100
    verified = df["verify"] == True
    not_verified = df["verify"] == False
    match_rate = pd.to_numeric(df["MatchRate(%)"], errors="coerce")

    cond_case0 = (((df["Format"].str.len() <= 2) & (df["HasOnlyNum"] == True)) | 
                ((df["M_Format"].str.len() <= 2) & (df["M_HasOnlyNum"] == True)) |
                ((df["Format"].str.len() <= 2) & (df["similarity"] < 0.2))
                )

    cond_case1 = match_100 & verified
    cond_case2 = match_100 & not_verified & (df["HasKor"] == True) & (df["M_HasKor"] == True)
    cond_case3 = match_100 & not_verified & (df["HasAlpha"] == True) & (df["M_HasAlpha"] == True)
    cond_case4 = (match_rate > 50) & (df["similarity"] > 0.5)
    cond_case5 = verified & (df["S_Index"] > 5) & (df["M_Index"] > 5)
    cond_case6 = (df["S_Index"] == 1) & (df["M_Index"] == 1)
    cond_case7 = match_100 & not_verified & (df["S_Index"] <= 2) & (df["M_Index"] <= 2)
    cond_case8 = (match_100 & 
                (df["similarity"] > 0.3) & 
                not_verified & 
                (df["S_Index"] <= 1) & (df["M_Index"] <= 3) & 
                (df["HasKor"] == False) & (df["M_HasKor"] == False))
    cond_case9 = verified & (df["S_Index"] == df["M_Index"])
    cond_case10= (df["Format"].str.len() > 3) & (df["M_Format"].str.len() > 3) & (df["Unique(%)"] != 100) & (df["M_Unique(%)"] == 100)
    cond_case11 = (match_rate > 80) & (df["HasKor"] == True) & (df["M_HasKor"] == True)
    cond_case12 = ((match_rate > 80) & 
                (df["HasAlpha"] == True) & 
                (df["M_HasAlpha"] == True) & 
                (df["S_Index"] <5) & (df["M_Index"] <= 5))
    cond_case13 = (df["Format"].str.len() > 4) & (df["M_Format"].str.len() > 4)
    cond_case14 = ((match_rate > 50) & 
                (df["similarity"] >= 0.2) & 
                (df["S_Index"] > 5) & (df["M_Index"] > 5) &
                (((df["HasKor"] == True) & (df["M_HasKor"] == True)) | 
                ((df["HasAlpha"] == True) & (df["M_HasAlpha"] == True))))

    # 15	MatchRate(%) > 50 & similarity >= 0.1 & S_Index ==10 & M_Index == 10 &HasBlank== True & ((HasKor = True & M_HasKor = True) | (HasAlpha = True & M_HasAlpha = True))	TRUE	
    cond_case15 = ((match_rate > 50) & 
                (df["similarity"] >= 0.1) & 
                (df["S_Index"] == 10) & (df["M_Index"] == 10) & 
                (((df["HasKor"] == True) & (df["M_HasKor"] == True)) | 
                ((df["HasAlpha"] == True) & (df["M_HasAlpha"] == True))))

    cond_case16 = ((match_rate > 50) & 
                (df["similarity"] >= 0.3) & 
                (df["S_Index"] >= 2) & (df["M_Index"] >= 2) &
                (((df["HasKor"] == True) & (df["M_HasKor"] == True)) | 
                ((df["HasAlpha"] == True) & (df["M_HasAlpha"] == True)))) 
    cond_case17 = ((match_rate > 50) & 
                (df["S_Index"] == 10) & (df["M_Index"] == 10) &
                (((df["HasKor"] == True) & (df["M_HasKor"] == True)) | 
                ((df["HasAlpha"] == True) & (df["M_HasAlpha"] == True))))
    cond_case18 = ((df["similarity"] >= 0.3) & 
                (df["HasBlank"] == False) & (df["M_HasBlank"] == False) &
                (df["HasKor"] == False) & (df["M_HasKor"] == False))

    cond_case19 = (match_rate > 99) & (df["M_HasKor"] == False)

    cond_case21 = match_100 & not_verified & (df["S_Index"] <= 5) & (df["M_Index"] >= 5)
    cond_case22 = match_100 & not_verified & (df["HasOnlyNum"] == True) & (df["M_HasKor"] == True)
    cond_case23 = (match_rate > 80) & not_verified & (df["similarity"] < 0.3) & (df["HasAlpha"] == True) & (df["M_HasAlpha"] == True)
    cond_case24 = (match_rate > 80) & not_verified & (df["similarity"] < 0.3) & (df["HasOnlyNum"] == True) & (df["M_HasOnlyNum"] == True)
    cond_case25 = (match_rate > 80) & (df["HasAlpha"] == True) & (df["M_HasAlpha"] == True) & ((df["S_Index"] > 5) | (df["M_Index"] > 5))
    cond_case26 = (match_rate > 95) & ((df["HasKor"] != df["M_HasKor"]) | 
                                        (df["HasAlpha"] != df["M_HasAlpha"]) | 
                                        ((df["HasOnlyNum"] == True) & (df["M_HasOnlyNum"] == True)))

    df["mapping_case"] = 0
    df["mapping_result"] = False
    remaining = pd.Series(True, index=df.index)

    # df["S_List"] 전체 문자열 길이가 2 이하이면 거짓으로 처리
    df.loc[cond_case0 & remaining, ["mapping_case", "mapping_result"]] = [0, False]
    remaining &= ~cond_case0

    df.loc[cond_case1 & remaining, ["mapping_case", "mapping_result"]] = [1, True]
    remaining &= ~cond_case1
    df.loc[cond_case2 & remaining, ["mapping_case", "mapping_result"]] = [2, True]
    remaining &= ~cond_case2
    df.loc[cond_case3 & remaining, ["mapping_case", "mapping_result"]] = [3, True]
    remaining &= ~cond_case3
    df.loc[cond_case4 & remaining, ["mapping_case", "mapping_result"]] = [4, True]
    remaining &= ~cond_case4
    df.loc[cond_case5 & remaining, ["mapping_case", "mapping_result"]] = [5, True]
    remaining &= ~cond_case5
    df.loc[cond_case6 & remaining, ["mapping_case", "mapping_result"]] = [6, True]
    remaining &= ~cond_case6
    df.loc[cond_case7 & remaining, ["mapping_case", "mapping_result"]] = [7, True]
    remaining &= ~cond_case7
    df.loc[cond_case8 & remaining, ["mapping_case", "mapping_result"]] = [8, True]
    remaining &= ~cond_case8
    df.loc[cond_case9 & remaining, ["mapping_case", "mapping_result"]] = [9, True]
    remaining &= ~cond_case9
    df.loc[cond_case10 & remaining, ["mapping_case", "mapping_result"]] = [10, True]
    remaining &= ~cond_case10
    df.loc[cond_case11 & remaining, ["mapping_case", "mapping_result"]] = [11, True]
    remaining &= ~cond_case11
    df.loc[cond_case12 & remaining, ["mapping_case", "mapping_result"]] = [12, True]
    remaining &= ~cond_case12
    df.loc[cond_case13 & remaining, ["mapping_case", "mapping_result"]] = [13, True]
    remaining &= ~cond_case13
    df.loc[cond_case14 & remaining, ["mapping_case", "mapping_result"]] = [14, True]
    remaining &= ~cond_case14
    df.loc[cond_case15 & remaining, ["mapping_case", "mapping_result"]] = [15, True]
    remaining &= ~cond_case15
    df.loc[cond_case16 & remaining, ["mapping_case", "mapping_result"]] = [16, True]
    remaining &= ~cond_case16
    df.loc[cond_case17 & remaining, ["mapping_case", "mapping_result"]] = [17, True]
    remaining &= ~cond_case17
    df.loc[cond_case18 & remaining, ["mapping_case", "mapping_result"]] = [18, True]
    remaining &= ~cond_case18
    df.loc[cond_case19 & remaining, ["mapping_case", "mapping_result"]] = [19, True]
    remaining &= ~cond_case19

    df.loc[cond_case21 & remaining, ["mapping_case", "mapping_result"]] = [21, False]
    remaining &= ~cond_case21
    df.loc[cond_case22 & remaining, ["mapping_case", "mapping_result"]] = [22, False]
    remaining &= ~cond_case22
    df.loc[cond_case23 & remaining, ["mapping_case", "mapping_result"]] = [23, False]
    remaining &= ~cond_case23
    df.loc[cond_case24 & remaining, ["mapping_case", "mapping_result"]] = [24, False]
    remaining &= ~cond_case24
    df.loc[cond_case25 & remaining, ["mapping_case", "mapping_result"]] = [25, False]
    remaining &= ~cond_case25
    
    return df

#--------------------------------------------------
# Display Metrics
#--------------------------------------------------
def logical_relationship_summary( df: pd.DataFrame):
    """논리적 연관 관계 요약 지표"""
    total_files = df['FileName'].nunique()
    total_columns = df['ColumnName'].nunique()
    related_files = df['MasterFile'].nunique()
    related_columns = df[['MasterFile', 'MasterColumn']].drop_duplicates().shape[0]
    match100_cnt = df['MatchRate(%)'].eq(100).sum()
    match_over90_cnt = df['MatchRate(%)'].gt(90).sum() - match100_cnt
    match_over80_cnt = df['MatchRate(%)'].gt(80).sum() - match100_cnt - match_over90_cnt
    match_under70_cnt = df['MatchRate(%)'].lt(70).sum()

    summary = {
        "총 테이블 수":  f"{total_files}",
        "연관컬럼 #":    f"{total_columns}",
        "참조 테이블 #": f"{related_files}",
        "참조 컬럼 #":  f"{related_columns}",
        "참조율 100%":  f"{match100_cnt}",
        "90~80%": f"{match_over90_cnt}",
        "80~70%": f"{match_over80_cnt}",
        "70% 미만": f"{match_under70_cnt}",
    }

    metric_colors = {
        "총 테이블 수":     BLACK,       # 검정색
        "연관컬럼 #":       BLACK,       # 검정색
        "참조 테이블 #":    BLACK,       # 검정색
        "참조 컬럼 #":      BLACK,       # 검정색
        "참조율 100%":      BLUE,       # 파랑색
        "90~80%":          GREEN,       # 초록색
        "80~70%":          AMBER,       # 앰버
        "70% 미만":         GRAY,       # 회색
    }

    display_kpi_metrics(summary, metric_colors, '논리적 연관 관계 요약 지표')

#--------------------------------------------------
# Display File Info
#--------------------------------------------------
def display_file_info(df: pd.DataFrame) -> Optional[list[str]]:
    st.markdown("##### 📁 File Info")

    # 파일별 컬럼수, 매핑컬럼수, 매핑컬럼 중복 수, 매핑MasterFile수, 매핑MasterColumn수로 집계함
    file_info_df = df.groupby(['FileName']).agg(
        ColumnNameCount=('ColumnName', 'nunique'),
        MasterFileUniqueCount=('MasterFile', 'nunique'),
        MasterColumnUniqueCount=('MasterColumn', 'nunique'),
    ).reset_index()

    file_info_df.rename(columns={
        'ColumnNameCount': '연관 컬럼 #',
        'MasterFileUniqueCount': '참조 테이블 #',
        'MasterColumnUniqueCount': '참조 컬럼 #',
    }, inplace=True)

    # 첫컬럼에 select 컬럼 추가
    file_info_df.insert(0, 'select', False)
    _col_a, _col_b, _col_c = '연관 컬럼 #', '참조 테이블 #', '참조 컬럼 #'
    _max_a = max(int(file_info_df[_col_a].max()), 1) if len(file_info_df) else 1
    _max_b = max(int(file_info_df[_col_b].max()), 1) if len(file_info_df) else 1
    _max_c = max(int(file_info_df[_col_c].max()), 1) if len(file_info_df) else 1
    edited_file_info_df = st.data_editor(
        file_info_df,
        width='stretch',
        height=500,
        hide_index=True,
        column_config={
            _col_a: st.column_config.ProgressColumn(
                _col_a,
                min_value=0,
                max_value=_max_a,
                format="%d",
            ),
            _col_b: st.column_config.ProgressColumn(
                _col_b,
                min_value=0,
                max_value=_max_b,
                format="%d",
            ),
            _col_c: st.column_config.ProgressColumn(
                _col_c,
                min_value=0,
                max_value=_max_c,
                format="%d",
            ),
        },
    )
    selected_file_names = edited_file_info_df[edited_file_info_df['select'] == True]['FileName'].tolist()
    if len(selected_file_names) > 0:
        return selected_file_names
    st.info("💡 목록에서 파일을 선택하시면 상세 파일 정보를 보실 수 있습니다.")
    return None

def display_selected_file_info(df: pd.DataFrame):
    
    cols = ['FileName', 'ColumnName', 'MasterFile', 'MasterColumn', 'MatchRate(%)',  
    'Null(%)', 'Unique(%)', 'verify', 'mapping_case']

    df = df[cols]

    df.rename(columns={
        'FileName': 'File Name',
        'ColumnName': 'Column Name',
        'MasterFile': '참조 파일',
        'MasterColumn': '참조 컬럼',
        # 'CompareCount': '비교 건수',
        'MatchRate(%)': '일치율(%)',    
        'Null(%)': 'Null(%)',
        'Unique(%)': 'Unique(%)',
        'verify': '포맷 일치',
        'mapping_case': '참조 케이스',
        'mapping_result': '참조 결과',
    }, inplace=True)

    df["일치율(%)"] = pd.to_numeric(df["일치율(%)"], errors="coerce")
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        height=500,
        column_config={
            "일치율(%)": st.column_config.ProgressColumn(
                "일치율(%)",
                help="Master와의 데이터 일치율(0~100%)",
                min_value=0,
                max_value=100,
                format="%.1f%%",
            ),
        },
    )
    
 #---------------------------------------------------------
 # Graphviz 그래프 생성
 #---------------------------------------------------------
# sys.setrecursionlimit(10000)


def _relationship_map_register_target(
    *,
    score: float,
    src_id: str,
    tgt_item_label: str,
    grouped_targets_by_src: dict,
) -> None:
    """모든 구간을 그룹 노드로 집계 (100% 포함)."""
    if score >= 100:
        group_key, group_title, group_color = "group_100", "100% 그룹", "#81D4FA"
    elif score >= 90:
        group_key, group_title, group_color = "group_90", "90~99% 그룹", "#C8E6C9"
    elif score >= 80:
        group_key, group_title, group_color = "group_80", "80~90% 그룹", "#FFC107"
    elif score >= 70:
        group_key, group_title, group_color = "group_70", "70~80% 그룹", "#F8BBD0"
    else:
        group_key, group_title, group_color = "group_60", "60% 미만 그룹", "#E0E0E0"

    if src_id not in grouped_targets_by_src:
        grouped_targets_by_src[src_id] = {}
    if group_key not in grouped_targets_by_src[src_id]:
        grouped_targets_by_src[src_id][group_key] = {
            "title": group_title,
            "color": group_color,
            "items": set(),
        }
    grouped_targets_by_src[src_id][group_key]["items"].add(tgt_item_label)


def _relationship_map_render_groups(
    grouped_targets_by_src: dict, dot: Digraph, font_size: str
) -> None:
    group_order = ("group_100", "group_90", "group_80", "group_70", "group_60")
    for src_id, groups in grouped_targets_by_src.items():
        keys = sorted(
            groups.keys(),
            key=lambda k: group_order.index(k) if k in group_order else 99,
        )
        for group_key in keys:
            info = groups[group_key]
            if not info["items"]:
                continue
            items = sorted(info["items"])
            shown = items[:5]
            label = f"{info['title']}\n" + "\n".join(shown)
            group_node_id = f"{src_id}__{group_key}"
            dot.node(
                group_node_id,
                label=label,
                style="filled",
                fillcolor=info["color"],
                shape="box",
                fontsize=font_size,
            )
            dot.edge(
                src_id,
                group_node_id,
                color=info["color"],
                fontcolor=info["color"],
                penwidth="1.5",
            )


_RELATIONSHIP_MAP_CAPTION = (
    "색상은 참조율(또는 Similarity×100%) 구간별 그룹을 의미합니다.  "
    "🔵 : 100%(그룹)  |  🟢 : 90~99%(그룹)  |  🟠 : 80~89%(그룹)  |  "
    "🌸 : 70~79%(그룹)  |  ⚪ : 70% 미만(그룹)"
)


def logical_relationship_map(df: pd.DataFrame):
    if df is None or df.empty:
        st.warning("⚠️ 관계 맵을 생성할 데이터가 없습니다.")
        return

    required_cols = {"FileName", "ColumnName", "MasterFile", "MasterColumn", "MatchRate(%)"}
    if not required_cols.issubset(df.columns):
        st.error("컬럼 구성이 올바르지 않습니다.")
        return

    st.divider()
    st.markdown("### 🎯 Logical  Relationship & Reliability Map")

    # # [개선 1] 전체를 한꺼번에 그리지 않고, 선택한 파일만 그리도록 변경 (속도 향상 핵심)
    unique_files = sorted(df["FileName"].dropna().unique())
    selected_file = st.selectbox("파일을 선택하세요", unique_files)
    # selected_file = unique_files

    if selected_file:
        # 해당 파일 데이터 필터링
        f_df = df[df["FileName"] == selected_file].dropna(subset=["MasterFile", "MasterColumn"]).copy()
        
        if f_df.empty:
            st.info("선택한 파일에 대한 연관 데이터가 없습니다.")
            return

        # [개선 2] 샘플링 로직 유지 및 안내
        max_nodes = 100 # 성능을 위해 30~50개 권장
        if len(f_df) > max_nodes:
            st.info(f"💡 관계가 너무 많아 매칭률 상위 {max_nodes}건만 표시합니다.")
            f_df = f_df.sort_values("MatchRate(%)", ascending=False).head(max_nodes)

        # [개선 3] Graphviz 설정 최적화 대규모는 'neato', 계층 구조는 'dot'이 적합합니다. 
        # 여기서는 관계도이므로 'neato' 또는 'twopi'를 추천합니다.
        dot = Digraph(format='png', engine='dot') 
        display_dpi = '180'
        download_dpi = '180'
        dot.attr(
            rankdir='LR',  # LR, TB
            nodesep='0.1', # 0.5
            ranksep='0.1',  # 1.0
            fontname='Malgun Gothic',
            overlap='false',
            splines='true',
            dpi=display_dpi # 화면 표시용 DPI
        )
        # 그래프/노드/엣지 폰트 고정 (한글 깨짐 방지)
        dot.attr('node', fontname='Malgun Gothic')
        dot.attr('edge', fontname='Malgun Gothic')

        processed_nodes = set()
        grouped_targets_by_src = {}
        
        for _, row in f_df.iterrows():
            # ID값 단순화 (공백/특수문자 처리)
            src_id = f"{row['FileName']}.{row['ColumnName']}"
            tgt_id = f"{row['MasterFile']}.{row['MasterColumn']}"
            
            # src_label = f"{row['FileName']}\n({row['ColumnName']})"
            src_label = f"{row['ColumnName']}"
            tgt_label = f"{row['MasterFile']}\n({row['MasterColumn']})"
            tgt_item_label = f"{row['MasterFile']}({row['MasterColumn']})"
            
            try:
                score = float(row["MatchRate(%)"])
            except:
                score = 0.0

            FONT_SIZE = '10'
            # 노드 생성 (중복 방지)
            if src_id not in processed_nodes:
                dot.node(src_id, label=src_label, style='filled', fillcolor='#1E88E5', 
                         fontcolor='white', shape='box', fontsize=FONT_SIZE)                 
                processed_nodes.add(src_id)
            
            _relationship_map_register_target(
                score=score,
                src_id=src_id,
                tgt_item_label=tgt_item_label,
                grouped_targets_by_src=grouped_targets_by_src,
            )

        _relationship_map_render_groups(grouped_targets_by_src, dot, FONT_SIZE)

        # [개선 4] 렌더링 및 출력 (graphviz_chart 대신 PNG 표시 → 하단 불필요 여백 감소)
        display_png = None
        with st.spinner("그래프 생성 중..."):
            try:
                st.markdown("---")
                st.caption(_RELATIONSHIP_MAP_CAPTION)
                display_png = dot.pipe(format='png')
                st.image(display_png, use_container_width=True)
            except Exception as e:
                st.error(f"시각화 엔진 오류: {e}")

        if display_png is None:
            return

        try:
            dot.attr(dpi=download_dpi)
            png_bytes = dot.pipe(format='png')
            st.download_button(
                label="이미지 다운로드",
                data=png_bytes,
                file_name="logical_relationship.png",
                mime="image/png",
            )
        except Exception as e:
            st.warning(f"이미지 저장/다운로드 생성 실패: {e}")


def physical_relationship_map(df: pd.DataFrame):
    """선택 FileName 기준 ColumnName → R_FileName 물리 연관 맵 (logical_relationship_map 과 동일 Graphviz 스타일)."""
    if df is None or df.empty:
        st.warning("물리적 연관 관계를 생성할 데이터가 없습니다.")
        return

    required_cols = {"FileName", "ColumnName", "R_FileName", "R_ColumnName", "Similarity"}
    if not required_cols.issubset(df.columns):
        st.error(
            "컬럼 구성이 올바르지 않습니다. "
            "(FileName, ColumnName, R_FileName, R_ColumnName, Similarity 필요) "
            f"실제 컬럼명: {list(df.columns)}"
        )
        return

    st.divider()
    st.markdown("### 🧩 Physical Relationship & Reliability Map (일치/유사 파일명)")

    unique_files = sorted(df["FileName"].dropna().unique())
    selected_file = st.selectbox(
        "파일을 선택하세요", unique_files, key="physical_relationship_map_file"
    )
    if not selected_file:
        return

    f_df = prepare_physical_map_edges(df, selected_file)
    if f_df.empty:
        st.info("일치(S=1) 또는 유사(0.8<S<1) 관계가 없습니다.")
        return

    n_exact_cols = f_df.loc[_similarity_is_exact(f_df["Similarity"]), "ColumnName"].nunique()
    n_similar_cols = f_df.loc[_similarity_is_similar_band(f_df["Similarity"]), "ColumnName"].nunique()
    st.caption(
        f"맵 데이터: 요약 표와 동일 규칙(FileName·ColumnName·R_FileName dedup). "
        f"일치 컬럼 {n_exact_cols}개 · 유사 컬럼 {n_similar_cols}개 · 연결 {len(f_df)}건"
    )

    dot = Digraph(format="png", engine="dot")
    display_dpi = "250"
    download_dpi = "250"
    dot.attr(
        rankdir="LR",
        nodesep="0.2",    # 0.1
        ranksep="1.5",    # 0.1
        fontname="Malgun Gothic",
        overlap="false",
        splines="true",
        dpi=display_dpi,
    )
    dot.attr("node", fontname="Malgun Gothic")
    dot.attr("edge", fontname="Malgun Gothic")

    processed_nodes: set[str] = set()
    grouped_targets_by_src: dict = {}
    FONT_SIZE = "8"

    for _, row in f_df.iterrows():
        src_id = f"{selected_file}.{row['ColumnName']}"
        tgt_id = f"{row['R_FileName']}.{row['R_ColumnName']}"
        src_label = f"{row['ColumnName']}"
        tgt_label = f"{row['R_FileName']}\n({row['R_ColumnName']})"
        tgt_item_label = f"{row['R_FileName']}({row['R_ColumnName']})"

        try:
            score = float(row["Similarity"]) * 100.0
        except (TypeError, ValueError):
            score = 0.0

        if src_id not in processed_nodes:
            dot.node(
                src_id,
                label=src_label,
                style="filled",
                fillcolor="#1E88E5",
                fontcolor="white",
                shape="box",
                fontsize=FONT_SIZE,
            )
            processed_nodes.add(src_id)

        _relationship_map_register_target(
            score=score,
            src_id=src_id,
            tgt_item_label=tgt_item_label,
            grouped_targets_by_src=grouped_targets_by_src,
        )

    _relationship_map_render_groups(grouped_targets_by_src, dot, FONT_SIZE)

    display_png = None
    with st.spinner("그래프 생성 중..."):
        try:
            st.markdown("---")
            st.caption(_RELATIONSHIP_MAP_CAPTION)
            display_png = dot.pipe(format="png")
            st.image(display_png, use_container_width=True)
        except Exception as e:
            st.error(f"시각화 엔진 오류: {e}")

    if display_png is None:
        return

    try:
        dot.attr(dpi=download_dpi)
        png_bytes = dot.pipe(format="png")
        st.download_button(
            label="이미지 다운로드",
            data=png_bytes,
            file_name="physical_relationship_map.png",
            mime="image/png",
            key="physical_relationship_map_download",
        )
    except Exception as e:
        st.warning(f"이미지 저장/다운로드 생성 실패: {e}")




def calculate_column_similarity(df, model_name='all-MiniLM-L6-v2'):
    """
    FileName과 ColumnName의 조합을 서로 비교하여 유사도 점수를 계산합니다.
    PyTorch DLL 오류 시에는 difflib 문자열 유사도로 대체합니다.
    """

    # df 에서 LenMax < 2 하는 제외, DetailDataType in (DATECHAR, TIME, TIMESTAMP) 제외
    df = df[df["LenMax"] >= 2]
    df = df[~df["DetailDataType"].isin(["DATECHAR", "TIME", "TIMESTAMP"])]

    st.markdown("### 🎯 Column Similarity")
    # st.dataframe(df)

    pairs = df[['FileName', 'ColumnName']].drop_duplicates().values.tolist()
    column_names = [p[1] for p in pairs]

    SentenceTransformer, st_util, st_err = _get_sentence_transformers()
    use_embedding = SentenceTransformer is not None and st_util is not None
    embeddings = None

    if use_embedding:
        model = SentenceTransformer(model_name)
        embeddings = model.encode(column_names, convert_to_tensor=True)
#     else:
#         st.info(
#             "문장 **임베딩**은 PyTorch를 불러오지 못해 사용하지 않습니다. "
#             "대신 **문자열 유사도**(difflib)로 `ColumnName`끼리만 비교합니다."
#         )
#         with st.expander("PyTorch / c10.dll (WinError 1114) 해결 참고"):
#             st.code(st_err or "(오류 메시지 없음)", language="text")
#             st.markdown(
#                 """
# 1. [Visual C++ 2015–2022 **x64** 재배포 패키지](https://aka.ms/vs/17/release/vc_redist.x64.exe) 설치 후 **재부팅**
# 2. 백신/보안 SW가 `venv\\Lib\\site-packages\\torch` 를 차단하는지 확인
# 3. 터미널에서 `pip uninstall -y torch torchvision torchaudio` 후  
#    `pip install torch --index-url https://download.pytorch.org/whl/cpu`
# """
#             )

    results = []
    for i in range(len(pairs)):
        for j in range(len(pairs)):
            if use_embedding:
                sim_score = float(st_util.cos_sim(embeddings[i], embeddings[j]).item())
            else:
                sim_score = _difflib_name_similarity(column_names[i], column_names[j])
            results.append({
                'FileName': pairs[i][0],
                'ColumnName': pairs[i][1],
                'MasterFile': pairs[j][0],
                'MasterColumn': pairs[j][1],
                'Similarity': round(sim_score, 4),
            })


    result_df = pd.DataFrame(results)
    result_df = result_df[result_df["Similarity"] > 0.7]

    # CodeMapping(df)에 없는 컬럼이 있으면 df[튜플]에서 KeyError → 실제 존재 컬럼만 사용
    _key = ["FileName", "ColumnName"]
    _extra_src = [
        "PK", "Format", "FormatCnt", "Attribute", "DetailDataType",
        "Null(%)", "Unique(%)", 
    ]
    _cols_left = [c for c in _key + _extra_src if c in df.columns]
    tmp_df = df[_cols_left].drop_duplicates(subset=_key, keep="first")
    result_df = pd.merge(result_df, tmp_df, on=_key, how="left")

    # df에는 FileName/ColumnName만 있음. 비교 쌍의 오른쪽(MasterFile/MasterColumn) 메타는 동일 키로 rename 후 merge
    _extra_ref = [
        "PK", "Format", "FormatCnt", "Attribute", "DetailDataType", 
        "Null(%)", "Unique(%)"]
    _cols_ref = [c for c in _key + _extra_ref if c in df.columns]
    _r_rename = {
        "FileName": "MasterFile",
        "ColumnName": "MasterColumn",
        "PK": "R_PK",
        "Format": "R_Format",
        "FormatCnt": "R_FormatCnt",
        "Attribute": "R_Attribute",
        "DetailDataType": "R_DetailDataType",
        "Null(%)": "R_Null(%)",
        "Unique(%)": "R_Unique(%)",
    }
    tmp2_df = (
        df[_cols_ref]
        .drop_duplicates(subset=_key, keep="first")
        .rename(columns={c: _r_rename[c] for c in _cols_ref if c in _r_rename})
    )
    result_df = pd.merge(result_df, tmp2_df, on=["MasterFile", "MasterColumn"], how="left")
    # FileName = MasterFile & ColumnName = MasterColumn 인 경우 result_df['same_column'] = True 아니면 False로 설정
    result_df["same_column"] = (result_df["FileName"] == result_df["MasterFile"]) & (
        result_df["ColumnName"] == result_df["MasterColumn"]
    )
    mode = "임베딩(cos_sim)" if use_embedding else "문자열(SequenceMatcher)"
    st.caption(f"유사도 계산 방식: **{mode}**")

    # csv 로 저장
    result_df.to_csv("DS_Output/Column_Similarity.csv", index=False)
    # st.dataframe(result_df)
    return result_df

#  신규 추가 
# 1. 전체 Summary Metric 함수
def get_overall_summary(df):
    summary = {
        "총 비교 건수": len(df),
        "평균 문자열 유사도": f"{df['Similarity'].mean():.2%}",
        "평균 데이터 일치율(MatchRate)": f"{df['MatchRate(%)'].mean():.2f}%",
        "물리명 동일 컬럼 수": len(df[df['same_column'] == True]),
        "고신뢰 관계 건수 (Match > 80%)": len(df[df['MatchRate(%)'] >= 80])
    }

    metric_colors = {
        "총 비교 건수":      BLACK,       # 검정색
        "평균 문자열 유사도":      BLUE,       # 파랑색
        "평균 데이터 일치율(MatchRate)":          GREEN,       # 초록색
        "물리명 동일 컬럼 수":          AMBER,       # 앰버
        "고신뢰 관계 건수 (Match > 80%)":         GRAY,       # 회색
    }

    display_kpi_metrics(summary, metric_colors, '연관 관계 요약 지표')
    return summary

# 2. File 기준의 집계 (파일 간의 연관성 중심)
def get_file_level_agg(df):
    file_agg = df.groupby('FileName').agg({
        'R_FileName': 'nunique',
        'ColumnName': 'count',
        'MatchRate(%)': 'mean',
        'Similarity': 'mean'
    }).rename(columns={
        'R_FileName': '연관_파일_수',
        'ColumnName': '비교_컬럼_수',
        'MatchRate(%)': '평균_일치율',
        'Similarity': '평균_유사도'
    }).reset_index()
    return file_agg

# 3. File + Column 기준 집계 (특정 파일의 컬럼이 어디와 매칭되는지)
def get_file_column_agg(df):
    fc_agg = df.groupby(['FileName', 'ColumnName']).agg({
        'MatchRate(%)': ['mean', 'max', 'count'],
        'same_column': 'sum'
    })
    fc_agg.columns = ['평균_일치율', '최대_일치율', '매칭_횟수', '이름동일_횟수']
    return fc_agg.reset_index()

# 4. Column 명 기준 집계 (동일 이름 컬럼들의 실제 전역적 일치율)
def get_column_identity_agg(df):
    col_agg = df.groupby('ColumnName').agg({
        'FileName': 'nunique',
        'MatchRate(%)': ['mean', 'std'],
        'Similarity': 'mean'
    })
    col_agg.columns = ['발견된_파일_수', '평균_일치율', '일치율_표준편차', '평균_유사도']
    return col_agg.reset_index().sort_values(by='평균_일치율', ascending=False)

# 컬럼별 Similarity=1 건수 집계, 컬럼별 Similarity=1 & MatchRate(%)>=80 건수 집계
# 컬럼별 Similarity=1 & MatchRate(%)에 값이 없는 건수
def get_column_agg_old(df):
    sub = df.loc[df["Similarity"] == 1].copy()
    sub["_mr"] = pd.to_numeric(sub["MatchRate(%)"], errors="coerce")
    sub["_mr_eq100"] = (sub["_mr"] == 100).astype(np.int64)
    sub["_mr_ge90"] = (sub["_mr"] >= 90).astype(np.int64) - sub["_mr_eq100"]
    sub["_mr_ge80"] = (sub["_mr"] >= 80).astype(np.int64) - sub["_mr_eq100"] - sub["_mr_ge90"]
    sub["_mr_missing"] = sub["_mr"].isna().astype(np.int64)
    # MatchRate(%)가 0이거나(숫자 0) 값이 없는 경우(비어 있음·비숫자 → NaN)
    sub["_mr_zero"] = (sub["_mr"].isna() | (sub["_mr"] == 0)).astype(np.int64)
    col_agg = sub.groupby("ColumnName", as_index=False).agg(
        동일명컬럼 =("FileName", "count"),
        파일_수 =("FileName", "nunique"),
        일치율100  =("_mr_eq100", "sum"),
        일치율90이상 =("_mr_ge90", "sum"),
        일치율80이상=("_mr_ge80", "sum"),
        일치율0=("_mr_zero", "sum"),
        일치율_결측=("_mr_missing", "sum"),
    )  
    return col_agg
    # return col_agg.sort_values(by="동일컬럼발생_건수", ascending=False)

def _similarity_is_exact(sim: pd.Series) -> pd.Series:
    s = pd.to_numeric(sim, errors="coerce")
    return np.isclose(s, 1.0, rtol=0, atol=1e-6)


def _similarity_is_similar_band(sim: pd.Series) -> pd.Series:
    s = pd.to_numeric(sim, errors="coerce")
    return (s > 0.8) & ~_similarity_is_exact(s)


def _dedupe_physical_similarity_rows(sub: pd.DataFrame) -> pd.DataFrame:
    """요약·맵 공통: FileName+ColumnName+R_FileName 단위 최대 Similarity 1건."""
    sub = sub.copy()
    sub["Similarity"] = pd.to_numeric(sub["Similarity"], errors="coerce")
    sub["_mr"] = pd.to_numeric(sub.get("MatchRate(%)"), errors="coerce")
    sub = sub.sort_values(["Similarity", "_mr"], ascending=[False, False])
    return sub.drop_duplicates(
        subset=["FileName", "ColumnName", "R_FileName"], keep="first"
    )


def prepare_physical_map_edges(
    similarity_df: pd.DataFrame, file_name: str
) -> pd.DataFrame:
    """physical_relationship_map — get_column_agg 와 동일 규칙의 파일별 edge 목록."""
    cols = ["FileName", "ColumnName", "R_FileName", "R_ColumnName", "Similarity", "MatchRate(%)"]
    use_cols = [c for c in cols if c in similarity_df.columns]
    f = similarity_df.loc[similarity_df["FileName"] == file_name, use_cols].copy()
    f = f.dropna(subset=["ColumnName", "R_FileName", "R_ColumnName", "Similarity"])
    if f.empty:
        return f
    mask = _similarity_is_exact(f["Similarity"]) | _similarity_is_similar_band(f["Similarity"])
    return _dedupe_physical_similarity_rows(f.loc[mask])


def get_column_agg(df):
    def _agg_by_similarity(sub_df: pd.DataFrame, prefix: str) -> pd.DataFrame:
        if sub_df.empty:
            return pd.DataFrame(columns=["FileName", "ColumnName"])

        sub_unique = _dedupe_physical_similarity_rows(sub_df)

        sub_unique["_mr_eq100"] = (sub_unique["_mr"] == 100).astype(np.int64)
        sub_unique["_mr_90_99"] = (
            (sub_unique["_mr"] >= 90) & (sub_unique["_mr"] < 100)
        ).astype(np.int64)
        sub_unique["_mr_80_89"] = (
            (sub_unique["_mr"] >= 80) & (sub_unique["_mr"] < 90)
        ).astype(np.int64)
        sub_unique["_mr_missing"] = sub_unique["_mr"].isna().astype(np.int64)

        agg = sub_unique.groupby(["FileName", "ColumnName"], as_index=False).agg(
            **{
                f"{prefix}컬럼수": ("R_FileName", "count"),
                f"{prefix}100%": ("_mr_eq100", "sum"),
                f"{prefix}> 90%": ("_mr_90_99", "sum"),
                f"{prefix}> 80%": ("_mr_80_89", "sum"),
                f"{prefix}없음": ("_mr_missing", "sum"),
            }
        )
        return agg

    sim = pd.to_numeric(df["Similarity"], errors="coerce")
    eq1 = _agg_by_similarity(df.loc[_similarity_is_exact(sim)], prefix="(일치) ")
    ne1 = _agg_by_similarity(df.loc[_similarity_is_similar_band(sim)], prefix="(유사) ")

    col_agg = pd.merge(eq1, ne1, on=["FileName", "ColumnName"], how="outer").fillna(0)

    # 집계 컬럼만 정수로 정리 (FileName, ColumnName 제외)
    for c in col_agg.columns:
        if c not in ("FileName", "ColumnName"):
            col_agg[c] = pd.to_numeric(col_agg[c], errors="coerce").fillna(0).astype(np.int64)

    return col_agg


def aggregate_by_column_name(df: pd.DataFrame) -> pd.DataFrame:
    """
    ColumnName 기준 집계.
    - 파일수: 해당 컬럼명이 존재하는 FileName 수(nunique)
    - (일치) 컬럼수 등: 파일별 지표>0 인 FileName 수 (sum 아님 → 파일수와 동일 규칙)
    """
    if df is None or df.empty or "ColumnName" not in df.columns:
        return df

    _metric_cols = [c for c in df.columns if c not in ("FileName", "ColumnName")]
    work = df.copy()
    for c in _metric_cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0)

    records: list[dict] = []
    for col_name, g in work.groupby("ColumnName", dropna=False):
        row: dict = {"ColumnName": col_name}
        if "FileName" in g.columns:
            row["파일수"] = int(g["FileName"].nunique())
            per_file = g.groupby("FileName", dropna=False)
            for mc in _metric_cols:
                # sum(대상 R_FileName 건수)이 아니라, 지표>0 인 FileName 개수
                row[mc] = int((per_file[mc].max() > 0).sum())
        else:
            row["파일수"] = 0
            for mc in _metric_cols:
                row[mc] = int((g[mc] > 0).any())
        records.append(row)

    return pd.DataFrame(records)


def display_column_agg(column_agg: pd.DataFrame) -> pd.DataFrame:
    """FileName 없이 ColumnName 기준 집계 후 표시."""
    if column_agg is None or column_agg.empty:
        st.info("표시할 집계 데이터가 없습니다.")
        return column_agg

    if "ColumnName" not in column_agg.columns:
        st.warning("ColumnName 컬럼이 없습니다.")
        return column_agg

    view = aggregate_by_column_name(column_agg)
    view = view[
        (view.get("(일치) 컬럼수", 0) > 0) | (view.get("(유사) 컬럼수", 0) > 0)
    ]
    sort_col = "(일치) 컬럼수" if "(일치) 컬럼수" in view.columns else "ColumnName"
    view = view.sort_values(sort_col, ascending=False, na_position="last")

    def _prog_max(col: str) -> float:
        if col not in view.columns or view.empty:
            return 1.0
        m = view[col].max()
        return max(float(m), 1.0) if pd.notna(m) else 1.0

    _display_cols = ["(일치) 컬럼수", "(일치) 100%", "(유사) 컬럼수", "(유사) 100%"]
    _dm = {c: _prog_max(c) for c in ["파일수", *_display_cols] if c in view.columns or c == "파일수"}

    column_config = {
        "ColumnName": st.column_config.TextColumn(label="ColumnName"),
    }
    if "파일수" in view.columns:
        column_config["파일수"] = st.column_config.ProgressColumn(
            label="파일수",
            help="해당 ColumnName이 존재하는 FileName 개수",
            min_value=0,
            max_value=_dm.get("파일수", 1),
            format="%d",
            color="blue",
        )
    _prog_style = {
        "(일치) 컬럼수": (
            "Similarity==1 기준 해당 컬럼명이 있는 FileName 수(파일수와 동일 집계)",
            "green",
        ),
        "(일치) 100%": (
            "Similarity==1 기준 값 일치율 100%가 있는 FileName 수",
            "green",
        ),
        "(유사) 컬럼수": (
            "0.8<Similarity<1 기준 해당 컬럼명이 있는 FileName 수",
            SKYBLUE,
        ),
        "(유사) 100%": (
            "0.8<Similarity<1 기준 값 일치율 100%가 있는 FileName 수",
            SKYBLUE,
        ),
    }
    for col, (help_txt, color) in _prog_style.items():
        if col in view.columns:
            column_config[col] = st.column_config.ProgressColumn(
                label=col,
                help=help_txt,
                min_value=0,
                max_value=_dm.get(col, 1),
                format="%d",
                color=color,
            )

    st.dataframe(
        view,
        hide_index=True,
        height=500,
        width="stretch",
        column_config=column_config,
    )
    return view

def physical_relationship_analysis_summary(df: pd.DataFrame):
    # FileName, 파일별 컬럼수, (일치) 컬럼수" > 0 인 컬럼수, "(일치) 100%" > 0 인 컬럼수, "(유사) 컬럼수" > 0 인 컬럼수, "(유사) 100%" > 0 인 컬럼수
    if df is None or df.empty:
        st.info("표시할 데이터가 없습니다.")
        return None

    required_base_cols = {"ColumnName"}
    if not required_base_cols.issubset(set(df.columns)):
        st.warning("요약 집계를 위해 필요한 컬럼(ColumnName)이 없습니다.")
        return None
    if "FileName" not in df.columns:
        st.warning("파일 단위 요약을 위해 FileName 컬럼이 필요합니다.")
        return None

    def _to_num(s: pd.Series) -> pd.Series:
        return pd.to_numeric(s, errors="coerce").fillna(0)

    df2 = df.copy()
    for c in ["(일치) 컬럼수", "(일치) 100%", "(유사) 컬럼수", "(유사) 100%"]:
        if c in df2.columns:
            df2[c] = _to_num(df2[c])

    summary = (
        df2.groupby("FileName", dropna=False)
        .agg(
            **{
                "컬럼수": ("ColumnName", "nunique"),
                "명칭일치 컬럼": ("(일치) 컬럼수", lambda s: int((s > 0).sum()) if s is not None else 0),
                "명칭일치 & 값일치": ("(일치) 100%", lambda s: int((s > 0).sum()) if s is not None else 0),
                "명칭유사 컬럼": ("(유사) 컬럼수", lambda s: int((s > 0).sum()) if s is not None else 0),
                "명칭유사 & 값일치": ("(유사) 100%", lambda s: int((s > 0).sum()) if s is not None else 0),
            }
        )
        .reset_index()
    )

    for c in [
        "명칭일치 컬럼",
        "명칭일치 & 값일치",
        "명칭유사 컬럼",
        "명칭유사 & 값일치",
    ]:
        if c not in summary.columns:
            summary[c] = 0

    # 컬럼수가 1개인 파일은 제외 (컬럼수 > 1 인 행만 사용)
    summary = summary[summary["컬럼수"] > 1].reset_index(drop=True)
    if summary.empty:
        st.info("컬럼수가 2개 이상인 파일이 없습니다.")
        return None

    summary.insert(0, "select", False)

    _prog_cols = [
        "컬럼수",
        "명칭일치 컬럼",
        "명칭일치 & 값일치",
        "명칭유사 컬럼",
        "명칭유사 & 값일치",
    ]
    for _c in _prog_cols:
        if _c in summary.columns:
            summary[_c] = pd.to_numeric(summary[_c], errors="coerce").fillna(0)

    def _physical_summary_prog_max(col: str) -> float:
        if col not in summary.columns:
            return 1.0
        m = summary[col].max()
        return max(float(m), 1.0) if pd.notna(m) else 1.0

    _pm = {c: _physical_summary_prog_max(c) for c in _prog_cols}

    st.divider()
    st.subheader("📌 Physical Relationship 요약(파일 단위)")
    edited = st.data_editor(
        summary,
        hide_index=True,
        width='stretch',
        height=min(500, 40 + 35 * max(len(summary), 1)),
        column_config={
            "select": st.column_config.CheckboxColumn(label="선택", help="파일 선택"),
            "FileName": st.column_config.TextColumn(label="FileName", disabled=True),
            "컬럼수": st.column_config.ProgressColumn(
                label="컬럼수", min_value=0, max_value=_pm["컬럼수"], format="%d", color ='blue',
            ),
            "명칭일치 컬럼": st.column_config.ProgressColumn(
                label="명칭일치", min_value=0, max_value=_pm["명칭일치 컬럼"], format="%d", color="green",
            ),
            "명칭일치 & 값일치": st.column_config.ProgressColumn(
                label="명칭일치 & 값일치", min_value=0, max_value=_pm["명칭일치 & 값일치"], format="%d", color="green",
            ),
            "명칭유사 컬럼": st.column_config.ProgressColumn(
                label="명칭유사", min_value=0, max_value=_pm["명칭유사 컬럼"], format="%d", color=SKYBLUE,
            ),
            "명칭유사 & 값일치": st.column_config.ProgressColumn(
                label="명칭유사 & 값일치", min_value=0, max_value=_pm["명칭유사 & 값일치"], format="%d", color=SKYBLUE,
            ),
        },
        key="physical_relationship_summary_editor",
    )

    try:
        selected = edited.loc[edited["select"] == True, "FileName"].dropna().astype(str).tolist()  # noqa: E712
    except Exception:
        selected = []

    st.session_state["physical_relationship_selected_files"] = selected
    return selected

def physical_relationship_column_analysis_summary(detail_df: pd.DataFrame):
    st.divider()
    st.subheader("📊 선택 파일 내 ColumnName별 명칭 일치/유사 및 값일치율")

    if detail_df is None or detail_df.empty:
        st.info("표시할 데이터가 없습니다.")
        return None

    if "ColumnName" not in detail_df.columns:
        st.warning("ColumnName 컬럼이 없습니다.")
        return None

    _metric_cols = [
        "(일치) 컬럼수",
        "(일치) 100%",
        "(일치) 없음",
        "(유사) 컬럼수",
        "(유사) 100%",
    ]
    summary_df = aggregate_by_column_name(detail_df)
    if summary_df.empty:
        st.info("집계할 지표 컬럼이 없습니다.")
        return None
    sort_col = "(일치) 컬럼수" if "(일치) 컬럼수" in summary_df.columns else "ColumnName"
    summary_df = summary_df.sort_values(sort_col, ascending=False, na_position="last")

    def _detail_prog_max(col: str) -> float:
        if col not in summary_df.columns:
            return 1.0
        m = summary_df[col].max()
        return max(float(m), 1.0) if pd.notna(m) else 1.0

    _prog_keys = ["파일수", *_metric_cols] if "파일수" in summary_df.columns else _metric_cols
    _dm = {c: _detail_prog_max(c) for c in _prog_keys}

    column_config = {
        "ColumnName": st.column_config.TextColumn(label="ColumnName"),
    }
    if "파일수" in summary_df.columns:
        column_config["파일수"] = st.column_config.ProgressColumn(
            label="파일수",
            help="선택된 파일 중 해당 ColumnName이 존재하는 FileName 개수",
            min_value=0,
            max_value=_dm["파일수"],
            format="%d",
            color="blue",
        )
    _prog_style = {
        "(일치) 컬럼수": (
            "Similarity==1 기준 해당 컬럼명이 있는 FileName 수(파일수와 동일 집계)",
            "green",
        ),
        "(일치) 100%": ("Similarity==1 기준 값 일치율 100%가 있는 FileName 수", "green"),
        "(일치) 없음": ("Similarity==1 기준 일치율 없음이 있는 FileName 수", "gray"),
        "(유사) 컬럼수": ("0.8<Similarity<1 기준 해당 컬럼명이 있는 FileName 수", SKYBLUE),
        "(유사) 100%": ("0.8<Similarity<1 기준 값 일치율 100%가 있는 FileName 수", SKYBLUE),
    }
    for col, (help_txt, color) in _prog_style.items():
        if col in summary_df.columns:
            column_config[col] = st.column_config.ProgressColumn(
                label=col,
                help=help_txt,
                min_value=0,
                max_value=_dm[col],
                format="%d",
                color=color,
            )

    st.dataframe(
        summary_df,
        hide_index=True,
        width="stretch",
        height=500,
        column_config=column_config,
    )

    return None
# -------------------------------------------------------------------
# FILE LOADER & MAIN APP (기존 클래스 구조 유지)
# -------------------------------------------------------------------
@dataclass
class FileConfig:
    codemapping: str
    codemapping_6th: str
    column_similarity: str

class FileLoader:
    def __init__(self, yaml_config: Dict[str, Any]):
        self.yaml_config = yaml_config
        self.root_path = str(PROJECT_ROOT.resolve())
        self.files_config = self._setup_files_config()
    
    def _setup_files_config(self) -> FileConfig:
        def _full_path(path_str):
            p = Path(path_str)
            if not p.is_absolute():
                p = Path(self.root_path) / p
            return str(p.resolve())
        return FileConfig(
            codemapping=_full_path("DS_Output/CodeMapping.csv"),
            codemapping_6th=_full_path("DS_Output/CodeMapping_6th_int_mapping.csv"),
            column_similarity=_full_path("DS_Output/Column_Similarity.csv"),
        )
    
    def _resolve_existing_file(self, path: Path) -> Optional[Path]:
        if path.exists():
            return path
        if path.suffix == "":
            candidates = [path.with_suffix(".csv"), path.with_suffix(".CSV")]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
        return None

    def load_file(self, file_path: str, file_name: str) -> Optional[pd.DataFrame]:
        path = Path(file_path)
        resolved_path = self._resolve_existing_file(path)
        if resolved_path is None:
            if path.suffix == "":
                st.error(f"❌ {file_name} 파일을 찾을 수 없습니다. ({path} / {path.with_suffix('.csv')})")
            else:
                st.error(f"❌ {file_name} 파일을 찾을 수 없습니다. ({path})")
            return None
        try:
            for enc in ("utf-8-sig", "utf-8", "cp949"):
                try: return pd.read_csv(resolved_path, encoding=enc)
                except: continue
            return None
        except Exception as e:
            st.error(f"{file_name} 로드 실패: {str(e)}")
            return None

class DataLogicalRelationshipApp:
    def __init__(self):
        self.yaml_config = None
        self.loader = None
    
    def initialize(self) -> bool:
        try:
            self.yaml_config = load_yaml_datasense()
            self.loader = FileLoader(self.yaml_config)
            return True
        except Exception as e:
            st.error(f"초기화 오류: {e}")
            return False
    
    def physical_relationship_analysis(self):

        codemapping_df = self.loader.load_file(self.loader.files_config.codemapping, "CodeMapping")
        codemapping_6th_df = self.loader.load_file(self.loader.files_config.codemapping_6th, "CodeMapping_6th")
        column_similarity_df = self.loader.load_file(self.loader.files_config.column_similarity, "Column_Similarity")

        # 컬럼명별 유사도 계산 
        cols = ["FileName", "ColumnName", "MasterFile", "MasterColumn", "MatchRate(%)"]
        if column_similarity_df is not None:
            similarity_df = column_similarity_df
        else:
            st.warning(" 컬럼명별 유사도 계산을 진행합니다.")
            similarity_df = calculate_column_similarity(codemapping_df)
        tmp_df = codemapping_6th_df[cols]
        similarity_df = pd.merge(similarity_df, tmp_df, on=["FileName", "ColumnName", "MasterFile", "MasterColumn"], how="left")
        similarity_df = similarity_df.rename(columns={
            "MasterFile": "R_FileName",
            "MasterColumn": "R_ColumnName",
        })

        st.divider()
        st.subheader("📊 컬럼명별(명칭 일치/유사) 및 값 일치율별 갯수")
        column_agg = get_column_agg(similarity_df)
        column_agg = column_agg.sort_values(by="(일치) 컬럼수", ascending=False)

        modifiedcolumn_agg = display_column_agg(column_agg)

        if "ColumnName" not in modifiedcolumn_agg.columns:
            st.error("컬럼 집계 결과에 ColumnName 이 없습니다.")
            return
        df = pd.merge(codemapping_df, modifiedcolumn_agg, on="ColumnName", how="left")
        
        # cols = ["FileName", "ColumnName", "(일치) 컬럼수", 	"(일치) 100%", "(일치) > 90%", 	"(일치) > 80%", "(일치) 없음", "(유사) 컬럼수", "(유사) 100%", "(유사) > 90%", "(유사) > 80%", "(유사) 없음"]
        cols = ["FileName", "ColumnName", "(일치) 컬럼수", 	"(일치) 100%", "(일치) 없음", "(유사) 컬럼수", "(유사) 100%"]
        df = df[cols]

        selected_files = physical_relationship_analysis_summary(df)
        if selected_files is not None:
            selected_df = df[df["FileName"].isin(selected_files)].copy()
            physical_relationship_column_analysis_summary(selected_df)
            phys_map_df = similarity_df[
                similarity_df["FileName"].isin(selected_files)
            ].dropna(subset=["R_FileName", "R_ColumnName"])
            physical_relationship_map(phys_map_df)
            

    def logical_relationship_analysis(self):

        codemapping_df = self.loader.load_file(self.loader.files_config.codemapping, "CodeMapping")
        codemapping_6th_df = self.loader.load_file(self.loader.files_config.codemapping_6th, "CodeMapping_6th")

        # logical_relationship 을 생성하기 위한 데이터프레임 생성 및 요약 
        merge_df = merge_codemapping(codemapping_df, codemapping_6th_df)

        mv_df = mapping_verify(merge_df)
        mv_df2 = mapping_verify_2nd(mv_df)
        mv_df2 = mv_df2[mv_df2["mapping_result"] == True]

        st.markdown("##### 📊 논리적 연관 관계 요약")
        logical_relationship_summary(mv_df2)

        # 파일 정보 표시 및 선택 
        selected_file_names = display_file_info(mv_df2)
        if selected_file_names is not None:
            selected_df = mv_df2[mv_df2['FileName'].isin(selected_file_names)]
            st.markdown("##### 📊 Column Logical Relationship")
            logical_relationship_summary(selected_df)

            display_selected_file_info(selected_df)

            logical_relationship_map(selected_df)  # 논리적 연관 관계 맵 생성

        return None

# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------
def main():
    try:
        app = DataLogicalRelationshipApp()
        if app.initialize(): 
            st.title(f"📊 {APP_NAME}")
            st.markdown(APP_DESC)
            tab1, tab2 = st.tabs(["Physical Relationship Analysis", "Logical Relationship Analysis"])
            with tab1:
                app.physical_relationship_analysis()
            with tab2:  
                app.logical_relationship_analysis()
    except Exception as e:
        st.exception(e)

if __name__ == "__main__":
    main()
