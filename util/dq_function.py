import os
import re
import json
import yaml
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Tuple
from multiprocessing import Pool, cpu_count
from collections import Counter
from random import Random
import fnmatch
import traceback
import sys
from pathlib import Path

# '123.0' 형태만 정수부로 줄이기 (모듈 레벨)
_FLOAT_ZERO_RE = re.compile(r"^[+-]?\d+\.0+$")

# Import from dq_rules
# from dq_rules import validate_with_yaml_contract

# Global contract dictionary
DQ_CONTRACT_DICT = None

# ======================================================================
# IO & Utility Functions
# ======================================================================
def read_csv_any(path: str) -> pd.DataFrame:
    path = os.path.expanduser(os.path.expandvars(str(path)))
    for enc in ("utf-8-sig","utf-8","cp949","euc-kr"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, low_memory=False)
        except Exception:
            continue
    raise FileNotFoundError(path)

def _to_pct(x) -> float:
    """'12.34' / '12.34%' / '' / None 등을 안전하게 float(%)로."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    s = str(x).strip().replace('%', '')
    if s == '' or s.lower() == 'nan':
        return 0.0
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except:
        return 0.0
def _safe_to_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors='coerce')

def _proportions(counts: np.ndarray) -> np.ndarray:
    total = counts.sum()
    if total <= 0:
        return np.zeros_like(counts, dtype=float)
    return counts / total

def _strip_decimal_zero_if_numeric_str(x: object) -> str:
    """
    '123.0' '123.000' 같은 '숫자.0+' 형태만 → '123'으로.
    선행 0가 있는 코드('01000')나 실제 소수('1.25'), 버전('v1.0') 등은 건드리지 않음.
    """
    s = str(x)
    if _FLOAT_ZERO_RE.fullmatch(s):
        return s.split('.', 1)[0]
    return s 

def safe_int(x, default=0):
    try:
        if pd.isna(x) or x == '':
            return default
        return int(x)
    except Exception:
        return default

def safe_float(x, default=0.0):
    try:
        if pd.isna(x) or x == '':
            return default
        return float(x)
    except Exception:
        return default
# ======================================================================
# Oracle Type Inference (name/digits heuristics)
# ======================================================================   
CODEY_NAME_HINT    = re.compile(r"(zip|postal|우편|code|코드|id|식별|번호)$", re.IGNORECASE)

def Get_Oracle_Type(series, column_name: str | None = None):
    def _safe_to_numeric(s: pd.Series) -> pd.Series:
        return pd.to_numeric(s, errors='coerce')

    s_all = series.dropna().astype(str).str.strip()
    if s_all.empty:
        return "NULL"

    name_is_codey = bool(column_name and CODEY_NAME_HINT.search(str(column_name)))

    date_like = s_all.str.fullmatch(
        r"\d{4}[-/.]?\d{2}[-/.]?\d{2}([ T]\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?)?"
    ).mean()
    if date_like >= 0.98:
        return "DATE"

    num_like = s_all.str.fullmatch(r"[+-]?\d+(?:\.\d+)?").mean()
    has_leading_zero = s_all.str.match(r"^0\d+$").any()
    fixed_length     = s_all.str.len().nunique(dropna=True) == 1

    if num_like >= 0.98 and not name_is_codey and not has_leading_zero and not fixed_length:
        nums = _safe_to_numeric(s_all)
        if nums.empty:
            maxlen = int(s_all.str.len().max())
            return f"VARCHAR2({min(maxlen, 4000)})"
        if (nums % 1 == 0).all():
            max_digits = nums.abs().astype("Int64").astype(str).str.len().max()
            return f"NUMBER({int(max_digits)})"
        else:
            parts = nums.abs().astype(str).str.split(".")
            int_digits  = parts.str[0].str.len().astype(int).max()
            frac_digits = parts.str[1].str.len().fillna(0).astype(int).max()
            return f"NUMBER({int(int_digits + frac_digits)},{int(frac_digits)})"

    maxlen = int(s_all.str.len().max())
    return f"VARCHAR2({maxlen})" if maxlen <= 4000 else "CLOB"

# ======================================================================
# 파일별 컬럼 분석
# ======================================================================
# def create_datatype_df(filepath, code_type, extension):
#     """단일 파일의 컬럼별 Pandas/Oracle 타입 분석"""
#     try:
#         if extension in ("csv", ".csv"):
#             df = pd.read_csv(filepath, encoding="utf-8", low_memory=False)
#         elif extension in ("xlsx", ".xlsx"):
#             df = pd.read_excel(filepath)
#         elif extension in ("pkl", ".pkl"):
#             df = pd.read_pickle(filepath)
#         else:
#             raise ValueError(f"Unsupported file extension: {extension}")
#     except Exception as e:
#         print(f"파일 로드 실패: {filepath} → {e}")
#         return []

#     summary = []
#     for col in df.columns:
#         pandas_dtype = str(df[col].dtype)
#         try:
#             oracle_type = Get_Oracle_Type(df[col], col)
#         except Exception as e:
#             oracle_type = f"ERROR({e})"

#         summary.append({
#             "FilePath": str(filepath).replace('\\', '/'),
#             "FileName": os.path.basename(filepath),
#             "CodeType": code_type,
#             "ColumnName": col,
#             "PD_DataType": pandas_dtype,
#             "OracleType": oracle_type,
#         })

#     return summary

# # ======================================================================
# # Data Type 분석
# # ======================================================================
# def DataType_Analysis(config, source_dir_list):

#     """모든 코드 파일에 대한 DataType 분석"""
#     print("\n=== DataType 분석 시작 ===")

#     base_path = Path(str(config["ROOT_PATH"]).rstrip("/\\"))
#     datatype_path = f"{base_path}/{config['files']['datatype']}.csv"
#     datatype_df = read_csv_any(datatype_path)
    
#     # # 기존 데이터가 있으면 그대로 반환
#     # if not datatype_df.empty:
#     #     print(f"기존 DataType 파일을 찾았습니다. ({len(datatype_df)}개 레코드)")
#     #     return datatype_df
    
#     # print("⚠️ DataType 파일이 없습니다. 새로 생성합니다.")
    
#     # source_dir_list에서 파일 분석
#     datatype_list = []
#     for source_config in source_dir_list:
#         # 'source' 또는 'path' 키 지원
#         source_key = 'source' if 'source' in source_config else 'path'
#         if source_key not in source_config:
#             print(f"⚠️ source_config에 'source' 또는 'path' 키가 없습니다: {source_config.keys()}")
#             continue
            
#         base_path = Path(str(config["ROOT_PATH"]).rstrip("/\\"))
#         source_subpath = str(source_config[source_key]).lstrip("/\\")
#         source_path = base_path / source_subpath
        
#         if not source_path.exists():
#             print(f"⚠️ 경로가 존재하지 않습니다: {source_path}")
#             continue
        
#         # extension 처리 (.csv, csv 모두 지원)
#         extension = source_config.get('extension', 'csv').lstrip('.')
#         file_pattern = f"*.{extension}"
#         files = list(source_path.glob(file_pattern))
        
#         if not files:
#             print(f"⚠️ {source_path}에 {extension} 파일이 없습니다.")
#             continue
            
#         print(f"\n {source_config.get('type', 'Unknown')} 코드 분석 중... (총 {len(files)}개 파일)")
#         for file in files:
#             try:
#                 datatype = create_datatype_df(file, source_config.get("type", ""), file.suffix)
#                 if datatype:
#                     datatype_list.extend(datatype)
#             except Exception as e:
#                 print(f"파일 처리 오류: {file.name} → {e}")

#     if not datatype_list:
#         print("처리된 데이터가 없습니다.")
#         return None

#     result_df = pd.DataFrame(datatype_list)
    
#     # 컬럼명 변환: CodeType -> MasterType, PD_DataType -> DataType
#     if not result_df.empty:
#         if 'CodeType' in result_df.columns:
#             result_df = result_df.rename(columns={'CodeType': 'MasterType'})
#         if 'PD_DataType' in result_df.columns:
#             result_df = result_df.rename(columns={'PD_DataType': 'DataType'})
    
#     print(f"DataType 분석 완료: {len(result_df)}개 레코드")
#     return result_df

# ======================================================================
# Standard Format 생성
# ======================================================================
def create_standard_df(df):
    result_rows = []

    # 1st
    cols = ['MasterType', 'ColumnName', 'PK', 'Format', 'Format(%)', 'FormatMin', 'FormatMax',
            'FormatMedian', 'ModeString', 'DetailDataType', 'FormatCnt']
    standard_df = df.loc[:, cols].copy()
    standard_df['FormatSeq'] = 1
    result_rows.extend(standard_df.to_dict(orient='records'))

    # 2nd
    cols = ['MasterType', 'ColumnName', 'PK',  'Format2nd', 'Format2nd(%)', 'Format2ndMin', 'Format2ndMax',
            'Format2ndMedian', 'ModeString','DetailDataType', 'FormatCnt']
    standard_df = df.loc[:, cols].copy()
    standard_df = standard_df.rename(columns={
        'Format2nd': 'Format',
        'Format2nd(%)': 'Format(%)',
        'Format2ndMin': 'FormatMin',
        'Format2ndMax': 'FormatMax',
        'Format2ndMedian': 'FormatMedian'
    })
    standard_df['FormatSeq'] = 2
    result_rows.extend(standard_df.to_dict(orient='records'))

    result_df = pd.DataFrame(result_rows)
    result_df['Format(%)'] = result_df['Format(%)'].astype(float)
    result_df['FormatLength'] = result_df['Format'].astype(str).str.len()
    mask = (result_df['FormatLength'] > 2) & (result_df['Format(%)'] > 10.0)
    result_df = result_df.loc[mask]

    result_df = result_df.drop_duplicates(['MasterType', 'Format', 'ColumnName'])
    sum_df = result_df.groupby(['Format']).agg(count=('ColumnName', 'count')).rename(columns={'count': 'FormatCols'})
    result_df = pd.merge(result_df, sum_df, on='Format', how='left')

    cols = {'ADDRESS', 'URL', 'DATECHAR', 'TEL', 'EMAIL', 'CELLPHONE', 'CAR_NUMBER', 'COMPANY', 'TIMESTAMP', 'TIME', 'YYMMDD', 'DATECHAR', 'YEARMONTH', 'YEAR'}
    result_df.loc[(result_df['PK'] == 1), 'PK_Name'] = result_df['ColumnName'] 
    result_df.loc[(result_df['FormatCols'] == 1) & (~result_df['DetailDataType'].isin(cols)), 'Format_Unique_Name'] = result_df['ColumnName']
    result_df.loc[(result_df['DetailDataType'].isin(cols)), 'DataType_Name'] = result_df['DetailDataType']
    return result_df

# ======================================================================
# Unique Combination (simple greedy) with guard
# ======================================================================
def Find_Unique_Combination(df: pd.DataFrame, max_try_cols: int = 15) -> list[str]:
    """
    중복 없는 컬럼 조합 반환. 대규모 테이블 성능 보호를 위해 앞쪽 max_try_cols까지만 탐색.
    """
    if df.empty:
        return []
    
    columns = df.columns.tolist()[:max_try_cols]
    current_combo = []
    for column in columns:
        current_combo.append(column)
        try:
            group_sizes = df.groupby(current_combo).size()
            if not group_sizes.empty and group_sizes.max() == 1:
                return current_combo
        except Exception:
            # groupby 실패 시 현재 조합 반환
            continue
    return current_combo
# ======================================================================
# Severity 표준화
# ======================================================================
def _ensure_severity_column(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame({"Severity": []})
    d = df.copy()
    if d.empty and "Severity" not in d.columns:
        d["Severity"] = []
    lower_map = {c.lower(): c for c in d.columns}
    if "severity" in lower_map:
        src = lower_map["severity"]
        if src != "Severity": d = d.rename(columns={src: "Severity"})
    elif "level" in lower_map:
        d["Severity"] = d[lower_map["level"]]
    elif "priority" in lower_map:
        d["Severity"] = d[lower_map["priority"]]
    elif "sev" in lower_map:
        d["Severity"] = d[lower_map["sev"]]
    elif "Severity" not in d.columns:
        d["Severity"] = "medium"
    norm = {
        "l":"low","lo":"low","low":"low",
        "m":"medium","med":"medium","medium":"medium",
        "h":"high","hi":"high","high":"high",
        "c":"critical","crit":"critical","critical":"critical",
        "error":"high","warn":"medium","warning":"medium",
    }
    d["Severity"] = d["Severity"].astype(str).str.strip().str.lower().map(norm).fillna("medium")
    return d
   
# ======================================================================
# Determine_Detail_Type 함수
# ======================================================================
from dq_validate import (
    validate_date, validate_yearmonth, validate_latitude, validate_longitude,
    validate_YYMMDD, validate_tel, validate_cellphone, validate_address, validate_kor_name
)

FORMAT_MAX_VALUE   = 1000   # Format 검사 최대 길이 한계
FORMAT_AVG_LENGTH  = 50     # 평균 길이 기준(문장형 텍스트 추정)

def is_timestamp(pattern, pattern_type_cnt):
    return (pattern in ['nnnn-nn-nn nn:nn:nn', 'nnnn-nn-nn nn:nn:nn.nnnnnn', 'nnnn-nn-nn nn:nn:nn.']
            and int(pattern_type_cnt) == 1)

def is_time(pattern, pattern_type_cnt):
    return (pattern in ['nn:nn.n', 'nn:nn:nn', 'nn:nn:nn.nnnnnn', 'nn:nn:nn.']
            and int(pattern_type_cnt) == 1)

def is_datechar(pattern, format_stats):
    return (pattern in ['nnnnnnnn', 'nnnn-nn-nn', 'nnnn/nn/nn', 'nnnnKnnKnnK', 'nnnn.nn.nn', 'nnnn. n. nn.']
            and validate_date(str(format_stats['FormatMedian'])))

def is_yearmonth(pattern, format_stats):
    return (pattern in ['nnnnnn', 'nnnn-nn', 'nnnn/nn', 'nnnn.nn', 'nnnnKnnK']
            and validate_yearmonth(str(format_stats['FormatMedian'])))

def is_yymmdd(pattern, format_stats):
    return (pattern in ['nnnnnn', 'nn-nn-nn', 'nn/nn/nn', 'nn.nn.nn', 'nn.nn.nn.']
            and validate_YYMMDD(str(format_stats['FormatMedian'])))

def is_year(pattern, format_stats, total_stats):
    if pattern == 'nnnn' and format_stats['FormatMedian']:
        try:
            mode_val = float(total_stats['mode'])
            return 1990 < mode_val < 2999
        except Exception:
            return False
    return False

def is_latitude(pattern, format_stats):
    return (pattern in ['nn.nnnn','nn.nnnnn','nn.nnnnnn','nn.nnnnnnn','nn.nnnnnnnn']
            and validate_latitude(format_stats['FormatMode']))

def is_longitude(pattern, format_stats):
    return (pattern in ['nnn.nnnn','nnn.nnnnn','nnn.nnnnnn','nnn.nnnnnnn','nnn.nnnnnnnn']
            and validate_longitude(format_stats['FormatMode']))

def is_tel(pattern: str, top10_json: str, top_n: int = 10) -> bool:
    """
    Top10 컬럼(JSON 문자열)을 읽어서 상위 N개가 모두 전화번호이면 True 반환
    """
    # 전화번호 패턴만 허용
    tel_patterns = [
        'nnn-nnn-nnnn','nn-nnnn-nnnn','nn-nnn-nnnn','nnn-nnnn',
        'nnnn-nnnn','nnnnnnn','nnnnnnnn','nnnnnnnnnn'
    ]
    if pattern not in tel_patterns:
        return False

    # top10_json이 None이거나 빈 문자열인 경우 처리
    if not top10_json or top10_json.strip() == '':
        return False

    try:
        # JSON 문자열 → 리스트 변환
        values = json.loads(top10_json)
    except Exception as e:
        print(f"JSON 파싱 실패: {e}")
        return False

    # 상위 N개 추출 ( "__OTHER__" 제외 )
    top_values = [v for v in values if v != "__OTHER__"][:top_n]
    
    if not top_values:  # 빈 리스트인 경우
        return False

    # 첫 번째 값 검증하여 반드시 전화번호 형식이어야 함
    first_check = validate_tel(top_values[0])
    if not first_check:
        return False

    # 전화번호 검증 결과 계산
    valid_tel_count = sum(1 for val in top_values if validate_tel(val))
    total_count = len(top_values)
    
    return True if valid_tel_count / total_count >= 0.8 else False

def is_cellphone(pattern, format_stats):
    return (pattern in ['nnn-nnnn-nnnn','nnnnnnnnnnn']
            and validate_cellphone(format_stats['FormatMedian']))

def is_car_number(pattern, pattern_type_cnt):
    return (
        pattern in ['KKnnKnnnn', 'nnKnnnn', 'nnnKnnnn']
    )

def is_company(pattern, pattern_type_cnt):
    return (
        pattern in ['(K)KKKK', '(K)KKKKK', '(K)KKKKKK']
        and pattern_type_cnt > 5
    )

def is_email(pattern):
    return '@' in pattern and 1 <= pattern.count('.') <= 2

def is_url(pattern):
    return '://' in pattern and pattern.count('.') >= 1

def is_address(pattern: str, top10_json, top_n: int = 10) -> bool:
    """
    Top10(JSON 문자열 또는 리스트) 상위 값들이 validate_address 로 대부분 통과하면 ADDRESS.
    """
    if not (
        len(pattern) >= 8
        and pattern.count("K") >= 6
        and pattern.count(" ") >= 2
    ):
        return False

    if not top10_json:
        return False

    if isinstance(top10_json, (list, tuple, set)):
        values = [str(v) for v in top10_json]
    else:
        s = str(top10_json).strip()
        if not s:
            return False
        try:
            values = json.loads(s)
        except Exception:
            return False

    top_values = [str(v) for v in values if v != "__OTHER__"][:top_n]
    if not top_values:
        return False

    if not validate_address(top_values[0]):
        return False

    valid_cnt = sum(1 for v in top_values if validate_address(v))
    return (valid_cnt / len(top_values)) >= 0.8

def is_flag(pattern, format_stats, total_stats):
    if (format_stats['most_common_pattern'] == 'A' and
        total_stats.get('min') == 'N' and total_stats.get('max') == 'Y' and
        format_stats['pattern_type_cnt'] == 1): 
        return 'YN_Flag'
    if (format_stats['most_common_pattern'] == 'n' and
        total_stats.get('min') == '0' and total_stats.get('max') == '1' and
        format_stats['pattern_type_cnt'] == 1): 
        return 'True_False_Flag'
    if (format_stats['most_common_pattern'] in ['A','a'] and format_stats['pattern_type_cnt'] == 1): 
        return 'Alpha_Flag'
    if (format_stats['most_common_pattern'] == 'n' and format_stats['pattern_type_cnt'] == 1): 
        return 'Num_Flag'
    if (format_stats['most_common_pattern'] == 'K' and format_stats['pattern_type_cnt'] == 1): 
        return 'Kor_Flag'
    if ((format_stats['most_common_pattern'] == 'KKK') and format_stats['pattern_type_cnt'] < 6): 
        return 'KOR_NAME'
    return None

def is_text(pattern, max_length, format_stats):
    return (max_length > FORMAT_MAX_VALUE or
            len(pattern) > FORMAT_AVG_LENGTH or
            format_stats['pattern_type_cnt'] > 20)

def is_sequence(total_stats, unique_count):
    try:
        total_min = total_stats.get('min'); total_max = total_stats.get('max')
        if total_min not in (None,'') and total_max not in (None,''):
            total_min_f = float(total_min); total_max_f = float(total_max)
            if total_min_f.is_integer() and total_max_f.is_integer():
                total_min_i = int(total_min_f); total_max_i = int(total_max_f)
                expected_count = total_max_i - total_min_i + 1
                return expected_count > 0 and expected_count == unique_count
    except (ValueError, TypeError):
        pass
    return False

def Determine_Detail_Type(pattern, pattern_type_cnt, format_stats, total_stats,
                          max_length, unique_count, non_null_count, top10):
    format_stats = format_stats or {}
    total_stats = total_stats or {}
    detail_type = ''
    
    # 안전한 정수 변환
    max_length =        safe_int(max_length, 0)
    pattern_type_cnt =  safe_int(pattern_type_cnt, 0)
    unique_count =      safe_int(unique_count, 0)
    non_null_count =    safe_int(non_null_count, 0)
    # 1) 길이 기반
    if max_length > 4000:
        return 'CLOB'
    # 2) 날짜/시간
    if is_timestamp(pattern, pattern_type_cnt):     return 'TIMESTAMP'
    if is_time(pattern, pattern_type_cnt):          return 'TIME'
    if is_yymmdd(pattern, format_stats):            return 'YYMMDD'
    if is_datechar(pattern, format_stats):          return 'DATECHAR'
    if is_yearmonth(pattern, format_stats):         return 'YEARMONTH'
    if is_year(pattern, format_stats, total_stats): return 'YEAR'
    # 3) 좌표
    if is_latitude(pattern, format_stats):          return 'LATITUDE'
    if is_longitude(pattern, format_stats):         return 'LONGITUDE'
    # 4) 연락처
    if top10 and is_tel(pattern, top10, 10):        return 'TEL' # 10 검사할 항목 수 
    if is_cellphone(pattern, format_stats):         return 'CELLPHONE'
    if is_car_number(pattern, pattern_type_cnt):    return 'CAR_NUMBER'
    if is_company(pattern, pattern_type_cnt):       return 'COMPANY'
    # 5) 특수 포맷
    if is_email(pattern):   return 'EMAIL'
    if is_url(pattern):     return 'URL'
    # 6) NULL
    if len(pattern) == 0:   return 'NULL'

    # 7) 주소/텍스트/한글명 기반
    if pattern_type_cnt > 0 and pattern[:1] == 'K': # 한글 패턴 체크
        if top10 and is_address(pattern, top10, 10):
            return "ADDRESS"
        # if is_kor_name(pattern, format_stats):      return 'KOR_NAME'
        if is_text(pattern, max_length, format_stats): return 'Text'

    # 8) 플래그/유일성 기반
    if pattern_type_cnt > 0:
        flag_type = is_flag(pattern, format_stats, total_stats)
        if flag_type: return flag_type
        if is_sequence(total_stats, unique_count): return 'SEQUENCE'
        if unique_count == 1: return 'SINGLE VALUE'
        if non_null_count > 0 and non_null_count == unique_count: return 'UNIQUE'

    return detail_type

# ======================================================================
# Distribution Snapshot + PSI
# ======================================================================
def dist_length_bins(s: pd.Series):
    x = s.dropna().astype(str).str.len().astype(float)
    edges = np.array([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5, 8.5, 12.5, 20.5, 32.5, 64.5, 128.5, np.inf])
    labels = ["0","1","2","3","4","5-8","9-12","13-20","21-32","33-64","65-128","129+"]
    if x.empty:
        return labels, np.zeros(len(labels), dtype=float)
    counts, _ = np.histogram(x.to_numpy(), bins=edges)
    return labels, _proportions(counts)

def dist_numeric_logbins(s: pd.Series) -> Tuple[list, np.ndarray]:
    """숫자 규모(절대값 log10) + 부호/0 구분 고정 bin 분포"""
    x = _safe_to_numeric(s).dropna()
    labels = ["(-inf,-1e6]","(-1e6,-1e3]","(-1e3,-1]", "(-1,0)","0",
              "(0,1)", "[1,1e3)", "[1e3,1e6)", "[1e6,inf)"]
    if x.empty:
        return labels, np.zeros(len(labels))
    neg = x[x < 0]; pos = x[x > 0]; zeros = (x == 0).sum()
    def bucket_neg(v):
        av = np.abs(v)
        return np.array([(av > 1e6).sum(),
                         ((av > 1e3)&(av <= 1e6)).sum(),
                         ((av >= 1)&(av <= 1e3)).sum(),
                         ((av > 0)&(av < 1)).sum()],dtype=int)
    def bucket_pos(v):
        return np.array([((v > 0)&(v < 1)).sum(),
                         ((v >= 1)&(v < 1e3)).sum(),
                         ((v >= 1e3)&(v < 1e6)).sum(),
                         (v >= 1e6).sum()],dtype=int)
    cneg = bucket_neg(neg); cpos = bucket_pos(pos)
    counts = np.array([cneg[0], cneg[1], cneg[2], cneg[3], zeros,
                       cpos[0], cpos[1], cpos[2], cpos[3]], dtype=int)
    return labels, _proportions(counts)

def dist_benford(s: pd.Series) -> Tuple[list, np.ndarray]:
    """Benford 1st digit 분포(1~9)"""
    x = _safe_to_numeric(s)
    labels = [str(i) for i in range(1,10)]
    if x.empty:
        return labels, np.zeros(9)
    v = x.replace(0, np.nan).dropna().abs().astype(str).str.replace(r'\.', '', regex=True)
    v = v.str.lstrip('0').str[0]
    v = v[v.isin(labels)]
    if v.empty:
        return labels, np.zeros(9)
    counts = v.value_counts().reindex(labels).fillna(0).to_numpy()
    return labels, _proportions(counts)

# --- PSI helpers -------------------------------------------------------
def _psi_safe(p, q, eps=1e-8) -> float:
    """라벨/길이/NaN/합계0 방어 PSI"""
    p = np.asarray(p, dtype=float).ravel()
    q = np.asarray(q, dtype=float).ravel()
    L = max(p.size, q.size)
    if p.size < L: p = np.pad(p, (0, L-p.size), constant_values=0.0)
    if q.size < L: q = np.pad(q, (0, L-q.size), constant_values=0.0)
    p = np.where(np.isfinite(p), p, 0.0); q = np.where(np.isfinite(q), q, 0.0)
    if p.sum() == 0 and q.sum() == 0:
        return 0.0
    p = np.clip(p, eps, None); q = np.clip(q, eps, None)
    p = p / p.sum(); q = q / q.sum()
    return float(np.sum((p - q) * np.log(p / q)))

def _align_by_labels(labels_base, props_base, labels_cur, props_cur):
    """합집합 라벨 순서로 p(base), q(cur) 정렬"""
    lab_base = list(labels_base); lab_cur = list(labels_cur)
    union = list(dict.fromkeys(lab_base + lab_cur))
    idx_b = {l:i for i,l in enumerate(lab_base)}
    idx_c = {l:i for i,l in enumerate(lab_cur)}
    p = np.array([props_base[idx_b[l]] if l in idx_b else 0.0 for l in union], dtype=float)
    q = np.array([props_cur[idx_c[l]] if l in idx_c else 0.0 for l in union], dtype=float)
    return p, q, union

# ======================================================================
# Distribution Snapshot + PSI
# ======================================================================
def dist_length_bins(s: pd.Series):
    x = s.dropna().astype(str).str.len().astype(float)
    edges = np.array([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5, 8.5, 12.5, 20.5, 32.5, 64.5, 128.5, np.inf])
    labels = ["0","1","2","3","4","5-8","9-12","13-20","21-32","33-64","65-128","129+"]
    if x.empty:
        return labels, np.zeros(len(labels), dtype=float)
    counts, _ = np.histogram(x.to_numpy(), bins=edges)
    return labels, _proportions(counts)

def dist_numeric_logbins(s: pd.Series) -> Tuple[list, np.ndarray]:
    """숫자 규모(절대값 log10) + 부호/0 구분 고정 bin 분포"""
    x = _safe_to_numeric(s).dropna()
    labels = ["(-inf,-1e6]","(-1e6,-1e3]","(-1e3,-1]", "(-1,0)","0",
              "(0,1)", "[1,1e3)", "[1e3,1e6)", "[1e6,inf)"]
    if x.empty:
        return labels, np.zeros(len(labels))
    neg = x[x < 0]; pos = x[x > 0]; zeros = (x == 0).sum()
    def bucket_neg(v):
        av = np.abs(v)
        return np.array([(av > 1e6).sum(),
                         ((av > 1e3)&(av <= 1e6)).sum(),
                         ((av >= 1)&(av <= 1e3)).sum(),
                         ((av > 0)&(av < 1)).sum()],dtype=int)
    def bucket_pos(v):
        return np.array([((v > 0)&(v < 1)).sum(),
                         ((v >= 1)&(v < 1e3)).sum(),
                         ((v >= 1e3)&(v < 1e6)).sum(),
                         (v >= 1e6).sum()],dtype=int)
    cneg = bucket_neg(neg); cpos = bucket_pos(pos)
    counts = np.array([cneg[0], cneg[1], cneg[2], cneg[3], zeros,
                       cpos[0], cpos[1], cpos[2], cpos[3]], dtype=int)
    return labels, _proportions(counts)

def dist_benford(s: pd.Series) -> Tuple[list, np.ndarray]:
    """Benford 1st digit 분포(1~9)"""
    x = _safe_to_numeric(s)
    labels = [str(i) for i in range(1,10)]
    if x.empty:
        return labels, np.zeros(9)
    v = x.replace(0, np.nan).dropna().abs().astype(str).str.replace(r'\.', '', regex=True)
    v = v.str.lstrip('0').str[0]
    v = v[v.isin(labels)]
    if v.empty:
        return labels, np.zeros(9)
    counts = v.value_counts().reindex(labels).fillna(0).to_numpy()
    return labels, _proportions(counts)

def dist_topk_categories(s: pd.Series, k: int = 10) -> Tuple[list, np.ndarray]:
    """Top-k 카테고리 + Other"""
    x = s.dropna().astype(str)
    # if x.empty:
    #     return ["__OTHER__"], np.array([0.0])
    if x.empty:
        return [""], np.array([0.0])
    top = x.value_counts().head(k)
    # labels = top.index.tolist() + ["__OTHER__"]
    labels = top.index.tolist()
    counts = top.values.astype(float)
    other = max(0, len(x) - int(counts.sum()))
    counts = np.append(counts, other).astype(float)
    return labels, _proportions(counts)

def build_dist_snapshot_for_df(df: pd.DataFrame, file_name: str, topk=10) -> list[dict]:
    rows = []
    for col in df.columns:
        s = df[col]
        # Length
        labels, props = dist_length_bins(s)
        rows.append({"FileName": file_name, "ColumnName": str(col),
                     "DistType": "length",
                     "Labels": json.dumps(labels, ensure_ascii=False),
                     "Proportions": json.dumps(props.tolist()),
                     "Value #": int(s.size - s.isna().sum())})
        # Top-K
        labels, props = dist_topk_categories(s, k=topk)
        rows.append({"FileName": file_name, "ColumnName": str(col),
                     "DistType": "topk",
                     "Labels": json.dumps(labels, ensure_ascii=False),
                     "Proportions": json.dumps(props.tolist()),
                     "Value #": int(s.size - s.isna().sum())})
        # Numeric 전용
        s_num = _safe_to_numeric(s)
        if (s_num.notna().mean() >= 0.9):
            labels, props = dist_numeric_logbins(s)
            rows.append({"FileName": file_name, "ColumnName": str(col),
                         "DistType": "num_log",
                         "Labels": json.dumps(labels, ensure_ascii=False),
                         "Proportions": json.dumps(props.tolist()),
                         "Value #": int(s_num.notna().sum())})
            labels, props = dist_benford(s)
            rows.append({"FileName": file_name, "ColumnName": str(col),
                         "DistType": "benford",
                         "Labels": json.dumps(labels, ensure_ascii=False),
                         "Proportions": json.dumps(props.tolist()),
                         "Value #": int(s_num.notna().sum())})
    return rows

# --- PSI helpers -------------------------------------------------------
def _psi_safe(p, q, eps=1e-8) -> float:
    """라벨/길이/NaN/합계0 방어 PSI"""
    p = np.asarray(p, dtype=float).ravel()
    q = np.asarray(q, dtype=float).ravel()
    L = max(p.size, q.size)
    if p.size < L: p = np.pad(p, (0, L-p.size), constant_values=0.0)
    if q.size < L: q = np.pad(q, (0, L-q.size), constant_values=0.0)
    p = np.where(np.isfinite(p), p, 0.0); q = np.where(np.isfinite(q), q, 0.0)
    if p.sum() == 0 and q.sum() == 0:
        return 0.0
    p = np.clip(p, eps, None); q = np.clip(q, eps, None)
    p = p / p.sum(); q = q / q.sum()
    return float(np.sum((p - q) * np.log(p / q)))

def _align_by_labels(labels_base, props_base, labels_cur, props_cur):
    """합집합 라벨 순서로 p(base), q(cur) 정렬"""
    lab_base = list(labels_base); lab_cur = list(labels_cur)
    union = list(dict.fromkeys(lab_base + lab_cur))
    idx_b = {l:i for i,l in enumerate(lab_base)}
    idx_c = {l:i for i,l in enumerate(lab_cur)}
    p = np.array([props_base[idx_b[l]] if l in idx_b else 0.0 for l in union], dtype=float)
    q = np.array([props_cur[idx_c[l]] if l in idx_c else 0.0 for l in union], dtype=float)
    return p, q, union

def compute_snapshot_drift(current_snap: pd.DataFrame, baseline_snap: pd.DataFrame,
                           key_cols=('FileName','ColumnName','DistType')) -> pd.DataFrame:
    if current_snap.empty or baseline_snap.empty:
        return pd.DataFrame(columns=list(key_cols)+["PSI","Drift"])
    m = pd.merge(current_snap, baseline_snap, on=list(key_cols),
                 suffixes=('', '_base'), how='inner')
    rows = []
    for _, r in m.iterrows():
        labels_c = json.loads(r["Labels"])
        props_c  = np.array(json.loads(r["Proportions"]), dtype=float)
        labels_b = json.loads(r["Labels_base"])
        props_b  = np.array(json.loads(r["Proportions_base"]), dtype=float)
        p, q, _  = _align_by_labels(labels_b, props_b, labels_c, props_c)
        psi      = _psi_safe(p, q)
        rows.append({ key_cols[0]: r[key_cols[0]],
                      key_cols[1]: r[key_cols[1]],
                      key_cols[2]: r[key_cols[2]],
                      "PSI": round(psi, 4),
                      "Drift": ("Stable" if psi < 0.1 else "Moderate" if psi < 0.25 else "Significant") })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["PSI"], ascending=False).reset_index(drop=True)
    return out

# ======================================================================
# DQ Score + Top Issues
# ======================================================================
def _safe_num(x, default=0.0) -> float:
    try:
        return float(x)
    except:
        return default

def _length_volatility(row) -> float:
    lmin = _safe_num(row.get('LenMin', 0))
    lmax = _safe_num(row.get('LenMax', 0))
    if lmax <= 0:
        return 0.0
    return max(0.0, min(100.0, (lmax - lmin) / lmax * 100.0))

def _type_mixed_pct(row) -> float:
    f1 = _to_pct(row.get('Format(%)', 0))
    f2 = _to_pct(row.get('Format2nd(%)', 0))
    f3 = _to_pct(row.get('Format3rd(%)', 0))
    top = max(0.0, min(100.0, max(f1, f2, f3)))
    return 100.0 - top

def _duplicate_pct(row) -> float:
    u = max(0.0, min(100.0, _to_pct(row.get('Unique(%)', 0))))
    return max(0.0, 100.0 - u)

def _rule_fail_pct(row) -> float:
    return _to_pct(row.get('RuleFail(%)', 0))

def add_dq_scores(result_df: pd.DataFrame,
                  weights: dict | None = None,
                  tag_thresholds: dict | None = None) -> pd.DataFrame:
    df = result_df.copy()
    if weights is None:
        weights = {"null": 0.40, "type_mixed": 0.25, "length_vol": 0.15, "duplicate": 0.10, "rule_fail": 0.10}
    if tag_thresholds is None:
        tag_thresholds = {"high_null": 20.0, "mixed_format": 30.0, "length_vol": 30.0, "low_unique": 90.0}

    df["Null_pct"]       = df.get("Null(%)", 0).apply(_to_pct)
    df["TypeMixed_pct"]  = df.apply(_type_mixed_pct, axis=1)
    df["LengthVol_pct"]  = df.apply(_length_volatility, axis=1)
    df["Duplicate_pct"]  = df.apply(_duplicate_pct, axis=1)
    df["RuleFail_pct"]   = df.apply(_rule_fail_pct, axis=1)

    penalty = (weights["null"]*df["Null_pct"] +
               weights["type_mixed"]*df["TypeMixed_pct"] +
               weights["length_vol"]*df["LengthVol_pct"] +
               weights["duplicate"]*df["Duplicate_pct"] +
               weights["rule_fail"]*df["RuleFail_pct"])

    df["DQ_Score"] = (100.0 - penalty).clip(0.0, 100.0).round(2)

    tags = []
    for _, r in df.iterrows():
        t = []
        if r["Null_pct"]      > tag_thresholds["high_null"]:    t.append("High NULLs")
        if r["TypeMixed_pct"] > tag_thresholds["mixed_format"]: t.append("Mixed formats")
        if r["LengthVol_pct"] > tag_thresholds["length_vol"]:   t.append("Length volatility")
        if r["Duplicate_pct"] > tag_thresholds["low_unique"]:   t.append("Very low uniqueness")
        if r["RuleFail_pct"]  > 0:                              t.append("Rule failures")
        tags.append(", ".join(t))
    df["DQ_Issues"]  = tags
    df["Issue_Count"] = df["DQ_Issues"].apply(lambda s: 0 if not s else len(s.split(", ")))
    return df

def build_top_issue_reports(scored_df: pd.DataFrame, top_n: int = 10):
    df = scored_df.copy()
    worst_columns = (df.sort_values(["DQ_Score","Null_pct","TypeMixed_pct"], ascending=[True, False, False])
                       .loc[:, ["FileName","ColumnName","DQ_Score","DQ_Issues","Null_pct","TypeMixed_pct","LengthVol_pct","Duplicate_pct","RuleFail_pct"]]
                       .head(top_n).reset_index(drop=True))
    by_file = (df.groupby(["FileName"], as_index=False)
                 .agg(Columns=("ColumnName","count"),
                      DQ_Avg=("DQ_Score","mean"),
                      DQ_P10=("DQ_Score", lambda s: np.percentile(s, 10)),
                      DQ_Min=("DQ_Score","min"))
                 .sort_values(["DQ_Avg","DQ_Min"]).reset_index(drop=True))
    by_file["DQ_Avg"] = by_file["DQ_Avg"].round(2)
    by_file["DQ_P10"] = by_file["DQ_P10"].round(2)
    by_file["DQ_Min"] = by_file["DQ_Min"].round(2)

    issue_catalog = (df.assign(has_issue = df["DQ_Issues"].apply(lambda s: s != ""))
                       .groupby("has_issue", as_index=False).size()
                       .rename(columns={"size":"Count"}))
    total = int(issue_catalog["Count"].sum()) or 1
    issue_catalog["Ratio(%)"] = (issue_catalog["Count"] / total * 100).round(2)

    return {"worst_columns": worst_columns, "by_file": by_file, "issue_catalog": issue_catalog}

# ======================================================================
# Baseline IO + Drift (Proxy-PSI)
# ======================================================================
def save_or_load_baseline(scored_df: pd.DataFrame, baseline_path: str, update=False) -> pd.DataFrame:
    """
    - baseline 파일이 없거나 update=True면 현재 scored_df를 baseline으로 저장 후 반환
    - 그 외에는 기존 baseline을 읽어 반환
    """
    os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
    if (not os.path.exists(baseline_path)) or update:
        scored_df.to_csv(baseline_path, index=False, encoding='utf-8-sig')
        return scored_df.copy()
    else:
        return pd.read_csv(baseline_path, encoding='utf-8-sig')

def _psi_proxy(p, q, eps=1e-6) -> float:
    p = np.asarray(p, dtype=float); q = np.asarray(q, dtype=float)
    p = np.clip(p, eps, None);      q = np.clip(q, eps, None)
    p = p / p.sum();                q = q / q.sum()
    return float(np.sum((p - q) * np.log(p / q)))

def _pattern_vector(row):
    f1 = _to_pct(row.get('Format(%)', 0))
    f2 = _to_pct(row.get('Format2nd(%)', 0))
    f3 = _to_pct(row.get('Format3rd(%)', 0))
    other = max(0.0, 100.0 - (f1 + f2 + f3))
    return np.array([f1, f2, f3, other]) / 100.0

def _null_vector(row):
    nullp = _to_pct(row.get('Null(%)', 0))
    return np.array([nullp, 100.0 - nullp]) / 100.0

def _unique_vector(row):
    up = _to_pct(row.get('Unique(%)', 0))
    return np.array([up, 100.0 - up]) / 100.0

def _label_drift(psi_val: float) -> str:
    if psi_val < 0.1:    return "Stable"
    elif psi_val < 0.25: return "Moderate"
    else:                return "Significant"

def compute_proxy_drift(current_df: pd.DataFrame, baseline_df: pd.DataFrame,
                        key_cols=('FileName','ColumnName'),
                        weights=None) -> pd.DataFrame:
    if weights is None:
        weights = {"pattern": 1.0, "null": 1.0, "unique": 1.0}

    if current_df is None or baseline_df is None or current_df.empty or baseline_df.empty:
        return pd.DataFrame(columns=list(key_cols)+[
            "PSI_Pattern","PSI_Null","PSI_Unique","PSI_Composite","Drift",
            "Pattern_Changed","Top2_Changed","Top3_Changed",
            "Null%_cur","Null%_base","Unique%_cur","Unique%_base"
        ])

    need = list(key_cols) + [
        'Format','Format2nd','Format3rd',
        'Format(%)','Format2nd(%)','Format3rd(%)',
        'Null(%)','Unique(%)'
    ]
    cur  = current_df[[c for c in need if c in current_df.columns]].copy()
    base = baseline_df[[c for c in need if c in baseline_df.columns]].copy()

    m = pd.merge(cur, base, on=list(key_cols), suffixes=('', '_base'), how='inner')
    rows = []
    for _, r in m.iterrows():
        v_pat_cur  = _pattern_vector(r)
        v_null_cur = _null_vector(r)
        v_uni_cur  = _unique_vector(r)

        v_pat_base = _pattern_vector({'Format(%)': r.get('Format(%)_base',0),
                                      'Format2nd(%)': r.get('Format2nd(%)_base',0),
                                      'Format3rd(%)': r.get('Format3rd(%)_base',0)})
        v_null_base = _null_vector({'Null(%)': r.get('Null(%)_base',0)})
        v_uni_base  = _unique_vector({'Unique(%)': r.get('Unique(%)_base',0)})

        psi_pattern = _psi_proxy(v_pat_base, v_pat_cur)
        psi_null    = _psi_proxy(v_null_base, v_null_cur)
        psi_unique  = _psi_proxy(v_uni_base, v_uni_cur)

        wsum = (weights['pattern'] + weights['null'] + weights['unique']) or 1.0
        composite = (weights['pattern']*psi_pattern +
                     weights['null']*psi_null +
                     weights['unique']*psi_unique) / wsum

        rows.append({
            key_cols[0]: r[key_cols[0]],
            key_cols[1]: r[key_cols[1]],
            "PSI_Pattern":   round(psi_pattern, 4),
            "PSI_Null":      round(psi_null, 4),
            "PSI_Unique":    round(psi_unique, 4),
            "PSI_Composite": round(composite, 4),
            "Drift": _label_drift(composite),
            "Pattern_Changed": bool(r.get('Format','')    != r.get('Format_base','')),
            "Top2_Changed":    bool(r.get('Format2nd','') != r.get('Format2nd_base','')),
            "Top3_Changed":    bool(r.get('Format3rd','') != r.get('Format3rd_base','')),
            "Null%_cur":    _to_pct(r.get('Null(%)',0)),
            "Null%_base":   _to_pct(r.get('Null(%)_base',0)),
            "Unique%_cur":  _to_pct(r.get('Unique(%)',0)),
            "Unique%_base": _to_pct(r.get('Unique(%)_base',0)),
        })

    drift_df = pd.DataFrame(rows)
    if not drift_df.empty:
        drift_df = drift_df.sort_values(['PSI_Composite','PSI_Pattern','PSI_Null'],
                                        ascending=[False, False, False]).reset_index(drop=True)
    return drift_df

# ======================================================================
# 규칙 매칭/정규화/샘플 수집
# ======================================================================
def _iter_contract_column_rules(contract_dict, file_name: str, col_name: str):
    if not contract_dict:
        return
    for item in contract_dict.get("data_contract", {}).get("columns", []):
        fpat = str(item.get("file", "*")); cpat = str(item.get("column", "*"))
        if fnmatch.fnmatch(file_name, fpat) and fnmatch.fnmatch(col_name, cpat):
            yield item

def _get_effective_pattern_rule(contract_dict, file_name: str, col_name: str):
    for item in _iter_contract_column_rules(contract_dict, file_name, col_name):
        rules = item.get("rules", {}) or {}
        pat = rules.get("pattern", {}) or {}
        if pat:
            return pat
    return None

def normalize_series_by_contract_pattern(s: pd.Series, file_name: str, col_name: str, contract_dict) -> pd.Series:
    """
    fixed_length + allow_leading_zero가 있는 컬럼 → zfill 적용
    (우편번호 등 선행 0 보존)
    """
    pat = _get_effective_pattern_rule(contract_dict, file_name, col_name)
    if not pat:
        return s
    fixed_len = pat.get("fixed_length", None)
    allow_lz  = bool(pat.get("allow_leading_zero", False))
    if fixed_len and allow_lz:
        return s.astype(str).str.strip().str.zfill(int(fixed_len))
    return s

def make_df_for_distribution(df: pd.DataFrame, file_name: str, contract_dict) -> pd.DataFrame:
    if not contract_dict or df is None or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        try:
            out[col] = normalize_series_by_contract_pattern(out[col], file_name, str(col), contract_dict)
        except Exception:
            pass
    return out

def collect_value_samples(df: pd.DataFrame, file_name: str, contract_dict,
                          per_col: int = 200, random_state: int = 42,
                          normalize: bool = True) -> list[dict]:
    rng = Random(random_state)
    rows = []
    if df is None or df.empty:
        return rows
    cols_to_sample = set()
    if contract_dict:
        for col in df.columns:
            for _ in _iter_contract_column_rules(contract_dict, file_name, str(col)):
                cols_to_sample.add(str(col))
                break
    if not cols_to_sample:
        cols_to_sample = set(map(str, list(df.columns)[:10]))
    for col in cols_to_sample:
        s = df[col]
        if normalize:
            s = normalize_series_by_contract_pattern(s, file_name, col, contract_dict)
        nonnull = s.dropna()
        if nonnull.empty:
            continue
        take = min(len(nonnull), per_col)
        try:
            sample_vals = nonnull.sample(n=take, random_state=rng.randint(0, 10**9)).astype(str).tolist()
        except Exception:
            sample_vals = nonnull.astype(str).head(take).tolist()
        rows.extend({"FileName": file_name, "ColumnName": col, "Value": v} for v in sample_vals)
    return rows

def get_importance_for_column(contract_dict, file_name: str, col_name: str) -> float:
    imp = 1.0
    if not contract_dict:
        return imp
    for item in _iter_contract_column_rules(contract_dict, file_name, col_name):
        try:
            val = float(item.get("importance", 1.0))
            if val > imp:
                imp = val
        except Exception:
            pass
    return imp

def apply_score_importance(scored_df: pd.DataFrame, contract_dict) -> pd.DataFrame:
    if scored_df is None or scored_df.empty:
        return scored_df
    df = scored_df.copy()
    df["Importance"] = [get_importance_for_column(contract_dict, str(r.get("FileName","")), str(r.get("ColumnName","")))
                        for _, r in df.iterrows()]
    penalty = 100.0 - df["DQ_Score"].astype(float)
    df["Weighted_DQ_Score"] = (100.0 - penalty * df["Importance"]).clip(0.0, 100.0).round(2)
    return df