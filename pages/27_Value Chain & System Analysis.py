# -------------------------------------------------
# 25_Value Chain & System Definition.py 에서 입력된 내용을 분석
# 2025.12.26 Qliker 
# -------------------------------------------------
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

from util.Display import create_metric_card # KPI 메트릭 표시 함수
# -------------------------------------------------------------------
# 3. 필수 라이브러리 import
# -------------------------------------------------------------------
import streamlit as st
import pandas as pd
import plotly.express as px
import os
from pathlib import Path


SOLUTION_NAME = "Value Chain & System Analysis"
SOLUTION_KOR_NAME = "Value Chain & System Analysis"
APP_NAME = "Value Chain & System Analysis"
APP_DESC = "###### Value Chain & System를 기반으로 각 파일들에 대한 통계 정보입니다.  "

from util.Files_FunctionV20 import load_yaml_datasense, set_page_config
set_page_config(APP_NAME)

# -------------------------------------------------
# 3. Streamlit 페이지 설정
# ------------------------------------------------- 
# 경로 설정 (Pathlib 활용)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = PROJECT_ROOT
OUTPUT_DIR = BASE_PATH / "DS_Output"
VC_FILE = OUTPUT_DIR / "DS_ValueChain.csv"
SYS_FILE = OUTPUT_DIR / "DS_System.csv"
VC_SYS_FILE = OUTPUT_DIR / "DS_ValueChain_System_File.csv"
MAPPING_FILE = OUTPUT_DIR / "CodeMapping.csv"

# -------------------------------------------------
# 4. 데이터 로드
# ------------------------------------------------- 
# @st.cache_data
def load_data(file_path):
    """파일을 로드합니다. 파일이 없으면 None을 반환합니다."""
    if not os.path.exists(file_path):
        return None
    try:
        return pd.read_csv(file_path)
    except Exception as e:
        st.error(f"파일 로드 실패: {file_path}, 오류: {str(e)}")
        return None

def get_file_summary(file_names, df_mapping):
    """선택된 파일 리스트에 대해 FileName, ColumnCnt, PK List를 추출"""
    if df_mapping is None or len(file_names) == 0:
        return pd.DataFrame(columns=['FileName', 'ColumnCnt', 'PK_List'])
    
    relevant_mapping = df_mapping[df_mapping['FileName'].isin(file_names)]
    summary = []
    for f_name in file_names:
        f_data = relevant_mapping[relevant_mapping['FileName'] == f_name]
        col_cnt = len(f_data)
        
        # PK 컬럼 추출 (PK 값이 1인 컬럼들)
        pk_str = "-"
        if 'PK' in f_data.columns:
            pk_cols = f_data[f_data['PK'].astype(str).str.contains('1', na=False)]['ColumnName'].tolist()
            if pk_cols:
                pk_str = ", ".join(pk_cols)
            
        summary.append({
            'FileName': f_name,
            'ColumnCnt': col_cnt,
            'PK_List': pk_str
        })
    
    return pd.DataFrame(summary)

def load_data_validation():
    """ 필요한 파일을 로드하고 전처리합니다. """
    # 파일 존재 여부 먼저 확인
    missing_files = []
    if not os.path.exists(VC_FILE):
        missing_files.append(f"VC_FILE: {VC_FILE}")
    if not os.path.exists(SYS_FILE):
        missing_files.append(f"SYS_FILE: {SYS_FILE}")
    if not os.path.exists(VC_SYS_FILE):
        missing_files.append(f"VC_SYS_FILE: {VC_SYS_FILE}")
    if not os.path.exists(MAPPING_FILE):
        missing_files.append(f"MAPPING_FILE: {MAPPING_FILE}")
    
    if missing_files:
        st.error("다음 파일들을 찾을 수 없습니다:")
        for file_info in missing_files:
            st.error(f"  - {file_info}")
        return None, None
    
    # 파일 로드
    df_vc = load_data(VC_FILE)
    df_sys = load_data(SYS_FILE)
    df_vc_sys = load_data(VC_SYS_FILE)
    df_mapping = load_data(MAPPING_FILE)

    # 로드 결과 확인
    failed_files = []
    if df_vc is None:
        failed_files.append(f"VC_FILE: {VC_FILE}")
    if df_sys is None:
        failed_files.append(f"SYS_FILE: {SYS_FILE}")
    if df_vc_sys is None:
        failed_files.append(f"VC_SYS_FILE: {VC_SYS_FILE}")
    if df_mapping is None:
        failed_files.append(f"MAPPING_FILE: {MAPPING_FILE}")
    
    if failed_files:
        st.error("다음 파일들을 로드할 수 없습니다:")
        for file_info in failed_files:
            st.error(f"  - {file_info}")
        return None, None, None, None

    df_vc_sys = pd.merge(df_vc_sys, df_vc, on=['Industry', 'Activity'], how='left')
    df_vc_sys = pd.merge(df_vc_sys, df_sys, on=['Industry', 'System'], how='left')
    df_vc_sys = df_vc_sys.dropna(subset=['Activity', 'System'])
    df_vc_sys = df_vc_sys[(df_vc_sys['Activity'] != 'Unknown') & (df_vc_sys['System'] != 'Unknown')]
    df_vc_sys = df_vc_sys.sort_values(['Activity_Seq', 'System_Seq'], ascending=True)

    return df_vc, df_sys, df_vc_sys, df_mapping

def select_industry(df_vc, df_sys, df_vc_sys):
    
    col_sel1, col_sel2 = st.columns([1, 1])
    with col_sel1:
        st.header("🏢 Industry Selection")

    with col_sel2:
        industries = sorted(df_vc_sys['Industry'].unique())
        selected_industry = st.selectbox("분석할 산업군을 선택하세요", industries)
        df_ind = df_vc_sys[df_vc_sys['Industry'] == selected_industry]
        df_sys = df_sys[df_sys['Industry'] == selected_industry]
        df_vc = df_vc[df_vc['Industry'] == selected_industry]

    if df_ind is not None:
        summary = {
            "Activity #": len(df_vc['Activity'].unique()),
            "System #": len(df_sys['System'].unique()),
            "File #": len(df_ind['FileName'].unique())
        }

        # 각 메트릭에 대한 색상 정의
        metric_colors = {
            "Activity #": "#1f77b4",
            "System #": "#2ca02c", 
            "File #": "#ff7f0e"
        }
        cols = st.columns(len(summary))
        for col, (key, value) in zip(cols, summary.items()):
            color = metric_colors.get(key, "#0072B2") # 기본 색상
            col.markdown(create_metric_card(value, key, color), unsafe_allow_html=True)
        return selected_industry, df_ind

def activity_analysis(df_ind, df_mapping, all_activities):
    st.header(f"⚙️ Activity Analysis")
    # Activity_Seq 순으로 정렬
    act_counts = df_ind.groupby('Activity')['FileName'].count().reset_index()
    # Activity_Seq를 가져와서 merge하여 정렬
    activity_seq = df_ind[['Activity', 'Activity_Seq']].drop_duplicates()
    act_counts = act_counts.merge(activity_seq, on='Activity', how='left')
    act_counts = act_counts.sort_values('Activity_Seq', ascending=True)

    act_col1, act_col2 = st.columns([3, 3])
    with act_col1:
        act_tab1, act_tab2, act_tab3 = st.tabs(["Activity별 파일 분포(파이 차트)", 
        "Activity별 파일 수(막대 차트)", "Activity별 파일 수(테이블)"])
        with act_tab1:  
            # # 파이 차트 생성 (도넛 형태) 
            fig_act = px.pie(act_counts, names='Activity', values='FileName', 
                            title=f"Activity별 파일 분포",
                            hole=0.4, # 도넛 형태
                            color_discrete_sequence=px.colors.qualitative.Pastel,
                            category_orders={'Activity': act_counts['Activity'].tolist()})
            fig_act.update_traces(textposition='inside', textinfo='percent+label', sort=False)
            st.plotly_chart(fig_act, width="stretch")

        with act_tab2:
            # 막대 차트 생성 (Activity별 파일 수) 
            fig_act = px.bar(act_counts, x='Activity', y='FileName', 
                            title=f"Activity별 파일 수",
                            color='Activity', height=400)
            fig_act.update_layout(bargap=0.2, showlegend=False)
            st.plotly_chart(fig_act, width="stretch")
        with act_tab3:
            st.dataframe(act_counts, width="stretch", height=400, hide_index=True)

    with act_col2:
        selected_act = st.selectbox("Activity를 선택하세요", all_activities, key="sel_act")
        # st.subheader(f"📄 '{selected_act}' Activity에 속한 파일 요약")
        act_files = df_ind[df_ind['Activity'] == selected_act]['FileName'].unique()
        act_summary = get_file_summary(act_files, df_mapping)
        st.dataframe(act_summary, width="stretch", height=400, hide_index=True)

    st.divider()


def system_analysis(df_ind, df_mapping, all_systems):
    st.header(f"💻 System Analysis")
    
    # System_Seq 순으로 정렬
    sys_counts = df_ind.groupby('System')['FileName'].count().reset_index()
    # System_Seq를 가져와서 merge하여 정렬
    system_seq = df_ind[['System', 'System_Seq']].drop_duplicates()
    sys_counts = sys_counts.merge(system_seq, on='System', how='left')
    sys_counts = sys_counts.sort_values('System_Seq', ascending=True)
    sys_col1, sys_col2 = st.columns([3, 3])
    
    with sys_col1:
        sys_tab1, sys_tab2, sys_tab3 = st.tabs(["System별 파일 분포(파이 차트)", 
                    "System별 파일 수(막대 차트)", "System별 파일 수(테이블)"])
        with sys_tab1:
            # 파이 차트 생성
            fig_sys = px.pie(sys_counts, names='System', values='FileName', 
                            title=f"System별 파일 분포",
                            hole=0.4, # 도넛 형태
                            color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_sys.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_sys, width="stretch")
        with sys_tab2:
            # 막대 차트 생성 (System별 파일 수)
            fig_sys = px.bar(sys_counts, x='System', y='FileName', 
                            title=f"System별 파일 수",
                            color='System', height=400)
            st.plotly_chart(fig_sys, width="stretch")
        with sys_tab3:
            st.dataframe(sys_counts, width="stretch", height=400, hide_index=True)

    with sys_col2:
        selected_sys = st.selectbox("System을 선택하세요", all_systems, key="sel_sys")
        sys_files = df_ind[df_ind['System'] == selected_sys]['FileName'].unique()
        sys_summary = get_file_summary(sys_files, df_mapping)
        st.dataframe(sys_summary, width="stretch", height=400, hide_index=True)

#-----------------------------------------------------------------------------------------
def Display_MasterFormat_Detail(ff_df):
    """Master Format Detail 화면 출력"""

    # 각 뷰별 컬럼 정의
    VIEW_COLUMNS = {
        "Value Info": [
            'FileName', 'ColumnName', 'OracleType', 'PK', 'ValueCnt',
            'Null(%)', 'UniqueCnt', 'Unique(%)',
            'MinString', 'MaxString', 'ModeString', # 'MedianString', 'ModeCnt', 'Mode(%)'
        ],
        "Value Type Info": [
            'FileName', 'ColumnName', 'ValueCnt', 'FormatCnt',
            'Format', 'Format(%)', 'FormatMin', 'FormatMax', 'FormatMode', 'FormatMedian',
            'Format2nd', 'Format2nd(%)', 'Format2ndMin', 'Format2ndMax', 'Format2ndMode', 'Format2ndMedian',
            'Format3rd', 'Format3rd(%)'
        ],

        "Top10 Info": [
            'FileName', 'ColumnName', 'ValueCnt', 'ModeString', 'ModeCnt', 'Mode(%)',
            'Top10', 'Top10(%)'
        ],
        "Length Info": [
            'FileName', 'ColumnName', 'OracleType', 'PK', 'DetailDataType',
            'LenCnt', 'LenMin', 'LenMax', 'LenAvg', 'LenMode',
            'RecordCnt', 'SampleRows', 'ValueCnt', 'NullCnt', 'Null(%)',
            'UniqueCnt', 'Unique(%)'
        ],
        "Character Info": [
            'FileName', 'ColumnName', 'ValueCnt', 'HasBrokenKor', 'HasSpecial', 'HasUnicode', 'HasChinese', 
            'HasTab', 'HasCr', 'HasLf', 'HasJapanese', 'HasBlank', 'HasDash', 'HasDot', 'HasAt', 'HasAlpha',
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

    if ff_df.empty:
        st.warning("Data Quality 분석 파일을 로드할 수 없습니다.")
        return False

    if ff_df is not None and not ff_df.empty:
        tabs = ['Value Info', 'Value Type Info', 'Top10 Info', 'Length Info', 
            'Character Info', 'DQ Score Info', 'Total Statistics']
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tabs)

        with tab1:
            st.markdown("###### 모든 컬럼들의 데이터 값 정보를 제공합니다.")
            # 존재하는 컬럼만 선택
            available_cols = [col for col in VIEW_COLUMNS['Value Info'] if col in ff_df.columns]
            if available_cols:
                df = ff_df[available_cols].reset_index(drop=True)
                st.dataframe(data=df, width=1400, height=600, hide_index=True)
            else:
                st.warning("표시할 컬럼이 없습니다.")
        with tab2:
            st.markdown("###### 모든 컬럼들의 데이터 타입 정보를 제공합니다.")
            # 존재하는 컬럼만 선택
            available_cols = [col for col in VIEW_COLUMNS['Value Type Info'] if col in ff_df.columns]
            if available_cols:
                df = ff_df[available_cols].reset_index(drop=True)
                st.dataframe(data=df, width=1400, height=600, hide_index=True)
            else:
                st.warning("표시할 컬럼이 없습니다.")
        with tab3:
            st.markdown("###### 모든 컬럼들의 빈도수 상위 10개를 제공합니다.")
            # 존재하는 컬럼만 선택
            available_cols = [col for col in VIEW_COLUMNS['Top10 Info'] if col in ff_df.columns]
            if available_cols:
                df = ff_df[available_cols].reset_index(drop=True)
                st.dataframe(data=df, width=1400, height=600, hide_index=True)
            else:
                st.warning("표시할 컬럼이 없습니다.")
        with tab4:
            st.markdown("###### 모든 컬럼들의 길이 정보를 제공합니다.")
            # 존재하는 컬럼만 선택
            available_cols = [col for col in VIEW_COLUMNS['Length Info'] if col in ff_df.columns]
            if available_cols:
                df = ff_df[available_cols].reset_index(drop=True)
                st.dataframe(data=df, width=1400, height=600, hide_index=True)
            else:
                st.warning("표시할 컬럼이 없습니다.")
        with tab5:
            st.markdown("###### 모든 컬럼들의 구성하는 문자 정보를 제공합니다.")
            # 존재하는 컬럼만 선택
            available_cols = [col for col in VIEW_COLUMNS['Character Info'] if col in ff_df.columns]
            if available_cols:
                df = ff_df[available_cols].reset_index(drop=True)
                st.dataframe(data=df, width=1400, height=600, hide_index=True)
            else:
                st.warning("표시할 컬럼이 없습니다.")
        with tab6:
            st.markdown("###### 모든 컬럼들의 Data Quality Score 정보를 제공합니다. (기업의 상황에 따라 기준이 다를 수 있습니다. 컨설팅 후 확정합니다.)")
            # 존재하는 컬럼만 선택
            available_cols = [col for col in VIEW_COLUMNS['DQ Score Info'] if col in ff_df.columns]
            if available_cols:
                df = ff_df[available_cols].reset_index(drop=True)
                st.dataframe(data=df, width=1400, height=600, hide_index=True)
            else:
                st.warning("표시할 컬럼이 없습니다.")
        with tab7:
            st.markdown("###### 모든 컬럼들의 통계 정보를 제공합니다.")
            df = ff_df.reset_index(drop=True)
            st.dataframe(data=df, width=1400, height=600,hide_index=True)
    else:
        st.warning("Data Quality 분석 파일을 로드할 수 없습니다.")
        return False
    return True    

def file_detail_analysis(df_ind, df_mapping):
    st.divider()
    st.markdown(f"### 📑 파일 상세 정보")
    
    final_files = sorted(df_ind['FileName'].unique())
    selected_file = st.selectbox("조회할 파일을 최종 선택하세요", final_files)

    if selected_file and df_mapping is not None:
        detail_df = df_mapping[df_mapping['FileName'] == selected_file]
        
        if not detail_df.empty:
            # 메트릭 표시
            m1, m2, m3, m4 = st.columns(4)
            
            # 총 레코드 수 (여러 컬럼명 시도)
            total_records = "N/A"
            try:
                if 'TotalRecords' in detail_df.columns:
                    val = detail_df['TotalRecords'].iloc[0]
                    if pd.notna(val):
                        total_records = f"{int(val):,}"
                elif 'RecordCnt' in detail_df.columns:
                    val = detail_df['RecordCnt'].iloc[0]
                    if pd.notna(val):
                        total_records = f"{int(val):,}"
                elif 'ValueCnt' in detail_df.columns:
                    val = detail_df['ValueCnt'].max()
                    if pd.notna(val):
                        total_records = f"{int(val):,}"
            except (ValueError, TypeError, IndexError, KeyError):
                pass
            
            # Sampling Row 수
            sampling_row = "N/A"
            if 'SampleRows' in detail_df.columns:
                try:
                    # 숫자로 변환 시도 (NaN 처리 포함)
                    sample_rows_series = pd.to_numeric(detail_df['SampleRows'], errors='coerce')
                    # NaN이 아닌 첫 번째 값 사용
                    valid_value = sample_rows_series.dropna()
                    if not valid_value.empty:
                        sampling_row = f"{int(valid_value.iloc[0]):,}"
                    # 모든 행이 NaN인 경우, 첫 번째 행의 원본 값 확인
                    elif not detail_df['SampleRows'].empty:
                        first_val = detail_df['SampleRows'].iloc[0]
                        if pd.notna(first_val) and str(first_val).strip() != '':
                            try:
                                sampling_row = f"{int(float(str(first_val))):,}"
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    pass

            # Null(%) > 0% 인 컬럼 수
            null_0_cnt = "N/A"
            if 'Null(%)' in detail_df.columns:
                try:
                    null_pct_series = pd.to_numeric(detail_df['Null(%)'], errors='coerce')
                    null_0_cnt = f"{len(detail_df[null_pct_series > 0])}"
                except Exception:
                    pass

            # Null(%) == 100% 인 컬럼 수
            null_100_cnt = "N/A"
            if 'Null(%)' in detail_df.columns:
                try:
                    null_pct_series = pd.to_numeric(detail_df['Null(%)'], errors='coerce')
                    null_100_cnt = f"{len(detail_df[null_pct_series == 100])}"
                except Exception:
                    pass

            # Unique(%) == 100% 인 컬럼 수
            unique_100_cnt = "N/A"
            if 'Unique(%)' in detail_df.columns:
                try:
                    unique_pct_series = pd.to_numeric(detail_df['Unique(%)'], errors='coerce')
                    unique_100_cnt = f"{len(detail_df[unique_pct_series == 100])}"
                except Exception:
                    pass
            

            # 메트릭 표시
            summary = {
                "Total Records": total_records,
                "Column #": len(detail_df),
                "Sampling #": sampling_row,
                "Has Null": null_0_cnt,
                "Has All Null": null_100_cnt,
                "Unique Columns": unique_100_cnt,
            }

            metric_colors = {
                "Total Records": "#1f77b4",      # 파란색 (정보성)
                "Column #": "#2ca02c",           # 초록색 (긍정적)
                "Sampling #": "#9467bd",         # 보라색 (정보성)
                "Has Null": "#ffbb78",           # 연한 주황색 (경고)
                "Has All Null": "#d62728",       # 빨간색 (위험)
                "Unique Columns": "#17becf",     # 청록색 (긍정적)
            }

            cols = st.columns(len(summary))
            for col, (key, value) in zip(cols, summary.items()):
                color = metric_colors.get(key, "#0072B2") # 기본 색상
                col.markdown(create_metric_card(value, key, color), unsafe_allow_html=True)

            result = Display_MasterFormat_Detail(detail_df)

        else:
            st.warning("상세 매핑 데이터가 없습니다.")
    else:
        st.warning("System 파일이 없습니다.")

def main():
    st.title(APP_NAME)
    st.markdown(APP_DESC)

    # 데이터 로드 & 전처리
    df_vc, df_sys, df_vc_sys, df_mapping = load_data_validation()
    
    if df_vc is None or df_sys is None or df_vc_sys is None or df_mapping is None:
        st.error(f"데이터 파일을 찾을 수 없습니다: {VC_FILE}, {SYS_FILE}, {VC_SYS_FILE}, {MAPPING_FILE}")
        return

    selected_industry, df_ind = select_industry(df_vc, df_sys, df_vc_sys)

    all_activities = sorted(df_ind['Activity'].unique())
    all_systems = sorted(df_ind['System'].unique())

    # 2. Activity 섹션 (파이 차트 + 독립 정보)
    activity_analysis(df_ind, df_mapping, all_activities)

    # 3. System 섹션 (파이 차트 + 독립 정보)
    system_analysis(df_ind, df_mapping, all_systems)

    # 4. 파일 상세 정보 출력
    file_detail_analysis(df_ind, df_mapping)

    # 드릴다운: 특정 컬럼의 Format 분포 등을 더 보고 싶을 때를 위한 확장
    with st.expander("Raw Data (CodeMapping) 전체 보기", expanded=False):
        st.dataframe(df_mapping, width="stretch", height=600, hide_index=True)
    st.divider()

if __name__ == "__main__":
    main()