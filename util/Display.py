import streamlit as st
import pandas as pd

# 공통 KPI 표시 함수
def create_metric_card(value, label, color="#0072B2"):
    """메트릭 카드 HTML 생성"""
    return f"""
        <div style="text-align: center; padding: 1.2rem; background-color: #FFFFFF; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="color: {color}; font-size: 2em; font-weight: bold;">{value}</div>
            <div style="color: #404040; font-size: 1em; margin-top: 0.5rem;">{label}</div>
        </div>
    """

def display_kpi_metrics(summary, metric_colors, title):
    """KPI 메트릭 표시 공통 함수"""
    st.markdown(f"### {title}")
    
    # 메트릭 표시
    cols = st.columns(len(summary))
    for col, (key, value) in zip(cols, summary.items()):
        color = metric_colors.get(key, "#0072B2")  # 기본 색상
        col.markdown(create_metric_card(value, key, color), unsafe_allow_html=True)


#-----------------------------------------------------------------------------------------
# Master KPI 
def Display_File_Statistics(filestats_df: pd.DataFrame) -> bool:
    """ 
    Master Statistics KPIs 
    filestats_df: 파일 통계 데이터프레임 (FileStatistics.csv)
    """
    df = filestats_df.copy()
    df = df[(df['MasterType'] != 'Common') & (df['MasterType'] != 'Reference') & (df['MasterType'] != 'Validation')]
    
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

    metric_colors = {
        "Data File #":      "#1f77b4",
        "Total Record #":   "#2ca02c", 
        "Total File Size":  "#ff7f0e",
        "Work Date":        "#9467bd"     # 보라색
    }

    display_kpi_metrics(summary, metric_colors, 'File Statistics')
    return True
