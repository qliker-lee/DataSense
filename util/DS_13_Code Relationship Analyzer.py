# -*- coding: utf-8 -*-
# DS_13_Code Relationship Analyzer.py
# 코드 관계 분석 프로그램은 파일 형식 매핑 결과와 룰 매핑 결과를 기반으로 코드 관계 분석을 수행합니다.
# 2026.01.03 Qliker

import pandas as pd
import numpy as np
import os
import sys
# import logging

from pathlib import Path
import traceback
from typing import Dict, Any, Iterable, Optional, Sequence, List
from multiprocessing import Pool, cpu_count, Manager
from itertools import combinations
from collections import defaultdict

#---------------------------------------------------------------
# Path & Directory 설정
#---------------------------------------------------------------

if getattr(sys, 'frozen', False):  # A. 실행파일(.exe) 상태일 때: .exe 파일이 있는 위치가 루트입니다.
    ROOT_PATH = Path(sys.executable).parent
else:  # B. 소스코드(.py) 상태일 때: 현재 파일(util/..)의 상위 폴더가 루트입니다.   
    ROOT_PATH = Path(__file__).resolve().parents[1]

if str(ROOT_PATH) not in sys.path: # # 시스템 경로에 루트 추가 (어디서 실행해도 모듈을 찾을 수 있게 함)
    sys.path.insert(0, str(ROOT_PATH))

try:
    # from util.io import load_yaml_datasense  # YAML 파일 사용 안 함 (상수 사용)
    # from util.dq_format import Expand_Format, Combine_Format
    from util.dq_validate import (
        init_reference_globals,
        validate_date, validate_yearmonth, validate_latitude, validate_longitude,
        validate_YYMMDD, validate_year, validate_tel, validate_cellphone,
        validate_url, validate_email, validate_kor_name, validate_address,
        validate_country_code, validate_gender, validate_gender_en, validate_car_number,
        validate_time, validate_timestamp,
    )

except ImportError as e:
    print(f"필수 모듈 로드 실패: {e}")
    sys.exit(1)
# ---------------------- 전역 기본값 ----------------------
DEBUG_MODE = True   # 디버그 모드 여부 (True: 디버그 모드, False: 운영 모드)

OUTPUT_FILE_NAME = 'CodeMapping'       # 코드 관계 분석 결과 파일 이름
OUTPUT_FILEFORMAT = 'FileFormatMapping' # 파일 형식 매핑 결과 파일 이름
OUTPUT_FILENUMERIC = 'FileNumericStats' # 숫자 형식 통계 결과 파일 이름

OUTPUT_DIR = ROOT_PATH / 'DS_Output'
FILEFORMAT_FILE = OUTPUT_DIR / 'FileFormat.csv'
RULEDATATYPE_FILE = OUTPUT_DIR / 'RuleDataType.csv'
MASTER_META_FILE = ROOT_PATH / 'DS_Meta' / 'Master_Meta.csv'
CODEMAPPING_FILE = OUTPUT_DIR / 'CodeMapping.csv'
CODEMAPPING_ERD_FILE = OUTPUT_DIR / 'CodeMapping_erd.csv'  # 논리 ERD 매핑 결과 파일 이름
EXCLUSIVE_FILE = OUTPUT_DIR / "ERD_exclusive.csv"   # ERD 작성에서 제외할 컬럼 정의 

MATCH_RATE_THRESHOLD = 20 # 매핑 결과 중 MatchRate(%) 20% 이상인 레코드만 선택 (기본값: 20%)

# ---------------------- 함수 선언 ----------------------
def _clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    """
    데이터프레임의 헤더를 정리하는 함수
    """
    out = df.copy()
    out.columns = [str(c).replace('\ufeff', '').strip() for c in out.columns]
    return out

# ---------------------------------------------------------
# 1. 워커 함수 (CPU 코어별로 독립 실행되는 비교 로직) internal mapping 에서 사용
# ---------------------------------------------------------
def compare_columns_worker(task_info):
    """
    각 코어에서 실행될 독립적인 비교 함수
    task_info: (a_meta, b_meta, a_set, b_set)
    """
    a, b, a_set, b_set = task_info
    
    if not a_set or not b_set:
        return None

    # 교집합 연산 (Set 연산은 파이썬에서 가장 빠름)
    intersection = a_set.intersection(b_set)
    compare_count = len(intersection)
    total_count = len(a_set)
    
    match_rate = round(compare_count / total_count * 100, 2) if total_count > 0 else 0.0

    # 임계치(예: 10%) 미만은 결과에서 제외하여 메모리 절약
    if match_rate < 10.0:
        return None

    return {
        "FilePath": a['FilePath'], "FileName": a['FileName'], "ColumnName": a['ColumnName'],
        "MasterType": "Internal",
        "MasterFilePath": b['FilePath'], "MasterFile": b['FileName'],
        "ReferenceMasterType": "Internal", "MasterColumn": b['ColumnName'],
        "CompareLength": a.get('CompareLength', 0),
        "CompareCount": compare_count, "SourceCount": total_count, "MatchRate(%)": match_rate
    }

#-----------------------------------------------------------------------------------------------------    
def Expand_Format(Source_df, Mode='Reference') -> pd.DataFrame:
    """    Source_df의 상위 3개 포맷(Format_1~3)을 행으로 펼쳐서 반환.    """
    try:

        # 1) 전처리
        s_df = Source_df.copy().rename(columns={
            'Format':        'Format_1',
            'Format2nd':     'Format_2',
            'Format3rd':     'Format_3',
            'FormatMin':     'FormatMin_1',
            'FormatMax':     'FormatMax_1',
            'FormatMedian':   'FormatMedian_1',
            'Format2ndMin':  'FormatMin_2',
            'Format2ndMax':  'FormatMax_2',
            'Format2ndMedian': 'FormatMedian_2',
            'Format3rdMin':  'FormatMin_3',
            'Format3rdMax':  'FormatMax_3',
            'Format3rdMedian': 'FormatMedian_3',
            'FormatValue':   'FormatValue_1',
            'Format2ndValue':'FormatValue_2',
            'Format3rdValue':'FormatValue_3',
            'Format(%)':     'Format(%)_1',
            'Format2nd(%)':  'Format(%)_2',
            'Format3rd(%)':  'Format(%)_3',
        })

        # 2) i=1..3 별로 분리 → 표준 컬럼명으로 통일 → 붙이기
        frames = []
        for i in (1, 2, 3):
            cols_i = [
                'FilePath', 'FileName', 'ColumnName', 'DetailDataType',  'MasterType', 'CompareLength', 'FormatCnt', 'UniqueCnt',
                f'Format_{i}', f'FormatMin_{i}', f'FormatMax_{i}', f'FormatMedian_{i}', 
                f'FormatValue_{i}', f'Format(%)_{i}'
            ]

            # 존재하는 컬럼만 선택
            available_cols = [c for c in cols_i if c in s_df.columns]
            if not available_cols:
                continue
                
            df_i = s_df[available_cols].copy()
            
            # 컬럼명 변경 (존재하는 컬럼만)
            rename_dict = {}
            if f'Format_{i}' in df_i.columns:
                rename_dict[f'Format_{i}'] = 'Format'
            if f'FormatMin_{i}' in df_i.columns:
                rename_dict[f'FormatMin_{i}'] = 'FormatMin'
            if f'FormatMax_{i}' in df_i.columns:
                rename_dict[f'FormatMax_{i}'] = 'FormatMax'
            if f'FormatMedian_{i}' in df_i.columns:
                rename_dict[f'FormatMedian_{i}'] = 'FormatMedian'
            if f'FormatValue_{i}' in df_i.columns:
                rename_dict[f'FormatValue_{i}'] = 'FormatValue'
            if f'Format(%)_{i}' in df_i.columns:
                rename_dict[f'Format(%)_{i}'] = 'Format(%)'
            
            if rename_dict:
                df_i = df_i.rename(columns=rename_dict)

            df_i['MatchNo'] = i

            # 빈/결측 포맷 제거 (Format 컬럼이 있는 경우만)
            if 'Format' in df_i.columns and not df_i.empty:
                format_series = df_i['Format']
                # Series인지 확인 (단일 컬럼 선택은 항상 Series 반환)
                if isinstance(format_series, pd.Series):
                    mask = format_series.notna() & (format_series.astype(str).str.strip() != '')
                    df_i = df_i[mask]
                # 이상 케이스: DataFrame이 반환된 경우는 스킵
                elif isinstance(format_series, pd.DataFrame):
                    continue

            # 숫자형 정리
            for col in ('FormatValue', 'Format(%)', 'CompareLength'):
                if col in df_i.columns:
                    df_i[col] = pd.to_numeric(df_i[col], errors='coerce')

            frames.append(df_i)

        if not frames:
            return pd.DataFrame(columns=[
                'FilePath', 'FileName', 'ColumnName', 'DetailDataType', 'MasterType', 'FormatCnt', 'UniqueCnt', 'MatchNo',
                'Format', 'FormatMin', 'FormatMax', 'FormatMedian', 'FormatValue', 'Format(%)', 'CompareLength'
            ])

        result_df = pd.concat(frames, ignore_index=True)

        # 정렬 & 중복 제거(선택)
        result_df = (result_df
                     .drop_duplicates()
                     .sort_values(['FilePath','FileName','ColumnName','MasterType','Format(%)'], ascending=[True, True, True, True, False])
                     .reset_index(drop=True))

        return result_df

    except Exception as e:
        print(f"전체 처리 중 오류 발생: {e}")
        raise


def Combine_Format(source_df, reference_df):
    """
    source_df와 reference_df를 조합하여 반환 (기술적 최적화 버전)
    """
    try:
        # 제외할 타입 리스트 (set으로 변환하여 검색 속도 향상)
        except_types = {
            'Time', 'Timestamp', 'Date', 'DateTime', 'DATECHAR', 'TIME', 'TIMESTAMP', 
            'DATE', 'DATETIME', 'YEAR', 'YEARMONTH', 'YYMMDD', 'LATITUDE', 'LONGITUDE', 
            'TEL', 'CELLPHONE', 'ADDRESS', 'Alpha_Flag', 'Num_Flag', 'YN_Flag', 
            'NUM_Flag', 'KOR_Flag', 'KOR_Name'
        }

        # 1. 필터링 최적화: 불필요한 copy()를 줄이고 필터링 후 필요한 컬럼만 선택
        if 'DetailDataType' in source_df.columns:
            s_df = source_df[~source_df['DetailDataType'].isin(except_types)]
        else:
            s_df = source_df

        if 'DetailDataType' in reference_df.columns:
            r_df = reference_df[~reference_df['DetailDataType'].isin(except_types)]
        else:
            r_df = reference_df

        # 2. Merge 전 필요한 컬럼만 추출 및 Rename (메모리 절약)
        rename_map = {
            'FilePath': 'MasterFilePath', 'FileName': 'MasterFile',
            'MasterType': 'ReferenceMasterType', 'ColumnName': 'MasterColumn',
            'FormatCnt': 'MasterFormatCnt', 'FormatMin': 'MasterMin',
            'FormatMax': 'MasterMax', 'FormatMedian': 'MasterMedian',
            'FormatValue': 'MasterValue', 'Format(%)': 'Master(%)',
            'UniqueCnt': 'MasterUniqueCnt'
        }
        
        # r_df에서 필요한 컬럼만 골라내며 바로 이름을 바꿉니다.
        r_cols = ['Format'] + list(rename_map.keys())
        r_df = r_df[r_cols].rename(columns=rename_map)

        # 3. Merge 및 중복 제거
        result_df = pd.merge(s_df, r_df, on='Format', how='left')
        result_df = result_df.dropna(subset=['MasterFile'])
        result_df = result_df.drop_duplicates(['FilePath', 'FileName', 'ColumnName', 'MasterFile', 'MasterColumn'])

        # 4. 숫자형 변환 및 결측치 처리 (Vectorized fillna)
        num_cols = [
            'FormatCnt', 'FormatValue', 'UniqueCnt', 'CompareLength',
            'MasterFormatCnt', 'MasterValue', 'MasterUniqueCnt'
        ]
        for c in num_cols:
            if c in result_df.columns:
                result_df[c] = pd.to_numeric(result_df[c], errors='coerce').fillna(0)

        # 5. MasterCompareLength 계산 최적화
        # .str 연산은 무거우므로 결측치 먼저 처리 후 마지막 글자 추출
        mcol_series = result_df['MasterColumn'].astype(str)
        last_char = mcol_series.str[-1]
        result_df['MasterCompareLength'] = np.where(last_char.str.isdigit(), last_char, '0')

        # 6. 플래그 계산 (불필요한 Series 생성을 피하고 numpy 연산 활용)
        # result_df['Format']이 object일 수 있으므로 str.len() 연산 최적화
        fmt_len = result_df['Format'].astype(str).str.len()

        f0 = result_df['FormatMedian'].between(result_df['MasterMin'], result_df['MasterMax'])
        f1 = fmt_len > 1
        f2 = result_df['FormatCnt'] < result_df['MasterValue']
        f3 = ~( (result_df['FormatCnt'] >= result_df['MasterFormatCnt'] * 1.5) & 
                (result_df['FormatCnt'] >= 5) & 
                (result_df['MasterCompareLength'] == '0') )
        f5 = result_df['UniqueCnt'] >= 10
        f6 = result_df['FormatValue'] >= 10
        f8 = ~( (result_df['FilePath'] == result_df['MasterFilePath']) & 
                (result_df['FileName'] == result_df['MasterFile']) & 
                (result_df['ColumnName'] == result_df['MasterColumn']) )

        # 7. 최종 결과 할당 (bool을 int로 바로 변환)
        result_df['Match_Flag']  = f0.astype(int)
        result_df['Match_Flag1'] = f1.astype(int)
        result_df['Match_Flag2'] = f2.astype(int)
        result_df['Match_Flag3'] = f3.astype(int)
        result_df['Match_Flag4'] = 1
        result_df['Match_Flag5'] = f5.astype(int)
        result_df['Match_Flag6'] = f6.astype(int)
        result_df['Match_Flag7'] = 1
        result_df['Match_Flag8'] = f8.astype(int)

        # Final_Flag 연산 (논리 연산 & 가 산술 곱셈보다 빠름)
        # 모든 플래그가 1이어야 하므로 & 연산자를 사용합니다.
        result_df['Final_Flag'] = (
            result_df['Match_Flag'] & result_df['Match_Flag2'] & 
            result_df['Match_Flag3'] & result_df['Match_Flag5'] & 
            result_df['Match_Flag6'] & result_df['Match_Flag8']
        ).astype(int)

        return result_df

    except Exception as e:
        print(f"조합 처리 중 오류 발생: {e}")
        raise

#--------------[ 클래스 선언 ]--------------
# --- [1. 경로 및 설정 관리 클래스] ---
class DQConfig:
    ROOT_PATH = Path(__file__).resolve().parents[1]

    @staticmethod
    def get_path(rel_path) -> str:
        """EXE 빌드 환경과 일반 파이썬 환경 모두 대응"""
        return str(DQConfig.ROOT_PATH / rel_path)

# sys.path 추가 (내부 모듈 참조용)
if str(DQConfig.ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(DQConfig.ROOT_PATH))



class Initializing_Main_Class:
    # def __init__(self):

    def process_files_mapping(self):
        try:
            # 1. 파일 로드 (유지보수 용이하게 경로 관리)
            f_format_path = FILEFORMAT_FILE
            r_datatype_path = RULEDATATYPE_FILE
            m_meta_path = MASTER_META_FILE

            # 데이터 로드 시 에러 방지 (str 연산 오류 방지를 위해 모든 컬럼을 str로 읽거나 처리)
            df_ff = pd.read_csv(f_format_path, encoding='utf-8-sig', dtype=str).fillna('')
            df_rt = pd.read_csv(r_datatype_path, encoding='utf-8-sig', dtype=str).fillna('')
            df_mm = pd.read_csv(m_meta_path, encoding='utf-8-sig', dtype=str).fillna('')

            if df_ff.empty or df_rt.empty or df_mm.empty:
                print(f"기본 파일 로드 실패: {f_format_path}, {r_datatype_path}, {m_meta_path}")
                return False

            print("모든 기본 파일 로드 완료")

            # 2.  'str' 연산 부분 수정 (Vectorized 연산 사용)  예: 특정 컬럼에만 str 연산 적용
            for df in [df_ff, df_rt, df_mm]:
                for col in df.columns:
                    # 데이터프레임 자체가 아닌, 개별 시리즈(컬럼)에 str.strip() 적용
                    df[col] = df[col].astype(str).str.strip()

            # 3. 코드 관계 분석 메인 로직 
            result_df, erd_df = self.execute_relationship_analysis(df_ff, df_rt, df_mm)
  
            if result_df is not None and not result_df.empty:
                p = os.path.join(OUTPUT_DIR, CODEMAPPING_FILE)
                result_df.to_csv(p, index=False, encoding='utf-8-sig')
                print(f"Final CodeMapping : {CODEMAPPING_FILE} 저장")
            if erd_df is not None and not erd_df.empty:
                p = os.path.join(OUTPUT_DIR, CODEMAPPING_ERD_FILE)
                erd_df.to_csv(p, index=False, encoding='utf-8-sig')
                print(f"Final ERD Mapping : {CODEMAPPING_ERD_FILE} 저장")
            
            return True

        except Exception as e:
            print(f"분석 중 오류 발생: {e}")
            print(traceback.format_exc())
            return False

    def execute_relationship_analysis(self, df_ff, df_rt, df_mm) -> pd.DataFrame:
        """
        df_ff: 파일 형식 매핑 결과
        df_rt: 룰 매핑 결과
        df_mm: 마스터 매핑 결과
        """
        # 1) Reference
        reference_df = self.reference_mapping(df_ff)
        if reference_df is None or reference_df.empty:
            print("[reference_mapping] reference_df is empty")
            return pd.DataFrame()
        if DEBUG_MODE and reference_df is not None and not reference_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_3rd_ref_mapping.csv')
            reference_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"3rd reference mapping : {p} 저장")

        # 2) Rule
        rule_df = self.rule_mapping(df_ff, df_rt)
        if rule_df is None or rule_df.empty:
            print("[rule_mapping] rule_df is empty")
            return pd.DataFrame()
        if DEBUG_MODE and rule_df is not None and not rule_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_4th_rule_mapping.csv')
            rule_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"4th rule mapping : {p} 저장")

        # 3) Numeric stats
        numeric_df = self.numeric_column_statistics(df_ff)
        if DEBUG_MODE and numeric_df is not None and not numeric_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_5th_numeric_stats.csv')
            numeric_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"5th numeric stats : {p} 저장")

        # 4) Internal
        internal_df = self.internal_mapping(df_ff) # "데이터가 생긴 모양(Pattern)이 같은 것들끼리만" 그룹핑하여 비교 대상을 확 줄여버립니다.
        if internal_df is None or internal_df.empty:
            print("[internal_mapping] internal_df is empty")
            return pd.DataFrame()
        if DEBUG_MODE and internal_df is not None and not internal_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_6th_int_mapping.csv')
            internal_df.to_csv(p, index=False, encoding='utf-8-sig')

        # 5) concat + pivot + final
        concat_df = self.mapping_concat(reference_df, internal_df, rule_df)
        if concat_df is None or concat_df.empty:
            print("[mapping_concat] concat_df is empty")
            return pd.DataFrame()
        if DEBUG_MODE and concat_df is not None and not concat_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_7th_concat.csv')
            concat_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"7th concat_df : {p} 저장")

        pivoted_df = self.mapping_pivot(internal_df) 
        if pivoted_df is None or pivoted_df.empty:
            print("[mapping_pivot] pivoted_df is empty")
            return pd.DataFrame()
        if DEBUG_MODE and pivoted_df is not None and not pivoted_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_8th_pivoted.csv')
            pivoted_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"8th pivoted_df : {p} 저장")

        final_df = self.final_mapping(df_ff, pivoted_df, reference_df, rule_df) # 새로운 방식 
        if final_df is None or final_df.empty:
            print("[final_mapping] final_df is empty")
            return pd.DataFrame()
        if DEBUG_MODE and final_df is not None and not final_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_9th_final.csv')
            final_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"9th final mapping : {p} 저장")
        
        # ERD Mapping 수행 (DS_14 기능 통합)
        erd_df = self.build_erd_mapping(final_df)
        if DEBUG_MODE and erd_df is not None and not erd_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_10th_erd.csv')
            erd_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"10th erd_df : {p} 저장")
        
        # ERD_exclusive.csv 파일 생성/업데이트 (24_ERD_Column_Setup.py 기능 통합)
        self.create_or_update_exclusive_file(erd_df if erd_df is not None and not erd_df.empty else final_df)

        return final_df, erd_df

    # ---------------------------------------------------------
    # 2. 메인 클래스 내 확장 메서드 
    # ---------------------------------------------------------
    def mapping_check(self, mapping_df: pd.DataFrame, sample: int = 10000) -> pd.DataFrame:
        """기존 패턴 매핑 방식을 유지하되, 데이터 정제 과정을 캐싱하여 속도 최적화"""
        
        # --- 내부 유틸리티: 값을 한 번만 정제해서 저장 ---
        cleaned_cache = {} # (fpath, col, limit) -> cleaned_series_set

        def get_cleaned_values(fpath, col, df_source, limit):
            key = (fpath, col, limit)
            if key not in cleaned_cache:
                # 1. 샘플링 및 정제 (최초 1회만 수행)
                s = df_source[col].dropna().astype(str).str.strip()
                s = s.replace({'': pd.NA, 'nan': pd.NA, 'None': pd.NA}).dropna()
                
                if len(s) > sample:
                    s = s.sample(sample, random_state=42)
                
                if limit > 0:
                    s = s.str[:int(limit)]
                
                # 교집합 연산을 위해 set으로 변환하여 캐싱
                cleaned_cache[key] = set(s.unique())
            return cleaned_cache[key]

        # --------------------------------------------------
        mapping_df = mapping_df.copy()
        rows = []
        src_cache = {} # 파일 객체 캐시

        # FilePath 순으로 정렬하여 파일 로드 횟수 최소화
        for _, r in mapping_df.sort_values(by=['FilePath', 'MasterFilePath']).iterrows():
            fpath, col = str(r['FilePath']), str(r['ColumnName'])
            mpath, mcol = str(r['MasterFilePath']), str(r['MasterColumn'])
            
            # 파일 로드 (캐시 활용)
            for path in [fpath, mpath]:
                if path not in src_cache:
                    try:
                        src_cache[path] = _clean_headers(pd.read_csv(path, dtype=str, encoding='utf-8-sig', low_memory=False))
                    except: continue

            if fpath not in src_cache or mpath not in src_cache: continue
            
            df, md = src_cache[fpath], src_cache[mpath]
            if col not in df.columns or mcol not in md.columns: continue

            # 비교 길이 설정
            comp_len = int(r.get('CompareLength', 0) or r.get('MasterCompareLength', 0))

            # ✅ 핵심: 이미 정제된 데이터셋을 가져옴 (중복 연산 0)
            s_vals_set = get_cleaned_values(fpath, col, df, comp_len)
            m_vals_set = get_cleaned_values(mpath, mcol, md, comp_len)

            # ✅ 고속 Set 교집합 연산
            intersection = s_vals_set.intersection(m_vals_set)
            compare_count = len(intersection)
            total_count = len(s_vals_set)
            match_rate = round(compare_count / total_count * 100, 2) if total_count > 0 else 0.0

            if match_rate >= MATCH_RATE_THRESHOLD:
                rows.append({
                    "FilePath": fpath, "FileName": r['FileName'], "ColumnName": col, 
                    "MasterType": r['MasterType'], "MasterFilePath": mpath, "MasterFile": r.get('MasterFile',''),
                    "ReferenceMasterType": r['ReferenceMasterType'], "MasterColumn": mcol,
                    "CompareLength": comp_len, "CompareCount": compare_count, 
                    "SourceCount": total_count, "MatchRate(%)": match_rate
                })

        return pd.DataFrame(rows)

    #--------------------------------------------------
    def mapping_pivot(self, df_merged: pd.DataFrame, valid_threshold: float = 10.0,
                         top_k: int = 3, drop_old_pivot_cols: bool = True) -> pd.DataFrame:
        """Top-K 후보를 가로로 전개하는 개선된 피벗 로직"""
        
        if df_merged is None or df_merged.empty:
            return self._make_empty_pivot_df(top_k)

        # 1. 컬럼명 정리
        rename_map = {
            'MasterFilePath':'CodeFilePath', 'MasterFile':'CodeFile',
            'ReferenceMasterType':'CodeType', 'MasterColumn':'CodeColumn',
            'CompareCount':'Matched', 'MatchRate(%)':'Matched(%)'
        }
        df = df_merged.rename(columns=rename_map).copy()

        # 2. 숫자형 변환 및 필터링
        for numc in ["Matched", "Matched(%)"]:
            if numc in df.columns:
                df[numc] = pd.to_numeric(df[numc], errors='coerce').fillna(0)

        mask = (df["Matched"] > 0) & (df["Matched(%)"] >= valid_threshold)
        df = df.loc[mask].copy()
        
        if df.empty:
            return self._make_empty_pivot_df(top_k)

        # 3. 정렬 및 랭킹 부여 (Top-K 추출)
        grp_keys = ["FilePath", "FileName", "ColumnName", "MasterType"]
        sort_keys = grp_keys + ["Matched(%)", "Matched"]
        
        df = df.sort_values(sort_keys, ascending=[True]*4 + [False]*2, kind="mergesort")
        df['rank'] = df.groupby(grp_keys).cumcount() + 1
        df = df.loc[df["rank"] <= top_k]

        # 4. Pivot Table 생성
        value_vars = ["CodeFilePath", "CodeFile", "CodeType", "CodeColumn", "Matched", "Matched(%)"]
        wide = df.pivot_table(
            index=grp_keys,
            columns="rank",
            values=value_vars,
            aggfunc="first"
        )

        # 5. 컬럼명 평탄화 (Multi-index -> Single-index) 예: ('CodeFile', 1) -> 'CodeFile_1'
        wide.columns = [f"{c[0]}_{int(c[1])}" for c in wide.columns]
        wide = wide.reset_index()

        # 6. 컬럼 순서 정렬 (CodeFile_1, Matched_1, CodeFile_2, Matched_2... 순서로 정렬하고 싶을 때)
        ordered_cols = grp_keys.copy()
        for i in range(1, top_k + 1):
            for base in value_vars:
                col_name = f"{base}_{i}"
                if col_name in wide.columns:
                    ordered_cols.append(col_name)
                else:
                    wide[col_name] = "" if "Matched" not in base else 0
                    ordered_cols.append(col_name)

        return wide[ordered_cols].fillna("")

    def _make_empty_pivot_df(self, top_k):
        """빈 결과 데이터프레임 생성 유틸리티"""
        cols = ["FilePath", "FileName", "ColumnName", "MasterType"]
        bases = ["CodeFilePath", "CodeFile", "CodeType", "CodeColumn", "Matched", "Matched(%)"]
        for i in range(1, top_k + 1):
            for b in bases:
                cols.append(f"{b}_{i}")
        return pd.DataFrame(columns=cols)

    #--------------------------------------------------
    def rule_mapping(
        self,
        fileformat_df: pd.DataFrame,
        ruldatatype_df: pd.DataFrame,
        valid_types: Sequence[str] = (
            'URL','YEAR','EMAIL','CELLPHONE','TEL','LATITUDE','LONGITUDE',
            'DATECHAR','YEARMONTH','YYMMDD','ADDRESS','KOR_NAME', 'TIME', 'TIMESTAMP',
            'COUNTRY_ISO3','국가코드','시도','차량번호','GENDER','GENDER_EN'
        ),
        encodings_try: Iterable[str] = ("utf-8-sig","utf-8","cp949"),
        sampling_rows: Optional[int] = None,
        use_valuecnt_fallback: bool = True
    ) -> pd.DataFrame:
        """
        ruldatatype_df를 보고 파일의 컬럼에 대해 validate_* 함수를 적용해서 룰 기반 매핑 결과를 만들어 반환
        """
        out_cols = [
            'FilePath','FileName','ColumnName','MasterType','MasterColumn',
            'CompareCount','MatchRate(%)','MasterFile','ReferenceMasterType',
            'MasterFilePath','CompareLength','SourceCount'
        ]
        
        if ruldatatype_df is None or ruldatatype_df.empty:
            print("[rule_mapping] ruldatatype_df is empty")
            return pd.DataFrame(columns=out_cols)

        required_cols = ["FilePath","FileName","ColumnName","MasterType","ValueCnt","Rule","MatchedScoreList"]
        miss = set(required_cols) - set(ruldatatype_df.columns)
        if miss:
            print(f"[rule_mapping] ruldatatype_df 필수 컬럼 누락: {sorted(miss)}")
            raise ValueError(f"ruldatatype_df 필수 컬럼 누락: {sorted(miss)}")

        rule_clean = ruldatatype_df["Rule"].fillna("").astype(str).str.strip()
        mask = (ruldatatype_df["MasterType"] != "Reference") & (rule_clean != "")
        df_rule = ruldatatype_df.loc[mask, required_cols].copy()
        
        if df_rule.empty:
            print("[rule_mapping] df_rule is empty - MasterType이 'Reference'이거나 Rule이 빈 문자열인 행만 있음")
            return pd.DataFrame(columns=out_cols)

        # Matched(%) 계산 (MatchedScoreList의 첫 값)
        df_rule["Matched(%)"] = (
            df_rule["MatchedScoreList"].astype(str)
            .str.split(";").str[0].str.strip()
            .replace({"": np.nan, "nan": np.nan, "None": np.nan})
            .astype(float).fillna(0.0) * 100.0
        ).round(2)

        # rule name standardization
        rule_key_syn = {
            "주소": "ADDRESS", "국가코드": "COUNTRY_ISO3", "이메일": "EMAIL",
            "휴대폰": "CELLPHONE", "전화": "TEL", "위도": "LATITUDE", "경도": "LONGITUDE",
            "연월": "YEARMONTH", "연월일": "DATECHAR", "성씨": "KOR_NAME",
            "성별구분": "GENDER", "성별구분_영문": "GENDER_EN",
        }
        def _std_rule_name(x: str) -> str:
            x = (x or "").strip()
            xu = x.upper()
            if xu in (t.upper() for t in valid_types):
                return xu
            return rule_key_syn.get(x, xu)

        df_rule["Rule"] = df_rule["Rule"].map(_std_rule_name)
        vtypes = {t.upper() for t in valid_types}
        rule_df = df_rule[df_rule["Rule"].isin(vtypes)].copy()
        
        if rule_df.empty:
            print(f"[rule_mapping] rule_df is empty - valid_types에 포함된 Rule이 없음")
            return pd.DataFrame(columns=out_cols)

        mapper = {
            'URL': validate_url, 'YEAR': validate_year, 'EMAIL': validate_email,
            'CELLPHONE': validate_cellphone, 'TEL': validate_tel,
            'LATITUDE': validate_latitude, 'LONGITUDE': validate_longitude,
            'DATECHAR': validate_date, 'YEARMONTH': validate_yearmonth,
            'YYMMDD': validate_YYMMDD, 'ADDRESS': validate_address,
            'KOR_NAME': validate_kor_name,
            'COUNTRY_ISO3': validate_country_code, '국가코드': validate_country_code,
            '시도': validate_address, '차량번호': validate_car_number,
            'GENDER': validate_gender, 'GENDER_EN': validate_gender_en,
            'TIME': validate_time, 'TIMESTAMP': validate_timestamp,
        }

        results: List[Dict[str, Any]] = []
        # 파일 경로별 처리 (group by FilePath)
        file_groups = list(rule_df.sort_values('FilePath').groupby('FilePath'))
        
        # FilePath 정규화 함수
        def normalize_filepath(path_str):
            """경로를 정규화하여 일치시킴"""
            if pd.isna(path_str) or path_str == '':
                return path_str
            path_str = str(path_str).strip()
            # 백슬래시를 슬래시로 변환
            path_str = path_str.replace('\\', '/')
            # 상대 경로인 경우 절대 경로로 변환 시도
            if not os.path.isabs(path_str):
                # 여러 인코딩 시도
                for enc in encodings_try:
                    try:
                        # ROOT_PATH 기준으로 절대 경로 생성
                        abs_path = Path(path_str)
                        if not abs_path.is_absolute():
                            abs_path = Path.cwd() / abs_path
                        if abs_path.exists():
                            return str(abs_path.resolve()).replace('\\', '/')
                    except:
                        continue
            return path_str
        
        for fpath, grp in file_groups:
            src_path = normalize_filepath(fpath)
            
            if not os.path.exists(src_path):
                print(f"[rule_mapping] 파일 경로 확인 불가: {src_path} (원본: {fpath})")
                # 대체 경로 시도
                alt_paths = [
                    str(Path(src_path).resolve()),
                    src_path.replace('/', '\\'),
                    src_path.replace('\\', '/'),
                ]
                found = False
                for alt in alt_paths:
                    if os.path.exists(alt):
                        src_path = alt
                        found = True
                        break
                if not found:
                    continue

            # 전체 파일 읽기 (헤더 정리)
            try:
                df_src = pd.read_csv(src_path, encoding='utf-8-sig', on_bad_lines="skip", dtype=str, low_memory=False)
                df_src = _clean_headers(df_src)
            except Exception as e:
                print(f"[rule_mapping] 파일 로드 실패: {src_path} -> {e}")
                continue

            # sampling
            if sampling_rows and sampling_rows > 0 and len(df_src) > sampling_rows:
                df_src = df_src.sample(n=sampling_rows, random_state=42)

            for _, r in grp.iterrows():
                col = str(r['ColumnName']).replace('\ufeff','').strip()
                if col not in df_src.columns:
                    continue

                series = df_src[col].dropna().astype(str)
                non_null = len(series)
                if non_null == 0:
                    continue

                key = str(r['Rule']).strip().upper()
                fn = mapper.get(key)
                if fn is None:
                    print(f"[rule_mapping] 미지원 Rule: {key} (지원되는 Rule: {sorted(mapper.keys())})")
                    continue

                try:
                    # apply validator and count True
                    valid_count = int(series.apply(fn).sum())
                except Exception as e:
                    print(f"[rule_mapping] validate 실패: {src_path}::{col} ({key}) -> {e}")
                    continue

                if valid_count <= 0:
                    continue

                rate = round(valid_count / max(non_null, 1) * 100, 2)
                results.append({
                    'FilePath': src_path,
                    'FileName': os.path.basename(src_path),
                    'ColumnName': col,
                    'MasterType': str(r['MasterType']).strip(),
                    'MasterColumn': key,
                    'CompareCount': int(valid_count),
                    'MatchRate(%)': float(rate),
                    'MasterFilePath': 'Rule',
                    'MasterFile': 'Rule',
                    'ReferenceMasterType': 'Rule',
                    'CompareLength': '',
                    'SourceCount': int(non_null),
                })

        if not results:
            return pd.DataFrame(columns=out_cols)

        out = pd.DataFrame(results)[out_cols].copy()
        for c in ('CompareCount','SourceCount','MatchRate(%)'):
            out[c] = pd.to_numeric(out[c], errors='coerce')
        out['MatchRate(%)'] = out['MatchRate(%)'].astype("float32").round(2)
        return out

    # ------------------ (4) 숫자 통계 ------------------
    def numeric_column_statistics(self, fileformat_df: pd.DataFrame, vSamplingRows: int = 10_000) -> Optional[pd.DataFrame]:
        """fileformat_df의 DetailDataType이 비어있는 항목들에 대해 숫자 통계 계산"""
        def calc_numeric(file_path: str, cols: List[str]) -> Optional[pd.DataFrame]:
            try:
                if not os.path.exists(file_path):
                    return None
                if file_path.lower().endswith('.csv'):
                    df = pd.read_csv(file_path, low_memory=False)
                elif file_path.lower().endswith('.pkl'):
                    df = pd.read_pickle(file_path)
                else:
                    df = pd.read_excel(file_path)
                if len(df) > vSamplingRows:
                    df = df.sample(n=vSamplingRows, random_state=42)

                rows=[]
                for c in cols:
                    if c not in df.columns:
                        continue
                    s = pd.to_numeric(df[c], errors='coerce').dropna()
                    if s.empty:
                        continue
                    desc = s.describe()
                    mean, std = desc['mean'], desc['std']
                    lcl, ucl = mean - 3*std, mean + 3*std
                    rows.append({
                        'FilePath': file_path, 'FileName': os.path.basename(file_path), 'ColumnName': c,
                        'dtype': str(s.dtype), 'Count': int(desc['count']), 'Mean': float(mean), 'Std': float(std),
                        'Min': float(desc['min']), '25%': float(desc['25%']), '50%': float(desc['50%']),
                        '75%': float(desc['75%']), 'Max': float(desc['max']),
                        'LCL': float(lcl), 'UCL': float(ucl),
                        'BelowLCL': int((s < lcl).sum()), 'AboveUCL': int((s > ucl).sum())
                    })
                return pd.DataFrame(rows) if rows else None
            except Exception as e:
                print(f"[numeric] 처리 오류: {file_path} -> {e}")
                return None

        # select candidates: DetailDataType empty AND Format(%) < 90 AND LenCnt > 2
        len_cnt = pd.to_numeric(fileformat_df.get('LenCnt', pd.Series(dtype='float')), errors='coerce').fillna(0)
        fmt_pct = pd.to_numeric(fileformat_df.get('Format(%)', pd.Series(dtype='float')), errors='coerce').fillna(0)
        target = fileformat_df[
            (len_cnt > 2) & (fmt_pct < 90) & (
                fileformat_df.get('DetailDataType').isna() |
                (fileformat_df.get('DetailDataType').astype(str).str.len() == 0)
            )
        ].copy()

        if target.empty:
            print("Numeric: 처리 대상 없음")
            return None

        blocks=[]
        for fpath, grp in target.groupby('FilePath'):
            cols = grp['ColumnName'].tolist()
            r = calc_numeric(fpath, cols)
            if r is not None and not r.empty:
                blocks.append(r)
        if not blocks:
            print("Numeric 결과 없음")
            return None
        return pd.concat(blocks, ignore_index=True)

    # ------------------ (5) Reference / Internal / Concat ------------------
    def reference_mapping(self, fileformat_df: pd.DataFrame) -> pd.DataFrame:
        expand_df = Expand_Format(fileformat_df)
        if expand_df is None or expand_df.empty:
            print("ref_1st : [reference_mapping] expand_df is empty")
            return pd.DataFrame()
        if DEBUG_MODE and expand_df is not None and not expand_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_1st_expand.csv')
            expand_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"1st expand_df : {p} 저장")
            
        expand_df['Format(%)'] = pd.to_numeric(expand_df.get('Format(%)', 0), errors='coerce').fillna(0)
        expand_df = expand_df.loc[expand_df['Format(%)'] > 10].copy()
        source_df = expand_df.loc[expand_df['MasterType'] != 'Reference'].copy()
        reference_df = expand_df.loc[expand_df['MasterType'] == 'Reference'].copy()
        if reference_df is None or reference_df.empty:
            print("ref_2nd : [reference_mapping] expand_df 중 Reference 타입 레코드 없음")
            return pd.DataFrame()

        combine_df = Combine_Format(source_df, reference_df)
        if combine_df is None or combine_df.empty:
            print("ref_2nd : [reference_mapping] combine_df is empty")
            return pd.DataFrame()

        if DEBUG_MODE and combine_df is not None and not combine_df.empty:
            p = os.path.join(OUTPUT_DIR, OUTPUT_FILE_NAME + '_2nd_combine.csv')
            combine_df.to_csv(p, index=False, encoding='utf-8-sig')
            print(f"2nd combine_df : {p} 저장")
        # Combine_Format must produce columns expected by mapping_check (MasterFilePath etc.)
        combine_df = combine_df[combine_df.get('Final_Flag', 0) == 1].copy()
        if combine_df.empty:
            return pd.DataFrame()
        mapping_df = self.mapping_check(combine_df)
        if mapping_df is None or mapping_df.empty:
            print("ref_3rd : [reference_mapping] mapping_check_df is empty")
            return pd.DataFrame()
        mapping_df = mapping_df[mapping_df['MatchRate(%)'] > MATCH_RATE_THRESHOLD]
        mapping_df = mapping_df.sort_values(by=['FilePath','ColumnName','MatchRate(%)'], ascending=[True,True,False])
        
        if mapping_df is None or mapping_df.empty:
            print(f"ref_4th : [reference_mapping] {MATCH_RATE_THRESHOLD} 조건 미충족")
            return pd.DataFrame()   
        return mapping_df

    def internal_mapping(self, fileformat_df: pd.DataFrame) -> pd.DataFrame:
        expand_df = Expand_Format(fileformat_df)
        expand_df['Format(%)'] = pd.to_numeric(expand_df.get('Format(%)', 0), errors='coerce').fillna(0)
        expand_df = expand_df.loc[expand_df['Format(%)'] > 10].copy()
        source_df = expand_df.loc[expand_df['MasterType'] != 'Reference'].copy()
        combine_df = Combine_Format(source_df, source_df) # Match 된 레코드 중 조건을 충족하는 레코드만 선택
        combine_df = combine_df[combine_df.get('Final_Flag', 0) == 1].copy()
        if combine_df.empty:
            return pd.DataFrame()
        mapping_df = self.mapping_check(combine_df)
        mapping_df = mapping_df[mapping_df['MatchRate(%)'] > MATCH_RATE_THRESHOLD]
        mapping_df = mapping_df.sort_values(by=['FilePath','ColumnName','MatchRate(%)'], ascending=[True,True,False])
        return mapping_df

    def mapping_concat(self, reference_df: pd.DataFrame, internal_df: pd.DataFrame, rule_df: pd.DataFrame) -> pd.DataFrame:
        required_cols = [
            'FilePath','FileName','ColumnName','MasterType','MasterFilePath',
            'MasterFile','ReferenceMasterType','MasterColumn','CompareLength',
            'CompareCount','MatchRate(%)'
        ]
        # safe slicing: if any missing -> create empty frame with those columns
        def safe_slice(df):
            if df is None or df.empty:
                return pd.DataFrame(columns=required_cols)
            cols_present = [c for c in required_cols if c in df.columns]
            missing = [c for c in required_cols if c not in df.columns]
            out = df.copy()
            for m in missing:
                out[m] = "" if "Count" not in m and "Rate" not in m else 0
            return out[required_cols]

        rref = safe_slice(reference_df)
        rint = safe_slice(internal_df)
        rrul = safe_slice(rule_df)
        concat_df = pd.concat([rref, rint, rrul], ignore_index=True)
        # rename to pivot-friendly names
        concat_df = concat_df.rename(columns={
            'MasterFilePath':'CodeFilePath','MasterFile':'CodeFile',
            'ReferenceMasterType':'CodeType','MasterColumn':'CodeColumn',
            'CompareCount':'Matched','MatchRate(%)':'Matched(%)'
        })
        # keep meaningful candidates only (>=20% match)
        concat_df['Matched(%)'] = pd.to_numeric(concat_df.get('Matched(%)', 0), errors='coerce').fillna(0)
        concat_df = concat_df[concat_df['Matched(%)'] > MATCH_RATE_THRESHOLD]
        concat_df = concat_df.sort_values(by=['FilePath','FileName','ColumnName','MasterType','Matched(%)'],
                                          ascending=[True,True,True,True,False])
        return concat_df

    def final_mapping(self, fileformat_df, pivoted_df, reference_df, rule_df) -> pd.DataFrame:
        """fileformat_df와 ruldatatype(preset)과 pivoted_df를 합쳐 최종 산출"""
        # rule_df 안전 처리
        if rule_df is None or rule_df.empty:
            df_rule = pd.DataFrame()
        else:
            df_rule = rule_df.copy()
        
        rule_required_cols = ["FilePath","FileName","ColumnName","MasterType", "Rule","MatchedScoreList"]
        # safe: fill missing rule cols if necessary
        if not df_rule.empty:
            for c in rule_required_cols:
                if c not in df_rule.columns:
                    df_rule[c] = ""
            df_rule = df_rule[rule_required_cols].copy()
        else:
            df_rule = pd.DataFrame(columns=rule_required_cols)
        #---------------------------------------------------------
        #  reference_df 읽어옴. 
        #---------------------------------------------------------
        ref_cols = ["FilePath","FileName","ColumnName","MasterType","MasterFilePath","MasterFile","ReferenceMasterType","MasterColumn","CompareLength","CompareCount","SourceCount","MatchRate(%)"]
        
        # reference_df가 None이거나 비어있는 경우 처리
        if reference_df is None or reference_df.empty:
            ref_df = pd.DataFrame(columns=ref_cols)
        else:
            # 안전하게 컬럼 확인 및 추가
            missing_cols = [c for c in ref_cols if c not in reference_df.columns]
            if missing_cols:
                # 누락된 컬럼 추가
                for c in missing_cols:
                    if "Count" in c or "Rate" in c:
                        reference_df[c] = 0
                    else:
                        reference_df[c] = ""
            
            ref_df = reference_df[ref_cols].copy()
            ref_df = ref_df.sort_values(by=['FilePath','FileName','ColumnName','MasterType','MatchRate(%)'], ascending=[True,True,True,True,False])
            ref_df = ref_df.groupby(['FilePath', 'ColumnName'], as_index=False).head(1)
        
        ref_df = ref_df.rename(columns={
            'MasterFilePath':'CodeFilePath_4',
            'MasterFile':'CodeFile_4',
            'ReferenceMasterType':'CodeType_4',
            'MasterColumn':'CodeColumn_4',
            'CompareCount':'Matched_4',
            'MatchRate(%)':'Matched(%)_4'
        })

        #---------------------------------------------------------
        #  pivoted_df 읽어옴. 
        #---------------------------------------------------------
        # pivoted_df may be empty -> create empty with expected columns
        pivot_cols = [
            'FilePath','FileName','ColumnName','MasterType',
            'CodeColumn_1','CodeFile_1','CodeFilePath_1','CodeType_1','Matched_1','Matched(%)_1',
            'CodeColumn_2','CodeFile_2','CodeFilePath_2','CodeType_2','Matched_2','Matched(%)_2'
        ]
        if pivoted_df is None or pivoted_df.empty:
            pivoted_df = pd.DataFrame(columns=pivot_cols)
        else:  # ensure all pivot cols exist
            for c in pivot_cols:
                if c not in pivoted_df.columns:
                    pivoted_df[c] = ""

        # merge
        df = pd.merge(fileformat_df, df_rule, on=['FilePath','FileName','ColumnName','MasterType'], how='left', suffixes=("","_rule"))
        df = pd.merge(df, pivoted_df, on=['FilePath','FileName','ColumnName','MasterType'], how='left', suffixes=("","_pivot"))
        df = pd.merge(df, ref_df, on=['FilePath','FileName','ColumnName','MasterType'], how='left', suffixes=("","_ref"))

        #---------------------------------------------------------
        #  Attribute 컬럼 생성
        #---------------------------------------------------------
        # Rule 컬럼에서 세미콜론 기준 첫 번째 값 추출하여 Attribute에 설정
        df['Attribute'] = ""
        if 'Rule' in df.columns:
            # Rule 컬럼을 문자열로 변환하고 NaN 처리
            df['Rule'] = df['Rule'].fillna("").astype(str).str.strip()
            # 세미콜론 기준으로 첫 번째 값 추출
            rule_first_value = df['Rule'].str.split(';').str[0].str.strip()
            # 값이 있으면 Attribute에 설정
            mask_rule = rule_first_value != ""
            df.loc[mask_rule, 'Attribute'] = rule_first_value[mask_rule]
        
        # Rule에서 값이 없는 경우 CodeColumn_4 값 사용
        if 'CodeColumn_4' in df.columns:
            df['CodeColumn_4'] = df['CodeColumn_4'].fillna("").astype(str).str.strip()
            mask_no_rule = (df['Attribute'] == "") & (df['CodeColumn_4'] != "")
            df.loc[mask_no_rule, 'Attribute'] = df.loc[mask_no_rule, 'CodeColumn_4']

        #---------------------------------------------------------
        #  PK -> FK mapping (if PK column present in fileformat_df) 추가
        #---------------------------------------------------------
        if 'PK' in fileformat_df.columns:
            pk_numeric = pd.to_numeric(fileformat_df['PK'], errors='coerce').fillna(0).astype(int)
            mask_pk = pk_numeric == 1
            tmp_df = fileformat_df.loc[mask_pk, ['FilePath','ColumnName']].copy()
            tmp_df = tmp_df.rename(columns={'FilePath':'CodeFilePath_1','ColumnName':'CodeColumn_1'})
            tmp_df['FK'] = 'FK'
            df = pd.merge(df, tmp_df, on=['CodeFilePath_1','CodeColumn_1'], how='left')

        return df

    # ===============================================================
    # ERD Mapping (DS_14 기능 통합)
    # ===============================================================
    def build_recursive_mapping_full(self, codemapping_df, max_depth=10):
        """
        codemapping_df 전체 행에 대해 재귀 매핑 수행 (미매핑 포함)
        Level 구조 자동 확장
        Matched(%)_n 정보 포함
        """
        # ----------------------------------------
        # 1. MasterType이 'Rule'인 경우 제외
        # ----------------------------------------
        codemapping_df = codemapping_df[codemapping_df["MasterType"] != "Rule"].copy()
        codemapping_df["CodeFile_1"] = codemapping_df["CodeFile_1"].apply(lambda x: x if x != "Rule" else "")

        # ----------------------------------------
        # 2. 그래프 구성 및 Matched(%) 정보 저장
        # ----------------------------------------
        graph = {}       # (file, col, master) → list of children
        nodes_info = {}  # node → {file, column, master}
        edge_matched = {}  # (parent, child) → Matched(%)_1 값

        for _, r in codemapping_df.iterrows():
            parent = (str(r["FileName"]), str(r["ColumnName"]), str(r["MasterType"]))
            child = None

            # child 존재 여부 및 CodeType_1이 'Rule'이 아닌 경우만 포함
            if pd.notna(r.get("CodeFile_1", "")) and str(r["CodeFile_1"]).strip() != "":
                code_type_1 = str(r.get("CodeType_1", "")).strip()
                child = (str(r["CodeFile_1"]), str(r["CodeColumn_1"]), code_type_1)

            # parent 등록
            nodes_info[parent] = {
                "file": parent[0],
                "column": parent[1],
                "master": parent[2],
            }
            graph.setdefault(parent, [])

            # child 등록 및 Matched(%) 정보 저장
            if child:
                nodes_info[child] = {
                    "file": child[0],
                    "column": child[1],
                    "master": child[2],
                }
                graph[parent].append(child)
                
                # Matched(%)_1 정보 저장
                matched_val = str(r.get("Matched(%)_1", "")).strip() if pd.notna(r.get("Matched(%)_1", "")) else ""
                edge_matched[(parent, child)] = matched_val

        # ----------------------------------------
        # 3. DFS - leaf 만 결과로 저장
        # ----------------------------------------
        results = []

        def dfs(path, depth):
            if depth > max_depth:
                return

            last = path[-1]
            children = graph.get(last, [])

            # Matched(%) 50 초과인 child만 필터링
            valid_children = []
            for child in children:
                if child not in path:  # cycle 방지
                    # Matched(%) 값이 50 이하인 경우 skip
                    matched_key = (last, child)
                    matched_val_str = edge_matched.get(matched_key, "")
                    should_skip = False
                    if matched_val_str:
                        try:
                            matched_val = float(matched_val_str)
                            if matched_val <= 50:
                                should_skip = True
                        except (ValueError, TypeError):
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
                    if i == 0:
                        record[f"Level{i}_Matched(%)"] = ""
                    else:
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
        # 4. 모든 시작 노드에 대해 DFS 수행
        # ----------------------------------------
        all_roots = list(nodes_info.keys())
        for root in all_roots:
            dfs([root], 1)

        # ----------------------------------------
        # 5. 결과 DataFrame 생성
        # ----------------------------------------
        df = pd.DataFrame(results)

        # 없는 Level 컬럼 자동 생성
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
        # 6. Level 관계를 전체 합친 컬럼 생성
        # ----------------------------------------
        def build_relationship_path(row):
            """Level 관계를 문자열로 합치기"""
            path_parts = []
            for i in range(1, max_level + 1):
                file_col = f"Level{i}_File"
                col_col = f"Level{i}_Column"
                
                if file_col in row and col_col in row:
                    file_val_raw = row[file_col]
                    col_val_raw = row[col_col]
                    
                    if pd.notna(file_val_raw) and pd.notna(col_val_raw):
                        file_val = str(file_val_raw).strip()
                        col_val = str(col_val_raw).strip()
                        
                        if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                            col_val and col_val.lower() not in ['nan', 'none', '']):
                            if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                path_parts.append(f"{file_val}.{col_val}")
            
            if path_parts:
                return " -> ".join(path_parts)
            else:
                return ""
        
        def build_relationship_path_internal(row):
            """Level 관계를 문자열로 합치기 (제외 대상 MasterType 제외)"""
            EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
            path_parts = []
            for i in range(1, max_level + 1):
                file_col = f"Level{i}_File"
                col_col = f"Level{i}_Column"
                master_type_col = f"Level{i}_MasterType"
                
                if file_col in row and col_col in row:
                    # MasterType이 제외 대상인 경우 skip
                    master_type = str(row.get(master_type_col, "")).strip() if pd.notna(row.get(master_type_col, "")) else ""
                    if master_type in EXCLUDED_MASTER_TYPES:
                        continue
                    
                    file_val_raw = row[file_col]
                    col_val_raw = row[col_col]
                    
                    if pd.notna(file_val_raw) and pd.notna(col_val_raw):
                        file_val = str(file_val_raw).strip()
                        col_val = str(col_val_raw).strip()
                        
                        if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                            col_val and col_val.lower() not in ['nan', 'none', '']):
                            if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                path_parts.append(f"{file_val}.{col_val}")
            
            if path_parts:
                return " -> ".join(path_parts)
            else:
                return ""
        
        df["Level_Relationship"] = df.apply(build_relationship_path, axis=1)
        df["Level_Relationship_Internal"] = df.apply(build_relationship_path_internal, axis=1)
        
        # Level_Depth 컬럼 생성
        def calculate_level_depth(row):
            max_depth = -1
            for i in range(0, max_level + 1):
                file_col = f"Level{i}_File"
                col_col = f"Level{i}_Column"
                
                if file_col in row and col_col in row:
                    file_val = str(row[file_col]).strip()
                    col_val = str(row[col_col]).strip()
                    
                    if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                        col_val and col_val.lower() not in ['nan', 'none', '']):
                        if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                            max_depth = i
            
            return max_depth if max_depth >= 0 else 0
        
        df["Level_Depth"] = df.apply(calculate_level_depth, axis=1)
        
        # Level_Depth_Internal 계산 (제외 대상 MasterType 제외)
        def calculate_level_depth_internal(row):
            """Level 관계의 깊이 계산 (제외 대상 MasterType 제외)"""
            EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
            max_depth = -1
            for i in range(0, max_level + 1):
                file_col = f"Level{i}_File"
                col_col = f"Level{i}_Column"
                master_type_col = f"Level{i}_MasterType"
                
                if file_col in row and col_col in row:
                    # MasterType이 제외 대상인 경우 skip
                    master_type = str(row.get(master_type_col, "")).strip() if pd.notna(row.get(master_type_col, "")) else ""
                    if master_type in EXCLUDED_MASTER_TYPES:
                        continue
                    
                    file_val = str(row[file_col]).strip()
                    col_val = str(row[col_col]).strip()
                    
                    if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                        col_val and col_val.lower() not in ['nan', 'none', '']):
                        if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                            max_depth = i
            
            return max_depth if max_depth >= 0 else 0
        
        df["Level_Depth_Internal"] = df.apply(calculate_level_depth_internal, axis=1)
        
        # Level_Relationship, Level_Relationship_Internal, Level_Depth, Level_Depth_Internal 컬럼을 Level 컬럼들 다음에 추가
        ordered_cols.append("Level_Relationship")
        ordered_cols.append("Level_Relationship_Internal")
        ordered_cols.append("Level_Depth")
        ordered_cols.append("Level_Depth_Internal")
        df = df[ordered_cols]

        return df

    def build_erd_mapping(self, final_df: pd.DataFrame) -> pd.DataFrame:
        """
        ERD Mapping 생성 (DS_14 기능 통합)
        final_df를 기반으로 재귀 매핑을 수행하여 Level 구조 생성
        """ 
        if final_df is None or final_df.empty:
            print("[build_erd_mapping] final_df is empty")
            return pd.DataFrame()
        
        try:
            # 재귀 매핑 수행
            result_2nd = self.build_recursive_mapping_full(final_df, max_depth=10)
            
            if result_2nd.empty:
                print("[build_erd_mapping] 재귀 매핑 결과가 비어있습니다")
                return pd.DataFrame()
            
            # Level0을 FileName, ColumnName, MasterType으로 매핑
            result_2nd = result_2nd.rename(columns={
                "Level0_File": "FileName",
                "Level0_Column": "ColumnName",
                "Level0_MasterType": "MasterType",
            })
            
            # base_cols 준비
            base_cols = ["FilePath", "FileName", "ColumnName", "MasterType", "PK", "FK", "Attribute"]
            if "FilePath" not in final_df.columns:
                final_df["FilePath"] = ""
            if "PK" not in final_df.columns:
                final_df["PK"] = ""
            if "FK" not in final_df.columns:
                final_df["FK"] = ""
            if "Attribute" not in final_df.columns:
                final_df["Attribute"] = ""
            
            # final_df에서 base_cols 추출
            final_base = final_df[base_cols].copy() if all(c in final_df.columns for c in base_cols) else pd.DataFrame(columns=base_cols)
            
            # 병합
            erd_df = pd.merge(final_base, result_2nd, on=["FileName", "ColumnName", "MasterType"], how="left")
            
            # CodeColumn_n 컬럼들 병합 (DS_14의 run_pipeline 로직)
            code_cols_to_merge = []
            for n in [1, 2, 3, 4]:
                for col_suffix in ['CodeColumn', 'CodeFile', 'CodeFilePath', 'CodeType', 'Matched', 'Matched(%)']:
                    col_name = f'{col_suffix}_{n}'
                    if col_name in final_df.columns:
                        code_cols_to_merge.append(col_name)
            
            if code_cols_to_merge:
                merge_cols = ['FileName', 'ColumnName', 'MasterType']
                if 'FilePath' in final_df.columns:
                    merge_cols = ['FilePath'] + merge_cols
                code_df = final_df[merge_cols + code_cols_to_merge].copy()
                
                merge_on = ['FileName', 'ColumnName', 'MasterType']
                if 'FilePath' in erd_df.columns and 'FilePath' in code_df.columns:
                    merge_on = ['FilePath'] + merge_on
                erd_df = pd.merge(erd_df, code_df, on=merge_on, how='left', suffixes=('', '_code'))
                
                # 중복 컬럼 정리
                for col in code_cols_to_merge:
                    if f'{col}_code' in erd_df.columns:
                        mask = erd_df[col].isna() | (erd_df[col].astype(str).str.strip() == "")
                        erd_df.loc[mask, col] = erd_df.loc[mask, f'{col}_code']
                        erd_df = erd_df.drop(columns=[f'{col}_code'])
                    elif col not in erd_df.columns:
                        erd_df[col] = ""
                
                # CodeColumn_1, CodeColumn_2, CodeColumn_3을 순차적으로 처리하고, CodeColumn_4가 있으면 마지막에 추가
                def left_compact_code_columns(row):
                    """CodeColumn_1, CodeColumn_2, CodeColumn_3을 왼쪽으로 compact하고, CodeColumn_4가 있으면 마지막에 추가"""
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
                compacted_df = erd_df.apply(left_compact_code_columns, axis=1)
                
                # 원본 DataFrame의 CodeColumn_n 관련 컬럼들을 compacted 결과로 교체
                for n in [1, 2, 3, 4]:
                    for col_suffix in ['CodeColumn', 'CodeFile', 'CodeFilePath', 'CodeType', 'Matched', 'Matched(%)']:
                        col_name = f'{col_suffix}_{n}'
                        if col_name in compacted_df.columns:
                            erd_df[col_name] = compacted_df[col_name]
                
                # CodeColumn_n을 Level_n으로 변환 (n=1,2,3,4)
                for level_num in [1, 2, 3, 4]:
                    level_file_col = f'Level{level_num}_File'
                    level_col_col = f'Level{level_num}_Column'
                    level_type_col = f'Level{level_num}_MasterType'
                    level_matched_col = f'Level{level_num}_Matched(%)'
                    
                    if level_file_col not in erd_df.columns:
                        erd_df[level_file_col] = ""
                        erd_df[level_col_col] = ""
                        erd_df[level_type_col] = ""
                        erd_df[level_matched_col] = ""
                
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
                        erd_df[code_file_col].notna() & 
                        (erd_df[code_file_col].astype(str).str.strip() != '') &
                        (erd_df[code_file_col].astype(str).str.lower() != 'nan')
                    )
                    code_column_valid = (
                        erd_df[code_col_col].notna() & 
                        (erd_df[code_col_col].astype(str).str.strip() != '') &
                        (erd_df[code_col_col].astype(str).str.lower() != 'nan')
                    )
                    level_empty = (
                        erd_df[level_file_col].isna() | 
                        (erd_df[level_file_col].astype(str).str.strip() == '') |
                        (erd_df[level_file_col].astype(str).str.lower() == 'nan')
                    )
                    
                    mask = code_file_valid & code_column_valid & level_empty
                    
                    if mask.any():
                        erd_df.loc[mask, level_file_col] = erd_df.loc[mask, code_file_col].astype(str).str.strip()
                        erd_df.loc[mask, level_col_col] = erd_df.loc[mask, code_col_col].astype(str).str.strip()
                        erd_df.loc[mask, level_type_col] = erd_df.loc[mask, code_type_col].fillna('').astype(str).str.strip()
                        erd_df.loc[mask, level_matched_col] = erd_df.loc[mask, code_matched_col].fillna('').astype(str).str.strip()
                
                # CodeColumn_1, CodeColumn_2, CodeColumn_3이 모두 비어있고 CodeFile_4에 값이 있는 경우
                def check_code_columns_empty(row):
                    """CodeColumn_1, CodeColumn_2, CodeColumn_3이 모두 비어있는지 확인"""
                    for n in [1, 2, 3]:
                        code_col = f'CodeColumn_{n}'
                        if code_col in row:
                            code_val = str(row.get(code_col, '')).strip() if pd.notna(row.get(code_col, '')) else ''
                            if code_val and code_val.lower() not in ['nan', 'none', '']:
                                return False
                    return True
                
                code_file_4_valid = (
                    erd_df['CodeFile_4'].notna() & 
                    (erd_df['CodeFile_4'].astype(str).str.strip() != '') &
                    (erd_df['CodeFile_4'].astype(str).str.lower() != 'nan')
                )
                code_column_4_valid = (
                    erd_df['CodeColumn_4'].notna() & 
                    (erd_df['CodeColumn_4'].astype(str).str.strip() != '') &
                    (erd_df['CodeColumn_4'].astype(str).str.lower() != 'nan')
                )
                
                code_columns_empty_mask = erd_df.apply(check_code_columns_empty, axis=1)
                mask_code4_fallback = code_columns_empty_mask & code_file_4_valid & code_column_4_valid
                
                # Level1이 비어있으면 CodeFile_4를 Level1로 사용
                if mask_code4_fallback.any():
                    level1_empty = (
                        erd_df['Level1_File'].isna() | 
                        (erd_df['Level1_File'].astype(str).str.strip() == '') |
                        (erd_df['Level1_File'].astype(str).str.lower() == 'nan')
                    )
                    mask_level1 = mask_code4_fallback & level1_empty
                    
                    if mask_level1.any():
                        if 'Level1_File' not in erd_df.columns:
                            erd_df['Level1_File'] = ""
                            erd_df['Level1_Column'] = ""
                            erd_df['Level1_MasterType'] = ""
                            erd_df['Level1_Matched(%)'] = ""
                        
                        erd_df.loc[mask_level1, 'Level1_File'] = erd_df.loc[mask_level1, 'CodeFile_4'].astype(str).str.strip()
                        erd_df.loc[mask_level1, 'Level1_Column'] = erd_df.loc[mask_level1, 'CodeColumn_4'].astype(str).str.strip()
                        erd_df.loc[mask_level1, 'Level1_MasterType'] = erd_df.loc[mask_level1, 'CodeType_4'].fillna('').astype(str).str.strip()
                        erd_df.loc[mask_level1, 'Level1_Matched(%)'] = erd_df.loc[mask_level1, 'Matched(%)_4'].fillna('').astype(str).str.strip()
                
                # Level_Depth 재계산
                def recalculate_level_depth(row):
                    """Level 관계의 깊이 재계산 (Level0부터 Level4까지)"""
                    max_depth = -1
                    for i in range(0, 5):
                        file_col = f"Level{i}_File"
                        col_col = f"Level{i}_Column"
                        
                        if file_col in row and col_col in row:
                            file_val = str(row.get(file_col, '')).strip() if pd.notna(row.get(file_col, '')) else ''
                            col_val = str(row.get(col_col, '')).strip() if pd.notna(row.get(col_col, '')) else ''
                            
                            if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                                col_val and col_val.lower() not in ['nan', 'none', '']):
                                if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                    max_depth = i
                    
                    return max_depth if max_depth >= 0 else 0
                
                erd_df['Level_Depth'] = erd_df.apply(recalculate_level_depth, axis=1)
                
                # Level_Depth_Internal 재계산 (제외 대상 MasterType 제외)
                def recalculate_level_depth_internal(row):
                    """Level 관계의 깊이 재계산 (제외 대상 MasterType 제외, Level0부터 Level4까지)"""
                    EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
                    max_depth = -1
                    for i in range(0, 5):
                        file_col = f"Level{i}_File"
                        col_col = f"Level{i}_Column"
                        master_type_col = f"Level{i}_MasterType"
                        
                        if file_col in row and col_col in row:
                            # MasterType이 제외 대상인 경우 skip
                            master_type = str(row.get(master_type_col, "")).strip() if pd.notna(row.get(master_type_col, "")) else ""
                            if master_type in EXCLUDED_MASTER_TYPES:
                                continue
                            
                            file_val = str(row.get(file_col, '')).strip() if pd.notna(row.get(file_col, '')) else ''
                            col_val = str(row.get(col_col, '')).strip() if pd.notna(row.get(col_col, '')) else ''
                            
                            if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                                col_val and col_val.lower() not in ['nan', 'none', '']):
                                if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                    max_depth = i
                    
                    return max_depth if max_depth >= 0 else 0
                
                erd_df['Level_Depth_Internal'] = erd_df.apply(recalculate_level_depth_internal, axis=1)
                
                # Level_Relationship 재계산
                for i in range(1, 5):
                    file_col = f"Level{i}_File"
                    col_col = f"Level{i}_Column"
                    if file_col not in erd_df.columns:
                        erd_df[file_col] = ""
                    if col_col not in erd_df.columns:
                        erd_df[col_col] = ""
                
                def recalculate_level_relationship(row):
                    """Level 관계를 문자열로 합치기 (Level1부터 Level4까지)"""
                    path_parts = []
                    for i in range(1, 5):
                        file_col = f"Level{i}_File"
                        col_col = f"Level{i}_Column"
                        
                        try:
                            file_val_raw = row[file_col] if file_col in row else ''
                            col_val_raw = row[col_col] if col_col in row else ''
                        except (KeyError, IndexError):
                            continue
                        
                        if pd.notna(file_val_raw) and pd.notna(col_val_raw):
                            file_val = str(file_val_raw).strip()
                            col_val = str(col_val_raw).strip()
                            
                            if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                                col_val and col_val.lower() not in ['nan', 'none', '']):
                                if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                    path_parts.append(f"{file_val}.{col_val}")
                    
                    if path_parts:
                        return " -> ".join(path_parts)
                    else:
                        return ""
                
                def recalculate_level_relationship_internal(row):
                    """Level 관계를 문자열로 합치기 (제외 대상 MasterType 제외, Level1부터 Level4까지)"""
                    EXCLUDED_MASTER_TYPES = ['Rule', 'Reference', 'Validation', 'Common']
                    path_parts = []
                    for i in range(1, 5):
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
                        
                        try:
                            file_val_raw = row[file_col] if file_col in row else ''
                            col_val_raw = row[col_col] if col_col in row else ''
                        except (KeyError, IndexError):
                            continue
                        
                        if pd.notna(file_val_raw) and pd.notna(col_val_raw):
                            file_val = str(file_val_raw).strip()
                            col_val = str(col_val_raw).strip()
                            
                            if (file_val and file_val.lower() not in ['nan', 'none', ''] and 
                                col_val and col_val.lower() not in ['nan', 'none', '']):
                                if not (file_val.lower() == 'nan' and col_val.lower() == 'nan'):
                                    path_parts.append(f"{file_val}.{col_val}")
                    
                    if path_parts:
                        return " -> ".join(path_parts)
                    else:
                        return ""
                
                erd_df['Level_Relationship'] = erd_df.apply(recalculate_level_relationship, axis=1)
                erd_df['Level_Relationship_Internal'] = erd_df.apply(recalculate_level_relationship_internal, axis=1)
            
            # Level 컬럼 정렬
            level_cols = [col for col in erd_df.columns if col.startswith("Level") and col not in ["Level_Depth", "Level_Depth_Internal", "Level_Relationship", "Level_Relationship_Internal"]]
            level_cols = sorted(level_cols, key=lambda x: (
                int(x.split("_")[0].replace("Level", "")) if x.split("_")[0].replace("Level", "").isdigit() else 999,
                x
            ))
            
            # 최종 컬럼 순서
            level_depth_col = ["Level_Depth"] if "Level_Depth" in erd_df.columns else []
            level_depth_internal_col = ["Level_Depth_Internal"] if "Level_Depth_Internal" in erd_df.columns else []
            level_relationship_col = ["Level_Relationship"] if "Level_Relationship" in erd_df.columns else []
            level_relationship_internal_col = ["Level_Relationship_Internal"] if "Level_Relationship_Internal" in erd_df.columns else []
            final_cols = base_cols + level_depth_col + level_depth_internal_col + level_relationship_col + level_relationship_internal_col + level_cols + code_cols_to_merge
            final_cols = [col for col in final_cols if col in erd_df.columns]
            erd_df = erd_df[final_cols]
            
            return erd_df
            
        except Exception as e:
            print(f"[build_erd_mapping] 오류 발생: {e}")
            print(traceback.format_exc())
            return pd.DataFrame()
    
    def create_or_update_exclusive_file(self, df: pd.DataFrame):
        """
        ERD_exclusive.csv 파일 생성/업데이트 (24_ERD_Column_Setup.py 기능 통합)
        df: CodeMapping_erd.csv 또는 CodeMapping.csv 데이터프레임
        """
        try:
            # 필수 컬럼 확인
            required_cols = ['FileName', 'ColumnName']
            if not all(col in df.columns for col in required_cols):
                print(f"[create_or_update_exclusive_file] 필수 컬럼이 없습니다: {required_cols}")
                return
            
            # CodeMapping.csv에서 OracleType 정보 가져오기 (24_ERD_Column_Setup.py와 동일)
            df_cm = None
            if CODEMAPPING_FILE.exists():
                try:
                    df_cm = pd.read_csv(CODEMAPPING_FILE, encoding='utf-8-sig', dtype=str).fillna('')
                    # 컬럼 정리
                    for col in df_cm.columns:
                        df_cm[col] = df_cm[col].astype(str).str.strip()
                    print(f"[create_or_update_exclusive_file] CodeMapping.csv 로드 완료: {len(df_cm)}행")
                except Exception as e:
                    print(f"[create_or_update_exclusive_file] CodeMapping.csv 로드 실패: {e}")
            
            # CodeMapping.csv가 있으면 OracleType 정보 병합
            if df_cm is not None and not df_cm.empty and 'OracleType' in df_cm.columns:
                # df와 df_cm을 FileName, ColumnName으로 병합하여 OracleType 정보 추가
                merge_keys = ['FileName', 'ColumnName']
                if all(col in df.columns for col in merge_keys):
                    df = pd.merge(df, df_cm[merge_keys + ['OracleType']], on=merge_keys, how='left', suffixes=('', '_cm'))
                    # OracleType이 비어있으면 _cm 버전 사용
                    if 'OracleType_cm' in df.columns:
                        df['OracleType'] = df['OracleType'].fillna(df['OracleType_cm'])
                        df = df.drop(columns=['OracleType_cm'])
                else:
                    # df에 FileName, ColumnName이 없으면 df_cm을 직접 사용
                    df = df_cm.copy()
            elif df_cm is not None and not df_cm.empty:
                # df_cm에 OracleType이 없으면 df_cm을 직접 사용
                df = df_cm.copy()
            
            # MasterType이 'Master'인 데이터만 필터링 (24_ERD_Column_Setup.py와 동일)
            if 'MasterType' in df.columns:
                df_filtered = df[df['MasterType'] == 'Master'].copy()
            else:
                df_filtered = df.copy()
            
            if df_filtered.empty:
                print("[create_or_update_exclusive_file] 필터링된 데이터가 비어있습니다.")
                return
            
            # 컬럼별 통계 생성
            col_to_tables = defaultdict(set)
            col_types = {}
            
            for _, row in df_filtered.iterrows():
                c_name = str(row['ColumnName']).strip()
                f_name = str(row['FileName']).strip()
                o_type = str(row.get('OracleType', '')).strip().upper() if pd.notna(row.get('OracleType')) else ""
                
                if c_name and f_name:
                    col_to_tables[c_name].add(f_name)
                    # DATE, TIMESTAMP, DATETIME 타입 우선 선택
                    if c_name not in col_types or o_type in ['DATE', 'TIMESTAMP', 'DATETIME']:
                        col_types[c_name] = o_type
            
            # 통계 데이터프레임 생성
            stats_data = []
            for col, tables in col_to_tables.items():
                curr_type = col_types.get(col, "")
                stats_data.append({
                    "ColumnName": col,
                    "OracleType": curr_type,
                    "ConnectionCount": len(tables),
                    "exclusive": 1 if curr_type in ['DATE', 'TIMESTAMP', 'DATETIME'] else 0
                })
            
            current_stats_df = pd.DataFrame(stats_data)
            
            # 기존 파일이 있으면 병합, 없으면 새로 생성
            if EXCLUSIVE_FILE.exists():
                try:
                    old_df = pd.read_csv(EXCLUSIVE_FILE, encoding='utf-8-sig')
                    if 'exclusive' in old_df.columns:
                        # 필요한 컬럼만 추출하여 merge 시 충돌 방지
                        old_settings = old_df[['ColumnName', 'exclusive']].drop_duplicates('ColumnName')
                        final_df = pd.merge(current_stats_df, old_settings, on='ColumnName', how='left', suffixes=('_init', ''))
                        # 기존 설정이 있으면 쓰고, 없으면 초기값(_init) 사용
                        final_df['exclusive'] = final_df['exclusive'].fillna(final_df['exclusive_init']).astype(int)
                        final_df = final_df.drop(columns=['exclusive_init'])
                    else:
                        final_df = current_stats_df
                except Exception as e:
                    print(f"[create_or_update_exclusive_file] 기존 파일 읽기 오류: {e}")
                    final_df = current_stats_df
            else:
                final_df = current_stats_df
            
            # ConnectionCount 기준 정렬
            final_df = final_df.sort_values(by="ConnectionCount", ascending=False)
            
            # 파일 저장
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            final_df.to_csv(EXCLUSIVE_FILE, index=False, encoding='utf-8-sig')
            print(f"[create_or_update_exclusive_file] ERD_exclusive.csv 생성/업데이트 완료: {EXCLUSIVE_FILE}")
            print(f"[create_or_update_exclusive_file] 총 {len(final_df)}개 컬럼, 제외 설정 {len(final_df[final_df['exclusive'] == 1])}개")
            
        except Exception as e:
            print(f"[create_or_update_exclusive_file] 오류 발생: {e}")
            print(traceback.format_exc())

# 메인 실행부
if __name__ == "__main__":
    import time
    start_time = time.time()
    analyzer = Initializing_Main_Class()
    result = analyzer.process_files_mapping()
    if result:
        print("="*50)
        print("Success : 코드 관계 분석 완료")
    else:
        print("="*50)
        print("Fail : 코드 관계 분석 실패")

    print(f"총 처리 시간: {time.time()-start_time:.2f}초")
    print("="*50)


# 다음은 성능향상을 위하여 적용한 기법들 입니다.  
# 📊 성능 최적화 요약 (43s → 17.9s)최적화 단계적용 기술효과
# 1단계: 필터링set 기반 검색 및 중복 copy() 
# 제거초기 데이터 로딩 및 메모리 점유율 감소
# 2단계: 병합(Merge)필요한 컬럼만 선택하여 조인
# 조인 연산 시 발생하는 오버헤드 최소화
# 3단계: 연산(Flag)between, & 논리 연산자 활용
# CPU 수준의 비트 연산으로 계산 속도 극대화
# 4단계: 문자열 처리
# np.where와 벡터화된 .str 접근문자열 루프 처리 비용 절감