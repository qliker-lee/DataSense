# -*- coding: utf-8 -*-
"""
DataSense DQ Profiling System 
Qliker, 2026.01.02 Version 2.0 
"""

import os
import re
import sys
import time
import json
import ast
import traceback
# import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from multiprocessing import Pool, cpu_count
from collections import Counter

#---------------------------------------------------------------
# Path & Directory 설정
#---------------------------------------------------------------
if getattr(sys, 'frozen', False):  # A. 실행파일(.exe) 상태일 때: .exe 파일이 있는 위치가 루트입니다.
    ROOT_PATH = Path(sys.executable).parent
else:  # B. 소스코드(.py) 상태일 때: 현재 파일(util/..)의 상위 폴더가 루트입니다.   
    ROOT_PATH = Path(__file__).resolve().parents[1]

if str(ROOT_PATH) not in sys.path: # # 시스템 경로에 루트 추가 (어디서 실행해도 모듈을 찾을 수 있게 함)
    sys.path.insert(0, str(ROOT_PATH))

# ---------------------------------------------------------------
# [2. 모듈 Import] 어떤 환경에서도 에러 없이 불러오도록 예외 처리
# ---------------------------------------------------------------

META_PATH = ROOT_PATH / 'DS_Meta' / 'CodeList_Meta.csv'
OUTPUT_DIR = ROOT_PATH / 'DS_Output'
FORMAT_FILE = OUTPUT_DIR / 'FileFormat.csv'
STATS_FILE = OUTPUT_DIR / 'FileStats.csv'
DATATYPE_FILE = OUTPUT_DIR / 'DataType.csv'
RULEDATATYPE_FILE = ROOT_PATH / 'DS_Output' / 'RuleDataType.csv'

RULE_DEFINITION_FILE = ROOT_PATH / 'DS_Meta' / 'RuleDefinition.csv'
RULE_DEFINITION_VALIDDATA_FILE = ROOT_PATH / 'DS_Meta' / 'RuleDefinition_ValidData.csv'
SAMPLE_ROWS = 10000
FORMAT_MAX_VALUE = 10000

#---------------------------------------------------------------
# Debug 설정
#---------------------------------------------------------------
DEBUG_MODE = False  # True로 설정하면 상세한 디버그 로그 출력
DEBUG_MAX_COLUMNS = 10  # 디버그할 최대 컬럼 수 (0이면 모두 디버그)

# ---------------- 유효성 함수(없으면 더미 대체) ----------------
try:
    from util.dq_validate import (
        validate_date, validate_yearmonth, validate_latitude, validate_longitude,
        validate_YYMMDD, validate_tel, validate_cellphone, validate_address, validate_gender, validate_gender_en
    )
except ImportError:
    try:
        from dq_validate import (
            validate_date, validate_yearmonth, validate_latitude, validate_longitude,
            validate_YYMMDD, validate_tel, validate_cellphone, validate_address, validate_gender, validate_gender_en
        )
    except Exception:
        def _false(*a, **k): return False
        validate_date = validate_yearmonth = validate_latitude = validate_longitude = _false
        validate_YYMMDD = validate_tel = validate_cellphone = validate_address = _false
        validate_gender = validate_gender_en = _false

# ... (상단 Import 및 경로 설정 부분은 유지) ...
def validate_rule(row, rule_row, valid_data_dict):
    """
    개별 컬럼 데이터가 RuleDefinition의 규칙에 맞는지 검증합니다.
    """
    try:
        # 1. 길이 체크
        current_len = row.get('LenMax', 0)
        min_len = rule_row.get('MinLen')
        max_len = rule_row.get('MaxLen')
        
        if pd.notnull(min_len) and min_len != '' and current_len < float(min_len): return False
        if pd.notnull(max_len) and max_len != '' and current_len > float(max_len): return False

        # 2. rule1 (패턴) 체크
        rule_pattern = rule_row.get('rule1', '')
        if pd.notnull(rule_pattern) and str(rule_pattern).strip() != '':
            if not eval_rule_string(row, str(rule_pattern)):
                return False

        # 3. rule2 (Top10 / FirstNTop10) 체크 - 'or' 조건 대응 버전
        rule2_raw = rule_row.get('rule2', '')
        if pd.notnull(rule2_raw) and 'in' in str(rule2_raw):
            # ' or ' 로 구분된 여러 조건을 각각 검사
            sub_rules = str(rule2_raw).split(' or ')
            or_match = False
            
            for sub in sub_rules:
                if ' in ' not in sub: continue
                target_col, valid_name = sub.split(' in ')
                target_col, valid_name = target_col.strip(), valid_name.strip()
                
                # JSON 파싱 보정 (홑따옴표를 쌍따옴표로)
                json_str = str(row.get(target_col, '{}')).replace("'", '"')
                try:
                    current_top_data = json.loads(json_str).keys()
                except:
                    current_top_data = []
                
                valid_list = valid_data_dict.get(valid_name, [])
                
                # 하나라도 일치하면 이 sub_rule은 참
                if any(str(item) in map(str, valid_list) for item in current_top_data):
                    or_match = True
                    break
            
            if not or_match: return False

        return True
    except Exception as e:
        # 디버깅용: 필요한 경우 주석 해제
        # print(f"Error in {row.get('ColumnName')}: {e}")
        return False

def eval_rule_string(row, rule_str):
    """문자열로 된 규칙(예: Format == 'nnn')을 판정합니다."""
    try:
        # row의 데이터를 로컬 변수로 변환하여 eval이 계산할 수 있게 함
        Format = row.get('Format', '')
        FormatCnt = row.get('FormatCnt', 0)
        # 선배님의 RuleDefinition에 있는 "Format == 'AAA'" 등을 실제 비교
        # 따옴표 처리 등을 보정하여 실행
        safe_rule = rule_str.replace('""', '"')
        return eval(safe_rule, {"Format": Format, "FormatCnt": FormatCnt})
    except:
        return False


# ---------------- IO ----------------
def read_csv_any(path) -> pd.DataFrame:
    """CSV 파일을 읽습니다. 여러 인코딩을 시도합니다."""
    path = os.path.expanduser(os.path.expandvars(str(path)))
    path_obj = Path(path)
    
    # 파일 존재 여부 확인
    if not path_obj.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    
    for enc in ("utf-8-sig","utf-8","cp949","euc-kr"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            # 인코딩 문제가 아닌 다른 오류는 즉시 발생
            raise Exception(f"파일 읽기 오류 ({path}): {e}")
    raise Exception(f"모든 인코딩 시도 실패: {path}")

def parse_jsonish_list(x):
    if x is None or (isinstance(x, float) and pd.isna(x)): return []
    if isinstance(x, (list, tuple, set)):
        return [str(v).strip().strip('"').strip("'")
                for v in x if str(v).strip().lower() not in {"", "nan", "null", "none"}]
    s = str(x).strip()
    if not s or s.lower() in {"nan", "null", "none", "{}", "[]"}: return []
    
    # 파이썬 딕셔너리 문자열을 JSON으로 변환 (홑따옴표 -> 쌍따옴표)
    # { '이': 50 } -> { "이": 50 }
    json_str = s.replace("'", '"')
    
    # JSON 형식 시도
    try:
        obj = json.loads(json_str)
        if isinstance(obj, dict):
            # 딕셔너리인 경우 키 목록 반환 (문자열로 변환하여 정규화)
            return [str(k).strip().strip('"').strip("'") 
                    for k in obj.keys() if str(k).strip().lower() not in {"", "nan", "null", "none"}]
        elif isinstance(obj, (list, tuple)):
            return [str(v).strip().strip('"').strip("'")
                    for v in obj if str(v).strip().lower() not in {"", "nan", "null", "none"}]
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 괄호 제거 후 토큰 분리
    s_cleaned = re.sub(r'^[\[\(\{]\s*|\s*[\]\)\}]$', '', s)
    # 딕셔너리 형태 문자열 처리: {'key1': value1, 'key2': value2} -> [key1, key2]
    if s_cleaned.startswith('{') or (':' in s_cleaned and (',' in s_cleaned or '}' in s_cleaned)):
        try:
            # 홑따옴표를 쌍따옴표로 변환 후 JSON 파싱 재시도
            dict_str = s_cleaned.replace("'", '"')
            obj = json.loads(dict_str)
            if isinstance(obj, dict):
                return [str(k).strip().strip('"').strip("'") 
                        for k in obj.keys() if str(k).strip().lower() not in {"", "nan", "null", "none"}]
        except:
            # 정규식으로 키 추출 시도
            try:
                keys = re.findall(r'["\']?([^"\':,]+)["\']?\s*:', s_cleaned)
                if keys:
                    return [k.strip().strip('"').strip("'") for k in keys if k.strip()]
            except:
                pass
    
    tokens = re.split(r'[,\|;\/\n\r\t]+', s_cleaned)
    return [t.strip().strip('"').strip("'")
            for t in tokens if t and t.strip().lower() not in {"", "nan", "null", "none"}]

def to_float(x, default=0.0):
    try:
        v = pd.to_numeric(x, errors="coerce")
        return float(v) if pd.notna(v) else default
    except Exception:
        return default

# ======================================================================
# Oracle Type Inference (name/digits heuristics)
# ======================================================================
CODEY_NAME_HINT = re.compile(r"(code|id|no|key)$", re.IGNORECASE)

def _safe_to_numeric(series):
    try:
        return pd.to_numeric(series, errors="coerce").dropna()
    except Exception:
        return pd.Series([], dtype=float)

def Get_Oracle_Type(series, column_name: str | None = None):
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
    fixed_length = s_all.str.len().nunique(dropna=True) == 1

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
            int_digits = parts.str[0].str.len().astype(int).max()
            frac_digits = parts.str[1].str.len().fillna(0).astype(int).max()
            return f"NUMBER({int(int_digits + frac_digits)},{int(frac_digits)})"

    maxlen = int(s_all.str.len().max())
    return f"VARCHAR2({maxlen})" if maxlen <= 4000 else "CLOB"

# ======================================================================
# 파일별 컬럼 분석
# ======================================================================
def create_datatype_df(filepath, code_type, extension):
    """단일 파일의 컬럼별 Pandas/Oracle 타입 분석"""
    try:
        if extension in ("csv", ".csv"):
            df = pd.read_csv(filepath, encoding="utf-8", low_memory=False)
        elif extension in ("xlsx", ".xlsx"):
            df = pd.read_excel(filepath)
        elif extension in ("pkl", ".pkl"):
            df = pd.read_pickle(filepath)
        else:
            raise ValueError(f"Unsupported file extension: {extension}")
    except Exception as e:
        print(f"파일 로드 실패: {filepath} → {e}")
        return []

    summary = []
    for col in df.columns:
        pandas_dtype = str(df[col].dtype)
        try:
            oracle_type = Get_Oracle_Type(df[col], col)
        except Exception as e:
            oracle_type = f"ERROR({e})"

        summary.append({
            "FilePath": str(filepath).replace('\\', '/'),
            "FileName": os.path.basename(filepath),
            "MasterType": code_type,
            "ColumnName": col,
            "DataType": pandas_dtype,
            "OracleType": oracle_type,
        })

    return summary

# ======================================================================
# 전체 분석
# ======================================================================
def DataType_Analysis(source_dir_list) -> pd.DataFrame:
    """모든 코드 파일에 대한 DataType 분석"""
    print("\n=== DataType 분석 시작 ===")

    output_dir = OUTPUT_DIR
    datatype_file = DATATYPE_FILE

    datatype_df = []

    for source_config in source_dir_list:
        source_subpath = str(source_config["source"]).lstrip("/\\")
        source_path = ROOT_PATH / source_subpath

        file_pattern = f"*.{source_config['extension'].lstrip('.')}"
        files = list(source_path.glob(file_pattern))

        if not files:
            print(f"No files found in {source_path}")
            continue

        for file in files:
            try:
                datatype = create_datatype_df(file, source_config["type"], file.suffix)
                datatype_df.extend(datatype)
            except Exception as e:
                print(f"파일 처리 오류: {file.name} → {e}")
                continue

    if not datatype_df:
        print("처리된 데이터가 없습니다.")
        return None

    return pd.DataFrame(datatype_df)
    # result_path = datatype_file
    # result_df.to_csv(result_path, index=False, encoding="utf-8-sig")

    # print(f"결과 저장 완료: {result_path}")
    # return 0
# ---------------- ValidData ----------------
def _read_valid_file(path: str, colname: str, strict_column: bool = True) -> list[str]:
    if not path: return []
    path = os.path.expanduser(os.path.expandvars(str(path).strip().strip('"').strip("'")))
    df = None
    for enc in ("utf-8-sig","cp949","utf-8"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc)
            break
        except Exception:
            continue
    if df is None:
        print(f"유효값 파일을 읽지 못했습니다: {path}")
        return []
    if strict_column and colname not in df.columns:
        print(f"'{os.path.basename(path)}'에 '{colname}' 컬럼이 없습니다. 건너뜀.")
        return []
    series = df[colname] if colname in df.columns else df.select_dtypes(include="object").iloc[:,0]
    vals = (series.dropna().astype(str).map(lambda s: s.strip().strip('"').strip("'")))
    return [v for v in vals if v and v.lower() not in {"nan","null","none"}]

def build_valid_map(df_v: pd.DataFrame, *, base_dir: str | None = None,
                    case_sensitive: bool = True, strict_file_column: bool = True) -> dict[str, set]:
    def norm(v: str) -> str:
        """문자열 정규화: 양쪽 모두 str().strip()으로 변환하여 "눈에 보이는 그대로" 비교"""
        v = str(v).strip() if v is not None else ""
        return v if case_sensitive else v.lower()
    valid_map: dict[str, set] = {}
    for _, r in df_v.iterrows():
        name = str(r.get("valid_name","")).strip()
        if not name: continue
        list_or_file = str(r.get("ListOrFile","List")).strip()
        raw = r.get("valid_list","")
        values: list[str] = []
        if list_or_file.lower() == "list":
            # JSON 보정: 파이썬 딕셔너리 문자열을 JSON으로 변환
            if raw is not None and isinstance(raw, str):
                json_str = str(raw).replace("'", '"')
                values = parse_jsonish_list(json_str)
            else:
                values = parse_jsonish_list(raw)
        elif list_or_file.lower() == "file":
            path = str(raw or "").strip()
            if base_dir and path and not os.path.isabs(path):
                path = os.path.join(base_dir, path)
            values = _read_valid_file(path, colname=name, strict_column=strict_file_column)
        else:
            print(f"알 수 없는 ListOrFile='{list_or_file}' (valid_name={name})")
        # 모든 값을 문자열로 정규화 (str().strip())
        values = [norm(v) for v in values if v]
        valid_map.setdefault(name, set()).update(values)
    return valid_map

# ---------------- RuleType helpers ----------------
FORMAT_MAX_VALUE = 4000
FORMAT_AVG_LENGTH = 100

def is_timestamp(pattern, pattern_cnt):
    return (pattern in ['nnnn-nn-nn nn:nn:nn','nnnn-nn-nn nn:nn:nn.nnnnnn','nnnn-nn-nn nn:nn:nn.']
            and int(pattern_cnt) == 1)

def is_time(pattern, pattern_cnt):
    return (pattern in ['nn:nn.n','nn:nn:nn','nn:nn:nn.nnnnnn','nn:nn:nn.']
            and int(pattern_cnt) == 1)

def is_datechar(pattern, median):
    return (pattern in ['nnnnnnnn','nnnn-nn-nn','nnnn/nn/nn','nnnnKnnKnnK','nnnn.nn.nn','nnnn. n. nn.']
            and validate_date(str(median)))

def is_yearmonth(pattern, median):
    return (pattern in ['nnnnnn','nnnn-nn','nnnn/nn','nnnn.nn','nnnnKnnK']
            and validate_yearmonth(str(median)))

def is_yymmdd(pattern, median):
    return (pattern in ['nnnnnn','nn-nn-nn','nn/nn/nn','nn.nn.nn','nn.nn.nn.']
            and validate_YYMMDD(str(median)))

def is_year(pattern, median, mode_string):
    if pattern == 'nnnn' and median:
        try:
            mode_val = float(mode_string)
            return 1990 < mode_val < 2999
        except Exception:
            return False
    return False

def is_latitude(pattern, median):
    return (pattern in ['nn.nnnn','nn.nnnnn','nn.nnnnnn','nn.nnnnnnn','nn.nnnnnnnn']
            and validate_latitude(median))

def is_longitude(pattern, median):
    return (pattern in ['nnn.nnnn','nnn.nnnnn','nnn.nnnnnn','nnn.nnnnnnn','nnn.nnnnnnnn']
            and validate_longitude(median))

def is_tel(pattern, top10, top_n: int = 10) -> bool: 
    def _ensure_list(x):
        if isinstance(x, (list, tuple, set)):
            return [str(v) for v in x]
        return parse_jsonish_list(x)  # 문자열이면 JSON/구분자 파싱

    tel_patterns = [
        'nnn-nnn-nnnn','nn-nnnn-nnnn','nn-nnn-nnnn','nnn-nnnn',
        'nnnn-nnnn','nnnnnnn','nnnnnnnn','nnnnnnnnnn'
    ]
    if pattern not in tel_patterns:
        return False

    values = _ensure_list(top10)
    top_values = [v for v in values if v != "__OTHER__"][:top_n]
    if not top_values:
        return False

    # 상위 값 중 전화번호로 판정되는 비율이 80% 이상이면 TEL
    valid_tel_count = sum(1 for v in top_values if validate_tel(v))
    return (valid_tel_count / len(top_values)) >= 0.9


def is_cellphone(pattern, median): return (pattern in ['nnn-nnnn-nnnn','nnnnnnnnnnn'] and validate_cellphone(median))
def is_car_number(pattern, pattern_cnt): return pattern in ['KKnnKnnnn','nnKnnnn','nnnKnnnn']
def is_company(pattern, pattern_cnt):    return (pattern in ['(K)KKKK','(K)KKKKK','(K)KKKKKK'] and int(pattern_cnt) > 5)
def is_email(pattern): return ('@' in pattern and 1 <= pattern.count('.') <= 2)
def is_url(pattern):   return ('://' in pattern and pattern.count('.') >= 1)
def is_address(pattern, median): return (len(pattern) >= 8 and pattern.count('K') >= 6 and pattern.count(' ') >= 2 and validate_address(median))

def is_flag(pattern, pattern_cnt, median, min_string, max_string):
    if (pattern == 'A' and min_string == 'N' and max_string == 'Y' and int(pattern_cnt) == 1): return 'YN_Flag'
    if (pattern == 'n' and min_string == '0' and max_string == '1' and int(pattern_cnt) == 1): return 'True_False_Flag'
    if (pattern in ['A','a'] and int(pattern_cnt) == 1): return 'Alpha_Flag'
    if (pattern == 'n' and int(pattern_cnt) == 1):       return 'Num_Flag'
    if (pattern == 'K' and int(pattern_cnt) == 1):       return 'Kor_Flag'
    if ((pattern == 'KKK') and int(pattern_cnt) < 6):    return 'KOR_NAME'
    return None

def is_text(pattern, max_length, pattern_cnt):
    return (int(max_length) > FORMAT_MAX_VALUE or len(pattern) > FORMAT_AVG_LENGTH or int(pattern_cnt) > 20)

def is_sequence(min_string, max_string, unique_count):
    try:
        if min_string not in (None,'') and max_string not in (None,''):
            a = float(min_string); b = float(max_string)
            if a.is_integer() and b.is_integer():
                ai = int(a); bi = int(b)
                expected = bi - ai + 1
                return expected > 0 and expected == int(unique_count)
    except Exception:
        pass
    return False

def safe_int(x, default=0):
    try:
        if pd.isna(x) or x == '': return default
        return int(float(x))
    except Exception:
        return default

def Determine_Rule_Type(r: pd.Series) -> str:
    try:
        pattern     = str(r.get('Format','') or '')
        pattern_cnt = safe_int(r.get('FormatCnt',0), 0)
        median      = str(r.get('FormatMedian','') or r.get('Median','') or r.get('MedianString','') or '')
        mode_string = str(r.get('FormatMode','') or r.get('ModeString','') or '')
        top10       = str(r.get('Top10','') or '')
        min_string  = str(r.get('FormatMin','') or r.get('MinString','') or '')
        max_string  = str(r.get('FormatMax','') or r.get('MaxString','') or '')
        max_length  = safe_int(r.get('LenMax',0), 0)
        unique_cnt  = safe_int(r.get('UniqueCnt',0), 0)
        value_cnt   = safe_int(r.get('ValueCnt',0), 0)
        has_alpha   = safe_int(r.get('HasAlpha',0), 0)
        has_num     = safe_int(r.get('HasNum',0), 0)
        has_kor     = safe_int(r.get('HasKor',0), 0)
        has_special = safe_int(r.get('HasSpecial',0), 0)
        unique_percent = float(r.get('Unique(%)',0))

        if max_length > FORMAT_MAX_VALUE: return 'CLOB'
        if len(pattern) == 0:            return 'NULL'

        if is_timestamp(pattern, pattern_cnt):      return 'TIMESTAMP'
        if is_time(pattern, pattern_cnt):           return 'TIME'
        if is_yymmdd(pattern, median):              return 'YYMMDD'
        if is_datechar(pattern, median):            return 'DATECHAR'
        if is_yearmonth(pattern, median):           return 'YEARMONTH'
        if is_year(pattern, median, mode_string):   return 'YEAR'

        if is_latitude(pattern, median):            return 'LATITUDE'
        if is_longitude(pattern, median):           return 'LONGITUDE'

        if is_tel(pattern, top10, 10) and unique_percent != 100 and has_alpha == 0 and has_kor == 0: return 'TEL'
        if is_cellphone(pattern, median) and has_alpha == 0 and has_kor == 0: return 'CELLPHONE'
        if is_car_number(pattern, pattern_cnt):     return 'CAR_NUMBER'
        if is_company(pattern, pattern_cnt):        return 'COMPANY'

        if is_email(pattern): return 'EMAIL'
        if is_url(pattern):   return 'URL'

        if pattern_cnt > 0 and pattern[:1] == 'K':
            if is_address(pattern, median):         return 'ADDRESS'
            if is_text(pattern, max_length, pattern_cnt): return 'Text'

        if pattern_cnt > 0:
            flag_type = is_flag(pattern, pattern_cnt, median, min_string, max_string)
            if flag_type: return flag_type
            if is_sequence(min_string, max_string, unique_cnt): return 'SEQUENCE'
            if unique_cnt == 1: return 'SINGLE VALUE'
        return ''
    except Exception as e:
        print(f"Error in Determine_Rule_Type: {e}")
        return ''

# ---------------- Env ----------------
def build_env(row: pd.Series, valid_map: dict, *, rule_type_auto: str = "") -> dict:
    env = {c: row[c] for c in row.index}

    # 숫자형 캐스팅
    for c in ("FormatCnt","FormatLength","HasBlank","LenCnt","LenMin","LenMax",
              "ValueCnt","SampleRows","UniqueCnt"):
        env[c] = to_float(row.get(c), 0.0)

    # FormatBlankCnt 계산 (Format 문자열에서 공백 개수)
    format_str = str(row.get("Format",""))
    env["FormatBlankCnt"] = format_str.count(' ')
    
    # FormatLength가 없으면 Format 길이로 계산
    if "FormatLength" not in env or env["FormatLength"] == 0:
        env["FormatLength"] = len(format_str)

    # Top10 계열은 list로 파싱 (JSON 보정: 홑따옴표 -> 쌍따옴표)
    for c in row.index:
        if str(c).endswith("Top10"):
            raw_value = row.get(c)
            # 파이썬 딕셔너리 문자열을 JSON으로 변환
            if raw_value is not None and isinstance(raw_value, str):
                # { '이': 50 } -> { "이": 50 } 변환
                json_str = str(raw_value).replace("'", '"')
                parsed = parse_jsonish_list(json_str)
            else:
                parsed = parse_jsonish_list(raw_value)
            env[c] = parsed
            # 디버그: Top10 데이터가 비어있으면 경고
            if DEBUG_MODE and len(parsed) == 0 and pd.notna(raw_value) and str(raw_value).strip() not in {"", "nan", "null", "none"}:
                print(f"      Top10 파싱 실패: {c} = {raw_value}")

    # 주요 문자열들
    env["Format"]        = format_str
    env["MedianString"]  = str(row.get("FormatMedian","") or row.get("Median","") or row.get("MedianString","") or "")
    env["ModeString"]    = str(row.get("FormatMode","") or row.get("ModeString","") or "")
    env["MinString"]     = str(row.get("FormatMin","") or row.get("MinString","") or "")
    env["MaxString"]     = str(row.get("FormatMax","") or row.get("MaxString","") or "")
    
    # Top10도 파싱된 리스트로 설정 (JSON 보정 적용)
    top10_raw = row.get("Top10")
    if top10_raw is not None and isinstance(top10_raw, str):
        # 파이썬 딕셔너리 문자열을 JSON으로 변환: { '이': 50 } -> { "이": 50 }
        json_str = str(top10_raw).replace("'", '"')
        env["Top10"] = parse_jsonish_list(json_str)
    else:
        env["Top10"] = parse_jsonish_list(top10_raw) if top10_raw is not None else []
    
    env["RuleTypeAuto"]  = rule_type_auto  # 규칙에서 바로 사용 가능

    # 유효값 집합
    for name, s in valid_map.items():
        env[name] = s
    return env

# ---------------- Safe eval ----------------
ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp,
    ast.And, ast.Or, ast.BitAnd, ast.BitOr, ast.Not, ast.Invert,
    ast.Compare, ast.Name, ast.Load, ast.Constant, ast.Num,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.USub, ast.UAdd, ast.Add, ast.Sub,
    ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Call, ast.Attribute,
)

# 기존 함수 대체
def _membership_ratio(left, right) -> float:
    """
    멤버십 비율 계산 (문자열 정규화 적용)
    - 양쪽 모두 str().strip()으로 변환하여 "눈에 보이는 그대로" 비교
    - "02"와 2를 다르게 인식하도록 처리
    """
    # 컨테이너 대상: set/list/tuple
    if isinstance(right, (set, list, tuple)):
        # right의 모든 값을 문자열로 정규화 (strip 적용)
        rset = set(str(x).strip() for x in right if x is not None)
        if isinstance(left, (list, tuple, set)):
            # left의 모든 값을 문자열로 정규화
            L = [str(x).strip() for x in left if x is not None]
            if not L:
                return 0.0
            # 정규화된 값으로 비교
            matches = sum(1 for x in L if x in rset)
            return matches / len(L) if L else 0.0
        # left가 단일 값인 경우
        left_str = str(left).strip() if left is not None else ""
        return 1.0 if left_str in rset else 0.0

    # 문자열 대상: 'left'가 'right'의 부분문자열이어야 함
    if isinstance(right, str):
        right_str = right.strip()
        if isinstance(left, str):
            left_str = left.strip()
            return 1.0 if left_str in right_str else 0.0
        if isinstance(left, (list, tuple, set)):
            L = [str(x).strip() for x in left if x is not None]
            if not L:
                return 0.0
            matches = sum(1 for x in L if x in right_str)
            return matches / len(L) if L else 0.0

    return 0.0

class SafeEval(ast.NodeVisitor):
    def __init__(self, env: dict, threshold: float, valid_map: dict, func_registry: dict):
        self.env = env
        self.threshold = threshold
        self.valid_map = valid_map
        self.funcs = func_registry
        self._ratios: list[float] = []

    def visit(self, node):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"Disallowed node: {type(node).__name__}")
        return super().visit(node)

    def visit_Expression(self, node): return self.visit(node.body)
    def visit_Constant(self, node):   return node.value
    def visit_Name(self, node):
        if node.id in self.env: return self.env[node.id]
        raise NameError(f"Unknown name: {node.id}")

    def visit_UnaryOp(self, node):
        v = self.visit(node.operand)
        if isinstance(node.op, (ast.Not, ast.Invert)): return not bool(v)
        if isinstance(node.op, ast.USub): return -float(v)
        if isinstance(node.op, ast.UAdd): return +float(v)
        raise ValueError("Bad unary")

    def visit_BinOp(self, node):
        L = self.visit(node.left); R = self.visit(node.right)
        if   isinstance(node.op, ast.BitAnd):  return bool(L) and bool(R)
        elif isinstance(node.op, ast.BitOr):   return bool(L) or bool(R)
        elif isinstance(node.op, ast.Add):     return L + R
        elif isinstance(node.op, ast.Sub):     return L - R
        elif isinstance(node.op, ast.Mult):    return L * R
        elif isinstance(node.op, ast.Div):     return L / R
        elif isinstance(node.op, ast.FloorDiv):return L // R
        elif isinstance(node.op, ast.Mod):     return L % R
        raise ValueError("Bad binop")

    def visit_BoolOp(self, node):
        if isinstance(node.op, ast.And):
            for v in node.values:
                if not bool(self.visit(v)): return False
            return True
        if isinstance(node.op, ast.Or):
            for v in node.values:
                if bool(self.visit(v)): return True
            return False
        raise ValueError("Bad boolop")

    def visit_Call(self, node):
        # --- len()/size() 허용 ---
        if isinstance(node.func, ast.Name) and node.func.id in {"len", "size"}:
            if len(node.args) != 1:
                raise ValueError("len(x)는 인자 1개만 허용합니다.")
            x = self.visit(node.args[0])
            if isinstance(x, (list, tuple, set, str)):
                return len(x)
            return 0

        # --- safe helper whitelist: 룰에서 직접 호출 허용 ---
        safe_fns = {
            "is_tel": is_tel,
            "is_datechar": is_datechar,
            "is_yearmonth": is_yearmonth,
            "is_yymmdd": is_yymmdd,
            "is_timestamp": is_timestamp,
            "is_time": is_time,
            "is_latitude": is_latitude,
            "is_longitude": is_longitude,
            "is_email": is_email,
            "is_url": is_url,
        }
        if isinstance(node.func, ast.Name) and node.func.id in safe_fns:
            fn = safe_fns[node.func.id]
            args = [self.visit(a) for a in node.args]
            try:
                return bool(fn(*args))
            except TypeError as e:
                # 인자 개수/타입 오류를 친절히 표시
                raise ValueError(f"{node.func.id} 호출 인자가 올바르지 않습니다: {e}")

        # --- 문자열 메서드 count:  "aaa".count("a")
        if isinstance(node.func, ast.Attribute) and node.func.attr == "count":
            obj = self.visit(node.func.value)
            args = [self.visit(a) for a in node.args]
            if not isinstance(obj, str) or len(args) != 1 or not isinstance(args[0], str):
                raise ValueError("count()는 문자열.count('서브스트링')만 허용합니다.")
            return obj.count(args[0])

        # --- 함수형 count(x, sub)
        if isinstance(node.func, ast.Name) and node.func.id == "count":
            if len(node.args) != 2:
                raise ValueError("count(x, sub)는 2개의 인자만 허용합니다.")
            x   = self.visit(node.args[0])
            sub = self.visit(node.args[1])
            if not isinstance(sub, str):
                raise ValueError("count(x, sub)에서 sub는 문자열이어야 합니다.")
            if isinstance(x, str):
                return x.count(sub)
            if isinstance(x, (list, tuple, set)):
                return sum(1 for v in x if str(v) == sub)
            return 0

        raise ValueError("허용되지 않은 호출입니다.")


    def visit_Compare(self, node):
        left_val = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right_val = self.visit(comp)
            if isinstance(op, (ast.In, ast.NotIn)):
                if isinstance(right_val, str) and right_val in self.valid_map:
                    target = self.valid_map[right_val]
                else:
                    target = right_val
                # left_val도 정규화 (리스트인 경우 각 요소를 str().strip()으로 변환)
                if isinstance(left_val, (list, tuple, set)):
                    normalized_left = [str(x).strip() if x is not None else "" for x in left_val]
                else:
                    normalized_left = str(left_val).strip() if left_val is not None else ""
                
                ratio = _membership_ratio(normalized_left, target)
                self._ratios.append(ratio)
                ok = (ratio >= self.threshold)
                ok = ok if isinstance(op, ast.In) else (not ok)
            else:
                L, R = left_val, right_val
                try:
                    Lf = float(L); Rf = float(R)
                    if   isinstance(op, ast.Eq):    ok = (Lf == Rf)
                    elif isinstance(op, ast.NotEq): ok = (Lf != Rf)
                    elif isinstance(op, ast.Gt):    ok = (Lf >  Rf)
                    elif isinstance(op, ast.GtE):   ok = (Lf >= Rf)
                    elif isinstance(op, ast.Lt):    ok = (Lf <  Rf)
                    elif isinstance(op, ast.LtE):   ok = (Lf <= Rf)
                    else: raise ValueError("Bad compare")
                except Exception:
                    if   isinstance(op, ast.Eq):    ok = (str(L) == str(R))
                    elif isinstance(op, ast.NotEq): ok = (str(L) != str(R))
                    elif isinstance(op, ast.Gt):    ok = (str(L) >  str(R))
                    elif isinstance(op, ast.GtE):   ok = (str(L) >= str(R))
                    elif isinstance(op, ast.Lt):    ok = (str(L) <  str(R))
                    elif isinstance(op, ast.LtE):   ok = (str(L) <= str(R))
                    else: raise ValueError("Bad compare")
            if not ok: return False
            left_val = right_val
        return True

def eval_expr(expr: str, env: dict, valid_map: dict, threshold: float, func_registry: dict, debug=False):
    txt = (expr or "").strip()
    if txt == "" or txt.lower() in {"nan","na","none"}:
        return True, []
    
    # 구문 오류 자동 수정 시도 (괄호 불일치)
    original_txt = txt
    # 괄호 불일치 수정: `| Format ==` -> `| (Format ==`
    txt = re.sub(r'\|\s*Format\s*==', r'| (Format ==', txt)
    # 닫는 괄호 추가: `Format == "KKK") | Format ==` -> `Format == "KKK") | (Format ==`
    txt = re.sub(r'\)\s*\|\s*Format\s*==', r') | (Format ==', txt)
    
    if txt != original_txt and debug:
        print(f"      구문 자동 수정: {original_txt} -> {txt}")
    
    try:
        tree = ast.parse(txt, mode="eval")
        ev = SafeEval(env, threshold=threshold, valid_map=valid_map, func_registry=func_registry)
        ok = bool(ev.visit(tree))
        if debug:
            print(f"      평가 결과: {ok}, ratios: {ev._ratios}, threshold: {threshold}")
            if ev._ratios:
                print(f"        ratio 상세: {[f'{r:.3f}' for r in ev._ratios]}")
        return ok, ev._ratios
    except SyntaxError as e:
        if debug:
            print(f"      구문 오류: {e} (표현식: {txt})")
        return False, []
    except Exception as e:
        if debug:
            print(f"      평가 오류: {e} (표현식: {txt})")
            # env에 있는 주요 변수들 출력
            print(f"        env 주요 변수: Format={env.get('Format', 'N/A')}, FormatCnt={env.get('FormatCnt', 'N/A')}")
            if 'Top10' in env:
                print(f"        Top10 길이: {len(env.get('Top10', []))}")
        return False, []

# ---------------- RuleType 산출 ----------------
def apply_rules_and_type(dt: pd.DataFrame, ff: pd.DataFrame, rd: pd.DataFrame, vd: pd.DataFrame, threshold: float) -> pd.DataFrame:
    valid_map = build_valid_map(vd)
    print(f"ValidData 맵 생성 완료: {len(valid_map)}개 항목")
    if DEBUG_MODE:
        print(f"[DEBUG] ValidData 맵 내용:")
        for key, value_set in list(valid_map.items())[:10]:  # 최대 10개만 출력
            print(f"  {key}: {len(value_set)}개 - {list(value_set)[:5] if len(value_set) > 5 else list(value_set)}")

    # 함수 화이트리스트 레지스트리
    FUNC = {
        "is_datechar":  lambda fmt, med: is_datechar(str(fmt), str(med)),
        "is_yearmonth": lambda fmt, med: is_yearmonth(str(fmt), str(med)),
        "is_yymmdd":    lambda fmt, med: is_yymmdd(str(fmt), str(med)),
        "is_year":      lambda fmt, med, mode="": is_year(str(fmt), str(med), str(mode)),
        "is_latitude":  lambda fmt, med: is_latitude(str(fmt), str(med)),
        "is_longitude": lambda fmt, med: is_longitude(str(fmt), str(med)),
        "is_tel": lambda *args: is_tel(
            str(args[0]) if len(args) > 0 else "",
            args[1]      if len(args) > 1 else "",
            int(args[2]) if len(args) > 2 else 10
        ),
        "is_cellphone": lambda fmt, med: is_cellphone(str(fmt), str(med)),
        "is_car_number":lambda fmt, cnt=0: is_car_number(str(fmt), to_float(cnt,0)),
        "is_company":   lambda fmt, cnt=0: is_company(str(fmt), to_float(cnt,0)),
        "is_email":     lambda fmt: is_email(str(fmt)),
        "is_url":       lambda fmt: is_url(str(fmt)),
        "is_address":   lambda fmt, med: is_address(str(fmt), str(med)),
        # 대안: TypeIs("DATECHAR") 는 SafeEval 안에서 처리
    }

    # dt와 ff를 먼저 병합하여 모든 컬럼 정보를 유지
    # 병합 키 확인 및 로깅
    # print(f"병합 전 - dt: {len(dt)}행, ff: {len(ff)}행")
    if len(dt) == 0:
        print("DataType 파일이 비어있습니다!")
        return pd.DataFrame()
    if len(ff) == 0:
        print("FileFormat 파일이 비어있습니다!")
        return pd.DataFrame()
    
    # 병합 키 확인
    merge_keys = ["FilePath","FileName","ColumnName", "MasterType"]
    missing_keys_dt = [k for k in merge_keys if k not in dt.columns]
    missing_keys_ff = [k for k in merge_keys if k not in ff.columns]
    if missing_keys_dt:
        print(f"DataType에 병합 키가 없습니다: {missing_keys_dt}")
        print(f"DataType 컬럼: {list(dt.columns)}")
    if missing_keys_ff:
        print(f"FileFormat에 병합 키가 없습니다: {missing_keys_ff}")
        print(f"FileFormat 컬럼: {list(ff.columns)}")
    
    # FilePath 정규화: 경로 구분자를 통일하고 절대 경로로 변환
    def normalize_path(path_str):
        """경로를 정규화하여 일치시킴"""
        if pd.isna(path_str) or path_str == '':
            return path_str
        path_str = str(path_str)
        # 백슬래시를 슬래시로 변환
        path_str = path_str.replace('\\', '/')
        # 상대 경로인 경우 절대 경로로 변환 시도
        if not os.path.isabs(path_str):
            # ROOT_PATH 기준으로 절대 경로 생성
            abs_path = (ROOT_PATH / path_str).resolve()
            return str(abs_path).replace('\\', '/')
        return path_str
    
    # FilePath 정규화
    dt_normalized = dt.copy()
    ff_normalized = ff.copy()
    
    if 'FilePath' in dt_normalized.columns:
        dt_normalized['FilePath'] = dt_normalized['FilePath'].apply(normalize_path)
    if 'FilePath' in ff_normalized.columns:
        ff_normalized['FilePath'] = ff_normalized['FilePath'].apply(normalize_path)
    
    # MasterType이 다를 수 있으므로, 먼저 FilePath, FileName, ColumnName으로 병합 시도
    # MasterType은 나중에 처리
    primary_keys = ["FilePath", "FileName", "ColumnName"]
    
    # MasterType이 없는 경우 기본값 설정
    if 'MasterType' not in dt_normalized.columns:
        dt_normalized['MasterType'] = 'Master'
    if 'MasterType' not in ff_normalized.columns:
        ff_normalized['MasterType'] = 'Master'
    
    # 먼저 primary_keys로 병합 시도
    out = pd.merge(dt_normalized, ff_normalized, on=primary_keys, how="inner", suffixes=('_dt', '_ff'))
    
    # MasterType이 양쪽에 있는 경우, dt의 MasterType을 우선 사용
    if 'MasterType_dt' in out.columns and 'MasterType_ff' in out.columns:
        out['MasterType'] = out['MasterType_dt'].fillna(out['MasterType_ff'])
        out = out.drop(columns=['MasterType_dt', 'MasterType_ff'])
    elif 'MasterType_dt' in out.columns:
        out['MasterType'] = out['MasterType_dt']
        out = out.drop(columns=['MasterType_dt'])
    elif 'MasterType_ff' in out.columns:
        out['MasterType'] = out['MasterType_ff']
        out = out.drop(columns=['MasterType_ff'])
    
    # print(f"병합 후 - out: {len(out)}행")
    
    if len(out) == 0:
        print("병합 결과가 비어있습니다! dt와 ff의 병합 키가 일치하지 않을 수 있습니다.")
        print(f"dt 샘플 (첫 3행):")
        if len(dt) > 0:
            for key in merge_keys:
                if key in dt.columns:
                    print(f"  {key}: {dt[key].unique()[:5] if len(dt) > 0 else []}")
        print(f"ff 샘플 (첫 3행):")
        if len(ff) > 0:
            for key in merge_keys:
                if key in ff.columns:
                    print(f"  {key}: {ff[key].unique()[:5] if len(ff) > 0 else []}")
        return pd.DataFrame()
    
    matched_rules_col, matched_scores_list_col = [], []
    match_score_avg_col, max_score_col, rule_type_col = [], [], []
    
    print(f"총 {len(out)}개 컬럼에 대해 {len(rd)}개 규칙 평가 시작")
    if DEBUG_MODE:
        print(f"[DEBUG] 디버그 모드 활성화 (최대 {DEBUG_MAX_COLUMNS}개 컬럼 디버그)")

    debug_count = 0
    for idx, (_, row) in enumerate(out.iterrows()):
        col_name = row.get('ColumnName', f'Column_{idx}')
        file_name = row.get('FileName', 'Unknown')
        
        # 디버그 모드일 때만 상세 로그
        is_debug = DEBUG_MODE and (DEBUG_MAX_COLUMNS == 0 or debug_count < DEBUG_MAX_COLUMNS)
        
        if is_debug:
            print(f"\n[DEBUG] 컬럼 {idx+1}/{len(out)}: {file_name} > {col_name}")
            print(f"  Format: {row.get('Format', 'N/A')}, FormatCnt: {row.get('FormatCnt', 'N/A')}")
        
        # RuleType 먼저 산출하고 env에 넣어 규칙에서 사용 가능
        rule_type = Determine_Rule_Type(row)
        rule_type_col.append(rule_type)
        
        if is_debug:
            print(f"  자동 RuleType: {rule_type}")

        env = build_env(row, valid_map, rule_type_auto=rule_type)

        pairs = []
        rule_evaluated = 0
        for rule_idx, (_, r) in enumerate(rd.iterrows()):
            rn    = str(r.get("RuleName","") or "")
            rule1 = str(r.get("rule1","") or "")
            rule2 = str(r.get("rule2","") or "")
            
            rule_evaluated += 1

            # rule1 평가
            ok1 = False
            rule1_error = None
            try:
                ok1, _ = eval_expr(rule1, env, valid_map, threshold, FUNC, debug=is_debug)
            except Exception as e:
                ok1 = False
                rule1_error = str(e)
                if is_debug:
                    print(f"  규칙 '{rn}' rule1 평가 오류: {e}")

            # rule2 평가 (비어있으면 통과)
            ok2 = False
            score = 0.0
            rule2_error = None
            if rule2.strip() == "" or rule2.strip().lower() in {"nan","na","none"}:
                ok2, score = True, 1.0
            else:
                try:
                    ok2, ratios = eval_expr(rule2, env, valid_map, threshold, FUNC, debug=is_debug)
                    score = (sum(ratios)/len(ratios)) if ratios else 1.0
                except Exception as e:
                    ok2, score = False, 0.0
                    rule2_error = str(e)
                    if is_debug:
                        print(f"  규칙 '{rn}' rule2 평가 오류: {e}")

            if is_debug:
                print(f"  규칙 '{rn}' ({rule_idx+1}/{len(rd)}): rule1={ok1}, rule2={ok2} (score={score:.4f})")
                if rule1:
                    print(f"    rule1: {rule1}")
                if rule2 and rule2.strip() not in {"", "nan", "na", "none"}:
                    print(f"    rule2: {rule2}")
                # rule2가 실패한 경우 상세 정보 출력
                if not ok2 and rule2.strip() not in {"", "nan", "na", "none"}:
                    # 관련 Top10 데이터 확인
                    for key in ["Top10", "First1Top10", "First2Top10", "First3Top10", "Last1Top10", "Last2Top10", "Last3Top10"]:
                        if key in env and env[key]:
                            print(f"      {key}: {len(env[key])}개 항목 - {env[key][:3] if len(env[key]) > 3 else env[key]}")
                    
                    # rule2에서 사용된 valid_map 키 확인
                    if ' in ' in rule2:
                        # "First3Top10 in 유효CELLPHONE" 같은 패턴에서 valid_map 키 추출
                        import re as re_module
                        in_matches = re_module.findall(r'(\w+)\s+in\s+(\S+)', rule2)
                        for left_key, right_key in in_matches:
                            if right_key in valid_map:
                                valid_set = valid_map[right_key]
                                print(f"      valid_map['{right_key}']: {len(valid_set)}개 항목 - {list(valid_set)[:5] if len(valid_set) > 5 else list(valid_set)}")
                                # left_key의 실제 값과 비교
                                if left_key in env:
                                    left_values = env[left_key] if isinstance(env[left_key], (list, tuple, set)) else [env[left_key]]
                                    print(f"      비교: {left_key}={left_values[:3]} vs {right_key}={list(valid_set)[:3]}")
                                    # 일치하는 항목 찾기
                                    matches = [v for v in left_values if str(v).strip() in valid_set]
                                    if matches:
                                        print(f"        일치 항목: {matches[:3]}")
                                    else:
                                        print(f"        일치 항목 없음 (left 값들이 valid_set에 없음)")
                            else:
                                print(f"      valid_map에 '{right_key}' 키가 없습니다.")

            if ok1 and ok2:
                pairs.append((rn, float(score)))
                if is_debug:
                    print(f"  ✓ 규칙 매칭 성공: {rn} (점수: {score:.4f})")

        if is_debug:
            print(f"  총 {rule_evaluated}개 규칙 평가, {len(pairs)}개 매칭")
            if len(pairs) == 0:
                print(f"  ⚠ 매칭된 규칙 없음 (Format: {row.get('Format', 'N/A')}, RuleType: {rule_type})")

        if pairs:
            pairs.sort(key=lambda x: x[1], reverse=True)  # 점수 내림차순
            names  = [p[0] for p in pairs]
            scores = [p[1] for p in pairs]
            matched_rules_col.append("; ".join(names))
            matched_scores_list_col.append("; ".join(f"{s:.4f}" for s in scores))
            match_score_avg_col.append(round(float(np.mean(scores)), 4))
            max_score_col.append(round(float(np.max(scores)), 4))
        else:
            matched_rules_col.append("")
            matched_scores_list_col.append("")
            match_score_avg_col.append("")
            max_score_col.append(0.0)
        
        if is_debug:
            debug_count += 1

    out = out.assign(
        Rule             = matched_rules_col if any(matched_rules_col) else rule_type_col,
        RuleType         = rule_type_col,
        MatchedRule      = matched_rules_col,
        MatchedScoreList = matched_scores_list_col,
        MatchScoreAvg    = match_score_avg_col,
        MatchScoreMax    = max_score_col,
    ).sort_values(by=["MatchScoreMax","MatchScoreAvg"], ascending=[False, False]).reset_index(drop=True)

    # 통계 출력
    matched_count = sum(1 for x in matched_rules_col if x)
    unmatched_count = len(matched_rules_col) - matched_count
    # print(f"\n규칙 매칭 통계:")
    # print(f"  - 총 컬럼 수: {len(out)}")
    if len(out) > 0:
        print(f"  - 규칙 매칭 성공: {matched_count} ({matched_count/len(out)*100:.1f}%)")
        print(f"  - 규칙 매칭 실패: {unmatched_count} ({unmatched_count/len(out)*100:.1f}%)")
    
    if unmatched_count > 0 and DEBUG_MODE:
        print(f"\n매칭 실패한 컬럼 샘플 (최대 5개):")
        unmatched_samples = []
        for idx, (_, row) in enumerate(out.iterrows()):
            if not matched_rules_col[idx]:
                unmatched_samples.append({
                    'FileName': row.get('FileName', 'N/A'),
                    'ColumnName': row.get('ColumnName', 'N/A'),
                    'Format': row.get('Format', 'N/A'),
                    'RuleType': rule_type_col[idx]
                })
                if len(unmatched_samples) >= 5:
                    break
        for sample in unmatched_samples:
            print(f"  - {sample['FileName']} > {sample['ColumnName']}: Format={sample['Format']}, RuleType={sample['RuleType']}")

    return out

def MasterRuleDataType() -> pd.DataFrame:
    """모든 코드 파일에 대한 Rule & DataType 분석"""
    print("=== Rule & DataType 분석 시작 ===")

    # --- 안전한 경로 결합 ---
    datatype_f = DATATYPE_FILE
    fileformat_f = FORMAT_FILE
    rule_definition_f = RULE_DEFINITION_FILE
    rule_definition_validdata_f = RULE_DEFINITION_VALIDDATA_FILE

    # 파일 존재 여부 확인
    required_files = {
        "DataType": datatype_f,
        "FileFormat": fileformat_f,
        "RuleDefinition": rule_definition_f,
        "RuleDefinition_ValidData": rule_definition_validdata_f
    }
    
    missing_files = []
    for name, file_path in required_files.items():
        if not Path(file_path).exists():
            missing_files.append(f"{name}: {file_path}")
    
    if missing_files:
        print("필수 파일이 없습니다:")
        for msg in missing_files:
            print(f"  - {msg}")
        return None

    try:
        dt = read_csv_any(datatype_f)
        
        ff = read_csv_any(fileformat_f)
        
        rd = read_csv_any(rule_definition_f)
        if "Use_Flag" in rd.columns:
            rd = rd[rd["Use_Flag"] == "Y"].copy()
        else:
            print("  - Use_Flag 컬럼이 없어 모든 규칙을 사용합니다.")
        
        vd = read_csv_any(rule_definition_validdata_f)

        # print(f"규칙 적용 시작 (DataType: {len(dt)}행, FileFormat: {len(ff)}행)")
        res = apply_rules_and_type(dt, ff, rd, vd, threshold=0.30)

        return res
    except FileNotFoundError as e:
        print(f"파일을 찾을 수 없습니다: {e}")
        print(traceback.format_exc())
        return None
    except Exception as e:
        print(f"MasterRuleDataType 처리 중 오류: {e}")
        print(traceback.format_exc())
        return None

 #-----------------------------------------------------------------------
# Load CodeMapping File ( CodeFormat을 수행할 Source Folder Path )
#-----------------------------------------------------------------------
def load_codemapping_validate() -> list[dict]:
        try:    
            print(f"META_PATH: {META_PATH}")
            source_list = pd.read_csv(META_PATH)
            # source_list의 필수 컬럼 점검  ( execution_flag,type, source, extension 존재 여부)
            required_columns = ['execution_flag', 'type', 'source', 'extension']
            for col in required_columns:
                if col not in source_list.columns:
                    print(f"{META_PATH} 파일 구조 점검 : {col} 컬럼이 없습니다.")
                    return []
            
            filtered = source_list[source_list['execution_flag'] == 'Y']
            print(f"수행할 폴더 수: {len(filtered)} 개 ")
            
            return filtered.to_dict(orient='records')
        except Exception as e:
            print(f"{META_PATH} 파일 점검 : 메타데터 파일 읽기 실패: {e}")
            return []   
# ---------------- main ----------------
def main():
    """
    DataSense Rule & DataType 분석 메인 함수
    """
    start_time = time.time()
    
    try:
        print("=" * 60)
        print("DataSense Rule & DataType 분석 시작")
        print("=" * 60)
               
        source_list = load_codemapping_validate()
        if  source_list is None or len(source_list) == 0:
            print(f"메타 파일 점검 : {META_PATH}")
            return None

        datatype_df = DataType_Analysis(source_list)

        if datatype_df is None or len(datatype_df) == 0:
            print(f"DataType 분석 실패")
            return None
        else:
            # OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            datatype_df.to_csv(DATATYPE_FILE, index=False, encoding="utf-8-sig")
            print(f"DataType 결과: {DATATYPE_FILE} ({len(datatype_df)}행)")

        # MasterRuleDataType 분석
        rule_datatype_df = MasterRuleDataType()
        if rule_datatype_df is None or len(rule_datatype_df) == 0:
            print(f"MasterRuleDataType 분석 실패")
            return None
        else:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            rule_datatype_df.to_csv(RULEDATATYPE_FILE, index=False, encoding="utf-8-sig")
            print(f"Rule 결과: {RULEDATATYPE_FILE} ({len(rule_datatype_df)}행)")
        
        end_time = time.time()
        processing_time = end_time - start_time
        print("=" * 60)
        print(f"총 처리 시간: {processing_time:.2f}초")
        print("=" * 60)
        
    except Exception as e:
        print(f"MasterRuleDataType 오류 발생: {e}")
        print(traceback.format_exc())
        return None

if __name__ == "__main__":
    main()
