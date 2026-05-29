# -*- coding: utf-8 -*-
# Copyright (c) 2026, qliker. All rights reserved.
# 2026.05.04 
"""데이터 품질 검증: 날짜·주소·연락처·코드 등. 참조 CSV는 init_reference_globals 로 적재."""

from __future__ import annotations
import os
import re
import unicodedata
from datetime import datetime
from typing import Iterable, Set, Dict, Tuple
import pandas as pd
import phonenumbers
from phonenumbers import PhoneNumberType
from pathlib import Path
import sys

DEBUG = False

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

FORMAT_MAX_VALUE = 1000
FORMAT_AVG_LENGTH = 50
MULTIPROCESSING_THRESHOLD = 1000

DEFAULT_SIDO_CSV     = r"DS_Input/Reference/시도명.csv"
DEFAULT_SIGUNGU_CSV  = r"DS_Input/Reference/시군구명.csv"
DEFAULT_KORNAME_CSV  = r"DS_Input/Reference/한국성씨.csv"
DEFAULT_COUNTRY_ISO3 = r"DS_Input/Reference/Country_ISO3.csv"
DEFAULT_B_DONG_CSV = r"DS_Input/Reference/법정동코드.csv"
DEFAULT_H_DONG_CSV = r"DS_Input/Reference/행정동코드.csv"
DEFAULT_ROAD_CSV   = r"DS_Input/Reference/도로명코드.csv"
DEFAULT_UNIT_CSV = r"DS_Input/Reference/단위코드.csv"
DEFAULT_OLD_ZIP_CSV = r"DS_Input/Reference/우편번호구3.csv"
DEFAULT_ZIP_CSV = r"DS_Input/Reference/우편번호.csv"
DEFAULT_BIZ_NAME_CSV = r"DS_Input/Reference/사업자명5.csv"
BIZ_NAME_PREFIX_LEN = 5

B_DONG_SET: Set[str] = set()
H_DONG_SET: Set[str] = set()
ROAD_CODE_SET: Set[str] = set()
YMD8_SET: Set[str] = set()
YYMMDD_SET: Set[str] = set()
SIDO_SET: Set[str] = set()
SIGUNGU_SET: Set[str] = set()
SIDO_TO_SIGUNGU: Dict[str, Set[str]] = {}
KOR_NAME_SET: Set[str] = set()
COUNTRY_ISO3_SET: Set[str] = set()
UNIT_CODE_SET: Set[str] = set()
OLD_ZIP_PREFIX_SET: Set[str] = set()
ZIP_PREFIX_SET: Set[str] = set()
ZIP_CODE_SET: Set[str] = set()
OLD_ZIP_CODE_SET: Set[str] = set()
BIZ_NAME_SET: Set[str] = set()

DEFAULT_ENCODINGS: Tuple[str, ...] = ("utf-8-sig", "cp949", "utf-8")
_SIDO_SIGUNGU_OPTIONAL = {"세종특별자치시"}

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
    "강원": "강원도", "강원특별자치도": "강원도",
    "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도",
    "경북": "경상북도", "경남": "경상남도",
}

_SIDO_SUFFIX_RE = re.compile(r'(특별자치)?(광역)?(특별)?(자치)?(시|도)$')


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

def _safe_num(x, default=0.0) -> float:
    try:
        if pd.isna(x) or x == '':
            return default
        return float(x)
    except Exception:
        return default


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s))
    s = s.replace("\u3000", " ")
    return " ".join(s.split())

def _normalize_sido_token(tok: str) -> str:
    tok = _norm(tok)
    return _SIDO_ALIASES.get(tok, tok)

def _sido_base(s: str) -> str:
    """경상북도→경북, 전라남도→전남, 강원특별자치도→강원 등 축약 베이스"""
    t = _norm(s)
    t = _SIDO_SUFFIX_RE.sub('', t)
    t = (t.replace('경상북', '경북')
           .replace('경상남', '경남')
           .replace('전라북', '전북')
           .replace('전라남', '전남')
           .replace('충청북', '충북')
           .replace('충청남', '충남'))
    return t

def _read_csv_with_encodings(path: str, encs: Iterable[str]) -> pd.DataFrame:
    last = None
    for enc in encs:
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, low_memory=False)
        except Exception as e:
            last = e
    raise RuntimeError(f"[CSV 로드 실패] {path} :: {last}")


def _require_reference_csv(path: str) -> None:
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"참조 CSV가 없습니다: {path}")

def load_kor_name_set(csv_path: str, *, use_first_char: bool = True) -> Set[str]:
    if not csv_path or not os.path.exists(csv_path):
        return set()
    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set()
    first_col = df.columns[0]
    out: Set[str] = set()
    for v in df[first_col].dropna().astype(str):
        vv = _norm(v).strip().strip('"').strip("'")
        if not vv or vv.lower() in {"nan", "null", "none"}:
            continue

        out.add(vv[:1] if use_first_char else vv)
    return out

def load_sido_set_from_csv(csv_path: str, *, strict_column: bool = True) -> Set[str]:
    if not csv_path or not os.path.exists(csv_path):
        return set()
    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set()
    if strict_column:
        if "시도명" not in df.columns:
            raise KeyError("시도명.csv에 '시도명' 컬럼이 없습니다.")
        s_col = "시도명"
    else:
        s_col = df.select_dtypes(include="object").columns.tolist()[0]
    series = df[s_col].dropna().astype(str).map(_norm)
    return {_normalize_sido_token(v) for v in series if v}

def load_sigungu_set_from_csv(csv_path: str, *, strict_column: bool = True) -> Set[str]:
    if not csv_path or not os.path.exists(csv_path):
        return set()
    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set()
    if strict_column:
        if "시군구명" not in df.columns:
            raise KeyError("시군구명.csv에 '시군구명' 컬럼이 없습니다.")
        g_col = "시군구명"
    else:
        g_col = df.select_dtypes(include="object").columns.tolist()[0]
    series = df[g_col].dropna().astype(str).map(_norm)
    return {v for v in series if v}

def load_country_iso3_set(csv_path: str) -> Set[str]:
    if not csv_path or not os.path.exists(csv_path):
        if DEBUG: print(f"[INFO] Country_ISO3 경로 없음: {csv_path}")
        return set()
    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set()
    col = None
    for c in df.columns.astype(str):
        cl = c.strip().lower()
        if cl in {"iso3","alpha-3","alpha-3 code","country_iso3","cca3"}:
            col = c; break
    if col is None:
        col = df.columns[0]
    vals = (df[col].dropna().astype(str).map(lambda x: _norm(x).upper()))
    return {v for v in vals if re.fullmatch(r"[A-Z]{3}", v)}

def load_ymd_sets_from_csv(csv_path: str) -> tuple[Set[str], Set[str]]:
    """
    연월일.csv에서 날짜 컬럼을 읽어 YYYYMMDD/YYMMDD 집합을 생성.
    - 우선 '연월일' 컬럼을 찾고, 없으면 첫 번째 object 컬럼 사용
    - 셀 값에서 숫자만 추출하여 8자리(YYYYMMDD) 또는 6자리(YYMMDD)로 정규화
    - 8자리 값을 보면 6자리(뒤 6자리)도 함께 추가
    """
    if not csv_path or not os.path.exists(csv_path):
        return set(), set()

    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set(), set()

    col = "연월일" if "연월일" in df.columns else None
    if col is None:
        obj_cols = df.select_dtypes(include="object").columns.tolist()
        if not obj_cols:
            return set(), set()
        col = obj_cols[0]

    y8: Set[str] = set()
    y6: Set[str] = set()
    for v in df[col].dropna().astype(str):
        digits = re.sub(r"[^0-9]", "", _norm(v))
        if len(digits) >= 8:
            ymd = digits[:8]
            if re.fullmatch(r"\d{8}", ymd):
                y8.add(ymd)
                y6.add(ymd[2:])
        elif len(digits) == 6 and re.fullmatch(r"\d{6}", digits):
            y6.add(digits)

    return y8, y6


def load_code_set(csv_path: str, col_name: str) -> Set[str]:
    if not csv_path or not os.path.exists(csv_path):
        return set()
    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set()
    target_col = col_name if col_name in df.columns else df.columns[0]
    vals = df[target_col].dropna().astype(str).map(lambda x: re.sub(r"\D", "", x)[:8])
    return {v for v in vals if v}


def load_unit_code_set(csv_path: str) -> Set[str]:
    if not csv_path or not os.path.exists(csv_path):
        return set()
    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set()
    out: Set[str] = set()
    for col in df.columns:
        for v in df[col].dropna().astype(str):
            t = _norm(v).strip().strip('"').strip("'")
            if not t or t.lower() in {"nan", "null", "none"}:
                continue
            out.add(t.upper())
    return out

def load_biz_name_set(csv_path: str) -> Set[str]:
    if not csv_path or not os.path.exists(csv_path):
        return set()
    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set()
    # 사업자명은 노이즈가 많아 정규화 후 접두어만 보관(성능/오탐 균형)
    out: Set[str] = set()
    for raw in df[df.columns[0]].dropna().astype(str):
        clean = _clean_company_name(raw)
        if not clean:
            continue
        out.add(clean[:BIZ_NAME_PREFIX_LEN])
    return out

def init_reference_globals(root_path: str | os.PathLike, *, strict_columns: bool = True, verbose: bool = False) -> None:
    """root_path 기준 참조 CSV 로드 → 전역 세트 채움. 지정 경로에 파일이 없으면 FileNotFoundError."""
    root = str(root_path)
    
    sido_csv    = os.path.join(root, DEFAULT_SIDO_CSV)
    sigungu_csv = os.path.join(root, DEFAULT_SIGUNGU_CSV)
    kor_csv     = os.path.join(root, DEFAULT_KORNAME_CSV)
    iso3_csv    = os.path.join(root, DEFAULT_COUNTRY_ISO3)
    biz_name_csv    = os.path.join(root, DEFAULT_BIZ_NAME_CSV)

    global SIDO_SET, SIGUNGU_SET, SIDO_TO_SIGUNGU, KOR_NAME_SET, COUNTRY_ISO3_SET
    global B_DONG_SET, H_DONG_SET, ROAD_CODE_SET, UNIT_CODE_SET, OLD_ZIP_PREFIX_SET
    global BIZ_NAME_SET

    if DEBUG or verbose:
        print(
            "[INIT] reference csv paths\n"
            f"  - sido   : {sido_csv} (exists={os.path.exists(sido_csv)})\n"
            f"  - sigungu: {sigungu_csv} (exists={os.path.exists(sigungu_csv)})\n"
            f"  - korname: {kor_csv} (exists={os.path.exists(kor_csv)})\n"
            f"  - iso3   : {iso3_csv} (exists={os.path.exists(iso3_csv)})"
            f"  - biz_name: {biz_name_csv} (exists={os.path.exists(biz_name_csv)})"
        )

    _require_reference_csv(sido_csv)
    _require_reference_csv(sigungu_csv)
    SIDO_SET = load_sido_set_from_csv(sido_csv, strict_column=strict_columns)
    SIGUNGU_SET = load_sigungu_set_from_csv(sigungu_csv, strict_column=strict_columns)
    SIDO_TO_SIGUNGU = {}

    _require_reference_csv(biz_name_csv)
    BIZ_NAME_SET = load_biz_name_set(biz_name_csv)

    _require_reference_csv(kor_csv)
    KOR_NAME_SET = load_kor_name_set(kor_csv, use_first_char=True)

    _require_reference_csv(iso3_csv)
    COUNTRY_ISO3_SET = load_country_iso3_set(iso3_csv)

    b_dong_p = os.path.join(root, DEFAULT_B_DONG_CSV)
    h_dong_p = os.path.join(root, DEFAULT_H_DONG_CSV)
    road_p = os.path.join(root, DEFAULT_ROAD_CSV)
    unit_p = os.path.join(root, DEFAULT_UNIT_CSV)
    _require_reference_csv(b_dong_p)
    _require_reference_csv(h_dong_p)
    _require_reference_csv(road_p)
    _require_reference_csv(unit_p)
    B_DONG_SET = load_code_set(b_dong_p, "법정동코드")
    H_DONG_SET = load_code_set(h_dong_p, "행정동코드")
    ROAD_CODE_SET = load_code_set(road_p, "도로명코드")
    UNIT_CODE_SET = load_unit_code_set(unit_p)

    if DEBUG or verbose:
        print(
            f"[INIT] loaded counts: SIDO:{len(SIDO_SET)} / SIGUNGU:{len(SIGUNGU_SET)} "
            f"/ BIZ_NAME_PREFIX:{len(BIZ_NAME_SET)} / KOR_NAME:{len(KOR_NAME_SET)} "
            f"/ ISO3:{len(COUNTRY_ISO3_SET)} "
            f"/ B_DONG:{len(B_DONG_SET)} / H_DONG:{len(H_DONG_SET)} "
            f"/ ROAD_CODE:{len(ROAD_CODE_SET)} / UNIT_CODE:{len(UNIT_CODE_SET)}"
        )

         
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


def validate_b_dong_code(val) -> bool:
    """법정동코드 유효성 (8자리)"""
    if val is None: return False
    s = re.sub(r"\D", "", str(val))
    if len(s) < 8: return False
    code = s[:8]
    if B_DONG_SET:
        return code in B_DONG_SET
    # 폴백: 파일 없을 시 최소한의 형식 체크 (00으로 시작하지 않는 8자리 숫자)
    return len(code) == 8 and not code.startswith("00")

def validate_h_dong_code(val) -> bool:
    """행정동코드 유효성 (8자리)"""
    if val is None: return False
    s = re.sub(r"\D", "", str(val))
    if len(s) < 8: return False
    code = s[:8]
    if H_DONG_SET:
        return code in H_DONG_SET
    return len(code) == 8 and not code.startswith("00")

def validate_road_name_code(val) -> bool:
    """도로명코드 유효성"""
    if val is None: return False
    s = re.sub(r"\D", "", str(val))
    if not s: return False
    if ROAD_CODE_SET:
        # 도로명코드는 체계에 따라 길이기 다양하므로 전체 비교 혹은 앞부분 비교
        return s in ROAD_CODE_SET or s[:8] in ROAD_CODE_SET
    return len(s) >= 8

def validate_tel_old(val: str) -> bool:
    if not isinstance(val, str):  # 입력이 문자열이 아니면 False 리턴
        return False
    if re.search(r"[A-Za-z]", val):
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

def validate_korean_number(phone_input):
    try:
        # 1. 번호 파싱
        parsed = phonenumbers.parse(phone_input, "KR")
        
        # 2. 전체적인 유효성 체크 (형식, 국번 제한 등 모두 포함)
        if not phonenumbers.is_valid_number(parsed):
            return "유효하지 않은 번호입니다."

        # 3. 번호 유형 판별
        num_type = phonenumbers.number_type(parsed)
        
        if num_type == PhoneNumberType.MOBILE:
            return f"[{phone_input}] -> 휴대폰 (Mobile)"
        elif num_type == PhoneNumberType.FIXED_LINE:
            return f"[{phone_input}] -> 유선전화 (Fixed Line)"
        elif num_type == PhoneNumberType.FIXED_LINE_OR_MOBILE:
            return f"[{phone_input}] -> 유선 또는 휴대폰 (공용)"
        else:
            return f"[{phone_input}] -> 기타 번호 유형"

    except Exception as e:
        return f"분석 불가: {e}"


def validate_korean_number_enhanced(phone_input):
    """
    한국 전화번호 분석 (강화판).

    - **7~8자리**이고 맨 앞이 2~9인 경우: `validate_tel` 과 같이 *지역번호(0XX) 생략*
      국내만 번호로 간주합니다. (`phonenumbers` 단독으로는 전부 유효 처리되지 않던 값 보완)
    - 그 외: `phonenumbers` 로 파싱 후 `is_valid_number` → 유형(휴대/유선/공용/기타).
    - 유효 번호는 아니지만 `is_possible_number` 인 경우: 형식만 가능한 수준임을 안내.

    Returns:
        str (톤은 `validate_korean_number` 와 동일)
    """
    if phone_input is None or not str(phone_input).strip():
        return "유효하지 않은 번호입니다."

    raw = str(phone_input).strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return "유효하지 않은 번호입니다."

    # validate_tel / validate_tel_old: 지역번호 없는 7~8자리 (앞자리 2~9)
    if len(digits) in (7, 8) and digits[0] in "23456789":
        return f"[{phone_input}] -> 지역번호 생략 (Local 7~8자리, 국번+가입자번호)"

    try:
        parsed = phonenumbers.parse(raw, "KR")
    except Exception as e:
        return f"분석 불가: {e}"

    if phonenumbers.is_valid_number(parsed):
        num_type = phonenumbers.number_type(parsed)
        if num_type == PhoneNumberType.MOBILE:
            return f"[{phone_input}] -> 휴대폰 (Mobile)"
        if num_type == PhoneNumberType.FIXED_LINE:
            return f"[{phone_input}] -> 유선전화 (Fixed Line)"
        if num_type == PhoneNumberType.FIXED_LINE_OR_MOBILE:
            return f"[{phone_input}] -> 유선 또는 휴대폰 (공용)"
        return f"[{phone_input}] -> 기타 번호 유형"

    if phonenumbers.is_possible_number(parsed):
        return (
            f"[{phone_input}] -> 번호 형식은 가능하나 "
            f"국가 번호체계상 유효할당(VALID)로 확인되지 않음"
        )

    return "유효하지 않은 번호입니다."

def validate_rrn(rrn):
    # 1. 형식 체크 (숫자 6자리 - 숫자 7자리)
    pattern = re.compile(r'^(\d{6})-?([1-8]\d{6})$')
    match = pattern.match(rrn)
    if not match:
        return False
    
    first_part, second_part = match.groups()
    full_number = first_part + second_part
    
    # 2. 날짜 유효성 체크
    # 성별 코드로 태어난 세기 판별
    gender_code = int(second_part[0])
    if gender_code in [1, 2, 5, 6]:
        year_prefix = "19"
    elif gender_code in [3, 4, 7, 8]:
        year_prefix = "20"
    else:
        year_prefix = "18"
        
    birth_date_str = year_prefix + first_part
    try:
        datetime.strptime(birth_date_str, "%Y%m%d")
    except ValueError:
        return False # 잘못된 날짜 (예: 991332)

    # 3. 체크섬(Checksum) 공식 검증
    # 각 자리에 곱해지는 가중치: 2,3,4,5,6,7, 8,9,2,3,4,5
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    total = 0
    for i in range(12):
        total += int(full_number[i]) * weights[i]
    
    # 공식: (11 - (총합 % 11)) % 10
    check_digit = (11 - (total % 11)) % 10
    
    return check_digit == int(full_number[12])


def validate_foreign_rn(alrn):
    """외국인등록번호 유효성 검증 (6자리-7자리)"""
    # 1. 형식 체크
    pattern = re.compile(r'^(\d{6})-?([5-8]\d{6})$') # 외국인은 성별코드가 5, 6, 7, 8로 시작
    match = pattern.match(alrn)
    if not match:
        return False
    
    first, second = match.groups()
    full = first + second
    
    # 2. 날짜 유효성 (주민번호 로직과 동일)
    year_prefix = "19" if second[0] in "56" else "20"
    try:
        datetime.strptime(year_prefix + first, "%Y%m%d")
    except ValueError:
        return False

    # 3. 외국인 전용 체크섬 공식
    # 가중치: 2,3,4,5,6,7, 8,9,2,3,4,5
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    total = sum(int(full[i]) * weights[i] for i in range(12))
    
    # 공식: (13 - (total % 11)) % 10
    check_digit = (13 - (total % 11)) % 10
    
    return check_digit == int(full[12])


def validate_driver_license(dln):
    """운전면허번호 형식 검증 (지역번호-연도-일련번호-체크섬)"""
    # 하이픈 제거 후 12자리 숫자
    clean_dln = re.sub(r'[^0-9]', '', dln)
    
    if len(clean_dln) != 12:
        return False
    
    # 패턴 설명: 지역(11~28)-연도(00~99)-일련번호(6자리)-체크섬(2자리)
    # (실제 업무에서는 지역 코드가 텍스트인 경우 숫자로 변환하는 로직이 선행되어야 함)
    pattern = re.compile(r'^(11|12|13|14|15|16|17|18|19|20|21|22|23|24|25|26|28)\d{10}$')
    return bool(pattern.match(clean_dln))

def validate_passport(passport):
    """여권번호 형식 검증"""
    # M: 일반여권, S: 거주여권, R: 거주여권 등
    # 차세대 여권은 숫자와 문자가 혼합된 형태(예: M123A4567)일 수 있음
    passport = passport.upper().replace("-", "").strip()
    
    # 1. 구권: 영문 1자리 + 숫자 8자리
    old_pattern = re.compile(r'^[MSGRD][0-9]{8}$')
    # 2. 신권(차세대): 영문 1자리 + 숫자 3자리 + 영문 1자리 + 숫자 4자리
    new_pattern = re.compile(r'^[MSGRD][0-9]{3}[A-Z][0-9]{4}$')
    
    if old_pattern.match(passport) or new_pattern.match(passport):
        return True
    return False

def validate_account_info(value, info_type="ID"):
    """
    계정 관련 정보(ID, 닉네임)의 일반적인 형식을 체크합니다.
    비밀번호는 복잡도 설정을 기준으로 검증합니다.
    """
    value = str(value).strip()
    
    if info_type == "ID":
        # 영문 소문자/숫자 조합 5~20자
        return bool(re.match(r'^[a-z0-9_.-]{5,20}$', value))
    
    elif info_type == "PASSWORD":
        # 최소 8자, 영문/숫자/특수문자 포함 여부 (보안 권고 기준)
        has_upper = any(c.isupper() for c in value)
        has_lower = any(c.islower() for c in value)
        has_digit = any(c.isdigit() for c in value)
        has_spec = any(c in "!@#$%^&*()" for c in value)
        return len(value) >= 8 and (has_lower + has_digit + has_spec >= 2)

    return False

def validate_network_identifier(value, id_type="IP"):
    """IP 주소(IPv4/IPv6) 및 MAC 주소 형식을 검증합니다."""
    value = str(value).strip()

    if id_type == "IP":
        # IPv4 패턴
        ipv4_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        # IPv6 패턴 (단순화 버전)
        ipv6_pattern = r'^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$'
        return bool(re.match(ipv4_pattern, value) or re.match(ipv6_pattern, value))

    elif id_type == "MAC":
        # XX:XX:XX:XX:XX:XX 또는 XX-XX-XX-XX-XX-XX 형식
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
        return bool(re.match(mac_pattern, value))

    return False

def validate_advertising_id(value):
    """ADID(Android) 및 IDFA(iOS) 형식을 검증합니다. (UUID 형식)"""
    value = str(value).strip().lower()
    # 8-4-4-4-12 형태의 16진수 UUID 패턴
    adid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    return bool(re.match(adid_pattern, value))

def _cookie_format_matches(value) -> bool:
    """전형적인 HTTP 쿠키(Key=Value) 문자열 형태인지 확인합니다."""
    cookie_pattern = r'^([^=]+)=([^;]+)(;\s*[^=]+=[^;]+)*$'
    return bool(re.match(cookie_pattern, str(value)))


def validate_finance_info(value, info_type="CARD"):
    """카드번호(Luhn 알고리즘) 및 계좌번호 형식을 검증합니다."""
    val_str = re.sub(r'[^0-9]', '', str(value))
    
    if info_type == "CARD":
        # 1. 길이 체크 (보통 14, 15, 16자리)
        if len(val_str) not in [14, 15, 16, 19]: return False
        # 2. Luhn 알고리즘 체크섬 검증
        total = 0
        reverse_digits = val_str[::-1]
        for i, digit in enumerate(reverse_digits):
            n = int(digit)
            if i % 2 == 1:
                n *= 2
                if n > 9: n -= 9
            total += n
        print(total, total % 10)
        return total % 10 == 0

    elif info_type == "BANK_ACCOUNT":
        # 한국 주요 은행 계좌번호 패턴 (10~14자리 숫자)
        return bool(re.match(r'^\d{10,14}$', val_str))
    
    return False

def validate_car_number(value):
    """한국 자동차 번호판 형식을 검증합니다."""
    # 예: 12가 3456, 123가 4567, 서울 00 가 0000 등
    pattern = r'^(\d{2,3}[가-힣]\s?\d{4})|([가-힣]{2}\s?\d{2}[가-힣]\s?\d{4})$'
    return bool(re.match(pattern, str(value).strip()))

def detect_sensitive_content(value):
    """텍스트 데이터 내 민감 키워드 포함 여부를 식별합니다."""
    val_str = str(value).replace(" ", "")
    
    # 1. 신념 및 가치관 관련 키워드
    belief_keywords = ['기독교', '불교', '천주교', '이슬람', '무교', '정당', '위원회', '민주당', '국민의힘']
    # 2. 사회적 정보 및 성생활 (가이드라인 준수)
    social_keywords = ['전과', '금고형', '집행유예', '노동조합', '노조', '성적지향', '성생활']
    # 3. 건강 및 생체 정보
    health_keywords = ['혈액형', '확진', '완치', '병력', '질환', '지문', '홍채', '안면인식']

    for word in belief_keywords:
        if word in val_str: return "SENSITIVE_BELIEF"
    for word in social_keywords:
        if word in val_str: return "SENSITIVE_SOCIAL"
    for word in health_keywords:
        if word in val_str: return "SENSITIVE_HEALTH"
        
    return None    

def validate_location_gps(value):
    """GPS 좌표(위도, 경도) 형식을 검증합니다."""
    # 예: 37.5665, 126.9780
    pattern = r'^-?\d{1,3}\.\d+,\s?-?\d{1,3}\.\d+$'
    return bool(re.match(pattern, str(value).strip()))

def is_academic_info(value):
    """학교명, 학번 등 학력 관련 패턴을 확인합니다."""
    val_str = str(value).strip()
    # 대학교/대학원 명칭 혹은 학번(8~10자리 숫자 중 특정 패턴)
    if "대학교" in val_str or "대학원" in val_str:
        return "SCHOOL_NAME"
    if re.match(r'^(19|20)\d{6,8}$', val_str): # 학번(입학년도 포함)
        return "STUDENT_ID"
    return None

import re

def detect_medical_pii(value):
    """의료 및 건강 관련 키워드와 패턴을 탐지합니다."""
    val_str = str(value).replace(" ", "")

    # 1. 혈액형 패턴 (Rh+ A, B, O, AB 등)
    blood_pattern = r'^(Rh[+-])?(A|B|O|AB)(형)?$'
    if re.match(blood_pattern, val_str, re.IGNORECASE):
        return "MEDICAL_BLOOD_TYPE"

    # 2. 질병 및 의료 키워드 (사전 기반 매칭)
    health_keywords = [
        '당뇨', '고혈압', '확진', '양성', '음성', '처방전', 
        '진단서', '입원', '수술', '병력', '질환', '알레르기'
    ]
    for word in health_keywords:
        if word in val_str:
            return "MEDICAL_HEALTH_HISTORY"

    # 3. 생체 데이터 식별자 (보통 시스템 ID 형태)
    if any(tag in val_str.upper() for tag in ['BIO_ID', 'IRIS_', 'FINGER_']):
        return "MEDICAL_BIOMETRIC_DATA"

    return None

import re

def detect_hr_legal_pii(value):
    val_str = str(value).replace(" ", "")

    # 1. 사번 패턴 (회사마다 다르지만 보통 연도+일련번호 형식)
    # 예: 20260101, HR-10293
    emp_id_pattern = r'^([12]\d{3}[0-9]{4})|(HR|EMP)-\d{4,6}$'
    if re.match(emp_id_pattern, val_str):
        return "HR_EMPLOYEE_ID"

    # 2. 법률/징계 키워드 (민감도가 매우 높음)
    legal_keywords = [
        '정직', '감봉', '해고', '징계위원회', '소송', 
        '피고인', '원고', '가압류', '지급명령', '비밀유지'
    ]
    for word in legal_keywords:
        if word in val_str:
            return "LEGAL_SENSITIVE_CONTENT"

    # 3. 자격증 번호 (국가기술자격 등)
    # 예: 12-34-567890 (일반적인 자격증 번호 형식)
    cert_pattern = r'^\d{2}-\d{2}-\d{6}$'
    if re.match(cert_pattern, val_str):
        return "HR_CERTIFICATE_NO"

    return None


def validate_strict_date(value):
    # 숫자만 남기기 (2025-02-30 -> 20250230)
    clean_val = "".join(filter(str.isdigit, str(value)))
    
    if len(clean_val) == 8:
        try:
            # 존재하지 않는 날짜면 여기서 에러 발생
            datetime.strptime(clean_val, "%Y%m%d")
            return True
        except ValueError:
            return False
    return False

def validate_biz_no(biz_no):
    # 숫자만 추출
    biz_no = "".join(filter(str.isdigit, biz_no))
    if len(biz_no) != 10:
        return False
    
    # 가중치: 1 3 7 1 3 7 1 3 5
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = 0
    
    # 1. 앞 8자리 가중치 곱해서 합산
    for i in range(8):
        total += int(biz_no[i]) * weights[i]
    
    # 2. 9번째 자리 처리 (특이 로직)
    # (9번째 숫자 * 5)를 10으로 나눈 몫과 나머지를 더함
    temp = int(biz_no[8]) * 5
    total += (temp // 10) + (temp % 10)
    
    # 3. 검증 번호 확인
    # (10 - (합계 % 10)) % 10
    check_digit = (10 - (total % 10)) % 10
    
    return check_digit == int(biz_no[9])

def validate_corp_no(corp_no):
    # 숫자만 추출
    corp_no = "".join(filter(str.isdigit, corp_no))
    if len(corp_no) != 13:
        return False
    
    # 가중치: 1 2 1 2 1 2 1 2 1 2 1 2 (연속되는 1, 2)
    weights = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    
    for i in range(12):
        total += int(corp_no[i]) * weights[i]
    
    # 검증 공식: (10 - (총합 % 10)) % 10
    check_digit = (10 - (total % 10)) % 10
    
    return check_digit == int(corp_no[12])


def validate_tel(val: str) -> bool:
    """한국 전화번호 (지역번호·휴대폰)."""
    if not isinstance(val, str):
        return False

    if re.search(r"[A-Za-z]", val):
        return False

    digits = "".join(filter(str.isdigit, val))
    n = len(digits)
    
    if n < 7 or n > 11:
        return False

    if n in (7, 8):
        return digits[0] in "23456789"
    
    if digits.startswith("02"):
        local = digits[2:]
        return len(local) in (7, 8) and local[0] not in {"0", "1"}
    
    if digits.startswith("010"):
        local = digits[3:]
        return 7 <= len(local) <= 8 and local[0] not in {"0", "1"}
    
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


def validate_zip_code(value) -> bool:
    """
    대한민국 5자리 우편번호 유효성 검사:
    1) 5자리 숫자인가?
    2) 실제 사용 가능한 대역(01xxx ~ 63xxx) 안에 있는가?
    """
    if value is None:
        return False
    
    # 1. 전처리: 문자열화 및 하이픈/공백 제거
    s = re.sub(r"\D", "", str(value))
    
    # 2. 기본 길이 체크: 반드시 5자리여야 함
    if len(s) != 5:
        return False
    
    # 3. 대역(Range) 검증
    # 현재 대한민국 우편번호는 01000(서울) ~ 63644(제주) 사이의 범위를 가집니다.
    # ※ 00*** 대역은 현재 사용되지 않습니다.
    try:
        zip_int = int(s)
        # 01000 미만이거나 64000 이상인 경우 가짜 번호일 확률이 높음
        if 1000 <= zip_int <= 63999:
            return True
        return False
    except ValueError:
        return False

def validate_zip_code_old(val: str) -> bool:
    """
    구 우편번호(6자리) 유효성 검사:
    - nnn-nnn 또는 nnnnnn 형식인지 확인
    - 앞 3자리가 유효 접두어 세트에 존재하는지 확인
    """
    if val is None:
        return False
    
    # 1. 전처리 (.0 제거 및 공백 제거)
    s = str(val).strip()
    if s.endswith('.0'): s = s[:-2]
    
    # 2. 형식 검증 (숫자 6자리 혹은 3자리-3자리)
    if not re.fullmatch(r"^\d{3}-?\d{3}$", s):
        return False
        
    # 3. 앞 3자리 추출 및 세트 비교
    digits = re.sub(r"\D", "", s)
    prefix = digits[:3]
    
    if OLD_ZIP_PREFIX_SET:
        return prefix in OLD_ZIP_PREFIX_SET
        
    # 참조 파일이 없는 경우 최소한의 형식(6자리 숫자)만 체크
    return len(digits) == 6

_UNIT_FALLBACK_DENY = frozenset({
    "NAME", "DATA", "TYPE", "CODE", "TEXT", "VALUE", "NULL", "NONE",
})



def validate_kor_name(value: str) -> bool:
    if not value: return False
    
    # s = _norm(str(value)).replace(" ", "")
    
    # if not re.fullmatch(r"^[가-힣]{2,5}$", s):
    #     return False

    # if not KOR_NAME_SET:
    #     if DEBUG:
    #         print("KOR_NAME_SET is empty")
    #     return True

    return str(value)[0] in KOR_NAME_SET


def validate_country_code(value: str) -> bool:
    """ISO 3166-1 alpha-3 전용. 세트가 있으면 membership, 없으면 3대문자 형식만 체크."""
    s = str(value).strip().upper()
    if not s or not re.fullmatch(r"[A-Z]{3}", s):
        return False
    return (s in COUNTRY_ISO3_SET) if COUNTRY_ISO3_SET else True

def validate_address(value: str) -> bool:
    if not SIDO_SET or not SIGUNGU_SET:
        return False # 데이터 로드 확인 필요

    try:
        s = _norm(value)
        if not s: return False
        parts = s.split()
        if len(parts) < 2: return False

        # ---------------------------------------------------------
        # 1단계: 시도(SIDO) 확인
        # ---------------------------------------------------------
        input_sido = parts[0]
        # '서울특별시' vs '서울' 등 양방향 포함 관계 확인
        is_valid_sido = any(
            input_sido in s or s in input_sido 
            for s in SIDO_SET if len(s) >= 2
        )
        
        if not is_valid_sido:
            return False

        # ---------------------------------------------------------
        # 2단계: 시군구(SIGUNGU) 확인 (단어별 개별 매칭)
        # ---------------------------------------------------------
        # parts[1] (성남시) 혹은 parts[2] (분당구) 중 하나라도 셋에 있는지 확인
        # '시군구명.csv'에 단어 단위로 저장된 데이터에 최적화
        is_valid_sigungu = False
        
        # 주소의 2번째, 3번째 단어를 검사
        for i in range(1, min(len(parts), 3)):
            target = parts[i].replace(" ", "")
            # 시군구 셋에 정확히 일치하거나 포함되는 명칭이 있는지 확인
            if any(target == g.replace(" ", "") for g in SIGUNGU_SET):
                is_valid_sigungu = True
                break
        
        # ---------------------------------------------------------
        # 3단계: 최종 판정 및 보조 확인
        # ---------------------------------------------------------
        if is_valid_sido and is_valid_sigungu:
            return True

        # 시도는 맞는데 시군구명이 특이한 경우 (예: 도로명 주소 특이 케이스)
        if is_valid_sido and len(parts) >= 2:
            # 두 번째 혹은 세 번째 단어가 '동/로/길/구/시'로 끝나면 주소로 간주
            for i in range(1, min(len(parts), 3)):
                if any(parts[i].endswith(suffix) for suffix in ("시", "군", "구", "로", "길", "동")):
                    return True

        return False
    except Exception:
        return False


def _clean_company_name(text: str) -> str:
    if not text: return ""
    # 유니코드 정규화 및 소문자화 (영문 사업자 대응)
    text = unicodedata.normalize('NFKC', str(text)).lower()
    # 법인격 키워드 및 특수문자, 공백 제거
    text = re.sub(r'\(주\)|주식회사|\(유\)|유한회사|\(사\)|사단법인|\(재\)|재단법인|㈜|㈲|㈔', '', text)
    text = re.sub(r'[^a-z0-9가-힣]', '', text)
    return text.strip()

def validate_company_name(value: str) -> bool:
    if not value: return False
    
    raw_val = str(value)
    clean_val = _clean_company_name(raw_val)
    if not clean_val: return False

    # 전략 1: 참조 데이터셋(Set)에 존재하는지 확인 (접두어 기반)
    key = clean_val[:BIZ_NAME_PREFIX_LEN]
    if key and key in BIZ_NAME_SET:
        return True

    # 전략 2: 데이터셋에 없더라도 '주식회사' 등 강력한 증거가 있는 경우
    # 이때는 글자 수가 너무 짧지 않은지(노이즈 방지)만 체크
    if any(kw in raw_val for kw in ['(주)', '주식회사', '㈜', '유한회사', '(유)']):
        return len(clean_val) >= 2
    
    # 전략 3: 부분 일치 (참조 데이터가 사업자명 앞부분을 포함하는지)
    # 5자리 자르기 대신 최소 3자 이상 매칭되는 '포함 관계'를 봅니다.
    # (성능을 위해 clean_val이 길 때만 수행하거나 생략 가능)
    if len(clean_val) >= 4:
        # BIZ_NAME_SET이 크면 루프는 느릴 수 있으므로 주의
        # 필요시 인덱싱된 접두사 사전 등을 별도로 구축하여 성능 보강
        pass

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
    """날짜+시각 문자열 (pandas 파싱)."""
    if val is None:
        return False
    s = str(val).strip()
    if not s or s.lower() in {"nan", "null", "none"}:
        return False
    if s.endswith(".0"):
        s = s[:-2]
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return False
        y = int(ts.year)
        return 1800 <= y <= 2200
    except Exception:
        return False

def _strip_decimal_zero(value):
    text = str(value).strip()
    if text.endswith('.0'):
        return text[:-2]
    return text


def get_pattern(value):
    try:
        text = _strip_decimal_zero(value)[:20]
        p = []
        for ch in text:
            if ch.isdigit(): p.append('n')
            elif '가' <= ch <= '힣': p.append('K')
            elif ch.isupper(): p.append('A')
            elif ch.islower(): p.append('a')
            elif ch in '(){}[]-=. :@/*': p.append(ch)
            else: p.append('s')
        return "".join(p)
    except Exception:
        return ""


def _get_clean_pattern(pattern):
    return re.sub(r'[^nKAask]', '', pattern)


def is_timestamp(value, pattern):
    clean_p = _get_clean_pattern(pattern)
    if 10 <= len(clean_p) <= 20 and clean_p.startswith('nnnn'):
        return validate_timestamp(value)
    return False


def is_timestamp_old(value, pattern):
    if pattern not in ['nnnn-nn-nn nn:nn:nn', 'nnnn-nn-nn nn:nn:nn.nnnnnn', 
            'nnnn-nn-nn nn:nn:nn.', 'nnnn-nn-nn nn:nn', 'nnnn-nn-nn n:nn', 'nnnn-nn-nn nn:nn AA', 'nnnn-n-nn nn:nn AA']:
        return False
    return validate_timestamp(value)

def is_time(value, pattern):
    clean_p = _get_clean_pattern(pattern)
    # nnnn(4자, 12:30) ~ nnnnnn(6자, 12:30:59)
    if len(clean_p) in [4, 5, 6] and not pattern.startswith('nnnn'):
        return validate_time(value)
    return False

def is_time_old(value, pattern):
    if pattern not in ['nn:nn.n', 'nn:nn:nn', 'nn:nn:nn.nnnnnn', 'nn:nn:nn.']:
        return False
    if DEBUG:
        print("is_time", value, pattern)
    return validate_time(value)

def is_yymmdd(value, pattern):
    """YYMMDD: 숫자 6자리 골격이거나 구분자 포함 패턴 모두 수용."""
    # clean_p = _get_clean_pattern(pattern)
    # if clean_p == "nnnnnn":
    #     return validate_YYMMDD(value)
    if pattern in ("nnnnnn", "nn-nn-nn", "nn/nn/nn", "nn.nn.nn"):
        return validate_YYMMDD(value)
    return False

def is_yearmonth(value, pattern):
    if pattern not in ['nnnnnn', 'nnnn-nn', 'nnnn/nn', 'nnnn.nn', 'nnnnKnnK']:
        return False
    return validate_yearmonth(value)

def is_year(value, pattern):
    if pattern not in ['nnnn', 'nnnnK']:
        return False
    return validate_year(value)
    
def is_datechar(value, pattern):
    if pattern not in ['nnnnnnnn', 'nnnn-nn-nn', 'nnnn/nn/nn', 'nnnnKnnKnnK', 'nnnn.nn.nn', 'nnnn. n. nn.']:
        return False
    return validate_date(value)
def is_biz_no(value, pattern):
    if _get_clean_pattern(pattern) == 'nnnnnnnnnn':
        return validate_biz_no(value)
    return False

def is_corp_no(value, pattern):
    if _get_clean_pattern(pattern) == 'nnnnnnnnnnnnn':
        return validate_corp_no(value)
    return False

def is_rrn(value, pattern):
    if _get_clean_pattern(pattern) == 'nnnnnnnnnnnnn':
        return validate_rrn(value)
    return False

def is_zip_code(value, pattern):
    if pattern not in ['nnnnn']:
        return False
    return validate_zip_code(value)

def is_old_zip_code(value, pattern):
    if pattern not in ['nnnnnn', 'nnn-nnn']:
        return False
    return validate_zip_code_old(value)
def is_road_name_code(value, pattern):
    if pattern not in ['nnnnnnnnnn']:
        return False
    return validate_road_name_code(value)

def is_b_dong_code(value, pattern):
    if pattern not in ['nnnnnnnnnn']:
        return False
    return validate_b_dong_code(value)

def is_h_dong_code(value, pattern):
    if pattern not in ['nnnnnnnnnn']:
        return False
    return validate_h_dong_code(value)

def is_tel(value, pattern):
    clean_p = _get_clean_pattern(pattern)
    # 기호 없이 숫자만 8개인 경우('nnnnnnnn')는 TEL에서 제외하거나 점수를 낮춤
    if pattern == 'nnnnnnnn': 
        return False # 날짜와 경합 방지를 위해 숫자만 8자리는 TEL로 보지 않음
    if len(clean_p) in [7, 8, 9, 10, 11]:
        return validate_tel(value)
    return False

def is_cellphone(value, pattern):
    clean_p = _get_clean_pattern(pattern)
    if clean_p == 'nnnnnnnnnnn' or clean_p == 'nnnnnnnnnn':
        return validate_cellphone(value)
    return False

def is_car_number(value, pattern):
    if pattern not in ['KKnnKnnnn', 'nnKnnnn', 'nnnKnnnn']:
        return False
    return validate_car_number(value)

def is_kor_name(value, pattern):
    if len(str(value)) > 4:
        return False
    if pattern  in ['KKK', 'KKKK', 'K KK', 'KK KK']:
        return str(value)[0] in KOR_NAME_SET
    return False
    # return validate_kor_name(value)

def is_kor_name_marked(value, pattern):
    if pattern not in ['KK*', 'K*K']:
        return False
    return str(value)[0] in KOR_NAME_SET
    # return validate_kor_name(value)

def is_address_old(value, pattern) -> bool:
    if len(pattern) < 8 or pattern.count("K") < 6 or pattern.count(" ") < 3:
        return False
    return validate_address(value)

def is_address(value, pattern):
    if not SIDO_SET or not SIGUNGU_SET:
        # 데이터가 로드되지 않았을 경우 로그 출력 (실제 운영시 삭제 가능)
        print("Reference Data not loaded.")
        return False

    val_str = str(value).strip()
    parts = val_str.split()
    if len(parts) < 2:
        return False

    # ---------------------------------------------------------
    # 1. 시도(SIDO) 확인: '서울' in '서울특별시' or '서울특별시' in '서울'
    # ---------------------------------------------------------
    sido_input = parts[0]
    is_valid_sido = any(
        sido_input in s or s in sido_input 
        for s in SIDO_SET if len(s) >= 2
    )

    if not is_valid_sido:
        return False

    # ---------------------------------------------------------
    # 2. 시군구(SIGUNGU) 및 주소 키워드 확인 (단어별 루프)
    # ---------------------------------------------------------
    # parts[1] (예: 강남구), parts[2] (예: 논현로) 등을 순회하며 검사
    for i in range(1, len(parts)):
        word = parts[i].replace(" ", "")
        if not word: continue

        # (1) 시군구 DB에 정확히 있는지 확인 (예: '분당구'가 CSV에 있는 경우)
        if any(word == g.replace(" ", "") for g in SIGUNGU_SET):
            return True

        # (2) 도로명/지번 키워드 접미사 확인 (예: '황새울로', '가산동')
        # DB에 해당 단어가 없더라도 주소 형식이 확실하면 True
        if any(word.endswith(sx) for sx in ("시", "군", "구", "로", "길", "동", "가")):
            # 단, '로', '길'의 경우 숫자와 조합된 경우도 고려 (예: 마장로512번길)
            return True

    # 3. 복합 단어 확인 (예: '성남시' + '분당구' 조합이 DB에 한 줄로 있는 경우 대비)
    if len(parts) >= 3:
        combined = (parts[1] + parts[2]).replace(" ", "")
        if any(combined == g.replace(" ", "") for g in SIGUNGU_SET):
            return True

    return False

def is_company_name(value, pattern):
    # value 에 공백이 있으면 False 리턴 
    if " " in str(value):
        return False
    # 패턴에 유니코드 기호가 포함되어 있거나 (주) 형식이 보일 때
    # 'S'는 특수문자를 의미한다고 가정 (시스템에 따라 다를 수 있음)
    if "(" in pattern or ")" in pattern or "S" in pattern:
        return validate_company_name(value)
    
    # 한글과 영문이 섞인 긴 이름인 경우도 검사
    if "K" in pattern and len(pattern) >= 3:
        return validate_company_name(value)
        
    return False

def is_foreign_rn(value, pattern):
    if pattern not in ['nnnnnn-nnnnnnnn', 'nnnnnnnnnnnnnnnn']:
        return False
    return validate_foreign_rn(value)

def is_driver_license(value, pattern):
    if pattern not in ['nnnnnnnnnnnn', 'nn-nn-nnnnnn-nn']:
        return False
    return validate_driver_license(value)

# 구권 : M12984732, 신권 : M115R7062 M882W1459
def is_passport(value, pattern):
    if pattern not in ['Annnnnnnn', 'AnnnAnnnn']:
        return False
    return validate_passport(value)

def is_adid(value, pattern):
    if pattern not in ['nnnnnnnn-nnnnnnnn']:
        return False
    return validate_advertising_id(value)

def is_cookie_format(value, pattern):
    return _cookie_format_matches(value)

# 예: 4111-1111-1111-1111(16), Amex 15자리 nnnn-nnnnnn-nnnn, 19자리는 validate_finance_info에서만 허용
def is_card_number(value, pattern):
    if pattern not in ['nnnn-nnnn-nnnn-nnnn', 'nnnn-nnnnnn-nnnnn' , 'nnnn nnnn nnnn nnnn', 'nnnn nnnnnn nnnnn']:
        return False
    n_in_pattern = pattern.count("n")
    # 허용 패턴은 15·16자리 표기만 포함. (validate_finance_info 는 14·19자리도 허용하나 대응 패턴 템플릿 없음)
    if n_in_pattern not in (15, 16) or pattern.count(" ") > 3 or (
        pattern.count("-") > 3 or pattern.count("K") > 0 or pattern.count("a") > 0  or pattern.count(":") > 0 or pattern.count(".") > 0
    ):
        return False

    return validate_finance_info(value, 'CARD')

def is_account_info(value, pattern):
    if len(pattern) < 14 or len(pattern) > 17 or pattern.count("n") > 15: 
        return False
    if (pattern.count(" ") > 3 or pattern.count(":") > 0 or pattern.count(".") > 0 or
        pattern.count("-") > 3 or pattern.count("K") > 0 or pattern.count("a") > 0):
        return False
    return validate_finance_info(value, 'BANK_ACCOUNT')

def is_network_identifier(value, pattern):
    if len(pattern) < 8 or len(pattern) > 20 or pattern.count(" ") > 3 or pattern.count("K") > 1:
        return False
    return validate_network_identifier(value)

def is_email(value, pattern):
    if '@' in pattern:
        return validate_email(value)
    return False

def is_url(value, pattern):
    if '://' in pattern or 'www' in value.lower():
        return validate_url(value)
    return False

def is_latitude(value, pattern):
    if pattern not in ['nn.nnnn','nn.nnnnn','nn.nnnnnn','nn.nnnnnnn','nn.nnnnnnnn']:
        return False
    return validate_latitude(value)

def is_country_code(value, pattern):
    if pattern not in ['[A-Z]{3}', '[a-z]{3}']:
        return False
    return validate_country_code(value)

def is_tel_old(value, pattern):
    if pattern not in ['nnn-nnn-nnnn','nn-nnnn-nnnn','nn-nnn-nnnn','nnn-nnnn','nnnn-nnnn','nnnnnnn','nnnnnnnn','nnnnnnnnnn']:
        return False
    return validate_tel(value)

def is_cellphone_old(value, pattern):
    if pattern not in ['nnn-nnnn-nnnn','nnnnnnnnnnn']:
        return False
    return validate_cellphone(value)

#------------------------------------------------------------------------
#   실제로 매핑을 수행하는 함수 
#------------------------------------------------------------------------
# 검증기별 기본 우선순위 설정 (점수가 높을수록 우선순위가 높음)
# 체크섬이 있거나 패턴이 복잡한 항목에 높은 점수를 부여합니다.
VALIDATORS = [
    (is_timestamp, 'TIMESTAMP'),
    (is_time, 'TIME'),
    (is_yymmdd, 'YYMMDD'),
    (is_datechar, 'DATECHAR'),
    (is_yearmonth, 'YEARMONTH'),
    (is_year, 'YEAR'),
    (is_rrn, 'RRN'),
    (is_biz_no, 'BIZ_NO'),
    (is_corp_no, 'CORP_NO'),
    (is_road_name_code, 'ROAD_CODE'),
    (is_b_dong_code, 'B_DONG_CODE'),
    (is_h_dong_code, 'H_DONG_CODE'),
    (is_zip_code, 'ZIP_CODE'),
    (is_old_zip_code, 'ZIP_CODE_OLD'),
    (is_tel, 'TEL'),
    (is_cellphone, 'CELLPHONE'),
    (is_car_number, 'CAR_NUMBER'),
    (is_email, 'EMAIL'),
    (is_url, 'URL'),
    (is_kor_name, 'NAME_KOR'),
    (is_kor_name_marked, 'NAME_KOR_MARKED'),
    (is_address, 'ADDRESS'),
    (is_company_name, 'COMPANY_NAME'),
    (is_foreign_rn, 'FOREIGN_RN'),
    (is_driver_license, 'DRIVER_LICENSE'),
    (is_passport, 'PASSPORT'),
    (is_adid, 'ADID'),
    (is_cookie_format, 'COOKIE_FORMAT'),
    (is_network_identifier, 'NETWORK_IDENTIFIER'),
    (is_card_number, 'CARD_NUMBER'),
    (is_account_info, 'BANK_ACCOUNT'),
]

# 속성별 우선순위(priority)·매칭 허용 비율(tolerance). find_label·컬럼 집계 동률 시 priority로 결정.
DEFAULT_TOLERANCE = 0.8
VALIDATOR_CONFIG: Dict[str, Dict[str, float]] = {
    "NULL": {"priority": 100, "tolerance": 1.0},
    "RRN": {"priority": 100, "tolerance": 0.6},
    "BIZ_NO": {"priority": 100, "tolerance": 0.7},
    "CORP_NO": {"priority": 100, "tolerance": 0.7},
    "EMAIL": {"priority": 90, "tolerance": 0.8},
    "URL": {"priority": 90, "tolerance": 0.8},
    "DATECHAR": {"priority": 88, "tolerance": 0.9},
    "YYMMDD": {"priority": 88, "tolerance": 0.9},
    "YEARMONTH": {"priority": 88, "tolerance": 0.9},
    "TIMESTAMP": {"priority": 60, "tolerance": 0.9},
    "ZIP_CODE": {"priority": 45, "tolerance": 0.8},
    "ZIP_CODE_OLD": {"priority": 40, "tolerance": 0.8},
    "ROAD_CODE": {"priority": 30, "tolerance": 0.8},
    "B_DONG_CODE": {"priority": 30, "tolerance": 0.8},
    "H_DONG_CODE": {"priority": 30, "tolerance": 0.8},
    "YEAR": {"priority": 20, "tolerance": 0.9},
    "TIME": {"priority": 20, "tolerance": 0.9},
    "NAME_KOR": {"priority": 65, "tolerance": 0.8},
    "NAME_KOR_MARKED": {"priority": 65, "tolerance": 0.8},
    "COMPANY_NAME": {"priority": 65, "tolerance": 0.5},
    "ADDRESS": {"priority": 70, "tolerance": 0.5},
    "TEL": {"priority": 80, "tolerance": 0.9},
    "CELLPHONE": {"priority": 85, "tolerance": 0.8},
    "CAR_NUMBER": {"priority": 85, "tolerance": 0.8},
    "CARD_NUMBER": {"priority": 85, "tolerance": 0.8},
    "BANK_ACCOUNT": {"priority": 85, "tolerance": 0.8},
    "NETWORK_IDENTIFIER": {"priority": 85, "tolerance": 0.8},
    "ADID": {"priority": 85, "tolerance": 0.8},
    "COOKIE_FORMAT": {"priority": 85, "tolerance": 0.8},
    "PASSPORT": {"priority": 85, "tolerance": 0.8},
    "DRIVER_LICENSE": {"priority": 85, "tolerance": 0.8},
    "FOREIGN_RN": {"priority": 85, "tolerance": 0.8},
}


def validator_priority(label: str) -> int:
    cfg = VALIDATOR_CONFIG.get(label)
    if isinstance(cfg, dict):
        return int(cfg.get("priority", 10))
    return 10


def validator_tolerance(label: str) -> float:
    cfg = VALIDATOR_CONFIG.get(label)
    if isinstance(cfg, dict) and "tolerance" in cfg:
        return float(cfg["tolerance"])
    return DEFAULT_TOLERANCE

def find_label(value):
    """
    모든 검증기를 테스트하여 매칭된 결과를 스코어 기반 내림차순으로 리턴합니다.
    리턴 형식: (best_label, best_score, all_candidates)
    """
    text = str(value).strip()
    if text.endswith('.0'):
        text = text[:-2]
    
    # 1. Null/Empty 처리
    if not text or text.lower() in ['nan', 'null', 'none']:
        return 'NULL', 100, [('NULL', 100)]

    # 2. 패턴 생성 (1회)
    pattern = get_pattern(text)
    
    matched_list = [] # (label, score)를 담을 리스트

    # 3. 모든 검증기 전수 조사 (Exhaustive Search)
    for validator_func, label in VALIDATORS:
        try:
            if validator_func(value, pattern):
                score = validator_priority(label)
                matched_list.append((label, score))
        except Exception:
            continue

    # 4. 결과 분석
    if not matched_list:
        return None, 0, []

    # 5. VALIDATOR_CONFIG priority 내림차순, 동률이면 라벨명으로 안정 정렬
    matched_list.sort(key=lambda x: (-x[1], x[0]))
    
    best_label, best_score = matched_list[0]
    
    return best_label, best_score, matched_list


def column_label_trust_decision(
    label: str,
    *,
    match_rate: float,
    sample_size: int,
) -> tuple[bool, float]:
    """
    Top-N 등 컬럼 단위로 집계한 뒤, 대표 라벨을 출력해도 될지 판단합니다.
    VALIDATOR_CONFIG 의 tolerance 와 동일 규칙을 사용합니다.

    Returns:
        (is_trusted, target_tolerance)
    """
    target_tolerance = validator_tolerance(label) if label else DEFAULT_TOLERANCE
    if sample_size <= 0:
        return False, target_tolerance
    if match_rate >= 0.99:
        return True, target_tolerance
    is_trusted = match_rate >= target_tolerance and sample_size >= 10
    return is_trusted, target_tolerance


def _bootstrap_reference_globals() -> None:
    """import 시 1회 참조 CSV 로드. 비활성: QDQM_SKIP_REF_INIT=1."""
    flag = os.environ.get("QDQM_SKIP_REF_INIT", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return
    try:
        init_reference_globals(ROOT_PATH, strict_columns=False, verbose=DEBUG)
    except Exception as e:
        if DEBUG:
            print(f"[WARN] init_reference_globals 자동 호출 실패: {e}")


_bootstrap_reference_globals()

