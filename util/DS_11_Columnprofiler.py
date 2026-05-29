# -*- coding: utf-8 -*-
"""
DataSense DQ Profiling System 이전 프로그램 : dq_columnprofiler.py
Qliker, 2026.01.02 Version 2.0 
"""

import os
import re
import sys
import unicodedata
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

# CSV 미로드 시 시도 인정 범위 (_SIDO_ALIASES 의 정식 명칭)
_CANONICAL_SIDO_FROM_ALIASES: frozenset[str] = frozenset(_SIDO_ALIASES.values())

_SIDO_SUFFIX_RE = re.compile(r'(특별자치)?(광역)?(특별)?(자치)?(시|도)$')

# 주소 검증용 (dq_validate.py 와 동일 로직 — validate_address 에서 사용)
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s))
    s = s.replace("\u3000", " ")
    return " ".join(s.split())


def _normalize_sido_token(tok: str) -> str:
    tok = _norm(tok)
    return _SIDO_ALIASES.get(tok, tok)


def _sido_base(s: str) -> str:
    t = _norm(s)
    t = _SIDO_SUFFIX_RE.sub("", t)
    t = (
        t.replace("경상북", "경북")
        .replace("경상남", "경남")
        .replace("전라북", "전북")
        .replace("전라남", "전남")
        .replace("충청북", "충북")
        .replace("충청남", "충남")
    )
    return t


# '123.0' 형태만 정수부로 줄이기 (모듈 레벨; DQUtils._FLOAT_ZERO_RE 와 동일 패턴)
_FLOAT_ZERO_RE = re.compile(r"^[+-]?\d+\.0+$")

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

# ======================================================================
# Oracle Type Inference (name/digits heuristics)
# ======================================================================   
CODEY_NAME_HINT    = re.compile(r"(zip|postal|우편|code|코드|id|식별|번호)$", re.IGNORECASE)

def Get_Oracle_Type(series, column_name: str | None = None):
    def _safe_to_numeric(s: pd.Series) -> pd.Series:
        return pd.to_numeric(s, errors='coerce')

    s = series.copy()
    # 전부 결측이면 즉시 NULL
    if s.isna().all():
        return "NULL"
    # 문자열 형태의 NULL 처리 (object 타입만)
    if s.dtype == object:
        s = s.replace({r'^\s*(nan|null|none)\s*$': pd.NA}, regex=True)
    s_all = s.dropna().astype(str).str.strip()
    float_zero_re = re.compile(r'^[+-]?\d+\.0+$')
    s_all = s_all.map(lambda v: v.split('.', 1)[0] if float_zero_re.fullmatch(v) else v)
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


# def validate_YYMMDD_old(val: str) -> bool:
#     return bool(re.fullmatch(r"\d{6}", str(val)))

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

def validate_YYYYMMDD(value) -> bool:
    """
    문자열 value 가 YYYYMMDD(8자리 연월일) 형태인지 검사합니다.
      1) 연월일.csv 로드로 YMD8_SET 이 있으면 → 비숫자 제거 후 앞 8자리가 YMD8_SET 에 있는지 비교
      2) 세트가 비어 있으면 → datetime 으로 달력상 유효한 날짜인지 폴백 검증
    """
    if value is None:
        return False
    s = str(value).strip()
    if not s or s.lower() in {"nan", "null", "none"}:
        return False
    if s.endswith(".0"):
        s = s[:-2]

    digits = re.sub(r"[^0-9]", "", s)
    if len(digits) < 8:
        return False
    ymd = digits[:8]

    if YMD8_SET:
        return ymd in YMD8_SET

    try:
        y, m, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])
        if not (1 <= m <= 12 and 1 <= d <= 31):
            return False
        datetime(y, m, d)
        return 1900 <= y <= 9999
    except Exception:
        return False

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


def _looks_sigungu_token(x: str) -> bool:
    x = _norm(x)
    return bool(x) and x.endswith(("시", "군", "구", "자치구", "특별자치시"))


def _validate_address_fallback_aliases(parts: list[str]) -> bool:
    """
    시도/시군구 CSV 가 없을 때: _SIDO_ALIASES 정식명 + 시군구 접미사(시/군/구…) 완화 검증.
    """
    tok = _normalize_sido_token(parts[0])
    if tok in _CANONICAL_SIDO_FROM_ALIASES:
        sido = tok
    else:
        base = _sido_base(tok)
        cand = [sd for sd in _CANONICAL_SIDO_FROM_ALIASES if _sido_base(sd) == base]
        if not cand:
            return False
        sido = cand[0]

    if sido in _SIDO_SIGUNGU_OPTIONAL:
        return len(parts) >= 2

    candidates: list[str] = []
    if len(parts) >= 2:
        candidates.append(_norm(parts[1]))
    if len(parts) >= 3:
        candidates.append(_norm(parts[1] + " " + parts[2]))
        candidates.append(_norm(parts[1] + parts[2]))
        candidates.append(_norm(parts[2]))
    candidates = [x for x in candidates if _looks_sigungu_token(x)]
    return bool(candidates)


def _validate_address_with_reference_csv(parts: list[str]) -> bool:
    """시도·시군구 참조 CSV 가 로드된 경우 정밀 검증."""
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

    candidates: list[str] = []
    if len(parts) >= 2:
        candidates.append(_norm(parts[1]))
    if len(parts) >= 3:
        candidates.append(_norm(parts[1] + " " + parts[2]))
        candidates.append(_norm(parts[1] + parts[2]))
        candidates.append(_norm(parts[2]))

    candidates = [x for x in candidates if _looks_sigungu_token(x)]
    if not candidates:
        return False

    if SIDO_TO_SIGUNGU:
        valid_gus = SIDO_TO_SIGUNGU.get(sido, set())
        if valid_gus:
            nospace = {g.replace(" ", "") for g in valid_gus}
            return any(x in valid_gus or x.replace(" ", "") in nospace for x in candidates)
    nospace_all = {g.replace(" ", "") for g in SIGUNGU_SET}
    return any(x in SIGUNGU_SET or x.replace(" ", "") in nospace_all for x in candidates)


def validate_address(value: str) -> bool:
    """
    주소(ADDRESS) 유효성:
      - 시도·시군구 CSV(SIDO_SET + SIGUNGU_SET 또는 SIDO_TO_SIGUNGU)가 있으면 목록 기반 정밀 검증
      - 없으면 _SIDO_ALIASES 의 정식 시도명 + 시군구 접미사(시/군/구…) 로 완화 검증 (항상 True 로 통과하지 않음)
    """
    try:
        s = _norm(value)
        if not s:
            return False
        parts = s.split()
        if len(parts) < 2:
            return False

        use_csv = bool(SIDO_SET) and (bool(SIGUNGU_SET) or bool(SIDO_TO_SIGUNGU))
        if use_csv:
            return _validate_address_with_reference_csv(parts)
        return _validate_address_fallback_aliases(parts)
    except Exception:
        return False


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

def is_yymmdd(pattern, top10, top_n: int = 10) -> bool:
    if pattern not in ['nnnnnn', 'nn-nn-nn', 'nn/nn/nn', 'nn.nn.nn', 'nn.nn.nn.']:
        return False

    if not top10:
        return False

    # Top10은 JSON 문자열 또는 리스트일 수 있음
    if isinstance(top10, (list, tuple, set)):
        values = [str(v) for v in top10]
    else:
        try:
            values = json.loads(top10)
        except Exception as e:
            print(f"JSON 파싱 실패: {e}")
            return False

    top_values = [v for v in values if v != "__OTHER__"][:top_n]
    if not top_values:
        return False

    valid_cnt = sum(1 for v in top_values if validate_YYMMDD(str(v)))
    return (valid_cnt / len(top_values)) >= 0.9

def is_yyyymmdd(pattern, top10, top_n: int = 10) -> bool:
    if pattern not in ['nnnnnnnn', 'nnnn-nn-nn', 'nnnn/nn/nn', 'nnnn.nn.nn', 'nnnn.nn.nn.']:
        return False

    if not top10:
        return False

    # Top10은 JSON 문자열 또는 리스트일 수 있음
    if isinstance(top10, (list, tuple, set)):
        values = [str(v) for v in top10]
    else:
        try:
            values = json.loads(top10)
        except Exception as e:
            print(f"JSON 파싱 실패: {e}")
            return False

    top_values = [v for v in values if v != "__OTHER__"][:top_n]
    if not top_values:
        return False

    valid_cnt = sum(1 for v in top_values if validate_YYYYMMDD(str(v)))
    return (valid_cnt / len(top_values)) >= 0.9

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
    Top10(JSON 문자열 또는 리스트) 상위 값들이 validate_address 로 대부분 통과하면 ADDRESS 로 간주.
    is_tel 과 동일하게 상위 N개 중 비율(기본 80%)로 판단.
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
        try:
            values = json.loads(top10_json)
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
    if is_yymmdd(pattern, top10, 10):              return 'YYMMDD'
    if is_yyyymmdd(pattern, top10, 10):             return 'YYYYMMDD'
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

def Determine_Detail_Type_new(pattern, pattern_type_cnt, format_stats, total_stats,
                          max_length, unique_count, non_null_count, top10):
    """
    점수제 분류기 초안(is_jumin, check_* 미구현)으로 호출 시 NameError 가 발생할 수 있어,
    현재는 실사용과 동일하게 Determine_Detail_Type 으로 위임합니다.
    """
    return Determine_Detail_Type(
        pattern,
        pattern_type_cnt,
        format_stats,
        total_stats,
        max_length,
        unique_count,
        non_null_count,
        top10,
    )
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
            top10_json = json.dumps(top10_counts.index.tolist(), ensure_ascii=False)
            
            top10_rates = (top10_counts / val_cnt * 100).round(2).tolist() if val_cnt > 0 else []

            res.update({
                'LenCnt': int(lens.nunique()), 'LenMin': lens.min(), 'LenMax': lens.max(),
                'LenAvg': round(lens.mean(), 1), 
                'LenMode': int(lens.mode().iloc[0]) if not lens.mode().empty else 0,
                'UniqueCnt': unique_cnt, 'Unique(%)': round(unique_cnt / val_cnt * 100, 2),
                'MinString': sorted_vals[0], 'MaxString': sorted_vals[-1],
                'ModeString': self.valid_series.mode().iloc[0] if not self.valid_series.mode().empty else "", 
                'MedianString': sorted_vals[len(sorted_vals)//2],
                'ModeCnt': int(top10_counts.iloc[0]) if not top10_counts.empty else 0,
                'Top10': top10_json,
                'Top10(%)': json.dumps(top10_rates, ensure_ascii=False)
            })

            # 3. 포맷(패턴) 분석
            patterns = self._get_pattern_custom(self.valid_series)
            pat_counts = patterns.value_counts()
            pattern_type_cnt = len(pat_counts)
            most_common_pattern = pat_counts.index[0] if not pat_counts.empty else ""
            
            res['FormatCnt'] = pattern_type_cnt
            # 상위 Top10 포맷 및 분포 비율
            if not pat_counts.empty:
                top10_patterns = pat_counts.head(10)
                res['FormatTop10'] = json.dumps(top10_patterns.index.tolist(), ensure_ascii=False)
                top10_rates = (top10_patterns / val_cnt * 100).round(2).tolist()
                res['FormatTopRate'] = json.dumps(top10_rates, ensure_ascii=False)
            else:
                res['FormatTop10'] = json.dumps([], ensure_ascii=False)
                res['FormatTopRate'] = json.dumps([], ensure_ascii=False)
            
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

            if val_cnt > 10:
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
            else:
                detail_type = ''
            
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
            f_top10 = first_n.value_counts().head(10).index.tolist()
            res[f'First{n}Top10'] = json.dumps(f_top10, ensure_ascii=False)

            # 2. 끝 N자리 Top 10
            last_n = s.str[-n:]
            l_top10 = last_n.value_counts().head(10).index.tolist()
            res[f'Last{n}Top10'] = json.dumps(l_top10, ensure_ascii=False)
            
        for n in [1, 2, 3]:
            res.update(self._get_edge_stats('First', n))
            res.update(self._get_edge_stats('Last', n))

        return res
 