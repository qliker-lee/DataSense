# -*- coding: utf-8 -*-
# Copyright (c) 2026, qliker. All rights reserved.
# 2026.05.04 
"""
dq_validate.py
- 주소/이메일/URL/전화/위경도/날짜/국가코드(ISO3)/한국성씨 등 유효성 함수 모음
- 시도/시군구/성씨/국가코드 목록을 프로젝트 루트 기준 CSV에서 로드하여
  전역 세트(SIDO_SET, SIGUNGU_SET, SIDO_TO_SIGUNGU, KOR_NAME_SET, COUNTRY_ISO3_SET)에 주입
  YYYYMMDD, YYMMDD 유효성 검사 함수 추가
"""

from __future__ import annotations
import os
import re
import unicodedata
import json
import traceback
import logging
from datetime import datetime
from typing import Iterable, Optional, Set, Dict, Tuple
import pandas as pd
import phonenumbers
from phonenumbers import PhoneNumberType
from pathlib import Path
import sys

# --------------------------- 기본 설정 ---------------------------
DEBUG = False

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
# 국내 전화(유선/휴대폰 포함)
_KR_AREA3 = {'031','032','033','041','042','043','044','051','052','053','054','055','061','062','063','064'}


# --- 추가 전역 세트 ---
B_DONG_SET: Set[str] = set()
H_DONG_SET: Set[str] = set()
ROAD_CODE_SET: Set[str] = set()
YMD8_SET: Set[str] = set()    # 'YYYYMMDD' (숫자 8자리)
YYMMDD_SET: Set[str] = set()  # 'YYMMDD'   (숫자 6자리)
SIDO_SET: Set[str] = set()
SIGUNGU_SET: Set[str] = set()
SIDO_TO_SIGUNGU: Dict[str, Set[str]] = {}   # (주의) '시도명.csv'와 '시군구명.csv'가 분리라면 대부분 비어있음
KOR_NAME_SET: Set[str] = set()              # 한국성씨(한 글자 성)
COUNTRY_ISO3_SET: Set[str] = set()          # ISO 3166-1 alpha-3
UNIT_CODE_SET: Set[str] = set()             # 단위코드(EA, KG, 개 등) — 단위코드.csv
OLD_ZIP_PREFIX_SET: Set[str] = set()
ZIP_PREFIX_SET: Set[str] = set()
ZIP_CODE_SET: Set[str] = set()
OLD_ZIP_CODE_SET: Set[str] = set()

DEFAULT_ENCODINGS: Tuple[str, ...] = ("utf-8-sig", "cp949", "utf-8")
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
    except:
        return default
# ======================================================================
# 
# ======================================================================
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

# --------------------------- 로더들 ---------------------------
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

        out.add(vv[:1] if use_first_char else vv) # 성씨 첫 글자만 저장[cite: 1]
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
        # 첫 번째 문자열(object) 컬럼
        obj_cols = df.select_dtypes(include="object").columns.tolist()
        if not obj_cols:
            return set(), set()
        col = obj_cols[0]

    y8: Set[str] = set()
    y6: Set[str] = set()
    for v in df[col].dropna().astype(str):
        digits = re.sub(r"[^0-9]", "", _norm(v))
        # 8자리 이상이면 앞 8자리 사용
        if len(digits) >= 8:
            ymd = digits[:8]
            if re.fullmatch(r"\d{8}", ymd):
                y8.add(ymd)
                y6.add(ymd[2:])  # 뒤 6자리(YYMMDD)도 추가
        # 6자리만 따로 제공되는 경우도 수용
        elif len(digits) == 6 and re.fullmatch(r"\d{6}", digits):
            y6.add(digits)

    return y8, y6


# def init_ymd_sets(root_path: str | os.PathLike, *, verbose: bool = False) -> None:
#     global YMD8_SET, YYMMDD_SET
#     root = os.path.abspath(str(root_path))

#     for rel in DEFAULT_YMD_CSV_CANDIDATES:
#         path = os.path.normpath(os.path.join(root, rel))
#         # if verbose:
#         #     print(f"[DEBUG] 탐색 중: {path} (exists={os.path.exists(path)})")
#         if os.path.exists(path):
#             y8, y6 = load_ymd_sets_from_csv(path)
#             YMD8_SET, YYMMDD_SET = y8, y6
#             # if verbose:
#             #     print(f"[INIT] 연월일 로드 성공: {path} / YYYYMMDD:{len(YMD8_SET)} / YYMMDD:{len(YYMMDD_SET)}")
#             # break
#     else:
#         YMD8_SET, YYMMDD_SET = set(), set()
#         if verbose:
#             print("[INIT] 연월일.csv 미발견 → 파일 기반 날짜 검증 비활성(기본 로직으로 폴백)")


# --------------------------- 전역 세트 초기화(필수 호출) ---------------------------
def init_reference_globals(root_path: str | os.PathLike, *, strict_columns: bool = True, verbose: bool = False) -> None:
    """
    프로젝트 루트(DS_Master.yaml의 ROOT_PATH)를 기준으로 CSV들을 읽어서
    전역 세트를 '항상' 채워 넣습니다. (빈 파일/부재 시 빈 셋)
    """
    root = str(root_path)
    sido_csv    = os.path.join(root, DEFAULT_SIDO_CSV)
    sigungu_csv = os.path.join(root, DEFAULT_SIGUNGU_CSV)
    kor_csv     = os.path.join(root, DEFAULT_KORNAME_CSV)
    iso3_csv    = os.path.join(root, DEFAULT_COUNTRY_ISO3)

    global SIDO_SET, SIGUNGU_SET, SIDO_TO_SIGUNGU, KOR_NAME_SET, COUNTRY_ISO3_SET
    global B_DONG_SET, H_DONG_SET, ROAD_CODE_SET, UNIT_CODE_SET, OLD_ZIP_PREFIX_SET
    if DEBUG or verbose:
        print(
            "[INIT] reference csv paths\n"
            f"  - sido   : {sido_csv} (exists={os.path.exists(sido_csv)})\n"
            f"  - sigungu: {sigungu_csv} (exists={os.path.exists(sigungu_csv)})\n"
            f"  - korname: {kor_csv} (exists={os.path.exists(kor_csv)})\n"
            f"  - iso3   : {iso3_csv} (exists={os.path.exists(iso3_csv)})"
        )
    try:
        SIDO_SET    = load_sido_set_from_csv(sido_csv, strict_column=strict_columns)
    except Exception as e:
        if DEBUG or verbose: print(f"[WARN] 시도 로드 실패: {e}")
        SIDO_SET = set()
    try:
        SIGUNGU_SET = load_sigungu_set_from_csv(sigungu_csv, strict_column=strict_columns)
    except Exception as e:
        if DEBUG or verbose: print(f"[WARN] 시군구 로드 실패: {e}")
        SIGUNGU_SET = set()

    try:
        OLD_ZIP_PREFIX_SET = load_old_zip_prefix_set(os.path.join(root, DEFAULT_OLD_ZIP_CSV))
    except Exception as e:
        if DEBUG or verbose: print(f"[WARN] 구 우편번호 3자리파일 로드 실패: {e}")
        OLD_ZIP_PREFIX_SET = set()

    # 분리된 파일 구조에서는 시도→시군구 매핑이 없음
    SIDO_TO_SIGUNGU = {}

    try:
        KOR_NAME_SET = load_kor_name_set(kor_csv, use_first_char=True)
        if DEBUG or verbose:
            exists = os.path.exists(kor_csv)
            size = os.path.getsize(kor_csv) if exists else None
            msg = f"[INIT] 한국성씨 로드: {kor_csv} (exists={exists} size={size} count={len(KOR_NAME_SET)})"
            if DEBUG and KOR_NAME_SET:
                sample = sorted(KOR_NAME_SET)[:20]
                msg += f" sample={sample}"
            print(msg)
            if exists and len(KOR_NAME_SET) == 0:
                print("[WARN] 한국성씨.csv 를 읽었지만 값이 0개입니다. CSV 컬럼/인코딩/내용을 확인하세요.")
    except Exception as e:
        if DEBUG or verbose: print(f"[WARN] 한국성씨 로드 실패: {e}")
        KOR_NAME_SET = set()

    try:
        COUNTRY_ISO3_SET = load_country_iso3_set(iso3_csv)
    except Exception as e:
        if DEBUG or verbose: print(f"[WARN] ISO3 로드 실패: {e}")
        COUNTRY_ISO3_SET = set()

    # # ★ 추가: 연월일 세트 초기화
    # init_ymd_sets(root_path, verbose=verbose)

    # 코드 계열 세트 초기화
    B_DONG_SET = load_code_set(os.path.join(root, DEFAULT_B_DONG_CSV), "법정동코드")
    H_DONG_SET = load_code_set(os.path.join(root, DEFAULT_H_DONG_CSV), "행정동코드")
    ROAD_CODE_SET = load_code_set(os.path.join(root, DEFAULT_ROAD_CSV), "도로명코드")

    try:
        UNIT_CODE_SET = load_unit_code_set(os.path.join(root, DEFAULT_UNIT_CSV))
    except Exception as e:
        if DEBUG or verbose:
            print(f"[WARN] 단위코드 로드 실패: {e}")
        UNIT_CODE_SET = set()

    if DEBUG or verbose:
        print(
            f"[INIT] loaded counts: SIDO:{len(SIDO_SET)} / SIGUNGU:{len(SIGUNGU_SET)} "
            f"/ KOR_NAME:{len(KOR_NAME_SET)} / ISO3:{len(COUNTRY_ISO3_SET)} "
            f"/ OLD_ZIP_PREFIX:{len(OLD_ZIP_PREFIX_SET)} "
            f"/ B_DONG:{len(B_DONG_SET)} / H_DONG:{len(H_DONG_SET)} "
            f"/ ROAD_CODE:{len(ROAD_CODE_SET)} / UNIT_CODE:{len(UNIT_CODE_SET)}"
        )
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


# --------------------------- 로더 추가 ---------------------------
def load_code_set(csv_path: str, col_name: str) -> Set[str]:
    if not csv_path or not os.path.exists(csv_path):
        return set()
    df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
    if df.empty:
        return set()
    
    # 지정된 컬럼이 없으면 첫 번째 컬럼 사용
    target_col = col_name if col_name in df.columns else df.columns[0]
    
    # 8자리 검사를 위해 슬라이싱 및 정규화
    vals = df[target_col].dropna().astype(str).map(lambda x: re.sub(r"\D", "", x)[:8])
    return {v for v in vals if v}


def load_unit_code_set(csv_path: str) -> Set[str]:
    """단위코드 CSV의 모든 컬럼 값을 수집(코드·명칭 혼재 대비). 값은 정규화 후 대문자 통일."""
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


# --------------------------- 유효성 함수 추가 ---------------------------

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
    """한국 전화번호 유효성 검사 (지역번호/휴대폰 포함)"""
    if not isinstance(val, str):
        return False

    if re.search(r"[A-Za-z]", val):
        return False

    # 숫자만 추출
    # digits = re.sub(r"\D", "", val)
    digits = "".join(filter(str.isdigit, val))
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

def load_old_zip_prefix_set(csv_path: str) -> Set[str]:
    """
    우편번호구3.csv에서 앞 3자리 고유값만 추출하여 세트로 반환
    """
    if not csv_path or not os.path.exists(csv_path):
        return set()
    
    try:
        # 첫 번째 컬럼에 우편번호가 있다고 가정
        df = _read_csv_with_encodings(csv_path, DEFAULT_ENCODINGS)
        if df.empty:
            return set()
            
        first_col = df.columns[0]
        # 1. 숫자만 남기기 2. 앞 3자리 자르기 3. 고유값(set) 저장
        prefixes = (
            df[first_col]
            .dropna()
            .astype(str)
            .map(lambda x: re.sub(r"\D", "", x)[:3]) 
        )
        return {v for v in prefixes if len(v) == 3}
    except Exception as e:
        if DEBUG: print(f"[WARN] 구 우편번호 접두어 로드 실패: {e}")
        return set()

def validate_old_zip_code(val: str) -> bool:
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
# init_reference_globals 함수 내에 아래 로직을 추가하여 호출하십시오.
# OLD_ZIP_PREFIX_SET = load_old_zip_prefix_set(os.path.join(root, DEFAULT_OLD_ZIP_CSV))

_UNIT_FALLBACK_DENY = frozenset({
    "NAME", "DATA", "TYPE", "CODE", "TEXT", "VALUE", "NULL", "NONE",
})


def validate_unit_code(val) -> bool:
    """
    단위코드 검사.
    - UNIT_CODE_SET 이 있으면: 목록에 있는 값만 True (대소문자 무시, 공백·유니코드 정규화 후 비교)
    - 없으면: 짧은 영문/숫자/한글 조합만 완화 허용(일반 컬럼명 오인 최소화를 위해 블랙리스트 적용)
    """
    if val is None:
        return False
    raw = str(val).strip()
    if not raw or raw.lower() in {"nan", "null", "none"}:
        return False
    s = _norm(raw).strip().upper()
    if not s:
        return False
    if UNIT_CODE_SET:
        return s in UNIT_CODE_SET
    if s in _UNIT_FALLBACK_DENY:
        return False
    return bool(re.fullmatch(r"^[A-Z0-9가-힣.\-/·]{1,16}$", s))


def validate_kor_name(value: str) -> bool:
    if not value: return False
    
    # 1. 전처리: load_kor_name_set 과 동일하게 NFC 정규화 후 공백 제거
    s = _norm(str(value)).replace(" ", "")
    
    # 2. 기본 제약: 한글 2~5자[cite: 1]
    if not re.fullmatch(r"^[가-힣]{2,5}$", s):
        return False

    if not KOR_NAME_SET:
        if DEBUG:
            print("KOR_NAME_SET is empty")
        return True

    # 3. 성씨: 참조 CSV는 첫 글자(단일 음절)만 세트에 넣으므로 첫 글자만 비교
    return s[0] in KOR_NAME_SET

# def validate_kor_name_old(value: str) -> bool:
#     """
#     한국성씨.csv에 나열된 성씨로 시작하며, 
#     논리적인 한글 성명(성+이름) 구조를 가졌는지 검사합니다.
#     """
#     if not KOR_NAME_SET:
#         # 세트가 비어있다면 최소한 한글 2~5자 패턴이라도 확인
#         print("KOR_NAME_SET is empty")
#         return bool(re.fullmatch(r"^[가-힣]{2,5}$", str(value)))
    
#     try:
#         # 1. 전처리: 공백 제거 및 문자열화
#         s = str(value).strip().replace(" ", "")
        
#         # 2. 기본 제약: 한글로만 구성, 길이는 2~5자 사이 (외자 이름 포함)
#         if not re.fullmatch(r"^[가-힣]{2,5}$", s):
#             return False
        
#         # 3. 성씨 매칭 (긴 성씨부터 우선 매칭)
#         # 복성(2글자)을 먼저 확인한 후 단성(1글자)을 확인하여 오판을 방지합니다.
#         # 예: '황보관'에서 '황'이 아닌 '황보'를 먼저 찾음
#         surnames = sorted(list(KOR_NAME_SET), key=len, reverse=True)
        
#         has_valid_surname = False
#         matched_surname = ""
#         for surname in surnames:
#             if s.startswith(surname):
#                 has_valid_surname = True
#                 matched_surname = surname
#                 break
        
#         if not has_valid_surname:
#             return False
            
#         # 4. 성을 제외한 이름이 존재하는지 확인 (성만 있고 이름이 없는 경우 방지)
#         name_part = s[len(matched_surname):]
#         return len(name_part) > 0

#     except Exception:
#         return False

def validate_country_code(value: str) -> bool:
    """ISO 3166-1 alpha-3 전용. 세트가 있으면 membership, 없으면 3대문자 형식만 체크."""
    s = str(value).strip().upper()
    if not s or not re.fullmatch(r"[A-Z]{3}", s):
        return False
    return (s in COUNTRY_ISO3_SET) if COUNTRY_ISO3_SET else True

def validate_address(value: str) -> bool:
    if not SIDO_SET or not SIGUNGU_SET:
        return True # Fallback

    try:
        s = _norm(value)
        if not s: return False
        parts = s.split()
        if len(parts) < 2: return False # 최소 '시도 시군구'는 있어야 함

        # 1. 시도 검증 및 정규화
        tok = _normalize_sido_token(parts[0])
        sido = None
        if tok in SIDO_SET:
            sido = tok
        else:
            base = _sido_base(tok)
            cand_sido = [sd for sd in SIDO_SET if _sido_base(sd) == base]
            if cand_sido:
                sido = cand_sido[0]
        
        if not sido: return False

        # 세종특별자치시 등 시군구가 생략 가능한 지역 처리
        if sido in _SIDO_SIGUNGU_OPTIONAL:
            return True

        # 2. 시군구 후보군 생성 및 검증 (유연성 강화)
        # 후보 1: '금천구' (단독)
        # 후보 2: '용인시 기흥구' (결합)
        candidates = []
        candidates.append(parts[1]) 
        if len(parts) >= 3:
            candidates.append(parts[1] + " " + parts[2])
            candidates.append(parts[1] + parts[2])

        # 검증 로직: 후보 중 하나라도 시군구 세트에 있는지 확인
        valid_gus = SIDO_TO_SIGUNGU.get(sido, SIGUNGU_SET)
        nospace_gus = {g.replace(" ", "") for g in valid_gus}

        for cand in candidates:
            # 1) 전체 명칭 매칭 (예: '용인시 기흥구')
            if cand in valid_gus or cand.replace(" ", "") in nospace_gus:
                return True
            
            # 2) 단독 명칭 매칭 (예: '기흥구'가 용인시에 속하는지 확인)
            # SIGUNGU_SET의 요소들이 '시명 구명' 형태일 때 '구명'만 포함되어 있는지 체크
            if any(cand in g for g in valid_gus if len(cand) >= 2):
                # 단, '시/군/구'로 끝나는 단어일 때만 신뢰도 상승
                if cand.endswith(("시","군","구")):
                    return True

        # 3. 도로명/지번 패턴 추가 확인 (보조 수단)
        # 시도/시군구는 맞는데 뒤에 '동/로/길'이 나오면 주소로 확신
        if len(parts) >= 3:
            if any(parts[2].endswith(("동", "로", "길", "가")) for _ in [0]):
                # 앞의 2개 토큰이 최소한의 형태를 갖췄다면 True
                return True

        return False

    except Exception:
        return True

def validate_address_old(value: str) -> bool:
    """
    주소(ADDRESS) 유효성 강화:
      - 시도 토큰은 약칭/축약(경북/전남/강원특자 등)까지 허용
      - 시군구 후보: 두번째 토큰, (2+3)결합(공백/무공백), 세번째 단독까지
      - 접미사(시/군/구/자치구/특별자치시)로 노이즈 감소
      - SIDO→SIGUNGU 매핑이 있으면 우선, 없으면 전역 시군구 셋으로 완화
    """
    # 참조 세트가 초기화되지 않은 경우(예: init_reference_globals 미호출)
    # 검증을 '실패'로 처리하면 파이프라인이 과도하게 깨지므로 True로 완화하되,
    # 기본 동작은 조용히 통과시키고(DEBUG일 때만 1회 경고) 로그 오염을 방지한다.
    if not SIDO_SET or (not SIGUNGU_SET):
        global _REF_GLOBALS_WARNED
        try:
            warned = _REF_GLOBALS_WARNED
        except NameError:
            warned = False
            _REF_GLOBALS_WARNED = False
        if (DEBUG is True) and (not warned):
            print("SIDO_SET or SIGUNGU_SET is not initialized (validate_address: fallback=True)")
            _REF_GLOBALS_WARNED = True
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

#-----------------------------------------------------------------
#---------------------------------------------------------------
# Determine_Detail_Type helpers 함수
#---------------------------------------------------------------

def is_timestamp(value, pattern): # ["2009-07-06 0:33", 2014-12-28 12:00 AM", 
    if pattern not in ['nnnn-nn-nn nn:nn:nn', 'nnnn-nn-nn nn:nn:nn.nnnnnn', 
            'nnnn-nn-nn nn:nn:nn.', 'nnnn-nn-nn nn:nn', 'nnnn-nn-nn n:nn', 'nnnn-nn-nn nn:nn AA', 'nnnn-n-nn nn:nn AA']:
        return False
    return validate_timestamp(value) 

def is_time(value, pattern):  # "30:03.0", 
    if pattern not in ['nn:nn.n', 'nn:nn:nn', 'nn:nn:nn.nnnnnn', 'nn:nn:nn.']:
        return False
    print("is_time", value, pattern)
    return validate_time(value)

def is_date(value, pattern):
    if pattern not in ['nnnnnnnn', 'nnnn-nn-nn', 'nnnn/nn/nn', 'nnnn.nn.nn']:
        return False
    return validate_date(value)

def is_yymmdd(value, pattern):
    if pattern not in ['nnnnnn', 'nn-nn-nn', 'nn/nn/nn', 'nn.nn.nn']:
        return False
    return validate_YYMMDD(value)

def is_datechar(value, pattern):
    if pattern not in ['nnnnnnnn', 'nnnn-nn-nn', 'nnnn/nn/nn', 'nnnnKnnKnnK', 'nnnn.nn.nn', 'nnnn. n. nn.']:
        return False
    return validate_date(value)

def is_yearmonth(value, pattern):
    if pattern not in ['nnnnnn', 'nnnn-nn', 'nnnn/nn', 'nnnn.nn', 'nnnnKnnK']:
        return False
    return validate_yearmonth(value)

def is_year(value, pattern):
    if pattern not in ['nnnn', 'nnnnK']:
        return False
    return validate_year(value)

def is_latitude(value, pattern):
    if pattern not in ['nn.nnnn','nn.nnnnn','nn.nnnnnn','nn.nnnnnnn','nn.nnnnnnnn']:
        return False
    return validate_latitude(value)

def is_tel(value, pattern):
    if pattern not in ['nnn-nnn-nnnn','nn-nnnn-nnnn','nn-nnn-nnnn','nnn-nnnn','nnnn-nnnn','nnnnnnn','nnnnnnnn','nnnnnnnnnn']:
        return False
    return validate_tel(value)

def is_cellphone(value, pattern):
    if pattern not in ['nnn-nnnn-nnnn','nnnnnnnnnnn']:
        return False
    return validate_cellphone(value)

def is_car_number(value, pattern):
    if pattern not in ['KKnnKnnnn', 'nnKnnnn', 'nnnKnnnn']:
        return False
    return validate_car_number(value)

def is_email(value, pattern):
    if pattern not in ['@']:
        return False
    return validate_email(value)

def is_url(value, pattern):
    if pattern not in ['://']:
        return False
    return validate_url(value)

def is_kor_name(value, pattern) -> bool:
    if pattern not in ['KKK', 'kkk', 'K KK']:
        return False
    return validate_kor_name(value)

# 주소는 반드시 K 갯수가 8 개이상, ' ' 가 3개 이상 있어야 함
def is_address(value, pattern) -> bool:
    if len(pattern) < 8 or pattern.count("K") < 6 or pattern.count(" ") < 3:
        return False
    return validate_address(value)

def is_country_code(value, pattern):
    if pattern not in ['[A-Z]{3}', '[a-z]{3}']:
        return False
    return validate_country_code(value)

def is_old_zip_code(value, pattern):
    if pattern not in ['nnnnn']:
        return False
    return validate_old_zip_code(value)

def is_zip_code(value, pattern):
    if pattern not in ['nnnnn']:
        return False
    return validate_zip_code(value)

def is_old_zip_code(value, pattern):
    if pattern not in ['nnnnnn', 'nnn-nnn']:
        return False
    return validate_old_zip_code(value)

def is_biz_no(value, pattern):  # 사업자등록번호 
    if pattern not in ['nnnnnnnnnn' , 'nnn-nn-nnnnn']:
        return False
    return validate_biz_no(value)

def is_corp_no(value, pattern): # 법인번호 
    if pattern not in ['nnnnnnnnnnnnnnn', 'n.nnnnnA+nn']:
        return False
    return validate_corp_no(value)

def is_rrn(value, pattern): # 주민번호
    if pattern not in ['nnnnnn-nnnnnnnn', 'nnnnnnnnnnnnnn']:
        return False
    return validate_rrn(value)

def is_road_name_code(value, pattern): # 도로명코드
    if pattern not in ['nnnnnnnnnnnnnnn']:
        return False
    return validate_road_name_code(value)

def is_b_dong_code(value, pattern): # 법정동코드
    if pattern not in ['nnnnnnnnnnnnnnn']:
        return False
    return validate_b_dong_code(value)

def is_h_dong_code(value, pattern): # 행정동코드
    if pattern not in ['nnnnnnnnnnnnnnn']:
        return False
    return validate_h_dong_code(value)


# def is_flag(value, pattern):
#     return validate_flag(value)

# def is_text(value, pattern, max_length):
#     return max_length > 1000 or len(pattern) > 1000


#------------------------------------------------------------------

def _strip_decimal_zero(value):
    text = str(value).strip()
    if text.endswith('.0'):
        return text[:-2]
    return text

def get_pattern(value):
    try:
        # 소수점 .0 제거 및 최대 20자 추출
        text = _strip_decimal_zero(value)[:20]
        p = []
        for ch in text:
            if ch.isdigit(): p.append('n')
            elif '가' <= ch <= '힣': p.append('K')
            elif ch.isupper(): p.append('A')
            elif ch.islower(): p.append('a')
            elif ch in '(){}[]-=. :@/': p.append(ch)
            else: p.append('s')
        return "".join(p)
    except:
        return ""


# 1. 검증 함수들을 리스트(또는 딕셔너리)로 관리
VALIDATORS = [
    # (검증함수, 반환할 레이블)
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
    (is_address, 'ADDRESS'),
]


def find_attribute(value):
    # Null 체크 및 패턴 생성 최적화
    text = str(value).strip()
    if text.endswith('.0'):
        text = text[:-2]
    
    if not text:
        return 'NULL', True

    # 패턴 생성 (한 번만 수행)
    pattern = get_pattern(text)

    # 2. 루프를 통한 자동 검증 (우아한 핵심 부분)
    for validator_func, label in VALIDATORS:
        try:
            if validator_func(value, pattern):
                return label, True
        except Exception:
            continue  # 특정 검증기 에러 시 다음으로 진행
    return None, False

def find_attribute_OLD(value):


    pattern = get_pattern(value)

    # 2) 날짜/시간
    if is_timestamp(value, pattern):        return 'TIMESTAMP', True
    if is_time(value, pattern):             return 'TIME', True
    if is_yymmdd(value, pattern):           return 'YYMMDD', True
    if is_datechar(value, pattern):         return 'DATECHAR', True
    if is_yearmonth(value, pattern):        return 'YEARMONTH', True
    if is_year(value, pattern):             return 'YEAR', True
    # 3) 주민번호, 사업자등록번호, 법인번호, 도로명코드, 행정동코드, 법정도코드, 우편번호
    if is_rrn(value, pattern):              return 'RRN', True
    if is_biz_no(value, pattern):           return 'BIZ_NO', True
    if is_corp_no(value, pattern):          return 'CORP_NO', True
    if is_road_name_code(value, pattern):   return 'ROAD_CODE', True
    if is_b_dong_code(value, pattern):      return 'B_DONG_CODE', True
    if is_h_dong_code(value, pattern):      return 'H_DONG_CODE', True
    if is_zip_code(value, pattern):         return 'ZIP_CODE', True
    if is_old_zip_code(value, pattern):     return 'ZIP_CODE_OLD', True
    # if is_latitude(value, pattern):          return 'LATITUDE', True
    # if is_longitude(value, pattern):         return 'LONGITUDE', True
    # 4) 연락처 & 차량번호
    if is_tel(value, pattern):              return 'TEL', True # 10 검사할 항목 수 
    if is_cellphone(value, pattern):        return 'CELLPHONE', True
    if is_car_number(value, pattern):       return 'CAR_NUMBER', True
    # if is_company(value, pattern):          return 'COMPANY', True
    # 5) 특수 포맷
    if is_email(value, pattern):            return 'EMAIL', True
    if is_url(value, pattern):              return 'URL', True
    # 6) NULL
    if len(pattern) == 0:                   return 'NULL', True

    # 7) 주소/텍스트/한글명 기반
    if is_kor_name(value, pattern):         return "NAME_KOR", True
    if is_address(value, pattern):          return "ADDRESS", True
    return None, False


def _bootstrap_reference_globals() -> None:
    """
    대부분의 스크립트가 init_reference_globals 를 따로 호출하지 않아도
    주소/성씨 등 참조 세트가 비지 않도록, 모듈 import 시 1회 로드합니다.

    비활성화: 환경변수 QDQM_SKIP_REF_INIT=1 (또는 true/yes/on)
    """
    flag = os.environ.get("QDQM_SKIP_REF_INIT", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return
    try:
        # import 시점에는 컬럼명 변형에 대비해 완화 모드( selftest 기본과 동일 )
        # 엄격 검증이 필요하면 앱에서 init_reference_globals(..., strict_columns=True) 재호출
        init_reference_globals(ROOT_PATH, strict_columns=False, verbose=DEBUG)
    except Exception as e:
        if DEBUG:
            print(f"[WARN] init_reference_globals 자동 호출 실패: {e}")


_bootstrap_reference_globals()
