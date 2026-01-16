import re
import pandas as pd
import os
import streamlit as st
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import datetime
from pathlib import Path
import sys

import yaml

try:
    from graphviz import Digraph
    GRAPHVIZ_AVAILABLE = True
except ImportError:
    GRAPHVIZ_AVAILABLE = False
    st.warning("Graphviz를 사용할 수 없습니다. Code Relationship Diagram을 생성할 수 없습니다.")

CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# # YAML 파일 로드 함수
# def load_yaml():
#     import yaml
#     import sys
#     # 현재 파일의 상위 디렉토리를 path에 추가
#     # CURRENT_DIR_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#     # sys.path.append(CURRENT_DIR_PATH)
#     yaml_path = PROJECT_ROOT / "DataSense" / "util"
#     yaml_file_name = 'DS_Master.yaml'

#     file_path = yaml_path / yaml_file_name
#     try:
#         with open(file_path, 'r', encoding='utf-8') as f:
#             return yaml.safe_load(f)
#     except FileNotFoundError:  
#         st.error(f"QDQM의 기본 YAML 파일을 찾을 수 없습니다: {file_path}")
#         return None



def load_yaml_datasense():
    """
    DataSense 설정 YAML 파일을 로드하고 프로젝트 루트 경로를 동적으로 설정합니다.
    """
    # 1. 프로젝트 루트 경로 계산 (현재 파일 위치 기준 1단계 상위)
    # 예: QDQM/util/Files_FunctionV20.py -> QDQM
    try:
        current_file_path = Path(__file__).resolve()
        project_root = current_file_path.parents[1]  # util의 부모 = QDQM
        
        # sys.path에 추가하여 모듈 참조 가능하게 설정
        if str(project_root) not in sys.path:
            sys.path.append(str(project_root))
            
        # 2. YAML 경로 설정
        yaml_dir = project_root / "util"
        yaml_file_name = 'DS_00_Main_Config.yaml'
        file_path = yaml_dir / yaml_file_name
        
        # 3. 파일 로드
        if not file_path.exists():
            st.error(f"⚠️ YAML 파일을 찾을 수 없습니다: {file_path}")
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
            if config is None:
                config = {}

            # 4. ROOT_PATH 동적 감지 및 할당
            # 설정이 없거나, 기존 경로가 유효하지 않을 경우 현재 감지된 루트로 갱신
            yaml_root = config.get('ROOT_PATH')
            if not yaml_root or not Path(yaml_root).exists():
                config['ROOT_PATH'] = str(project_root)
            
            return config

    except Exception as e:
        st.error(f"❌ YAML 로드 중 예기치 못한 오류 발생: {str(e)}")
        return None

# YAML 파일 로드 함수
def load_yaml_datasense_old():
    import yaml
    import sys
    from pathlib import Path
    
    # 현재 파일의 상위 디렉토리를 path에 추가  
    CURRENT_DIR_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.append(CURRENT_DIR_PATH)
    
    # Streamlit Cloud 호환: 상대 경로 사용
    # 프로젝트 루트 기준으로 상대 경로 구성
    # project_root = Path(CURRENT_DIR_PATH)  
    yaml_path = PROJECT_ROOT / "DataSense" / "util"
    yaml_file_name = 'DS_Master.yaml'
    
    file_path = yaml_path / yaml_file_name
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
            # ROOT_PATH가 없거나 절대경로인 경우 자동 감지
            if not config.get('ROOT_PATH') or Path(config.get('ROOT_PATH', '')).is_absolute():
                config['ROOT_PATH'] = str(project_root)
            
            return config
    except FileNotFoundError:  
        st.error(f"Data Sense의 YAML 파일을 찾을 수 없습니다: {file_path}")
        return None
    except Exception as e:
        st.error(f"YAML 파일 로드 중 오류 발생: {str(e)}")
        return None
# 기본 페이지 설정
def set_page_config(yaml_file):
    POWERED_BY = "Powered by QLIKER"
    EMAIL = "qliker@kakao.com"
    APP_NAME = "Data Sense"
    APP_KOR_NAME = "데이터 센스"
    APP_VER = "1.0"

    st.set_page_config(
        page_title=APP_NAME,
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.sidebar.header(APP_NAME)
    st.sidebar.markdown("""
        <div style='background-color: #F0F8FF; padding: 10px; border-radius: 10px; margin: 10px 0;'>
        <p style='font-size: 20px; color: #333; line-height: 1.6;'>
            Data has <span style='font-size: 20px; color: #cc3300; font-weight: bold;'> a value.</span><br>
            Data is<span style='font-size: 20px; color: #cc3300; font-weight: bold;'> an asset.</span><br>
            Data shapes <span style='color: #cc3300; font-weight: bold;'> our future.</span>
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.sidebar.markdown("")
    # st.sidebar.markdown(f"<h4>{POWERED_BY}</h4>", unsafe_allow_html=True)
    st.sidebar.markdown(f"<h4>{EMAIL}</h4>", unsafe_allow_html=True)

    return None

# 31_Value Chain Diagram.py 에서 사용하는 함수
def display_valuechain_sample_image():
    from PIL import Image

    CURRENT_DIR = Path(__file__).resolve()
    PROJECT_ROOT = CURRENT_DIR.parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.append(str(PROJECT_ROOT))

    sample_image = "DataSense/DS_Output/valuechain_primary_sample.png"
    filepath = os.path.join(PROJECT_ROOT, sample_image)

    if not os.path.exists(filepath):
        st.error(f"Sample Image 파일이 존재하지 않습니다: {filepath}")
        return False
    st.markdown("#### Value Chain Primary Sample Image")
    image = Image.open(filepath)
    st.image(image, caption="Value Chain Primary Sample Image", width=800)

    sample_image = "DataSense/DS_Output/valuechain_support_sample.png"
    filepath = os.path.join(PROJECT_ROOT, sample_image)

    if not os.path.exists(filepath):
        st.error(f"Sample Image 파일이 존재하지 않습니다: {filepath}")
        return False
    st.markdown("#### Value Chain Support Sample Image")
    image = Image.open(filepath)
    st.image(image, caption="Value Chain Support Sample Image", width=800)
    return True

# 31_Value Chain Diagram.py 에서 사용하는 함수 (현재는 사용하지 않음 - 기본 다이어그램 생성)
def create_default_diagram() -> Digraph:
    from graphviz import Digraph
    """기본 Value Chain 다이어그램 생성"""
    dot = Digraph(format='png')
    dot.attr(rankdir='LR', fontsize='10')

    # Primary Activities
    dot.attr('node', shape='box', style='filled', color='lightblue2')
    dot.node('P0', 'Inbound Logistics\n(수거/접수)\nKPI: 수거율\n시스템: TMS')
    dot.node('P1', 'Operations\n(허브 처리)\nKPI: 자동분류율\n시스템: WMS')
    dot.node('P2', 'Outbound Logistics\n(배송)\nKPI: 배송완료율\n시스템: PDA/모바일')
    dot.node('P3', 'Marketing & Sales\nKPI: 고객유치율\n시스템: CRM')
    dot.node('P4', 'Service\n(CS/반품)\nKPI: 클레임 처리율\n시스템: VOC 시스템')

    # Support Activities
    dot.attr('node', shape='ellipse', style='filled', color='#eef8d2', border='black')
    dot.node('Infra', 'Infrastructure\n(재무/법무)\n시스템: ERP')
    dot.node('HR', 'HR Management\n(인력 운영)\n시스템: HRIS')
    dot.node('Tech', 'Technology\n(TES, 자동화)\n시스템: AI/IoT')
    dot.node('Procure', 'Procurement\n(설비/차량)\n시스템: 자산관리')

    # Edges
    dot.edges([('P0', 'P1'), ('P1', 'P2'), ('P2', 'P3'), ('P3', 'P4')])
    for support in ['Infra', 'HR', 'Tech', 'Procure']:
        for primary in ['P0', 'P1', 'P2', 'P3', 'P4']:
            dot.edge(support, primary, style='dashed', color='lightgrey')

    return dot


def Display_File_KPIs(df, title):
    """ Main KPIs """
    st.markdown(f"### {title}")   
    # CSS 스타일 정의
    # st.markdown("""
    #     <style>
    #     div[data-testid="metric-container"] {
    #         background-color: #FFFFFF;
    #         border: 1px solid #E0E0E0;
    #         padding: 1rem;
    #         border-radius: 10px;
    #         box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    #     }
    #     div[data-testid="metric-container"] > label[data-testid="stMetricLabel"] {
    #         display: flex;
    #         justify-content: center;
    #         color: #404040;
    #         font-weight: 600;
    #     }
    #     div[data-testid="metric-container"] > div[data-testid="stMetricValue"] {
    #         display: flex;
    #         justify-content: center;
    #         font-weight: bold;
    #     }
    #     </style>
    # """, unsafe_allow_html=True)

    # KPI 계산
    file_cnt = len(df['FileName'].unique())
    Column_cnt = df['ColumnCnt'].sum()
    if df['RecordCnt'].sum() < 1000000:
        record_Cnt = df['RecordCnt'].sum()
        record_Cnt_unit = ' 건'
    else:
        record_Cnt = df['RecordCnt'].sum()/1000000
        record_Cnt_unit = ' 백만'

    # file_size = df['FileSize'].sum()
    # file_size_unit = ' Bytes'

    if df['FileSize'].sum() > 1000000:
        file_size = df['FileSize'].sum() / 1000000
        file_size_unit = ' MB'
    else:
        file_size = df['FileSize'].sum()/1000
        file_size_unit = ' KB'

    work_date = df['WorkDate'].unique().max()

    summary = {
        "Total Files #": f"{file_cnt:,}", 
        "Total Columns #": f"{Column_cnt:,}", # Column_cnt,
        "Record #": f"{record_Cnt:,.0f} {record_Cnt_unit}",   # record_Cnt, 
        "File Size": f"{file_size:,.0f} {file_size_unit}",  #file_size,
        "Analyzed Date" : work_date
    }
    
    # 각 메트릭에 대한 색상 정의
    metric_colors = {
        "Total Files #": "#1f77b4",      # 파란색
        "Total Columns #": "#2ca02c",      # 초록색
        "Record #": "#ff7f0e",      # 주황색
        "File Size": "#d62728",       # 빨간색
        "Analyzed Date": "#9467bd"         # 보라색
    }

    # 메트릭 표시
    cols = st.columns(len(summary))
    for col, (key, value) in zip(cols, summary.items()):
        color = metric_colors.get(key, "#0072B2")  # 기본 색상
        col.markdown(f"""
            <div style="text-align: center; padding: 1.2rem; background-color: #FFFFFF; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="color: {color}; font-size: 2em; font-weight: bold;">{value}</div>
                <div style="color: #404040; font-size: 1em; margin-top: 0.5rem;">{key}</div>
            </div>
        """, unsafe_allow_html=True)

    return

# Create Main KPIs
def Display_KPIs(df):   # Old Function
    """ Main KPIs """
    st.markdown("###  품질 점검 파일 정보")   
    # CSS 스타일 정의
    st.markdown("""
        <style>
        div[data-testid="metric-container"] {
            background-color: #FFFFFF;
            border: 1px solid #E0E0E0;
            padding: 1rem;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        div[data-testid="metric-container"] > label[data-testid="stMetricLabel"] {
            display: flex;
            justify-content: center;
            color: #404040;
            font-weight: 600;
        }
        div[data-testid="metric-container"] > div[data-testid="stMetricValue"] {
            display: flex;
            justify-content: center;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)

    # KPI 계산
    file_cnt = len(df['FileName'].unique())
    Column_cnt = df['ColumnCnt'].sum()
    record_Cnt = df['RecordCnt'].sum()/1000000
    file_size = df['FileSize'].sum()/1000000
    work_date = df['WorkDate'].unique().max()
    summary = {
        "Total Files #": f"{file_cnt:,}", 
        "Total Columns #": f"{Column_cnt:,}", # Column_cnt,
        "Record #(백만)": f"{record_Cnt:,.0f}",   # record_Cnt, 
        "File Size(MB)": f"{file_size:,.0f}",  #file_size,
        "Analyzed Date" : work_date
    }
    
    # 각 메트릭에 대한 색상 정의
    metric_colors = {
        "Total Files #": "#1f77b4",      # 파란색
        "Total Columns #": "#2ca02c",      # 초록색
        "Record #(백만)": "#ff7f0e",      # 주황색
        "File Size(MB)": "#d62728",       # 빨간색
        "Working Date": "#9467bd"         # 보라색
    }

    # 메트릭 표시
    cols = st.columns(len(summary))
    for col, (key, value) in zip(cols, summary.items()):
        color = metric_colors.get(key, "#0072B2")  # 기본 색상
        col.markdown(f"""
            <div style="text-align: center; padding: 1.2rem; background-color: #FFFFFF; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="color: {color}; font-size: 2em; font-weight: bold;">{value}</div>
                <div style="color: #404040; font-size: 1em; margin-top: 0.5rem;">{key}</div>
            </div>
        """, unsafe_allow_html=True)

    return

def Files_Basic_Info(df):
    st.markdown("### 파일별 컬럼 수, 파일 크기, 유니크 컬럼 수, Null 컬럼 수 및 분석을 위한 샘플링 정보")

    data = df[['FileName', 'ColumnCnt', 'FileSize', 'RecordCnt', 'SamplingRows', 'IsUnique', 'IsNull']]   
    data.loc[:, 'Sampling(%)'] = df['Sampling(%)'].map(lambda x: f"{x:.1f}%")
    
    st.data_editor(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100), 
            "ColumnCnt": st.column_config.NumberColumn("Columns #", help="컬럼 수"),
            "FileSize": st.column_config.NumberColumn("File Size", help="파일 크기 (bytes)"),
            "RecordCnt": st.column_config.NumberColumn("Row #", help="전체 행 수"),
            "SamplingRows": st.column_config.NumberColumn("Sampling #", help="분석에 사용된 샘플링 행 수"),
            "IsUnique": st.column_config.NumberColumn("Unique Columns", help="유니크 값을 가진 컬럼 수"),
            "IsNull": st.column_config.NumberColumn("Null Columns", help="NULL 값이 포함된 컬럼 수"),
            "Sampling(%)": st.column_config.TextColumn("Sample Ratio(%)", help="전체 데이터 중 샘플링된 비율"),
        }, hide_index=True,   height=600, width=1000, 
        disabled=True
    )  


def Files_Basic_Info_Selection(df):
    st.markdown("#### 점검해야 할 파일들의 정보입니다")
    # 필요한 컬럼만 선택하고 체크박스 컬럼 추가
    data = (df[['FileName', 'RecordCnt', 'ColumnCnt', 'IsNull', 'IsUnique', 
                'UnicodeCnt', 'BelowLCL', 'UpperUCL', 
                'BrokenKoreanCnt', 'ChineseCnt', 'SpecialCnt', 'IsNull']]
            .assign(Check=False))
    
    # 각 행별로 조건 확인하여 주의 이모지 설정
    data['주의'] = ''  # 기본값으로 빈 문자열 설정
    data.loc[(data['UnicodeCnt'] > 0) 
             | (data['BelowLCL'] > 0)
             | (data['UpperUCL'] > 0)
             , '주의'] = '🚨'  # Unicode가 있는 행
   
    # Check와 주의 컬럼을 맨 앞으로 이동
    cols = ['Check', '주의'] + [col for col in data.columns if col not in ['Check', '주의']]
    data = data[cols]

    # 0을 빈 문자열로 변환
    numeric_columns = ['RecordCnt', 'ColumnCnt', 'IsNull', 'IsUnique', 'UnicodeCnt', 'BelowLCL', 
                      'UpperUCL', 'BrokenKoreanCnt', 'ChineseCnt', 'SpecialCnt', 'HasNull']
    # for col in numeric_columns:
    #     data[col] = data[col].apply(lambda x: ' ' if x == 0 else x)

    grouped = st.data_editor(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100), 
            "RecordCnt": st.column_config.NumberColumn("Row #", help="전체 행 수", format="%d"),
            "ColumnCnt": st.column_config.NumberColumn("Columns #", help="컬럼 수", format="%d"),
            "IsNull": st.column_config.NumberColumn("Null #", help="전체 NULL 컬럼 수", format="%d"),
            "IsUnique": st.column_config.NumberColumn("Unique #", help="유니크 컬럼 수", format="%d"),
            "SpecialCnt": st.column_config.NumberColumn("Special", help="특수문자 포함 컬럼 수", format="%d"),
            "UnicodeCnt": st.column_config.NumberColumn("Unicode", help="유니코드 포함 컬럼 수", format="%d"),
            "BrokenKoreanCnt": st.column_config.NumberColumn("Broken Kor", help="한글 깨짐 포함 컬럼 수", format="%d"),
            "ChineseCnt": st.column_config.NumberColumn("ChineseChars", help="한자 포함 컬럼 수", format="%d"),
            "BelowLCL": st.column_config.NumberColumn("LT LCL", help="LCL보다 작은 값 포함 컬럼 수", format="%d"),
            "UpperUCL": st.column_config.NumberColumn("GT UCL", help="UCL보다 큰 값 포함 컬럼 수", format="%d"),
            "HasNull": st.column_config.NumberColumn("Has Null #", help="NULL 포함 컬럼 수", format="%d"),
            "Check": st.column_config.CheckboxColumn("Check", help="Selection", default=False), 
        },
        disabled=["File" , "Columns #", "Row #", "Null #", "Has Unicode", "Has BrokenKor", "Has Chinese", 
                  "Less Than LCL", "Greater Than UCL", "Has Null #"], 
        hide_index=True,
        height=600
    )
    return(grouped.loc[grouped["Check"] == True]["FileName"] )

def Files_Character_Info(df):
    st.write("### 유니코드, 한글미완성, 한자 및 특수문자를 갖고 있는 컬럼 수")
    # data = df
    data = df[['FileName', 'ColumnCnt', 'IsNull', 'UnicodeCnt', 'BrokenKoreanCnt', 'ChineseCnt', 
               'SpecialCnt', 'HasDash', 'HasDot', 'HasBracket', 'HasBlank', 'HasAt']]
    st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100), 
            "ColumnCnt": st.column_config.NumberColumn("Columns #", help="컬럼 수"),
            "IsNull": st.column_config.NumberColumn("Has Null", help="NULL 값이 포함된 컬럼 수"),
            "UnicodeCnt": st.column_config.NumberColumn("Has Unicode", help="Unicode 문자가 포함된 컬럼 수"),
            "BrokenKoreanCnt": st.column_config.NumberColumn("Has Broken Kor", help="미완성 한글 문자가 포함된 컬럼 수"),
            "ChineseCnt": st.column_config.NumberColumn("Has Chinese", help="한자가 포함된 컬럼 수"),
            "SpecialCnt": st.column_config.NumberColumn("Has Special", help="특수문자가 포함된 컬럼 수"),
            "HasDash": st.column_config.NumberColumn("Has Dash", help="대시가 포함된 컬럼 수"),
            "HasDot": st.column_config.NumberColumn("Has Dot", help="점이 포함된 컬럼 수"),
            "HasBracket": st.column_config.NumberColumn("Has Bracket", help="괄호가 포함된 컬럼 수"),
            "HasBlank": st.column_config.NumberColumn("Has Blank", help="공백이 포함된 컬럼 수"),
            "HasAt": st.column_config.NumberColumn("Has At", help="At 기호가 포함된 컬럼 수"),
        }, hide_index=True,   height=600, width=1200
    )  


def Files_Data_Type_Info(df):
    st.write("### 파일별 컬럼의 데이터 속성별 컬럼 수")
    data = df[['FileName', 'ColumnCnt','IsText', 'IsNum', 'Date', 'DateChar', 'TimeChar', 'TimeStamp', 'IsNull', 'CLOB', 'SINGLE VALUE', 'FLAG']]
               
    st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100), 
            "ColumnCnt": st.column_config.NumberColumn("Columns #", help="컬럼 수"),
            "Text": st.column_config.NumberColumn("Text", help="데이터 타입이 텍스트인 컬럼 수"),
            "IsNum": st.column_config.NumberColumn("Number", help="데이터 타입이 숫자인 컬럼 수"),
            "Date": st.column_config.NumberColumn("Date", help="데이터 타입이 날짜인 컬럼 수"),
            "DateChar": st.column_config.NumberColumn("Date(Char)", help="데이터 타입이 문자(날짜)인 컬럼 수"),
            "TimeChar": st.column_config.NumberColumn("Time(Char)", help="데이터 타입이 문자(시간)인 컬럼 수"),
            "TimeStamp": st.column_config.NumberColumn("TimeStamp", help="데이터 타입이 타임스탬프인 컬럼 수"),
            "IsNull": st.column_config.NumberColumn("Null Column", help="NULL 값이 포함된 컬럼 수"),
            'CLOB': st.column_config.NumberColumn("CLOB", help="데이터 타입이 CLOB인 컬럼 수"),
            'SINGLE VALUE': st.column_config.NumberColumn("SINGLE VALUE", help="데이터가 단일값인 컬럼 수"),
            'FLAG': st.column_config.NumberColumn("FLAG", help="데이터가 단일값이면서 FLAG 성격인 컬럼 수"),
        }, hide_index=True,   height=600, width=1000
    )  
 
def Files_Data_Attribute_Info(df):
    st.write("### 데이터에 영문, 숫자, 한글 등을 포함한 컬럼 수")
    data = df[['FileName', 'ColumnCnt', 'IsText', 'HasOnlyAlpha', 
               'HasKor', 'HasOnlyKor', 'HasOnlyNum', 'HasMinus', 
               'NullCnt']]
    st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100), 
            "ColumnCnt": st.column_config.NumberColumn("Columns #", help="컬럼 수"),
            "IsText": st.column_config.NumberColumn("Text Cnt", help="텍스트 컬럼 수"),
            "HasOnlyAlpha": st.column_config.NumberColumn("Only Alpha", help="알파벳만 포함된 컬럼 수"),
            "HasKor": st.column_config.NumberColumn("Has Kor", help="한글이 포함된 컬럼 수"),
            "HasOnlyKor": st.column_config.NumberColumn("Only Kor", help="한글만 포함된 컬럼 수"),
            "HasOnlyNum": st.column_config.NumberColumn("Only Num", help="숫자만 포함된 컬럼 수"),
            "HasMinus": st.column_config.NumberColumn("Has Minus", help="마이너스가 포함된 컬럼 수"),
            "NullCnt": st.column_config.NumberColumn("Null Column", help="NULL 값이 포함된 컬럼 수"),
        }, hide_index=True,   height=600, width=1300
    )  


def Unicode_Columns_Display(df):
    st.write("#### Unicode가 포함된 컬럼 목록")
    data = df[df['UnicodeCnt'] > 0][['FileName', 'No', 'ColumnName', 'ValueCnt', 
                                     'UnicodeCnt', 'UnicodeChars', 'UnicodeOrdValues']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "UnicodeCnt": st.column_config.NumberColumn("Unicode Rows", help="Unicode 행 수", width=40),
            "UnicodeChars": st.column_config.TextColumn("Unicode", help="Unicode 문자", width=250),
            "UnicodeOrdValues": st.column_config.TextColumn("유니코드 정수", help="OrdUnicode 문자 정수", width=250),
        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    return(edited_df)

def Broken_Kor_Columns_Display(df):
    st.write("#### 미완성 한글 문자가 포함된 컬럼 목록")
    data = df[df['BrokenKoreanCnt'] > 0][['FileName', 'No', 'ColumnName', 'ValueCnt', 'BrokenKoreanCnt', 'BrokenKoreanChars']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "BrokenKoreanCnt": st.column_config.NumberColumn("Broken Kor", help="미완성 한글 문자 행 수", width=40),
            "BrokenKoreanChars": st.column_config.TextColumn("미완성 한글", help="미완성 한글 문자", width=250),
        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    return(edited_df)

def Chinese_Columns_Display(df):
    st.write("#### 한자가 포함된 컬럼 목록")
    data = df[df['ChineseCnt'] > 0][['FileName', 'No', 'ColumnName', 'ValueCnt', 'ChineseCnt', 'ChineseChars']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "ChineseCnt": st.column_config.NumberColumn("한자 행 수", help="한자 행 수", width=40),
            "ChineseChars": st.column_config.TextColumn("한자", help="한자 문자", width=250),
        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    return(edited_df)

def BelowLCL_Columns_Display(df):
    st.write("#### 하한선 미만값을 갖고 있는 컬럼 목록")
    data = df[df['BelowLCL'] > 0][['FileName', 'No', 'ColumnName', 'ValueCnt', 'BelowLCL', 'Min', 'Mean', 'StDev', 'LCL']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "BelowLCL": st.column_config.NumberColumn("LT LCL", help="하한선 미만 행 수", width=40),
            "Min": st.column_config.NumberColumn("Min", help="최소값", width=40),
            "Mean": st.column_config.NumberColumn("Avg(Mean)", help="평균값", width=40),
            "StDev": st.column_config.NumberColumn("StdDev", help="표준편차", width=40),
            "LCL": st.column_config.NumberColumn("LCL", help="하한선", width=40),
        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    return(edited_df)

def UpperUCL_Columns_Display(df):
    st.write("#### 상한선 이상값을 갖고 있는 컬럼 목록")
    data = df[df['UpperUCL'] > 0][['FileName', 'No', 'ColumnName', 'ValueCnt', 'UpperUCL', 'Max', 'Mean', 'StDev', 'UCL']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "UpperUCL": st.column_config.NumberColumn("GT UCL", help="상한선 이상 행 수", width=40),
            "Max": st.column_config.NumberColumn("Max", help="최대값", width=40),
            "Mean": st.column_config.NumberColumn("Avg(Mean)", help="평균값", width=40),
            "StDev": st.column_config.NumberColumn("StdDev", help="표준편차", width=40),
            "UCL": st.column_config.NumberColumn("UCL", help="상한선", width=40),
        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    return(edited_df)

def Special_Columns_Display(df):
    st.write("#### 특수문자가 포함된 컬럼 목록")
    data = df[df['SpecialCnt'] > 0][['FileName', 'No', 'ColumnName', 'ValueCnt', 'SpecialCnt']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "SpecialCnt": st.column_config.NumberColumn("Has Special", help="특수문자 행 수", width=40),
            # "Special": st.column_config.TextColumn("특수문자", help="특수문자", width=250),    
        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    return(edited_df)

def Display_DataQuality_KPIs(df):
    """ 품질 점검 지표 표시 """

    st.markdown("""
        <style>
        [data-testid="stMetricValue"] {
            font-size: 18px;
        }
        [data-testid="stMetricLabel"] {
            font-size: 18px;
        }
        [data-testid="stMetricDelta"] {
            font-size: 18px;
        }
        [data-testid="stMetricDelta"] svg {
            display: none;
        }
        .metric-row {
            font-size: 22px;
        }
        .small-font {
            font-size: 22px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Calculate totals
    total_Files = len(df['FileName'].unique())
    total_Columns = df['ColumnCnt'].sum()

    # Define metrics with consistent keys and calculate percentages
    metrics = {
        '유니코드': {
            'Files': len(df[df['UnicodeCnt'] > 0]['FileName'].unique()),
            'Columns': df['UnicodeCnt'].sum(),
            'color': '#FF9800'  # Orange
        },
        '한글미완성': {
            'Files': len(df[df['BrokenKoreanCnt'] > 0]['FileName'].unique()),
            'Columns': df['BrokenKoreanCnt'].sum(),
            'color': '#F44336'  # Red
        },
        '하한선미만': {
            'Files': len(df[df['BelowLCL'] > 0]['FileName'].unique()),
            'Columns': df['BelowLCL'].sum(),
            'color': '#2196F3'  # Blue
        },
        '상한선이상': {
            'Files': len(df[df['UpperUCL'] > 0]['FileName'].unique()),
            'Columns': df['UpperUCL'].sum(),
            'color': '#4CAF50'  # Green
        },
        '참조무결성': {
            'Files': len(df[df['Match_Check'] > 0]['FileName'].unique()),
            'Columns': df['Match_Check'].sum(),
            'color': '#9C27B0'  # Purple
        },
        '일자(문자)점검': {
            'Files': len(df[df['Date_Check'] > 0]['FileName'].unique()),
            'Columns': df['Date_Check'].sum(),
            'color': '#795548'  # Brown
        },
        '길이점검': {
            'Files': len(df[df['Len_Check'] > 0]['FileName'].unique()),
            'Columns': df['Len_Check'].sum(),
            'color': '#607D8B'  # Blue Grey
        },         
        '한자문자': {
            'Files': len(df[df['ChineseCnt'] > 0]['FileName'].unique()),
            'Columns': df['ChineseCnt'].sum(),
            'color': '#F44336'  # Red
        },
        
    }

    # Add percentage calculations
    for key in metrics:
        metrics[key]['Files_pct'] = (metrics[key]['Files'] / total_Files * 100) if total_Files > 0 else 0
        metrics[key]['Columns_pct'] = (metrics[key]['Columns'] / total_Columns * 100) if total_Columns > 0 else 0


    # Create three columns for metrics display
    st.markdown('### 품질 점검 지표')
    cols = st.columns(4)

    # Display metrics in columns with percentages
    for idx, (key, value) in enumerate(metrics.items()):
        col_idx = idx % 4
        with cols[col_idx]:
            st.markdown(f'<div style="padding: 10px; border-radius: 5px; background-color: {value["color"]}20;">', unsafe_allow_html=True)
            st.metric(
                label=key,
                value=f"{value['Files']:,}개 파일 ({value['Files_pct']:.1f}%)",
                delta=f"{value['Columns']:,}개 컬럼 ({value['Columns_pct']:.1f}%)",
                delta_color="off"
            )
            st.markdown('</div>', unsafe_allow_html=True)
    
    return()

def Files_Integrity_Info(df):  # 선택한 파일의 모든 무결성 분석
    st.write("-" * 100)
    st.markdown("### 데이터 품질 점검 결과")
    # 필요한 컬럼만 선택하고 체크박스 컬럼 추가
    data = (df[['FileName', 'RecordCnt', 'ColumnCnt', 'IsNull', 'IsUnique', 
                'UnicodeCnt', 'BelowLCL', 'UpperUCL', 
                'BrokenKoreanCnt', 'ChineseCnt', 'SpecialCnt', 'HasNull', 
                'Match_Total', 'Match_Good', 'Match_Check', 
                'Date_Check', 'Len_Check']]
            .assign(Check=False))
    
    # 각 행별로 조건 확인하여 주의 이모지 설정
    data[['유니코드', '한글미완성', '하한선미만', '상한선이상', '마스터참조점검', 'Date(문자)점검', '길이점검']] = ''
    data.loc[(data['UnicodeCnt'] > 0) , '유니코드'] = data.loc[data['UnicodeCnt'] > 0].apply(lambda x: f"⚠️({x['UnicodeCnt']})", axis=1)
    data.loc[(data['BrokenKoreanCnt'] > 0) , '한글미완성'] = data.loc[data['BrokenKoreanCnt'] > 0].apply(lambda x: f"⚠️({x['BrokenKoreanCnt']})", axis=1)
    data.loc[(data['BelowLCL'] > 0) , '하한선미만'] = data.loc[data['BelowLCL'] > 0].apply(lambda x: f"⚠️({x['BelowLCL']})", axis=1)
    data.loc[(data['UpperUCL'] > 0) , '상한선이상'] = data.loc[data['UpperUCL'] > 0].apply(lambda x: f"⚠️({x['UpperUCL']})", axis=1)
    data.loc[(data['Match_Check'] > 0) , '참조무결성'] = data.loc[data['Match_Check'] > 0].apply(lambda x: f"⚠️({x['Match_Check']})", axis=1)
    data.loc[(data['Date_Check'] > 0) , '일자(문자)점검'] = data.loc[data['Date_Check'] > 0].apply(lambda x: f"⚠️({x['Date_Check']})", axis=1)
    data.loc[(data['Len_Check'] > 0) , '길이점검'] = data.loc[data['Len_Check'] > 0].apply(lambda x: f"⚠️({x['Len_Check']})", axis=1)
    data.loc[(data['UnicodeCnt'] > 0) 
            | (data['BrokenKoreanCnt'] > 0)
            | (data['BelowLCL'] > 0)
            | (data['UpperUCL'] > 0)
            | (data['Match_Check'] > 0)
            | (data['Date_Check'] > 0)
            | (data['Len_Check'] > 0)
            , '주의'] = '🚨'  # 전체 점검

    # Check와 주의 컬럼을 맨 앞으로 이동
    columns = ['Check', '주의', 'FileName', 'RecordCnt', 'ColumnCnt', '유니코드', '한글미완성', '하한선미만', 
               '상한선이상', '참조무결성', '일자(문자)점검', '길이점검', 'HasNull'] 

    grouped = st.data_editor(
        data[columns],
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100), 
            "RecordCnt": st.column_config.NumberColumn("Row #", help="전체 행 수"),
            "ColumnCnt": st.column_config.NumberColumn("Columns #", help="컬럼 수"),
            "HasNull": st.column_config.NumberColumn("Null #", help="NULL 컬럼 수"),
            "Null(%)": st.column_config.NumberColumn("Null(%)", help="NULL 비율", width=100),
            "유니코드": st.column_config.TextColumn("유니코드", help="유니코드 포함 컬럼 수"),
            "한글미완성": st.column_config.TextColumn("한글미완성", help="한글미완성 포함 컬럼 수"),
            "하한선미만": st.column_config.TextColumn("하한선미만", help="하한선미만 포함 컬럼 수"),
            "상한선이상": st.column_config.TextColumn("상한선이상", help="상한선이상 포함 컬럼 수"),
            "참조무결성": st.column_config.TextColumn("참조무결성", help="마스터 참조 점검 컬럼 수"),
            "일자(문자)점검": st.column_config.TextColumn("일자(문자)점검", help="일자(문자)점검 컬럼 수"),
            "길이점검": st.column_config.TextColumn("길이점검", help="길이점검 컬럼 수"),
            "Check": st.column_config.CheckboxColumn("Check", help="Selection", default=False), 
        },
        disabled=["File" , "Columns #", "Row #", "Null #", "Has Unicode", "Has BrokenKor", "Has Chinese", 
                  "Less Than LCL", "Greater Than UCL", "Has Null #"], 
        hide_index=True,
        height=600
    )
  
    checked_files = pd.DataFrame(grouped)[lambda x: x["Check"]]["FileName"].tolist()
    st.write("주의 이모지는 점검해야할 컬럼이 있음을 의미합니다. 괄호 안의 숫자는 점검해야할 컬럼 수를 의미합니다.")
    if len(checked_files) == 0:
        st.markdown("\n##### 파일을 선택하세요.")  


    # 체크된 파일명만 리스트로 반환
    return checked_files

def Referential_Integrity_Display(df):
    st.markdown("#### 참조무결성 점검 리스트")

    data = df[df['Match_Check'] > 0][['FileName', 'No', 'ColumnName', 'RecordCnt', 'ValueCnt', 'NullCnt', 'Master', 
                'Matched', 'Matched(%)', 'Tolerance1']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "RowCnt": st.column_config.NumberColumn("행수", help="전체 행 수", width=40),
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "NullCnt": st.column_config.NumberColumn("NULL", help="NULL 행수", width=40),
            "Master": st.column_config.TextColumn("마스터", help="Master 컬럼", width=100),  
            "Matched": st.column_config.NumberColumn("매칭 #", help="매칭된 행 수", width=40),   
            "Matched(%)": st.column_config.NumberColumn("매칭율(%)", help="매칭 비율", width=30),
            "Tolerance1": st.column_config.NumberColumn("허용치(%)", help="허용기준", width=30),
        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    # st.markdown("\n##### 참조된 컬럼의 값이 마스터 파일에 존재하지 않습니다. (참조무결성)")

    return(edited_df)

def Date_Integrity_Display(df):
    st.markdown("#### 일자(문자) 컬럼 점검 리스트")
    data = df[df['Date_Check'] > 0][['FileName', 'No', 'ColumnName', 'DetailDataType', 'RecordCnt', 'ValueCnt', 
            'NullCnt', 'Master', 'Matched', 'Matched(%)', 'Tolerance1']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "DetailDataType": st.column_config.TextColumn("Data Type", help="Data Type", width=100),
            "RowCnt": st.column_config.NumberColumn("행수", help="전체 행 수", width=40),
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "NullCnt": st.column_config.NumberColumn("NULL", help="NULL 행수", width=40),
            "Master": st.column_config.TextColumn("마스터", help="Master 컬럼", width=100),  
            "Matched": st.column_config.NumberColumn("매칭 #", help="매칭된 행 수", width=40),   
            "Matched(%)": st.column_config.NumberColumn("매칭율(%)", help="매칭 비율", width=30),
            "Tolerance1": st.column_config.NumberColumn("허용치(%)", help="허용기준", width=30),
        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    st.markdown("\n##### 데이터 중 날짜규칙에 위배된 데이터가 존재합니다. (ex:20240230, 99999999 등) ")
    return(edited_df)

def Data_Length_Integrity_Display(df):
    st.markdown("#### 데이터 길이 점검 리스트")

    st.write(df)
    data = df[df['Len_Check'] > 0][['FileName', 'No', 'ColumnName', 'DataType','RecordCnt', 'ValueCnt',
             'MasterCode', 'LenMode', 'LenMax']]
    edited_df = st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "DataType": st.column_config.TextColumn("Data Type", help="Data Type", width=100),
            "RowCnt": st.column_config.NumberColumn("행수", help="전체 행 수", width=40),
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수", width=40),
            "MasterCode": st.column_config.TextColumn("마스터", help="Master 컬럼", width=100),  
            "LenMode": st.column_config.NumberColumn("길이 최빈값", help="Len Mode", width=40),
            "LenMax": st.column_config.NumberColumn("길이 최대값", help="Len Max", width=40),


        }, 
        hide_index=True,   
        height=400, 
        width=1200,
    )
    st.markdown("\n##### LenMax(데이터의 최대길이) > Len Mode(빈도가 가장 높은 길이) * 2 보다 큰 경우 리스트를 작성합니다.")
    return(edited_df)

def File_Column_Total_Integrity_Display(Column_df, file):  
    # Filter data for the specific file
    file_data = Column_df[Column_df['FileName'] == file].copy()

    # 필요한 열이 모두 있는지 확인
    required_columns = ['Match_Check', 'ValueCnt', 'Matched']
    missing_columns = [col for col in required_columns if col not in file_data.columns]

    if missing_columns:
        # 필요한 열이 없을 경우 처리
        st.error(f"다음 열이 누락되었습니다: {', '.join(missing_columns)}")
        return

    # 숫자로 변환할 수 없는 값이 있는지 확인하고 처리
    for col in required_columns:
        file_data[col] = pd.to_numeric(file_data[col], errors='coerce').fillna(0).astype(int)

    # '참조 무결성 컬럼/행' 계산
    referential_integrity = (
        f"{len(file_data[file_data['Match_Check'] > 0])} / "
        f"{int(file_data[file_data['Match_Check'] > 0]['ValueCnt'].sum() - file_data[file_data['Match_Check'] > 0]['Matched'].sum())}"
    )

    file_data.loc[(file_data['UnicodeCnt'] > 0) 
        | (file_data['BrokenKoreanCnt'] > 0)
        | (file_data['BelowLCL'] > 0)
        | (file_data['UpperUCL'] > 0)
        | (file_data['Match_Check'] > 0)
        | (file_data['Date_Check'] > 0)
        | (file_data['Len_Check'] > 0)
        , '주의'] = '🚨'  # 전체 점검
    
    file_data['Null(%)'] = pd.to_numeric(file_data['Null(%)'], errors='coerce')
    # Create a summary of integrity issues
    integrity_summary = {
        '컬럼 수': int(file_data['No'].max() if not file_data.empty else 0),
        'Record 수': f"{int(file_data['RecordCnt'].max() if not file_data.empty else 0):,}",  # Added comma formatting
        'NULL 컬럼 수': len(file_data[file_data['Null(%)'] == 100]),
        '점검 컬럼 수': len(file_data[file_data['주의'] == '🚨']),
        '유니코드 컬럼/행': f"{len(file_data[file_data['UnicodeCnt'] > 0])} / {int(file_data['UnicodeCnt'].sum())}",
        '미완성 한글 컬럼/행': f"{len(file_data[file_data['BrokenKoreanCnt'] > 0])} / {int(file_data['BrokenKoreanCnt'].sum())}",     
        '하한선 미만 컬럼/행': f"{len(file_data[file_data['BelowLCL'] > 0])} / {int(file_data['BelowLCL'].sum())}", 
        '상한선 이상 컬럼/행': f"{len(file_data[file_data['UpperUCL'] > 0])} / {int(file_data['UpperUCL'].sum())}",
        '마스터 참조 컬럼/참조율(%)': referential_integrity,
        '마스터 참조 적합': f"{len(file_data[file_data['Match_Good'] > 0])} / {(file_data['Match_Good'].sum() / len(file_data[file_data['Match_Total'] > 0]) * 100 if file_data['No'].max() > 0 else 0):.1f}%",
        '참조 무결성 컬럼/행': f"{len(file_data[file_data['Match_Check'] > 0])} / {int(file_data[file_data['Match_Check'] > 0]['ValueCnt'].sum() - file_data[file_data['Match_Check'] > 0]['Matched'].sum())}",
        '일자(숫자) 점검 컬럼/행': f"{len(file_data[file_data['Date_Check'] > 0])} / {int(file_data[file_data['Date_Check'] > 0]['ValueCnt'].sum() - file_data[file_data['Date_Check'] > 0]['Matched'].sum())}",
        '길이 점검 컬럼': int(file_data['Len_Check'].sum() if not file_data.empty else 0),   
        '한자 포함 컬럼/행': f"{len(file_data[file_data['ChineseCnt'] > 0])} / {int(file_data['ChineseCnt'].sum()):,}", 
        '특수문자 포함 컬럼/행': f"{len(file_data[file_data['SpecialCnt'] > 0])} / {int(file_data['SpecialCnt'].sum()):,}",    
    }
    
    # Display summary metrics in columns
    # st.markdown(f" #### [ {file} ] 파일 상세 정보")
    cols = st.columns(4)
    for idx, (key, value) in enumerate(integrity_summary.items()):
        with cols[idx % 4]:
            st.metric(label=key, value=value)

    # Display detailed Column information
    if not file_data.empty:
        # Select relevant columns for display
        display_cols = ['No', 'ColumnName', 'DataType', 'ValueCnt',
                        'MasterCode',  'Matched', 'Matched(%)', 'Tolerance1', 
                       'UnicodeCnt', 'BelowLCL', 'UpperUCL', 
                       'BrokenKoreanCnt', 'ChineseCnt', 'SpecialCnt', 'NullCnt', 
                       'Match_Total', 'Match_Good', 'Match_Check', 
                       'Date_Check', 'Len_Check',
                       'Unicode', 'BrokenKorean', 'Chinese',
                       'Special']
        
        # Ensure all required columns exist
        for col in display_cols:
            if col not in file_data.columns:
                file_data[col] = 0
        
        data = file_data[display_cols].copy()
        
        # Convert numeric columns to integers
        for col in ['Match_Total', 'Match_Good', 'ColumnNo']:
            if col in data.columns:
                # 숫자로 변환할 수 없는 값이 있는지 확인
                data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0).astype(int)
        
        # 각 행별로 조건 확인하여 주의 이모지 설정
        data[['주의', '유니코드', '미완성 한글', '하한선 미만', '상한선 이상', '참조무결성', '일자(숫자) 점검', '길이 점검']] = ''
        data.loc[(data['UnicodeCnt'] > 0) , '유니코드'] = data.loc[data['UnicodeCnt'] > 0].apply(lambda x: f"⚠️({x['UnicodeCnt']})", axis=1)
        data.loc[(data['BrokenKoreanCnt'] > 0) , '미완성 한글'] = data.loc[data['BrokenKoreanCnt'] > 0].apply(lambda x: f"⚠️({x['BrokenKoreanCnt']})", axis=1)
        data.loc[(data['BelowLCL'] > 0) , '하한선 미만'] = data.loc[data['BelowLCL'] > 0].apply(lambda x: f"⚠️({x['BelowLCL']})", axis=1)
        data.loc[(data['UpperUCL'] > 0) , '상한선 이상'] = data.loc[data['UpperUCL'] > 0].apply(lambda x: f"⚠️({x['UpperUCL']})", axis=1)
        data.loc[(data['Match_Check'] > 0) , '참조무결성'] = data.loc[data['Match_Check'] > 0].apply(lambda x: f"⚠️({x['ValueCnt']-x['Matched']})", axis=1)
        data.loc[(data['Date_Check'] > 0) , '일자(숫자) 점검'] = data.loc[data['Date_Check'] > 0].apply(lambda x: f"⚠️({x['ValueCnt']-x['Matched']})", axis=1)
        data.loc[(data['Len_Check'] > 0) , '길이 점검'] = data.loc[data['Len_Check'] > 0].apply(lambda x: f"⚠️", axis=1)
        data.loc[(data['UnicodeCnt'] > 0) 
                | (data['BrokenKoreanCnt'] > 0)
                | (data['BelowLCL'] > 0)
                | (data['UpperUCL'] > 0)
                | (data['Match_Check'] > 0)
                | (data['Date_Check'] > 0)
                | (data['Len_Check'] > 0)
                , '주의'] = '🚨'  # 전체 점검
        
        # 컬럼 리스트 수정
        columns = ['주의', 'No', 'ColumnName', 'DataType', 'ValueCnt', '유니코드', 
                '미완성 한글', '하한선 미만', '상한선 이상', '참조무결성', '일자(숫자) 점검', 
                '길이 점검', 'MasterCode', 'Matched', 'Matched(%)', 'Tolerance1', 'ChineseCnt', 'SpecialCnt']
                
        data = data[columns].copy()
        
        # Add visual indicators for issues
        st.dataframe(
            data,
            column_config={
                "No": st.column_config.NumberColumn("No", help="Column No", width=50),
                "ColumnName": st.column_config.TextColumn("컬럼명", help="Column Name", width=130),
                "DataType": st.column_config.TextColumn("데이터타입", help="Data Type", width=80), 
                "ValueCnt": st.column_config.NumberColumn("데이터수", help="Value Count", width=80),
                "MasterCode": st.column_config.TextColumn("마스터", help="Data Type", width=130),
                "Matched": st.column_config.NumberColumn("Matched", help="Len Mode", width=80),
                "Matched(%)": st.column_config.NumberColumn("Matched(%)", help="Len Max", width=80),
                "Tolerance1": st.column_config.NumberColumn("허용치(%)", help="Len Max", width=80),
                "ChineseCnt": st.column_config.NumberColumn("한자", help="한자", width=80),
                "SpecialCnt": st.column_config.NumberColumn("특수문자", help="특수문자", width=80),
            },
            hide_index=True,
            height=500, width=1500
        )
    else:
        st.warning(f"No data available for File: {file}")

    return()

def File_Total_Integrity_Display(Column_df):
    # Get unique filenames and ensure it's a list
    file_names = Column_df['FileName'].unique().tolist() if 'FileName' in Column_df.columns else []
    
    if not file_names:
        st.warning("분석할 파일이 없습니다.")
        return
    
    st.markdown(f"#### 컬럼별 상세정보 입니다.")
    # Create tabs for each file
    tabs = st.tabs(file_names)
    
    # Display each file's data in its respective tab
    for idx, file in enumerate(file_names):
        with tabs[idx]:
            File_Column_Total_Integrity_Display(Column_df, file)
    return


# def Unicode_Columns_Display_Detail(df, CURRENT_DIR_PATH, QDQM_ver):
#     st.write("#### 유니코드가 포함된 레코드")
#     file_name = df['FileName'].unique()
#     dfs = [] # 빈 데이터프레임 리스트 생성

#     for file in file_name:  # 각 파일에서 데이터를 읽어서 리스트에 추가
#         unicode_file = CURRENT_DIR_PATH+'/output/detail/'+file+'_Unicode_File.csv'
#         if not os.path.exists(unicode_file):
#             continue
#         df = pd.read_csv(unicode_file) 
#         if df is not None and not df.empty:
#             dfs.append(df)
    
#     if dfs: # 데이터프레임이 있는 경우에만 concat 실행
#         result_df = pd.concat(dfs, ignore_index=True)
#         display_df = result_df[['FileName', 'ColumnName', 'RecNo', 'Unicode', 'OrdUnicode', 'ColumnValue']]
#         st.dataframe(display_df, hide_index=True, height=500, width=1000)
#     else:
#         st.warning("유니코드 상세 데이터가 없습니다.")
#     return

# def Broken_Kor_Columns_Display_Detail(df, CURRENT_DIR_PATH, QDQM_ver):
#     st.write("#### 미완성 한글 문자가 포함된 레코드")
#     file_name = df['FileName'].unique()
#     dfs = [] # 빈 데이터프레임 리스트 생성
    
#     for file in file_name:  # 각 파일에서 데이터를 읽어서 리스트에 추가
#         broken_kor_file = CURRENT_DIR_PATH+'/output/detail/'+file+'_Broken_Kor_File.csv'
#         if not os.path.exists(broken_kor_file):
#             continue
#         df = pd.read_csv(broken_kor_file) 
#         if df is not None and not df.empty:
#             dfs.append(df)
    
#     if dfs: # 데이터프레임이 있는 경우에만 concat 실행
#         result_df = pd.concat(dfs, ignore_index=True)
#         display_df = result_df[['FileName', 'ColumnName', 'RecNo', 'BrokenKorean', 'ColumnValue']]
#         st.dataframe(display_df, hide_index=True, height=500, width=1000)
#     else:
#         st.warning("미완성 한글 문자가 포함된 파일이 없습니다.")
#     return

# def Chinese_Columns_Display_Detail(df, CURRENT_DIR_PATH, QDQM_ver):
#     st.write("#### 한자가 포함된 레코드")
#     file_name = df['FileName'].unique()
#     dfs = [] # 빈 데이터프레임 리스트 생성
    
#     for file in file_name:  # 각 파일에서 데이터를 읽어서 리스트에 추가
#         chinese_file = CURRENT_DIR_PATH+'/output/detail/'+file+'_Chinese_File.csv'
#         if not os.path.exists(chinese_file):
#             continue
#         df = pd.read_csv(chinese_file) 
#         if df is not None and not df.empty:
#             dfs.append(df)
    
#     if dfs: # 데이터프레임이 있는 경우에만 concat 실행
#         result_df = pd.concat(dfs, ignore_index=True)
#         display_df = result_df[['FileName', 'ColumnName', 'RecNo', 'Chinese', 'ColumnValue']]
#         st.dataframe(display_df, hide_index=True, height=500, width=1000)
#     else:
#         st.warning("한자가 포함된 파일이 없습니다.")
#     return

# def Special_Columns_Display_Detail(df, CURRENT_DIR_PATH, QDQM_ver):
#     st.write("#### 특수문자가 포함된 레코드")
#     file_name = df['FileName'].unique()
#     dfs = [] # 빈 데이터프레임 리스트 생성
    
#     for file in file_name:  # 각 파일에서 데이터를 읽어서 리스트에 추가
#         special_file = CURRENT_DIR_PATH+'/output/detail/'+file+'_Special_File.csv'
#         if not os.path.exists(special_file):
#             continue
#         df = pd.read_csv(special_file) 
#         if df is not None and not df.empty:
#             dfs.append(df)
    
#     if dfs: # 데이터프레임이 있는 경우에만 concat 실행
#         result_df = pd.concat(dfs, ignore_index=True)
#         display_df = result_df[['FileName', 'ColumnName', 'RecNo', 'Special', 'ColumnValue']]
#         st.dataframe(display_df, hide_index=True, height=500, width=1000)
#     else:
#         st.warning("특수문자가 포함된 파일이 없습니다.")
#     return


def Date_Columns_Display_Detail(df, CURRENT_DIR_PATH, QDQM_ver):
    st.write("#### 일자(문자)컬럼이 포함된 레코드")
    file_name = df['FileName'].unique()
    dfs = [] # 빈 데이터프레임 리스트 생성
    
    for file in file_name:  # 각 파일에서 데이터를 읽어서 리스트에 추가
        date_file = CURRENT_DIR_PATH+'/output/detail/'+file+'_DateChar검증.csv'
        if not os.path.exists(date_file):
            continue
        df = pd.read_csv(date_file) 
        if df is not None and not df.empty:
            dfs.append(df)
    
    if dfs: # 데이터프레임이 있는 경우에만 concat 실행
        result_df = pd.concat(dfs, ignore_index=True)
        display_df = result_df[['FileName', 'ColumnName', 'RecNo', 'DateChar']]
        st.dataframe(display_df, hide_index=True, height=500, width=1000)
    else:
        st.warning("일자(문자)가 포함된 파일이 없습니다.")
    return

def Numeric_Columns_Statistics(df): 
    st.write("### 숫자 컬럼 통계")
    st.markdown("기본 통계값 및 하한값 미만, 상한값 초과 행수와 주의 마크를 표시합니다.")

    df['주의'] = ''  # 기본값으로 빈 문자열 설정
    df.loc[(df['BelowLCL'] > 0) | (df['UpperUCL'] > 0), '주의'] = '🚨'  # 변동형 문자열 컬럼    

    data = df[df['MasterCode']=='Measure'][['FileName', 'No', 'ColumnName', 'DataType', 'RecordCnt', 'ValueCnt',
                                          'Min', 'StDev', '25%', '50%', '75%', 'Max', 'Mean', 
                                          'LCL' , 'UCL', '주의', 'BelowLCL', 'UpperUCL', 
                                          'OracleType', 'HasMinus', 'NullCnt',
                                          ]]
    # 각 행별로 조건 확인하여 주의 이모지 설정
    st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "DataType": st.column_config.TextColumn("데이터타입", help="데이터타입", width=100),
            "RowCnt": st.column_config.NumberColumn("행수", help="전체 행 수"),
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수"),

            "Min": st.column_config.NumberColumn("Min", help="최소값"), 
            "StDev": st.column_config.NumberColumn("StDev", help="표준편차"),
            "25%": st.column_config.NumberColumn("25%", help="1분위수", format="%.2f"),  
            "50%": st.column_config.NumberColumn("50%", help="중앙값", format="%.2f"),
            "75%": st.column_config.NumberColumn("75%", help="3분위수", format="%.2f"),
            "Max": st.column_config.NumberColumn("Max", help="최대값", format="%.2f"),
            "Mean": st.column_config.NumberColumn("Avg", help="평균값", format="%.2f"),
            "LCL": st.column_config.NumberColumn("LCL", help="하한값"),
            "UCL": st.column_config.NumberColumn("UCL", help="상한값"),
            "HasMinus": st.column_config.NumberColumn("Minus #", help="음수인 행수"),
            "OracleType": st.column_config.NumberColumn("Precision", help="소숫점이하 길이"),
            "BelowLCL": st.column_config.NumberColumn("LT LCL", help="LCL 미만 행수"),
            "UpperUCL": st.column_config.NumberColumn("GT UCL", help="UCL 초과 행수"),
            "NullCnt": st.column_config.NumberColumn("Null #", help="NULL이 있는 행수"),
            "주의": st.column_config.TextColumn("주의", help="주의 마크"),
        },
        hide_index=True,
        height=400,
        width=1500
    )

    if data['BelowLCL'].any() > 0 or data['UpperUCL'].any() > 0:
        st.markdown("""
UCL이란 관리 상한(Upper Control Limit), LCL이란 관리 하한(Lower Control Limit)을 의미합니다.\n
UCL과 LCL은 보통 중앙선으로부터 상하로 3시그마 (표준편차의 3배) 위치합니다. \n
99.7300%의 데이터값이 UCL과 LCL 사이에 있게 됩니다. 벗어난 값을 outlier이라 합니다.\n
극단치(outlier) : 통계적 자료분석의 결과를 왜곡시키거나, 자료 분석의 적절성을 위협하는 변수값 또는 사례를 말한다. 
기술통계학적 기법에서는 분포의 집중경향치의 값을 왜곡시키거나, 상관계수 추정치의 값을 왜곡시키는 개체 또는 변수의 값을 의미한다. 
추리통계에서는 모수추정치의 값을 왜곡시키는 개체 또는 변수의 값이며, 통상적으로 표준화된 잔차의 분석에서 개체의 변수값이 0(평균)으로부터 ±3 표준편차밖에 위치하는 사례나, 일반적인 경향에서 벗어나는 사례를 지칭한다.\n
[네이버 지식백과] 극단치 [極端値, outlier]
                    """, unsafe_allow_html=True)
    return()

def Columns_Value_Length_Statistics(df): 
    st.write("### 컬럼 값 및 길이 통계")
    st.markdown("각 컬럼의 값과 길이에 대한 통계정보를 제공합니다. 길이 정보를 기준으로 고정형, 변동형 및 최소, 최대, 평균, 최빈값 정보를 제공합니다. \n")
    
    data = df[['FileName', 'No', 'ColumnName', 'DataType', 'ValueCnt', 'LenCnt', 
               'LenMin', 'LenMax', 'LenAvg', 'LenMode', 'OracleType', 'MinString', 'MaxString', 'ModeString']]
    # 각 행별로 조건 확인하여 주의 이모지 설정
    data['주의'] = ''  # 기본값으로 빈 문자열 설정
    data.loc[(data['DataType'] == 'NumChar') & (data['LenMax'] > data['LenMode']*2), '주의'] = '🚨'  # 변동형 문자열 컬럼

    st.dataframe(
        data,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "DataType": st.column_config.TextColumn("Data Type", help="데이터 유형"),
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수"),
            "LenCnt": st.column_config.NumberColumn("Len #", help="길이 종류"),
            "LenMin": st.column_config.NumberColumn("Len Min", help="길이 최소"),
            "LenMax": st.column_config.NumberColumn("Len Max", help="길이 최대"),
            "LenAvg": st.column_config.NumberColumn("Len Avg", help="길이 평균"),
            "LenMode": st.column_config.NumberColumn("Len Mode", help="길이 최빈값"),
            "OracleType": st.column_config.TextColumn("OracleType", help="소숫점이하 길이"),
            "MinString": st.column_config.TextColumn("Min String", help="최소 문자열"),
            "MaxString": st.column_config.TextColumn("Max String", help="최대 문자열"),
            "ModeString": st.column_config.TextColumn("Mode(최빈값)", help="최빈값"),
        },
        hide_index=True,
        height=600,
        width=1500
    )

    st.markdown("주의 마크가 표시된 컬럼는 최대 길이 > 길이 최빈값 * 2 인 경우를 의미합니다.")
    
def Columns_Format_Statistics(df):
    st.write("### 데이터 포맷 통계")
    # 컬럼명 재설정
    df = df[['FileName', 'No', 'ColumnName', 'DataType', 'MasterCode', 'ValueCnt', 'FormatCnt', 
            'Format', 'FormatValue', 'Format(%)', 'Format2nd', 'Format2ndValue', 
            'Format3rd', 'Format3rdValue']]

    st.dataframe(
        df,
        column_config={
            "FileName": st.column_config.TextColumn("파일명", help="파일명", width=100),  
            "No": st.column_config.TextColumn("No ", help="컬럼번호", width=10),  
            "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=100), 
            "DataType": st.column_config.TextColumn("Data Type", help="데이터 유형", width=60),
            "MasterCode": st.column_config.TextColumn("마스터", help="마스터 컬럼", width=100),
            "ValueCnt": st.column_config.NumberColumn("데이타 수", help="값이 있는 행수"),
            "FormatCnt": st.column_config.NumberColumn("포맷종류", help="포맷 종류", width=50),
            "Format": st.column_config.TextColumn("포맷", help="포맷", width=100),
            "FormatValue": st.column_config.NumberColumn("포맷 값", help="포맷 값", width=50),
            "Format(%)": st.column_config.NumberColumn("포맷 값", help="포맷 값", width=50),
            "Format2nd": st.column_config.TextColumn("포맷 2", help="포맷 2", width=100),
            "Format2ndValue": st.column_config.NumberColumn("포맷 값 2", help="포맷 값 2", width=50),
            "Format3rd": st.column_config.TextColumn("포맷 3", help="포맷 3", width=100),
            "Format3rdValue": st.column_config.NumberColumn("포맷 값 3", help="포맷 값 3", width=50),
        },
        hide_index=True,
        height=500,
        width=1500
    )
    return()