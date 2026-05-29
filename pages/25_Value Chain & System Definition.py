# -*- coding: utf-8 -*-
"""
Value Chain & System 데이터 관리 (통합)
Industry별 Value Chain, System 정의 및 File 매핑을 관리하는 통합 도구입니다.
2025.12.24 Qliker (Integrated Version)
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

# -------------------------------------------------
# 2. Standard / Third-party imports
# -------------------------------------------------
import streamlit as st
import pandas as pd
from pathlib import Path
import re
import os
import logging
from PIL import Image

# -------------------------------------------------------------------
# 0. Streamlit 경고 억제 설정 (ScriptRunContext 관련)
# -------------------------------------------------------------------
logging.getLogger('streamlit.runtime.scriptrunner.script_run_context').setLevel(logging.ERROR)
# -------------------------------------------------------------------
# 1. 경로 및 상수 설정
# -------------------------------------------------------------------
OUTPUT_DIR = PROJECT_ROOT / "DS_Output"
IMAGE_DIR = PROJECT_ROOT / "images"
IMAGE_SAMPLE_DIR = PROJECT_ROOT / "images_sample"
VALUECHAIN_CSV_PATH = OUTPUT_DIR / "DS_ValueChain.csv"
SYSTEM_CSV_PATH = OUTPUT_DIR / "DS_System.csv"
FILE_STATS_PATH = OUTPUT_DIR / "FileStats.csv"
FILE_FORMAT_PATH = OUTPUT_DIR / "FileFormat.csv"
MAPPING_CSV_PATH = OUTPUT_DIR / "DS_ValueChain_System_File.csv"
# -------------------------------------------------
# 3. Streamlit 페이지 설정 (다른 st.* 호출보다 먼저)
# -------------------------------------------------
APP_NAME = "🏭 Value Chain & System Definition"
APP_DESC = "#### Value Chain & System을 입력, 수정, 삭제하고 파일을 매핑하는 통합 도구입니다."
from util.Files_FunctionV20 import set_page_config

set_page_config(APP_NAME)

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

# 디렉토리가 없으면 생성
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Value Chain 컬럼 정의
VALUECHAIN_COLUMNS = [
    "Industry", "Activity_Seq", "Activity_Type", 
    "Activity", "Activity_Kor", "Activity_Description"
]

# System 컬럼 정의
SYSTEM_COLUMNS = [
    "Industry", "System_Seq", "System", "System_Kor", "System_Description"
]

# -------------------------------------------------------------------
# 2. 공통 유틸리티 함수
# -------------------------------------------------------------------
def show_sample_image(image_filename, caption):
    """Sample 이미지를 표시합니다."""
    try:
        sample_path = IMAGE_SAMPLE_DIR / image_filename
        if sample_path.exists():
            image = Image.open(sample_path)
            st.image(image, caption=caption, width=600)
            st.info("**위의 이미지는 Value Chain의 예제 이미지입니다.**")
        else:
            st.warning(f"⚠️ Sample 이미지를 찾을 수 없습니다: {image_filename}")
    except Exception as e:
        st.error(f"❌ Sample 이미지 로드 중 오류가 발생했습니다: {e}")

def check_no_korean(text):
    """영문 필드에 한글이 포함되어 있는지 확인 (True면 한글 없음)"""
    return not bool(re.search('[가-힣]', str(text)))

def get_all_industries():
    """Value Chain과 System 데이터에서 모든 Industry를 수집합니다."""
    industries = set()
    
    # Value Chain에서 Industry 수집
    if VALUECHAIN_CSV_PATH.exists():
        try:
            vc_df = pd.read_csv(VALUECHAIN_CSV_PATH, encoding="utf-8-sig")
            if not vc_df.empty and "Industry" in vc_df.columns:
                industries.update(vc_df["Industry"].unique().tolist())
        except Exception:
            pass
    
    # System에서 Industry 수집
    if SYSTEM_CSV_PATH.exists():
        try:
            sys_df = pd.read_csv(SYSTEM_CSV_PATH, encoding="utf-8-sig")
            if not sys_df.empty and "Industry" in sys_df.columns:
                industries.update(sys_df["Industry"].unique().tolist())
        except Exception:
            pass
    
    return sorted(list(industries))

def _read_csv_file(path: Path):
    """CSV 읽기 (Streamlit UI 없음, cache_data용)."""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        return df if not df.empty else None
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def _load_mapping_datasets():
    """File 매핑용 CSV 병합 (캐시)."""
    df_vc = _read_csv_file(VALUECHAIN_CSV_PATH)
    df_sys = _read_csv_file(SYSTEM_CSV_PATH)
    df_stats = _read_csv_file(FILE_STATS_PATH)
    df_format = _read_csv_file(FILE_FORMAT_PATH)
    if df_vc is None or df_sys is None or df_stats is None or df_format is None:
        return None

    except_master_type = ["Reference", "Validation", "Common"]
    df_stats = df_stats[~df_stats["MasterType"].isin(except_master_type)].copy()
    df_stats = df_stats.drop(columns=["MasterType", "SamplingRows", "Sampling(%)", "WorkDate"])

    df_format = df_format[~df_format["MasterType"].isin(except_master_type)].copy()
    df_PK = df_format[df_format["PK"] == 1].copy()
    if not df_PK.empty and "ColumnName" in df_PK.columns:
        df_PK = df_PK.groupby(["FilePath", "FileName"])["ColumnName"].apply(
            lambda x: ", ".join(sorted(x.unique()))
        ).reset_index()
        df_PK.columns = ["FilePath", "FileName", "PK_List"]
    else:
        df_PK = pd.DataFrame(columns=["FilePath", "FileName", "PK_List"])

    df_stats = pd.merge(df_stats, df_PK, on=["FilePath", "FileName"], how="left")
    df_stats["PK_List"] = df_stats["PK_List"].fillna("")
    df_format = pd.merge(
        df_format, df_stats[["FilePath", "FileName", "FileNo"]], on=["FilePath", "FileName"], how="left"
    )
    df_format = df_format.drop(columns=["FilePath"])
    df_stats = df_stats.drop(columns=["FilePath"])
    return df_vc, df_sys, df_stats.reset_index(drop=True), df_format


def load_csv(path, mode=0):
    """CSV 파일을 로드합니다. mode = 1 이면 read file & validateion, mode 0 이면 read only and not message"""
    if path.exists():
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            if df.empty and mode == 1:
                st.error(f"❌ '{path.name}' 파일이 존재하지 않거나 내용이 없습니다. 먼저 파일 분석을 수행하세요.")
                return None
            return df
        except Exception as e:
            st.error(f"❌ '{path.name}' 파일을 읽는 중 오류가 발생했습니다: {e}")
            return None
    else:
        if mode == 1:
            st.error(f"❌ '{path.name}' 파일이 존재하지 않습니다. 먼저 파일 분석을 수행하세요.")
        return None

def save_csv(df, path):
    """CSV 파일을 저장합니다."""
    try:
        df.to_csv(path, index=False, encoding="utf-8-sig")
        st.success(f"🎉 '{path.name}' 파일이 성공적으로 저장되었습니다.")
    except Exception as e:
        st.error(f"❌ 파일 저장 중 오류가 발생했습니다: {e}")

# -------------------------------------------------------------------
# 3. Value Chain 관련 함수
# -------------------------------------------------------------------
def load_valuechain_data():
    """Value Chain 데이터를 로드합니다."""
    if VALUECHAIN_CSV_PATH.exists():
        try:
            return pd.read_csv(VALUECHAIN_CSV_PATH, encoding="utf-8-sig")
        except Exception as e:
            st.error(f"Value Chain 파일을 읽는 중 오류가 발생했습니다: {e}")
            return pd.DataFrame(columns=VALUECHAIN_COLUMNS)
    return pd.DataFrame(columns=VALUECHAIN_COLUMNS)

def save_valuechain_data(df):
    """Value Chain 데이터를 저장합니다."""
    try:
        df.to_csv(VALUECHAIN_CSV_PATH, index=False, encoding="utf-8-sig")
        return True
    except Exception as e:
        st.error(f"Value Chain 파일 저장 중 오류가 발생했습니다: {e}")
        return False

def value_chain_tab(target_industry):
    """Value Chain Activity Management Tab"""
    st.markdown("### 📊 Value Chain Activity Definition")
    
    # 데이터 로드
    df = load_valuechain_data()
    
    # 현재 산업 데이터 필터링
    if "Industry" not in df.columns:
        st.error("데이터에 'Industry' 컬럼이 없습니다. 파일을 확인해주세요.")
        return
    
    industry_df = (
        df[df["Industry"] == target_industry]
        .sort_values("Activity_Seq")
        .reset_index(drop=True)
    )

    sub_tab = st.radio(
        "Value Chain 작업",
        ["📋 Activity List (Edit/Delete)", "➕ Add New Activity"],
        horizontal=True,
        key=f"vc_sub_tab_{target_industry}",
        label_visibility="collapsed",
    )

    if sub_tab == "📋 Activity List (Edit/Delete)":
        if industry_df.empty:
            st.info("등록된 활동이 없습니다. 'Add New Activity' 탭에서 첫 번째 항목을 추가하세요.")
        else:
            st.markdown("💡 **수정 방법:** 표 내부의 값을 직접 클릭하여 수정 후 하단 변경사항 저장 버튼을 클릭하세요.")
            st.markdown("**순번**은 중복이 되지 않도록 순차적으로 일련번호를 부여합니다.")
            
            edited_df = st.data_editor(
                industry_df,
                key=f"vc_editor_{target_industry}",
                num_rows="dynamic",
                width='stretch',
                hide_index=True,
                column_config={
                    "Industry": st.column_config.TextColumn("산업군", disabled=True),
                    "Activity_Seq": st.column_config.NumberColumn("순번", required=True, width="small"),
                    "Activity_Type": st.column_config.SelectboxColumn(
                        "구분", options=["Primary", "Support"], required=True, width="small"
                    ),
                    "Activity": st.column_config.TextColumn("활동명(영문)", required=True, width="medium"),
                    "Activity_Kor": st.column_config.TextColumn("활동명(한글)", required=True, width="medium"),
                    "Activity_Description": st.column_config.TextColumn("설명", width="large")
                },
            )
            
            if st.button("💾 변경사항 저장", key=f"vc_save_{target_industry}", type="primary"):
                # 한글 입력 체크
                invalid_names = [n for n in edited_df["Activity"] if not check_no_korean(n)]
                
                if invalid_names:
                    st.error(f"❌ Error: Activity Name (English) cannot contain Korean: {invalid_names}")
                else:
                    # Merge and save data
                    other_df = df[df["Industry"] != target_industry]
                    edited_df["Industry"] = target_industry
                    final_df = pd.concat([other_df, edited_df], ignore_index=True)
                    
                    if save_valuechain_data(final_df):
                        st.success("데이터가 성공적으로 저장되었습니다.")
                        _load_mapping_datasets.clear()
                        st.rerun()

    else:
        st.dataframe(
            industry_df,
            width='stretch',
            hide_index=True,
            column_config={
                "Industry": st.column_config.TextColumn("산업군"),
                "Activity_Seq": st.column_config.NumberColumn("순번", width="small"),
                "Activity_Type": st.column_config.SelectboxColumn("구분", width="small"),
                "Activity": st.column_config.TextColumn("활동명(영문)", width="medium"),
                "Activity_Kor": st.column_config.TextColumn("활동명(한글)", width="medium"),
                "Activity_Description": st.column_config.TextColumn("설명", width="large")
            },
            # width="stretch",
            height=300
        )
        with st.form("add_activity_form", clear_on_submit=True):
            st.markdown("##### ➕ Add New Activity")
            c1, c2, c3 = st.columns([1, 2, 2])
            with c1:
                a_type = st.selectbox("활동 구분", ["Primary", "Support"])
            with c2:
                a_name = st.text_input("Activity Name (English Only)")
            with c3:
                a_name_kor = st.text_input("Activity Name (Korean Name)")
            
            a_desc = st.text_area("Activity Description")
            
            submitted = st.form_submit_button("Register Value Chain Activity")
            
            if submitted:
                if not a_name or not a_name_kor:
                    st.warning("Activity Name (English and Korean) must be entered.")
                elif not check_no_korean(a_name):
                    st.error("❌ Error: Activity Name (English) cannot contain Korean.")
                else:
                    # Seq 자동 부여
                    next_seq = 1
                    if not industry_df.empty:
                        next_seq = industry_df["Activity_Seq"].max() + 1
                    
                    new_row = pd.DataFrame([{
                        "Industry": target_industry,
                        "Activity_Seq": next_seq,
                        "Activity_Type": a_type,
                        "Activity": a_name,
                        "Activity_Kor": a_name_kor,
                        "Activity_Description": a_desc
                    }])
                    
                    full_df = pd.concat([df, new_row], ignore_index=True)
                    if save_valuechain_data(full_df):
                        st.success(f"'{a_name}' Activity has been successfully registered.")
                        _load_mapping_datasets.clear()
                        st.rerun()

# -------------------------------------------------------------------
# 4. System 관련 함수
# -------------------------------------------------------------------
def load_system_data():
    """System 데이터를 로드합니다."""
    if SYSTEM_CSV_PATH.exists():
        try:
            return pd.read_csv(SYSTEM_CSV_PATH, encoding="utf-8-sig")
        except Exception as e:
            st.error(f"System 파일을 읽는 중 오류가 발생했습니다: {e}")
            return pd.DataFrame(columns=SYSTEM_COLUMNS)
    return pd.DataFrame(columns=SYSTEM_COLUMNS)

def save_system_data(df):
    """System 데이터를 저장합니다."""
    try:
        df.to_csv(SYSTEM_CSV_PATH, index=False, encoding="utf-8-sig")
        return True
    except Exception as e:
        st.error(f"System 파일 저장 중 오류가 발생했습니다: {e}")
        return False

def system_tab_old(target_industry):
    """System 관리 탭"""
    st.markdown("### 🏭 System Definition")
    
    # 데이터 로드
    df = load_system_data()
    
    # 현재 산업 데이터 필터링
    if "Industry" not in df.columns:
        st.error("데이터에 'Industry' 컬럼이 없습니다. 파일을 확인해주세요.")
        return
    
    industry_df = df[df["Industry"] == target_industry].sort_values("System_Seq")
    if "System_Color" in industry_df.columns:
        industry_df["System_Color"] = (
            industry_df["System_Color"]
            .astype("string")
            .fillna("")
        )
    
    # 서브 탭
    tab_list, tab_add = st.tabs(["📋 System List", "➕ Add New System"])
    
    # [Tab: 목록 및 수정/삭제]
    with tab_list:
        if industry_df.empty:
            st.info("등록된 System이 없습니다. 'Add New System' 탭에서 첫 번째 항목을 추가하세요.")
        else:
            st.markdown("💡 **수정 방법:** 표 내부의 값을 직접 클릭하여 수정 후 하단 변경사항 저장 버튼을 클릭하세요.")
            st.markdown("**순번** 은 중복이 되지 않도록 일련번호를 부여합니다.")
            
            edited_df = st.data_editor(
                industry_df,
                key=f"sys_editor_{target_industry}",
                num_rows="dynamic",
                width='stretch',
                hide_index=True,
                column_config={
                    "Industry": st.column_config.TextColumn("산업군", disabled=True),
                    "System_Seq": st.column_config.NumberColumn("순번", required=True, width="small"),
                    "System": st.column_config.TextColumn("System명(영문)", required=True, width="medium"),
                    "System_Kor": st.column_config.TextColumn("System명(한글)", required=True, width="medium"),
                    "System_Color": st.column_config.TextColumn("System 색상", width="small"),
                    "System_Description": st.column_config.TextColumn("설명", width="large")
                },
            )
            
            if st.button("💾 변경사항 저장", key=f"sys_save_{target_industry}", type="primary"):
                # 한글 입력 체크
                invalid_names = [n for n in edited_df["System"] if not check_no_korean(n)]
                
                if invalid_names:
                    st.error(f"❌ 오류: System명(영문)에 한글이 포함될 수 없습니다: {invalid_names}")
                else:
                    # 데이터 병합 및 저장
                    other_df = df[df["Industry"] != target_industry]
                    edited_df["Industry"] = target_industry
                    final_df = pd.concat([other_df, edited_df], ignore_index=True)
                    
                    if save_system_data(final_df):
                        st.success("데이터가 성공적으로 저장되었습니다.")
                        st.rerun()
    
    # [Tab: 새 System 등록]
    with tab_add:
        with st.form("add_system_form", clear_on_submit=True):
            st.markdown("##### ➕ 새로운 System 추가")
            st.dataframe(
                industry_df,
                width='stretch',
                hide_index=True,
                column_config={
                    "Industry": st.column_config.TextColumn("산업군"),
                    "System_Seq": st.column_config.NumberColumn("순번", width="small"),
                    "System": st.column_config.TextColumn("System명(영문)", width="medium"),
                    "System_Kor": st.column_config.TextColumn("System명(한글)", width="medium"),
                    "System_Color": st.column_config.TextColumn("System 색상", width="small"),
                    "System_Description": st.column_config.TextColumn("설명", width="large")
                },
                height=300
            )
            c1, c2, c3 = st.columns([1, 2, 2])
            with c1:
                System = st.text_input("System명 (English Only)")
            with c2:
                System_kor = st.text_input("System명 (한글 명칭)")
            with c3:
                System_color = st.color_picker("System 색상")
                if System_color:
                    System_color = System_color.lower()
            system_desc = st.text_area("System 상세 설명")
            
            submitted = st.form_submit_button("System 등록")
            
            if submitted:
                if not System or not System_kor:
                    st.warning("System명(영문 및 한글)을 모두 입력해 주세요.")
                elif not check_no_korean(System):
                    st.error("❌ System명(영문)에는 한글을 입력할 수 없습니다.")
                else:
                    # Seq 자동 부여
                    next_seq = 1
                    if not industry_df.empty:
                        next_seq = industry_df["System_Seq"].max() + 1
                    
                    new_row = pd.DataFrame([{
                        "Industry": target_industry,
                        "System_Seq": next_seq,
                        "System": System,
                        "System_Kor": System_kor,
                        "System_Color": System_color,
                        "System_Description": system_desc
                    }])
                    
                    full_df = pd.concat([df, new_row], ignore_index=True)
                    if save_system_data(full_df):
                        st.success(f"'{System}' System이 성공적으로 등록되었습니다.")
                        st.rerun()

# import streamlit as st
# import pandas as pd

def system_tab(target_industry):
    """System 관리 탭 - 시각적 요소 및 UI 개선 버전"""
    st.markdown(f"### 🏭 {target_industry} System Definition")
    
    # 데이터 로드
    df = load_system_data()
    
    # 현재 산업 데이터 필터링 및 전처리
    if "Industry" not in df.columns:
        st.error("데이터에 'Industry' 컬럼이 없습니다. 파일을 확인해주세요.")
        return
    
    industry_df = (
        df[df["Industry"] == target_industry]
        .sort_values("System_Seq")
        .reset_index(drop=True)
    )

    # 색상 데이터 보정 (문자열 변환 및 소문자화)
    if "System_Color" in industry_df.columns:
        industry_df["System_Color"] = (
            industry_df["System_Color"].astype(str).str.lower().replace("nan", "")
        )

    sub_tab = st.radio(
        "System 작업",
        ["📋 System List & Edit", "➕ Add New System"],
        horizontal=True,
        key=f"sys_sub_tab_{target_industry}",
        label_visibility="collapsed",
    )

    if sub_tab == "📋 System List & Edit":
        if industry_df.empty:
            st.info(f"'{target_industry}'에 등록된 System이 없습니다. 오른쪽 탭에서 첫 번째 항목을 추가하세요.")
        else:
            st.markdown("💡 **Tip:** 표 안의 값을 직접 수정하거나 행을 추가/삭제할 수 있습니다. 수정 후 반드시 아래 **저장 버튼**을 눌러주세요.")
            
            # 데이터 에디터 설정
            edited_df = st.data_editor(
                industry_df,
                key=f"sys_editor_{target_industry}",
                num_rows="dynamic",
                width='stretch',
                hide_index=True,
                column_config={
                    "Industry": st.column_config.TextColumn("산업군", disabled=True),
                    "System_Seq": st.column_config.NumberColumn("순번", help="표시 순서", required=True, width="small"),
                    "System": st.column_config.TextColumn("System명(영문)", help="영문명만 입력 가능", required=True),
                    "System_Kor": st.column_config.TextColumn("System명(한글)", required=True),
                    # 색상 컬럼을 텍스트 대신 미리보기나 선택박스로 운영 가능 (여기선 텍스트 유지하되 설명 추가)
                    "System_Color": st.column_config.TextColumn("색상 코드", help="Hex 코드 (예: #ff4b4b)"),
                    "System_Description": st.column_config.TextColumn("상세 설명", width="large")
                },
            )
            
            save_col1, save_col2 = st.columns([1, 5])
            with save_col1:
                save_btn = st.button("💾 변경사항 저장", key=f"sys_save_{target_industry}", type="primary")
            
            if save_btn:
                # 유효성 검사 (영문명 한글 포함 여부)
                invalid_names = [n for n in edited_df["System"] if not check_no_korean(str(n))]
                
                if invalid_names:
                    st.error(f"❌ 오류: 영문명에 한글이 포함된 항목이 있습니다: {invalid_names}")
                else:
                    # 데이터 병합 프로세스
                    other_df = df[df["Industry"] != target_industry]
                    edited_df["Industry"] = target_industry  # 새로 추가된 행 대비
                    # 색상 코드 표준화
                    if "System_Color" in edited_df.columns:
                        edited_df["System_Color"] = edited_df["System_Color"].astype(str).str.lower()
                    
                    final_df = pd.concat([other_df, edited_df], ignore_index=True)
                    
                    if save_system_data(final_df):
                        st.success("🎉 데이터가 성공적으로 반영되었습니다.")
                        _load_mapping_datasets.clear()
                        st.rerun()

    else:
        st.markdown("##### ➕ 새로운 System 상세 등록")
        
        with st.form("add_system_form", clear_on_submit=True):
            # 레이아웃 정돈
            row1_c1, row1_c2 = st.columns(2)
            with row1_c1:
                new_sys_en = st.text_input("System명 (English Only) *", placeholder="E.g., ERP_SYSTEM")
            with row1_c2:
                new_sys_kor = st.text_input("System명 (한글 명칭) *", placeholder="예: 전사자원관리")
            
            row2_c1, row2_c2, row2_c3 = st.columns([1, 1, 2])
            with row2_c1:
                # Seq 자동 계산 시각화
                next_seq_val = 1 if industry_df.empty else int(industry_df["System_Seq"].max() + 1)
                st.info(f"다음 순번: **{next_seq_val}**")
            with row2_c2:
                # 컬러 피커
                new_color = st.color_picker("시스템 테마 색상", "#1b6cff")
            with row2_c3:
                st.write("") # 간격 맞춤용
                st.caption("선택한 색상은 대시보드 및 리포트의 테마로 사용됩니다.")
            
            new_desc = st.text_area("System 상세 설명", placeholder="해당 시스템의 주요 목적과 기능을 입력하세요.")
            
            # 제출 버튼
            submitted = st.form_submit_button("🚀 System 등록하기", use_container_width=True)
            
            if submitted:
                if not new_sys_en or not new_sys_kor:
                    st.warning("⚠️ 필수 항목(영문/한글 명칭)을 모두 입력해 주세요.")
                elif not check_no_korean(new_sys_en):
                    st.error("❌ 영문 명칭에는 한글을 사용할 수 없습니다.")
                else:
                    # 신규 데이터 구성
                    new_row = pd.DataFrame([{
                        "Industry": target_industry,
                        "System_Seq": next_seq_val,
                        "System": new_sys_en,
                        "System_Kor": new_sys_kor,
                        "System_Color": new_color.lower(),
                        "System_Description": new_desc
                    }])
                    
                    # 저장 및 갱신
                    full_df = pd.concat([df, new_row], ignore_index=True)
                    if save_system_data(full_df):
                        st.success(f"✅ '{new_sys_kor}' 시스템이 성공적으로 추가되었습니다.")
                        _load_mapping_datasets.clear()
                        st.rerun()

        if not industry_df.empty:
            with st.expander("현재 등록된 시스템 요약 보기"):
                st.table(industry_df[["System_Seq", "System", "System_Kor", "System_Color"]])
# -------------------------------------------------------------------
# 5. File 매핑 관련 함수
# -------------------------------------------------------------------
def load_data_validation():
    """File 매핑에 필요한 데이터를 로드하고 검증합니다."""
    missing = [
        p.name for p in (VALUECHAIN_CSV_PATH, SYSTEM_CSV_PATH, FILE_STATS_PATH, FILE_FORMAT_PATH)
        if not p.exists()
    ]
    if missing:
        st.error(f"❌ 필요한 파일이 없습니다: {', '.join(missing)}. 먼저 파일 분석을 수행하세요.")
        return None, None, None, None

    result = _load_mapping_datasets()
    if result is None:
        st.error("❌ 필요한 데이터 파일이 없거나 내용이 비어 있습니다. 먼저 파일 분석을 수행하세요.")
        return None, None, None, None
    return result

def mapping_file_tab(target_industry):
    """File Mapping Management Tab"""
    st.markdown("### 🔗 Value Chain & System 에 파일을 매핑합니다.")
    st.markdown("##### 파일별로 연관된 Value Chain의 Activity와 System을 매핑합니다.")
    
    # 데이터 로드
    df_vc, df_sys, df_stats, df_format = load_data_validation()
    if df_vc is None or df_sys is None or df_stats is None or df_format is None:
        st.warning("⚠️ 필요한 데이터 파일이 없습니다. 먼저 파일 분석을 수행하세요.")
        return
    
    # Prepare option data (based on selected Industry)
    activity_options = [""] + df_vc[df_vc["Industry"] == target_industry]["Activity"].tolist()
    system_options = [""] + df_sys[df_sys["Industry"] == target_industry]["System"].tolist()

    # Load and merge existing mapping data
    df_mapping_exist = load_csv(MAPPING_CSV_PATH, mode=0)
    
    # Merge mapping information based on FileStats (Left Join)
    display_df = df_stats.copy()

    if df_mapping_exist is not None and not df_mapping_exist.empty:
        # 해당 산업군의 데이터만 필터링하여 병합 (FileName 중복 제거)
        industry_mapping = (
            df_mapping_exist[df_mapping_exist["Industry"] == target_industry]
            .drop_duplicates(subset=["FileName"], keep="last")
        )
        if not industry_mapping.empty:
            display_df = pd.merge(
                display_df,
                industry_mapping[["FileName", "Activity", "System"]],
                on="FileName",
                how="left",
            )
        else:
            display_df["Activity"] = ""
            display_df["System"] = ""
    else:
        display_df["Activity"] = ""
        display_df["System"] = ""

    # 결측치 처리
    display_df["Activity"] = display_df["Activity"].fillna("")
    display_df["System"] = display_df["System"].fillna("")
    display_df = display_df.reset_index(drop=True)

    # 데이터 편집기
    # st.subheader(f"📍 [{target_industry}] File Mapping List")
    st.caption("입력방법: Activity 또는 System 컬럼을 클릭하여 등록된 항목을 선택하세요. 내용을 비우면 매핑이 해제됩니다.")

    edited_df = st.data_editor(
        display_df,
        key=f"mapping_editor_{target_industry}",
        width='stretch',
        hide_index=True,
        column_config={
            "FileNo": st.column_config.NumberColumn("No", disabled=True),
            "FileName": st.column_config.TextColumn("파일명", disabled=True),
            "FileSize": st.column_config.NumberColumn("크기", disabled=True),
            "RecordCnt": st.column_config.NumberColumn("행 수", disabled=True),
            "ColumnCnt": st.column_config.NumberColumn("컬럼 수", disabled=True),
            "PK_List": st.column_config.TextColumn("PK 컬럼", disabled=True),
            "Activity": st.column_config.SelectboxColumn(
                "Value Chain", 
                options=activity_options,
                help="이 파일과 관련된 Value Chain의 Activity를 선택하세요."
            ),
            "System": st.column_config.SelectboxColumn(
                "System", 
                options=system_options,
                help="이 파일이 속한 시스템을 선택하세요."
            )
        }
    )

    # 저장 로직
    if st.button("💾 매핑 정보 저장", key=f"mapping_save_{target_industry}", type="primary"):
        # 저장할 데이터 구성
        new_mapping_data = edited_df.copy()
        new_mapping_data["Industry"] = target_industry
        
        # 필요한 컬럼만 추출 (매핑 결과 파일 구조)
        final_save_cols = ["Industry", "FileName", "Activity", "System"]
        current_industry_df = new_mapping_data[final_save_cols]

        # 기존 전체 매핑 파일에서 현재 산업군 데이터 교체
        if MAPPING_CSV_PATH.exists():
            full_mapping_df = load_csv(MAPPING_CSV_PATH)
            if full_mapping_df is not None and not full_mapping_df.empty:
                # 다른 산업군 데이터 보존
                other_industries_df = full_mapping_df[full_mapping_df["Industry"] != target_industry]
                final_df = pd.concat([other_industries_df, current_industry_df], ignore_index=True)
            else:
                final_df = current_industry_df
        else:
            final_df = current_industry_df

        # 저장
        save_csv(final_df, MAPPING_CSV_PATH)
        st.success(f"🎉 [{target_industry}] Mapping information has been successfully saved.")
        _load_mapping_datasets.clear()
        st.rerun()
    
    # 파일 상세 검색
    st.divider()
    st.subheader("🔍 파일 상세 검색 (No로 검색)")
    file_no = st.number_input("No", key=f"file_no_{target_industry}", min_value=1, format="%d")

    format_cols = ["FileName", "ColumnName", "OracleType", "PK", "ValueCnt", "Null(%)", "Unique(%)", 
                   "FormatCnt", "Format", "Top10"]

    if st.button("🔍 검색", key=f"search_{target_industry}"):
        if file_no:
            df_file = df_format[df_format["FileNo"] == file_no]
            if not df_file.empty:
                st.dataframe(df_file[format_cols], width='stretch', hide_index=True, height=500)
            else:
                st.error("🔍 해당 No의 파일이 없습니다.")

# -------------------------------------------------------------------
# 6. 메인 UI 함수
# -------------------------------------------------------------------
def main():
    st.title(APP_NAME)
    st.markdown(APP_DESC)
    # st.markdown("##### This is a unified tool to manage Value Chain, System Definition and File Mapping by Industry.")
    
    with st.expander("Value Chain 예제 이미지 보기", expanded=False):
        show_sample_image("Sample_ValueChain_Licened.jfif", "Value Chain Image")
    # --- [Section 1: Industry Selection and Management] ---
    st.markdown("### 1️⃣ Select Industry")
    
    # Collect all Industry list (Value Chain + System)
    existing_industries = get_all_industries()
    
    # 메인 화면에 산업군 선택 박스 배치
    col_sel, col_new = st.columns([2, 3])
    
    with col_sel:
        selection = st.selectbox(
            "Registered Industry List",
            options=["-- Select --", "+ Add New Industry"] + existing_industries,
            index=0,
            key="industry_selection"
        )
    
    target_industry = ""
    with col_new:
        if selection == "+ Add New Industry":
            new_ind = st.text_input("Add New Industry Name", key="new_industry_input")
            if new_ind:
                target_industry = new_ind
        elif selection != "-- Select --":
            target_industry = selection
    
    # Industry가 선택되지 않은 경우 중단
    if not target_industry:
        st.info("Please select or add a new Industry to manage.")
        return
    
    # st.subheader(f"📍 대상 산업: {target_industry}")
    st.info("📌 **다음 탭을 순차적으로 수행하세요.**")
    
    # --- [섹션 2: 메인 탭] (선택한 탭만 실행 — st.tabs는 숨은 탭까지 매번 실행됨) ---
    main_tab_labels = [
        "📊 Value Chain Definition",
        "🏭 System Definition",
        "🔗 Map Value Chain & System to File",
    ]
    main_tab = st.radio(
        "작업 구분",
        main_tab_labels,
        horizontal=True,
        key="vc_sys_main_tab",
        label_visibility="collapsed",
    )

    if main_tab == main_tab_labels[0]:
        value_chain_tab(target_industry)
    elif main_tab == main_tab_labels[1]:
        system_tab(target_industry)
    else:
        mapping_file_tab(target_industry)

# --- 실행부 ---
if __name__ == "__main__":
    main()
