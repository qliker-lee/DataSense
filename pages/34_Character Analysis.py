# -*- coding: utf-8 -*-
"""
🔍 DataSense Character Analysis (& Cleansing)
Author: qliker 2026-04-27
"""

import sys
import csv
import re
import unicodedata
import hanja
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# -------------------------------------------------------------------
# 1. 환경 설정 및 경로 최적화
# -------------------------------------------------------------------
CURRENT_DIR = Path(__file__).resolve().parent
# pages/ 아래 스크립트 → 프로젝트 루트는 pages의 부모(QDQM). parents[1]은 그 위 폴더라 styles 경로가 깨짐.
PROJECT_ROOT = CURRENT_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Streamlit 경고 억제
try:
    from util.streamlit_warnings import setup_streamlit_warnings
    setup_streamlit_warnings()
except ImportError:
    pass

# -------------------------------------------------------------------
# Unicode 정제 엔진 (기존 src/unicode_cleaner_engine.py 로직 인라인)
# -------------------------------------------------------------------
class UnicodeCleaner:
    def _is_broken_hangul(self, ch):
        """한글 미완성 문자(자음, 모음 단독) 판별"""
        try:
            name = unicodedata.name(ch, "")
            return "HANGUL" in name and "SYLLABLE" not in name
        except ValueError:
            return False

    def strip_accents_and_control(self, text):
        """악센트(Mn) 제거"""
        if not text:
            return ""
        nfd_form = unicodedata.normalize("NFD", text)
        cleaned = "".join([c for c in nfd_form if unicodedata.category(c) != "Mn"])
        return unicodedata.normalize("NFC", cleaned)

    def clean_unicode(self, text, mode=1, exclude_cats=None):
        if exclude_cats is None:
            exclude_cats = ["Cc", "Cf", "Cn", "So"]
        if not text:
            return ""

        text = unicodedata.normalize("NFKC", text)

        cleaned_chars = []
        for c in text:
            name = unicodedata.name(c, "UNKNOWN")
            cat = unicodedata.category(c)
            if name == "UNKNOWN" or "REPLACEMENT CHARACTER" in name:
                continue
            if cat in exclude_cats:
                continue
            cleaned_chars.append(c)

        text = "".join(cleaned_chars)
        text = self.strip_accents_and_control(text)

        if mode == 3:
            text = hanja.translate(text, "substitution")

        if mode in (2, 3):
            text = "".join([ch for ch in text if not self._is_broken_hangul(ch)])

        return text.strip()


# -------------------------------------------------------------------
# 2. 상수 및 전역 설정
# -------------------------------------------------------------------
OUTPUT_DIR = PROJECT_ROOT / "DS_Output"
CHARACTER_FILE = OUTPUT_DIR / "FileCharacter.csv"
CHARACTER_DETAIL_FILE = OUTPUT_DIR / "FileCharacterDetail.csv"
UNICODE_MAP_FILE = OUTPUT_DIR / "Unicode_CharacterMap.csv"
UNICODE_CATEGORY_FILE = OUTPUT_DIR / "Unicode_Category.csv"

APP_NAME = "Character Analysis (비정형 문자 분석)"
APP_DESC = "#### 비정형 문자(깨진한글, 유니코드, 제어문자, 한자 등) 탐지 현황 및 상세 분석"

_STYLISH_PALETTE = [
    "#00B4D8", "#52B788", "#F59E0B", "#FACC15", "#D6AD60",
    "#0077B6", "#2D6A4F", "#D97706", "#CA8A04", "#78350F",
    "#90E0EF", "#B7E4C7", "#FCD34D", "#FEF08A", "#E5D3B3"
]
_TEXT_COLOR = "#ECEFF1"
_GRID_COLOR = "rgba(255, 255, 255, 0.07)"

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
from util.Files_FunctionV20 import set_page_config
set_page_config(APP_NAME)

from util.Display import display_kpi_metrics

# --- FileCharacter*.csv 로드 · KPI ---
def load_character_data():
    return pd.read_csv(CHARACTER_FILE), pd.read_csv(CHARACTER_DETAIL_FILE)

def dashboard_character(df_summary):
    """ 파일별 결함 탐지 현황 """
    st.divider()
    total_files = df_summary['FileName'].nunique()
    total_broken = df_summary['BrokenKoreanCnt'].sum()
    total_unicode = df_summary['UnicodeCnt'].sum()
    total_control = df_summary['ControlCnt'].sum()
    total_chinese = df_summary['ChineseCnt'].sum()

    summary = {
        "분석 대상 파일": f"{total_files:,} 파일",
        "깨진 한글": f"{total_broken:,} 건",
        "유니코드": f"{total_unicode:,} 건",
        "제어문자": f"{total_control:,} 건",
        "한자(Chinese)": f"{total_chinese:,} 건",
    }
    metric_colors = {
        "분석 대상 파일": "#1f77b4",
        "깨진 한글": "#d62728",
        "유니코드": "#ff7f0e",      # 짙은 오렌지색
        "제어문자": "#d62728",      # 빨간색
        "한자(Chinese)": "#1a9850",
    }
    display_kpi_metrics(summary, metric_colors, "📈 Character Analysis Summary")


# --- TOP 10 문자 분포(막대·도넛) ---

def _truncate_label(s: str, max_len: int = 10) -> str:
    t = str(s)
    return t[: max_len - 1] + "…" if len(t) > max_len else t

def _char_counts_top10(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col not in df.columns:
        return pd.DataFrame(columns=["Character", "Count"])
    all_chars = df[col].fillna("").astype(str).str.split(",").explode().str.strip()
    all_chars = all_chars[all_chars != ""]
    if all_chars.empty:
        return pd.DataFrame(columns=["Character", "Count"])
    vc = all_chars.value_counts().head(10)
    return pd.DataFrame({"Character": vc.index.astype(str), "Count": vc.values})

def display_special_character_analysis(df_summary):
    """불필요한 기교를 제거하고 가독성을 극대화한 TOP 10 분석 차트"""

    st.divider()
    st.subheader("📝 비정형 문자 TOP 10 분석")

    panels = [
        ("깨진 한글", "BrokenKoreanChars"),
        ("유니코드", "UnicodeChars"),
        ("한자", "ChineseChars"),
    ]
    counts_list = [_char_counts_top10(df_summary, key) for _, key in panels]

    # --- [1] 막대 차트 (Bar Chart) - 패턴 제거 및 단색 처리 ---
    st.markdown("##### 📊 유형별 결함 문자 분포")
    fig_bar = make_subplots(rows=1, cols=3, subplot_titles=[f"<b>{t}</b>" for t, _ in panels], horizontal_spacing=0.07)

    for i, cc in enumerate(counts_list, start=1):
        if cc.empty:
            fig_bar.add_trace(go.Bar(x=["(없음)"], y=[0], marker_color="#37474F"), row=1, col=i)
        else:
            full = cc["Character"].tolist()
            vals = cc["Count"].tolist()
            
            fig_bar.add_trace(go.Bar(
                x=[_truncate_label(x) for x in full],
                y=vals,
                marker=dict(
                    color=_STYLISH_PALETTE[:len(vals)], # 패턴 없이 깔끔한 단색 적용
                    line=dict(color="rgba(255,255,255,0.1)", width=0.5) 
                ),
                customdata=[[orig] for orig in full],
                hovertemplate="<b>%{customdata[0]}</b><br>건수: %{y:,}<extra></extra>",
                text=vals,
                textposition="outside",
                textfont=dict(color=_TEXT_COLOR, size=11),
                showlegend=False
            ), row=1, col=i)

    fig_bar.update_layout(
        height=400,
        font=dict(color=_TEXT_COLOR, family="Pretendard, sans-serif"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=80, b=80, l=40, r=20),
    )
    fig_bar.update_xaxes(tickangle=-40, gridcolor=_GRID_COLOR)
    fig_bar.update_yaxes(gridcolor=_GRID_COLOR, zeroline=False)
    st.plotly_chart(fig_bar, width="stretch")

    # --- [2] 도넛 차트 (Donut Chart) ---
    st.markdown("##### 🍩 결함 문자 점유율 분석")
    fig_pie = make_subplots(rows=1, cols=3, specs=[[{"type": "domain"}] * 3], subplot_titles=[f"<b>{t}</b>" for t, _ in panels])

    for i, cc in enumerate(counts_list, start=1):
        if cc.empty:
            fig_pie.add_trace(go.Pie(labels=["(없음)"], values=[1], hole=0.6, marker_colors=["#37474F"]), row=1, col=i)
        else:
            full = cc["Character"].tolist()
            vals = cc["Count"].tolist()
            
            fig_pie.add_trace(go.Pie(
                labels=[_truncate_label(x) for x in full],
                values=vals,
                hole=0.6,
                marker=dict(colors=_STYLISH_PALETTE[:len(vals)], line=dict(color="#000000", width=2)),
                customdata=[[orig] for orig in full],
                hovertemplate="<b>%{customdata[0]}</b><br>%{percent}<extra></extra>",
                textinfo="percent",
                textposition="inside",
                textfont=dict(color="#000000", size=10, family="Arial Black"),
                showlegend=False,
                sort=False
            ), row=1, col=i)

    fig_pie.update_layout(
        height=380,
        font=dict(color=_TEXT_COLOR),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=80, b=40, l=20, r=20),
    )
    st.plotly_chart(fig_pie, width="stretch")


# --- 파일별 건수 집계 · 막대 차트 · 요약 metric ---
def calculate_file_character_fig_top10(df_summary):
    total_files = df_summary['FileName'].nunique()
    # 데이터 집계
    fig_df = df_summary.groupby('FileName')[['BrokenKoreanCnt', 'UnicodeCnt','ControlCnt', 'ChineseCnt']].sum().reset_index()
    fig_df['TotalCnt'] = fig_df[['BrokenKoreanCnt', 'UnicodeCnt', 'ControlCnt', 'ChineseCnt']].sum(axis=1)
    fig_df = fig_df.sort_values('TotalCnt', ascending=False)
    # 파일수가 50개 미만인 경우는 모두출력하고, 이상인 경우 상위 50개반 출력
    if total_files < 50:
        fig_df_top = fig_df
    else:
        fig_df_top = fig_df.head(50)

    return fig_df_top


def display_file_character_distribution_bar_chart(fig_df_top):
    """ 파일별 결함 탐지 분포 막대 차트 """
    st.divider()
    st.subheader("📝 파일별 결함 탐지 현황")
    fig = px.bar(fig_df_top, 
                x='FileName', 
                y=['BrokenKoreanCnt', 'UnicodeCnt', 'ControlCnt', 'ChineseCnt'],
                labels={'value': '탐지 건수', 'variable': '유형'},
                barmode='stack',
                color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig, width='stretch')
    return fig_df_top


def display_metrics(df: pd.DataFrame):
    st.divider()
    st.subheader("📊 파일별 비정형 문자 정보 요약")
    m1, m2, m3, m4, m5, m6, m7, m8 = st.columns(8)
    m1.metric("발견파일", f"{df['FilePath'].nunique():,}" if 'FilePath' in df.columns else f"{df['FileName'].nunique():,}")
    total_columns = df[['FileName', 'ColumnName']].drop_duplicates().shape[0] if {'FileName','ColumnName'}.issubset(df.columns) else 0
    m2.metric("컬럼 합계", f"{total_columns:,}")
    if 'BrokenKoreanCnt' in df.columns:
        m3.metric("깨진한글 파일", f"{df[pd.to_numeric(df['BrokenKoreanCnt'], errors='coerce').fillna(0) > 0]['FileName'].nunique():,}")
        m4.metric("깨진한글 컬럼", f"{df[pd.to_numeric(df['BrokenKoreanCnt'], errors='coerce').fillna(0) > 0]['ColumnName'].nunique():,}")

    if 'UnicodeCnt' in df.columns:
        m5.metric("유니코드 파일", f"{df[pd.to_numeric(df['UnicodeCnt'], errors='coerce').fillna(0) > 0]['FileName'].nunique():,}")
        m6.metric("유니코드 컬럼", f"{df[pd.to_numeric(df['UnicodeCnt'], errors='coerce').fillna(0) > 0]['ColumnName'].nunique():,}")
    if 'ChineseCnt' in df.columns:
        m7.metric("한자 파일", f"{df[pd.to_numeric(df['ChineseCnt'], errors='coerce').fillna(0) > 0]['FileName'].nunique():,}")
        m8.metric("한자 컬럼", f"{df[pd.to_numeric(df['ChineseCnt'], errors='coerce').fillna(0) > 0]['ColumnName'].nunique():,}")


# --- 상세: 파일 선택 · 요약/상세 테이블 ---
def _get_clean_df(df):
    """불필요한 컬럼 제거 및 결측치 처리"""
    drop_cols = ['FilePath', 'ControlChars', 'UnicodeOrdValues']
    df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors='ignore')
    return df.fillna('')

def _prepare_display_summary(df):
    """파일별 결함 컬럼 수 및 전체 건수 집계"""
    cols = ["BrokenKoreanCnt", "UnicodeCnt", "ChineseCnt", "ControlCnt"]
    
    # 컬럼별 유무 체크 (0보다 크면 1로 카운트)
    df_counts = df.groupby("FileName").agg({
        "ColumnName": "count",
        **{c: lambda x: (pd.to_numeric(x, errors="coerce") > 0).sum() for c in cols}
    }).rename(columns={"ColumnName": "결함 컬럼수", **{c: f"{c.replace('Cnt','')} 컬럼수" for c in cols}})

    # 전체 건수 합계
    df_sums = df.groupby("FileName").agg({
        c: "sum" for c in cols
    }).rename(columns={c: f"{c.replace('Cnt','')} 건수" for c in cols})

    merged = df_counts.merge(df_sums, on='FileName').reset_index()
    
    # 정렬용 토탈 계산 및 상위 50개 제한
    sort_cols = [f"{c.replace('Cnt','')} 건수" for c in cols]
    merged["_total"] = merged[sort_cols].sum(axis=1)
    merged = merged.sort_values("_total", ascending=False).head(50).drop(columns=["_total"])
    
    merged.insert(0, "선택", False)
    return merged

def _render_file_selector(df):
    """파일 선택용 데이터 에디터 렌더링 (숫자 컬럼은 ProgressColumn)."""
    col_cfg = {
        "선택": st.column_config.CheckboxColumn("선택", width="small", help="상세 보기할 파일 선택"),
        "FileName": st.column_config.TextColumn("파일명", help="파일명", width=120),
    }
    skip = {"선택", "FileName"}
    numeric_cols = [c for c in df.columns if c not in skip]
    max_by = {}
    for c in numeric_cols:
        s = pd.to_numeric(df[c], errors="coerce").fillna(0)
        max_by[c] = max(int(s.max()) if len(s) else 0, 1)
        col_cfg[c] = st.column_config.ProgressColumn(
            c,
            help=c,
            min_value=0,
            max_value=max_by[c],
            format="%d",
            width=10,
        )
    return st.data_editor(
        df,
        column_config=col_cfg,
        hide_index=True,
        width="stretch",
        height=500,
        key="char_analysis_file_selector",
    )

def _render_detail_dashboard(file_name, s_summary, s_detail):
    """선택된 파일의 상세 대시보드 출력"""
    st.subheader(f"📊 {file_name} 요약 정보")
    
    # Metric 출력
    m_cols = st.columns(4)
    metrics = [
        ("비정형컬럼", s_summary['ColumnName'].nunique()),
        ("깨진한글 컬럼", _get_unique_cnt(s_summary, 'BrokenKoreanCnt')),
        ("유니코드 컬럼", _get_unique_cnt(s_summary, 'UnicodeCnt')),
        ("한자 컬럼", _get_unique_cnt(s_summary, 'ChineseCnt'))
    ]
    for col, (label, val) in zip(m_cols, metrics):
        col.metric(label, f"{val:,}")

    # 컬럼별 요약 테이블
    s_summary_display = s_summary[['FileName', 'ColumnName', 'BrokenKoreanCnt', 'UnicodeCnt', 'ChineseCnt'
        , 'BrokenKoreanChars' ,'UnicodeChars', 'UnicodeOrdInt', 'UnicodeCategories', 'ChineseChars'
    ]].copy()
    # ProgressColumn 스케일링을 위해 최대값 계산
    _broken_max = int(pd.to_numeric(s_summary_display.get("BrokenKoreanCnt"), errors="coerce").fillna(0).max() or 0)
    _unicode_max = int(pd.to_numeric(s_summary_display.get("UnicodeCnt"), errors="coerce").fillna(0).max() or 0)
    _chinese_max = int(pd.to_numeric(s_summary_display.get("ChineseCnt"), errors="coerce").fillna(0).max() or 0)
    _broken_max = max(1, _broken_max)
    _unicode_max = max(1, _unicode_max)
    _chinese_max = max(1, _chinese_max)
    st.dataframe(s_summary_display, 
    column_config={
        "FileName": st.column_config.TextColumn("파일명", help="파일명", width=120),
        "ColumnName": st.column_config.TextColumn("컬럼명", help="컬럼명", width=120),
        "BrokenKoreanCnt": st.column_config.ProgressColumn("깨진한글 건수", help="깨진한글 건수"
            , min_value=0, max_value=_broken_max, format="%d", width="small"),
        "UnicodeCnt": st.column_config.ProgressColumn("유니코드 건수", help="유니코드 건수"
            , min_value=0, max_value=_unicode_max, format="%d", width="small"), 
        "ChineseCnt": st.column_config.ProgressColumn("한자 건수", help="한자 건수"
            , min_value=0, max_value=_chinese_max, format="%d", width="small"),
    },  hide_index=True, width="stretch", height=400)

    # 레코드별 상세 테이블
    s_detail_cnt = s_detail.shape[0]
    st.subheader(f"📝 레코드 상세 ({s_detail_cnt}건)")
    st.dataframe(s_detail.head(1000), hide_index=True, width="stretch", height=500)

def _get_unique_cnt(df, col):
    """특정 결함이 있는 유니크 컬럼 수 반환"""
    if col not in df.columns: return 0
    return df[pd.to_numeric(df[col], errors='coerce').fillna(0) > 0]['ColumnName'].nunique()


def character_detail_analysis(df_summary, df_detail) -> str | None:
    """비정형 문자 파일별/레코드별 상세 분석 메인 함수"""
    st.subheader("🔎 파일별 상세 결함 내역 (컬럼 및 레코드)")
    st.caption("데이터 프레임 헤더에 마우스를 위치하면 상세 설명을 확인할 수 있습니다.")

    # 1. 데이터 정제 및 요약 데이터 생성
    summary_clean = _get_clean_df(df_summary)
    detail_clean = _get_clean_df(df_detail)
    
    # 2. 파일별 통계 데이터 생성 (집계 로직 분리)
    display_df = _prepare_display_summary(summary_clean)

    # 3. 메인 파일 선택 에디터 출력
    edited_df = _render_file_selector(display_df)

    # 4. 파일 선택에 따른 상세 화면 렌더링
    selected_files = edited_df.loc[edited_df['선택'], 'FileName'].dropna().unique().tolist()
    if not selected_files:
        st.info("상세 보기를 위해 파일을 선택하세요.")
        return None

    selected_file = selected_files[0]
    st.divider()
    
    # 상세 데이터 필터링
    s_summary = summary_clean[summary_clean['FileName'] == selected_file].reset_index(drop=True)
    s_detail = detail_clean[detail_clean['FileName'] == selected_file].reset_index(drop=True)

    if s_detail.empty:
        st.info("상세 데이터 내역이 없습니다.")
        return None

    # 5. 상세 대시보드 렌더링 (Metric -> Summary Table -> Detail Table)
    _render_detail_dashboard(selected_file, s_summary, s_detail)

    return selected_file
# ---------------------------------------------------------------------------
# Unicode 정제 (UnicodeCleaner + 고유값 매핑)
# ---------------------------------------------------------------------------
_unicode_cleaner: UnicodeCleaner | None = None


def _get_unicode_cleaner() -> UnicodeCleaner:
    global _unicode_cleaner
    if _unicode_cleaner is None:
        _unicode_cleaner = UnicodeCleaner()
    return _unicode_cleaner


def _clean_series_via_unique_map(series: pd.Series, mode: int, exclude_cats: list) -> pd.Series:
    """행마다 정제 대신, 고유 문자열 값에만 clean_unicode 적용 후 map으로 복원."""
    s = series.fillna("").astype(str)
    uniq = pd.unique(s)
    if len(uniq) == 0:
        return s.copy()
    cleaner = _get_unicode_cleaner()
    cache = {u: cleaner.clean_unicode(u, mode=mode, exclude_cats=exclude_cats) for u in uniq}
    return s.map(cache)


def _unique_chars_from_series(series: pd.Series) -> set[str]:
    ch: set[str] = set()
    for val in series:
        ch.update(str(val))
    return ch


def _build_char_clean_map(charset: set[str], mode: int, exclude_cats: list) -> dict[str, str]:
    """글자 단위 정제 결과 캐시 (extract_changed_chars 등에서 재사용)."""
    if not charset:
        return {}
    cleaner = _get_unicode_cleaner()
    return {c: cleaner.clean_unicode(c, mode=mode, exclude_cats=exclude_cats) for c in charset}


def _unicode_scalars_hex(s) -> str:
    """정제 전·후 비교용: 문자열의 코드포인트만 0x#### 형태로 공백 구분 (표시용 변환 없음)."""
    if s is None:
        return ""
    try:
        if pd.isna(s):
            return ""
    except TypeError:
        pass
    t = str(s)
    if not t:
        return ""
    return " ".join(f"0x{ord(c):04x}" for c in t)


# --- 선택 파일 정제 UI · 결과 표/다운로드 ---
def character_cleansing(selected_file, df_detail, category_df):
    """속도와 식별성을 모두 잡은 정제 분석 함수"""
    if not selected_file:
        return

    st.subheader(f"📊 정제 문자 정밀 분석: {selected_file}")

    # 1. 초기 필터링 (필요한 컬럼만 로드)
    det = df_detail.loc[df_detail["FileName"] == selected_file].copy()
    if det.empty:
        st.info("데이터가 없습니다.")
        return

    # 2. 정제 모드 설정
    cleanse_mode = st.radio("정제 모드", ["1: 유니코드 정제", "2: 유니코드 & 미완성한글 제거", "3: 유니코드 & 미완성한글 & 한자변환"], horizontal=True)
    mode_map = {"1: 유니코드 정제": 1, "2: 유니코드 & 미완성한글 제거": 2, "3: 유니코드 & 미완성한글 & 한자변환": 3}
    selected_mode = mode_map[cleanse_mode]
    exclude_cats = ['Cc', 'Cf', 'Cn', 'So'] # 제어문자, 서식문자, 구두점, 기타 문자 제외

    if st.button("🚀 정제 실행"):
        with st.spinner("정제 중 ... (고유 값·문자 단위 캐시 적용)"):
            raw_series = det["DataValue"].fillna("").astype(str)
            cleaned_series = _clean_series_via_unique_map(raw_series, selected_mode, exclude_cats)
            char_map = _build_char_clean_map(_unique_chars_from_series(raw_series), selected_mode, exclude_cats)

            diff_mask = raw_series != cleaned_series
            if not diff_mask.any():
                st.success("✅ 정제할 문자가 없는 깨끗한 파일입니다.")
                return

            diff_df = det[diff_mask].copy()
            diff_df["Cleaned_DataValue"] = cleaned_series[diff_mask]
            diff_df["정제후전체문자"] = diff_df["Cleaned_DataValue"]

            def extract_changed_chars(row):
                orig = str(row["DataValue"])
                before, after = [], []
                for char in orig:
                    c_char = char_map[char]
                    if char != c_char:
                        before.append(char)
                        after.append(c_char if c_char != "" else "[삭제]")
                return "".join(before), "".join(after)

            # 변경된 행들에 대해서만 상세 추출 수행
            diff_results = diff_df.apply(extract_changed_chars, axis=1)
            diff_df['정제전_문자'], diff_df['정제후_문자'] = zip(*diff_results)

            # [Step 4] Hex 값 변환
            diff_df['정제전_Hex'] = diff_df['정제전_문자'].map(_unicode_scalars_hex)
            diff_df['정제후_Hex'] = diff_df['정제후_문자'].map(_unicode_scalars_hex)

            # 3. 결과 출력
            st.warning(f"🔎 총 {len(diff_df):,}건의 결함 레코드가 분석되었습니다.")
            
            display_cols = [
                "ColumnName",
                "RecNo",
                "DataValue",
                "정제후전체문자",
                "정제전_문자",
                "정제후_문자",
                "정제전_Hex",
                "정제후_Hex",
            ]

            st.dataframe(
                diff_df[display_cols].head(1000),
                hide_index=True,
                width="stretch",
                column_config={
                    "DataValue": st.column_config.TextColumn("원본 전체", width=200),
                    "정제후전체문자": st.column_config.TextColumn(
                        "정제 후 전체",
                        width=200,
                        help="정제 엔진 적용 후 전체 문자열",
                    ),
                    "정제전_문자": st.column_config.TextColumn("정제 전 문자", width=100, help="결함 문자만 추출"),
                    "정제후_문자": st.column_config.TextColumn("정제 후 문자", width=100, help="글자 단위 변경 요약"),
                },
            )
            st.download_button(
                "📥 정제 대상 리스트 다운로드",
                diff_df[display_cols].to_csv(index=False).encode("utf-8-sig"),
                f"defect_chars_{selected_file}.csv",
                "text/csv",
                key="download_defect_chars",
            )

    st.divider()
    st.write("유니코드는 카테고리 Cc(제어), Cf(서식), Cn(미할당), So(기타 기호) 등을 제외 규칙에 따라 정제됩니다.")
    st.write("미완성 한글·한자 옵션은 선택한 정제 모드에 따라 추가 처리됩니다.")

    with st.expander("유니코드 카테고리 정보 설명"):
        category_info_display(category_df)


# --- 분석 파이프라인(차트 → 상세 → 정제) ---
def analysis_character(df_summary, df_detail, category_df):
    """ 비정형 문자 분석 main 함수 """
    
    display_special_character_analysis(df_summary)

    fig_df_top = calculate_file_character_fig_top10(df_summary)

    display_metrics(df_summary)

    display_file_character_distribution_bar_chart(fig_df_top)

    selected_file = character_detail_analysis(df_summary, df_detail)
    if selected_file:
        character_cleansing(selected_file, df_detail, category_df)


# --- Unicode_CharacterMap / Unicode_Category CSV 생성 및 로드 ---
class UnicodeCategoryDefiner:
    def __init__(self):
        self.category_definitions = {
            'Lu': ('Letter, Uppercase', '대문자 언어 문자 (A, B, C...)'),
            'Ll': ('Letter, Lowercase', '소문자 언어 문자 (a, b, c...)'),
            'Lt': ('Letter, Titlecase', '단어의 첫 글자만 대문자인 형태 (ǅ...)'),
            'Lm': ('Letter, Modifier', '수식 글자, 첨자 형태 (ʰ, ʸ...)'),
            'Lo': ('Letter, Other', '기타 글자 (한글 완성형, 한자, 히라가나 등)'),
            'Mn': ('Mark, Nonspacing', '폭이 없는 조합 기호 (악센트 등)'),
            'Mc': ('Mark, Spacing Combining', '폭이 있는 조합 기호'),
            'Me': ('Mark, Enclosing', '문자를 감싸는 기호 (원형 등)'),
            'Nd': ('Number, Decimal Digit', '일반 숫자 (0-9)'),
            'Nl': ('Number, Letter', '글자 형태의 숫자 (로마 숫자 Ⅲ, 한자 숫자 등)'),
            'No': ('Number, Other', '기타 숫자 (원문자 숫자 ①, 분수 등)'),
            'Pc': ('Punctuation, Connector', '연결용 문장부호 (언더바 _ 등)'),
            'Pd': ('Punctuation, Dash', '대시/하이픈 (- 등)'),
            'Ps': ('Punctuation, Open', '여는 괄호 ( ( [ { < ...)'),
            'Pe': ('Punctuation, Close', '닫는 괄호 ( ) ] } > ...)'),
            'Pi': ('Punctuation, Initial quote', '시작 따옴표 (“...)'),
            'Pf': ('Punctuation, Final quote', '끝 따옴표 (”...)'),
            'Po': ('Punctuation, Other', '기타 문장부호 (., !? # & 등)'),
            'Sm': ('Symbol, Math', '수학 기호 (+, =, ∞...)'),
            'Sc': ('Symbol, Currency', '통화 기호 ($, ₩, €...)'),
            'Sk': ('Symbol, Modifier', '수정 기호, 성조 표현 (^, ~ ...)'),
            'So': ('Symbol, Other', '기타 기호 (©, ®, ™, 이모지 등)'),
            'Zs': ('Separator, Space', '공백 문자 (일반 Space)'),
            'Zl': ('Separator, Line', '행 구분자'),
            'Zp': ('Separator, Paragraph', '단락 구분자'),
            'Cc': ('Other, Control', '제어 문자 (줄바꿈, 탭 등)'),
            'Cf': ('Other, Format', '포맷팅 문자'),
            'Cs': ('Other, Surrogate', '서러게이트 (유니코드 내부 처리용)'),
            'Co': ('Other, Private Use', '사용자 정의 영역 (Private Use Area)'),
            'Cn': ('Other, Not Assigned', '미할당 문자'),
        }

    def generate_unicode_category(self) -> pd.DataFrame:
        report_data = []
        category_samples: dict[str, list[str]] = {}
        for i in range(0x11000):
            if 0xD800 <= i <= 0xDFFF:
                continue
            try:
                char = chr(i)
                cat = unicodedata.category(char)
                samples = category_samples.setdefault(cat, [])
                if len(samples) < 5:
                    samples.append(char)
            except Exception:
                continue

        for code, (name, desc) in self.category_definitions.items():
            samples = category_samples.get(code, [])
            samples = [c for c in samples if not (0xD800 <= ord(c) <= 0xDFFF)]
            if not samples:
                example_char = "N/A"
                example_ord = ""
                example_hex = ""
                example_name = ""
            else:
                example_char = " | ".join(samples)
                example_ord = " | ".join(str(ord(c)) for c in samples)
                example_hex = " | ".join(f"0x{ord(c):04X}" for c in samples)
                example_name = " | ".join(unicodedata.name(c, "N/A") for c in samples)
            report_data.append({
                'category': code,
                'category_name': name,
                'category_description': desc,
                'example': example_char,
                'example_hex': example_hex,
                'example_ord': example_ord,
                'example_name': example_name,
            })

        df = pd.DataFrame(report_data)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(UNICODE_CATEGORY_FILE, index=False, encoding='utf-8-sig', quoting=csv.QUOTE_ALL, escapechar='\\')
        return df

class UnicodeMasterTool:
    def strip_accents_and_special(self, char: str) -> str:
        if not char:
            return ""
        nfd_form = unicodedata.normalize('NFD', char)
        stripped = "".join(c for c in nfd_form if unicodedata.category(c) != 'Mn')
        stripped = "".join(c for c in stripped if unicodedata.category(c) not in ('Cc', 'Cf'))
        # unicodedata.name()는 "문자 1개"만 허용. (정규화 결과가 다문자일 수 있음)
        if stripped and len(stripped) == 1 and unicodedata.name(stripped, "UNKNOWN") == "UNKNOWN":
            return ""
        return stripped

    def generate_character_group(self, char: str) -> tuple[str, str]:
        if not char:
            return ("EMPTY", "EMPTY")
        try:
            name = unicodedata.name(char, "UNKNOWN")
        except Exception:
            name = "UNKNOWN"
        if name == "UNKNOWN":
            return ("UNKNOWN", "UNKNOWN")
        parts = name.split()
        group = parts[0] if parts else "UNKNOWN"
        sub_group = parts[1] if len(parts) > 1 else "UNKNOWN"
        return (group, sub_group)

    def generate_unicode_map(self) -> pd.DataFrame:
        char_data = []
        total_steps = 0x11000
        progress_bar = st.progress(0.0)
        for i in range(total_steps):
            if 0xD800 <= i <= 0xDFFF:
                continue
            try:
                char = chr(i)
                category = unicodedata.category(char)
                if category == 'Cn':
                    continue
                char_name = unicodedata.name(char, "")
                norm_1st = unicodedata.normalize('NFKC', char)
                norm_2nd = self.strip_accents_and_special(norm_1st)
                group, sub_group = self.generate_character_group(char)
                normalized_2nd_group, normalized_2nd_sub_group = self.generate_character_group(norm_2nd) if len(norm_2nd) == 1 else ("MULTI", "MULTI")
                char_data.append({
                    'Character': char,
                    'UnicodeOrd': ord(char),
                    'UnicodeHex': f"0x{ord(char):04X}",
                    'UnicodeName': char_name,
                    'category': category,
                    'Normalized_1st(NFKC)': norm_1st,
                    'NFKC_Hex': f"0x{ord(norm_1st[0]):04X}" if len(norm_1st) == 1 else "",
                    'Normalized_2nd(Accent Strip)': norm_2nd,
                    'Accent_Strip_Hex': f"0x{ord(norm_2nd[0]):04X}" if len(norm_2nd) == 1 else "",
                    'Length_2nd': len(norm_2nd),
                    'Changed_name_2nd': unicodedata.name(norm_2nd, "") if len(norm_2nd) == 1 else "MULTIPLE CHARACTERS",
                    'Changed_FLAG(org_2nd)': 1 if norm_2nd != char else 0,
                    'Group': group,
                    'SubGroup': sub_group,
                    'Normalized_2nd_Group': normalized_2nd_group,
                    'Normalized_2nd_SubGroup': normalized_2nd_sub_group,
                })
            except Exception:
                continue
            if i % 5000 == 0:
                progress_bar.progress(i / total_steps)

        df = pd.DataFrame(char_data)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(UNICODE_MAP_FILE, index=False, encoding='utf-8-sig', quoting=csv.QUOTE_ALL, escapechar='\\')
        progress_bar.empty()
        return df

def create_load_data() -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    tool = UnicodeMasterTool()
    category_tool = UnicodeCategoryDefiner()

    if not UNICODE_MAP_FILE.exists() or not UNICODE_CATEGORY_FILE.exists():
        tool.generate_unicode_map()
        category_tool.generate_unicode_category()

    if not UNICODE_MAP_FILE.exists() or not UNICODE_CATEGORY_FILE.exists():
        st.error("Unicode Map/Category 파일을 생성할 수 없습니다.")
        return None, None

    unicode_df = pd.read_csv(UNICODE_MAP_FILE)
    category_df = pd.read_csv(UNICODE_CATEGORY_FILE)

    # 기존 파일이 있어도 최신 정규화 로직 반영
    norm_1st_series = unicode_df['Normalized_1st(NFKC)'].fillna("").astype(str)
    norm_2nd_series = norm_1st_series.apply(tool.strip_accents_and_special)
    unicode_df['Normalized_2nd(Accent Strip)'] = norm_2nd_series
    unicode_df['Accent_Strip_Hex'] = norm_2nd_series.apply(lambda s: f"0x{ord(s[0]):04X}" if len(s) == 1 else "")
    unicode_df['Length_2nd'] = norm_2nd_series.apply(len)
    unicode_df['Changed_name_2nd'] = norm_2nd_series.apply(lambda s: unicodedata.name(s, "") if len(s) == 1 else "MULTIPLE CHARACTERS")
    char_series = unicode_df['Character'].fillna("").astype(str)
    unicode_df['Changed_FLAG(org_2nd)'] = (norm_2nd_series != char_series).astype(int)
    group_pairs = norm_2nd_series.apply(tool.generate_character_group)
    unicode_df['Normalized_2nd_Group'] = group_pairs.apply(lambda g: g[0])
    unicode_df['Normalized_2nd_SubGroup'] = group_pairs.apply(lambda g: g[1])

    return unicode_df, category_df

def category_info_display(category_df: pd.DataFrame):
    category_cnt = category_df['category'].nunique()
    st.subheader("📊 유니코드 카테고리 정보")
    st.write("유니코드(Unicode)는 전 세계의 모든 문자를 컴퓨터에서 일관되게 표현하기 위해 유니코드 컨소시엄(Unicode Consortium)이 제정한 국제 문자 인코딩 표준입니다.")
    st.write("각 문자마다 U+XXXX 형식의 고유한 코드 포인트를 부여하며, UTF-8, UTF-16, UTF-32 등의 인코딩 방식으로 저장 및 전송됩니다.")
    st.markdown(
        "##### 데이터에 유니코드가 포함된 경우 데이터 분석·마이그레이션 시 "
        "<span style='color:#d32f2f;font-weight:700;'>오류</span>가 발생할 수 있습니다.",
        unsafe_allow_html=True,
    )
    st.markdown(
        "##### 유니코드 정보를 확인하고 정제하면 "
        "<span style='color:#d32f2f;font-weight:700;'>오류</span>를 줄일 수 있습니다.",
        unsafe_allow_html=True,
    )

    with st.expander("유니코드의 핵심 특징 및 구성 요소"):
        st.write("목적: 언어별로 다른 인코딩 방식을 통일하여 호환성 문제 해결.")
        st.write("범위: 15.1 버전 기준으로 U+0000부터 U+10FFFF까지의 공간을 사용.")
        st.write("구성: 총 17개의 평면으로 나뉘며, 0번 평면(다국어 기본 평면, BMP)에 가장 자주 쓰이는 문자 배치.")
        st.write("주요 인코딩 방식: UTF-8: 웹에서 가장 널리 사용되는 가변 길이 인코딩. ASCII와 호환되며 1~4 바이트 사용. UTF-16: 2 또는 4 바이트를 사용하여 문자를 표현. UTF-32: 모든 문자를 4 바이트 고정 길이로 표현.")
        st.write("유니코드 덕분에 한글, 라틴 문자, 한자, 이모지 등을 한 화면에서 깨짐 없이 표시할 수 있습니다.")
        st.write(f"유니코드 카테고리는 문자의 종류를 분류하는 데 사용되며, 총 {category_cnt}개의 카테고리로 구성됩니다. ")

    st.dataframe(category_df, width='stretch', height=500, hide_index=True)


# --- Expander: 코드포인트 Hex 조회 ---
def display_unicode_info(unicode_df: pd.DataFrame):
    st.subheader("📊 Unicode Info")
    hex_input = st.text_input("Hex 값을 입력하세요. (예: 0x321C, 0041)", value="0x0000")
    if not hex_input:
        return
    raw = hex_input.strip()
    try:
        if raw.lower().startswith("0x"):
            raw = raw[2:]
        raw = re.sub(r"[^0-9a-fA-F]", "", raw)
        if not raw:
            raise ValueError("빈 입력값")
        value = int(raw, 16)
        hex_value = f"0x{value:04X}"
        if 'UnicodeHex' not in unicode_df.columns:
            st.info("UnicodeHex 컬럼이 없습니다.")
            return
        unicode_info = unicode_df[unicode_df['UnicodeHex'].astype(str).str.upper() == hex_value.upper()]
        if unicode_info.empty:
            st.info(f"조회 결과가 없습니다: {hex_value}")
        else:
            st.write(f"🔍 **{hex_value}** 검색 결과")
            st.dataframe(unicode_info, width='stretch', hide_index=True)
    except ValueError:
        st.error("올바른 16진수 형식이 아닙니다. (예: 0x321C)")
    except Exception as e:
        st.error(f"오류 발생: {e}")


# -------------------------------------------------------------------
# 메인 진입점
# -------------------------------------------------------------------
def main():
    st.title(f"📊 {APP_NAME}")
    st.markdown(APP_DESC)

    try:
        df_summary, df_detail = load_character_data()
    except Exception as e:
        st.error(f"Character 분석 데이터 파일을 찾을 수 없습니다: {e}")
        return

    unicode_df, category_df = create_load_data()
    if unicode_df is None or category_df is None:
        st.error("Unicode Map/Category 데이터를 준비할 수 없습니다.")
        return

    dashboard_character(df_summary)
    analysis_character(df_summary, df_detail, category_df)

    with st.expander("🔍 Unicode Hex Quick Lookup"):
        display_unicode_info(unicode_df)

    st.divider()


if __name__ == "__main__":
    main()