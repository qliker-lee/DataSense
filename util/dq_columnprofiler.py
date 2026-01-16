
import os
import re
import sys
import yaml
import time
import json
import traceback
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from multiprocessing import Pool, cpu_count
from collections import Counter

#---------------------------------------------------------------
# Constants 설정
#---------------------------------------------------------------
# --- [1. 경로 및 설정 관리] ---
ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

FORMAT_MAX_VALUE   = 1000   # Format 검사 최대 길이 한계
FORMAT_AVG_LENGTH  = 50     # 평균 길이 기준(문장형 텍스트 추정)

# 멀티프로세싱 관련 상수
MULTIPROCESSING_THRESHOLD = 1000  # 멀티프로세싱 사용 최소 데이터 수
#---------------------------------------------------------------
# Define Set Variables
#---------------------------------------------------------------
from typing import Iterable, Optional, Set, Dict, Tuple

# 프로젝트 루트 기준(Initializing_Main_Class 에서 넘겨줍니다)
DEFAULT_SIDO_CSV     = r"DS_Input/Reference/Sido.csv"
DEFAULT_SIGUNGU_CSV  = r"DS_Input/Reference/Sigungu.csv"
DEFAULT_KORNAME_CSV  = r"DS_Input/Reference/KorName.csv"
DEFAULT_COUNTRY_ISO3 = r"DS_Input/Reference/Country_ISO3.csv"

# --- 추가: 전역 세트 ---
YMD8_SET: Set[str] = set()    # 'YYYYMMDD' (숫자 8자리)
YYMMDD_SET: Set[str] = set()  # 'YYMMDD'   (숫자 6자리)

DEFAULT_ENCODINGS: Tuple[str, ...] = ("utf-8-sig", "cp949", "utf-8")

# --------------------------- 전역(필수) ---------------------------
SIDO_SET: Set[str] = set()
SIGUNGU_SET: Set[str] = set()
SIDO_TO_SIGUNGU: Dict[str, Set[str]] = {}   # (주의) '시도명.csv'와 '시군구명.csv'가 분리라면 대부분 비어있음
KOR_NAME_SET: Set[str] = set()              # 한국성씨(한 글자 성)
COUNTRY_ISO3_SET: Set[str] = set()          # ISO 3166-1 alpha-3

# 세종 특례: 시군구 생략 허용
_SIDO_SIGUNGU_OPTIONAL = {"세종특별자치시"}

# 시도 약칭 → 정식 명칭 보정 (데이터셋 표기와 맞추세요)
_SIDO_ALIASES = {
    "서울": "서울특별시", "서울시": "서울특별시",
    "부산": "부산광역시", "부산시": "부산광역시",
    "대구": "대구광역시", "대구시": "대구광역시",
    "인천": "인천광역시", "인천시": "인천광역시",
    "광주": "광주광역시", "광주시": "광주광역시",
    "대전": "대전광역시", "대전시": "대전광역시",
    "울산": "울산광역시", "울산시": "울산광역시",
    "세종": "세종특별자치시", "세종시": "세종특별자치시",
    "제주": "제주특별자치도", "제주도": "제주특별자치도",
    "경기": "경기도",
    "강원": "강원도",  # 데이터가 '강원특별자치도'면 여기서 바꾸세요
    "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도",
    "경북": "경상북도", "경남": "경상남도",
}

_SIDO_SUFFIX_RE = re.compile(r'(특별자치)?(광역)?(특별)?(자치)?(시|도)$')

#---------------------------------------------------------------
# Logging 설정
#---------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def log_info(msg): 
    logger.info(msg)

def log_error(msg): 
    logger.error(msg)

def log_warning(msg):
    logger.warning(msg)

#---------------------------------------------------------------
# Import user defined Modules   
#---------------------------------------------------------------
# try:
#     from util.dq_function import Get_Oracle_Type, Determine_Detail_Type
# except ImportError as e:
#     print(f"필수 모듈 로드 실패: {e}")
#     print(f"ROOT_PATH: {ROOT_PATH}")
#     print(f"sys.path: {sys.path[:3]}")  # 처음 3개만 출력
#     if __name__ == "__main__":
#         sys.exit(1)
#     raise

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
# IO & Utility Functions
# ======================================================================
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
# ======================================================================
# Determine_Detail_Type 함수
# ======================================================================
# --------------------------- 유효성 함수 ---------------------------
def validate_date(value) -> bool:
    """
    YYYYMMDD 유효성:
      1) 연월일.csv가 로드되어 YMD8_SET이 있으면 → '숫자만 추출한 앞 8자리'가 YMD8_SET에 있는지 비교
      2) 세트가 비어있으면(파일 없음) → 기존 datetime 기반 검증으로 폴백
    """
    s = str(value).strip()
    if s.endswith('.0'):
        s = s[:-2]

    digits = re.sub(r'[^0-9]', '', s)
    if len(digits) < 8:
        return False
    ymd = digits[:8]

    if YMD8_SET:
        return ymd in YMD8_SET

    # 폴백: 기존 로직
    try:
        y, m, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])
        if not (1 <= m <= 12 and 1 <= d <= 31):
            return False
        datetime(y, m, d)
        return 1900 <= y <= 9999
    except Exception:
        return False


def validate_YYMMDD_old(val: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", str(val)))

def validate_YYMMDD(value: str) -> bool:
    """
    YYMMDD 유효성:
      1) 연월일.csv가 로드되어 YYMMDD_SET이 있으면 → '숫자만 추출한 6자리'가 YYMMDD_SET에 있는지 비교
      2) 세트가 비어있으면 → 기존 %y%m%d 파싱으로 폴백
    """
    if value is None:
        return False
    s = str(value).strip()
    if s.endswith('.0'):
        s = s[:-2]

    digits = re.sub(r'[^0-9]', '', s)
    if len(digits) != 6:
        return False

    if YYMMDD_SET:
        return digits in YYMMDD_SET

    # 폴백: 기존 로직
    try:
        datetime.strptime(digits, "%y%m%d")
        return True
    except ValueError:
        return False

# def validate_date(value) -> bool:
#     try:
#         s = str(value).strip()
#         if s.endswith('.0'): s = s[:-2]
#         if s.isdigit() and len(s) == 8:
#             y, m, d = int(s[:4]), int(s[4:6]), int(s[6:8])
#         else:
#             nums = re.sub(r'[^0-9]', '', s)
#             if len(nums) < 8: return False
#             y, m, d = int(nums[:4]), int(nums[4:6]), int(nums[6:8])
#         if not (1 <= m <= 12 and 1 <= d <= 31): return False
#         datetime(y, m, d)
#         return 1900 <= y <= 9999
#     except Exception:
#         return False

def validate_yearmonth(value) -> bool:
    try:
        s = str(value)
        if s.endswith('.0'): s = s[:-2]
        nums = re.sub(r'[^0-9]', '', s)
        if len(nums) != 6: return False
        y, m = int(nums[:4]), int(nums[4:])
        return (1900 <= y <= 9999) and (1 <= m <= 12)
    except Exception:
        return False

# def validate_YYMMDD(value: str) -> bool:
#     if value is None: return False
#     s = str(value)
#     if s.endswith('.0'): s = s[:-2]
#     if not s.isdigit() or len(s) != 6: return False
#     try:
#         datetime.strptime(s, "%y%m%d"); return True
#     except ValueError:
#         return False

def validate_year(value) -> bool:
    try:
        s = str(value)
        if s.endswith('.0'): s = s[:-2]
        y = int(s)
        return 1900 <= y <= 2999
    except Exception:
        return False

def validate_latitude(value) -> bool:
    try:
        v = float(str(value).strip())
        return -90 <= v <= 90
    except Exception:
        return False

def validate_longitude(value) -> bool:
    try:
        v = float(str(value).strip())
        return -180 <= v <= 180
    except Exception:
        return False

# 국내 전화(유선/휴대폰 포함)
_KR_AREA3 = {'031','032','033','041','042','043','044','051','052','053','054','055','061','062','063','064'}

def validate_tel_old(val: str) -> bool:
    if not isinstance(val, str):  # 입력이 문자열이 아니면 False 리턴
        return False
    digits = re.sub(r"\D", "", val) # 숫자만 추출 ("-", " ", "(" 등 제거)
    n = len(digits) # 전체 자릿수 n 계산
    if n < 7 or n > 11: # 7자리 이상 11자리 이하만 유효
        return False
    if n in (7, 8): # 맨 앞자리가 2~9일 때만 허용 (0,1 제외)
        return digits[0] in "23456789"
    if digits.startswith("02"): # "02"로 시작하면 뒤는 7~8자리
        local = digits[2:]
        return len(local) in (7, 8) and local and local[0] not in {"0", "1"}
    if digits.startswith("010"):
        local = digits[3:]
        return bool(local) and local[0] not in {"0", "1"}
    if re.match(r"0[3-9][0-9]", digits):
        local = digits[3:]
        return len(local) in (7, 8) and local and local[0] not in {"0", "1"}
    return False

import re

def validate_tel(val: str) -> bool:
    """한국 전화번호 유효성 검사 (지역번호/휴대폰 포함)"""
    if not isinstance(val, str):
        return False
    
    # 숫자만 추출
    digits = re.sub(r"\D", "", val)
    n = len(digits)
    
    # 자릿수 검사
    if n < 7 or n > 11:
        return False

    # =========================
    # 1) 지역번호 없는 7~8자리
    # =========================
    if n in (7, 8):
        return digits[0] in "23456789"
    
    # =========================
    # 2) 서울 번호 (02)
    # =========================
    if digits.startswith("02"):
        local = digits[2:]
        return len(local) in (7, 8) and local[0] not in {"0", "1"}
    
    # =========================
    # 3) 휴대폰 (010)
    # =========================
    if digits.startswith("010"):
        local = digits[3:]
        return 7 <= len(local) <= 8 and local[0] not in {"0", "1"}
    
    # =========================
    # 4) 기타 지역번호 (03~09X)
    # =========================
    if re.match(r"0[3-9][0-9]", digits):
        local = digits[3:]
        return len(local) in (7, 8) and local[0] not in {"0", "1"}
    
    return False


def validate_cellphone(value) -> bool:
    s = str(value)
    if s.endswith('.0'): s = s[:-2]
    digits = re.sub(r'[^0-9]', '', s)
    if len(digits) not in (10, 11):
        return False
    if digits[:3] not in ['010','011','016','017','018','019']:
        return False
    local = digits[3:]
    return bool(local) and local[0] not in {'0','1'}

def validate_url(value) -> bool:
    url_pattern = re.compile(
        r'^https?:\/\/(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|localhost|\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?(?:/?|[/?]\S+)$',
        re.IGNORECASE
    )
    return bool(url_pattern.match(str(value)))

def validate_email(value) -> bool:
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(email_pattern.match(str(value)))

def validate_kor_name(value: str) -> bool:
    """값의 첫 글자가 KOR_NAME_SET에 있으면 True. 세트 없으면 완화 True."""
    if not KOR_NAME_SET:
        return True
    try:
        s = str(value)
        return bool(s) and (s[:1] in KOR_NAME_SET)
    except Exception:
        return True

def validate_country_code(value: str) -> bool:
    """ISO 3166-1 alpha-3 전용. 세트가 있으면 membership, 없으면 3대문자 형식만 체크."""
    s = str(value).strip().upper()
    if not s or not re.fullmatch(r"[A-Z]{3}", s):
        return False
    return (s in COUNTRY_ISO3_SET) if COUNTRY_ISO3_SET else True

def validate_address(value: str) -> bool:
    """
    주소(ADDRESS) 유효성 강화:
      - 시도 토큰은 약칭/축약(경북/전남/강원특자 등)까지 허용
      - 시군구 후보: 두번째 토큰, (2+3)결합(공백/무공백), 세번째 단독까지
      - 접미사(시/군/구/자치구/특별자치시)로 노이즈 감소
      - SIDO→SIGUNGU 매핑이 있으면 우선, 없으면 전역 시군구 셋으로 완화
    """
    if not SIDO_SET or (not SIGUNGU_SET and not SIDO_TO_SIGUNGU):
        return True  # 참조 세트 미초기화 시 파이프라인 유지

    try:
        s = _norm(value)
        if not s: return False
        parts = s.split()
        if not parts: return False

        tok = _normalize_sido_token(parts[0])
        if tok not in SIDO_SET:
            base = _sido_base(tok)
            cand_sido = [sd for sd in SIDO_SET if _sido_base(sd) == base]
            if not cand_sido:
                return False
            sido = cand_sido[0]
        else:
            sido = tok

        if sido in _SIDO_SIGUNGU_OPTIONAL:
            return len(parts) >= 2

        # 시군구 후보 생성
        candidates = []
        if len(parts) >= 2:
            candidates.append(_norm(parts[1]))                      # '성남시'
        if len(parts) >= 3:
            candidates.append(_norm(parts[1] + " " + parts[2]))     # '성남시 분당구'
            candidates.append(_norm(parts[1] + parts[2]))           # '성남시분당구'
            candidates.append(_norm(parts[2]))                       # '분당구'

        def looks_sigungu(x: str) -> bool:
            return x.endswith(("시","군","구","자치구","특별자치시"))

        candidates = [x for x in candidates if looks_sigungu(x)]
        if not candidates:
            return False

        if SIDO_TO_SIGUNGU:
            valid_gus = SIDO_TO_SIGUNGU.get(sido, set())
            if valid_gus:
                nospace = {g.replace(" ", "") for g in valid_gus}
                return any(x in valid_gus or x.replace(" ", "") in nospace for x in candidates)
        nospace_all = {g.replace(" ", "") for g in SIGUNGU_SET}
        return any(x in SIGUNGU_SET or x.replace(" ", "") in nospace_all for x in candidates)

    except Exception:
        return True


def validate_gender(val: str) -> bool:
    return str(val) in ["남", "여"]

def validate_gender_en(val: str) -> bool:
    return str(val).upper() in ["M", "F"]


def validate_car_number(val: str) -> bool:
    if not isinstance(val, str):
        return False

    val = val.strip()

    # 1) 기존 한국 차량 번호: 숫자(2~3) + 한글(1) + 숫자(4) 예: 12가1234, 123나4567
    pattern_kor = r"^\d{2,3}[가-힣]\d{4}$"

    # 2) 확장 패턴: 한글(2) + 숫자(2) + 한글(1) + 숫자(4)  예: 가나12다1234
    pattern_kor2 = r"^[가-힣]{2}\d{2}[가-힣]\d{4}$"

    return bool(re.fullmatch(pattern_kor, val) or re.fullmatch(pattern_kor2, val))

def validate_time(val: str) -> bool:

    pattern_1 = r"^\d{2}:\d{2}:\d{2}$"
    pattern_2 = r"^\d{2}:\d{2}.\d{1}$"

    if not re.fullmatch(pattern_1, str(val)) and not re.fullmatch(pattern_2, str(val)):
        return False
    return True

def validate_timestamp(val: str) -> bool:
    return True

#---------------------------------------------------------------
# Determine_Detail_Type helpers 함수
#---------------------------------------------------------------

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

def is_address(pattern, format_stats):
    return (len(pattern) >= 8 and pattern.count('K') >= 6 and pattern.count(' ') >= 2
            and validate_address(format_stats['FormatMedian']))

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
        if is_address(pattern, format_stats):       return 'ADDRESS'
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

def Determine_Detail_Type_new(pattern, pattern_type_cnt, format_stats, total_stats,
                          max_length, unique_count, non_null_count, top10):
    # 1. 최우선 순위: 패턴이 완벽하게 일치하는가? (강한 규칙)
    if is_email(pattern): return 'EMAIL'
    if is_jumin(pattern): return 'JUMIN'
    
    # 2. 통계적 분석 (약한 규칙)
    # 점수 계산기를 도입하여 가장 높은 점수를 얻은 타입을 선택
    scores = {
        'CODE': check_code_score(unique_count, non_null_count, pattern_type_cnt),
        'TEXT': check_text_score(max_length, pattern_type_cnt),
        'FLAG': check_flag_score(unique_count, top10)
    }
    
    # 가장 점수가 높은 것을 선택하되, 동점이면 우선순위에 따라 반환
    best_type = max(scores, key=scores.get)
    return best_type if scores[best_type] > 50 else 'UNKNOWN'
    """
'코드 개편 3단계' 가이드
1단계: 확실한 것부터 먼저 처리하기 (패턴 매칭)
이메일(@), 전화번호(-와 숫자), 주민번호처럼 "누가 봐도 이건 이거다!" 싶은 것들을 가장 윗줄에서 처리합니다.
2단계: 숫자의 의미 파악하기 (통계 기반)
값이 딱 2개면 FLAG, 고유값이 많고 길면 TEXT, 고유값이 적당하면 CODE로 분류합니다. 이때 **전체 건수 대비 비율(%)**을 기준으로 삼으면 데이터 양에 상관없이 정확해집니다.
3단계: 예외 상황 '점수제' 도입
이게 CODE 같기도 하고 TEXT 같기도 할 때는 각 항목에 점수를 매겨서(예: 한글이 많으면 TEXT 점수 +10점) 가장 높은 점수인 쪽으로 결정하는 방식을 도입해 보세요.
"""
#---------------------------------------------------------------
# DQUtils & ColumnProfiler Class
#---------------------------------------------------------------
class DQUtils:
    _FLOAT_ZERO_RE = re.compile(r'^[+-]?\d+\.0+$')
    @staticmethod
    def strip_decimal_zero(x):
        try:
            s = str(x)
            return s.split('.', 1)[0] if DQUtils._FLOAT_ZERO_RE.fullmatch(s) else s
        except Exception as e:
            log_error(f"strip_decimal_zero 오류: {e}, 값: {x}")
            return str(x)
    
    @staticmethod
    def get_pattern(value):
        try:
            s = DQUtils.strip_decimal_zero(value)[:20]
            p = []
            for ch in s:
                if ch.isdigit(): p.append('n')
                elif '가' <= ch <= '힣': p.append('K')
                elif ch.isalpha(): p.append('A' if ch.isupper() else 'a')
                elif ch in '(){}[]-=. :@/': p.append(ch)
                else: p.append('s')
            return "".join(p)
        except Exception as e:
            log_error(f"get_pattern 오류: {e}, 값: {value}")
            return ""


# 멀티프로세싱용 모듈 레벨 함수
def _process_chunk_has_stats(chunk):
    """청크 단위로 Has 통계 계산 (멀티프로세싱용)"""
    results = {}
    for val in chunk:
        # 제어 문자
        if '\t' in val: results['has_tab'] = results.get('has_tab', 0) + 1
        if '\r' in val: results['has_cr'] = results.get('has_cr', 0) + 1
        if '\n' in val: results['has_lf'] = results.get('has_lf', 0) + 1
        
        # 포함 여부
        if ' ' in val: results['has_blank'] = results.get('has_blank', 0) + 1
        if '-' in val: results['has_dash'] = results.get('has_dash', 0) + 1
        if '.' in val: results['has_dot'] = results.get('has_dot', 0) + 1
        if '@' in val: results['has_at'] = results.get('has_at', 0) + 1
        if any(c in val for c in '()[]{}'): results['has_bracket'] = results.get('has_bracket', 0) + 1
        if '-' in val.split('.')[0]: results['has_minus'] = results.get('has_minus', 0) + 1
        
        # 문자 성격
        if re.search(r'[a-zA-Z]', val): results['has_alpha'] = results.get('has_alpha', 0) + 1
        if re.search(r'[가-힣]', val): results['has_kor'] = results.get('has_kor', 0) + 1
        if re.search(r'[0-9]', val): results['has_num'] = results.get('has_num', 0) + 1
        
        # 전용 구성
        if val.isalpha(): results['has_only_alpha'] = results.get('has_only_alpha', 0) + 1
        if val.isdigit(): results['has_only_num'] = results.get('has_only_num', 0) + 1
        if re.match(r'^[가-힣]+$', val): results['has_only_kor'] = results.get('has_only_kor', 0) + 1
        if val.isalnum(): results['has_only_alphanum'] = results.get('has_only_alphanum', 0) + 1
        
        # 첫 문자 성격
        if val:
            f = val[0]
            if re.match(r'[가-힣]', f): results['f_kor'] = results.get('f_kor', 0) + 1
            if f.isdigit(): results['f_num'] = results.get('f_num', 0) + 1
            if f.isalpha() and not re.match(r'[가-힣]', f): results['f_alpha'] = results.get('f_alpha', 0) + 1
            if not (re.match(r'[가-힣]', f) or f.isdigit() or f.isalpha()): 
                results['f_spec'] = results.get('f_spec', 0) + 1
        
        # 기타
        if re.search(r'[\ufffd]', val): results['has_broken_kor'] = results.get('has_broken_kor', 0) + 1
        if re.search(r'[^\w\s\u1100-\u11FF\u3130-\u318F\uAC00-\uD7A3!-~]', val): 
            results['has_special'] = results.get('has_special', 0) + 1
        if re.search(r'[\u4e00-\u9fff]', val): results['has_chinese'] = results.get('has_chinese', 0) + 1
        if re.search(r'[\u3040-\u30ff\u31f0-\u31ff]', val): results['has_japanese'] = results.get('has_japanese', 0) + 1
        
        # Unicode 체크
        others = [c for c in val if ord(c) > 127]
        if others:
            joined_others = "".join(others)
            pattern = r'[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u1100-\u11FF\u3130-\u318F\uAC00-\uD7A3\ufffd]'
            cleaned = re.sub(pattern, '', joined_others)
            if len(cleaned) > 0: results['has_unicode_pure'] = results.get('has_unicode_pure', 0) + 1
            
            pattern_v2 = r'[\s\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u1100-\u11FF\u3130-\u318F\uAC00-\uD7A3\ufffd]'
            cleaned_v2 = re.sub(pattern_v2, '', joined_others)
            if len(cleaned_v2) > 0: results['has_unicode2'] = results.get('has_unicode2', 0) + 1
    
    return results

#---------------------------------------------------------------
# ColumnProfiler Class
#---------------------------------------------------------------
class ColumnProfiler:
    def __init__(self, df, col, sample_rows):
        self.df = df
        self.col = col
        self.sample_rows = sample_rows
        # 속도 향상을 위해 한 번만 변환하여 재사용합니다.
        self.valid_series = df[col].dropna().astype(str)
        self.str_vals = self.valid_series

    def _strip_decimal_zero(self, val):
        """숫자형 문자열의 .0 제거 (사용자 DQUtils 로직)"""
        s = str(val)
        if s.endswith('.0'): return s[:-2]
        return s

    def _get_pattern_custom(self, s):
        """사용자 작성 get_pattern 로직 (n, K, A, a 등 변환)"""
        def transform(value):
            try:
                text = self._strip_decimal_zero(value)[:20]
                p = []
                for ch in text:
                    if ch.isdigit(): p.append('n')
                    elif '가' <= ch <= '힣': p.append('K')
                    elif ch.isupper(): p.append('A')
                    elif ch.islower(): p.append('a')
                    elif ch in '(){}[]-=. :@/': p.append(ch)
                    else: p.append('s')
                return "".join(p)
            except: return ""
        return s.apply(transform)

    def _get_edge_stats(self, side, n):
        """시작/끝 N자리의 Top 3 값과 빈도 추출"""
        if self.valid_series.empty: return {}
        extracted = self.str_vals.str[:n] if side == 'First' else self.str_vals.str[-n:]
        counts = extracted.value_counts().head(3)
        res = {}
        for i in range(1, 4):
            res[f'{side}{n}M{i}'] = counts.index[i-1] if len(counts) >= i else ""
            res[f'{side}{n}Cnt{i}'] = int(counts.iloc[i-1]) if len(counts) >= i else 0
        return res

    def profile(self):
        """기본 통계와 상세 타입 판정을 통합한 최종 메서드"""
        try:
            val_cnt = len(self.valid_series)
            record_cnt = len(self.df)
            
            # 1. 결과 데이터 구조 초기화
            res = {
                'ColumnName': self.col,
                'DataType': str(self.df[self.col].dtype),
                'RecordCnt': record_cnt,
                'SampleRows': self.sample_rows,
                'ValueCnt': val_cnt,
                'NullCnt': record_cnt - val_cnt,
                'Null(%)': round((record_cnt - val_cnt) / record_cnt * 100, 2) if record_cnt > 0 else 0,
            }

            if val_cnt == 0:
                res.update({'OracleType': 'VARCHAR2(255)', 'DetailDataType': '', 'PK': 0})
                return res

            # 2. 통계치 계산
            lens = self.valid_series.str.len()
            unique_cnt = self.valid_series.nunique()
            sorted_vals = sorted(self.valid_series.tolist())
            top10_counts = self.valid_series.value_counts().head(10)
            top10_json = json.dumps(top10_counts.to_dict(), ensure_ascii=False)
            
            res.update({
                'LenCnt': val_cnt, 'LenMin': lens.min(), 'LenMax': lens.max(),
                'LenAvg': round(lens.mean(), 1), 
                'LenMode': int(lens.mode().iloc[0]) if not lens.mode().empty else 0,
                'UniqueCnt': unique_cnt, 'Unique(%)': round(unique_cnt / val_cnt * 100, 2),
                'MinString': sorted_vals[0], 'MaxString': sorted_vals[-1],
                'ModeString': self.valid_series.mode().iloc[0] if not self.valid_series.mode().empty else "", 
                'MedianString': sorted_vals[len(sorted_vals)//2],
                'ModeCnt': int(top10_counts.iloc[0]) if not top10_counts.empty else 0,
                'Top10': top10_json,
                'Top10(%)': round(top10_counts.sum() / val_cnt * 100, 2)
            })

            # 3. 포맷(패턴) 분석
            patterns = self._get_pattern_custom(self.valid_series)
            pat_counts = patterns.value_counts()
            pattern_type_cnt = len(pat_counts)
            most_common_pattern = pat_counts.index[0] if not pat_counts.empty else ""
            
            res['FormatCnt'] = pattern_type_cnt
            
            # 상위 3개 포맷 상세 통계
            for i, sfx in enumerate(['', '2nd', '3rd']):
                key = f'Format{sfx}'
                if i < len(pat_counts):
                    fmt = pat_counts.index[i]
                    f_subset = self.valid_series[patterns == fmt]
                    f_vals = sorted(f_subset.tolist())
                    res.update({
                        key: fmt,
                        f'{key}Value': int(pat_counts.iloc[i]),
                        f'{key}(%)': round(pat_counts.iloc[i] / val_cnt * 100, 2),
                        f'{key}Min': f_vals[0],
                        f'{key}Max': f_vals[-1],
                        f'{key}Mode': f_subset.mode().iloc[0] if not f_subset.mode().empty else "",
                        f'{key}Median': f_vals[len(f_vals)//2]
                    })

            # 4. 상세 데이터 타입 판정 (판정 함수들이 요구하는 Key를 모두 주입)
            total_stats = {
                'LenMin': res['LenMin'], 'LenMax': res['LenMax'],
                'LenMode': res['LenMode'], 'LenMedian': lens.median(),
                'min': res['MinString'], 'max': res['MaxString'], 'mode': res['ModeString']
            }
            
            # 핵심: Determine_Detail_Type 내부의 is_text, is_flag 등이 사용하는 Key들을 여기서 다 넣어줍니다.
            format_stats = {
                'FormatMode': most_common_pattern,
                'most_common_pattern': most_common_pattern, # 추가: KeyError 해결
                'pattern_type_cnt': pattern_type_cnt,       # 추가: KeyError 해결
                'LenMin': res.get('FormatMin', 0),
                'LenMax': res.get('FormatMax', 0),
                'LenMode': res.get('FormatMode', 0),
                'FormatMedian': res.get('FormatMedian', "")
            }

            detail_type = Determine_Detail_Type(
                pattern=most_common_pattern, 
                pattern_type_cnt=pattern_type_cnt,
                format_stats=format_stats,
                total_stats=total_stats,
                max_length=res['LenMax'],
                unique_count=unique_cnt,
                non_null_count=val_cnt,
                top10=top10_json
            )
            
            res['DetailDataType'] = detail_type
            res['PK'] = 1 if detail_type == "UNIQUE" else 0
            res['OracleType'] = Get_Oracle_Type(self.valid_series, self.col)

            # 5. 기타 구성 통계 추가
            self._add_composition_stats(res)
            
            return res

        except Exception as e:
            import traceback
            logging.error(f"컬럼 프로파일링 실패 (컬럼: {self.col}): {str(e)}")
            logging.error(traceback.format_exc())
            return res

    def _add_composition_stats(self, res):
        """문자 구성 요소 및 시작/끝 패턴 추가"""
        s = self.valid_series
        val_cnt = len(s)
        # 문자열 통계 및 Top 10
        # sorted_vals = sorted(self.valid_series.tolist())
        # top10 = self.valid_series.value_counts().head(10)
        # res.update({
        #     'MinString': sorted_vals[0], 'MaxString': sorted_vals[-1],
        #     'ModeString': self.valid_series.mode().iloc[0], 'MedianString': sorted_vals[len(sorted_vals)//2],
        #     'ModeCnt': int(top10.iloc[0]), 'Mode(%)': round(top10.iloc[0] / val_cnt * 100, 2),
        #     'Top10': json.dumps(top10.to_dict(), ensure_ascii=False),
        #     'Top10(%)': round(top10.sum() / val_cnt * 100, 2)
        # })

        # Has... (존재/구성 여부 체크)
        s = self.valid_series
        res.update({
            'HasBlank': 1 if s.str.contains(r'\s').any() else 0,
            'HasDash': 1 if s.str.contains('-').any() else 0,
            'HasDot': 1 if s.str.contains(r'\.').any() else 0,
            'HasAt': 1 if s.str.contains('@').any() else 0,
            'HasAlpha': 1 if s.str.contains(r'[a-zA-Z]').any() else 0,
            'HasKor': 1 if s.str.contains(r'[가-힣]').any() else 0,
            'HasNum': 1 if s.str.contains(r'[0-9]').any() else 0,
            'HasBracket': 1 if s.str.contains(r'[\[\]\(\)\{\}]').any() else 0,
            'HasMinus': 1 if s.str.contains(r'^-').any() else 0,
            'HasOnlyAlpha': 1 if s.str.match(r'^[a-zA-Z]+$').all() else 0,
            'HasOnlyNum': 1 if s.str.match(r'^[0-9]+$').all() else 0,
            'HasOnlyKor': 1 if s.str.match(r'^[가-힣]+$').all() else 0,
            'HasOnlyAlphanum': 1 if s.str.match(r'^[a-zA-Z0-9]+$').all() else 0,
            'HasBrokenKor': 1 if s.str.contains(r'[\ufffd]').any() else 0,
            'HasSpecial': 1 if s.str.contains(r'[^a-zA-Z0-9가-힣\s]').any() else 0,
            'HasUnicode': 1 if s.apply(lambda x: any(ord(c) > 127 for c in x)).any() else 0,
            'HasUnicode2': 1 if s.apply(lambda x: any(ord(c) > 0xFFFF for c in x)).any() else 0,
            'HasChinese': 1 if s.str.contains(r'[\u4e00-\u9fff]').any() else 0,
            'HasJapanese': 1 if s.str.contains(r'[\u3040-\u30ff]').any() else 0,
            'HasTab': 1 if s.str.contains('\t').any() else 0,
            'HasCr': 1 if s.str.contains('\r').any() else 0,
            'HasLf': 1 if s.str.contains('\n').any() else 0,
        })

        # 첫 글자 및 Edge Stats (First/Last 1~3)
        fc = s.str[0]
        res.update({
            'FirstChrKor': fc.str.contains(r'[가-힣]').sum(),
            'FirstChrNum': fc.str.contains(r'[0-9]').sum(),
            'FirstChrAlpha': fc.str.contains(r'[a-zA-Z]').sum(),
            'FirstChrSpecial': val_cnt - (fc.str.contains(r'[a-zA-Z0-9가-힣]').sum())
        })

        # --- [추가] 시작(First) 및 끝(Last) N자리 Top 10 추출 ---
        for n in [1, 2, 3]:
            # 1. 시작 N자리 Top 10
            first_n = s.str[:n]
            f_top10 = first_n.value_counts().head(10).to_dict()
            res[f'First{n}Top10'] = json.dumps(f_top10, ensure_ascii=False)

            # 2. 끝 N자리 Top 10
            last_n = s.str[-n:]
            l_top10 = last_n.value_counts().head(10).to_dict()
            res[f'Last{n}Top10'] = json.dumps(l_top10, ensure_ascii=False)
            
        for n in [1, 2, 3]:
            res.update(self._get_edge_stats('First', n))
            res.update(self._get_edge_stats('Last', n))

        return res
        
    # def profile(self):
    #     val_cnt = len(self.valid_series)
    #     record_cnt = len(self.df)
        
    #     # 기본 정보 (DataType, OracleType, DetailDataType)
    #     dtype = str(self.df[self.col].dtype)
    #     max_len = self.valid_series.str.len().max() if val_cnt > 0 else 0
    #     oracle_type = f"VARCHAR2({int(max_len)})" if val_cnt > 0 else "VARCHAR2(255)"
    #     detail_type = "UNIQUE" if self.valid_series.is_unique and val_cnt > 0 else ""

    #     res = {
    #         'ColumnName': self.col, 'PK': 1 if detail_type == "UNIQUE" else 0,
    #         'DataType': dtype, 'OracleType': oracle_type, 'DetailDataType': detail_type,
    #         'RecordCnt': record_cnt, 'SampleRows': self.sample_rows,
    #         'ValueCnt': val_cnt, 'NullCnt': record_cnt - val_cnt,
    #         'Null(%)': round((record_cnt - val_cnt) / record_cnt * 100, 2) if record_cnt > 0 else 0,
    #     }

    #     if val_cnt == 0: return res

    #     # 길이 및 고유성
    #     lens = self.valid_series.str.len()
    #     unique_cnt = self.valid_series.nunique()
    #     res.update({
    #         'LenCnt': val_cnt, 'LenMin': lens.min(), 'LenMax': lens.max(),
    #         'LenAvg': round(lens.mean(), 1), 'LenMode': int(lens.mode().iloc[0]),
    #         'UniqueCnt': unique_cnt, 'Unique(%)': round(unique_cnt / val_cnt * 100, 2),
    #     })

    #     # 포맷 분석 (사용자 정의 로직 적용)
    #     patterns = self._get_pattern_custom(self.valid_series)
    #     pat_counts = patterns.value_counts()
    #     res['FormatCnt'] = len(pat_counts)
    #     for i, sfx in enumerate(['', '2nd', '3rd']):
    #         key = f'Format{sfx}'
    #         if i < len(pat_counts):
    #             fmt = pat_counts.index[i]
    #             res[f'{key}'] = fmt
    #             res[f'{key}Value'] = int(pat_counts.iloc[i])
    #             res[f'{key}(%)'] = round(pat_counts.iloc[i] / val_cnt * 100, 2)
    #             f_vals = sorted(self.valid_series[patterns == fmt].tolist())
    #             res[f'{key}Min'], res[f'{key}Max'] = f_vals[0], f_vals[-1]
    #             res[f'{key}Mode'] = Counter(f_vals).most_common(1)[0][0]
    #             res[f'{key}Median'] = f_vals[len(f_vals)//2]

    #     # 문자열 통계 및 Top 10
    #     sorted_vals = sorted(self.valid_series.tolist())
    #     top10 = self.valid_series.value_counts().head(10)
    #     res.update({
    #         'MinString': sorted_vals[0], 'MaxString': sorted_vals[-1],
    #         'ModeString': self.valid_series.mode().iloc[0], 'MedianString': sorted_vals[len(sorted_vals)//2],
    #         'ModeCnt': int(top10.iloc[0]), 'Mode(%)': round(top10.iloc[0] / val_cnt * 100, 2),
    #         'Top10': json.dumps(top10.to_dict(), ensure_ascii=False),
    #         'Top10(%)': round(top10.sum() / val_cnt * 100, 2)
    #     })

    #     # Has... (존재/구성 여부 체크)
    #     s = self.valid_series
    #     res.update({
    #         'HasBlank': 1 if s.str.contains(r'\s').any() else 0,
    #         'HasDash': 1 if s.str.contains('-').any() else 0,
    #         'HasDot': 1 if s.str.contains(r'\.').any() else 0,
    #         'HasAt': 1 if s.str.contains('@').any() else 0,
    #         'HasAlpha': 1 if s.str.contains(r'[a-zA-Z]').any() else 0,
    #         'HasKor': 1 if s.str.contains(r'[가-힣]').any() else 0,
    #         'HasNum': 1 if s.str.contains(r'[0-9]').any() else 0,
    #         'HasBracket': 1 if s.str.contains(r'[\[\]\(\)\{\}]').any() else 0,
    #         'HasMinus': 1 if s.str.contains(r'^-').any() else 0,
    #         'HasOnlyAlpha': 1 if s.str.match(r'^[a-zA-Z]+$').all() else 0,
    #         'HasOnlyNum': 1 if s.str.match(r'^[0-9]+$').all() else 0,
    #         'HasOnlyKor': 1 if s.str.match(r'^[가-힣]+$').all() else 0,
    #         'HasOnlyAlphanum': 1 if s.str.match(r'^[a-zA-Z0-9]+$').all() else 0,
    #         'HasBrokenKor': 1 if s.str.contains(r'[\ufffd]').any() else 0,
    #         'HasSpecial': 1 if s.str.contains(r'[^a-zA-Z0-9가-힣\s]').any() else 0,
    #         'HasUnicode': 1 if s.apply(lambda x: any(ord(c) > 127 for c in x)).any() else 0,
    #         'HasUnicode2': 1 if s.apply(lambda x: any(ord(c) > 0xFFFF for c in x)).any() else 0,
    #         'HasChinese': 1 if s.str.contains(r'[\u4e00-\u9fff]').any() else 0,
    #         'HasJapanese': 1 if s.str.contains(r'[\u3040-\u30ff]').any() else 0,
    #         'HasTab': 1 if s.str.contains('\t').any() else 0,
    #         'HasCr': 1 if s.str.contains('\r').any() else 0,
    #         'HasLf': 1 if s.str.contains('\n').any() else 0,
    #     })

    #     # 첫 글자 및 Edge Stats (First/Last 1~3)
    #     fc = s.str[0]
    #     res.update({
    #         'FirstChrKor': fc.str.contains(r'[가-힣]').sum(),
    #         'FirstChrNum': fc.str.contains(r'[0-9]').sum(),
    #         'FirstChrAlpha': fc.str.contains(r'[a-zA-Z]').sum(),
    #         'FirstChrSpecial': val_cnt - (fc.str.contains(r'[a-zA-Z0-9가-힣]').sum())
    #     })
    #     for n in [1, 2, 3]:
    #         res.update(self._get_edge_stats('First', n))
    #         res.update(self._get_edge_stats('Last', n))

    #     return res
# #---------------------------------------------------------------
# class ColumnProfiler_old:
#     def __init__(self, df, column, sample_rows):
#         try:
#             if df is None or df.empty:
#                 raise ValueError(f"DataFrame이 비어있거나 None입니다.")
#             if column not in df.columns:
#                 raise ValueError(f"컬럼 '{column}'이 DataFrame에 존재하지 않습니다.")
            
#             self.logger = logging.getLogger(__name__)
#             self.col = column
#             self.series = df[column]
#             self.non_null = self.series.dropna()
#             self.str_vals = self.non_null.astype(str)
#             self.count = len(df)
#             self.sample_rows = sample_rows
#         except Exception as e:
#             log_error(f"ColumnProfiler 초기화 오류 (컬럼: {column}): {e}")
#             log_error(traceback.format_exc())
#             raise

#     def _compute_has_stats_parallel(self, str_vals_list):
#         """멀티프로세싱으로 Has 통계 계산"""
#         if len(str_vals_list) < MULTIPROCESSING_THRESHOLD:
#             # 데이터가 적으면 순차 처리
#             return _process_chunk_has_stats(str_vals_list)
        
#         # 청크로 나누기
#         num_workers = min(cpu_count(), 8)  # 최대 8개 워커
#         chunk_size = max(1, len(str_vals_list) // num_workers)
#         chunks = [str_vals_list[i:i+chunk_size] for i in range(0, len(str_vals_list), chunk_size)]
        
#         # 병렬 처리
#         try:
#             with Pool(num_workers) as pool:
#                 results = pool.map(_process_chunk_has_stats, chunks)
#         except Exception as e:
#             log_warning(f"멀티프로세싱 실패, 순차 처리로 전환: {e}")
#             return _process_chunk_has_stats(str_vals_list)
        
#         # 결과 합산
#         merged = {}
#         for r in results:
#             for key, val in r.items():
#                 merged[key] = merged.get(key, 0) + val
        
#         return merged

#     def profile(self):
#         try:
#             if self.count == 0: return {}

#             # 멀티프로세싱으로 Has 통계 계산
#             str_vals_list = self.str_vals.tolist()
#             has_stats = self._compute_has_stats_parallel(str_vals_list)
            
#             # 결과 추출
#             has_tab = has_stats.get('has_tab', 0)
#             has_cr = has_stats.get('has_cr', 0)
#             has_lf = has_stats.get('has_lf', 0)
#             has_blank = has_stats.get('has_blank', 0)
#             has_dash = has_stats.get('has_dash', 0)
#             has_dot = has_stats.get('has_dot', 0)
#             has_at = has_stats.get('has_at', 0)
#             has_bracket = has_stats.get('has_bracket', 0)
#             has_minus = has_stats.get('has_minus', 0)
#             has_alpha = has_stats.get('has_alpha', 0)
#             has_kor = has_stats.get('has_kor', 0)
#             has_num = has_stats.get('has_num', 0)
#             has_only_alpha = has_stats.get('has_only_alpha', 0)
#             has_only_num = has_stats.get('has_only_num', 0)
#             has_only_kor = has_stats.get('has_only_kor', 0)
#             has_only_alphanum = has_stats.get('has_only_alphanum', 0)
#             f_kor = has_stats.get('f_kor', 0)
#             f_num = has_stats.get('f_num', 0)
#             f_alpha = has_stats.get('f_alpha', 0)
#             f_spec = has_stats.get('f_spec', 0)
#             has_broken_kor = has_stats.get('has_broken_kor', 0)
#             has_special = has_stats.get('has_special', 0)
#             has_chinese = has_stats.get('has_chinese', 0)
#             has_japanese = has_stats.get('has_japanese', 0)
#             has_unicode_pure = has_stats.get('has_unicode_pure', 0)
#             has_unicode2 = has_stats.get('has_unicode2', 0)

#             val_cnt = len(self.non_null)
#             null_cnt = self.count - val_cnt
#             unique_cnt = self.non_null.nunique()
            
#             # 기본 통계 및 누락된 SampleRows 추가
#             res = {
#                 'ColumnName': self.col,
#                 'DataType': str(self.series.dtype),
#                 'OracleType': Get_Oracle_Type(self.series, self.col),
#                 'PK': 1 if unique_cnt == self.count and self.count > 0 else 0,
#                 'RecordCnt': self.count,
#                 'SampleRows': self.sample_rows, # 누락 컬럼 반영
#                 'ValueCnt': val_cnt,
#                 'NullCnt': null_cnt,
#                 'Null(%)': round(null_cnt / self.count * 100, 2) if self.count > 0 else 0,
#                 'UniqueCnt': unique_cnt,
#                 'Unique(%)': round(unique_cnt / val_cnt * 100, 2) if val_cnt > 0 else 0,
#                 'HasBlank': int(has_blank), 'HasDash': int(has_dash), 'HasDot': int(has_dot), 'HasAt': int(has_at),
#                 'HasAlpha': int(has_alpha), 'HasKor': int(has_kor), 'HasNum': int(has_num),
#                 'HasBracket': int(has_bracket), 'HasMinus': int(has_minus),
#                 'HasOnlyAlpha': int(has_only_alpha), 'HasOnlyNum': int(has_only_num),
#                 'HasOnlyKor': int(has_only_kor), 'HasOnlyAlphanum': int(has_only_alphanum),
#                 'FirstChrKor': int(f_kor), 'FirstChrNum': int(f_num), 'FirstChrAlpha': int(f_alpha), 'FirstChrSpecial': int(f_spec),
#                 'HasBrokenKor': int(has_broken_kor), 'HasSpecial': int(has_special), 
#                 'HasUnicode': int(has_unicode_pure),'HasUnicode2': int(has_unicode2),  
#                 'HasChinese': int(has_chinese), 'HasJapanese': int(has_japanese),
#                 'HasTab': int(has_tab), 'HasCr': int(has_cr), 'HasLf': int(has_lf)
#             }

#             if val_cnt > 0:
#                 lens = self.str_vals.str.len()
#                 len_counts = lens.value_counts()
                
#                 # 길이 관련 누락 컬럼 반영
#                 res['LenCnt'] = len(len_counts)
#                 res['LenMin'] = int(lens.min())
#                 res['LenMax'] = int(lens.max())
#                 res['LenAvg'] = round(lens.mean(), 1)
#                 res['LenMode'] = int(len_counts.index[0]) if len(len_counts) > 0 else 0

#                 top_counts = self.str_vals.value_counts().head(10)
#                 top10_json = json.dumps(top_counts.index.tolist(), ensure_ascii=False) if len(top_counts) > 0 else "[]"
                
#                 res['MinString'] = self.str_vals.min()
#                 res['MaxString'] = self.str_vals.max()
#                 res['ModeString'] = top_counts.index[0] if len(top_counts) > 0 else ""
#                 res['MedianString'] = self.str_vals.sort_values().iloc[val_cnt // 2] if val_cnt > 0 else ""
#                 res['ModeCnt'] = int(top_counts.iloc[0]) if len(top_counts) > 0 else 0
#                 res['Mode(%)'] = round((res['ModeCnt'] / self.count) * 100, 2) if self.count > 0 else 0


#                 # 패턴 및 포맷 분석
#                 patterns = self.str_vals.map(DQUtils.get_pattern)
#                 pattern_stats = Counter(patterns).most_common()
#                 res['FormatCnt'] = len(pattern_stats)

#                 # 1~3순위 포맷 루프 (규격명칭 준수)
#                 prefixes = [("", ""), ("2nd", "2nd"), ("3rd", "3rd")]
#                 for i, (p_name, _) in enumerate(prefixes):
#                     if len(pattern_stats) > i:
#                         p_val, p_cnt = pattern_stats[i]
#                         fmt_subset = self.str_vals[patterns == p_val]
#                         res[f'Format{p_name}'] = p_val
#                         res[f'Format{p_name}Value'] = p_cnt
#                         res[f'Format{p_name}(%)'] = round(p_cnt / val_cnt * 100, 2) if val_cnt > 0 else 0
#                         res[f'Format{p_name}Min'] = fmt_subset.min() if len(fmt_subset) > 0 else ""
#                         res[f'Format{p_name}Max'] = fmt_subset.max() if len(fmt_subset) > 0 else ""
#                         mode_result = fmt_subset.mode()
#                         res[f'Format{p_name}Mode'] = mode_result[0] if len(mode_result) > 0 else ""
#                         sorted_subset = fmt_subset.sort_values()
#                         res[f'Format{p_name}Median'] = sorted_subset.iloc[len(sorted_subset)//2] if len(sorted_subset) > 0 else ""
#                     else:
#                         res[f'Format{p_name}'] = ""
#                         res[f'Format{p_name}Value'] = 0
#                         res[f'Format{p_name}(%)'] = 0.0
#                         res[f'Format{p_name}Min'] = res[f'Format{p_name}Max'] = res[f'Format{p_name}Mode'] = res[f'Format{p_name}Median'] = ""

#                 # DetailDataType 판별
#                 f_stats = {'FormatMedian': res.get('MedianString', ''), 'FormatMode': res.get('ModeString', ''), 
#                         'most_common_pattern': pattern_stats[0][0] if pattern_stats and len(pattern_stats) > 0 else "", 
#                         'pattern_type_cnt': len(pattern_stats)}
#                 res['DetailDataType'] = Determine_Detail_Type(
#                     f_stats['most_common_pattern'], len(pattern_stats), 
#                     f_stats, {
#                         'min': res.get('MinString', ''), 
#                         'max': res.get('MaxString', ''), 
#                         'mode': res.get('ModeString', '')
#                     }, 
#                     int(res.get('LenMax', 0)), int(unique_cnt), int(val_cnt), top10_json
#                 )

#                 res.update({'Top10': top10_json, 'Top10(%)': round(top_counts.sum() / val_cnt * 100, 2) if val_cnt > 0 else 0})
#                 for n in [1, 2, 3]:
#                     res.update(self._get_edge_stats('First', n))
#                     res.update(self._get_edge_stats('Last', n))
#             return res
        
#         except Exception as e:
#             log_error(f"컬럼 '{self.col}' 분석 중 오류: {str(e)}")
#             log_error(traceback.format_exc())
#             return {}

#     def _get_edge_stats(self, side, n):
#         try:
#             stats = {}
#             func = (lambda x: x[:n]) if side == 'First' else (lambda x: x[-n:])
#             top = self.str_vals.apply(func).value_counts().head(3)
#             for i in range(3):
#                 val = str(top.index[i]) if i < len(top) else ""
#                 cnt = int(top.iloc[i]) if i < len(top) else 0
#                 stats[f'{side}{n}M{i+1}'] = val
#                 stats[f'{side}{n}Cnt{i+1}'] = cnt
#             return stats
#         except Exception as e:
#             log_warning(f"Edge 통계 계산 오류 (컬럼: {self.col}, side={side}, n={n}): {e}")
#             return {f'{side}{n}M{i+1}': "" for i in range(3)} | {f'{side}{n}Cnt{i+1}': 0 for i in range(3)}
