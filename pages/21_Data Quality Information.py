# streamlit를 이용한 Data Sense System : Data Quality Information
# 2025. 12. 20.  Qliker
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
# 2. Streamlit 경고 억제 설정 (Streamlit import 전에 호출)
# -------------------------------------------------------------------
from util.streamlit_warnings import setup_streamlit_warnings
setup_streamlit_warnings()

# -------------------------------------------------------------------
# 3. 필수 라이브러리 import
# -------------------------------------------------------------------
import streamlit as st
import pandas as pd
import numpy as np
import yaml
import re
from datetime import datetime
import sys
import os
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
# import warnings
from graphviz import Digraph
from dataclasses import dataclass
from typing import Dict, Any, Optional
import plotly.graph_objects as go


SOLUTION_NAME = "Data Sense System"
SOLUTION_KOR_NAME = "데이터 센스 시스템"
APP_NAME = "Data Quality Information"
APP_DESC = "###### Data Analyzer의 결과를 기반으로 각 컬럼들에 대한 통계 정보입니다.  "


from util.Files_FunctionV20 import load_yaml_datasense, set_page_config
set_page_config(APP_NAME)

from util.Display import create_metric_card

#-----------------------------------------------------------------------------------------
# Master KPI 
def Display_Master_KPIs(loaded_data):
    """ Master Statistics KPIs """
    def calculate_master_type_counts(df):
        """MasterType별 파일 수 계산"""
        if 'MasterType' not in df.columns or 'FileName' not in df.columns:
            return {}
        try:
            master_type_counts = df.groupby('MasterType')['FileName'].nunique()
            expected_types = ['Master', 'Operation', 'Attribute', 'Common', 'Reference', 'Validation']
            
            result = {}
            for master_type in expected_types:
                count = master_type_counts.get(master_type, 0)
                result[master_type] = f"{count:,}"
            return result
        except Exception as e:
            st.error(f"MasterType 계산 중 오류 발생: {str(e)}")
            return {}

    df = loaded_data['filestats']
    df = df[(df['MasterType'] != 'Common') & (df['MasterType'] != 'Reference') & (df['MasterType'] != 'Validation')]

    if df is None or df.empty:
        st.warning("데이터가 없습니다.")
        return
    
    st.markdown("### File Statistics")
    # KPI 계산
    total_files = len(df['FileName'].unique()) if 'FileName' in df.columns else 0
    total_records = df['RecordCnt'].sum() if 'RecordCnt' in df.columns else 0
    total_filesize = df['FileSize'].sum() if 'FileSize' in df.columns else 0
    total_master_types = len(df['MasterType'].unique()) if 'MasterType' in df.columns else 0
    work_date = df['WorkDate'].max() if 'WorkDate' in df.columns else ''

    if total_records < 1000:
        total_records_unit = '건'
    else:
        total_records = total_records / 10000
        total_records_unit = '만건'

    if total_filesize < 1000:
        total_filesize = total_filesize 
        total_filesize_unit = 'Bytes'
    elif total_filesize < 1000000:
        total_filesize = total_filesize / 1000
        total_filesize_unit = 'KB'
    elif total_filesize < 1000000000:
        total_filesize = total_filesize / 1000000
        total_filesize_unit = 'MB'
    else:
        total_filesize = total_filesize / 1000000000
        total_filesize_unit = 'GB'        

    summary = {
        "Data File #": f"{total_files:,}",
        "Total Record #": f"{total_records:,.0f} {total_records_unit}",
        "Total File Size": f"{total_filesize:,.0f} {total_filesize_unit}",
        "Work Date": f"{work_date}"
    }

    # 각 메트릭에 대한 색상 정의
    metric_colors = {
        "Data File #": "#1f77b4",
        "Total Record #": "#2ca02c", 
        "Total File Size": "#ff7f0e",
        "Work Date": "#9467bd"
    }

    # 메트릭 표시
    cols = st.columns(len(summary))
    for col, (key, value) in zip(cols, summary.items()):
        color = metric_colors.get(key, "#0072B2")
        col.markdown(create_metric_card(value, key, color), unsafe_allow_html=True)

    return True

#-----------------------------------------------------------------------------------------
def Display_MasterFormat_Detail(loaded_data):
    """Master Format Detail 화면 출력 (21_Data Quality Information.py) 참조"""

    # 각 뷰별 컬럼 정의
    VIEW_COLUMNS = {
        "Value Info": [
            'FileName', 'ColumnName', 'OracleType', 'PK', 'ValueCnt',
            'Null(%)', 'UniqueCnt', 'Unique(%)',
            'MinString', 'MaxString', 'ModeString', 'MedianString', 'ModeCnt'
        ],
        "Value Type Info": [
            'FileName', 'ColumnName', 'ValueCnt', 'FormatCnt',
            'Format', 'Format(%)', 'FormatMin', 'FormatMax', 'FormatMode', 'FormatMedian',
            'Format2nd', 'Format2nd(%)', 'Format2ndMin', 'Format2ndMax', 'Format2ndMode', 'Format2ndMedian',
            'Format3rd', 'Format3rd(%)'
        ],

        "Top10 Info": [
            'FileName', 'ColumnName', 'ValueCnt', 'ModeString', 'ModeCnt',
            'Top10', 'Top10(%)'
        ],
        "Length Info": [
            'FileName', 'ColumnName', 'OracleType', 'PK', 'DetailDataType',
            'LenCnt', 'LenMin', 'LenMax', 'LenAvg', 'LenMode',
            'RecordCnt', 'SampleRows', 'ValueCnt', 'NullCnt', 'Null(%)',
            'UniqueCnt', 'Unique(%)'
        ],
        "Character Info": [
            'FileName', 'ColumnName', 'ValueCnt', 'HasBrokenKor', 'HasSpecial', 'HasUnicode', 
            'HasTab', 'HasCr', 'HasLf', 'HasChinese', 'HasJapanese', 'HasBlank', 'HasDash', 'HasDot', 'HasAt', 'HasAlpha',
            'HasKor', 'HasNum', 'HasBracket', 'HasMinus', 'HasOnlyAlpha', 'HasOnlyNum',
            'HasOnlyKor', 'HasOnlyAlphanum',
            'FirstChrKor', 'FirstChrNum', 'FirstChrAlpha', 'FirstChrSpecial'
        ],
        "DQ Score Info": [
            'FileName', 'ColumnName', 'ValueCnt', 'Null_pct', 'TypeMixed_pct', 'LengthVol_pct', 'Duplicate_pct',
            'DQ_Score', 'DQ_Issues', 'Issue_Count'
        ]
    }

    # ---------------------------
    st.markdown("### Data Quality Information")
    st.markdown("###### 아래의 탭에서 상세 정보를 확인할 수 있습니다.")
    ff_df = loaded_data.get('fileformat', pd.DataFrame())
    ff_df = ff_df[(ff_df['MasterType'] != 'Common') & (ff_df['MasterType'] != 'Reference') & (ff_df['MasterType'] != 'Validation')]
    
    if ff_df.empty:
        st.warning("Data Quality 분석 파일을 로드할 수 없습니다.")
        return False

    if ff_df is not None and not ff_df.empty:
        tabs = ['Value Info', 'Value Type Info', 'Top10 Info', 'Length Info', 
            'Character Info', 'DQ Score Info', 'Total Statistics']
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tabs)

        with tab1:
            st.markdown("###### 모든 컬럼들의 데이터 값 정보를 제공합니다.")
            # render_table(ff_df, 'Data Value Info', VIEW_COLUMNS['Value Info'])
            df = ff_df[VIEW_COLUMNS['Value Info']].reset_index(drop=True)
            st.dataframe(data=df, width=1400, height=600, hide_index=True)
        with tab2:
            st.markdown("###### 모든 컬럼들의 데이터 타입 정보를 제공합니다.")
            df = ff_df[VIEW_COLUMNS['Value Type Info']].reset_index(drop=True)
            st.dataframe(data=df, width=1400, height=600, hide_index=True)
        with tab3:
            st.markdown("###### 모든 컬럼들의 빈도수 상위 10개를 제공합니다.")
            df = ff_df[VIEW_COLUMNS['Top10 Info']].reset_index(drop=True)
            st.dataframe(data=df, width=1400, height=600, hide_index=True)
        with tab4:
            st.markdown("###### 모든 컬럼들의 길이 정보를 제공합니다.")
            df = ff_df[VIEW_COLUMNS['Length Info']].reset_index(drop=True)
            st.dataframe(data=df, width=1400, height=600, hide_index=True)
        with tab5:
            st.markdown("###### 모든 컬럼들의 구성하는 문자 정보를 제공합니다.")
            df = ff_df[VIEW_COLUMNS['Character Info']].reset_index(drop=True)
            st.dataframe(data=df, width=1400, height=600, hide_index=True)
        with tab6:
            st.markdown("###### 모든 컬럼들의 Data Quality Score 정보를 제공합니다. (기업의 상황에 따라 기준이 다를 수 있습니다. 컨설팅 후 확정합니다.)")
            df = ff_df[VIEW_COLUMNS['DQ Score Info']].reset_index(drop=True)
            st.dataframe(data=df, width=1400, height=600, hide_index=True)
        with tab7:
            st.markdown("###### 모든 컬럼들의 통계 정보를 제공합니다.")
            df = ff_df.reset_index(drop=True)
            st.dataframe(data=df, width=1400, height=600,hide_index=True)
    else:
        st.warning("Data Quality 분석 파일을 로드할 수 없습니다.")
        return False
    return True
#-----------------------------------------------------------------------------------------
@dataclass
class FileConfig:
    """파일 설정 정보"""
    fileformat: str
    filestats: str
    # fileformatmapping: str

class FileLoader:
    """파일 로딩을 위한 클래스"""
    
    def __init__(self, yaml_config: Dict[str, Any]):
        self.yaml_config = yaml_config
        self.root_path = str(PROJECT_ROOT.resolve())
        self.files_config = self._setup_files_config()
    
    def _setup_files_config(self) -> FileConfig:
        """파일 설정 구성"""
        files = self.yaml_config['files']
        return FileConfig(
            fileformat=f"{self.root_path}/{files['fileformat']}",
            filestats=f"{self.root_path}/{files['filestats']}",
            # fileformatmapping=f"{self.root_path}/{files['fileformatmapping']}",
        )
    
    def load_file(self, file_path: str, file_name: str) -> Optional[pd.DataFrame]:
        """단일 파일 로드"""
        if not os.path.exists(file_path):
            st.warning(f"{file_name} 파일이 존재하지 않습니다: {file_path}")
            return None
        
        try:
            extension = os.path.splitext(file_path)[1].lower()
            if extension == '.csv':
                return pd.read_csv(file_path)
            elif extension == '.xlsx':
                return pd.read_excel(file_path)
            elif extension == '.pkl':
                return pd.read_pickle(file_path)
            else:
                st.error(f"{file_name} 파일 형식을 지원하지 않습니다: {extension}")
                return None
        except Exception as e:
            st.error(f"{file_name} 파일 로드 실패: {str(e)}")
            return None
    
    def _fix_numeric_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """숫자형 컬럼의 빈 문자열을 NaN으로 변환하고 숫자형으로 변환"""
        if df is None or df.empty:
            return df
        
        df = df.copy()
        
        # 숫자형으로 변환해야 하는 컬럼을 자동 감지
        numeric_patterns = [
            r'Cnt', r'Count', r'\(%\)', r'pct', r'Min', r'Max', r'Avg', 
            r'Mode', r'Score', r'Value', r'Size', r'PK', r'Has[A-Z]', 
            r'First[A-Z]', r'Len[A-Z]', r'Format\d*', r'Top\d+'
        ]
        
        # 문자열 컬럼 제외 (명시적으로 문자열인 컬럼)
        string_columns = ['FileName', 'ColumnName', 'OracleType', 'DetailDataType',
                         'MinString', 'MaxString', 'ModeString', 'MedianString',
                         'Format', 'Format2nd', 'Format3rd', 'Top10', 'WorkDate',
                         'MasterType', 'DQ_Issues']
        
        for col in df.columns:
            # 문자열 컬럼은 제외
            if col in string_columns:
                df[col] = df[col].fillna('')
                continue
            
            # 패턴 매칭으로 숫자형 컬럼 후보 확인
            is_numeric_candidate = any(re.search(pattern, col, re.IGNORECASE) 
                                      for pattern in numeric_patterns)
            
            # 패턴 매칭이 안 되더라도 실제 데이터가 숫자로 변환 가능한지 확인
            if not is_numeric_candidate:
                # 샘플 데이터 확인 (최대 100개 행)
                sample_size = min(100, len(df))
                if sample_size > 0:
                    sample = df[col].dropna().head(sample_size)
                    if len(sample) > 0:
                        # 빈 문자열이 아닌 샘플 중 숫자로 변환 가능한 비율 확인
                        non_empty = sample[sample != '']
                        if len(non_empty) > 0:
                            try:
                                numeric_count = pd.to_numeric(non_empty, errors='coerce').notna().sum()
                                # 80% 이상이 숫자로 변환 가능하면 숫자형 컬럼으로 간주
                                if numeric_count / len(non_empty) >= 0.8:
                                    is_numeric_candidate = True
                            except Exception:
                                pass
            
            if is_numeric_candidate:
                # 빈 문자열을 NaN으로 변환
                df[col] = df[col].replace('', np.nan)
                # 숫자형으로 변환 시도
                try:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except Exception:
                    # 변환 실패 시 원본 유지하고 빈 문자열로 채움
                    df[col] = df[col].fillna('')
            else:
                # 숫자형이 아닌 컬럼은 빈 문자열로 유지
                df[col] = df[col].fillna('')
        
        return df
    
    def load_all_files(self) -> Dict[str, pd.DataFrame]:
        """모든 파일 로드"""
        files_to_load = {
            'fileformat': self.files_config.fileformat,
            'filestats': self.files_config.filestats,
            # 'fileformatmapping': self.files_config.fileformatmapping,
        }
        
        loaded_data = {}
        for name, path in files_to_load.items():
            # 확장자가 없는 경우 .csv 추가
            if not os.path.splitext(path)[1]:
                path = path + ".csv"

            df = self.load_file(path, name)
            if df is not None:
                # 숫자형 컬럼 처리
                df = self._fix_numeric_columns(df)
                loaded_data[name] = df

        return loaded_data
#-----------------------------------------------------------------------------------------
class DashboardManager:
    """대시보드 관리를 위한 클래스"""
    def __init__(self, yaml_config: Dict[str, Any]):
        self.yaml_config = yaml_config
        self.file_loader = FileLoader(yaml_config)
    
    def display_data_quality_information(self) -> bool:
        """Data Quality Information 대시보드 표시"""
        try:
            st.title(APP_NAME)
            st.markdown(APP_DESC)
            
            loaded_data = self.file_loader.load_all_files() # 모든 파일 로드
           
            # 마스터 통계 표시
            Display_Master_KPIs(loaded_data)

            # 마스터 포맷 상세 표시
            Display_MasterFormat_Detail(loaded_data)

            return True
            
        except Exception as e:
            st.error(f"대시보드 표시 중 오류 발생: {str(e)}")
            return False

#-----------------------------------------------------------------------------------------
class DataQualityInformationApp:
    """Data Quality Information 애플리케이션 메인 클래스"""
    
    def __init__(self):
        self.yaml_config = None
        self.dashboard_manager = None
    
    def initialize(self) -> bool:
        """애플리케이션 초기화"""
        try:
            self.yaml_config = load_yaml_datasense() # YAML 파일 로드
            if self.yaml_config is None:
                st.error("YAML 파일을 로드할 수 없습니다.")
                return False
                       
            self.dashboard_manager = DashboardManager(self.yaml_config) # 대시보드 매니저 초기화
            return True
            
        except Exception as e:
            st.error(f"애플리케이션 초기화 중 오류 발생: {str(e)}")
            return False
    
    def data_quality_information_run(self):
        """애플리케이션 실행"""
        try:
            success = self.dashboard_manager.display_data_quality_information()
                
        except Exception as e:
            st.error(f"애플리케이션 실행 중 오류 발생: {str(e)}")

def main():
    """메인 함수"""
    app = DataQualityInformationApp()
    
    if app.initialize():
        app.data_quality_information_run()
    else:
        st.error("애플리케이션 초기화 실패")

if __name__ == "__main__":
    main()
