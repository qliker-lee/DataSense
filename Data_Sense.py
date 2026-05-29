###################################################
# 2025. 12. 29.  Qliker
# DataSense Solution Main Portal 
###################################################
import streamlit as st
import sys
from pathlib import Path

# 
# # -------------------------------------------------------------------
# 기본 앱 정보
# -------------------------------------------------------------------
# 1. 경로 설정 및 환경 초기화
CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parent
IMAGE_SAMPLE_DIR = PROJECT_ROOT / "images_sample"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

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
from util.streamlit_warnings import setup_streamlit_warnings
from util.Files_FunctionV20 import set_page_config

APP_NAME = "DataSense Solution Main Portal"

setup_streamlit_warnings()
set_page_config(APP_NAME)

# -------------------------------------------------------------------

# 커스텀 CSS (고급스러운 대시보드 느낌)
st.markdown("""
    <style>
    .main-title { font-size: 42px; font-weight: 800; color: #1E3A8A; margin-bottom: 10px; }
    .sub-title { font-size: 20px; color: #4B5563; margin-bottom: 30px; }
    .card { background-color: #000000; color: #E5E7EB; padding: 25px; border-radius: 15px; border-left: 5px solid #2563EB; margin-bottom: 20px; }
    .card b { color: #F9FAFB; }
    .feature-header { font-size: 22px; font-weight: 700; color: #93C5FD; margin-bottom: 10px; }
    .highlight { color: #EA580C; font-weight: bold; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; background-color: #2563EB; color: white; }
    </style>
    """, unsafe_allow_html=True)

# def login_section():
#     """로그인 섹션 (사이드바)"""
#     with st.sidebar:
#         st.image("https://img.icons8.com/fluency/96/database.png", width=80)
#         st.markdown("### **Solution Access**")
#         with st.form("login_form"):
#             user = st.text_input("User Name")
#             pw = st.text_input("Password", type="password")
#             if st.form_submit_button("인증 및 접속"):
#                 if user == "qliker" and pw == "votmdnjem":
#                     st.session_state["logged_in"] = True
#                     st.success("인증 성공!")
#                     st.rerun()
#                 else:
#                     st.error("인증 정보가 올바르지 않습니다.")
        
#         st.divider()
#         st.info("💡 **DataSense v2.5**\n\n데이터의 흐름에서 비즈니스의 가치를 찾는 가장 빠른 방법")

def intro_page():
    """소개자료 컨텐츠 기반 메인 대시보드"""

    c11, c12 = st.columns([4, 2])
    with c11:
        st.info('#### "데이터의 흐름에서 비즈니스의 가치를 찾는다" (Find Value in the data)')
        st.markdown("###### - 자동화된 데이터 품질(DQ) 관리 및 가치 사슬(Value Chain) 기반")
        st.markdown("###### - 상위 데이터 아키텍쳐 정립을 위한 통합 분석 플랫폼")
    with c12:
        st.image("images_sample/Sample_Data2Business.png", width=300)        

    st.divider()
    c21, c22 = st.columns([4, 2])
    with c21:
        st.markdown("### 🎯 Our Philosophy")
        st.info('#### "데이터는 비즈니스의 언어" (Data as a Business Language)')
        st.markdown("###### - 단순히 데이터를 쌓는 것을 넘어,") 
        st.markdown("###### - 데이터 프로파일링부터 비즈니스 가치 사슬(Value Chain)까지 연결하여")
        st.markdown("###### - **데이터의 생성-흐름-품질**을 통합 관리합니다.")
    with c22:
        st.image("images_sample/Sample_DataisBusinessLanguage.png", width=300)


    # 2. 주요 기능 (Key Capabilities) - 3컬럼 레이아웃
    st.divider()
    st.markdown("### 🚀 Key Capabilities")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown('<div class="card"><p class="feature-header">🔍 Intelligent Data Profiling & Statistics</p>'
                    '결측치, 형식 준수율, 유니크 값 비율 자동 산출<br>'
                    '<b>유니코드, 미완성한글</b> 등 기술 결함 탐지<br>'
                    '데이터 값에 대한 다양한 <b>통계 분석</b></div>'
                    , unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card"><p class="feature-header">⛓️ ERD & Logical Data Relationship Diagram</p>'
                    '운영중인 시스템의 <b>ERD</b> 생성 및 확인<br>'
                    '데이터 값 기반의 <b>논리 다이어그램</b> 작성<br>'
                    '<b>참조코드(Reference Code)</b> 비교로 정합성 검증</div>'
                    , unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="card"><p class="feature-header">🏗️ Business Value Chain & System Mapping</p>'
                    '산업군별 <b>Primary/Support Activity</b> 정의<br>'
                    '<b>Activity 와 System 간 매핑</b> 및 파일 매핑<br>'
                    'Activity-to-System & File 분석으로 상위 <b>데이터 아키텍쳐 정립</b></div>', unsafe_allow_html=True)

    # 3. 비포/애프터 시나리오 (Business Scenarios)
    st.divider()
    st.markdown("### 💡 Business Transformation")
    with st.expander("✅ 시나리오: 특정 컬럼/구조 변경 시 영향도 파악", expanded=True):
        sc1, sc2 = st.columns(2)
        sc1.write("**Before**")
        sc1.error("배포 후 리포트가 깨진 뒤에야 원인 파악 (보수적 운영) → 시간 소요")
        sc2.write("**After**")
        sc2.success("변경 전 연관 관계 즉시 확인, 리스크 사전 제거")
    
    with st.expander("✅ 시나리오: 신규 인력 온보딩 및 인수인계"):
        sc3, sc4 = st.columns(2)
        sc3.write("**Before**")
        sc3.error("과거 문서 중심 설명으로 구조 이해까지 수주 소요")
        sc4.write("**After**")
        sc4.success("논리적 ERD 기반 분석으로 단기간에 업무 투입 가능 (기간 50% 단축) → 효율성 향상")

    # 4. 기대 효과 (Expected Benefits)
    st.divider()
    st.markdown("### 📈 Solution Expected Benefits")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("영향 분석 시간", "75% 감소")
    b2.metric("데이터 신뢰도", "99% 달성")
    b3.metric("온보딩 기간", "50% 단축")
    b4.metric("의사결정 속도", "2배 향상")

def download_solution_pdf():
    """소개자료를 다운로드 합니다."""
    SOLUTION_OVERVIEW_FILE = "DataSense_Solution_Overview.pdf"
    SOLUTION_WHITEPAPER_FILE = "DataSense WhitePaper_202601.pdf"

    st.divider()
    st.markdown("##### 📄 자세한 내용은 소개자료를 다운로드하여 확인하세요.")

    overview_path = IMAGE_SAMPLE_DIR / SOLUTION_OVERVIEW_FILE
    whitepaper_path = IMAGE_SAMPLE_DIR / SOLUTION_WHITEPAPER_FILE

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if overview_path.exists():
            with open(overview_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()
                st.download_button(
                    label="📄 DataSense Solution Overview ",
                    data=pdf_bytes,
                    file_name="DataSense_Solution_Overview.pdf",
                    mime="application/pdf",
                    type="primary"
                )
        else:
            st.write(f"소개자료 파일을 찾을 수 없습니다: {overview_path}")
    with col2:
        if whitepaper_path.exists():
            with open(whitepaper_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()
                st.download_button(
                    label="📄 DataSense WhitePaper",
                    data=pdf_bytes,
                    file_name="DataSense_WhitePaper.pdf",
                    mime="application/pdf",
                    type="primary"
                )
        else:
            st.write(f"소개자료 파일을 찾을 수 없습니다: {whitepaper_path}")

def display_datasense_overview():
    """
    DataSense 솔루션을 구성하는 주요 프로그램들을 카테고리별로 소개하는 함수
    첫 화면(Landing Page)에서 호출하여 사용합니다.
    """
    st.title("🚀 DataSense Integrated Solution Overview")
    st.markdown("""
    **DataSense**는 데이터 프로파일링부터 품질 분석, 관계 시각화, 그리고 개인정보 보호까지 
    데이터의 전 생애주기를 관리하는 통합 데이터 거버넌스 솔루션입니다.
    """)

    st.divider()

    # 1. 핵심 영역 메트릭 (시각적 강조)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Profiling", "Step 01", help="데이터 탐색 및 기본 분석")
    m2.metric("Relationship", "Step 02", help="데이터 간 연관성 및 흐름 파악")
    m3.metric("Quality", "Step 03", help="데이터 정합성 및 품질 진단")
    m4.metric("Privacy", "Step 04", help="개인식별정보(PII) 탐지 및 보호")

    st.markdown("### 🛠️ Solution Modules")

    # 2. 카테고리별 프로그램 소개 (Tabs 활용)
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 Discovery & Profiling", 
        "🔗 Relationship & Map", 
        "✅ Quality & Consistency", 
        "🛡️ Privacy & Compliance"
    ])

    with tab1:
        st.markdown("#### 데이터 기초 분석 및 정제")
        c1, c2 = st.columns(2)
        with c1:
            st.info("**11. Data Analyzer (Profiling)**\n\n데이터셋의 전체 구조와 분포를 자동 분석하여 기초 통계 및 특성 라벨링을 수행합니다.")
        with c2:
            st.info("**34. Character Analysis**\n\n깨진 한글, 특수문자, 유니코드 분석을 통해 데이터 정제 및 클렌징 포인트를 도출합니다.")

    with tab2:
        st.markdown("#### 데이터 참조 및 비즈니스 연관 관계")
        cols = st.columns(2)
        with cols[0]:
            st.success("**23. Physical & Logical Diagram**\n\n물리적/논리적 참조 관계를 Graphviz로 시각화하여 데이터 흐름을 추적합니다.")
            st.success("**26. Value Chain & System Diagram**\n\n비즈니스 밸류체인과 IT 시스템 간의 매핑 정보를 다이어그램으로 제공합니다.")
        with cols[1]:
            st.success("**28. Relationship & Reliability Map**\n\n데이터 간의 유사도와 매칭율을 기반으로 참조 무결성 및 신뢰도를 시각화합니다.")
            st.success("**30. Data Relationship Analysis**\n\n물리적 관계를 넘어선 논리적 연관 관계를 분석하고 요약합니다.")

    with tab3:
        st.markdown("#### 데이터 품질 관리 및 이력")
        cols = st.columns(2)
        with cols[0]:
            st.warning("**31. Data Quality Analysis**\n\n데이터 프로파일링 결과를 바탕으로 품질 규칙 준수 여부 및 오류 지표를 산출합니다.")
            st.warning("**32. Data Consistency Analysis**\n\n동일 컬럼의 형식이 여러 파일에서 일관되게 관리되는지 분석합니다.")
        with cols[1]:
            st.warning("**33. Code Change Analysis**\n\n데이터의 코드값 변동 이력 및 통계적 변화를 추적하여 변동성을 관리합니다.")

    with tab4:
        st.markdown("#### 개인정보 보호 및 규제 대응")
        st.error("**41. PII Integrated Analyzer**\n\n데이터 패턴과 컬럼 유사도 분석을 통해 개인식별정보(PII)를 자동 탐지하고 사용자가 직접 확정합니다.")
        st.caption("※ 식별된 PII 정보는 후속 개인정보 참조 맵(42번)과 실시간 연동됩니다.")

    st.divider()

    # 3. 하단 안내 및 바로가기
    st.info("💡 **Tip**: 왼쪽 사이드바 메뉴를 통해 각 프로그램의 상세 기능을 실행할 수 있습니다.")

def main():           
    st.markdown(
        '<h1 style="margin: 0;">🏛️ Data<span style="color:#FF0000;">S</span>ense 란?</h1>',
        unsafe_allow_html=True,
    )
    # sidebar()

    intro_page()

    download_solution_pdf()

    st.divider()
    with st.expander("📄 DataSense Solution Overview 상세 설명"):
        display_datasense_overview()

if __name__ == "__main__":
    main()