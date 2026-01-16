# -*- coding: utf-8 -*-
"""
2025.12.20  Qliker 
📊 Data Analyzer (통합)
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
import sys
# import warnings
from pathlib import Path
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Any, Optional
import yaml

# -------------------------------------------------------------------
# 기본 앱 정보
# -------------------------------------------------------------------
APP_NAME = "Data Analyzer (Data Profiling)"
APP_DESC = "##### 데이터 프로파일링을 수행하여 데이터 분석을 위한 다양한 통계 정보를 생성합니다."
APP_DESC2 = """
- 데이터 프로파일링을 수행하여 데이터 분석을 위한 다양한 통계 정보를 생성하고 (Data Quality Analyzer)
- 데이터 타입 및 사전 정의된 Rule을 적용하여 데이터의 의미를 분석하며 (Data Type & Rule Analyzer)
- 데이터 간의 논리적 관계도 정보를 생성합니다. (Data Relationship Analyzer)
"""

from util.Files_FunctionV20 import load_yaml_datasense, set_page_config

set_page_config(APP_NAME)

# -------------------------------------------------------------------
# YAML CONFIG 로더
# -------------------------------------------------------------------
def _fallback_load_yaml_datasense() -> Dict[str, Any]:
    """YAML 로드 실패 시 기본 설정 반환"""
    guessed_root = str(PROJECT_ROOT)
    cfg = {
        "ROOT_PATH": guessed_root,
        "files": {
            "fileformat_output": "DS_Output/FileFormat.csv",
            "ruledatatype_output": "DS_Output/RuleDataType.csv",
            "codemapping_output": "DS_Output/CodeMapping.csv",
        },
        "DataSense_Password": "qlalfqjsgh",  # 기본 비밀번호
    }
    path = Path(guessed_root) / "util" / "DS_00_Main_Config.yaml"
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
    
    df = df.copy()
    
    for col in df.columns:
        if df[col].dtype in ['int64', 'float64', 'int32', 'float32']:
            # 숫자형 컬럼: NaN을 0으로 변환 (None 표시 방지)
            df[col] = df[col].fillna(0)
        elif df[col].dtype == 'object': # object 타입인 경우 숫자로 변환 가능한지 확인 
            try:       
                numeric_series = pd.to_numeric(df[col], errors='coerce') # 숫자로 변환 시도
                if not numeric_series.isna().all():
                    # 숫자 값이 있으면 숫자형으로 변환하고 NaN은 0으로
                    df[col] = numeric_series.fillna(0)
                else:
                    # 숫자 값이 없으면 문자열로 처리
                    df[col] = df[col].fillna("")
            except Exception:
                # 변환 실패 시 문자열로 처리
                df[col] = df[col].fillna("")
        else:
            # 문자열 컬럼은 None을 빈 문자열로
            df[col] = df[col].fillna("")
    
    return df

def display_statistics_info():
    """통계 내역에 포함된 정보들"""
    st.markdown("###### 통계 내역에 포함된 정보들은 다음과 같습니다.")
    col1, col2, col3, col4, col5, col6 = st.columns([1, 1, 1, 1, 1, 1])
    
    with col1:
        st.markdown("##### 속성 정보")
        st.write("데이터 타입")
        st.write("오라클 타입")
        st.write("룰 기반 타입")
    
    with col2:
        st.markdown("##### Value 정보")
        st.write("Primary Key 여부")
        st.write("데이터 값의 열 개수")
        st.write("Uniqueness 비율")
        st.write("Null 비율")
        st.write("최소/최대/평균/중앙 값")
    
    with col3:
        st.markdown("##### Length 정보")
        st.write("Length 종류")
        st.write("Length 최소")
        st.write("Length 최대")
        st.write("Length 다빈도")
        st.write("Length 평균/중앙값")
    
    with col4:
        st.markdown("##### Value 구성")
        st.write("영문, 한글, 숫자 등 패턴 구성")
        st.write("패턴의 종류 수")
        st.write("다빈도 패턴 구성")
        st.write("다빈도 패턴 및 비율")
        # st.write("2nd/3rd 패턴 및 비율")
    
    with col5:
        st.markdown("##### Value Top 10")
        st.write("Top 10 값")
        st.write("Top 10 비율")
    
    with col6:
        st.markdown("##### 문자 통계")
        st.write("영문 대소문자 열 수")
        st.write("한글 포함 열 수")
        st.write("숫자 포함 열 수")
        st.write("특수문자 열 수")
        st.write("혼합 문자 열 수")

def display_data_quality_results(df: pd.DataFrame):
    """Data Quality Analyzer 분석 결과 표시"""
   
    if df is None:
        st.warning(f"⚠️ Data Quality Analyzer 분석 결과 파일을 찾을 수 없습니다.")
        return
    st.markdown("##### Data Quality Analyzer 분석 결과입니다.")
    # DataFrame 정규화 (None 값 처리 및 Arrow 호환성)
    df = normalize_dataframe_for_display(df)
    
    df = df.drop(columns=['FilePath'])
    st.dataframe(df, width='stretch', height=550, hide_index=True)

def display_data_type_rule_results(df: pd.DataFrame):
    """Data Type & Rule Analyzer 분석 결과 표시"""
    required_columns = [
            "FileName", "MasterType", "ColumnName", "DataType", "OracleType",
            "Rule", "RuleType", "MatchedRule", "MatchedScoreList", 
            "MatchScoreAvg", "MatchScoreMax"
        ]
    if df is None:
        st.warning(f"⚠️ Data Type & Rule Analyzer 분석 결과 파일을 찾을 수 없습니다.")
        return
    st.markdown("##### Data Type & Rule Analyzer 분석 결과입니다.")
    # DataFrame 정규화 (None 값 처리 및 Arrow 호환성)
    df = normalize_dataframe_for_display(df)
    
    # 필수 컬럼 필터링
    available_columns = [col for col in required_columns if col in df.columns]
    if available_columns:
        df = df[available_columns]
    
    st.dataframe(df, width='stretch', height=600, hide_index=True)

def display_code_relationship_results(df: pd.DataFrame):
    """Code Relationship Analyzer 분석 결과 표시"""
    if df is None:
        st.warning(f"⚠️ Code Relationship Analyzer 분석 결과 파일을 찾을 수 없습니다.")
        return
    st.markdown("##### Code Relationship Analyzer 분석 결과입니다.")
    # DataFrame 정규화 (None 값 처리 및 Arrow 호환성)
    df = normalize_dataframe_for_display(df)
    st.dataframe(df, width='stretch', height=600, hide_index=True)

# -------------------------------------------------------------------
# FILE LOADER
# -------------------------------------------------------------------
@dataclass
class FileConfig:
    """파일 설정 정보"""
    fileformat_output: str
    ruledatatype_output: str
    codemapping_output: str
    analyzer_script_quality: str
    analyzer_script_rule: str
    analyzer_script_relationship: str
    # analyzer_script_erd_mapping: str

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
            fileformat_output=_full_path(files.get('fileformat_output', 'DS_Output/FileFormat.csv')),
            ruledatatype_output=_full_path(files.get('ruledatatype_output', 'DS_Output/RuleDataType.csv')),
            codemapping_output=_full_path(files.get('codemapping_output', 'DS_Output/CodeMapping.csv')),
            analyzer_script_quality=_full_path(files.get('analyzer_script_quality', 'util/DS_11_MasterCodeFormat.py')),
            analyzer_script_rule=_full_path(files.get('analyzer_script_rule', 'util/DS_12_MasterRuleDataType.py')),
            analyzer_script_relationship=_full_path(files.get('analyzer_script_relationship', 'util/DS_13_Code Relationship Analyzer.py')),
            # analyzer_script_erd_mapping=_full_path(files.get('analyzer_script_erd_mapping', 'util/DS_14_ERD Mapping.py'))
        )
    
    def load_file(self, file_path: str, file_name: str) -> Optional[pd.DataFrame]:
        """CSV 파일 로드"""
        path = Path(file_path)
        if not path.exists():
            return None
        
        try:
            for enc in ("utf-8-sig", "utf-8", "cp949"):
                try:
                    df = pd.read_csv(path, encoding=enc)
                    return df
                except Exception:
                    continue
            return None
        except Exception as e:
            st.error(f"{file_name} 로드 실패: {str(e)}")
            return None

# -------------------------------------------------------------------
# DATA QUALITY ANALYZER
# -------------------------------------------------------------------
class DataQualityAnalyzer:
    """Data Quality Analyzer 애플리케이션"""
    
    def __init__(self, yaml_config: Dict[str, Any], loader: FileLoader):
        self.yaml_config = yaml_config
        self.loader = loader
        self.script_path = Path(loader.files_config.analyzer_script_quality)
        self.output_path = Path(loader.files_config.fileformat_output)
    
    def run_analyzer(self) -> bool:
        """Data Quality Analyzer 스크립트 실행"""
        if not self.script_path.exists():
            st.error(f"❌ 분석 스크립트를 찾을 수 없습니다: {self.script_path}")
            return False
        
        cmd = [sys.executable, str(self.script_path)]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            st.success("분석이 완료되었습니다 ✅")
            st.text_area("📜 실행 로그", result.stdout, height=200, key="quality_analyzer_log")
            return True
        except subprocess.CalledProcessError as e:
            st.error("❌ 실행 중 오류가 발생했습니다.")
            st.text_area("⚠️ 오류 로그", e.stderr, height=200, key="quality_analyzer_error")
            return False
# -------------------------------------------------------------------
# DATA TYPE & RULE ANALYZER
# -------------------------------------------------------------------
class DataTypeRuleAnalyzer:
    """Data Type & Rule Analyzer 애플리케이션"""
    
    def __init__(self, yaml_config: Dict[str, Any], loader: FileLoader):
        self.yaml_config = yaml_config
        self.loader = loader
        self.script_path = Path(loader.files_config.analyzer_script_rule)
    
    def run_analyzer(self) -> bool:
        """Data Type & Rule Analyzer 스크립트 실행"""
        if not self.script_path.exists():
            st.error(f"❌ 분석 스크립트를 찾을 수 없습니다: {self.script_path}")
            return False
        
        cmd = [sys.executable, str(self.script_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            st.success("분석이 완료되었습니다 ✅")
            st.text_area("📜 실행 로그", result.stdout, height=200, key="rule_analyzer_log")
            return True
        except subprocess.CalledProcessError as e:
            st.error("❌ 실행 중 오류가 발생했습니다.")
            st.text_area("⚠️ 오류 로그", e.stderr, height=200, key="rule_analyzer_error")
            return False
# -------------------------------------------------------------------
# CODE RELATIONSHIP ANALYZER
# -------------------------------------------------------------------
class CodeRelationshipAnalyzer:
    """Code Relationship Analyzer 애플리케이션"""
    
    def __init__(self, yaml_config: Dict[str, Any], loader: FileLoader):
        self.yaml_config = yaml_config
        self.loader = loader
        self.script_path = Path(loader.files_config.analyzer_script_relationship)
        # self.script_erd_path = Path(loader.files_config.analyzer_script_erd_mapping)
    
    def run_analyzer(self) -> bool:
        """Code Relationship Analyzer 스크립트 실행"""
        if not self.script_path.exists():
            st.error(f"❌ 분석 스크립트를 찾을 수 없습니다: {self.script_path}")
            return False
        
        cmd = [sys.executable, str(self.script_path)]
        # cmd_erd = [sys.executable, str(self.script_erd_path)]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            st.success("분석이 완료되었습니다 ✅")
            st.text_area("📜 실행 로그", result.stdout, height=200, key="relationship_analyzer_log")
            return True
        except subprocess.CalledProcessError as e:
            st.error("❌ 실행 중 오류가 발생했습니다.")
            st.text_area("⚠️ 오류 로그", e.stderr, height=200, key="relationship_analyzer_error")
            return False  
# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------
class DataAnalyzerApp:
    """Data Analyzer 통합 애플리케이션"""
    
    def __init__(self):
        self.yaml_config = None
        self.loader = None
        self.quality_analyzer = None
        self.rule_analyzer = None
        self.relationship_analyzer = None
        self.password = None
    
    def initialize(self) -> bool:
        """초기화"""
        try:
            self.yaml_config = load_yaml_datasense()
            self.loader = FileLoader(self.yaml_config)
            self.quality_analyzer = DataQualityAnalyzer(self.yaml_config, self.loader)
            self.rule_analyzer = DataTypeRuleAnalyzer(self.yaml_config, self.loader)
            self.relationship_analyzer = CodeRelationshipAnalyzer(self.yaml_config, self.loader)
            self.password = self.yaml_config.get("DataSense_Password", "") # tkfkdgo
            return True
        except Exception as e:
            st.error(f"초기화 오류: {e}")
            return False
    
    def data_analyzer(self):
        """메인 UI 표시"""
        st.title(f"📊 {APP_NAME}")
        st.markdown(APP_DESC)
        st.markdown(APP_DESC2)
        
        display_statistics_info()

        st.divider()
        col1, col2 = st.columns([1, 2])
        with col1:
            password_input = None
            with st.expander("🔐 실행 비밀번호 입력", expanded=True):
                password_input = st.text_input(
                    "비밀번호를 입력하세요",
                    type="password",
                    key="data_analyzer_password_input",
                    help="Data Analyzer 실행을 위한 비밀번호가 필요합니다."
                )

        with col2:
            st.markdown("###### 분석 대상 파일의 수 및 크기에 따라 시간이 많이 소요될 수 있습니다. (약 10분 이상 소요)")
            if st.button("🔍 Data Analyzer 실행", key="btn_integrated_analyzer"):
                if not password_input:
                    st.error("❌ 비밀번호를 입력하세요.")
                elif password_input != self.password:
                    st.error("❌ 비밀번호가 올바르지 않습니다.")
                else:
                    # 통합 분석 프로세스 시작
                    with st.spinner("전체 데이터 분석 프로세스를 진행 중입니다..."):
                        # 1. 프로그레스 바와 상태 텍스트 영역 생성
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # --- [1단계: Data Quality] ---
                        status_text.write("⏳ [1/3] Data Quality 분석을 수행 중입니다... (33%)")
                        progress_bar.progress(10) # 시작 시 약간 채움
                        
                        if self.quality_analyzer.run_analyzer():
                            progress_bar.progress(33)
                            
                            # --- [2단계: Data Type & Rule] ---
                            status_text.write("⏳ [2/3] Data Type & Rule 분석을 수행 중입니다... (66%)")
                            if self.rule_analyzer.run_analyzer():
                                progress_bar.progress(66)
                                
                                # --- [3단계: Code Relationship] ---
                                status_text.write("⏳ [3/3] Code Relationship 분석을 수행 중입니다... (100%)")
                                if self.relationship_analyzer.run_analyzer():
                                    progress_bar.progress(100)
                                    status_text.empty() # 진행 텍스트 삭제
                                    
                                    st.success("🎉 모든 분석 단계(Quality -> Rule -> Relationship)가 완료되었습니다!")
                                    st.balloons()
                                else:
                                    st.error("❌ 3단계(Relationship) 분석 중 오류가 발생했습니다.")
                            else:
                                st.error("❌ 2단계(Rule) 분석 중 오류가 발생했습니다.")
                        else:
                            st.error("❌ 1단계(Quality) 분석 중 오류가 발생했습니다.")
        #----------------------------------------------------
        # Data Analyzer 분석 결과 표시
        #----------------------------------------------------
        st.divider()
        st.markdown("##### Data Analyzer 분석 결과입니다.")
        tab1, tab2, tab3 = st.tabs(["Data Quality Analyzer", "Data Type & Rule Analyzer", "Code Relationship Analyzer"])
        with tab1:
            df = self.loader.load_file(self.loader.files_config.fileformat_output, "FileFormat")
            if df is not None:  
                display_data_quality_results(df)
            else:
                st.info("Data Quality Analyzer 분석 결과가 없습니다.")
        with tab2:
            df = self.loader.load_file(self.loader.files_config.ruledatatype_output, "RuleDataType")
            if df is not None:  
                st.info("아래 데이터는 이전에 처리된 결과입니다. ")
                display_data_type_rule_results(df)
            else:
                st.info("Data Type & Rule Analyzer 분석 결과가 없습니다.")
        with tab3:
            df = self.loader.load_file(self.loader.files_config.codemapping_output, "CodeMapping")
            if df is not None:  
                st.info("아래 데이터는 이전에 처리된 결과입니다. ")
                display_code_relationship_results(df)
            else:
                st.info("Code Relationship Analyzer 분석 결과가 없습니다.")

        st.info("##### Data Quality Information 앱에서 상세 분석을 수행할 수 있습니다.")
# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------
def main():
    try:
        app = DataAnalyzerApp()
        if app.initialize():
            app.data_analyzer()
        else:
            st.error("DataAnalyzerApp 초기화 실패")
    except Exception as e:
        st.error(f"애플리케이션 오류: {e}")
        import traceback
        st.exception(e)

if __name__ == "__main__":
    main()

