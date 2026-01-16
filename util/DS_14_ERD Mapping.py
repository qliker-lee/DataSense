# -*- coding: utf-8 -*-
"""
DS_14_Code Recursive Mapping 
2025.11.16 Qliker
- 코드 매핑 결과를 재귀적으로 분석하여 2nd Mapping 을 자동 생성한다.
- YAML 파일 없이 상수로 처리
"""

from __future__ import annotations
import pandas as pd
import os
import sys
import time
import logging

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
# -------------------------------------------------------------------
# 기본 경로
# -------------------------------------------------------------------

if getattr(sys, 'frozen', False):  # A. 실행파일(.exe) 상태일 때: .exe 파일이 있는 위치가 루트입니다.
    ROOT_PATH = Path(sys.executable).parent
else:  # B. 소스코드(.py) 상태일 때: 현재 파일(util/..)의 상위 폴더가 루트입니다.   
    ROOT_PATH = Path(__file__).resolve().parents[1]

if str(ROOT_PATH) not in sys.path: # # 시스템 경로에 루트 추가 (어디서 실행해도 모듈을 찾을 수 있게 함)
    sys.path.insert(0, str(ROOT_PATH))

# -------------------------------------------------------------------
# 상수 정의 (YAML 파일 대신 사용)
# -------------------------------------------------------------------
OUTPUT_DIR = ROOT_PATH / 'DS_Output'
CODEMAPPING_FILE = OUTPUT_DIR / 'CodeMapping.csv'
OUTPUT_FILE = OUTPUT_DIR / 'CodeMapping_relationship_2.csv'
CODEMAPPING_ERD_FILE = OUTPUT_DIR / 'CodeMapping_erd.csv'  # 통합에서 사용할 예정 
# ================================================================
# 도우미 함수 (DataSense.util.io 에서 가져옴)
# ================================================================
def normalize_str(s: str) -> str:
    """일반적인 문자열 정규화"""
    import unicodedata  # 한글 자모 결합 정규화를 위해 임포트
    s = unicodedata.normalize("NFC", str(s))
    s = s.replace("\u3000", " ")
    return " ".join(s.split())

def clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    """CSV 또는 XLSX 파일의 컬럼 헤더 정리"""
    new = df.copy()
    new.columns = [str(c).replace("\ufeff", "").strip() for c in new.columns]
    return new

# ================================================================
# 초기화 클래스
# ================================================================
class Initializing_Main_Class:
    def __init__(self):
        self.logger = None
        self.loaded_data: Dict[str, pd.DataFrame] = {}

        self._setup_logger()
        self.loaded_data = self._load_files()

    # -----------------------------------------------------------
    def _setup_logger(self):
        log_dir = ROOT_PATH / "logs"
        log_dir.mkdir(exist_ok=True)

        logfile = log_dir / f"ERD_Mapping_{datetime.now():%Y%m%d_%H%M%S}.log"

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(logfile, encoding="utf-8"),
                logging.StreamHandler()
            ]
        )

        self.logger = logging.getLogger("ERD_Mapping")

    # -----------------------------------------------------------
    def _resolve_read(self, filepath: Path) -> pd.DataFrame:
        filepath = Path(filepath).with_suffix(".csv")
        if not filepath.exists():
            raise FileNotFoundError(f"CodeMapping 파일 없음: {filepath}")

        if filepath.suffix.lower() == ".csv":
            df = pd.read_csv(filepath, dtype=str, low_memory=False)
        elif filepath.suffix.lower() == ".xlsx":
            df = pd.read_excel(filepath, dtype=str)
        else:
            raise ValueError(f"지원하지 않는 형식: {filepath}")

        df = clean_headers(df)
        df = df.fillna("")
        return df

    # -----------------------------------------------------------
    def _load_files(self) -> Dict[str, pd.DataFrame]:
        codemapping_df = self._resolve_read(CODEMAPPING_FILE)
        self.logger.info(f"CodeMapping 로딩: {CODEMAPPING_FILE}")
        return {"codemapping": codemapping_df}

    # ===============================================================
    # 재귀 매핑 함수 (DFS 기반)
    # ===============================================================
    def build_recursive_mapping_full(self, codemapping_df, max_depth=10):
        """
        codemapping_df 전체 행에 대해 재귀 매핑 수행 (미매핑 포함)
        Level 구조 자동 확장
        Matched(%)_n 정보 포함
        """

        # ----------------------------------------
        # 1. MasterType이 제외 대상인 경우 제외
        # ----------------------------------------
        EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
        codemapping_df = codemapping_df[~codemapping_df["MasterType"].isin(EXCLUDED_MASTER_TYPES)].copy()

        # CodeFile_1의 CodeType_1이 제외 대상인 경우도 빈 문자열로 처리
        for excluded_type in EXCLUDED_MASTER_TYPES:
            mask = codemapping_df["CodeType_1"] == excluded_type
            codemapping_df.loc[mask, "CodeFile_1"] = ""

        # ----------------------------------------
        # 2. 그래프 구성 및 Matched(%) 정보 저장
        # ----------------------------------------
        graph = {}       # (file, col, master) → list of children
        nodes_info = {}  # node → {file, column, master}
        edge_matched = {}  # (parent, child) → Matched(%)_1 값

        for _, r in codemapping_df.iterrows():
            parent = (str(r["FileName"]), str(r["ColumnName"]), str(r["MasterType"]))
            child = None

            # child 존재 여부 및 CodeType_1이 제외 대상이 아닌 경우만 포함
            EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
            if pd.notna(r.get("CodeFile_1", "")) and str(r["CodeFile_1"]).strip() != "":
                code_type_1 = str(r.get("CodeType_1", "")).strip()
                # CodeType_1이 제외 대상이 아닌 경우만 child로 등록
                if code_type_1 not in EXCLUDED_MASTER_TYPES:
                    child = (str(r["CodeFile_1"]), str(r["CodeColumn_1"]), code_type_1)

            # parent 등록
            nodes_info[parent] = {
                "file": parent[0],
                "column": parent[1],
                "master": parent[2],
            }
            graph.setdefault(parent, [])

            # child 등록 및 Matched(%) 정보 저장 (제외 대상이 아닌 경우만)
            if child:
                nodes_info[child] = {
                    "file": child[0],
                    "column": child[1],
                    "master": child[2],
                }
                graph[parent].append(child)
                
                # Matched(%)_1 정보 저장 (있으면 사용, 없으면 빈 문자열)
                matched_val = str(r.get("Matched(%)_1", "")).strip() if pd.notna(r.get("Matched(%)_1", "")) else ""
                edge_matched[(parent, child)] = matched_val

        # ----------------------------------------
        # 2. DFS - leaf 만 결과로 저장
        # ----------------------------------------
        results = []

        def dfs(path, depth):
            if depth > max_depth:
                return

            last = path[-1]
            children = graph.get(last, [])

            # Matched(%) 50 초과이고 MasterType이 제외 대상이 아닌 child만 필터링
            EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
            valid_children = []
            for child in children:
                if child not in path:  # cycle 방지
                    # child의 MasterType이 제외 대상인 경우 skip
                    child_master_type = child[2] if len(child) > 2 else ""
                    if child_master_type in EXCLUDED_MASTER_TYPES:
                        continue  # 제외 대상 MasterType은 skip
                    
                    # Matched(%) 값이 50 이하인 경우 skip
                    matched_key = (last, child)
                    matched_val_str = edge_matched.get(matched_key, "")
                    should_skip = False
                    if matched_val_str:
                        try:
                            matched_val = float(matched_val_str)
                            if matched_val <= 50:
                                should_skip = True  # 50 이하인 경우 skip
                        except (ValueError, TypeError):
                            # 숫자로 변환할 수 없는 경우는 통과
                            pass
                    if not should_skip:
                        valid_children.append(child)

            # 실제 탐색 가능한 하위 노드가 없음 → leaf
            if not valid_children:
                record = {}

                for i, node in enumerate(path, start=0):
                    f, c, m = node
                    record[f"Level{i}_File"] = f
                    record[f"Level{i}_Column"] = c
                    record[f"Level{i}_MasterType"] = m
                    
                    # Matched(%)_n 정보 추가
                    # Level0은 원본이므로 Matched(%) 정보 없음 (또는 빈 값)
                    if i == 0:
                        record[f"Level{i}_Matched(%)"] = ""
                    else:
                        # i-1에서 i로 가는 엣지의 Matched(%) 정보
                        parent_node = path[i - 1]
                        child_node = node
                        matched_key = (parent_node, child_node)
                        record[f"Level{i}_Matched(%)"] = edge_matched.get(matched_key, "")

                results.append(record)
                return

            # 하위 노드 존재 → 계속 DFS
            for child in valid_children:
                dfs(path + [child], depth + 1)

        # ----------------------------------------
        # 3. 모든 시작 노드에 대해 DFS 수행
        # ----------------------------------------
        all_roots = list(nodes_info.keys())

        for root in all_roots:
            dfs([root], 1)

        # ----------------------------------------
        # 4. 결과 DataFrame 생성
        # ----------------------------------------
        df = pd.DataFrame(results)

        # 없는 Level 컬럼 자동 생성 (정렬 보장)
        max_level = 0
        for col in df.columns:
            if "Level" in col:
                n = int(col.split("_")[0].replace("Level", ""))
                max_level = max(max_level, n)

        # 누락된 칼럼 빈 값으로 보정
        for i in range(0, max_level + 1):
            for suffix in ["File", "Column", "MasterType", "Matched(%)"]:
                key = f"Level{i}_{suffix}"
                if key not in df.columns:
                    df[key] = ""

        # 칼럼 정렬
        ordered_cols = []
        for i in range(0, max_level + 1):
            ordered_cols += [
                f"Level{i}_File",
                f"Level{i}_Column",
                f"Level{i}_MasterType",
                f"Level{i}_Matched(%)",
            ]

        df = df[ordered_cols]
        
        # ----------------------------------------
        # 5. Level 관계를 전체 합친 컬럼 생성
        # ----------------------------------------
        def build_relationship_path(row):
            """Level 관계를 문자열로 합치기: Level1_File.Level1_Column -> Level2_File.Level2_Column -> ..."""
            path_parts = []
            # Level1부터 최대 Level까지 확인 (Level0은 제외)
            for i in range(1, max_level + 1):
                file_col = f"Level{i}_File"
                col_col = f"Level{i}_Column"
                
                if file_col in row and col_col in row:
                    # 값 가져오기
                    file_val_raw = row[file_col]
                    col_val_raw = row[col_col]
                    
                    # NaN 체크 및 문자열 변환
                    if pd.notna(file_val_raw) and pd.notna(col_val_raw):
                        file_val = str(file_val_raw).strip()
                        col_val = str(col_val_raw).strip()
                        
                        # 빈 값, NaN, nan 문자열 제거
                        if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                            col_val and col_val.lower() not in ['nan', 'none', '']):
                            # nan.nan 형식 제거
                            if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                path_parts.append(f"{file_val}.{col_val}")
            
            # 화살표로 연결
            if path_parts:
                return " -> ".join(path_parts)
            else:
                return ""
        
        def build_relationship_path_internal(row):
            """Level 관계를 문자열로 합치기 (제외 대상 MasterType 제외): Level1_File.Level1_Column -> Level2_File.Level2_Column -> ..."""
            EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
            path_parts = []
            # Level1부터 최대 Level까지 확인 (Level0은 제외)
            for i in range(1, max_level + 1):
                file_col = f"Level{i}_File"
                col_col = f"Level{i}_Column"
                master_type_col = f"Level{i}_MasterType"
                
                if file_col in row and col_col in row:
                    # MasterType이 제외 대상인 경우 skip
                    master_type = str(row.get(master_type_col, "")).strip() if pd.notna(row.get(master_type_col, "")) else ""
                    if master_type in EXCLUDED_MASTER_TYPES:
                        continue
                    
                    # 값 가져오기
                    file_val_raw = row[file_col]
                    col_val_raw = row[col_col]
                    
                    # NaN 체크 및 문자열 변환
                    if pd.notna(file_val_raw) and pd.notna(col_val_raw):
                        file_val = str(file_val_raw).strip()
                        col_val = str(col_val_raw).strip()
                        
                        # 빈 값, NaN, nan 문자열 제거
                        if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                            col_val and col_val.lower() not in ['nan', 'none', '']):
                            # nan.nan 형식 제거
                            if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                path_parts.append(f"{file_val}.{col_val}")
            
            # 화살표로 연결
            if path_parts:
                return " -> ".join(path_parts)
            else:
                return ""
        
        # Level 관계 경로 컬럼 생성
        df["Level_Relationship"] = df.apply(build_relationship_path, axis=1)
        df["Level_Relationship_Internal"] = df.apply(build_relationship_path_internal, axis=1)
        df["Level_Relationship_Internal"] = df.apply(build_relationship_path_internal, axis=1)
        
        # Level_Depth 컬럼 생성 (실제로 값이 있는 Level의 최대 깊이)
        def calculate_level_depth(row):
            """Level 관계의 깊이 계산 (Level0부터 시작하여 실제 값이 있는 최대 Level 인덱스)"""
            max_depth = -1  # Level0부터 시작하므로 -1로 초기화
            for i in range(0, max_level + 1): # 2026. 01. 09 추가: Level3 까지 계산하도록 수정
                file_col = f"Level{i}_File"
                col_col = f"Level{i}_Column"
                
                if file_col in row and col_col in row:
                    file_val = str(row[file_col]).strip()
                    col_val = str(row[col_col]).strip()
                    
                    # 빈 값, NaN, nan 문자열이 아니면 depth 업데이트
                    if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                        col_val and col_val.lower() not in ['nan', 'none', '']):
                        if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                            max_depth = i
            
            return max_depth if max_depth >= 0 else 0
        
        df["Level_Depth"] = df.apply(calculate_level_depth, axis=1)
        
        # Level_Relationship, Level_Relationship_Internal, Level_Depth 컬럼을 Level 컬럼들 다음에 추가
        ordered_cols.append("Level_Relationship")
        ordered_cols.append("Level_Relationship_Internal")
        ordered_cols.append("Level_Depth")
        df = df[ordered_cols]

        return df

    #---------------------------------------------------------------------------------
    # 재귀 매핑 함수 (DFS 기반)
    #---------------------------------------------------------------------------------
    def recursive_mapping(self, df: pd.DataFrame, max_depth: int = 3) -> pd.DataFrame:
        """
        DFS 기반 재귀 매핑
        - LevelN_MasterType  = 해당 노드 MasterType
        - LevelN_CodeType    = Level(N-1)_MasterType (부모의 MasterType)
        """

        # ================================
        # 1) 노드별 MasterType / CodeType 정보 사전화
        # ================================
        nodes_info = {}

        df = df[df["MasterType"] != "Rule"].copy()
        
        for _, row in df.iterrows():
            src = (row["FileName"], row["ColumnName"])
            dst = (row["CodeFile_1"], row["CodeColumn_1"])

            # 원본 노드 정보
            nodes_info[src] = {
                "MasterType": row["MasterType"]
            }

            # 대상 노드 정보 (MasterType = CodeType_1)
            if dst not in nodes_info:
                nodes_info[dst] = {
                    "MasterType": row["CodeType_1"]
                }

        # ================================
        # 2) 그래프 구성
        # ================================
        graph = {}
        for _, row in df[df["FK"] == "FK"].iterrows():
            src = (row["FileName"], row["ColumnName"])
            dst = (row["CodeFile_1"], row["CodeColumn_1"])
            graph.setdefault(src, []).append(dst)

        # ================================
        # 3) DFS 실행
        # ================================
        results = []

        def dfs(path, depth):
            if depth > max_depth:
                return

            last = path[-1]

            # 자식이 있는가?
            has_child = last in graph and len(graph[last]) > 0

            if has_child:
                # 자식이 있으면 DFS 계속 진행하고 현재 레코드는 저장하지 않는다
                EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
                for nxt in graph[last]:
                    if nxt not in path:  # cycle 방지
                        # nxt의 MasterType이 제외 대상인 경우 skip
                        nxt_master_type = nodes_info.get(nxt, {}).get("MasterType", "")
                        if nxt_master_type not in EXCLUDED_MASTER_TYPES:
                            dfs(path + [nxt], depth + 1)
            else:
                # leaf 노드 → 최종 레코드만 저장
                record = {}
                for level, node in enumerate(path, start=1):
                    file, col = node
                    master_type = nodes_info[node]["MasterType"]

                    record[f"Level{level}_File"] = file
                    record[f"Level{level}_Column"] = col
                    record[f"Level{level}_MasterType"] = master_type
                results.append(record)
            # 다음 단계 DFS
            if last in graph:
                EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
                for nxt in graph[last]:
                    if nxt not in path:  # cycle 방지
                        # nxt의 MasterType이 제외 대상인 경우 skip
                        nxt_master_type = nodes_info.get(nxt, {}).get("MasterType", "")
                        if nxt_master_type not in EXCLUDED_MASTER_TYPES:
                            dfs(path + [nxt], depth + 1)

        # ================================
        # 4) DFS 시작
        # ================================
        for src in graph:
            dfs([src], 1)

        # ================================
        # 5) 결과 DF 생성
        # ================================
        out = pd.DataFrame(results).fillna("")
        self.logger.info(f"Recursive Mapping 생성 완료 rows={len(out)}")

        return out

    # ===============================================================
    # 파이프라인 실행
    # ===============================================================
    def run_pipeline(self):
        df = self.loaded_data["codemapping"]
        df = df[(df["MasterType"] != "Rule") & ((df["MasterType"] != "Reference") & (df["MasterType"] != "Validation"))].copy()

        # result = self.recursive_mapping(df)
        result = self.build_recursive_mapping_full(df)

        base_cols = ["FilePath", "FileName", "ColumnName", "MasterType", "PK", "FK", "Attribute"]
        # FilePath가 없으면 빈 문자열로 추가
        if "FilePath" not in df.columns:
            df["FilePath"] = ""
        final_df = df[base_cols].copy()

        result_2nd = result.rename(columns={
            "Level0_File":"FileName",
            "Level0_Column":"ColumnName",
            "Level0_MasterType":"MasterType",
        })

        final_df = pd.merge(final_df, result_2nd, on=["FileName", "ColumnName", "MasterType"], how="left")
        
        # Level_Depth, Level_Relationship, Level_Relationship_Internal 컬럼을 PK, FK 컬럼 다음에 위치시키기
        level_depth_col = ["Level_Depth"] if "Level_Depth" in final_df.columns else []
        level_relationship_col = ["Level_Relationship"] if "Level_Relationship" in final_df.columns else []
        level_relationship_internal_col = ["Level_Relationship_Internal"] if "Level_Relationship_Internal" in final_df.columns else []
        
        # Level 컬럼들 추출 (Level_Depth, Level_Relationship, Level_Relationship_Internal 제외)
        level_cols = [col for col in final_df.columns 
                     if col.startswith("Level") and col not in ["Level_Depth", "Level_Relationship", "Level_Relationship_Internal"]]
        level_cols = sorted(level_cols, key=lambda x: (
            int(x.split("_")[0].replace("Level", "")) if x.split("_")[0].replace("Level", "").isdigit() else 999,
            x
        ))
        
        # 최종 컬럼 순서: 기본 컬럼 + Level_Depth + Level_Relationship + Level_Relationship_Internal + Level 컬럼들
        final_cols = base_cols + level_depth_col + level_relationship_col + level_relationship_internal_col + level_cols
        
        # 존재하는 컬럼만 선택
        final_cols = [col for col in final_cols if col in final_df.columns]
        final_df = final_df[final_cols]
        
        #---------------------------------------------------------
        #  CodeColumn_n 순차 처리 및 Left-Compact 로직
        #---------------------------------------------------------
        # 원본 codemapping에서 CodeColumn_n 컬럼들을 가져와서 처리
        code_cols_to_merge = []
        for n in [1, 2, 3, 4]:
            for col_suffix in ['CodeColumn', 'CodeFile', 'CodeFilePath', 'CodeType', 'Matched', 'Matched(%)']:
                col_name = f'{col_suffix}_{n}'
                if col_name in df.columns:
                    code_cols_to_merge.append(col_name)
        
        if code_cols_to_merge:
            # 원본 df에서 CodeColumn_n 관련 컬럼들 추출 (FilePath 포함)
            merge_cols = ['FileName', 'ColumnName', 'MasterType']
            if 'FilePath' in df.columns:
                merge_cols = ['FilePath'] + merge_cols
            code_df = df[merge_cols + code_cols_to_merge].copy()
            
            # final_df와 병합 (FilePath가 있으면 포함)
            merge_on = ['FileName', 'ColumnName', 'MasterType']
            if 'FilePath' in final_df.columns and 'FilePath' in code_df.columns:
                merge_on = ['FilePath'] + merge_on
            final_df = pd.merge(final_df, code_df, on=merge_on, how='left', suffixes=('', '_code'))
            
            # CodeColumn_n 컬럼들이 중복되어 있을 수 있으므로 정리
            for col in code_cols_to_merge:
                if f'{col}_code' in final_df.columns:
                    # _code 접미사가 있는 컬럼이 있으면 원본 컬럼을 업데이트
                    mask = final_df[col].isna() | (final_df[col].astype(str).str.strip() == "")
                    final_df.loc[mask, col] = final_df.loc[mask, f'{col}_code']
                    final_df = final_df.drop(columns=[f'{col}_code'])
                elif col not in final_df.columns:
                    # 컬럼이 없으면 추가
                    final_df[col] = ""
            
            # CodeColumn_1, CodeColumn_2, CodeColumn_3을 순차적으로 처리하고, CodeColumn_4가 있으면 마지막에 추가
            def left_compact_code_columns(row):
                """CodeColumn_1, CodeColumn_2, CodeColumn_3을 왼쪽으로 compact하고, CodeColumn_4가 있으면 마지막에 추가"""
                # 각 n에 대한 컬럼 그룹 수집
                code_groups = []
                for n in [1, 2, 3]:
                    code_col = f'CodeColumn_{n}'
                    if code_col in row and pd.notna(row[code_col]) and str(row[code_col]).strip() != "":
                        code_groups.append({
                            'n': n,
                            'CodeColumn': str(row[code_col]).strip(),
                            'CodeFile': str(row.get(f'CodeFile_{n}', '')).strip() if pd.notna(row.get(f'CodeFile_{n}', '')) else '',
                            'CodeFilePath': str(row.get(f'CodeFilePath_{n}', '')).strip() if pd.notna(row.get(f'CodeFilePath_{n}', '')) else '',
                            'CodeType': str(row.get(f'CodeType_{n}', '')).strip() if pd.notna(row.get(f'CodeType_{n}', '')) else '',
                            'Matched': row.get(f'Matched_{n}', '') if pd.notna(row.get(f'Matched_{n}', '')) else '',
                            'Matched(%)': row.get(f'Matched(%)_{n}', '') if pd.notna(row.get(f'Matched(%)_{n}', '')) else '',
                        })
                
                # CodeColumn_4가 있으면 마지막에 추가
                if 'CodeColumn_4' in row and pd.notna(row['CodeColumn_4']) and str(row['CodeColumn_4']).strip() != "":
                    code_groups.append({
                        'n': 4,
                        'CodeColumn': str(row['CodeColumn_4']).strip(),
                        'CodeFile': str(row.get('CodeFile_4', '')).strip() if pd.notna(row.get('CodeFile_4', '')) else '',
                        'CodeFilePath': str(row.get('CodeFilePath_4', '')).strip() if pd.notna(row.get('CodeFilePath_4', '')) else '',
                        'CodeType': str(row.get('CodeType_4', '')).strip() if pd.notna(row.get('CodeType_4', '')) else '',
                        'Matched': row.get('Matched_4', '') if pd.notna(row.get('Matched_4', '')) else '',
                        'Matched(%)': row.get('Matched(%)_4', '') if pd.notna(row.get('Matched(%)_4', '')) else '',
                    })
                
                # 결과 딕셔너리 생성 (최대 4개까지)
                result = {}
                for i, group in enumerate(code_groups[:4], start=1):
                    result[f'CodeColumn_{i}'] = group['CodeColumn']
                    result[f'CodeFile_{i}'] = group['CodeFile']
                    result[f'CodeFilePath_{i}'] = group['CodeFilePath']
                    result[f'CodeType_{i}'] = group['CodeType']
                    result[f'Matched_{i}'] = group['Matched']
                    result[f'Matched(%)_{i}'] = group['Matched(%)']
                
                # 나머지 위치는 빈 값으로 채움
                for i in range(len(code_groups) + 1, 5):
                    result[f'CodeColumn_{i}'] = ""
                    result[f'CodeFile_{i}'] = ""
                    result[f'CodeFilePath_{i}'] = ""
                    result[f'CodeType_{i}'] = ""
                    result[f'Matched_{i}'] = ""
                    result[f'Matched(%)_{i}'] = ""
                
                return pd.Series(result)
            
            # 각 행에 대해 left-compact 적용
            compacted_df = final_df.apply(left_compact_code_columns, axis=1)
            
            # 원본 DataFrame의 CodeColumn_n 관련 컬럼들을 compacted 결과로 교체
            for n in [1, 2, 3, 4]:
                for col_suffix in ['CodeColumn', 'CodeFile', 'CodeFilePath', 'CodeType', 'Matched', 'Matched(%)']:
                    col_name = f'{col_suffix}_{n}'
                    if col_name in compacted_df.columns:
                        final_df[col_name] = compacted_df[col_name]
            
            # CodeColumn_n을 Level_n으로 변환 (n=1,2,3,4)
            # 각 Level 컬럼이 없으면 생성
            for level_num in [1, 2, 3, 4]:
                level_file_col = f'Level{level_num}_File'
                level_col_col = f'Level{level_num}_Column'
                level_type_col = f'Level{level_num}_MasterType'
                level_matched_col = f'Level{level_num}_Matched(%)'
                
                if level_file_col not in final_df.columns:
                    final_df[level_file_col] = ""
                    final_df[level_col_col] = ""
                    final_df[level_type_col] = ""
                    final_df[level_matched_col] = ""
            
            # CodeColumn_1부터 CodeColumn_4까지 순차적으로 Level 구조에 반영
            for level_num in [1, 2, 3, 4]:
                code_file_col = f'CodeFile_{level_num}'
                code_col_col = f'CodeColumn_{level_num}'
                code_type_col = f'CodeType_{level_num}'
                code_matched_col = f'Matched(%)_{level_num}'
                
                level_file_col = f'Level{level_num}_File'
                level_col_col = f'Level{level_num}_Column'
                level_type_col = f'Level{level_num}_MasterType'
                level_matched_col = f'Level{level_num}_Matched(%)'
                
                # CodeFile_n과 CodeColumn_n이 유효한 값인지 확인
                code_file_valid = (
                    final_df[code_file_col].notna() & 
                    (final_df[code_file_col].astype(str).str.strip() != '') &
                    (final_df[code_file_col].astype(str).str.lower() != 'nan')
                )
                code_column_valid = (
                    final_df[code_col_col].notna() & 
                    (final_df[code_col_col].astype(str).str.strip() != '') &
                    (final_df[code_col_col].astype(str).str.lower() != 'nan')
                )
                level_empty = (
                    final_df[level_file_col].isna() | 
                    (final_df[level_file_col].astype(str).str.strip() == '') |
                    (final_df[level_file_col].astype(str).str.lower() == 'nan')
                )
                
                mask = code_file_valid & code_column_valid & level_empty
                
                if mask.any():
                    final_df.loc[mask, level_file_col] = final_df.loc[mask, code_file_col].astype(str).str.strip()
                    final_df.loc[mask, level_col_col] = final_df.loc[mask, code_col_col].astype(str).str.strip()
                    final_df.loc[mask, level_type_col] = final_df.loc[mask, code_type_col].fillna('').astype(str).str.strip()
                    final_df.loc[mask, level_matched_col] = final_df.loc[mask, code_matched_col].fillna('').astype(str).str.strip()
            
            # CodeColumn_1부터 체크하여 값이 없으면 CodeFile_4를 Level 구조에 반영
            # CodeColumn_1, CodeColumn_2, CodeColumn_3이 모두 비어있는지 확인
            def check_code_columns_empty(row):
                """CodeColumn_1, CodeColumn_2, CodeColumn_3이 모두 비어있는지 확인"""
                for n in [1, 2, 3]:
                    code_col = f'CodeColumn_{n}'
                    if code_col in row:
                        code_val = str(row.get(code_col, '')).strip() if pd.notna(row.get(code_col, '')) else ''
                        if code_val and code_val.lower() not in ['nan', 'none', '']:
                            return False  # 하나라도 값이 있으면 False
                return True  # 모두 비어있으면 True
            
            # CodeFile_4와 CodeColumn_4가 유효한 값인지 확인
            code_file_4_valid = (
                final_df['CodeFile_4'].notna() & 
                (final_df['CodeFile_4'].astype(str).str.strip() != '') &
                (final_df['CodeFile_4'].astype(str).str.lower() != 'nan')
            )
            code_column_4_valid = (
                final_df['CodeColumn_4'].notna() & 
                (final_df['CodeColumn_4'].astype(str).str.strip() != '') &
                (final_df['CodeColumn_4'].astype(str).str.lower() != 'nan')
            )
            
            # CodeColumn_1, CodeColumn_2, CodeColumn_3이 모두 비어있고 CodeFile_4에 값이 있는 경우
            code_columns_empty_mask = final_df.apply(check_code_columns_empty, axis=1)
            mask_code4_fallback = code_columns_empty_mask & code_file_4_valid & code_column_4_valid
            
            # Level1이 비어있으면 CodeFile_4를 Level1로 사용
            if mask_code4_fallback.any():
                level1_empty = (
                    final_df['Level1_File'].isna() | 
                    (final_df['Level1_File'].astype(str).str.strip() == '') |
                    (final_df['Level1_File'].astype(str).str.lower() == 'nan')
                )
                mask_level1 = mask_code4_fallback & level1_empty
                
                if mask_level1.any():
                    # Level1 컬럼이 없으면 생성
                    if 'Level1_File' not in final_df.columns:
                        final_df['Level1_File'] = ""
                        final_df['Level1_Column'] = ""
                        final_df['Level1_MasterType'] = ""
                        final_df['Level1_Matched(%)'] = ""
                    
                    final_df.loc[mask_level1, 'Level1_File'] = final_df.loc[mask_level1, 'CodeFile_4'].astype(str).str.strip()
                    final_df.loc[mask_level1, 'Level1_Column'] = final_df.loc[mask_level1, 'CodeColumn_4'].astype(str).str.strip()
                    final_df.loc[mask_level1, 'Level1_MasterType'] = final_df.loc[mask_level1, 'CodeType_4'].fillna('').astype(str).str.strip()
                    final_df.loc[mask_level1, 'Level1_Matched(%)'] = final_df.loc[mask_level1, 'Matched(%)_4'].fillna('').astype(str).str.strip()
            
            # Level_Depth 재계산 (Level4 포함 및 CodeFile_4 반영)
            def recalculate_level_depth(row):
                """Level 관계의 깊이 재계산 (Level0부터 Level4까지)"""
                max_depth = -1
                for i in range(0, 5):  # Level0부터 Level4까지
                    file_col = f"Level{i}_File"
                    col_col = f"Level{i}_Column"
                    
                    if file_col in row and col_col in row:
                        file_val = str(row.get(file_col, '')).strip() if pd.notna(row.get(file_col, '')) else ''
                        col_val = str(row.get(col_col, '')).strip() if pd.notna(row.get(col_col, '')) else ''
                        
                        # 빈 값, NaN, nan 문자열이 아니면 depth 업데이트
                        if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                            col_val and col_val.lower() not in ['nan', 'none', '']):
                            if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                max_depth = i
                
                return max_depth if max_depth >= 0 else 0
            
            final_df['Level_Depth'] = final_df.apply(recalculate_level_depth, axis=1)
            
            # Level_Relationship 재계산 (모든 Level 포함: Level1부터 Level4까지)
            # 모든 Level 컬럼이 존재하는지 확인하고 없으면 생성
            for i in range(1, 5):  # Level1부터 Level4까지
                file_col = f"Level{i}_File"
                col_col = f"Level{i}_Column"
                if file_col not in final_df.columns:
                    final_df[file_col] = ""
                if col_col not in final_df.columns:
                    final_df[col_col] = ""
            
            def recalculate_level_relationship(row):
                """Level 관계를 문자열로 합치기 (Level1부터 Level4까지)"""
                path_parts = []
                # Level1부터 Level4까지 확인 (Level0은 제외)
                for i in range(1, 5):  # Level1부터 Level4까지
                    file_col = f"Level{i}_File"
                    col_col = f"Level{i}_Column"
                    
                    # 값 가져오기 (컬럼이 없으면 빈 문자열)
                    try:
                        file_val_raw = row[file_col] if file_col in row else ''
                        col_val_raw = row[col_col] if col_col in row else ''
                    except (KeyError, IndexError):
                        continue
                    
                    # NaN 체크 및 문자열 변환
                    if pd.notna(file_val_raw) and pd.notna(col_val_raw):
                        file_val = str(file_val_raw).strip()
                        col_val = str(col_val_raw).strip()
                        
                        # 빈 값, NaN, nan 문자열 제거
                        if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                            col_val and col_val.lower() not in ['nan', 'none', '']):
                            # nan.nan 형식 제거
                            if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                path_parts.append(f"{file_val}.{col_val}")
                
                # 화살표로 연결
                if path_parts:
                    return " -> ".join(path_parts)
                else:
                    return ""
            
            def recalculate_level_relationship_internal(row):
                """Level 관계를 문자열로 합치기 (제외 대상 MasterType 제외, Level1부터 Level4까지)"""
                EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
                path_parts = []
                # Level1부터 Level4까지 확인 (Level0은 제외)
                for i in range(1, 5):  # Level1부터 Level4까지
                    file_col = f"Level{i}_File"
                    col_col = f"Level{i}_Column"
                    master_type_col = f"Level{i}_MasterType"
                    
                    # MasterType이 제외 대상인 경우 skip
                    try:
                        master_type = str(row.get(master_type_col, "")).strip() if pd.notna(row.get(master_type_col, "")) else ""
                        if master_type in EXCLUDED_MASTER_TYPES:
                            continue
                    except (KeyError, IndexError):
                        pass
                    
                    # 값 가져오기 (컬럼이 없으면 빈 문자열)
                    try:
                        file_val_raw = row[file_col] if file_col in row else ''
                        col_val_raw = row[col_col] if col_col in row else ''
                    except (KeyError, IndexError):
                        continue
                    
                    # NaN 체크 및 문자열 변환
                    if pd.notna(file_val_raw) and pd.notna(col_val_raw):
                        file_val = str(file_val_raw).strip()
                        col_val = str(col_val_raw).strip()
                        
                        # 빈 값, NaN, nan 문자열 제거
                        if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                            col_val and col_val.lower() not in ['nan', 'none', '']):
                            # nan.nan 형식 제거
                            if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                path_parts.append(f"{file_val}.{col_val}")
                
                # 화살표로 연결
                if path_parts:
                    return " -> ".join(path_parts)
                else:
                    return ""
            
            final_df['Level_Relationship'] = final_df.apply(recalculate_level_relationship, axis=1)
            final_df['Level_Relationship_Internal'] = final_df.apply(recalculate_level_relationship_internal, axis=1)
            final_df['Level_Relationship_Internal'] = final_df.apply(recalculate_level_relationship_internal, axis=1)
        
        out_path = OUTPUT_FILE
        final_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        self.logger.info(f"저장 완료: {OUTPUT_FILE}")

# ================================================================
# main()
# ================================================================
def main():
    start = time.time()
    try:
        processor = Initializing_Main_Class()
        processor.run_pipeline()
        print("-"*50)
        print(f"총 처리 시간: {time.time() - start:.2f}초")
        print("-"*50)
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)
if __name__ == "__main__":
    main()
