# util/ds_generate_ERD.py
# 2026.01.09 Qliker (New Version)
# 물리적, 논리적 ERD 생성에 필요한 함수 정의 
# 
import streamlit as st  
from PIL import Image
from pathlib import Path
import graphviz
import pandas as pd 

# root 경로 설정 (root 경로는 util 폴더의 상위 폴더)
ROOT_DIR = Path(__file__).parent.parent
IMAGE_SAMPLE_DIR = ROOT_DIR / "images_sample"
IMAGE_DIR = ROOT_DIR / "images"
IMAGE_FILE = "Datasense_DRD"

def show_example_erd_images():
    st.info("""
    **Cloud 환경에서는 Graphviz 실행이 제한됩니다.**
    실제 Data Relationship Diagram 대신 생성된 예제 이미지를 표시합니다.
    """)
    try:
        tab1, tab2, tab3 = st.tabs(["예제 (Physical ERD)", "예제 (Logical ERD)", "예제 (Physical & Logical ERD)"])
        with tab1:
            img1_path = IMAGE_SAMPLE_DIR / "ERD_Physical_Sample.png"
            if img1_path.exists():
                img1 = Image.open(img1_path)
                st.image(img1, caption="예제 (Physical ERD)", width=1000)
                with open(img1_path, "rb") as f:
                    st.download_button(
                        label=f"💾 Physical ERD 다운로드 ",
                        data=f.read(),
                        file_name=f"ERD_Physical_Sample.png",
                        mime="image/png",
                        key=f"dl_ERD_Physical_Sample.png"
                    )
        with tab2:
            img2_path = IMAGE_SAMPLE_DIR / "ERD_Logical_Sample.png"
            if img2_path.exists():
                img2 = Image.open(img2_path)
                st.image(img2, caption="예제 (Logical ERD)", width=1000)
                with open(img2_path, "rb") as f:
                    st.download_button(
                        label=f"💾 Logical ERD 다운로드 ",
                        data=f.read(),
                        file_name=f"ERD_Logical_Sample.png",
                        mime="image/png",
                        key=f"dl_ERD_Logical_Sample.png"
                    )
        with tab3:
            img3_path = IMAGE_SAMPLE_DIR / "ERD_Physical & Logical_Sample.png"
            if img3_path.exists():
                img3 = Image.open(img3_path)
                st.image(img3, caption="예제 (Physical & Logical ERD)", width=1000)
                with open(img3_path, "rb") as f:
                    st.download_button(
                        label=f"💾 Physical & Logical ERD 다운로드 ",
                        data=f.read(),
                        file_name=f"ERD_Physical & Logical_Sample.png",
                        mime="image/png",
                        key=f"dl_ERD_Physical & Logical_Sample.png"
                    )
            st.info("🔵 파란색: Physical 연결만 | 🔴 빨간색: Logical 연결만 | 🟣 보라색: 두 연결 모두")

    except Exception as e:
        st.error(f"예제 이미지 로드 실패: {e}")



def display_erd_with_download(dot: graphviz.Digraph, suffix: str, related_tables_info: list = None) -> bool:
    """
    ERD 이미지를 표시하고 하단에 사용된 테이블 상세 정보를 출력함
    dot: graphviz.Digraph 객체
    suffix: 이미지 파일명 접미사
    related_tables_info: 사용된 테이블 상세 정보 리스트
    return: 성공 여부
    """
    
    file_name = f"ERD_{suffix}"
    output_path = IMAGE_DIR / "Physical_ERD" #file_name
    image_path = f"{output_path}.png"
    
    try:
        # 1. DPI 동적 조절 테이블 수가 100개 넘으면 dpi를 100으로 설정, 50개가 넘어가면 150, 그 이하는 300
        table_count = len(related_tables_info) if related_tables_info is not None else 0
        current_dpi = '300' if table_count < 50 else '150' if table_count < 100 else '100'
        
        dot.attr(dpi=current_dpi)
        dot.render(str(output_path), format='png', cleanup=True)
        
        # 2. 이미지 표시
        if Path(image_path).exists():
            st.write("---")
            with Image.open(image_path) as img:
                st.image(img, caption=f"Physical ERD - {suffix}", use_container_width=True)

            # 3. 다운로드 버튼
            with open(image_path, "rb") as file:
                st.download_button(
                    label="💾 ERD 이미지 다운로드 (PNG)",
                    data=file,
                    file_name=f"{file_name}.png",
                    mime="image/png"
                )
            
            # 4. [추가] 사용된 테이블 정보 데이터프레임 출력
            if related_tables_info is not None:
                st.write("### 📋 다이어그램 포함 테이블 명세")
                # 관련 정보를 보기 좋게 정리
                info_df = pd.DataFrame(related_tables_info)
                st.dataframe(info_df, use_container_width=True)

    except Exception as e:
        st.error(f"❌ 이미지 처리 중 오류 발생: {e}")
        st.info("💡 팁: 탐색 레벨(Depth)을 낮추거나 중심 테이블을 변경하여 이미지 크기를 줄여보세요.")
