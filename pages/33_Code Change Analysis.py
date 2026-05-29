# -*- coding: utf-8 -*-
"""
2026.02.26  Qliker 
📊 Code Change Analysis
"""
# -------------------------------------------------------------------
# 1. 경로 설정 (Streamlit warnings import 전에 필요)
# -------------------------------------------------------------------
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# -------------------------------------------------------------------
# 2. 컴파일 발생하는 Streamlit 경고 메시지 억제 설정 (Streamlit import 전에 호출)
# -------------------------------------------------------------------
from util.streamlit_warnings import setup_streamlit_warnings
setup_streamlit_warnings()

# -------------------------------------------------------------------
# 3. 필수 라이브러리 import
# -------------------------------------------------------------------
import streamlit as st
import subprocess
import os
import pandas as pd
import numbers
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional
import yaml

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
APP_NAME = "Code Change Analysis (코드 변동성 분석)"
APP_DESC = "#### 코드의 데이터 형태가 변동된 이력을 분석합니다. "

from util.Files_FunctionV20 import load_yaml_datasense, set_page_config
set_page_config(APP_NAME)

from util.Display import display_kpi_metrics
# -------------------------------------------------------------------
# YAML CONFIG 로더
# -------------------------------------------------------------------
def _fallback_load_yaml_datasense() -> Dict[str, Any]:
    """YAML 로드 실패 시 기본 설정 반환"""
    guessed_root = str(PROJECT_ROOT)
    cfg = {
        "ROOT_PATH": guessed_root,
        "files": {
            "dataprofile": "DS_Output/DataProfile.csv",
            "datachangehistory": "DS_Output/DataChangeHistory.csv",
            "datachangestats": "DS_Output/DataChangeStats.csv",
        },
        "DataSense_Password": "qlalfqjsgh",  # 기본 비밀번호
    }
    path = Path(guessed_root) / "util" / "DataSense_Config.yaml"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                y = yaml.safe_load(f) or {}
                y.setdefault("ROOT_PATH", guessed_root)
                y.setdefault("files", cfg["files"])
                return y
        except Exception:
            pass
    return cfg

try:
    from util.Files_FunctionV20 import load_yaml_datasense  # type: ignore
except Exception:
    load_yaml_datasense = _fallback_load_yaml_datasense

# -------------------------------------------------------------------
# 유틸 함수
# -------------------------------------------------------------------
def normalize_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame을 Streamlit 표시용으로 정규화
    - 숫자형 컬럼: NaN을 0으로 변환 (None 표시 방지)
    - object 타입 컬럼: 숫자로 변환 가능하면 변환, 불가능하면 None을 빈 문자열로
    - 문자열 컬럼: None을 빈 문자열로
    Args:
        df: 처리할 DataFrame
    Returns:
        정규화된 DataFrame
    """
    if df is None or df.empty:
        return df
    
    return df

def format_display_value(value: Any) -> str:
    """표시용 값 정규화: 불필요한 소수점 제거"""
    if pd.isna(value):
        return ""
    if isinstance(value, numbers.Number):
        num = float(value)
        if num.is_integer():
            return str(int(num))
        return f"{num}".rstrip("0").rstrip(".")
    text = str(value)
    if re.match(r"^-?\d+\.\d+$", text):
        return text.rstrip("0").rstrip(".")
    return text

def display_stats_metrics(stats_df: pd.DataFrame, history_df: pd.DataFrame):
    """Code Change Stats Analyzer 분석 결과 표시"""

    with st.expander("📊 Code Change Status Description.", expanded=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown("###### Changed (🚨)")
            st.markdown("###### Fixed")
            st.markdown("###### Variable")
        with col2:
            st.markdown("###### -> 데이터의 형식이 변경된 코드로서 점검 대상입니다.")
            st.markdown("###### -> 데이터의 형식이 고정형 코드입니다.")
            st.markdown("###### -> 데이터의 형식이 변동형 코드입니다.")

    total_files = stats_df['FileName'].nunique()
    total_columns = stats_df[['FileName', 'ColumnName']].drop_duplicates().shape[0]
    changed_columns = stats_df[stats_df['ChangeStatus'] == 'Changed'][['FileName', 'ColumnName']].drop_duplicates().shape[0]
    stable_columns = stats_df[stats_df['ChangeStatus'] == 'Fixed'][['FileName', 'ColumnName']].drop_duplicates().shape[0]
    variable_columns = stats_df[stats_df['ChangeStatus'] == 'Variable'][['FileName', 'ColumnName']].drop_duplicates().shape[0]
    
    summary = {
        "전체 파일수": f"{total_files:,}",
        "전체 코드수": f"{total_columns:,}",
        "Changed Code #": f"{changed_columns:,}",
        "Fixed Code #": f"{stable_columns:,}",
        "Variable Code #": f"{variable_columns:,}",
    }
    metric_colors = {
        "전체 파일수": "#1f77b4",
        "전체 코드수": "#2ca02c",
        "Changed Code #": "#d62728",
        "Fixed Code #": "#9467bd",
        "Variable Code #": "#1a9850",
    }
    display_kpi_metrics(summary, metric_colors, "Code Change Analyzer Summary")

def display_history_report(history_df: pd.DataFrame):
    st.subheader("Code Change History Report")
    ts_col = None
    for cand in ("EventTimestamp", "TimestampColumn", "Timestamp", "event_timestamp", "create_time"):
        if cand in history_df.columns:
            ts_col = cand
            break

    report_df = history_df.copy()
    if ts_col is not None:
        report_df[ts_col] = pd.to_datetime(report_df[ts_col], errors="coerce")
        report_df = report_df.sort_values([c for c in ["FileName", "ColumnName", ts_col] if c in report_df.columns])
    else:
        report_df = report_df.sort_values([c for c in ["FileName", "ColumnName"] if c in report_df.columns])

    def _safe_text(v) -> str:
        if v is None:
            return "-"
        s = str(v).strip()
        return "-" if s == "" or s.lower() == "nan" else s

    last_group = None
    for _, r in report_df.iterrows():
        f_name = _safe_text(r.get("FileName"))
        c_name = _safe_text(r.get("ColumnName"))
        group = (f_name, c_name)
        if group != last_group:
            st.markdown(f"**{f_name}**, **{c_name}** 의 코드 변동 이력입니다.")
            last_group = group

        if ts_col is not None:
            ts_val = r.get(ts_col)
            ts_text = "-" if pd.isna(ts_val) else pd.Timestamp(ts_val).strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_text = "-"

        b_fmt = _safe_text(r.get("BeforeFormat"))
        a_fmt = _safe_text(r.get("AfterFormat"))
        b_val = _safe_text(r.get("BeforeValue"))
        a_val = _safe_text(r.get("AfterValue"))
        b_len = _safe_text(r.get("B Length"))
        a_len = _safe_text(r.get("A Length"))

        st.markdown(
            f"- **{ts_text}** 기준으로 **{b_fmt} ({b_val})** 형태(길이: **{b_len}**)가 "
            f"**{a_fmt} ({a_val})** 형태(길이: **{a_len}**)로 변경되었습니다."
        )

def display_history_detail(history_df: pd.DataFrame):
    history_view_df = history_df.copy()
    if 'TimestampColumn' in history_view_df.columns:
        history_view_df = history_view_df.drop(columns=['TimestampColumn'])
    st.dataframe(history_view_df, width='stretch', height=300, hide_index=True, column_config={
        'BeforeFormat': st.column_config.TextColumn("Before Format", width='small'),
        'AfterFormat': st.column_config.TextColumn("After Format", width='small'),
        'BeforeValue': st.column_config.TextColumn("Before Value", width='small'),
        'AfterValue': st.column_config.TextColumn("After Value", width='small'),
    })

def select_stats(stats_df: pd.DataFrame, history_df: pd.DataFrame, profile_df: pd.DataFrame) -> list[str]:
    """Code Change Analyzer 분석 결과 표시"""
    if stats_df is None:
        st.warning(f"⚠️ Code Change Analyzer 분석 결과 파일을 찾을 수 없습니다.")
        return
    st.divider()
    st.subheader("Code Change Analyzer Detail")

    # stats_df = stats_df[stats_df['ChangeCode'] == 1 | stats_df['ChangeCode'] == 2]
    # ChangeStatus 를 선택 옵션으로 추가
    change_status_options = list(stats_df['ChangeStatus'].unique())
    # Default: Changed가 있으면 선택, 없으면 첫 번째 값
    default_index = change_status_options.index('Changed') if 'Changed' in change_status_options else 0
    change_status = st.selectbox(
        "ChangeStatus 선택",
        change_status_options,
        index=default_index,
        key="change_status_selectbox"
    )
    stats_df = stats_df[stats_df['ChangeStatus'] == change_status]  # ChangeStatus 필터링

    # stats_df 의 첫 컬럼에 선택 컬럼을 추가하여 체크된 행의 FileName을 리턴함 (selected_file_names)
    if 'Select' not in stats_df.columns:
        stats_df = stats_df.copy()
        stats_df.insert(0, 'Select', False)

    # ChangeCount를 진행바(ProgressColumn)로 표시 (값이 문자열로 들어오는 경우 대비)
    stats_df = stats_df.copy()
    if "ChangeCount" in stats_df.columns:
        stats_df["ChangeCount"] = pd.to_numeric(stats_df["ChangeCount"], errors="coerce").fillna(0).astype(int)
        change_count_max = int(stats_df["ChangeCount"].max()) if not stats_df.empty else 0
        change_count_max = max(change_count_max, 1)
    else:
        change_count_max = 1

    # TotalRows는 천단위 콤마로 표시 (예: 12,345)
    if "TotalRows" in stats_df.columns:
        _total_rows_num = pd.to_numeric(stats_df["TotalRows"], errors="coerce").fillna(0).astype(int)
        stats_df["TotalRows"] = _total_rows_num.map(lambda x: f"{x:,}")

    editor_column_config = {
        'Select': st.column_config.CheckboxColumn("Select", width='small'),
        'FileName': st.column_config.TextColumn("FileName", width='small'),
    }
    if "TotalRows" in stats_df.columns:
        editor_column_config["TotalRows"] = st.column_config.TextColumn("TotalRows", width="small")
    if "ChangeCount" in stats_df.columns:
        editor_column_config["ChangeCount"] = st.column_config.ProgressColumn(
            "ChangeCount",
            help="선택된 ChangeStatus 기준 변경 발생 횟수",
            format="%d",
            min_value=0,
            max_value=change_count_max,
            width="small",
        )

    selected_file_names = st.data_editor(
        stats_df,
        width='stretch',
        height=400,
        hide_index=True,
        column_config=editor_column_config,
        key="stats_df_editor",
    )
    selected_file_names = selected_file_names[selected_file_names['Select'] == True]['FileName'].tolist()
    if len(selected_file_names) == 0:
        st.info("상세분석을 위하여 코드를 선택해 주세요. ")
        return None

    if selected_file_names and change_status == 'Changed':
        history_df = history_df[history_df['FileName'].isin(selected_file_names)].copy()
        
        # BeforeValue, AfterValue 모두 문자형으로 출력
        for col_name in ['BeforeValue', 'AfterValue']:
            if col_name in history_df.columns:
                history_df[col_name] = history_df[col_name].apply(format_display_value)
        # ChangeCountInCol 은 제거
        history_df = history_df.drop(columns=['ChangeCountInCol'])
        history_df['B Length'] = history_df['BeforeValue'].str.len()
        history_df['A Length'] = history_df['AfterValue'].str.len()

        st.divider()
        tab0, tab1, tab2 = st.tabs(["Code Change History Report", "Code Change History", "Data Profile"])
        with tab0:
            display_history_report(history_df)
        with tab1:
            display_history_detail(history_df)
        with tab2:
            st.subheader("Data Profile Detail")
            profile_df = profile_df[profile_df['FileName'].isin(selected_file_names)]
            st.dataframe(profile_df, width='stretch', height=300, hide_index=True)
    else:
        st.info("선택된 파일이 없습니다.")
        return None

# -------------------------------------------------------------------
# FILE LOADER
# -------------------------------------------------------------------
@dataclass
class FileConfig:
    """파일 설정 정보"""
    dataprofile: str
    datachangehistory: str
    datachangestats: str
    datachangehistory_script: str

class FileLoader:
    """파일 로딩을 위한 클래스"""
    
    def __init__(self, yaml_config: Dict[str, Any]):
        self.yaml_config = yaml_config
        self.root_path = str(PROJECT_ROOT.resolve())
        self.files_config = self._setup_files_config()
    
    def _setup_files_config(self) -> FileConfig:
        """파일 설정 구성"""
        files = self.yaml_config.get('files', {})
        
        def _full_path(path_str):
            p = Path(path_str)
            if not p.is_absolute():
                p = Path(self.root_path) / p
            return str(p.resolve())
        
        return FileConfig(
            dataprofile=_full_path(files.get('dataprofile', 'DS_Output/DataProfile.csv')),
            datachangehistory=_full_path(files.get('datachangehistory', 'DS_Output/DataChangeHistory.csv')),
            datachangestats=_full_path(files.get('datachangestats', 'DS_Output/DataChangeStats.csv')),
            datachangehistory_script=_full_path(files.get('datachangehistory_script', 'util/DS_32_DataChangeHistory.py')),
        )
    
    def load_file(self, file_path: str, file_name: str) -> Optional[pd.DataFrame]:
        """CSV 파일 로드"""
        path = Path(file_path)
        if not path.exists():
            return None
        
        try:
            for enc in ("utf-8-sig", "utf-8", "cp949"):
                try:
                    df = pd.read_csv(path, encoding=enc, dtype=str)
                    return df
                except Exception:
                    continue
            return None
        except Exception as e:
            st.error(f"{file_name} 로드 실패: {str(e)}")
            return None

# -------------------------------------------------------------------
# DATA CHANGE ANALYZER
# -------------------------------------------------------------------
class DataChangeAnalyzer:
    """Data Change Analyzer 애플리케이션"""
    
    def __init__(self, yaml_config: Dict[str, Any], loader: FileLoader):
        self.yaml_config = yaml_config
        self.loader = loader
        self.datachangehistory_script_path = Path(loader.files_config.datachangehistory_script)
        self.output_path = Path(loader.files_config.datachangehistory)
    
    def run_analyzer(self) -> bool:
        """Code Change History script 실행"""

        if not self.datachangehistory_script_path.exists():
            st.error(
                f"❌ {self.datachangehistory_script_path} 분석 스크립트를 찾을 수 없습니다: "
            )
            return False
             
        changehistory_cmd = [sys.executable, str(self.datachangehistory_script_path)]
        try:
            changehistory_result = subprocess.run(changehistory_cmd, capture_output=True, text=True, check=True)
            st.success("Code Change History 분석이 완료되었습니다 ✅")
            st.text_area("📜 Code Change History 실행 로그", changehistory_result.stdout, height=200, key="changehistory_log")
            return True
        except subprocess.CalledProcessError as e:
            st.error(f"❌ 실행 중 오류가 발생했습니다: {e}")
            return False
# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------
class CodeChangeAnalyzerApp:
    """Code Change Analyzer 통합 애플리케이션"""
    
    def __init__(self):
        self.yaml_config = None
        self.loader = None
        self.data_change_analyzer = None
        self.password = None
    
    def initialize(self) -> bool:
        """초기화"""
        try:
            self.yaml_config = load_yaml_datasense()
            self.loader = FileLoader(self.yaml_config)
            self.data_change_analyzer = DataChangeAnalyzer(self.yaml_config, self.loader)
            self.password = self.yaml_config.get("DataSense_Password", "") # qlalfqjsgh
            return True
        except Exception as e:
            st.error(f"초기화 오류: {e}")
            return False
    
    def code_change_analysis(self):
        """메인 UI 표시"""
        st.title(f"📊 {APP_NAME}")
        st.markdown(APP_DESC)
        st.write("데이터가 시간 순서(create_time)대로 나열되어 있고 특정 시점을 기준으로 '코드' 컬럼의 체계(Format)가 완전히 바뀌는 구간이 존재합니다.")
        st.write("이를 자동으로 감지하기 위해 '슬라이딩 윈도우(Sliding Window)' 기법을 활용하여  데이터의 패턴을 추적하다가 패턴의 구성 비율이 변하는 지점을 '변곡점'으로 찾아냅니다.")

        
        st.divider()
        col1, col2 = st.columns([1, 2])
        with col1:
            password_input = None
            with st.expander("🔐 실행 비밀번호 입력", expanded=True):
                password_input = st.text_input(
                    "비밀번호를 입력하세요",
                    type="password",
                    key="data_change_analysis_password_input",
                    help="Code Change Analysis 실행을 위한 비밀번호가 필요합니다."
                )

        with col2:
            st.markdown("###### 분석 대상 파일의 수 및 크기에 따라 시간이 많이 소요될 수 있습니다. (약 10분 이상 소요)")
            if st.button("🔍 Code Change Analysis 실행", key="btn_code_change_analysis"):
                if not password_input:
                    st.error("❌ 비밀번호를 입력하세요.")
                elif password_input != self.password:
                    st.error("❌ 비밀번호가 올바르지 않습니다.")
                else:
                    # 통합 분석 프로세스 시작
                    with st.spinner("코드 변동 이력 분석 프로세스를 진행 중입니다..."):
                        # 1. 프로그레스 바와 상태 텍스트 영역 생성
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        if self.data_change_analyzer.run_analyzer():
                            progress_bar.progress(100)
                            status_text.empty() # 진행 텍스트 삭제
                            st.success("🎉 코드 변동 이력 분석이 완료되었습니다!")
                        else:
                            st.error("❌ 코드 변동 이력 분석 중 오류가 발생했습니다.")
        #----------------------------------------------------
        # Data Analyzer 분석 결과 표시
        #----------------------------------------------------
        st.divider()

        profile_df = self.loader.load_file(self.loader.files_config.dataprofile, "DataProfile")
        stats_df = self.loader.load_file(self.loader.files_config.datachangestats, "DataChangeStats")
        history_df = self.loader.load_file(self.loader.files_config.datachangehistory, "DataChangeHistory")

        if profile_df is None:
            st.info("❌ Data Profile 분석 결과가 없습니다.")
            st.info("Data Quality Analyzer 앱을 실행하여 데이터 프로파일링을 수행해 주세요.")
            return

        if stats_df is None:
            st.info("❌ Code Change Stats 분석 결과가 없습니다.")
            st.info("Code Change Analyzer 앱을 실행하여 코드 변동 이력을 분석해 주세요.")
            return

        if history_df is None:
            st.info("❌ Code Change History 분석 결과가 없습니다.")
            st.info("Code Change Analyzer 앱을 실행하여 코드 변동 이력을 분석해 주세요.")
            return

        if stats_df is not None and history_df is not None:  
            display_stats_metrics(stats_df, history_df)
            selected_file_names = select_stats(stats_df, history_df, profile_df)
        else:
            st.info("Code Change Stats Analyzer 분석 결과가 없습니다.")
# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------
def main():
    try:
        app = CodeChangeAnalyzerApp()
        if app.initialize():
            app.code_change_analysis()
        else:
            st.error("Code Change Analyzer App 초기화 실패")
    except Exception as e:
        st.error(f"Code Change Analyzer App 오류: {e}")
        import traceback
        st.exception(e)

if __name__ == "__main__":
    main()

