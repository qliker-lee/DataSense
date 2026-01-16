# -*- coding: utf-8 -*-
"""
🔗 DataSense Physical & Logical Data Relationship Diagram Generator
✔ Cloud / Local 환경 자동 감지 (Cloud : 예제 이미지 출력, Local : 실제 Graphviz Physical & Logical Data Relationship Diagram 생성)
Author: Qliker 2026-01-08
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
import shutil
from datetime import datetime
from collections import defaultdict
import streamlit as st
import pandas as pd
import graphviz
from graphviz import Digraph
import streamlit.components.v1 as components
from PIL import Image

Image.MAX_IMAGE_PIXELS = None # 이미지 크기 제한 해제 (DecompressionBombError 방지)
# -------------------------------------------------
# 3. Local imports
# -------------------------------------------------
from util.Files_FunctionV20 import set_page_config
from util.Display import Display_File_Statistics, display_kpi_metrics
from util.ds_generate_ERD import show_example_erd_images
# -------------------------------------------------
# 4. App Config (절대 상수임. 변경하지 마세요)
# -------------------------------------------------
APP_NAME = "Physical & Logical Diagram"
APP_TITLE = "Physical & Logical Data Relationship Diagram"
APP_DESCRIPTION = "데이터 값 매핑 기반 물리적 & 논리적 Data Relationship Diagram을 생성합니다."

OUTPUT_DIR = PROJECT_ROOT /  'DS_Output'
IMAGE_DIR = PROJECT_ROOT / 'images'
IMAGE_FILE = "Datasense_DRD"
EXCLUSIVE_FILE = OUTPUT_DIR / "ERD_exclusive.csv"

MAX_RELATED_TABLE_COUNT = 100

set_page_config(APP_NAME)
# -------------------------------------------------------------------
# ERD 상수 설정
# -------------------------------------------------------------------
MAX_TABLE_COUNT = 20    # ERD 생성 시 최대 테이블 수
ERD_IMAGE_FILENAME = 'Master_ERD_2'
ERD_IMAGE_FILEEXTENSION = 'png'

ERD_FONT_SIZE = '6'
ERD_FONT_NAME = 'Malgun Gothic'

# ========================================================================
# 함수 정의 섹션
# ========================================================================

# -------------------------------------------------
# 1. 유틸리티 함수 (Utility Functions)
# -------------------------------------------------
def is_cloud_env() -> bool:
    """Cloud 환경 감지"""
    try:
        return shutil.which("dot") is None
    except Exception:
        return True

def parse_relationship(relationship_str):
    """Level_Relationship_Internal 문자열에서 모든 관계를 추출합니다."""
    if not isinstance(relationship_str, str) or '->' not in relationship_str:
        return []
    
    segments = relationship_str.split(' -> ')
    relationships = []
    
    for i in range(len(segments) - 1):
        parent_segment = segments[i].strip()
        child_segment = segments[i+1].strip()
        
        try:
            # 파일명과 컬럼명 분리 (마지막 '.' 기준)
            parent_file, parent_col = parent_segment.rsplit('.', 1)
            child_file, child_col = child_segment.rsplit('.', 1)
            
            # Level_Relationship_Internal 순서를 반대로 해석하여 FK 관계 생성
            relationships.append({
                'Child_Table': child_file,
                'Child_Column': child_col,
                'Parent_Table': parent_file,
                'Parent_Column': parent_col
            })
        except ValueError:
            continue
    return relationships

def _extract_and_load_erd_data_impl(df_raw: pd.DataFrame):
    """     2nd Step: 데이터 통합 & find pk & fk    """

    required_columns = ['FileName', 'ColumnName', 'PK']
    missing_columns = [col for col in required_columns if col not in df_raw.columns]
    if missing_columns:
        st.error(f"필수 컬럼이 누락되었습니다: {missing_columns}")
        return None, None, None

    if 'Level_Relationship_Internal' not in df_raw.columns:
        st.warning("⚠️ 'Level_Relationship_Internal' 컬럼이 없습니다. FK 관계를 추출할 수 없습니다.")
        df_raw['Level_Relationship_Internal'] = ''

    # --- 2. ERD 정보 추출 메인 로직 ---
    tables_data = {}
    df_raw = df_raw.fillna('')

    # 2.1. 모든 테이블 및 컬럼 정보 추출 (벡터화된 연산 사용)
    df_raw['FileName'] = df_raw['FileName'].astype(str).str.strip()
    df_raw['ColumnName'] = df_raw['ColumnName'].astype(str).str.strip()
    df_valid = df_raw[(df_raw['FileName'] != '') & (df_raw['ColumnName'] != '')].copy()
    
    for file_name, group in df_valid.groupby('FileName'):
        if file_name not in tables_data:
            tables_data[file_name] = defaultdict(lambda: {'PK': '', 'FK': '', 'Parent_Table': ''})
        
        for _, row in group.iterrows():
            col_name = row['ColumnName']
            pk_status = 'PK' if str(row.get('PK', '')).strip() == '1' else ''
            tables_data[file_name][col_name]['PK'] = pk_status

    # 2.2. 관계 정보 추출 및 FK 업데이트 (필터링된 데이터만 처리)
    all_relationships = []
    # Level_Relationship_Internal 컬럼이 없으면 기본값 빈 문자열로 생성
    if 'Level_Relationship_Internal' not in df_valid.columns:
        df_valid['Level_Relationship_Internal'] = ''
    df_with_rel = df_valid[df_valid['Level_Relationship_Internal'].astype(str).str.strip() != ''].copy()
    
    for _, row in df_with_rel.iterrows():
        rel_str = str(row.get('Level_Relationship_Internal', '')).strip()
        parsed_rels = parse_relationship(rel_str)
        
        for rel in parsed_rels:
            all_relationships.append(rel)
            
            child_table = str(rel['Child_Table']).strip()
            child_col = str(rel['Child_Column']).strip()
            parent_table = str(rel['Parent_Table']).strip()
            
            if not child_table or not child_col or not parent_table:
                continue
            
            if child_table in tables_data and child_col in tables_data[child_table]:
                tables_data[child_table][child_col]['FK'] = 'FK'
                
                current_parents = str(tables_data[child_table][child_col]['Parent_Table']).strip()
                if current_parents:
                    parent_list = [p.strip() for p in current_parents.split(',') if p.strip()]
                    if parent_table not in parent_list:
                        parent_list.append(parent_table)
                        tables_data[child_table][child_col]['Parent_Table'] = ', '.join(parent_list)
                else:
                    tables_data[child_table][child_col]['Parent_Table'] = parent_table


    # 2.3. 최종 통합 DataFrame 생성 (벡터화된 연산 사용)
    df_raw['FileName'] = df_raw['FileName'].astype(str).str.strip()
    df_raw['ColumnName'] = df_raw['ColumnName'].astype(str).str.strip()
    df_raw = df_raw[(df_raw['FileName'] != '') & (df_raw['ColumnName'] != '')]
    
    # Level_Depth 처리
    if 'Level_Depth_Internal' in df_raw.columns:
        df_raw['Level_Depth_Internal'] = pd.to_numeric(df_raw['Level_Depth_Internal'], errors='coerce').fillna(0).astype(int)
    else:
        df_raw['Level_Depth_Internal'] = 0
    
    # FilePath 처리
    if 'FilePath' in df_raw.columns:
        df_raw['FilePath'] = df_raw['FilePath'].astype(str).str.strip()
    else:
        df_raw['FilePath'] = ''
    
    # Level_Relationship_Internal 처리
    if 'Level_Relationship_Internal' in df_raw.columns:
        df_raw['Level_Relationship_Internal'] = df_raw['Level_Relationship_Internal'].astype(str).str.strip()
    else:
        df_raw['Level_Relationship_Internal'] = ''
    
    # tables_data와 병합하여 PK/FK 정보 추가
    erd_data_list = []
    for _, row in df_raw.iterrows():
        file_name = row['FileName']
        col_name = row['ColumnName']
        
        if file_name in tables_data and col_name in tables_data[file_name]:
            info = tables_data[file_name][col_name]
            erd_data_list.append({
                'FileName': file_name,
                'ColumnName': col_name,
                'PK': 1 if info['PK'] == 'PK' else 0,
                'FK': 1 if info['FK'] == 'FK' else 0,
                'Parent_Table': str(info['Parent_Table']).strip(),
                'Level_Relationship_Internal': row['Level_Relationship_Internal'],
                'Level_Depth_Internal': int(row['Level_Depth_Internal']),
                'FilePath': row['FilePath']
            })
    
    if not erd_data_list:
        st.error("ERD 데이터를 생성할 수 없습니다. 입력 파일의 데이터를 확인해주세요.")
        return None, None, None
    
    df_erd_attributes = pd.DataFrame(erd_data_list)

    unique_relationships = {}
    for rel in all_relationships:
        key = (rel['Child_Table'], rel['Parent_Table'])
        
        if key not in unique_relationships:
            unique_relationships[key] = {
                'Child Table': rel['Child_Table'],
                'Parent Table': rel['Parent_Table'],
                'FK Columns': set(),
                'PK Columns': set()
            }
        
        unique_relationships[key]['FK Columns'].add(rel['Child_Column'])
        unique_relationships[key]['PK Columns'].add(rel['Parent_Column'])

    df_erd_relationships = pd.DataFrame([
        {
            'Child Table': rel['Child Table'],
            'Parent Table': rel['Parent Table'],
            'FK Columns': ', '.join(sorted(rel['FK Columns'])),
            'PK Columns': ', '.join(sorted(rel['PK Columns']))
        }
        for rel in unique_relationships.values()
    ])
    
    pk_map = df_erd_attributes[df_erd_attributes['PK'] == 1].groupby('FileName')['ColumnName'].apply(
        lambda x: list(x.astype(str))
    ).to_dict()
    
    return pk_map, df_erd_relationships, df_erd_attributes

try:
    from streamlit.runtime.scriptrunner.script_run_context import get_script_run_ctx
    if get_script_run_ctx(suppress_warning=True) is not None:
        extract_and_load_erd_data = st.cache_data(_extract_and_load_erd_data_impl)
    else:
        extract_and_load_erd_data = _extract_and_load_erd_data_impl
except:
    extract_and_load_erd_data = _extract_and_load_erd_data_impl

# -------------------------------------------------
# 2. 데이터 로드/처리 함수 (Data Loading & Processing)
# -------------------------------------------------
def load_data_all(files_to_load):
    """여러 CSV 파일을 로드합니다."""
    loaded_data = {}
    for name, path in files_to_load.items():
        if not path.exists():
            st.error(f"{path.name} 파일이 없습니다")
            return None
        df = pd.read_csv(path, encoding='utf-8-sig')
        loaded_data[name] = df
    return loaded_data

# def create_pk_fk_from_mapping(df_cr):
#     """데이터 통합 & find pk & fk"""
#     # 1. 데이터 추출 및 로드
#     pk_map, fk_map, it_df = _extract_and_load_erd_data_impl(df_cr)
    
#     if pk_map is None or fk_map is None or it_df is None:
#         st.error("ERD 데이터를 생성할 수 없습니다. 입력 파일의 데이터를 확인해주세요.")
#         return None, None, None

#     return pk_map, fk_map, it_df

# -------------------------------------------------
# 3. 관계 추출 함수 (Relationship Extraction)
# -------------------------------------------------
def _extract_relationships_from_erd_logic(selected_files: list, all_tables: set, it_df: pd.DataFrame):
    """
    22_Data Relationship Diagram.py용 논리적 관계 추출 함수
    Level_Relationship 또는 Level_Relationship_Internal을 사용
    반환: relationships_list = [(from_file, from_col, to_file, to_col), ...]
    """
    relationships_list = []
    
    # Level_Relationship_Internal 또는 Level_Relationship 컬럼 확인
    rel_col = None
    if 'Level_Relationship_Internal' in it_df.columns:
        rel_col = 'Level_Relationship_Internal'
    elif 'Level_Relationship' in it_df.columns:
        rel_col = 'Level_Relationship'
    else:
        return relationships_list
    
    # selected_files가 None이거나 빈 리스트인 경우 전체 데이터 기준으로 처리
    if selected_files is None:
        selected_files = []
    use_all_data = (len(selected_files) == 0)
    
    # 선택된 테이블의 컬럼 정보 수집
    selected_table_columns = {}
    if not use_all_data:
        selected_df = it_df[it_df['FileName'].isin(selected_files)]
        for table_name, group in selected_df.groupby('FileName'):
            selected_table_columns[table_name] = set(group['ColumnName'].dropna().astype(str).str.strip())
    
    # 관계 컬럼이 있는 행만 필터링
    df_with_rel = it_df[
        (it_df[rel_col].notna()) & 
        (it_df[rel_col].astype(str).str.strip() != '')
    ].copy()
    
    # all_tables가 None이거나 빈 set인 경우 모든 테이블 허용
    if all_tables is None:
        all_tables = set()
    use_all_tables = (len(all_tables) == 0)
    
    for _, row in df_with_rel.iterrows():
        file_name = str(row['FileName']).strip()
        col_name = str(row['ColumnName']).strip()
        rel_str = str(row[rel_col]).strip()
        
        is_selected_column = False
        if not use_all_data:
            is_selected_column = (file_name in selected_files and 
                                 col_name in selected_table_columns.get(file_name, set()))
        
        segments = rel_str.split(' -> ')
        parsed_segments = []
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            try:
                file_part, col_part = segment.rsplit('.', 1)
                parsed_segments.append((file_part.strip(), col_part.strip()))
            except ValueError:
                continue
        
        # 전체 데이터 모드이거나 선택된 컬럼/테이블이 포함된 경우
        should_process = use_all_data or is_selected_column or any(seg_file in selected_files for seg_file, _ in parsed_segments)
        
        if should_process:
            for i in range(len(parsed_segments) - 1):
                from_file, from_col = parsed_segments[i]
                to_file, to_col = parsed_segments[i+1]
                
                # all_tables 필터링 (전체 모드가 아닐 때만)
                if not use_all_tables:
                    if from_file not in all_tables or to_file not in all_tables:
                        continue
                
                relationships_list.append((from_file, from_col, to_file, to_col))
                
                if is_selected_column and i == 0 and file_name != from_file:
                    if use_all_tables or (file_name in all_tables and from_file in all_tables):
                        relationships_list.append((file_name, col_name, from_file, from_col))
    
    return relationships_list

def _extract_edge_groups_from_relationships(it_df: pd.DataFrame, selected_files: list = None, all_tables: set = None):
    """Level_Relationship_Internal에서 엣지 그룹을 추출합니다. ERD와 동일한 로직 사용."""
    if selected_files is None:
        selected_files = []
    if all_tables is None:
        all_tables = set()
    
    # ERD와 동일한 로직으로 관계 추출
    relationships_list = _extract_relationships_from_erd_logic(selected_files, all_tables, it_df)
    
    # 엣지 그룹으로 집계 (ERD와 동일하게 all_tables 필터링)
    edge_groups = {}  # {(from_file, to_file): set()}
    edge_groups_by_file = {}  # {file_name: set of (from_file, to_file)}
    
    for from_file, from_col, to_file, to_col in relationships_list:
        # ERD와 동일하게 all_tables 필터링
        if all_tables and (from_file not in all_tables or to_file not in all_tables):
            continue
            
        key = (from_file, to_file)
        if key not in edge_groups:
            edge_groups[key] = set()
        edge_groups[key].add((from_col, to_col))
        
        # 각 파일별로 엣지 그룹 수집
        if from_file not in edge_groups_by_file:
            edge_groups_by_file[from_file] = set()
        edge_groups_by_file[from_file].add(key)
        
        if to_file not in edge_groups_by_file:
            edge_groups_by_file[to_file] = set()
        edge_groups_by_file[to_file].add(key)
    
    return edge_groups_by_file

# -------------------------------------------------
# 4. 데이터 분석/요약 함수 (Data Analysis & Summary)
# -------------------------------------------------
def export_summary_result(integrated_df: pd.DataFrame):
    """    FileName 기준으로 집계하여 요약 정보를 저장합니다. (Level, Rel Table #, 파일릿 계산 추가)    """
    # Level_Relationship_Internal 문자열에서 모든 고유 파일 이름을 추출하는 유틸리티 함수
    def extract_unique_files_from_chain(relationship_str):
        if not isinstance(relationship_str, str) or not relationship_str.strip():
            return set()
        files = set()
        segments = relationship_str.split(' -> ')
        for segment in segments:
            segment = segment.strip()
            if not segment: continue
            try:
                # FileName.Column에서 FileName만 추출
                file_part, _ = segment.rsplit('.', 1)
                files.add(file_part.strip())
            except ValueError:
                continue
        return files

    # 1. 파일별 기본 통계 계산 (Column #, FilePath, Max_Level_Depth)
    def get_max_level_depth(series):
        if 'Level_Depth_Internal' not in integrated_df.columns: return 0
        non_na = series.dropna()
        if non_na.empty: return 0
        try:
            return int(pd.to_numeric(non_na, errors='coerce').max())
        except (ValueError, TypeError):
            return 0

    # Level_Depth_Internal 컬럼이 없으면 기본값 0으로 생성
    if 'Level_Depth_Internal' not in integrated_df.columns:
        integrated_df['Level_Depth_Internal'] = 0
    
    # groupby().agg() 딕셔너리 동적 생성
    agg_dict = {
        'ColumnName': 'nunique',
        'FilePath': lambda x: x.iloc[0] if not x.empty and 'FilePath' in integrated_df.columns else ''
    }
    
    # Level_Depth_Internal 컬럼이 있으면 추가
    if 'Level_Depth_Internal' in integrated_df.columns:
        agg_dict['Level_Depth_Internal'] = get_max_level_depth
    
    table_stats = integrated_df.groupby('FileName').agg(agg_dict).reset_index()
    
    # 컬럼명 변경
    table_stats.rename(columns={'ColumnName': 'Column #'}, inplace=True)
    if 'Level_Depth_Internal' in table_stats.columns:
        table_stats.rename(columns={'Level_Depth_Internal': 'Max_Level'}, inplace=True)
    else:
        table_stats['Max_Level'] = 0
    
    # 2. Level_Relationship_Internal 기반 총 관련 파일 개수 및 파일 리스트 계산 (★★★ 사용자 요청 지표 최적화 ★★★)
    # Level_Relationship_Internal 컬럼이 없으면 기본값 빈 문자열로 생성
    if 'Level_Relationship_Internal' not in integrated_df.columns:
        integrated_df['Level_Relationship_Internal'] = ''
    
    # Level_Relationship_Internal이 있는 행만 필터링
    temp_df = integrated_df[integrated_df['Level_Relationship_Internal'].astype(bool)].copy()
    
    # FileName별로 관련 파일 수집 (더 직접적인 방법)
    related_files_info = {}
    
    for file_name, group in temp_df.groupby('FileName'):
        all_files = set()
        # 각 행의 Level_Relationship_Internal에서 파일 추출
        for _, row in group.iterrows():
            rel_str = row['Level_Relationship_Internal']
            if pd.notna(rel_str) and isinstance(rel_str, str) and rel_str.strip():
                files = extract_unique_files_from_chain(rel_str)
                all_files.update(files)
        
        # 자기 자신(FileName)은 제외
        all_files.discard(file_name)
        
        # 정렬된 리스트로 변환
        sorted_files = sorted(list(all_files))
        related_files_info[file_name] = {
            'count': len(all_files),
            'list': sorted_files
        }

    summary_df = table_stats.copy()

    # Rel Table # (연관 파일 개수)
    summary_df['Rel Table #'] = summary_df['FileName'].apply(
        lambda x: related_files_info.get(x, {}).get('count', 0) if x in related_files_info else 0
    )
    
    # Related Files List (연관 파일 리스트)
    summary_df['Related Files List'] = summary_df['FileName'].apply(
        lambda x: ', '.join(related_files_info.get(x, {}).get('list', [])) if x in related_files_info else ''
    )
    
    summary_df = summary_df.sort_values(by='FileName').fillna(0)
    return summary_df

# -------------------------------------------------
# 5. 관계 탐색 함수 (Relationship Discovery)
# -------------------------------------------------
def get_related_tables(selected_files: list, it_df: pd.DataFrame):
    """선택된 테이블과 관련된 모든 테이블을 찾습니다."""
    # Level_Relationship_Internal 또는 Level_Relationship 컬럼 확인
    rel_col = None
    if 'Level_Relationship_Internal' in it_df.columns:
        rel_col = 'Level_Relationship_Internal'
    elif 'Level_Relationship' in it_df.columns:
        rel_col = 'Level_Relationship'
    else:
        return set(selected_files)
    
    # 선택된 테이블의 컬럼 정보 수집 (벡터화된 연산)
    selected_table_columns = {}
    selected_df = it_df[it_df['FileName'].isin(selected_files)]
    for table_name, group in selected_df.groupby('FileName'):
        selected_table_columns[table_name] = set(group['ColumnName'].dropna().astype(str).str.strip())
    
    # 관계 컬럼이 있는 행만 필터링
    df_with_rel = it_df[
        (it_df[rel_col].notna()) & 
        (it_df[rel_col].astype(str).str.strip() != '')
    ].copy()
    
    all_relations = []
    for _, row in df_with_rel.iterrows():
        file_name = str(row['FileName']).strip()
        col_name = str(row['ColumnName']).strip()
        rel_str = str(row[rel_col]).strip()
        
        is_selected_column = (file_name in selected_files and 
                             col_name in selected_table_columns.get(file_name, set()))
        
        segments = rel_str.split(' -> ')
        parsed_segments = []
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            try:
                file_part, _ = segment.rsplit('.', 1)
                parsed_segments.append((file_part.strip(), ''))
            except ValueError:
                continue
        
        if is_selected_column or any(seg_file in selected_files for seg_file, _ in parsed_segments):
            for i in range(len(parsed_segments) - 1):
                from_file, _ = parsed_segments[i]
                to_file, _ = parsed_segments[i+1]
                all_relations.append((from_file, to_file))
                
                if is_selected_column and i == 0 and file_name != from_file:
                    all_relations.append((file_name, from_file))
    
    related_tables = set(selected_files)
    tables_to_check = set(selected_files)
    
    for _ in range(5):
        newly_added = set()
        for from_table, to_table in all_relations:
            if from_table in tables_to_check:
                newly_added.add(to_table)
            if to_table in tables_to_check:
                newly_added.add(from_table)
        
        if not newly_added:
            break
        
        newly_added -= related_tables
        related_tables.update(newly_added)
        tables_to_check = newly_added
    
    return related_tables

def generate_logical_erd_image(selected_files: list, all_tables: set, pk_map: dict, it_df: pd.DataFrame, show_all_columns:bool):
    """
    논리적 ERD 이미지 생성 (물리적 ERD와 일관된 스타일)
    - 논리적 관계: 컬럼 데이터값으로 연결되는 관계
    - 물리적 ERD와 동일한 node 및 edge 표현 방법 및 색상 사용
    """
    # === 1. Graphviz 시각화 생성 (물리적 ERD와 동일한 설정) ===
    dot = Digraph(comment='Logical ERD', encoding='utf-8')
    dot.attr(rankdir='LR', nodesep='0.5', ranksep='2.5', splines='polyline')
    dot.attr('node', fontname='Malgun Gothic', fontsize='10', shape='none')
    dot.attr('edge', fontname='Malgun Gothic', fontsize='8')
    
    # === 2. 논리적 관계 추출 ===
    relationships_list = _extract_relationships_from_erd_logic(selected_files, all_tables, it_df)
    
    # 연결된 컬럼 수집
    connected_columns = {}
    for from_file, from_col, to_file, to_col in relationships_list:
        if from_file not in connected_columns:
            connected_columns[from_file] = set()
        connected_columns[from_file].add(from_col)
        
        if to_file not in connected_columns:
            connected_columns[to_file] = set()
        connected_columns[to_file].add(to_col)
    
    # === 3. 각 테이블별로 표시할 컬럼 결정 ===
    display_columns = {}
    for table_name in all_tables:
        is_selected = table_name in selected_files
        pk_cols_ordered = pk_map.get(table_name, [])
        pk_cols_set = set(pk_cols_ordered)
        connected_cols = connected_columns.get(table_name, set())
        
        if show_all_columns and is_selected:
            # 상세 모드 & 선택된 테이블: 모든 컬럼 표시
            all_cols = it_df[it_df['FileName'] == table_name]['ColumnName'].unique().tolist()
            all_cols_set = set(all_cols)
            # PK 컬럼은 순서 유지
            pk_to_display = [col for col in pk_cols_ordered if col in all_cols_set]
            # 나머지 컬럼은 정렬
            other_to_display = sorted(list(all_cols_set - pk_cols_set))
            display_columns[table_name] = pk_to_display + other_to_display
        else:
            # 요약 모드 또는 선택되지 않은 테이블: 연결된 컬럼만 표시
            pk_to_display = [col for col in pk_cols_ordered if col in connected_cols]
            other_to_display = sorted(list(connected_cols - pk_cols_set))
            display_columns[table_name] = pk_to_display + other_to_display

    # === 4. 테이블 노드 생성 (물리적 ERD와 동일한 스타일) ===
    def escape_html(text):
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # OracleType 정보 수집 (있는 경우)
    oracle_types = {}
    if 'OracleType' in it_df.columns:
        for _, row in it_df.iterrows():
            table_name = str(row['FileName']).strip()
            col_name = str(row['ColumnName']).strip()
            o_type = str(row['OracleType']).strip() if pd.notna(row['OracleType']) else ""
            if table_name not in oracle_types:
                oracle_types[table_name] = {}
            oracle_types[table_name][col_name] = o_type
    
    # FK 관계에 사용된 컬럼 추출
    fk_columns = set()
    for from_file, from_col, to_file, to_col in relationships_list:
        fk_columns.add((from_file, from_col))
        fk_columns.add((to_file, to_col))
    
    for table_name in sorted(all_tables):
        pk_cols_ordered = pk_map.get(table_name, [])
        pk_cols_set = set(pk_cols_ordered)
        table_cols = display_columns.get(table_name, [])
        
        # selected_files에 table_name이 있으면 오렌지색 아니면 연한 파랑색 (물리적 ERD와 동일)
        header_color = '#FFA500' if table_name in selected_files else '#BBDEFB'
        font_color = 'black'
        is_sel = table_name in selected_files
        
        label = f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" PORT="title">'
        label += f'<TR><TD BGCOLOR="{header_color}"><FONT COLOR="{font_color}"><B>{escape_html(table_name)}</B></FONT></TD></TR>'
        
        pk_to_display = [col for col in table_cols if col in pk_cols_set]
        other_to_display = [col for col in table_cols if col not in pk_cols_set]
        
        # PK 렌더링 (물리적 ERD와 동일한 스타일)
        for col in sorted(pk_to_display):
            safe_col = escape_html(col)
            label += f'<TR><TD ALIGN="LEFT" BGCOLOR="#E3F2FD" PORT="{safe_col}"><B>🔑 {safe_col}</B></TD></TR>'
        
        # 일반/FK 렌더링 (물리적 ERD와 동일한 스타일)
        for col in sorted(other_to_display):
            safe_col = escape_html(col)
            is_fk = (table_name, col) in fk_columns
            prefix = "🔗 " if is_fk else "  "
            label += f'<TR><TD ALIGN="LEFT" PORT="{safe_col}">{prefix}{safe_col}</TD></TR>'
        
        label += '</TABLE>>'
        dot.node(table_name, label)

    # === 5. 논리적 관계 Edge 추가 (물리적 ERD와 동일한 스타일) ===
    edge_groups = {}
    for from_file, from_col, to_file, to_col in relationships_list:
        key = (from_file, to_file)
        if key not in edge_groups:
            edge_groups[key] = []
        edge_groups[key].append((from_col, to_col))
    
    edge_count = 0
    for (from_file, to_file), cols_list in edge_groups.items():
        if from_file not in all_tables or to_file not in all_tables:
            continue
        
        from_col, to_col = cols_list[0]
        safe_from_col = escape_html(from_col)
        safe_to_col = escape_html(to_col)
        
        # 물리적 ERD와 동일한 edge 스타일
        dot.edge(f'{from_file}:{safe_from_col}', 
                f'{to_file}:{safe_to_col}',
                dir='both',
                arrowhead='none',
                arrowtail='crow',
                color='#555555',
                penwidth='1.0')
        edge_count += 1
    
    # ERD 생성 정보 수집
    erd_info = {
        'relationships_list': relationships_list,
        'all_tables': all_tables,
        'pk_map': pk_map,
        'connected_columns': connected_columns,
        'display_columns': display_columns,
        'show_all_columns': show_all_columns,
        'selected_files': selected_files,
        'mode': 'Logical'
    }
    
    return dot, edge_count, erd_info

def create_erd_result_dataframe(selected_files: list, all_tables: set, pk_map: dict, it_df: pd.DataFrame):
    """ERD 생성 결과를 데이터프레임으로 정리합니다. ERD와 동일한 필터링 로직 사용."""
    # ERD와 동일한 로직으로 관계 추출
    relationships_list = _extract_relationships_from_erd_logic(selected_files, all_tables, it_df)
    
    # 엣지 그룹으로 집계 (ERD와 동일)
    edge_groups = {}  # {(from_file, to_file): list of (from_col, to_col)}
    from_edge_groups = {}  # {table_name: set of (from_file, to_file)}
    to_edge_groups = {}  # {table_name: set of (from_file, to_file)}
    
    for from_file, from_col, to_file, to_col in relationships_list:
        # ERD와 동일하게 all_tables 필터링
        if from_file not in all_tables or to_file not in all_tables:
            continue
            
        key = (from_file, to_file)
        if key not in edge_groups:
            edge_groups[key] = []
        edge_groups[key].append((from_col, to_col))
        
        # From 관계 (이 테이블이 참조하는 테이블)
        if from_file not in from_edge_groups:
            from_edge_groups[from_file] = set()
        from_edge_groups[from_file].add(key)
        
        # To 관계 (이 테이블을 참조하는 테이블)
        if to_file not in to_edge_groups:
            to_edge_groups[to_file] = set()
        to_edge_groups[to_file].add(key)
    
    # 컬럼 정보 수집
    from_relations = {}  # {table_name: [(col, to_table, to_col), ...]}
    to_relations = {}  # {table_name: [(from_table, from_col, col), ...]}
    
    for from_file, from_col, to_file, to_col in relationships_list:
        if from_file not in from_relations:
            from_relations[from_file] = []
        from_relations[from_file].append((from_col, to_file, to_col))
        
        if to_file not in to_relations:
            to_relations[to_file] = []
        to_relations[to_file].append((from_file, from_col, to_col))
    
    result_data = []
    for table_name in sorted(all_tables):
        is_selected = table_name in selected_files
        pk_cols_ordered = pk_map.get(table_name, [])
        pk_cols_str = ', '.join(pk_cols_ordered) if pk_cols_ordered else ''
        
        all_fk_cols = set()
        parent_tables_set = set()
        child_tables_set = set()
        
        if table_name in from_relations:
            for from_col, to_table, _ in from_relations[table_name]:
                all_fk_cols.add(from_col)
                if to_table:
                    parent_tables_set.add(to_table)
        
        if table_name in to_relations:
            for from_table, _, to_col in to_relations[table_name]:
                all_fk_cols.add(to_col)
                if from_table:
                    child_tables_set.add(from_table)
        
        from_edge_count = len(from_edge_groups.get(table_name, set()))
        to_edge_count = len(to_edge_groups.get(table_name, set()))
        
        result_data.append({
            '테이블명': table_name,
            '선택여부': '✓' if is_selected else '',
            'PK 컬럼': pk_cols_str,
            'FK 컬럼': ', '.join(sorted(all_fk_cols)) if all_fk_cols else '',
            'Parent 테이블': ', '.join(sorted(parent_tables_set)) if parent_tables_set else '',
            'Child 테이블': ', '.join(sorted(child_tables_set)) if child_tables_set else '',
            '관계 수': from_edge_count + to_edge_count
        })
    
    return pd.DataFrame(result_data)

# #----------------------------------------------------------------------------------------
# # 데이터 추출 및 로드
# #-----------------------------------------------------------------------------------------
# def load_data_all(files_to_load):
#     """  데이터 추출 및 로드    """
#     loaded_data = {}

#     for name, path in files_to_load.items():
#         if not path.exists():
#             st.error(f"{path.name} 파일이 없습니다")
#             return None
#         df = pd.read_csv(path, encoding='utf-8-sig')
#         loaded_data[name] = df
#     return loaded_data

# def create_pk_fk_from_mapping(df_cr):
#     """     2nd Step: 데이터 통합 & find pk & fk    """

#     # 1. 데이터 추출 및 로드
#     pk_map, fk_map, it_df = _extract_and_load_erd_data_impl(df_cr)
    
#     if pk_map is None or fk_map is None or it_df is None:
#         st.error("ERD 데이터를 생성할 수 없습니다. 입력 파일의 데이터를 확인해주세요.")
#         return None, None, None

#     return pk_map, fk_map, it_df

def render_column_control_tab(df_cm):
    """
    컬럼 제어 설정 탭 렌더링 (24_ERD_Column_Setup.py 기능 통합)
    
    Args:
        df_cm: CodeMapping.csv 데이터프레임
    """
    if df_cm is None or df_cm.empty:
        st.warning("CodeMapping.csv 데이터를 사용할 수 없습니다.")
        return
    
    # MasterType이 'Master'인 데이터만 필터링
    df_cm_master = df_cm[df_cm['MasterType'] == 'Master'].copy() if 'MasterType' in df_cm.columns else df_cm.copy()
    
    # 1. 블랙리스트 설정 기능
    def manage_exclusive_config_inline(df):
        """ERD_exclusive.csv 관리 및 데이터 모델 불일치 상세 분석 기능"""
        from collections import defaultdict
        
        # 최신 정보(통계) 생성
        def get_fresh_stats(df_inner):
            col_to_tables = defaultdict(set)
            col_types = {}
            for _, row in df_inner.iterrows():
                c = str(row['ColumnName']).strip()
                f = str(row['FileName']).strip()
                t = str(row.get('OracleType', '')).strip().upper() if pd.notna(row.get('OracleType')) else ""
                if c and f:
                    col_to_tables[c].add(f)
                    if c not in col_types or t in ['DATE', 'TIMESTAMP', 'DATETIME']:
                        col_types[c] = t
            
            data = []
            for col, tables in col_to_tables.items():
                t_type = col_types.get(col, "")
                data.append({
                    "ColumnName": col,
                    "OracleType": t_type,
                    "ConnectionCount": len(tables),
                    "exclusive": 1 if t_type in ['DATE', 'TIMESTAMP', 'DATETIME'] else 0
                })
            return pd.DataFrame(data)
        
        current_df = get_fresh_stats(df)
        
        # 파일 로드 및 병합
        if EXCLUSIVE_FILE.exists():
            try:
                old_df = pd.read_csv(EXCLUSIVE_FILE, encoding='utf-8-sig')
                if 'exclusive' in old_df.columns:
                    old_settings = old_df[['ColumnName', 'exclusive']].drop_duplicates('ColumnName')
                    final_df = pd.merge(current_df, old_settings, on='ColumnName', how='left', suffixes=('_init', ''))
                    final_df['exclusive'] = final_df['exclusive'].fillna(final_df['exclusive_init']).astype(int)
                    final_df = final_df.drop(columns=['exclusive_init'])
                else:
                    final_df = current_df
            except Exception as e:
                st.warning(f"기존 파일 읽기 오류: {e}")
                final_df = current_df
        else:
            final_df = current_df
        
        final_df = final_df.sort_values(by="ConnectionCount", ascending=False)
        
        # UI: 블랙리스트 설정
        st.subheader("물리적 관계에서 제외할 컬럼 설정")
        final_df['exclusive_bool'] = final_df['exclusive'].astype(bool)
        
        edited_df = st.data_editor(
            final_df,
            column_config={"exclusive_bool": st.column_config.CheckboxColumn("제외"), "exclusive": None},
            disabled=["ColumnName", "OracleType", "ConnectionCount"],
            hide_index=True, width='stretch', key="ex_editor_select_files"
        )
        
        if st.button("설정 저장하기", type="primary", key="save_exclusive_select_files"):
            save_df = edited_df.copy()
            save_df['exclusive'] = save_df['exclusive_bool'].astype(int)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            save_df.drop(columns=['exclusive_bool']).to_csv(EXCLUSIVE_FILE, index=False, encoding='utf-8-sig')
            st.toast("설정이 파일에 저장되었습니다!", icon="✅")
            st.rerun()
        
        return edited_df[edited_df['exclusive_bool'] == True]['ColumnName'].tolist()
    
    # 2. 데이터 모델 일관성 분석 기능
    def render_consistency_checks_inline(df):
        st.write("---")
        st.subheader("🧪 2. 데이터 모델 일관성 분석")
        tab_inner1, tab_inner2 = st.tabs(["⚠️ OracleType 불일치", "📝 Format 불일치 (FormatCnt ≤ 3)"])
        
        with tab_inner1:
            # Group By: ColumnName, OracleType 별 건수 및 파일 리스트
            type_group = df.groupby(['ColumnName', 'OracleType']).agg(
                Count=('FileName', 'count'),
                FileList=('FileName', lambda x: ", ".join(sorted(x.unique())))
            ).reset_index()
            
            # 2개 이상의 타입을 가진 컬럼명 추출
            diff_type_cols = type_group.groupby('ColumnName').filter(lambda x: len(x) > 1)['ColumnName'].unique()
            
            if len(diff_type_cols) > 0:
                st.warning(f"동일 컬럼명 내 OracleType이 다른 사례: {len(diff_type_cols)}건")
                res_type = type_group[type_group['ColumnName'].isin(diff_type_cols)]
                st.dataframe(res_type.sort_values('ColumnName'), width='stretch', hide_index=True)
            else:
                st.success("모든 동일 컬럼의 OracleType이 일치합니다.")
        
        with tab_inner2:
            if 'Format' in df.columns and 'FormatCnt' in df.columns:
                f_base = df[df['FormatCnt'] <= 3].copy()
                # Group By: ColumnName, Format 별 건수 및 파일 리스트
                format_group = f_base.groupby(['ColumnName', 'Format']).agg(
                    Count=('FileName', 'count'),
                    FileList=('FileName', lambda x: ", ".join(sorted(x.unique())))
                ).reset_index()
                
                diff_format_cols = format_group.groupby('ColumnName').filter(lambda x: len(x) > 1)['ColumnName'].unique()
                
                if len(diff_format_cols) > 0:
                    st.warning(f"FormatCnt 3이하 컬럼 중 Format 불일치: {len(diff_format_cols)}건")
                    res_format = format_group[format_group['ColumnName'].isin(diff_format_cols)]
                    st.dataframe(res_format.sort_values('ColumnName'), width='stretch', hide_index=True)
                else:
                    st.success("조건에 해당하는 모든 컬럼의 Format이 일치합니다.")
            else:
                st.info("Format 정보가 데이터프레임에 없습니다.")
    
    # 블랙리스트 설정 실행
    blacklist = manage_exclusive_config_inline(df_cm_master)
    if blacklist:
        st.caption(f"현재 제외된 컬럼 수: {len(blacklist)}개")
    
    # 데이터 모델 일관성 분석 실행 (별도 프로그램에서 활용할 예정)
    # render_consistency_checks_inline(df_cm_master)

# -------------------------------------------------
# 7. 파일 선택 관련 함수 (File Selection)
# -------------------------------------------------
def prepare_file_selection_data(df_cr, df_cm=None, df_ex=None):
    """
    파일 선택을 위한 데이터 준비 함수
    
    Args:
        df_cr: 논리적 정보를 추출할 데이터프레임 (CodeMapping_erd.csv 또는 CodeMapping.csv)
        df_ex: ERD_exclusive.csv (제외할 컬럼 정보)
    
    Returns:
        tuple: (total_df, df_cm) - 준비된 데이터프레임과 원본 df_cm
        None: 필수 컬럼이 없거나 오류 발생 시
    """
    # df_cm이 제공되지 않으면 df_input 사용
    if df_cm is None:
        df_cm = df_cr

    # df_ex에서 exclusive == 1인 컬럼 제외 목록 생성
    excluded_columns = set()
    if df_ex is not None and not df_ex.empty:
        if 'ColumnName' in df_ex.columns and 'exclusive' in df_ex.columns:
            excluded_df = df_ex[df_ex['exclusive'] == 1]
            if not excluded_df.empty:
                excluded_columns = set(excluded_df['ColumnName'].astype(str).str.strip().unique())
    
    # 초기 데이터프레임에서 exclusive == 1인 컬럼 제외
    df_cr_filtered = df_cr.copy()
    df_cm_filtered = df_cm.copy()
    
    if excluded_columns:
        # df_input에서 제외
        if 'ColumnName' in df_cr_filtered.columns:
            df_cr_filtered = df_cr_filtered[
                ~df_cr_filtered['ColumnName'].astype(str).str.strip().isin(excluded_columns)
            ]
        
        # df_cm에서 제외
        if 'ColumnName' in df_cm_filtered.columns:
            df_cm_filtered = df_cm_filtered[
                ~df_cm_filtered['ColumnName'].astype(str).str.strip().isin(excluded_columns)
            ]

    # 필수 컬럼 확인
    required_cols = ['FileName', 'ColumnName', 'FilePath', 'PK']
    if not all(col in df_cm_filtered.columns for col in required_cols):
        st.warning("CodeMapping.csv에서 필요한 컬럼(FileName, ColumnName, FilePath, PK)을 찾을 수 없습니다.")
        return None, None

    # 1. 논리적 파일 요약 정보 생성 (df_input_filtered 사용 - Level_Relationship_Internal 포함 가능)
    summary_df = export_summary_result(df_cr_filtered)

    # 2. PK 컬럼 정보 추출 (df_cm_filtered 사용)
    pk_cols = df_cm_filtered[df_cm_filtered['PK'] == 1].groupby('FileName')['ColumnName'].apply(
        lambda x: ', '.join([str(item) for item in x if pd.notna(item) and str(item).strip()])
    ).reset_index()
    pk_cols.columns = ['FileName', 'PK Columns']

    # 3. 물리적 관계 계층 정보 계산 (precompute_physical_hierarchy 결과, df_cm_filtered 사용)
    if 'physical_hierarchy_df' not in st.session_state:
        st.session_state.physical_hierarchy_df = precompute_physical_hierarchy(df_cm_filtered)
    physical_hierarchy_df = st.session_state.physical_hierarchy_df

    # 4. 모든 정보 통합 (PK Columns + Summary + Physical Hierarchy)
    # summary_df에 이미 논리적 정보(Column #, Max_Level, Rel Table #, Related Files List)가 포함되어 있음
    total_df = pd.merge(pk_cols, summary_df, on='FileName', how='left')
    total_df = pd.merge(total_df, physical_hierarchy_df, on='FileName', how='left')
    total_df = total_df[(total_df['Column #'].fillna(0) > 1)]
    total_df = total_df.sort_values(by='FileName')

    # 5. 선택 체크박스 컬럼 추가
    total_df['선택'] = False

    # 6. 컬럼 순서 : 선택 -> 기본 정보 -> 물리적 관계 정보 -> 논리적 관계 정보 -> 추가 정보
    base_cols = ['선택', 'FileName', 'PK Columns']
    physical_cols = ['Level1_Cnt', 'Level2_Cnt', 'Level3_Cnt', 'Total_Related', 'Related_List']
    logical_cols = ['Column #', 'Max_Level', 'Rel Table #', 'Related Files List']
    extra_cols = ['FilePath']

    # 존재하는 컬럼만 선택
    cols_order = []
    for col_group in [base_cols, physical_cols, logical_cols, extra_cols]:
        cols_order.extend([col for col in col_group if col in total_df.columns])

    total_df = total_df[cols_order]
    
    return total_df, df_cm

def select_files(df_cr, df_cm=None, df_ex=None) -> list:
    """
    2nd Step: File Information
    논리적 연결관계(logical_cols) 정보를 구하지 못하는 경우에도 함수가 에러 없이 동작하도록 처리합니다.
    
    df_cr: 논리적 정보를 추출할 데이터프레임 (CodeMapping_erd.csv 또는 CodeMapping.csv)
    df_ex: ERD_exclusive.csv (제외할 컬럼 정보)
    """
    st.subheader("File Information & Select File")
    
    # 데이터 준비
    total_df, df_cm = prepare_file_selection_data(df_cr, df_cm, df_ex)
    if total_df is None:
        return None

    tab1, tab2, tab3, tab4 = st.tabs(["분석 파일 선택", "물리적 연결관계 정보", "논리적 연결관계 정보", "컬럼 제어 설정"])
    with tab1:
        st.write("파일별 물리적, 논리적 연결관계 정보 요약입니다. (컬럼헤드에 마우스를 위치하면 설명이 있습니다)")
        cols = ['선택', 'FileName', 'PK Columns', 'Column #', 'Level1_Cnt', 'Level2_Cnt', 'Level3_Cnt', 'Total_Related', 'Rel Table #', 'Max_Level']
        select_df = total_df[cols].copy()
        select_df = st.data_editor(select_df, hide_index=True, width=1600, height=500, column_config={
            '선택': st.column_config.CheckboxColumn('선택', width=80),
            'FileName': st.column_config.TextColumn(help='파일 이름', width=150),
            'PK Columns': st.column_config.TextColumn('PK컬럼', help='PK 컬럼', width=100),
            'Column #': st.column_config.NumberColumn('컬럼수', help='컬럼 수', width=50),
            'Level1_Cnt': st.column_config.NumberColumn('1관계', help='물리적 1단계 연결 파일 수', width=50),
            'Level2_Cnt': st.column_config.NumberColumn('2관계', help='물리적 2단계 연결 파일 수', width=50),
            'Level3_Cnt': st.column_config.NumberColumn('3관계', help='물리적 3단계 연결 파일 수', width=50),
            'Total_Related': st.column_config.NumberColumn('물리관계', help='물리적 총 연결 파일 수', width=80),
            'Rel Table #': st.column_config.NumberColumn('논리관계', help='논리적 파일 연결 그룹 개수', width=80),
        })

    with tab2:
        cols = ['FileName', 'PK Columns', 'Column #', 'Level1_Cnt', 'Level2_Cnt', 'Level3_Cnt', 'Total_Related', 'Related_List', 'FilePath']
        display_df = total_df[cols].copy()
        st.write("파일별 물리적 연결관계 정보 요약입니다. (컬럼헤드에 마우스를 위치하면 설명이 있습니다)")
        st.dataframe(display_df, hide_index=True, width=1200, height=500, column_config={
            'FileName': st.column_config.TextColumn(help='파일 이름', width=150),
            'PK Columns': st.column_config.TextColumn('PK컬럼', help='PK 컬럼', width=100),
            'Column #': st.column_config.NumberColumn('컬럼수', help='컬럼 수', width=50),
            'Level1_Cnt': st.column_config.NumberColumn('1관계', help='물리적 1단계 연결 파일 수', width=50),
            'Level2_Cnt': st.column_config.NumberColumn('2관계', help='물리적 2단계 연결 파일 수', width=50),
            'Level3_Cnt': st.column_config.NumberColumn('3관계', help='물리적 3단계 연결 파일 수', width=50),
            'Total_Related': st.column_config.NumberColumn('물리관계', help='물리적 총 연결 파일 수', width=50),
            'Related_List': st.column_config.TextColumn('물리관계파일', help='물리적 연결된 파일 목록', width=150),
        })
    with tab3:
        cols = ['FileName', 'PK Columns', 'Column #', 'Max_Level', 'Rel Table #', 'Related_List']
        display_df = total_df[cols].copy()
        st.write("파일별 논리적 연결관계 정보 요약입니다. (컬럼헤드에 마우스를 위치하면 설명이 있습니다)")
        st.dataframe(display_df, hide_index=True, width=1200, height=500, column_config={
            'FileName': st.column_config.TextColumn(help='파일 이름', width=150),
            'PK Columns': st.column_config.TextColumn('PK컬럼', help='PK 컬럼', width=100),
            'Column #': st.column_config.NumberColumn('컬럼수', help='컬럼 수', width=50),
            'Max_Level': st.column_config.NumberColumn('논리레벨', help='논리적 최대 레벨', width=50),
            'Rel Table #': st.column_config.NumberColumn('논리관계', help='논리적 파일 연결 그룹 개수', width=50),
            'Related_List': st.column_config.TextColumn('논리관계파일', help='논리적 연결된 파일 목록', width=150),
        })
    
    with tab4:
        # 컬럼 제어 설정 탭 렌더링
        render_column_control_tab(df_cm)

    # 8. 선택된 테이블 추출
    selected_files = select_df[select_df['선택'] == True]['FileName'].tolist()
    
    if not selected_files:
        st.info(f"파일을 선택하세요. 관계수가 많은면 다이어그램 생성에 시간이 오래 걸릴 수 있습니다.")
        return None

    return selected_files
#-----------------------------------------------------------------------------------------
# -------------------------------------------------
# 11. ERD 표시 함수 (ERD Display)
# -------------------------------------------------
def generate_logical_erd(selected_files, pk_map, it_df, show_all_columns:bool):
    """
    selected_files: 선택한 파일테이블 리스트
    pk_map: PK 컬럼 맵
    it_df: CodeMapping_erd.csv 데이터프레임
    show_all_columns: 상세 정보 표시 여부
    """
    
    st.write("---")
    st.subheader("⚙️ Logical ERD 생성 및 탐색 설정")
    
    anchor_table = selected_files[0] if isinstance(selected_files[0], str) else str(selected_files[0])

    try:
        # 관련 테이블 탐색
        related_tables = get_related_tables(selected_files, it_df)
        
        related_table_count = len(related_tables) # 연결된 테이블 수
        
        if related_table_count > MAX_RELATED_TABLE_COUNT:
            st.error(f"연결된 테이블 수가 {MAX_RELATED_TABLE_COUNT}개를 초과했습니다.")
            return False
        
        if not related_tables or len(related_tables) == 0:
            st.warning(f"⚠️ '{anchor_table}'와 연결된 테이블을 찾을 수 없습니다.")
        else:
            # related_tables를 set으로 변환
            if isinstance(related_tables, list):
                related_list = related_tables
            else:
                related_list = list(related_tables) if hasattr(related_tables, '__iter__') else [related_tables]
            
            # ERD 생성
            dot, edge_count, erd_info = generate_logical_erd_image(selected_files, set(related_list), pk_map, it_df, show_all_columns)
            
            if dot:
                suffix = f"Logical_{anchor_table}"
                display_erd_with_download(dot, suffix, edge_count)
                st.success(f"✅ 분석 완료: 총 {len(related_list)}개 테이블 연결됨")
    except Exception as e:
        st.error(f"❌ ERD 생성 중 오류가 발생했습니다: {str(e)}")
        import traceback
        st.error(traceback.format_exc())

#-----------------------------------------------------------------------------------------
def display_erd_result(selected_files, pk_map, it_df):
    """     4th Step: Data Relationship Diagram 결과 요약    """
    st.divider()
    st.subheader("3. Data Relationship Diagram 결과 요약")

    related_tables = get_related_tables(selected_files, it_df)

    tab1, tab2, tab3 = st.tabs(["Data Relationship Diagram 결과 요약", "선택된 테이블 상세 정보", "관계된 테이블 상세 정보"])
    with tab1:
        erd_result_df = create_erd_result_dataframe(selected_files, related_tables, pk_map, it_df)
        st.dataframe(
            erd_result_df, hide_index=True, width='stretch', height=500,
            column_config={
                '테이블명': st.column_config.TextColumn('테이블명', width=150),
                '선택여부': st.column_config.TextColumn('선택', width=50),
                'PK 컬럼': st.column_config.TextColumn('PK 컬럼', width=150),
                'FK 컬럼': st.column_config.TextColumn('FK 컬럼', width=150),
                'Parent 테이블': st.column_config.TextColumn('Parent 테이블', width=200),
                'Child 테이블': st.column_config.TextColumn('Child 테이블', width=200),
                '관계 수': st.column_config.NumberColumn('관계 수', width=50)
            }
        )

    with tab2:
        selected_files_df = it_df[it_df['FileName'].isin(selected_files)]
        selected_files_df = selected_files_df.drop(columns=['FilePath'])
        st.dataframe(selected_files_df, hide_index=True, width=1000, height=500)

    with tab3:
        related_tables_df = it_df[it_df['FileName'].isin(related_tables)]
        related_tables_df = related_tables_df.drop(columns=['FilePath'])
        st.dataframe(related_tables_df, hide_index=True, width=1000, height=500)

    st.divider()
    summary = {
        "총 테이블 수": f"{len(erd_result_df)}",
        "선택된 테이블 수": f"{len(erd_result_df[erd_result_df['선택여부'] == '✓'])}",
        "총 관계 수": f"{erd_result_df['관계 수'].sum()}",
        "PK 보유 테이블": f"{len(erd_result_df[erd_result_df['PK 컬럼'] != ''])}"
    }

    metric_colors = {
        "총 테이블 수":     "#1f77b4",       # 파랑색
        "선택된 테이블 수":  "#2ca02c",       # 초록색
        "총 관계 수":       "#9467bd",       # 보라색
        "PK 보유 테이블":   "#ff7f0e",       # 빨강색
    }

    display_kpi_metrics(summary, metric_colors, 'Data Relationship Diagram 결과 요약 지표')

#-----------------------------------------------------------------------------------------
# ERD 생성 Function
# 6. 물리적 계층 분석 함수 (Physical Hierarchy Analysis)
#-----------------------------------------------------------------------------------------
def precompute_physical_hierarchy(df):
    """모든 테이블에 대해 4단계까지의 물리적 관계 계층을 계산"""
    # 1. 인덱싱 (이전 로직 동일)
    table_to_cols = defaultdict(dict)
    col_to_tables = defaultdict(set)
    for _, row in df.iterrows():
        f, c, pk, o = str(row['FileName']), str(row['ColumnName']), str(row['PK']), str(row['OracleType'])
        # 날짜 및 공통필드 제외 로직 적용 (생략)
        table_to_cols[f][c] = pk.upper() in ['1', 'Y', 'TRUE']
        col_to_tables[c].add(f)

    # 2. 전수 조사
    hierarchy_data = []
    all_tables = sorted(table_to_cols.keys())

    for start_node in all_tables:
        levels = {0: {start_node}}
        visited = {start_node}
        
        for i in range(1, 4): # 3단계까지
            next_layer = set()
            for current_node in levels[i-1]:
                if current_node not in table_to_cols: continue
                for col, is_pk in table_to_cols[current_node].items():
                    neighbors = col_to_tables.get(col, set())
                    for nb in neighbors:
                        if nb not in visited:
                            # 물리적 관계 성립 조건
                            if is_pk or table_to_cols[nb].get(col, False):
                                next_layer.add(nb)
                                visited.add(nb)
            levels[i] = next_layer
        
        hierarchy_data.append({
            "FileName": start_node,
            "Level1_Cnt": len(levels[1]),
            "Level2_Cnt": len(levels[2]),
            "Level3_Cnt": len(levels[3]),
            "Total_Related": len(visited) - 1,
            "Related_List": ", ".join(list(visited)[1:6]) # + "..." 일부 샘플 표시
        })
    
    return pd.DataFrame(hierarchy_data)

def get_physical_n_level_tables(codemapping_df, start_table, level, df_ex:pd.DataFrame = None):
    """
    물리적 컬럼 매칭 기반 N-Level 테이블 탐색 (심층 탐색 보강) 
    df_ex: ERD_exclusive.csv 데이터프레임 (제외할 컬럼 정보)
    반환: (테이블 리스트, 테이블별 레벨 딕셔너리)
    """
    
    # df_ex에서 exclusive == 1인 컬럼 블랙리스트 생성
    blacklist_columns = set()
    if df_ex is not None and not df_ex.empty:
        if 'ColumnName' in df_ex.columns and 'exclusive' in df_ex.columns:
            # exclusive == 1인 컬럼명 추출
            excluded_df = df_ex[df_ex['exclusive'] == 1]
            if not excluded_df.empty:
                blacklist_columns = set(excluded_df['ColumnName'].astype(str).str.strip().unique())
    
    # 3. 고속 탐색을 위한 데이터 구조 빌드
    # table_to_cols: { 테이블명: { 컬럼명: PK여부 } }
    # col_to_tables: { 컬럼명: { 테이블명1, 테이블명2 } }
    table_to_cols = defaultdict(dict)
    col_to_tables = defaultdict(set)
    
    for _, row in codemapping_df.iterrows():
        f_name = str(row['FileName']).strip()
        c_name = str(row['ColumnName']).strip()
        is_pk = str(row['PK']).upper() in ['1', '1.0', 'Y', 'TRUE']
        
        # 제외 조건 필터링 (블랙리스트만)
        if c_name in blacklist_columns:
            continue
            
        table_to_cols[f_name][c_name] = is_pk
        col_to_tables[c_name].add(f_name)

    # 3. N-Level 탐색 (BFS) - 레벨 정보 추적
    visited_tables = {start_table}
    table_levels = {start_table: 0}  # 각 테이블의 레벨 정보
    current_layer = {start_table}
    
    # 지정된 level만큼 반복 탐색
    for i in range(level):
        next_layer = set()
        
        for table in current_layer:
            # 현재 레이어의 테이블이 가진 모든 컬럼을 조사
            my_columns = table_to_cols.get(table, {})
            
            for col_name, my_is_pk in my_columns.items():
                # 해당 컬럼을 공유하는 다른 테이블들(이웃)을 찾음
                potential_neighbors = col_to_tables.get(col_name, set())
                
                for neighbor in potential_neighbors:
                    if neighbor in visited_tables:
                        continue
                    
                    # [핵심] 물리적 관계 성립 조건: 
                    # 내 컬럼이 PK거나, 상대방의 동일한 컬럼이 PK여야 함
                    neighbor_is_pk = table_to_cols[neighbor].get(col_name, False)
                    
                    if my_is_pk or neighbor_is_pk:
                        next_layer.add(neighbor)
                        visited_tables.add(neighbor)
                        table_levels[neighbor] = i + 1  # 레벨 정보 저장
        
        # 다음 레이어가 없으면 중단
        if not next_layer:
            break
        current_layer = next_layer
        
    return list(visited_tables), table_levels

# -------------------------------------------------
# 8. ERD 유틸리티 함수 (ERD Utilities)
# -------------------------------------------------
def get_optimal_dpi(table_count: int) -> str:
    """테이블 수에 따라 가독성이 가장 좋은 DPI 반환"""
    if table_count <= 10: return '100'   # 적은 테이블은 너무 크지 않게
    if table_count <= 20: return '200'  # 중간 규모
    if table_count <= 50: return '300'  # 고해상도 필요
    return '450' # 대규모 관계망 (확대용)

def display_erd_with_download(dot, suffix: str, table_count: int):
    """ERD 표시 및 고해상도 다운로드 공통 처리"""
    # st.subheader(f"📊 {suffix} 다이어그램")
    st.write(f"🔍 분석 완료: 총 {table_count}개 테이블이 다이어그램에 포함되었습니다.")
    
    # 1. 화면 표시용 (Streamlit 기본 렌더링)
    st.graphviz_chart(dot, width='stretch')
    
    # 2. 고해상도 파일 저장 및 다운로드 버튼
    file_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    # filename = f"ERD_{suffix}_{file_time}"
    filename = f"ERD_{suffix}"
    
    # DPI 설정 적용
    dpi_val = get_optimal_dpi(table_count)
    dot.attr(dpi=dpi_val)
    
    try:
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        output_path_no_ext = IMAGE_DIR / filename
        
        # 파일 저장
        rendered_path = dot.render(str(output_path_no_ext), format='png', cleanup=True)
        actual_path = Path(rendered_path)
        
        if actual_path.exists():
            with open(actual_path, "rb") as f:
                st.download_button(
                    label=f"💾 PNG 다운로드 ",
                    data=f.read(),
                    file_name=actual_path.name,
                    mime="image/png",
                    key=f"dl_{filename}"
                )
    except Exception as e:
        st.warning(f"⚠️ 파일 저장 중 오류가 발생했으나 차트는 표시되었습니다: {e}")

# -------------------------------------------------
# 9. ERD 이미지 생성 함수 (ERD Image Generation)
# -------------------------------------------------
def generate_physical_erd_image(codemapping_df, df_ex, selected_files, related_tables, show_all_columns=False, table_levels=None):
    """
    물리적 관계 기반 ERD 생성 (N-Level 직접 연결만 표시)
    table_levels: {테이블명: 레벨} 딕셔너리 (선택된 테이블은 레벨 0)
    """
    # 초기 테이블 셋 설정
    related_tables_set = set(related_tables)
    
    # 레벨 정보가 없으면 모든 테이블을 레벨 0으로 설정
    if table_levels is None:
        table_levels = {table: 0 for table in related_tables_set}
        for table in selected_files:
            table_levels[table] = 0
    
    # 1. 블랙리스트(exclusive) 처리
    ex_cols = set()
    if df_ex is not None and not df_ex.empty and 'exclusive' in df_ex.columns:
        ex_cols = set(df_ex[df_ex['exclusive'] == 1]['ColumnName'].astype(str).str.strip().unique())

    # 2. 데이터 인덱싱 (성능 최적화)
    table_info = defaultdict(dict)
    col_to_tables = defaultdict(set)
    
    for _, row in codemapping_df.iterrows():
        f = str(row['FileName']).strip()
        c = str(row['ColumnName']).strip()
        is_pk = str(row.get('PK', '')).upper() in ['1', '1.0', 'Y', 'TRUE']
        o_type = str(row.get('OracleType', '')).strip().upper()
        
        table_info[f][c] = {'is_pk': is_pk, 'o_type': o_type}
        if c not in ex_cols:
            col_to_tables[c].add(f)

    # 3. N-Level 관계 추론 (인접한 레벨 간의 관계만 찾기 - 직접 연결만 표시)
    # 선택된 테이블(레벨 0)과 직접 연결된 레벨 1 테이블 간의 관계만 찾음
    # 레벨 1과 레벨 2 간의 관계도 찾지만, 같은 레벨 내 관계는 찾지 않음
    fk_candidates = set()
    
    # related_tables_set에 포함된 테이블들 간의 관계 찾기 (레벨 제한 적용)
    for from_table in related_tables_set:
        if from_table not in table_info: continue
        
        from_level = table_levels.get(from_table, 0)
        
        for col, info in table_info[from_table].items():
            if col not in col_to_tables: continue
            
            for to_table in col_to_tables[col]:
                # to_table도 related_tables_set에 포함된 경우에만 관계 추가
                if to_table not in related_tables_set:
                    continue
                    
                if from_table == to_table: continue
                
                to_level = table_levels.get(to_table, 0)
                
                # 레벨 제한: 인접한 레벨 간의 관계만 찾기 (레벨 차이가 1 이하)
                # 같은 레벨 내 관계는 찾지 않음 (성능 향상 및 명확성)
                level_diff = abs(from_level - to_level)
                if level_diff > 1:
                    continue
                
                # 이미 찾은 관계라면 스킵
                if (from_table, to_table, col) in fk_candidates or (to_table, from_table, col) in fk_candidates:
                    continue
                
                # 관계 성립 조건 (최소 한쪽은 PK)
                to_is_pk = table_info[to_table].get(col, {}).get('is_pk', False)
                if info['is_pk'] or to_is_pk:
                    # 방향성 결정 (PK가 부모, 레벨이 낮은 쪽이 부모)
                    if to_is_pk and not info['is_pk']:
                        fk_candidates.add((from_table, to_table, col))
                    elif from_level < to_level:
                        # 레벨이 낮은 쪽이 부모
                        fk_candidates.add((from_table, to_table, col))
                    else:
                        fk_candidates.add((to_table, from_table, col))

    fk_candidates = list(fk_candidates)
    display_count = len(related_tables_set)

    # 4. Graphviz 렌더링 (이전과 동일)
    dot = Digraph(comment='Physical ERD', encoding='utf-8')
    dot.attr(rankdir='LR', nodesep='0.5', ranksep='1.5', splines='polyline')
    dot.attr('node', fontname='Malgun Gothic', fontsize='10', shape='none')

    for table_name in sorted(related_tables_set):
        is_anchor = table_name in selected_files
        header_bg = '#FFA500' if is_anchor else '#BBDEFB'
        
        label = f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" PORT="title">'
        label += f'<TR><TD BGCOLOR="{header_bg}"><B>{table_name}</B></TD></TR>'
        
        cols = table_info[table_name]
        involved_cols = {c for f, t, c in fk_candidates if f == table_name or t == table_name}
        
        for c_name in sorted(cols.keys()):
            info = cols[c_name]
            if info['is_pk'] or c_name in involved_cols or (show_all_columns and is_anchor):
                prefix = "🔑 " if info['is_pk'] else ("🔗 " if c_name in involved_cols else "  ")
                bg = "#E3F2FD" if info['is_pk'] else "#FFFFFF"
                label += f'<TR><TD ALIGN="LEFT" BGCOLOR="{bg}" PORT="{c_name}">{prefix}{c_name}</TD></TR>'
        
        label += '</TABLE>>'
        dot.node(table_name, label)

    for f_tab, t_tab, col in fk_candidates:
        dot.edge(f'{f_tab}:{col}', f'{t_tab}:{col}', dir='both', 
                 arrowhead='none', arrowtail='crow', color='#444444')

    # ERD 생성 정보 수집
    erd_info = {
        'table_info': table_info,
        'fk_candidates': fk_candidates,
        'related_tables_set': related_tables_set,
        'table_levels': table_levels,
        'involved_cols_by_table': {table: {c for f, t, c in fk_candidates if f == table or t == table} 
                                    for table in related_tables_set},
        'show_all_columns': show_all_columns,
        'selected_files': selected_files,
        'mode': 'Physical'  # 모드 정보 추가
    }
    
    return dot, display_count, erd_info

def generate_combined_erd_image(codemapping_df, df_ex, df_cr, selected_files, related_tables, table_levels, pk_map, it_df, show_all_columns=False):
    """
    Physical & Logical 통합 ERD 생성 (색상으로 구분)
    - Physical 연결만: 파란색 (#0000FF)
    - Logical 연결만: 빨간색 (#FF0000)
    - 두 개 모두 연결: 보라색 (#800080)
    """
    related_tables_set = set(related_tables)
    
    # 1. 블랙리스트(exclusive) 처리
    ex_cols = set()
    if df_ex is not None and not df_ex.empty and 'exclusive' in df_ex.columns:
        ex_cols = set(df_ex[df_ex['exclusive'] == 1]['ColumnName'].astype(str).str.strip().unique())

    # 2. 데이터 인덱싱
    table_info = defaultdict(dict)
    col_to_tables = defaultdict(set)
    
    for _, row in codemapping_df.iterrows():
        f = str(row['FileName']).strip()
        c = str(row['ColumnName']).strip()
        is_pk = str(row.get('PK', '')).upper() in ['1', '1.0', 'Y', 'TRUE']
        o_type = str(row.get('OracleType', '')).strip().upper()
        
        table_info[f][c] = {'is_pk': is_pk, 'o_type': o_type}
        if c not in ex_cols:
            col_to_tables[c].add(f)

    # 3. Physical 관계 추출 (인접한 레벨 간의 관계만)
    physical_edges = set()
    
    for from_table in related_tables_set:
        if from_table not in table_info: continue
        
        from_level = table_levels.get(from_table, 0)
        
        for col, info in table_info[from_table].items():
            if col not in col_to_tables: continue
            
            for to_table in col_to_tables[col]:
                if to_table not in related_tables_set: continue
                if from_table == to_table: continue
                
                to_level = table_levels.get(to_table, 0)
                level_diff = abs(from_level - to_level)
                if level_diff > 1: continue
                
                if (from_table, to_table, col) in physical_edges or (to_table, from_table, col) in physical_edges:
                    continue
                
                to_is_pk = table_info[to_table].get(col, {}).get('is_pk', False)
                if info['is_pk'] or to_is_pk:
                    if to_is_pk and not info['is_pk']:
                        physical_edges.add((from_table, to_table, col))
                    elif from_level < to_level:
                        physical_edges.add((from_table, to_table, col))
                    else:
                        physical_edges.add((to_table, from_table, col))

    # 4. Logical 관계 추출 (22번 파일과 동일한 로직)
    logical_edges = set()
    logical_edge_details = {}  # {(from_file, to_file): (from_col, to_col)}
    
    # Level_Relationship_Internal 또는 Level_Relationship 컬럼 확인
    if 'Level_Relationship_Internal' in it_df.columns or 'Level_Relationship' in it_df.columns:
        logical_relationships = _extract_relationships_from_erd_logic(selected_files, related_tables_set, it_df)
        for from_file, from_col, to_file, to_col in logical_relationships:
            if from_file in related_tables_set and to_file in related_tables_set:
                key = (from_file, to_file)
                logical_edges.add(key)
                logical_edge_details[key] = (from_col, to_col)

    # 5. 관계 타입 분류 (Physical만, Logical만, 둘 다)
    edge_types = {}  # {(from_table, to_table): 'physical'|'logical'|'both'}
    
    for from_table, to_table, col in physical_edges:
        key = (from_table, to_table)
        reverse_key = (to_table, from_table)
        
        if key in edge_types or reverse_key in edge_types:
            edge_types[key if key in edge_types else reverse_key] = 'both'
        else:
            edge_types[key] = 'physical'
    
    for from_file, to_file in logical_edges:
        key = (from_file, to_file)
        reverse_key = (to_file, from_file)
        
        if key in edge_types or reverse_key in edge_types:
            edge_types[key if key in edge_types else reverse_key] = 'both'
        else:
            edge_types[key] = 'logical'

    # 6. Graphviz 렌더링
    dot = Digraph(comment='Physical & Logical ERD', encoding='utf-8')
    dot.attr(rankdir='LR', nodesep='0.5', ranksep='1.5', splines='polyline')
    dot.attr('node', fontname='Malgun Gothic', fontsize='10', shape='none')
    dot.attr('edge', fontname='Malgun Gothic', fontsize='8')

    # 7. 노드 생성
    for table_name in sorted(related_tables_set):
        is_anchor = table_name in selected_files
        header_bg = '#FFA500' if is_anchor else '#BBDEFB'
        
        label = f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" PORT="title">'
        label += f'<TR><TD BGCOLOR="{header_bg}"><B>{table_name}</B></TD></TR>'
        
        cols = table_info[table_name]
        
        # Physical과 Logical 관계에 모두 포함된 컬럼 수집
        physical_involved_cols = {c for f, t, c in physical_edges if f == table_name or t == table_name}
        logical_involved_cols = set()
        for from_file, to_file in logical_edges:
            if from_file == table_name or to_file == table_name:
                if (from_file, to_file) in logical_edge_details:
                    from_col, to_col = logical_edge_details[(from_file, to_file)]
                    if from_file == table_name:
                        logical_involved_cols.add(from_col)
                    if to_file == table_name:
                        logical_involved_cols.add(to_col)
        
        involved_cols = physical_involved_cols | logical_involved_cols
        
        for c_name in sorted(cols.keys()):
            info = cols[c_name]
            if info['is_pk'] or c_name in involved_cols or (show_all_columns and is_anchor):
                prefix = "🔑 " if info['is_pk'] else ("🔗 " if c_name in involved_cols else "  ")
                bg = "#E3F2FD" if info['is_pk'] else "#FFFFFF"
                label += f'<TR><TD ALIGN="LEFT" BGCOLOR="{bg}" PORT="{c_name}">{prefix}{c_name}</TD></TR>'
        
        label += '</TABLE>>'
        dot.node(table_name, label)

    # 8. 엣지 추가 (색상 구분)
    for from_table, to_table, col in physical_edges:
        key = (from_table, to_table)
        reverse_key = (to_table, from_table)
        
        edge_type = edge_types.get(key, edge_types.get(reverse_key, 'physical'))
        
        if edge_type == 'physical':
            edge_color = '#0000FF'  # 파란색
            penwidth = '1.5'
        elif edge_type == 'logical':
            edge_color = '#FF0000'  # 빨간색
            penwidth = '1.5'
        else:  # 'both'
            edge_color = '#800080'  # 보라색
            penwidth = '2.0'
        
        dot.edge(f'{from_table}:{col}', f'{to_table}:{col}', 
                 dir='both', arrowhead='none', arrowtail='crow', 
                 color=edge_color, penwidth=penwidth)
    
    # Logical 엣지 추가 (Physical과 중복되지 않는 경우만)
    for from_file, to_file in logical_edges:
        key = (from_file, to_file)
        reverse_key = (to_file, from_file)
        
        # Physical 관계에 이미 포함되어 있는지 확인
        has_physical = any((f == from_file and t == to_file) or (f == to_file and t == from_file) 
                          for f, t, _ in physical_edges)
        
        if not has_physical and key in logical_edge_details:
            # Logical 관계만 있는 경우
            from_col, to_col = logical_edge_details[key]
            dot.edge(f'{from_file}:{from_col}', f'{to_file}:{to_col}',
                     dir='both', arrowhead='none', arrowtail='crow',
                     color='#FF0000', penwidth='1.5')  # 빨간색

    # ERD 생성 정보 수집
    involved_cols_by_table = {}
    for table in related_tables_set:
        physical_cols = {c for f, t, c in physical_edges if f == table or t == table}
        logical_cols = set()
        for from_file, to_file in logical_edges:
            if (from_file == table or to_file == table) and (from_file, to_file) in logical_edge_details:
                from_col, to_col = logical_edge_details[(from_file, to_file)]
                if from_file == table:
                    logical_cols.add(from_col)
                if to_file == table:
                    logical_cols.add(to_col)
        involved_cols_by_table[table] = physical_cols | logical_cols
    
    erd_info = {
        'table_info': table_info,
        'physical_edges': physical_edges,
        'logical_edges': logical_edges,
        'logical_edge_details': logical_edge_details,
        'edge_types': edge_types,
        'related_tables_set': related_tables_set,
        'table_levels': table_levels,
        'involved_cols_by_table': involved_cols_by_table,
        'show_all_columns': show_all_columns,
        'selected_files': selected_files,
        'mode': 'Physical & Logical'
    }
    
    return dot, len(related_tables_set), erd_info

# -------------------------------------------------
# 10. ERD 정보/데이터프레임 생성 함수 (ERD Info DataFrame)
# -------------------------------------------------
def create_erd_info_dataframe(erd_info: dict) -> pd.DataFrame:
    """
    ERD 생성 정보를 컬럼 단위 데이터프레임으로 변환
    """
    rows = []
    
    mode = erd_info.get('mode', 'Unknown')
    table_info = erd_info.get('table_info', {})
    related_tables_set = erd_info.get('related_tables_set', set())
    show_all_columns = erd_info.get('show_all_columns', False)
    selected_files = erd_info.get('selected_files', [])
    involved_cols_by_table = erd_info.get('involved_cols_by_table', {})
    
    if mode == 'Physical':
        fk_candidates = erd_info.get('fk_candidates', [])
        table_levels = erd_info.get('table_levels', {})
        
        # 관계 정보 매핑
        relationships_by_col = defaultdict(list)
        for from_table, to_table, col in fk_candidates:
            relationships_by_col[(from_table, col)].append((to_table, col))
            relationships_by_col[(to_table, col)].append((from_table, col))
        
        # related_tables_set이 set이면 list로 변환
        if isinstance(related_tables_set, set):
            related_tables_list = sorted(list(related_tables_set))
        else:
            related_tables_list = sorted(list(related_tables_set)) if related_tables_set else []
        
        for table_name in related_tables_list:
            if table_name not in table_info:
                continue
            
            cols = table_info[table_name]
            involved_cols = involved_cols_by_table.get(table_name, set())
            is_anchor = table_name in selected_files
            level = table_levels.get(table_name, 0)
            
            # 표시된 컬럼 수집 (ERD에 실제로 표시된 컬럼)
            displayed_cols = set()
            for c_name, info in cols.items():
                is_displayed = info['is_pk'] or c_name in involved_cols or (show_all_columns and is_anchor)
                if is_displayed:
                    displayed_cols.add(c_name)
            
            # 표시된 컬럼에 대해 정보 생성
            for c_name in displayed_cols:
                info = cols[c_name]
                
                # 관계 정보 수집
                related_info = relationships_by_col.get((table_name, c_name), [])
                if related_info:
                    # 관계가 있는 경우: 각 관계마다 행 생성
                    for related_table, related_col in related_info:
                        rows.append({
                            'FileName': table_name,
                            'ColumnName': c_name,
                            'PK': 'Y' if info['is_pk'] else 'N',
                            'FK': 'Y',
                            'Relationship_Type': 'Physical',
                            'Related_Table': related_table,
                            'Related_Column': related_col,
                            'Level': level,
                            'Displayed': 'Y',
                            'Is_Anchor': 'Y' if is_anchor else 'N'
                        })
                else:
                    # 관계가 없는 컬럼도 표시 (ERD에 표시되었으므로)
                    rows.append({
                        'FileName': table_name,
                        'ColumnName': c_name,
                        'PK': 'Y' if info['is_pk'] else 'N',
                        'FK': 'N',
                        'Relationship_Type': 'Physical',
                        'Related_Table': '',
                        'Related_Column': '',
                        'Level': level,
                        'Displayed': 'Y',
                        'Is_Anchor': 'Y' if is_anchor else 'N'
                    })
    
    elif mode == 'Logical':
        relationships_list = erd_info.get('relationships_list', [])
        all_tables = erd_info.get('all_tables', set())
        pk_map = erd_info.get('pk_map', {})
        display_columns = erd_info.get('display_columns', {})
        connected_columns = erd_info.get('connected_columns', {})
        
        # 관계 정보 매핑
        relationships_by_col = defaultdict(list)
        for from_file, from_col, to_file, to_col in relationships_list:
            relationships_by_col[(from_file, from_col)].append((to_file, to_col))
            relationships_by_col[(to_file, to_col)].append((from_file, from_col))
        
        # all_tables가 set이면 list로 변환
        if isinstance(all_tables, set):
            all_tables_list = sorted(list(all_tables))
        else:
            all_tables_list = sorted(list(all_tables)) if all_tables else []
        
        for table_name in all_tables_list:
            is_anchor = table_name in selected_files
            pk_cols = set(pk_map.get(table_name, []))
            displayed_cols = set(display_columns.get(table_name, []))
            connected_cols = connected_columns.get(table_name, set())
            
            for col_name in displayed_cols:
                is_pk = col_name in pk_cols
                is_fk = col_name in connected_cols
                
                # 관계 정보 수집
                related_info = relationships_by_col.get((table_name, col_name), [])
                if related_info:
                    for related_table, related_col in related_info:
                        rows.append({
                            'FileName': table_name,
                            'ColumnName': col_name,
                            'PK': 'Y' if is_pk else 'N',
                            'FK': 'Y' if is_fk else 'N',
                            'Relationship_Type': 'Logical',
                            'Related_Table': related_table,
                            'Related_Column': related_col,
                            'Level': '',
                            'Displayed': 'Y',
                            'Is_Anchor': 'Y' if is_anchor else 'N'
                        })
                else:
                    rows.append({
                        'FileName': table_name,
                        'ColumnName': col_name,
                        'PK': 'Y' if is_pk else 'N',
                        'FK': 'N',
                        'Relationship_Type': 'Logical',
                        'Related_Table': '',
                        'Related_Column': '',
                        'Level': '',
                        'Displayed': 'Y',
                        'Is_Anchor': 'Y' if is_anchor else 'N'
                    })
    
    elif mode == 'Physical & Logical':
        physical_edges = erd_info.get('physical_edges', set())
        logical_edges = erd_info.get('logical_edges', set())
        logical_edge_details = erd_info.get('logical_edge_details', {})
        edge_types = erd_info.get('edge_types', {})
        table_levels = erd_info.get('table_levels', {})
        
        # Physical 관계 매핑
        physical_relationships_by_col = defaultdict(list)
        for from_table, to_table, col in physical_edges:
            physical_relationships_by_col[(from_table, col)].append((to_table, col, 'Physical'))
            physical_relationships_by_col[(to_table, col)].append((from_table, col, 'Physical'))
        
        # Logical 관계 매핑
        logical_relationships_by_col = defaultdict(list)
        for from_file, to_file in logical_edges:
            if (from_file, to_file) in logical_edge_details:
                from_col, to_col = logical_edge_details[(from_file, to_file)]
                logical_relationships_by_col[(from_file, from_col)].append((to_file, to_col, 'Logical'))
                logical_relationships_by_col[(to_file, to_col)].append((from_file, from_col, 'Logical'))
        
        for table_name in related_tables_set:
            if table_name not in table_info:
                continue
            
            cols = table_info[table_name]
            involved_cols = involved_cols_by_table.get(table_name, set())
            is_anchor = table_name in selected_files
            level = table_levels.get(table_name, 0)
            
            for c_name, info in cols.items():
                is_displayed = info['is_pk'] or c_name in involved_cols or (show_all_columns and is_anchor)
                
                # Physical 관계
                physical_related = physical_relationships_by_col.get((table_name, c_name), [])
                # Logical 관계
                logical_related = logical_relationships_by_col.get((table_name, c_name), [])
                
                # 모든 관계를 수집 (테이블-컬럼 조합 기준)
                physical_relations = {(rt, rc) for rt, rc, _ in physical_related}
                logical_relations = {(rt, rc) for rt, rc, _ in logical_related}
                all_relation_pairs = physical_relations | logical_relations
                
                # 각 관계에 대해 행 생성
                if all_relation_pairs:
                    for related_table, related_col in all_relation_pairs:
                        # Physical 관계인지 확인
                        has_physical = (related_table, related_col) in physical_relations
                        # Logical 관계인지 확인
                        has_logical = (related_table, related_col) in logical_relations
                        
                        # 타입 컬럼 설정
                        physical_type = 1 if has_physical else 0
                        logical_type = 1 if has_logical else 0
                        both_type = 1 if (has_physical and has_logical) else 0
                        check = 1 if (has_logical and not has_physical) else 0
                        
                        rows.append({
                            'FileName': table_name,
                            'ColumnName': c_name,
                            'PK': 'Y' if info['is_pk'] else 'N',
                            'FK': 'Y' if (has_physical or has_logical) else 'N',
                            'Physical_Type': physical_type,
                            'Logical_Type': logical_type,
                            'Both_Type': both_type,
                            'Check': check,
                            'Related_Table': related_table,
                            'Related_Column': related_col,
                            'Level': level,
                            'Displayed': 'Y' if is_displayed else 'N',
                            'Is_Anchor': 'Y' if is_anchor else 'N'
                        })
                
                # 관계가 없는 컬럼도 표시
                if not all_relation_pairs:
                    if is_displayed:
                        rows.append({
                            'FileName': table_name,
                            'ColumnName': c_name,
                            'PK': 'Y' if info['is_pk'] else 'N',
                            'FK': 'N',
                            'Physical_Type': 0,
                            'Logical_Type': 0,
                            'Both_Type': 0,
                            'Check': 0,
                            'Related_Table': '',
                            'Related_Column': '',
                            'Level': level,
                            'Displayed': 'Y',
                            'Is_Anchor': 'Y' if is_anchor else 'N'
                        })
                else:
                    if is_displayed:
                        rows.append({
                            'FileName': table_name,
                            'ColumnName': c_name,
                            'PK': 'Y' if info['is_pk'] else 'N',
                            'FK': 'N',
                            'Relationship_Type': 'None',
                            'Related_Table': '',
                            'Related_Column': '',
                            'Level': level,
                            'Displayed': 'Y',
                            'Is_Anchor': 'Y' if is_anchor else 'N'
                        })
    
    if not rows:
        return pd.DataFrame()
    
    df = pd.DataFrame(rows)
    
    # Logical 모드에서 중복 제거
    if mode == 'Logical':
        # 같은 FileName, ColumnName, Related_Table, Related_Column 조합이 중복되면 하나만 남기기
        # 단, Related_Table이 비어있지 않은 경우에만 중복 제거 (관계가 없는 컬럼은 유지)
        df_with_relations = df[df['Related_Table'] != ''].copy()
        df_without_relations = df[df['Related_Table'] == ''].copy()
        
        if not df_with_relations.empty:
            # 중복 제거: FileName, ColumnName, Related_Table, Related_Column 기준
            df_with_relations = df_with_relations.drop_duplicates(
                subset=['FileName', 'ColumnName', 'Related_Table', 'Related_Column'],
                keep='first'
            )
        
        # 다시 합치기
        if not df_without_relations.empty:
            df = pd.concat([df_with_relations, df_without_relations], ignore_index=True)
        else:
            df = df_with_relations
    
    # 정렬: FileName, ColumnName, Related_Table 순서
    df = df.sort_values(['FileName', 'ColumnName', 'Related_Table']).reset_index(drop=True)
    
    return df

# -------------------------------------------------
# 12. ERD 생성 래퍼 함수 (ERD Generation Wrappers)
# -------------------------------------------------
def run_erd_generation_wrapper(df_cm, df_ex, df_cr=None):
    """
    df_cm: CodeMapping.csv (물리적 관계 정보)
    df_ex: ERD_exclusive.csv (제외할 컬럼 정보)
    df_cr: CodeMapping_erd.csv (논리적 관계 정보, optional)
    """

    # 1st 파일 정보 출력 및 파일 선택 
    selected_files = select_files(df_cr, df_cm, df_ex)
    if not selected_files:
        return
    
    st.subheader("연결관계 정보 설정")
    col1, col2, col3     = st.columns([1, 1, 1])

    with col1:
        erd_mode = st.radio("연결관계 모드 선택", ["Physical", "Logical", "Physical & Logical"])

    with col2:
        if erd_mode == "Physical":
            depth = st.slider("탐색 깊이 (Level)", 1, 4, 2, key="depth_slider_physical")
        elif erd_mode == "Physical & Logical":
            depth = st.slider("탐색 깊이 (Level)", 1, 4, 2, key="depth_slider_combined")

    with col3:
        show_all = st.checkbox("전체 컬럼 표시", value=False)


    if st.button(f"🚀 {erd_mode} ERD 생성 및 분석 시작", type="primary"):
        # Cloud 환경에서는 예제 이미지만 표시하고, ERD는 생성하지 않지만 결과는 보여줌
        cloud_mode = is_cloud_env()
        # cloud_mode = True # 테스트용
        if cloud_mode:
            show_example_erd_images()

        with st.spinner("N-Level 관계 탐색 및 레이아웃 계산 중..."):
            if erd_mode == "Physical":
                # Physical 모드: depth를 사용하여 N-Level 탐색
                # 선택된 모든 테이블에 대해 각각 depth 레벨까지 직접 연결된 테이블만 찾기
                all_related_tables = set(selected_files)  # 선택된 테이블 포함
                all_table_levels = {}  # 모든 테이블의 레벨 정보 통합
                
                # 선택된 테이블은 모두 레벨 0
                for table in selected_files:
                    table_str = str(table) if isinstance(table, str) else str(table)
                    all_table_levels[table_str] = 0
                
                for anchor_table in selected_files:
                    anchor_table_str = str(anchor_table) if isinstance(anchor_table, str) else str(anchor_table)
                    # 각 선택된 테이블에 대해 depth 레벨까지 직접 연결된 테이블만 찾기
                    related_for_this, levels_for_this = get_physical_n_level_tables(df_cm, anchor_table_str, depth, df_ex)
                    all_related_tables.update(related_for_this)
                    # 레벨 정보 병합 (이미 있는 경우 더 낮은 레벨 유지)
                    for table, level in levels_for_this.items():
                        if table not in all_table_levels or all_table_levels[table] > level:
                            all_table_levels[table] = level
                
                related_list = list(all_related_tables)
                
                if not related_list or len(related_list) == 0:
                    st.warning(f"⚠️ 선택된 테이블과 연결된 테이블을 찾을 수 없습니다.")
                else:
                    # ERD 생성 (depth 제한된 테이블 목록과 레벨 정보 전달)
                    dot, count, erd_info = generate_physical_erd_image(df_cm, df_ex, selected_files, related_list, show_all, all_table_levels)
                    
                    if dot and not cloud_mode:
                        suffix = f"L{depth}_{len(selected_files)}tables"
                        display_erd_with_download(dot, suffix, count)
                        st.success(f"✅ 분석 완료: 선택된 {len(selected_files)}개 테이블 기준 {depth}레벨까지 직접 연결된 총 {len(related_list)}개 테이블 표시")

                    # ERD 정보 데이터프레임 표시
                    st.subheader("📊 ERD 생성 정보 (컬럼 단위)")
                    erd_df = create_erd_info_dataframe(erd_info)
                    st.dataframe(erd_df, width='stretch', hide_index=True)

            elif erd_mode == "Logical":
                # PK 맵과 it_df 생성
                pk_map, fk_map, it_df = _extract_and_load_erd_data_impl(df_cr)
                
                related_tables = get_related_tables(selected_files, it_df)
                related_table_count = len(related_tables)
                
                if related_table_count > MAX_RELATED_TABLE_COUNT:
                    st.error(f"연결된 테이블 수가 {MAX_RELATED_TABLE_COUNT}개를 초과했습니다.")
                elif not related_tables or len(related_tables) == 0:
                    st.warning(f"⚠️ 선택된 테이블과 연결된 테이블을 찾을 수 없습니다.")
                else:
                    dot, edge_count, erd_info = generate_logical_erd_image(
                        selected_files, 
                        set(related_tables), 
                        pk_map, 
                        it_df, 
                        show_all
                    )
                    
                    if dot and not cloud_mode:
                        suffix = f"{erd_mode}_{selected_files[0]}"
                        display_erd_with_download(dot, suffix, edge_count)
                        st.success(f"✅ 분석 완료: 총 {len(related_tables)}개 테이블 연결됨")

                    # ERD 정보 데이터프레임 표시
                    st.subheader("📊 ERD 생성 정보 (컬럼 단위)")
                    erd_df = create_erd_info_dataframe(erd_info)
                    st.dataframe(erd_df, width='stretch', hide_index=True)

            elif erd_mode == "Physical & Logical":
                # Physical & Logical 통합 모드
                # PK 맵과 it_df 생성
                pk_map, fk_map, it_df = _extract_and_load_erd_data_impl(df_cr)
                
                # Physical 관계 탐색
                all_related_tables = set(selected_files)
                all_table_levels = {}
                
                for table in selected_files:
                    table_str = str(table) if isinstance(table, str) else str(table)
                    all_table_levels[table_str] = 0
                
                for anchor_table in selected_files:
                    anchor_table_str = str(anchor_table) if isinstance(anchor_table, str) else str(anchor_table)
                    related_for_this, levels_for_this = get_physical_n_level_tables(df_cm, anchor_table_str, depth, df_ex)
                    all_related_tables.update(related_for_this)
                    for table, level in levels_for_this.items():
                        if table not in all_table_levels or all_table_levels[table] > level:
                            all_table_levels[table] = level
                
                # Logical 관계 탐색 (22번 파일과 동일한 로직)
                logical_related_tables = get_related_tables(selected_files, it_df)
                logical_related_table_count = len(logical_related_tables)
                
                # Physical과 Logical 관계를 통합
                all_related_tables.update(logical_related_tables)
                related_list = list(all_related_tables)
                
                if not related_list or len(related_list) == 0:
                    st.warning(f"⚠️ 선택된 테이블과 연결된 테이블을 찾을 수 없습니다.")
                else:
                    # 통합 ERD 생성
                    dot, count, erd_info = generate_combined_erd_image(
                        df_cm, df_ex, df_cr, selected_files, related_list, 
                        all_table_levels, pk_map, it_df, show_all
                    )
                    
                    if dot and not cloud_mode:
                        suffix = f"Combined_L{depth}_{len(selected_files)}tables"
                        display_erd_with_download(dot, suffix, count)
                        st.success(f"✅ 통합 분석 완료: Physical & Logical 관계를 색상으로 구분하여 표시 (총 {count}개 테이블)")
                        st.info("🔵 파란색: Physical 연결만 | 🔴 빨간색: Logical 연결만 | 🟣 보라색: 두 연결 모두")

                    # ERD 정보 데이터프레임 표시 (Cloud 환경에서도 표시)
                    st.subheader("📊 ERD 생성 정보 (컬럼 단위)")
                    erd_df = create_erd_info_dataframe(erd_info)
                    st.dataframe(erd_df, width='stretch', hide_index=True)

# -------------------------------------------------
# 13. 메인 함수 (Main)
# -------------------------------------------------
def main():
    st.title(APP_TITLE)
    st.caption(APP_DESCRIPTION)

    try:
        # 1. 데이터 로드
        path = OUTPUT_DIR
        files_to_load = {   # load 할 파일 목록
            'codemapping_erd': path / "CodeMapping_erd.csv", 
            'codemapping': path / "CodeMapping.csv",
            'filestats': path / "FileStats.csv", 
            'exclusive': path / "ERD_exclusive.csv"
        }

        loaded_data = load_data_all(files_to_load)

        if loaded_data is None:
            st.error("데이터 로드 중 오류가 발생했습니다.")
            return
        else:
            df_cr = loaded_data['codemapping_erd']
            df_cm = loaded_data['codemapping']
            df_fs = loaded_data['filestats']
            df_ex = loaded_data['exclusive']

        run_erd_generation_wrapper(df_cm, df_ex, df_cr)
        
    except Exception as e:
        st.error(f"Data Relationship Diagram 생성 중 치명적인 오류가 발생했습니다: {e}")
        return

if __name__ == '__main__':
    main()



