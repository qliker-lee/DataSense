###################################################
# 2025. 12. 29.  Qliker
# DataSense Solution Main Portal 
###################################################
import streamlit as st
import sys
from pathlib import Path

# 1. 경로 설정 및 환경 초기화
CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parent
# 여러 가능한 경로 시도 (로컬/Cloud 환경 대응)
IMAGE_DIR = PROJECT_ROOT /"images_sample" 

from util.streamlit_warnings import setup_streamlit_warnings
setup_streamlit_warnings()

# 페이지 기본 설정 (와이드 레이아웃 적용)
st.set_page_config(
    page_title="DataSense | 가시성 중심의 데이터 거버넌스",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS (고급스러운 대시보드 느낌)
st.markdown("""
    <style>
    .main-title { font-size: 42px; font-weight: 800; color: #1E3A8A; margin-bottom: 10px; }
    .sub-title { font-size: 20px; color: #4B5563; margin-bottom: 30px; }
    .card { background-color: #F8FAFC; padding: 25px; border-radius: 15px; border-left: 5px solid #2563EB; margin-bottom: 20px; }
    .feature-header { font-size: 22px; font-weight: 700; color: #1E40AF; margin-bottom: 10px; }
    .highlight { color: #EA580C; font-weight: bold; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; background-color: #2563EB; color: white; }
    </style>
    """, unsafe_allow_html=True)

def login_section():
    """로그인 섹션 (사이드바)"""
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/database.png", width=80)
        st.markdown("### **Solution Access**")
        with st.form("login_form"):
            user = st.text_input("User Name")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("인증 및 접속"):
                if user == "qliker" and pw == "votmdnjem":
                    st.session_state["logged_in"] = True
                    st.success("인증 성공!")
                    st.rerun()
                else:
                    st.error("인증 정보가 올바르지 않습니다.")
        
        st.divider()
        st.info("💡 **DataSense v2.5**\n\n데이터의 흐름에서 비즈니스의 가치를 찾는 가장 빠른 방법")

def intro_page():
    """소개자료 컨텐츠 기반 메인 대시보드"""
    
    st.info('#### 데이터의 흐름에서 비즈니스의 가치를 찾다.')
    st.markdown("**자동화된 데이터 품질(DQ) 관리** 및 가치 사슬(Value Chain) 기반"
        "<b> 상위 데이터 아키텍쳐 정립</b>을 위한 통합 분석 플랫폼", unsafe_allow_html=True)

    st.divider()

    # 1. 핵심 철학 (Core Philosophy)
    st.markdown("### 🎯 Our Philosophy")
    st.info('#### "데이터는 비즈니스의 언어다" (Data as a Business Language)')
    st.write("단순히 데이터를 쌓는 것을 넘어, 원천 데이터 프로파일링부터 비즈니스 가치 사슬까지 연결하여 **데이터의 생성-흐름-품질**을 통합 관리합니다.")
    
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
    pdf_paths = [  # 여러 가능한 경로를 순차적으로 시도
        IMAGE_DIR / "DataSense_Solution_Overview.pdf",
    ]
    
    pdf_found = None
    for pdf_path in pdf_paths:
        if pdf_path.exists():
            pdf_found = pdf_path
            break
        else:
            st.write(f"소개자료 파일을 찾을 수 없습니다: {pdf_path}")
    
    if pdf_found:
        with open(pdf_found, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
            st.download_button(
                label="📄 DataSense Solution Overview Download (PDF)",
                data=pdf_bytes,
                file_name="DataSense_Solution_Overview.pdf",
                mime="application/pdf",
                type="primary"
            )


def sidebar():
    st.sidebar.markdown("""
        <div style='background-color: #F0F8FF; padding: 10px; border-radius: 10px; margin: 10px;'>
        <p style='font-size: 16px; color: #333; line-height: 1.6;'>
            Data has <span style='color: #cc3300; font-weight: bold;'> a value.</span><br>
            Data is<span style='font-size: 16px; color: #cc3300; font-weight: bold;'> an asset.</span><br>
            Data shapes <span style='font-size: 16px; color: #cc3300; font-weight: bold;'> our future.</span>
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.sidebar.markdown("")
    st.sidebar.markdown("<h4>qliker@kakao.com</h4>", unsafe_allow_html=True)

def main():
            
    st.title("🏛️ DataSense 란?")
    sidebar()

    intro_page()
    download_solution_pdf()


if __name__ == "__main__":
    main()