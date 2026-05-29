# -*- coding: utf-8 -*-
"""
Value Chain & System Diagram Generator
DS_ValueChain.csv, DS_System.csv, DS_ValueChain_System_File.csv 파일을 이용하여 
Industry별 Value Chain Diagram과 System Architecture Diagram을 생성합니다.
Qliker 2025.
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
# 2. Streamlit 경고 억제 설정 (Streamlit import 전에 호출)
# -------------------------------------------------------------------
from util.streamlit_warnings import setup_streamlit_warnings
setup_streamlit_warnings()

from util.Display import create_metric_card # KPI 메트릭 표시 함수

# -------------------------------------------------------------------
# 3. 필수 라이브러리 import
# -------------------------------------------------------------------
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os
from pathlib import Path
import logging
import platform
import re
import shutil
from graphviz import Digraph
from PIL import Image
import plotly.express as px

# Streamlit 경고 억제
logging.getLogger('streamlit.runtime.scriptrunner.script_run_context').setLevel(logging.ERROR)

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
APP_NAME = "Value Chain & System Diagram"
APP_DESC = "#### Value Chain & System를 기반으로 Value Chain Diagram과 System Architecture Diagram을 생성합니다."

from util.Files_FunctionV20 import set_page_config
set_page_config(APP_NAME)
# -------------------------------------------------------------------
# 4. 경로 설정
# -------------------------------------------------------------------

OUTPUT_DIR      = PROJECT_ROOT / "DS_Output"
IMAGE_DIR       = PROJECT_ROOT / "images"
IMAGE_SAMPLE_DIR = PROJECT_ROOT / "images_sample"
VC_FILE         = OUTPUT_DIR / "DS_ValueChain.csv"
SYS_FILE        = OUTPUT_DIR / "DS_System.csv"
VC_SYS_FILE     = OUTPUT_DIR / "DS_ValueChain_System_File.csv"
MAPPING_FILE    = OUTPUT_DIR / "CodeMapping.csv"

# 디렉토리가 없으면 생성
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
# Graphviz PNG DPI: 300은 대형 다이어그램에서 렌더가 매우 길어질 수 있음. 고해상도는 QDQM_GRAPHVIZ_DPI=300 등으로 지정.
GRAPHVIZ_RENDER_DPI = os.environ.get("QDQM_GRAPHVIZ_DPI", "150")
# -------------------------------------------------
# Value Chain & System Diagram Color Code
# -------------------------------------------------
PRIMARY_FILLCOLOR = '#E3F2FD'
PRIMARY_COLOR =     '#1E88E5'
SUPPORT_FILLCOLOR = '#FFF9C4'
SUPPORT_COLOR =     '#FBC02D'

SYSTEM_FILLCOLOR =  '#E8F5E9'
SYSTEM_COLOR =      '#43A047'
FILE_FILLCOLOR =    '#F3E5F5'
FILE_COLOR =        '#9C27B0'
_GRAPHVIZ_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

def _first_valid_color_in_column(df_slice: pd.DataFrame, column_name: str) -> str | None:
    """df_slice에서 column_name의 첫 유효 색(hex·Graphviz 색 이름) 또는 None."""
    if df_slice.empty or column_name not in df_slice.columns:
        return None
    for val in df_slice[column_name].dropna():
        s = str(val).strip()
        if not s or s.lower() == "nan":
            continue
        if _GRAPHVIZ_HEX_COLOR.match(s):
            return s
        if re.match(r"^[a-zA-Z][a-zA-Z0-9]*$", s):
            return s
    return None

def _resolve_colors_from_column(
    df_slice: pd.DataFrame,
    column_name: str,
    default_fill: str,
    default_pen: str,
) -> tuple[str, str]:
    """column_name 값이 유효한 색이면 fillcolor·테두리에 사용, 아니면 기본값."""
    found = _first_valid_color_in_column(df_slice, column_name)
    if found is not None:
        return found, found
    return default_fill, default_pen

def _resolve_system_node_colors(sys_info: pd.DataFrame) -> tuple[str, str]:
    """System_Color가 유효하면 fillcolor·테두리에 사용, 없으면 SYSTEM_FILLCOLOR / SYSTEM_COLOR."""
    return _resolve_colors_from_column(sys_info, "System_Color", SYSTEM_FILLCOLOR, SYSTEM_COLOR)

def _system_arch_link_edge_color(sys_info: pd.DataFrame) -> str:
    """Activity→System 연결선: System_Color가 있으면 동일 색, 없으면 SYSTEM_COLOR."""
    c = _first_valid_color_in_column(sys_info, "System_Color")
    return c if c is not None else SYSTEM_COLOR
# Value Chain Diagram PNG 여백 (인치, Graphviz margin: left, top, right, bottom)
# LEFT: rankdir=LR 기준 첫 노드(시작) 앞 여백 / BOTTOM: Support 행 아래 여백
VC_DIAGRAM_MARGIN_LEFT = 0.5
VC_DIAGRAM_MARGIN_TOP = 0.15
VC_DIAGRAM_MARGIN_RIGHT = 0.15
VC_DIAGRAM_MARGIN_BOTTOM = 0.55
# ============================================================================
# 공통 유틸리티 함수
# ============================================================================

def is_cloud_env() -> bool:
    """Cloud 환경인지 확인합니다 (Graphviz dot 실행 파일 존재 여부로 판단)."""
    try:
        return shutil.which("dot") is None
    except Exception:
        return True

def show_sample_image(image_filename, caption):
    """Sample 이미지를 표시합니다."""
    try:
        sample_path = IMAGE_SAMPLE_DIR / image_filename
        if sample_path.exists():
            image = Image.open(sample_path)
            st.image(image, caption=caption, width='stretch')
            st.info("**Cloud 환경에서는 Graphviz 실행이 제한됩니다. 실제 Diagram 대신 예제 이미지를 표시합니다.**")
        else:
            st.warning(f"⚠️ Sample 이미지를 찾을 수 없습니다: {image_filename}")
    except Exception as e:
        st.error(f"❌ Sample 이미지 로드 중 오류가 발생했습니다: {e}")

def load_data(path):
    """CSV 파일을 로드합니다."""
    if path.exists():
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception as e:
            st.error(f"❌ 파일 로드 중 오류가 발생했습니다: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

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
        return None, None, None, None
    
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

def get_all_industries(df):
    """모든 Industry 목록을 반환합니다."""
    if df is None or df.empty:
        return []
    if "Industry" not in df.columns:
        return []
    return sorted(df["Industry"].unique().tolist())

def select_industry(df_vc, df_sys, df_vc_sys):
    
    col_sel1, col_sel2,  col3 = st.columns([1, 2, 1])
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

        st.divider()
        st.subheader("🏢 Value Chain & System Summary")
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
# ============================================================================
# Value Chain Diagram 생성 함수
# ============================================================================

def create_valuechain_diagram(df, industry):
    """
    Value Chain Diagram 생성 (Primary 상단, Support 하단, 수직 정렬 완벽 최적화)
    """
    df_ind = df[df["Industry"] == industry].copy()
    if df_ind.empty:
        return None
    
    df_ind = df_ind.sort_values("Activity_Seq")
    
    # 1. 그래프 기본 설정
    graph = Digraph(name=f"ValueChain_{industry}", format='png', engine='dot')
    
    # rankdir='LR': 왼쪽에서 오른쪽으로 흐름
    # nodesep: 상하 노드 간격 (좁게 설정하여 두 그룹을 붙임 : Defalut : 1.5)
    # ranksep: 좌우 노드 간격 (활동 간의 거리)
    # margin: 캔버스 여백(인치) left, top, right, bottom — 시작(좌)·하단을 넉넉히
    graph.attr(
        rankdir='LR',
        size='20,20',
        nodesep='1.5',
        ranksep='0.6',
        bgcolor='black',
        margin=(
            f'{VC_DIAGRAM_MARGIN_LEFT},{VC_DIAGRAM_MARGIN_TOP},'
            f'{VC_DIAGRAM_MARGIN_RIGHT},{VC_DIAGRAM_MARGIN_BOTTOM}'
        ),
    )
    
    # 폰트 설정
    font_name = 'Malgun Gothic' if platform.system() == 'Windows' else 'NanumGothic'

    # 모든 노드의 규격을 통일 (정렬의 핵심)
    graph.attr('node', shape='box', style='rounded,filled', fontname=font_name,
               fontsize='16', width='2.8', height='0.9', fixedsize='true', bgcolor='black', color='white')
    graph.attr('edge', fontname=font_name, color='white')
    
    primary_activities = df_ind[df_ind["Activity_Type"] == "Primary"].reset_index(drop=True)
    support_activities = df_ind[df_ind["Activity_Type"] == "Support"].reset_index(drop=True)
    
    max_cols = max(len(primary_activities), len(support_activities))

    # 2. 노드 생성 및 그룹화
    primary_node_ids = []
    support_node_ids = []

    for i in range(max_cols):
        # --- Primary 노드 생성 ---
        p_id = f"pri_{i}"
        if i < len(primary_activities):
            row = primary_activities.iloc[i]
            p_label = f"{row['Activity']}\\n({row['Activity_Kor']})"
            graph.node(p_id, label=p_label, fillcolor=PRIMARY_FILLCOLOR, color=PRIMARY_COLOR)
        else:
            graph.node(p_id, label='', style='invis')
        primary_node_ids.append(p_id)

        # --- Support 노드 생성 ---
        s_id = f"sup_{i}"
        if i < len(support_activities):
            row = support_activities.iloc[i]
            s_label = f"{row['Activity']}\\n({row['Activity_Kor']})"
            graph.node(s_id, label=s_label, fillcolor=SUPPORT_FILLCOLOR, color=SUPPORT_COLOR)
        else:
            graph.node(s_id, label='', style='invis')
        support_node_ids.append(s_id)

        # --- 수직 정렬 강제 (동일 선상 배치) ---
        # rank='same'과 투명 엣지를 사용하여 Primary가 무조건 위에, Support가 아래에 오도록 고정
        with graph.subgraph() as c:
            c.attr(rank='same')
            c.node(p_id)
            c.node(s_id)
        
        # Primary에서 Support로 투명선을 그어 상하 관계 확정
        graph.edge(p_id, s_id, style='invis')

    # 3. 수평 흐름 연결 (화살표)
    for i in range(max_cols - 1):
        # Primary 흐름 (실선 화살표)
        if i < len(primary_activities) - 1:
            graph.edge(primary_node_ids[i], primary_node_ids[i+1], 
                       style='bold', color=PRIMARY_COLOR, arrowhead='vee')
        
        # Support 흐름 (점선 화살표)
        if i < len(support_activities) - 1:
            graph.edge(support_node_ids[i], support_node_ids[i+1], 
                       style='dashed', color=SUPPORT_COLOR, arrowhead='vee')

    return graph

# ============================================================================
# System Architecture Diagram 생성 함수
# ============================================================================

def create_system_architecture_diagram(df_ind,  df_mapping, industry, mode="Summary"):
    """System Architecture Diagram을 생성합니다."""

    if df_ind.empty:
        return None

    dot = Digraph(name=f"SysArch_{mode}_{industry}", format='png', engine='dot')
    
    # 상세 모드일 때는 노드 내부 텍스트가 길어지므로 간격을 조정합니다.
    rank_sep = '3.5' if mode == "Summary" else '2.5'
    dot.attr(rankdir='TB', size='40,30', nodesep='0.3', ranksep=rank_sep, bgcolor='black', color='white')
    
    font_name = 'Malgun Gothic' if platform.system() == 'Windows' else 'NanumGothic'

    # --- 1. 상단 레이어: 가로 정렬 Activity (수정 금지 로직) ---
    activity_node_ids = []
    with dot.subgraph() as s:
        s.attr(rank='same')
        for _, row in df_ind.iterrows():
            act_id = f"act_{row['Activity']}"
            display_name = row['Activity_Kor'] if pd.notna(row.get('Activity_Kor')) else row['Activity']
            label = f"{display_name}\\n({row['Activity']})"
            
            if row.get('Activity_Type') == 'Primary':
                f_color, b_color = PRIMARY_FILLCOLOR, PRIMARY_COLOR
            else:
                f_color, b_color = SUPPORT_FILLCOLOR, SUPPORT_COLOR
            
            s.node(act_id, label=label, shape='box', style='filled,rounded', 
                   fillcolor=f_color, color=b_color, fontname=font_name, 
                   width='2.2', height='1.1', penwidth='2')
            activity_node_ids.append(act_id)

    for i in range(len(activity_node_ids) - 1):
        dot.edge(activity_node_ids[i], activity_node_ids[i+1], style='invis')

    # --- 2. 하단 레이어: IT Systems & Files ---
    mapped_systems = df_ind["System"].dropna().unique()
    system_node_ids = {}
    
    if len(mapped_systems) > 0:
        with dot.subgraph() as ss:
            ss.attr(rank='same')
            for sys_id in mapped_systems:
                if not sys_id: continue
                sys_info = df_ind[(df_ind["Industry"] == industry) & (df_ind["System"] == sys_id)]
                sys_kor = sys_info.iloc[0]["System_Kor"] if not sys_info.empty else sys_id
                sys_fill, sys_pen = _resolve_system_node_colors(sys_info)
                
                node_id = f"sys_{sys_id}"
                
                if mode == "Summary":
                    # 요약 모드: 기존 컴포넌트 형태
                    ss.node(node_id, label=f"{sys_kor}\\n({sys_id})", shape='component', 
                           style='filled', fillcolor=sys_fill, color=sys_pen, 
                           fontname=font_name, width='2.0', height='1.1')
                else:
                    # 상세 모드: 시스템명 아래에 파일 목록을 줄바꿈하여 포함
                    files = df_ind[df_ind["System"] == sys_id]["FileName"].dropna().unique()
                    file_list_str = "\\n".join([f"• {f}" for f in files]) if len(files) > 0 else "(No Files)"
                    
                    # HTML-like label을 사용하지 않고 단순 문자열과 구분선을 조합한 박스 형태
                    detail_label = f"{{ {sys_kor} ({sys_id}) | {file_list_str} }}"
                    
                    ss.node(node_id, label=detail_label, shape='record', # record 쉐이프 사용
                           style='filled', fillcolor=sys_fill, color=sys_pen, 
                           fontname=font_name, penwidth='1.5')
                
                system_node_ids[sys_id] = node_id

    # --- 3. 연결선 (Activity -> System) ---
    unique_links = df_ind[["Activity", "System"]].drop_duplicates()
    for _, row in unique_links.iterrows():
        if f"act_{row['Activity']}" in activity_node_ids and row['System'] in system_node_ids:
            sys_name = row["System"]
            sys_info = df_ind[(df_ind["Industry"] == industry) & (df_ind["System"] == sys_name)]
            edge_color = _system_arch_link_edge_color(sys_info)
            dot.edge(
                f"act_{row['Activity']}",
                system_node_ids[sys_name],
                color=edge_color,
                arrowhead="vee",
                penwidth="2.5",
            )

    return dot

# ============================================================================
# Value Chain & File Diagram 생성 함수
# ============================================================================

def create_valuechain_file_diagram(df_ind, industry):
    """Value Chain Activity와 FileName을 직접 연결하는 Diagram을 생성합니다.
    System Architecture Detail과 비슷하게 Activity별로 FileName을 박스로 묶어서 표시합니다."""

    if df_ind.empty:
        return None

    df_ind = df_ind[df_ind["Industry"] == industry].sort_values("Activity_Seq").copy()
    if df_ind.empty:
        return None
    
    dot = Digraph(name=f"ValueChain_File_{industry}", format='png', engine='dot')
    # 파일 목록이 포함되므로 간격을 넓게 설정
    dot.attr(rankdir='TB', size='40,30', nodesep='0.5', ranksep='2.5', bgcolor='black', color='white')
    
    font_name = 'Malgun Gothic' if platform.system() == 'Windows' else 'NanumGothic'

    # --- 1. 상단 레이어: 가로 정렬 Activity ---
    activity_node_ids = []
    with dot.subgraph() as s:
        s.attr(rank='same')
        for _, row in df_ind.iterrows():
            act_id = f"act_{row['Activity']}"
            display_name = row['Activity_Kor'] if pd.notna(row.get('Activity_Kor')) else row['Activity']
            label = f"{display_name}\\n({row['Activity']})"
            
            if row.get('Activity_Type') == 'Primary':
                f_color, b_color = PRIMARY_FILLCOLOR, PRIMARY_COLOR
            else:
                f_color, b_color = SUPPORT_FILLCOLOR, SUPPORT_COLOR
            
            s.node(act_id, label=label, shape='box', style='filled,rounded', 
                   fillcolor=f_color, color=b_color, fontname=font_name, 
                   width='2.2', height='0.8', penwidth='2')
            activity_node_ids.append(act_id)

    for i in range(len(activity_node_ids) - 1):
        dot.edge(activity_node_ids[i], activity_node_ids[i+1], style='invis')

    # --- 2. 하단 레이어: Activity별 FileName 박스 ---
    file_box_node_ids = {}
    file_box_edge_color = {}
    
    with dot.subgraph() as fs:
        fs.attr(rank='same')
        for _, row in df_ind.iterrows():
            activity = row['Activity']
            act_id = f"act_{activity}"
            
            # 해당 Activity에 연결된 FileName들 가져오기
            act_rows = df_ind[df_ind["Activity"] == activity]
            files = act_rows["FileName"].dropna().unique()
            
            if len(files) > 0:
                # 파일 목록을 줄바꿈으로 표시
                file_list_str = "\\n".join([f"• {f}" for f in files])
                
                # Activity 정보를 포함한 박스 레이블 생성
                display_name = row['Activity_Kor'] if pd.notna(row.get('Activity_Kor')) else activity
                detail_label = f"{{ {display_name} ({activity}) | {file_list_str} }}"
                
                file_fill, file_pen = _resolve_colors_from_column(
                    act_rows, "System_Color", FILE_FILLCOLOR, FILE_COLOR
                )
                # 각 Activity별 File 박스 노드 생성
                file_box_id = f"filebox_{activity}"
                fs.node(file_box_id, label=detail_label, shape='record',
                       style='filled', fillcolor=file_fill, color=file_pen,
                       fontname=font_name, penwidth='1.5')
                
                file_box_node_ids[activity] = file_box_id
                file_box_edge_color[activity] = file_pen

    # --- 3. 연결선 (Activity -> FileName 박스) ---
    for activity in file_box_node_ids.keys():
        act_id = f"act_{activity}"
        if act_id in activity_node_ids and activity in file_box_node_ids:
            edge_col = file_box_edge_color.get(activity, '#9E9E9E')
            dot.edge(act_id, file_box_node_ids[activity],
                     color=edge_col, arrowhead='vee', penwidth='1.5')

    return dot

# ============================================================================
# 메인 UI 함수
# ============================================================================

def value_chain_tab(df_vc, selected_industry):
    """Value Chain Diagram 탭"""
    st.markdown(f"### 📊 Value Chain Diagram ({selected_industry})")
    
    df_ind = df_vc[df_vc["Industry"] == selected_industry].copy()

    # # 데이터 미리보기
    # with st.expander("📋 Value Chain Data Preview", expanded=False):
    #     display_df = df_ind[["Activity_Seq", "Activity_Type", "Activity", "Activity_Kor", "Activity_Description"]].copy()
    #     display_df.columns = ["Seq", "Type", "Activity (EN)", "Activity (KR)", "Description"]
    #     st.dataframe(display_df, width='stretch', hide_index=True)
    
    # Cloud 환경 체크
    if is_cloud_env():
        show_sample_image("Sample_ValueChain.png", f"Value Chain Diagram: {selected_industry} (Sample)")
        return
    
    # Diagram 생성
    try:
        graph = create_valuechain_diagram(df_vc, selected_industry)
        
        if graph is None:
            st.warning("⚠️ Value Chain Diagram을 생성할 수 없습니다.")
            return
        
        # Diagram 렌더링 및 저장
        file_time = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        png_filename = f"ValueChain_{selected_industry}_{file_time}.png"
        png_filepath = IMAGE_DIR / png_filename
        
        try:
            graph.attr(dpi=GRAPHVIZ_RENDER_DPI)
            with st.spinner("Graphviz로 PNG를 생성하는 중입니다. 다이어그램이 크면 수십 초 이상 걸릴 수 있습니다."):
                graph.render(str(png_filepath.with_suffix('')), format='png', cleanup=True)
            actual_png_filepath = IMAGE_DIR / f"{png_filepath.stem}.png"
            
            if actual_png_filepath.exists():
                # 이미지 표시
                image = Image.open(actual_png_filepath)
                st.image(image, caption=f"Value Chain Diagram: {selected_industry}", 
                       width='stretch')
                
                # 다운로드 버튼
                with open(actual_png_filepath, 'rb') as f:
                    png_data = f.read()
                if png_data:
                    st.download_button(
                        label="📥 Download PNG",
                        data=png_data,
                        file_name=actual_png_filepath.name,
                        mime="image/png",
                        key="vc_download"
                    )
            else:
                st.error("❌ Value Chain Diagram PNG 파일 생성에 실패했습니다.")
                
        except Exception as e:
            st.error(f"❌ Value Chain Diagram 생성 중 오류가 발생했습니다: {e}")
            
            # try:
            #     svg_data = graph.pipe(format='svg').decode('utf-8')
            #     components.html(svg_data, height=800, scrolling=True)
            #     st.success("✅ Diagram이 SVG 형식으로 표시되었습니다.")
            # except Exception as svg_e:
            #     st.error(f"SVG 생성도 실패했습니다: {svg_e}")
    
    except Exception as e:
        st.error(f"❌ 예상치 못한 오류가 발생했습니다: {e}")
        # import traceback
        # st.code(traceback.format_exc())

def system_architecture_tab(df_vc, df_sys, df_ind, df_mapping, selected_industry, mode="Summary"):
    """System Architecture Diagram 탭"""
    if mode == "Summary":
        st.markdown(f"### 🏗️ System Architecture (Summary): **{selected_industry}**")
        st.markdown("##### Activity와 System 간의 연결 관계를 요약하여 표시합니다.")
    else:
        st.markdown(f"### 🔍 System Architecture (Detail): **{selected_industry}**")
        st.markdown("##### System 내부의 파일 목록을 포함한 상세 구성도를 표시합니다.")
    
    # # 데이터 미리보기
    # with st.expander("📋 System Architecture Data Preview", expanded=False):
    #     preview_cols = [
    #         "Activity_Seq", "Activity_Type", "Activity", "Activity_Kor",
    #         "System", "System_Kor", "FileName",
    #     ]
    #     preview_headers = [
    #         "Seq", "Type", "Activity (EN)", "Activity (KR)",
    #         "System (EN)", "System (KR)", "File Name",
    #     ]
    #     if "System_Color" in df_ind.columns:
    #         preview_cols.append("System_Color")
    #         preview_headers.append("System Color")
    #     vc_display = df_ind[preview_cols].copy()
    #     vc_display.columns = preview_headers

    #     st.dataframe(vc_display, width='stretch', hide_index=True)

    
    # Cloud 환경 체크
    if is_cloud_env():
        if mode == "Summary":
            show_sample_image("Sample_SysArch_Summary.png", f"System Architecture (Summary): {selected_industry} (Sample)")
        else:
            show_sample_image("Sample_SysArch_Detailed.png", f"System Architecture (Detail): {selected_industry} (Sample)")
        return
    
    try:
        graph = create_system_architecture_diagram(df_ind, df_mapping, selected_industry, mode=mode)
        if graph:
            file_time = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            path = IMAGE_DIR / f"SysArch_{mode}_{selected_industry}_{file_time}"
            graph.attr(dpi=GRAPHVIZ_RENDER_DPI)
            with st.spinner("Graphviz로 PNG를 생성하는 중입니다. 다이어그램이 크면 수십 초 이상 걸릴 수 있습니다."):
                graph.render(str(path), format='png', cleanup=True)
            actual_png_filepath = IMAGE_DIR / f"{path.name}.png"
            
            if actual_png_filepath.exists():
                st.image(str(actual_png_filepath), width='stretch')
                
                # 다운로드 버튼
                with open(actual_png_filepath, "rb") as f:
                    png_data = f.read()
                if png_data:
                    st.download_button(
                        f"📥 {mode} 이미지 다운로드",
                        png_data,
                        file_name=f"SysArch_{mode}_{selected_industry}.png",
                        mime="image/png",
                        key=f"sys_{mode.lower()}_download"
                    )
        else:
            st.warning("⚠️ System Architecture Diagram을 생성할 수 없습니다. 매핑 데이터를 확인해주세요.")
            
    except Exception as e:
        st.error(f"❌ System Architecture Diagram 생성 중 오류가 발생했습니다: {e}")

def valuechain_file_tab(df_vc, df_sys, df_ind, df_mapping, selected_industry):
    """Value Chain & File Diagram 탭"""
    st.divider()
    st.markdown(f"### 📁 Value Chain & File Diagram: **{selected_industry}**")
    st.markdown("##### Value Chain Activity와 FileName을 직접 연결하는 구성도를 표시합니다.")
    
    # # 데이터 로드
    # df_vc = load_data(VALUECHAIN_CSV_PATH)
    # df_mapping = load_data(MAPPING_CSV_PATH)
    
    # 선택된 Industry의 데이터 필터링
    # df_ind = df_vc[df_vc["Industry"] == selected_industry].copy() if not df_vc.empty else pd.DataFrame()
    # df_mapping = df_mapping[df_mapping["Industry"] == selected_industry].copy() if not df_mapping.empty else pd.DataFrame()
    
    # 데이터 미리보기
    # with st.expander("📋 Value Chain & File Data Preview", expanded=False):
    #     col1, col2 = st.columns(2)
        
    #     with col1:
    #         st.markdown("**Value Chain Activities**")
    #         if not df_ind.empty:
    #             vc_cols = ["Activity_Seq", "Activity_Type", "Activity", "Activity_Kor"]
    #             vc_headers = ["Seq", "Type", "Activity (EN)", "Activity (KR)"]
    #             if "System_Color" in df_ind.columns:
    #                 vc_cols.append("System_Color")
    #                 vc_headers.append("System Color")
    #             vc_display = df_ind[vc_cols].copy()
    #             vc_display.columns = vc_headers
    #             st.dataframe(vc_display, width='stretch', hide_index=True)
    #         else:
    #             st.info("No Value Chain data")
        
    #     with col2:
    #         st.markdown("**Activity-File Mapping**")
    #         if not df_mapping.empty:
    #             # Activity와 FileName만 표시 (System은 제외)
    #             # mapping_display = df_mapping[["Activity", "FileName"]].drop_duplicates().copy()
    #             # mapping_display.columns = ["Activity", "File Name"]
    #             st.dataframe(df_mapping, width='stretch', hide_index=True)
    #         else:
    #             st.info("No Mapping data")
    
    # Cloud 환경 체크
    if is_cloud_env():
        show_sample_image("Sample_ValueChain_File.png", f"Value Chain & File Diagram: {selected_industry} (Sample)")
        return
    
    try:
        graph = create_valuechain_file_diagram(df_ind, selected_industry)
        if graph:
            file_time = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            path = IMAGE_DIR / f"ValueChain_File_{selected_industry}_{file_time}"
            graph.attr(dpi=GRAPHVIZ_RENDER_DPI)
            with st.spinner("Graphviz로 PNG를 생성하는 중입니다. 다이어그램이 크면 수십 초 이상 걸릴 수 있습니다."):
                graph.render(str(path), format='png', cleanup=True)
            actual_png_filepath = IMAGE_DIR / f"{path.name}.png"
            
            if actual_png_filepath.exists():
                st.image(str(actual_png_filepath), width='stretch')
                
                # 다운로드 버튼
                with open(actual_png_filepath, "rb") as f:
                    png_data = f.read()
                if png_data:
                    st.download_button(
                        "📥 Value Chain & File 이미지 다운로드",
                        png_data,
                        file_name=f"ValueChain_File_{selected_industry}.png",
                        mime="image/png",
                        key="vc_file_download"
                    )
        else:
            st.warning("⚠️ Diagram을 생성할 수 없습니다. 매핑 데이터를 확인해주세요.")
            
    except Exception as e:
        st.error(f"❌ Diagram 생성 중 오류가 발생했습니다: {e}")

#-----------------------------------------------------------------------------------------
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

def activity_analysis(df_ind, df_mapping, all_activities):
    st.subheader(f"⚙️ Activity Analysis")
    # Activity_Seq 순으로 정렬
    act_counts = df_ind.groupby('Activity')['FileName'].count().reset_index()
    # Activity_Seq를 가져와서 merge하여 정렬
    activity_seq = df_ind[['Activity', 'Activity_Seq']].drop_duplicates()
    act_counts = act_counts.merge(activity_seq, on='Activity', how='left')
    act_counts = act_counts.sort_values('Activity_Seq', ascending=True)

    # # 파이 차트 생성 (도넛 형태) 
    fig_act = px.pie(act_counts, names='Activity', values='FileName', 
                    title=f"Activity별 파일 분포",
                    hole=0.4, # 도넛 형태
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    category_orders={'Activity': act_counts['Activity'].tolist()})
    fig_act.update_traces(textposition='inside', textinfo='percent+label', sort=False)
    st.plotly_chart(fig_act, width="stretch")

    # selected_act = st.selectbox("Activity를 선택하세요", all_activities, key="sel_act")
    # # st.subheader(f"📄 '{selected_act}' Activity에 속한 파일 요약")
    # act_files = df_ind[df_ind['Activity'] == selected_act]['FileName'].unique()
    # act_summary = get_file_summary(act_files, df_mapping)
    # st.dataframe(act_summary, width="stretch", height=400, hide_index=True)
    # st.divider()

def system_analysis(df_ind, df_sys, df_mapping, all_systems):
    st.subheader(f"💻 System Analysis")
    # System_Seq 순으로 정렬
    sys_counts = df_ind.groupby('System')['FileName'].count().reset_index()
    # System_Seq를 가져와서 merge하여 정렬
    system_seq = df_ind[['System', 'System_Seq']].drop_duplicates()
    sys_counts = sys_counts.merge(system_seq, on='System', how='left')
    sys_counts = sys_counts.sort_values('System_Seq', ascending=True)

    sys_order = sys_counts['System'].tolist()
    palette = px.colors.qualitative.Pastel
    pie_color_map = {}
    for i, sys_name in enumerate(sys_order):
        custom = _first_valid_color_in_column(df_ind[df_ind['System'] == sys_name], 'System_Color')
        pie_color_map[sys_name] = custom if custom is not None else palette[i % len(palette)]

    fig_sys = px.pie(
        sys_counts,
        names='System',
        values='FileName',
        title=f"System별 파일 분포",
        hole=0.4,
        color='System',
        color_discrete_map=pie_color_map,
        category_orders={'System': sys_order},
    )
    fig_sys.update_traces(textposition='inside', textinfo='percent+label', sort=False)
    st.plotly_chart(fig_sys, width="stretch")

    # selected_sys = st.selectbox("System을 선택하세요", all_systems, key="sel_sys")
    # sys_files = df_ind[df_ind['System'] == selected_sys]['FileName'].unique()
    # sys_summary = get_file_summary(sys_files, df_mapping)
    # st.dataframe(sys_summary, width="stretch", height=400, hide_index=True)

# #-----------------------------------------------------------------------------------------
# def Display_MasterFormat_Detail(ff_df):
#     """Master Format Detail 화면 출력"""

#     # 각 뷰별 컬럼 정의
#     VIEW_COLUMNS = {
#         "Value Info": [
#             'FileName', 'ColumnName', 'OracleType', 'PK', 'ValueCnt',
#             'Null(%)', 'UniqueCnt', 'Unique(%)',
#             'MinString', 'MaxString', 'ModeString', # 'MedianString', 'ModeCnt', 'Mode(%)'
#         ],
#         "Value Type Info": [
#             'FileName', 'ColumnName', 'ValueCnt', 'FormatCnt',
#             'Format', 'Format(%)', 'FormatMin', 'FormatMax', 'FormatMode', 'FormatMedian',
#             'Format2nd', 'Format2nd(%)', 'Format2ndMin', 'Format2ndMax', 'Format2ndMode', 'Format2ndMedian',
#             'Format3rd', 'Format3rd(%)'
#         ],

#         "Top10 Info": [
#             'FileName', 'ColumnName', 'ValueCnt', 'ModeString', 'ModeCnt', 'Mode(%)',
#             'Top10', 'Top10(%)'
#         ],
#         "Length Info": [
#             'FileName', 'ColumnName', 'OracleType', 'PK', 'DetailDataType',
#             'LenCnt', 'LenMin', 'LenMax', 'LenAvg', 'LenMode',
#             'RecordCnt', 'SampleRows', 'ValueCnt', 'NullCnt', 'Null(%)',
#             'UniqueCnt', 'Unique(%)'
#         ],
#         "Character Info": [
#             'FileName', 'ColumnName', 'ValueCnt', 'HasBrokenKor', 'HasSpecial', 'HasUnicode', 'HasChinese', 
#             'HasTab', 'HasCr', 'HasLf', 'HasJapanese', 'HasBlank', 'HasDash', 'HasDot', 'HasAt', 'HasAlpha',
#             'HasKor', 'HasNum', 'HasBracket', 'HasMinus', 'HasOnlyAlpha', 'HasOnlyNum',
#             'HasOnlyKor', 'HasOnlyAlphanum',
#             'FirstChrKor', 'FirstChrNum', 'FirstChrAlpha', 'FirstChrSpecial'
#         ],
#         "DQ Score Info": [
#             'FileName', 'ColumnName', 'ValueCnt', 'Null_pct', 'TypeMixed_pct', 'LengthVol_pct', 'Duplicate_pct',
#             'DQ_Score', 'DQ_Issues', 'Issue_Count'
#         ]
#     }

#     # ---------------------------
#     st.divider()
#     st.subheader("📊 Data Quality Information")
#     st.markdown("###### 아래의 탭에서 상세 정보를 확인할 수 있습니다.")

#     if ff_df.empty:
#         st.warning("Data Quality 분석 파일을 로드할 수 없습니다.")
#         return False

#     if ff_df is not None and not ff_df.empty:
#         tabs = ['Value Info', 'Value Type Info', 'Top10 Info', 'Length Info', 
#             'Character Info', 'DQ Score Info', 'Total Statistics']
#         tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tabs)

#         with tab1:
#             st.markdown("###### 모든 컬럼들의 데이터 값 정보를 제공합니다.")
#             # 존재하는 컬럼만 선택
#             available_cols = [col for col in VIEW_COLUMNS['Value Info'] if col in ff_df.columns]
#             if available_cols:
#                 df = ff_df[available_cols].reset_index(drop=True)
#                 st.dataframe(data=df, width=1400, height=600, hide_index=True)
#             else:
#                 st.warning("표시할 컬럼이 없습니다.")
#         with tab2:
#             st.markdown("###### 모든 컬럼들의 데이터 타입 정보를 제공합니다.")
#             # 존재하는 컬럼만 선택
#             available_cols = [col for col in VIEW_COLUMNS['Value Type Info'] if col in ff_df.columns]
#             if available_cols:
#                 df = ff_df[available_cols].reset_index(drop=True)
#                 st.dataframe(data=df, width=1400, height=600, hide_index=True)
#             else:
#                 st.warning("표시할 컬럼이 없습니다.")
#         with tab3:
#             st.markdown("###### 모든 컬럼들의 빈도수 상위 10개를 제공합니다.")
#             # 존재하는 컬럼만 선택
#             available_cols = [col for col in VIEW_COLUMNS['Top10 Info'] if col in ff_df.columns]
#             if available_cols:
#                 df = ff_df[available_cols].reset_index(drop=True)
#                 st.dataframe(data=df, width=1400, height=600, hide_index=True)
#             else:
#                 st.warning("표시할 컬럼이 없습니다.")
#         with tab4:
#             st.markdown("###### 모든 컬럼들의 길이 정보를 제공합니다.")
#             # 존재하는 컬럼만 선택
#             available_cols = [col for col in VIEW_COLUMNS['Length Info'] if col in ff_df.columns]
#             if available_cols:
#                 df = ff_df[available_cols].reset_index(drop=True)
#                 st.dataframe(data=df, width=1400, height=600, hide_index=True)
#             else:
#                 st.warning("표시할 컬럼이 없습니다.")
#         with tab5:
#             st.markdown("###### 모든 컬럼들의 구성하는 문자 정보를 제공합니다.")
#             # 존재하는 컬럼만 선택
#             available_cols = [col for col in VIEW_COLUMNS['Character Info'] if col in ff_df.columns]
#             if available_cols:
#                 df = ff_df[available_cols].reset_index(drop=True)
#                 st.dataframe(data=df, width=1400, height=600, hide_index=True)
#             else:
#                 st.warning("표시할 컬럼이 없습니다.")
#         with tab6:
#             st.markdown("###### 모든 컬럼들의 Data Quality Score 정보를 제공합니다. (기업의 상황에 따라 기준이 다를 수 있습니다. 컨설팅 후 확정합니다.)")
#             # 존재하는 컬럼만 선택
#             available_cols = [col for col in VIEW_COLUMNS['DQ Score Info'] if col in ff_df.columns]
#             if available_cols:
#                 df = ff_df[available_cols].reset_index(drop=True)
#                 st.dataframe(data=df, width=1400, height=600, hide_index=True)
#             else:
#                 st.warning("표시할 컬럼이 없습니다.")
#         with tab7:
#             st.markdown("###### 모든 컬럼들의 통계 정보를 제공합니다.")
#             df = ff_df.reset_index(drop=True)
#             st.dataframe(data=df, width=1400, height=600,hide_index=True)
#     else:
#         st.warning("Data Quality 분석 파일을 로드할 수 없습니다.")
#         return False
#     return True    
#-----------------------------------------------------------------------------------------
   
def main():
        # st.set_page_config(layout="wide")
    st.title(APP_NAME)
    st.markdown(APP_DESC)
    
    df_vc, df_sys, df_vc_sys, df_mapping = load_data_validation()   
    if df_vc is None or df_sys is None or df_vc_sys is None or df_mapping is None:
        st.error(f"데이터 파일을 찾을 수 없습니다: {VC_FILE}, {SYS_FILE}, {VC_SYS_FILE}, {MAPPING_FILE}")
        return
    
    # 데이터 로드
    selected_industry, df_ind = select_industry(df_vc, df_sys, df_vc_sys)

    df_vc = df_vc[df_vc['Industry'] == selected_industry]
    df_sys = df_sys[df_sys['Industry'] == selected_industry]
    df_vc_sys = df_vc_sys[df_vc_sys['Industry'] == selected_industry]
    # df_mapping = df_mapping[df_mapping['Industry'] == selected_industry]
    
    # 탭 생성
    st.divider()
    st.subheader("조회할 탭을 선택하세요.")
    tab_vc, tab_sys_summary, tab_sys_detail, tab_vc_file = st.tabs([
        "📊 Value Chain Diagram",
        "🏗️ Value Chain & System Mapping",
        "🔍 Value Chain,  System & File Mapping",
        "📁 Value Chain Diagram & File Mapping"
    ])
    
    with tab_vc:
        value_chain_tab(df_vc, selected_industry)
    
    with tab_sys_summary:
        system_architecture_tab(df_vc, df_sys, df_ind, df_mapping, selected_industry, mode="Summary")
    
    with tab_sys_detail:
        system_architecture_tab(df_vc, df_sys, df_ind, df_mapping, selected_industry, mode="Detailed")
    
    with tab_vc_file:
        valuechain_file_tab(df_vc, df_sys, df_ind, df_mapping, selected_industry)


    all_activities = sorted(df_ind['Activity'].unique())
    all_systems = sorted(df_ind['System'].unique())

    st.divider()
    col1, col2 = st.columns([3, 3])
    with col1:
        # 2. Activity 섹션 (파이 차트 + 독립 정보)
        activity_analysis(df_ind, df_mapping, all_activities)

    with col2:
        # 3. System 섹션 (파이 차트 + 독립 정보)
        system_analysis(df_ind, df_sys, df_mapping, all_systems)

    with st.expander("Value Chain & System Mapping 전체 보기", expanded=False):
        df_display = df_ind[['Activity_Seq','Activity_Type','Activity', 'Activity_Kor', 
                            'System_Seq', 'System', 'System_Kor', 'FileName']].copy().sort_values(['Activity_Seq', 'System_Seq'])
        df_display = df_display.rename(columns={'Activity_Seq': 'A_Seq', 'System_Seq': 'S_Seq', 'Activity_Type': 'A_Type'})
        st.dataframe(df_display,
            column_config={
                'A_Seq': st.column_config.NumberColumn(width="small"),
                'A_Type': st.column_config.SelectboxColumn(options=['Primary', 'Support'], width="small"),
                'Activity': st.column_config.TextColumn(width="small"),
                'Activity_Kor': st.column_config.TextColumn(width="medium"),
                'S_Seq': st.column_config.NumberColumn(width="small"),
                'System': st.column_config.TextColumn(width="small"),
                'System_Kor': st.column_config.TextColumn(width="medium"),
                'FileName': st.column_config.TextColumn(width="medium"),
            },
            width="stretch", 
            height=500, hide_index=True)

if __name__ == "__main__":
    main()

