# -*- coding: utf-8 -*-
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
from graphviz import Digraph

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
# 1. 경로 설정
CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
OUTPUT_DIR = PROJECT_ROOT / "DS_Output"

@st.cache_data
def load_rel_data():
    rel_path = OUTPUT_DIR / 'CodeMapping_erd.csv'
    if not rel_path.exists():
        st.error(f"데이터를 찾을 수 없습니다: {rel_path}")
        return pd.DataFrame()
    return pd.read_csv(rel_path)

def get_match_color(score):
    """매칭율에 따른 노드 색상 반환"""
    try:
        val = float(score)
        if val >= 90: return "#C8E6C9" # 녹색 (안정)
        if val >= 70: return "#FFF9C4" # 노랑 (주의)
        if val > 0:   return "#FFCDD2" # 빨강 (위험)
    except:
        pass
    return "#F5F5F5" # 회색 (데이터 없음)

def trace_column_relationships_with_score(df, selected_file):
    """참조 관계와 함께 매칭율(Score) 정보를 추출"""
    rel_data = [] # (source, target, score) 튜플 리스트
    file_rows = df[df['FileName'] == selected_file]
    
    for _, row in file_rows.iterrows():
        current_node = f"{selected_file}\n({row['ColumnName']})"
        
        for i in range(1, 5):
            ref_col = row.get(f'Level{i}_Column')
            ref_file = row.get(f'Level{i}_File')
            ref_score = row.get(f'Level{i}_Matched(%)')
            
            if pd.notna(ref_col) and pd.notna(ref_file) and str(ref_file).strip():
                reference_node = f"{ref_file}\n({ref_col})"
                # 관계 저장 (출발, 도착, 점수)
                rel_data.append({
                    'src': current_node,
                    'tgt': reference_node,
                    'score': ref_score if pd.notna(ref_score) else 0,
                    'is_self': True if str(ref_file).strip() == selected_file else False
                })
                current_node = reference_node
            else:
                break
    return rel_data

def select_file(df_rel):
    st.write("---")
    # st.dataframe(df_rel, width='stretch', hide_index=True)

    # 파일별 컬럼수, Level_Depth > 0 이상인 컬럼수, 참조 관계수, 매칭율 평균, 매칭율 표준편차
    df = df_rel.groupby('FileName').agg(
        ColumnCnt=('ColumnName', 'count'),
        LevelDepthCnt=('Level_Depth', lambda x: (x > 0).sum()),
    ).reset_index()

    # LevelDepthCnt 이름을 참조 관계수로 변경
    df.rename(columns={'LevelDepthCnt': 'RelationshipCnt'}, inplace=True)

    # 첫번째 컬럼에 select 컬럼 추가
    df.insert(0, 'select', False)

    for _c in ("ColumnCnt", "RelationshipCnt"):
        if _c in df.columns:
            df[_c] = pd.to_numeric(df[_c], errors="coerce").fillna(0)

    def _rel_map_prog_max(col: str) -> float:
        if col not in df.columns:
            return 1.0
        m = df[col].max()
        return max(float(m), 1.0) if pd.notna(m) else 1.0

    _max_colcnt = _rel_map_prog_max("ColumnCnt")
    _max_relcnt = _rel_map_prog_max("RelationshipCnt")

    edited_df = st.data_editor(
        df,
        width="stretch",
        hide_index=True,
        height=500,
        column_config={
            "select": st.column_config.CheckboxColumn("select", help="파일 선택"),
            "FileName": st.column_config.TextColumn("FileName", help="파일명"),
            "ColumnCnt": st.column_config.ProgressColumn(
                "ColumnCnt", help="컬럼 수", min_value=0, max_value=_max_colcnt, format="%d",
            ),
            "RelationshipCnt": st.column_config.ProgressColumn(
                "RelationshipCnt", help="참조 관계 수(Level_Depth>0)", min_value=0, max_value=_max_relcnt, format="%d",
            ),
        },
    )
    selected_files = edited_df[edited_df['select'] == True]['FileName'].tolist()
    if len(selected_files) > 0:
        return selected_files
    else:
        return None

def display_legend():
    st.write("---")
    st.write("#### 🎨 Color Legend & Guide")
    leg_cols = st.columns(5)
    with leg_cols[0]:
        st.markdown('🟢 **90% 이상**: 안정 (Matched)'); st.caption("데이터 정합성 매우 높음")
    with leg_cols[1]:
        st.markdown('🟡 **70%~89%**: 주의 (Warning)'); st.caption("일부 누락/오류 확인 필요")
    with leg_cols[2]:
        st.markdown('🔴 **70% 미만**: 위험 (Critical)'); st.caption("참조 관계 재검토 권장")
    with leg_cols[3]:
        st.markdown('⚪ **점수 없음**: 미진단'); st.caption("매칭 데이터 분석 전")


def main():
    st.set_page_config(page_title="Data Reliability Map", layout="wide")
    st.title("🎯 Data Relationship & Reliability Map")
    st.markdown("#### 참조 관계와 함께 **데이터 매칭율(Matching %)**을 분석하여 연결의 신뢰도를 진단합니다.")

    df_rel = load_rel_data()
    if not df_rel.empty:
        df_rel = df_rel[df_rel["MasterType"] == "Master"]

    selected_files = select_file(df_rel)
    if selected_files is  None:
        st.write("No files selected")

    # 상단 설정
    if selected_files is not None:
        for selected_file in selected_files:
            relationships = trace_column_relationships_with_score(df_rel, selected_file)
        
        if not relationships:
            st.warning("참조 관계 정보가 없습니다.")
        else:
            st.divider()
            st.subheader(f"📑 {selected_file} 중심 연관 관계도")
            dot = Digraph()
            dot.attr(rankdir='LR', fontname='Malgun Gothic', splines='ortho', bgcolor='black')
            
            # 중복 노드 방지를 위해 set 사용
            processed_nodes = set()

            for rel in relationships:
                src, tgt, score = rel['src'], rel['tgt'], rel['score']
                
                # 1. 소스 노드 설정 (최초 기준 파일인 경우만 진한 파랑)
                if src not in processed_nodes:
                    fcolor = '#1E88E5' if src.startswith(selected_file) else '#BBDEFB'
                    tcolor = 'white' if src.startswith(selected_file) else 'black'
                    dot.node(src, label=src, style='filled', fillcolor=fcolor, fontcolor=tcolor, shape='box')
                    processed_nodes.add(src)

                # 2. 타겟 노드 설정 (매칭율에 따른 색상 부여)
                if tgt not in processed_nodes:
                    node_bg = get_match_color(score)
                    dot.node(tgt, label=tgt, style='filled', fillcolor=node_bg, fontcolor='black', shape='box')
                    processed_nodes.add(tgt)

                # 3. 엣지 설정 (매칭율 표시)
                edge_label = f"{score}%" if score > 0 else "N/A"
                edge_color = "#2E7D32" if score >= 90 else "#FBC02D" if score >= 70 else "#C62828"
                dot.edge(src, tgt, label=edge_label, color=edge_color, fontcolor=edge_color, penwidth='1.5')

            st.graphviz_chart(dot, use_container_width=True)

            # -------------------------------------------------------------------
            # 하단 범례 (매칭율 기준)
            # -------------------------------------------------------------------
            display_legend()


if __name__ == "__main__":
    main()