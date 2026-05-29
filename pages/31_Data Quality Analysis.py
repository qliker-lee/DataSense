# -*- coding: utf-8 -*-
"""
2026.02.09  Qliker 
📊 Data Quality Analysis (Visual Enhanced)
"""
import sys
from pathlib import Path
import streamlit as st
import subprocess
import os
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, Optional
import yaml
import plotly.express as px
import plotly.graph_objects as go

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
from util.dq_datatype import Data_Type_Analysis
from util.DS_31_Quality_Rule import DataQualityAnalysisClass, DataQualityReportClass
from util.Display import display_kpi_metrics
# -------------------------------------------------------------------
# 폰트 크기 조정 및 색상 변경 (신규추가)
# # -------------------------------------------------------------------
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
APP_NAME = "Data Quality Analysis (데이터 품질 분석)"
APP_DESC = "#### 모든 파일의 각 컬럼들에 대한 프로파일링을 수행하여 품질분석을 위한 통계를 생성합니다."
OUTPUT_DIR = PROJECT_ROOT / "DS_Output"

set_page_config(APP_NAME)

dataqualityanalysis = DataQualityAnalysisClass()
dataqualityreport = DataQualityReportClass()

# -------------------------------------------------------------------
# [NEW] 시각화 및 스타일링 유틸리티
# -------------------------------------------------------------------
   
def display_visual_dashboard(df: pd.DataFrame):
    """['S (최상)', 'A (양호)', 'B (점검)', 'C (위험)', 'D (심각)'] 시계 방향 정렬"""
    st.divider()
    st.subheader("📈 Quality Insight Dashboard")
    
    # 데이터 전처리
    df['Quality Grade'] = df['Quality Grade'].astype(str).str.strip()
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("##### Overall Quality Grade Distribution by Columns.")
        # 정해진 등급 순서
        grade_order = ['S (최상)', 'A (양호)', 'B (점검)', 'C (위험)', 'D (심각)']
        
        # 데이터 집계 및 순서 재배치
        counts = df['Quality Grade'].value_counts().reindex(grade_order, fill_value=0).reset_index()
        counts.columns = ['Grade', 'Count']
        
        color_map = {
            'S (최상)': '#636EFA', 'A (양호)': '#00CC96', 
            'B (점검)': '#FFD700', 'C (위험)': '#FFA500', 'D (심각)': '#FF4B4B'
        }
        
        if counts['Count'].sum() > 0:
            fig_pie = px.pie(
                counts, 
                values='Count', 
                names='Grade', 
                color='Grade', 
                color_discrete_map=color_map,
                hole=0.5,
                category_orders={"Grade": grade_order} # 범례 순서 고정
            )
            
            # 핵심 설정: 12시 시작(rotation=0), 시계 방향(direction='clockwise')
            fig_pie.update_traces(
                textinfo='percent+label',
                rotation=0,             # 12시 방향 시작
                direction='clockwise',  # 시계 방향(우측 방향)으로 배치
                sort=False              # 자동 크기순 정렬 끄기 (우리가 정한 등급순 유지)
            )
            
            fig_pie.update_layout(
                showlegend=True, 
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
                margin=dict(t=20, b=50, l=10, r=10), 
                height=350
            )
            st.plotly_chart(fig_pie, width ="stretch", height=350)
        else:
            st.warning("표시할 등급 데이터가 없습니다.")


    with col2:
        # 2. 이슈 유형별 통계 (Horizontal Bar Chart)
        st.markdown("##### Number of issues per column and category")
        issue_metrics = {
            'Length Issue': df['Len Q Check'].sum(),
            'Value/Format': df['Format Q Check'].sum(),
            'Character': df['Char Q Check'].sum()
        }
        issue_df = pd.DataFrame(list(issue_metrics.items()), columns=['Category', 'Count'])
        
        fig_bar = px.bar(issue_df, y='Category', x='Count', orientation='h',
                         text='Count', color='Category',
                         color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_bar.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None, 
                              margin=dict(t=0, b=0, l=0, r=0), height=300)
        st.plotly_chart(fig_bar, width ="stretch", height=300)

def apply_quality_styling(df: pd.DataFrame):
    """품질 점수에 따른 데이터프레임 스타일링"""
    def score_color(val):
        if val <= 1: return 'color: #FF4B4B; font-weight: bold;'
        elif val <= 2: return 'color: #FFA500; font-weight: bold;'
        return ''
    
    # 데이터 에디터는 스타일링 적용이 안되므로, '표시용' 데이터프레임에 적용 권장
    return df.style.applymap(score_color, subset=['Quality Score'])

# -------------------------------------------------------------------
# 기존 로직 (수정 및 유지)
# -------------------------------------------------------------------
def quality_metrics(df: pd.DataFrame):
    """기존 Metric 정보 유지"""
    total_files = df['FileName'].nunique()
    total_columns = df[['FileName', 'ColumnName']].drop_duplicates().shape[0]

    hascode_files = df[df['CodeFlag'] == True]['FileName'].nunique()
    quality_1 = df[df['Quality Score'] == 1]['FileName'].nunique()
    quality_2 = df[df['Quality Score'] == 2]['FileName'].nunique()
    quality_3 = df[df['Quality Score'] == 3]['FileName'].nunique()
    len_check_files = df[df['Len Q Check'] == True]['FileName'].nunique()
    format_check_files = df[df['Format Q Check'] == True]['FileName'].nunique()
    character_check_files = df[df['Char Q Check'] == True]['FileName'].nunique()

    st.subheader("📁 File Quality Summary")
    m1, m2, m3, m4, m5, m6, m7, m8 = st.columns(8)
    m1.metric("Total Files", f"{total_files:,}")
    m2.metric("Has Code", f"{hascode_files:,}")
    m3.metric("심각(🚨)", f"{quality_1:,}")
    m4.metric("위험(⚠️)", f"{quality_2:,}")
    m5.metric("점검(☢️)", f"{quality_3:,}")
    m6.metric("Length Issue", f"{len_check_files:,}")
    m7.metric("Format Issue", f"{format_check_files:,}")
    m8.metric("Character Issue", f"{character_check_files:,}")

    # summary = {
    #     "전체 파일수": f"{total_files:,}",
    #     "전체 컬럼수": f"{total_columns:,}",
    #     "Has Code": f"{hascode_files:,}",
    #     "심각(🚨)": f"{quality_1:,}",
    #     "위험(⚠️)": f"{quality_2:,}",
    #     "점검(☢️)": f"{quality_3:,}",
    #     "Length Issue": f"{len_check_files:,}",
    #     "Format Issue": f"{format_check_files:,}",
    #     "Character Issue": f"{character_check_files:,}",
    # }

    # metric_colors = {
    #     "전체 파일수": "#1f77b4",
    #     "전체 컬럼수": "#2ca02c",
    #     "Has Code": "#ff7f0e",
    #     "심각(🚨)": "#1a9850",
    #     "위험(⚠️)": "#d62728",
    #     "점검(☢️)": "#9467bd",
    #     "Length Issue": "#e377c2",
    #     "Format Issue": "#e377c2",
    #     "Character Issue": "#e377c2",
    # }

    # display_kpi_metrics(summary, metric_colors, "데이터 품질 요약")

def display_file_info(df: pd.DataFrame):
    """강화된 파일/컬럼 상세 분석 UI"""
    if df is None:
        st.warning(f"⚠️ Data Profile 분석 결과 파일을 찾을 수 없습니다.")
        return

    # 대시보드 시각화 추가
    display_visual_dashboard(df)
    st.divider()

    st.markdown("### 📁 File-level Data Quality Summary")

    # 1. 파일별 요약 데이터 생성
    summary_df = df.groupby(['FileName']).agg({
        'ColumnName': 'count',
        'CodeFlag': 'sum',
    }).reset_index()
    summary_df.columns = ['FileName', 'Column #', 'Code #']

    # Quality Score 피벗 (1~5점 점수별 컬럼 수)
    score_df = df.groupby(['FileName', 'Quality Score']).agg({'ColumnName': 'count'}).reset_index()
    score_df = score_df.pivot(index='FileName', columns='Quality Score', values='ColumnName').fillna(0).astype(int)
    
    # 점수 컬럼 매핑 (누락된 점수 대비 reindex 추가)
    expected_scores = {1: '심각(🚨)', 2: '위험(⚠️)', 3: '점검(☢️)', 4: '양호(🤗)', 5: '최상(✨)'}
    score_df = score_df.reindex(columns=[1,2,3,4,5], fill_value=0)
    score_df.columns = [expected_scores[c] for c in score_df.columns]
    
    check_df = df.groupby(['FileName']).agg({
        'Len Q Check': 'sum',
        'Format Q Check': 'sum',
        'Char Q Check': 'sum',
    }).reset_index()
    check_df.columns = ['FileName', 'Length(👎)', 'Value(👎)', 'Char(⚠️)']

    merged_df = pd.merge(summary_df, score_df, on='FileName', how='left')
    merged_df = pd.merge(merged_df, check_df, on='FileName', how='left').fillna(0)

    # 상단 파일 선택
    merged_df.insert(0, 'Select', False)
    _progress_cols = [
        '심각(🚨)', '위험(⚠️)', '점검(☢️)', '양호(🤗)', '최상(✨)',
        'Length(👎)', 'Value(👎)', 'Char(⚠️)',
    ]
    _max_by_col = {}
    for _c in _progress_cols:
        if _c in merged_df.columns:
            _s = pd.to_numeric(merged_df[_c], errors="coerce").fillna(0)
            _m = int(_s.max()) if len(_s) else 0
            _max_by_col[_c] = max(_m, 1)

    edited_df = st.data_editor(
        merged_df, 
        width='stretch', 
        height=500, 
        hide_index=True, 
        column_config={
            'Select': st.column_config.CheckboxColumn("선택", width='small'),
            'FileName': st.column_config.TextColumn("파일명", width='medium'),
            'Column #': st.column_config.NumberColumn("컬럼수", width='small'),
            'Code #': st.column_config.NumberColumn("Code수", width='small'),
            '심각(🚨)': st.column_config.ProgressColumn(help="Grade: 심각(🚨)", min_value=0, max_value=_max_by_col.get('심각(🚨)', 1), format="%d", width='small'),
            '위험(⚠️)': st.column_config.ProgressColumn(help="Grade: 위험(⚠️)", min_value=0, max_value=_max_by_col.get('위험(⚠️)', 1), format="%d", width='small'),
            '점검(☢️)': st.column_config.ProgressColumn(help="Grade: 점검(☢️)", min_value=0, max_value=_max_by_col.get('점검(☢️)', 1), format="%d", width='small'),
            '양호(🤗)': st.column_config.ProgressColumn(help="Grade: 양호(🤗)", min_value=0, max_value=_max_by_col.get('양호(🤗)', 1), format="%d", width='small'),
            '최상(✨)': st.column_config.ProgressColumn(help="Grade: 최상(✨)", min_value=0, max_value=_max_by_col.get('최상(✨)', 1), format="%d", width='small'),
            'Length(👎)': st.column_config.ProgressColumn(help="Length Quality", min_value=0, max_value=_max_by_col.get('Length(👎)', 1), format="%d", width='small'),
            'Value(👎)': st.column_config.ProgressColumn(help="Value Quality", min_value=0, max_value=_max_by_col.get('Value(👎)', 1), format="%d", width='small'),
            'Char(⚠️)': st.column_config.ProgressColumn(help="Char Quality", min_value=0, max_value=_max_by_col.get('Char(⚠️)', 1), format="%d", width='small'),
        }
    )

    selected_file_names = edited_df[edited_df['Select'] == True]['FileName'].tolist()

    if not selected_file_names:
        st.info("💡 목록에서 파일을 선택하시면 상세 컬럼 품질 분석 결과를 보실 수 있습니다.")
        return

    st.divider()
    
    # 1. 시각화를 위한 데이터 재구성 (요청하신 시스템별 상세 리포트 방식 적용)
    st.markdown(f"#### 📊 Column-level Detail Analysis")
    
    selected_df = df[df['FileName'].isin(selected_file_names)].copy()
    
    # 등급에 따른 상태 이모지 및 텍스트 매핑 로직
    def get_status(grade):
        grade = str(grade).upper()
        if 'S' in grade: return "🔵 최상"   # 파란색 (신뢰)
        if 'A' in grade: return "🌐 양호"   # 하늘색 (안정 - 사용자 제안)
        if 'B' in grade: return "🟡 점검"   # 노란색 (주의)
        if 'C' in grade: return "🟠 위험"   # 주황색 (경고)
        if 'D' in grade: return "⚫ 심각"   # 검정색 (치명 - 사용자 제안)
        return "⚪ 미진단"

    # 시각화용 데이터 가공 (ProgressColumn을 위해 Quality Score를 0-100 점수로 환산: 1점당 20점)
    selected_df['Display Score'] = selected_df['Quality Score'] * 20.0
    selected_df['상태'] = selected_df['Quality Grade'].apply(get_status)

    # 2. [NEW] 시스템별/파일별 상세 품질 리포트 (Expander 적용)
    with st.expander("🔍 선택된 파일의 컬럼별 품질 품질 현황", expanded=True):
        st.write(f"###### 📂 대상 파일: {', '.join(selected_file_names)}")
        
        # 표시할 컬럼 설정
        view_cols = [
            'FileName', 'ColumnName', 'Display Score', '상태', 'CodeFlag',
            'Len Q', 'Format Q', 'Char Q', 'Null%'
        ]
        
        # 데이터 에디터 출력
        issue_editor = st.dataframe(
            selected_df[view_cols],
            width="stretch",
            height=450,
            hide_index=True,
            column_config={
                "FileName": st.column_config.TextColumn("파일명", width=100),
                "ColumnName": st.column_config.TextColumn("컬럼명", width=100),
                "CodeFlag": st.column_config.CheckboxColumn("Code 여부", width=50),
                "Display Score": st.column_config.ProgressColumn(
                    "품질 점수",
                    help="품질 점수(5점 만점)를 100점 만점으로 환산한 수치입니다.",
                    format="%.0f점",
                    min_value=0,
                    max_value=100,
                    width=200,
                ),
                "상태": st.column_config.TextColumn("진단 결과", width=50),
                "Len Q": st.column_config.TextColumn("길이 체크", width=50),
                "Format Q": st.column_config.TextColumn("형식 체크", width=50),
                "Char Q": st.column_config.TextColumn("문자 체크", width=50),
                "Null%": st.column_config.NumberColumn("결측률", format="%.1f%%", width=50)
            },
            # disabled=view_cols # 읽기 전용 설정
        )
        
        st.caption("💡 팁: 표 헤더를 클릭하면 정렬이 가능하며, '품질 점수'를 통해 시각적으로 문제를 파악할 수 있습니다.")

        selected_rows = selected_df
        
        if not selected_rows.empty:
            st.divider()
            st.markdown("#### 🚩 Column Issue Details")
            
            issue_list = []
            full_detail_df = df[df['FileName'].isin(selected_file_names)] # 상세 내용 추출용 원본 데이터

            for _, row in selected_rows.iterrows():
                target = full_detail_df[(full_detail_df['FileName'] == row['FileName']) & (full_detail_df['ColumnName'] == row['ColumnName'])].iloc[0]
                
                issues = [
                    ('Value', target['Value Issue'], target['Value Score']),
                    ('Format', target['Format Issue'], target['Format Score']),
                    ('Length', target['Length Issue'], target['Length Score']),
                    ('Fmt & Len', target['Format Length Issue'], target['Format Length Score']),
                    ('Character', target['Character Issue'], target['Character Score'])
                ]
                
                for category, detail, score in issues:
                    if pd.notna(detail) and str(detail).strip() != "":
                        issue_list.append({
                            'FileName': row['FileName'],
                            'ColumnName': row['ColumnName'],
                            'Category': category,
                            'Score': score,
                            'Detail': detail,
                            
                        })

        if issue_list:
            final_issue_df = pd.DataFrame(issue_list)
            st.dataframe(final_issue_df, 
            width='stretch', hide_index=True, column_config={
                "FileName": st.column_config.TextColumn("파일명", width=150),
                "ColumnName": st.column_config.TextColumn("컬럼명", width=150),
                "Category": st.column_config.TextColumn("이슈", width=50),
                "Score": st.column_config.NumberColumn("점수", width=30),
                "Detail": st.column_config.TextColumn("이슈 상세 내용", width=500),
            })
        else:
            st.success("✅ 선택한 컬럼에 특이사항(Issue)이 없습니다.")


    # 3. 선택된 파일의 컬럼별 상세 품질 리포트 (Expander 적용)
    with st.expander("🔍 선택된 파일의 컬럼별 모든 품질 리포트 보기", expanded=False):
        st.dataframe(selected_df, width='stretch', hide_index=True)

# -------------------------------------------------------------------
# FILE LOADER & MAIN APP (기존 클래스 구조 유지)
# -------------------------------------------------------------------
@dataclass
class FileConfig:
    dataprofile: str
    dataqualityanalysis: str

class FileLoader:
    def __init__(self, yaml_config: Dict[str, Any]):
        self.yaml_config = yaml_config
        self.root_path = str(PROJECT_ROOT.resolve())
        self.files_config = self._setup_files_config()
    
    def _setup_files_config(self) -> FileConfig:
        files = self.yaml_config.get('files', {})
        def _full_path(path_str):
            p = Path(path_str)
            if not p.is_absolute(): p = Path(self.root_path) / p
            return str(p.resolve())
        return FileConfig(
            dataprofile=_full_path(files.get('dataprofile', 'DS_Output/DataProfile.csv')),
            dataqualityanalysis=_full_path(files.get('dataqualityanalysis', 'DS_Output/DataQualityAnalysis.csv')),
        )
    
    def load_file(self, file_path: str, file_name: str) -> Optional[pd.DataFrame]:
        path = Path(file_path)
        if not path.exists(): return None
        try:
            for enc in ("utf-8-sig", "utf-8", "cp949"):
                try: return pd.read_csv(path, encoding=enc)
                except: continue
            return None
        except Exception as e:
            st.error(f"{file_name} 로드 실패: {str(e)}")
            return None

class DataQualityAnalyzerApp:
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
    
    def quality_analysis(self):
        st.title(f"📊 {APP_NAME}")
        st.markdown(APP_DESC)
        st.divider()

        col1, col2 = st.columns([1, 2])
        with col1:
            password_input = st.text_input("🔐 비밀번호", type="password", key="dq_pwd")

        with col2:
            st.markdown("###### 분석 실행 시 약 10분 이상 소요될 수 있습니다.")
            if st.button("🔍 Data Quality Analysis 실행", key="btn_run_dq"):
                if password_input == "qlalfqjsgh":
                    with st.spinner("품질 분석 중..."):
                        script_path = Path(PROJECT_ROOT / "util/DS_31_DataProfilingForQuality.py")
                        if script_path.exists():
                            result = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True, check=True)
                            st.success("분석 완료 ✅")
                            with st.expander("로그 확인"): st.text(result.stdout)
                        else: st.error("스크립트 파일을 찾을 수 없습니다.")
                else: st.error("❌ 비밀번호가 올바르지 않습니다.")
        
        st.divider()

        profile_df = self.loader.load_file(self.loader.files_config.dataprofile, "DataProfile")
        if profile_df is not None:  
            st.markdown("###### 분석 결과 확인")
            quality_df = dataqualityanalysis.run_dataqualityanalysis(profile_df)
            report_df = dataqualityreport.run_dataqualityreport(quality_df)
            merged_df = pd.merge(report_df, quality_df, on=('FileName', 'ColumnName'), how='left')

            if merged_df is not None:
                # st.write("debug 01: merged_df is not None")
                quality_metrics(merged_df)
                display_file_info(merged_df)
            else:
                st.info("💡 DataQualityAnalysis.csv 파일이 없습니다. ")
        else:
            st.info("💡 분석 결과가 없습니다. 위 버튼을 눌러 분석을 실행해 주세요.")

def main():
    try:
        app = DataQualityAnalyzerApp()
        if app.initialize(): app.quality_analysis()
    except Exception as e:
        st.exception(e)

if __name__ == "__main__":
    main()