# -*- coding: utf-8 -*-
"""
dq_validate.py
- 주소/이메일/URL/전화/위경도/날짜/국가코드(ISO3)/한국성씨 등 유효성 함수 모음
- 시도/시군구/성씨/국가코드 목록을 프로젝트 루트 기준 CSV에서 로드하여
  전역 세트(SIDO_SET, SIGUNGU_SET, SIDO_TO_SIGUNGU, KOR_NAME_SET, COUNTRY_ISO3_SET)에 주입
"""

from __future__ import annotations
import os, re, unicodedata
from datetime import datetime
from typing import Iterable, Optional, Set, Dict, Tuple
import pandas as pd

# --------------------------- 기본 설정 ---------------------------
DEBUG = False

# 프로젝트 루트 기준(Initializing_Main_Class 에서 넘겨줍니다)
DEFAULT_SIDO_CSV     = r"5_Reference_Code/Source/시도명.csv"
DEFAULT_SIGUNGU_CSV  = r"5_Reference_Code/Source/시군구명.csv"
DEFAULT_KORNAME_CSV  = r"6_Validation_Code/Source/한국성씨.csv"
DEFAULT_COUNTRY_ISO3 = r"5_Reference_Code/Source/Country_ISO3.csv"
# DEFAULT_YMD_CSV_CANDIDATES = r"6_Validation_Code/Source/연월일.csv"
# --- 추가: 연월일(YYYYMMDD/YYMMDD) 참조 파일 ---
DEFAULT_YMD_CSV_CANDIDATES = (
    r"DataSense/6_Validation_Code/Source/연월일.csv",   # 1순위
    r"6_Validation_Code/Source/연월일.csv",             # 2순위(대체 경로)
    r"DataSense/5_Reference_Code/Source/연월일.csv",    # 3순위(대체 경로)
    r"5_Reference_Code/Source/연월일.csv",              # 4순위(대체 경로)
)

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


def init_ymd_sets(root_path: str | os.PathLike, *, verbose: bool = False) -> None:
    global YMD8_SET, YYMMDD_SET
    root = os.path.abspath(str(root_path))

    for rel in DEFAULT_YMD_CSV_CANDIDATES:
        path = os.path.normpath(os.path.join(root, rel))
        # if verbose:
        #     print(f"[DEBUG] 탐색 중: {path} (exists={os.path.exists(path)})")
        if os.path.exists(path):
            y8, y6 = load_ymd_sets_from_csv(path)
            YMD8_SET, YYMMDD_SET = y8, y6
            # if verbose:
            #     print(f"[INIT] 연월일 로드 성공: {path} / YYYYMMDD:{len(YMD8_SET)} / YYMMDD:{len(YYMMDD_SET)}")
            # break
    else:
        YMD8_SET, YYMMDD_SET = set(), set()
        if verbose:
            print("[INIT] 연월일.csv 미발견 → 파일 기반 날짜 검증 비활성(기본 로직으로 폴백)")


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
    # 분리된 파일 구조에서는 시도→시군구 매핑이 없음
    SIDO_TO_SIGUNGU = {}

    try:
        KOR_NAME_SET = load_kor_name_set(kor_csv, use_first_char=True)
    except Exception as e:
        if DEBUG or verbose: print(f"[WARN] 한국성씨 로드 실패: {e}")
        KOR_NAME_SET = set()

    try:
        COUNTRY_ISO3_SET = load_country_iso3_set(iso3_csv)
    except Exception as e:
        if DEBUG or verbose: print(f"[WARN] ISO3 로드 실패: {e}")
        COUNTRY_ISO3_SET = set()

    # ★ 추가: 연월일 세트 초기화
    init_ymd_sets(root_path, verbose=verbose)

    # if verbose:
    #     print(f"[INIT] SIDO:{len(SIDO_SET)} / SIGUNGU:{len(SIGUNGU_SET)} "
    #           f"/ KOR_NAME:{len(KOR_NAME_SET)} / ISO3:{len(COUNTRY_ISO3_SET)} "
    #           f"/ YMD8:{len(YMD8_SET)} / YYMMDD:{len(YYMMDD_SET)}")
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
