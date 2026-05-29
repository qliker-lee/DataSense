# DS_31_DataProfilingForQuality.py
# 컬럼 프로파일링 통계
# 2026.02.05 최초 작성, Qiler
# Author: Qiler

import pandas as pd
import re
import os
import sys
import json
import unicodedata
from glob import glob
from pathlib import Path
from collections import Counter
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Set, Dict

# from DS_31_DataProfilingForQuality_Class import DataProfiler

TEST_FILE_NAME = '계정과목코드.csv'
# ---------------------------------------------------------------------------
# 1. Data Loader 계층 (소스 읽기 분리)
# ---------------------------------------------------------------------------
#---------------------------------------------------------------
# Determine_Detail_Type helpers 함수
#---------------------------------------------------------------
# TIMESTAMP_PATTERNS = ['nnnn-nn-nn nn:nn:nn.nnnnnn', 'nnnn-nn-nn n:nn', 'nnnn-nn-nn nn:nn:nn.nnnnnn', 'nnnn-nn-nn nn:nn:nn.']
# TIME_PATTERNS = ['nn:nn.n', 'nn:nn:nn', 'nn:nn:nn.nnnnnn', 'nn:nn:nn.']
# DATECHAR_PATTERNS = ['nnnnnnnn', 'nnnn-nn-nn', 'nnnn/nn/nn', 'nnnnKnnKnnK', 'nnnn.nn.nn', 'nnnn. n. nn.']
# YEARMONTH_PATTERNS = ['nnnnnn', 'nnnn-nn', 'nnnn/nn', 'nnnn.nn', 'nnnnKnnK']
# YEAR_PATTERNS = ['nnnnnn', 'nnnn-nn', 'nnnn/nn', 'nnnn.nn', 'nnnnKnnK']
# LATITUDE_PATTERNS = ['nn.nnnn', 'nn.nnnnn', 'nn.nnnnnn', 'nn.nnnnnnn', 'nn.nnnnnnnn']
# LONGITUDE_PATTERNS = ['nnn.nnnn', 'nnn.nnnnn', 'nnn.nnnnnn', 'nnn.nnnnnnn', 'nnn.nnnnnnnn']
# TEL_PATTERNS = ['nnn-nnn-nnnn', 'nn-nnnn-nnnn', 'nn-nnn-nnnn', 'nnn-nnnn', 'nnnn-nnnn', 'nnnnnnn', 'nnnnnnnn', 'nnnnnnnnnn']
# CELLPHONE_PATTERNS = ['nnn-nnnn-nnnn', 'nnnnnnnnnnn']
# CAR_NUMBER_PATTERNS = ['KKnnKnnnn', 'nnKnnnn', 'nnnKnnnn']
# COMPANY_PATTERNS = ['(K)KKKK', '(K)KKKKK', '(K)KKKKKK']
# EMAIL_PATTERNS = ['@', '.', '..']
# URL_PATTERNS = ['://', '.', '..']
# ADDRESS_PATTERNS = ['K', 'K ', 'K K', 'K K ', 'K K K', 'K K K ', 'K K K K', 'K K K K ']

# 유효성 체크용 전역 세트 (없으면 빈 세트로 동작)
YMD8_SET: Set[str] = set()    # 'YYYYMMDD' (숫자 8자리)
YYMMDD_SET: Set[str] = set()  # 'YYMMDD'   (숫자 6자리)
SIDO_SET: Set[str] = set()
SIGUNGU_SET: Set[str] = set()
SIDO_TO_SIGUNGU: Dict[str, Set[str]] = {}
# KOR_NAME_SET: Set[str] = set()
COUNTRY_ISO3_SET: Set[str] = set()
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

# 한국성씨 세트
KOR_NAME_SET = {
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권", "황", "안", "송", "류", "전", 
    "홍", "고", "문", "양", "손", "배", "백", "허", "유", "남", "심", "노", "하", "곽", "성", "차", "주", "우", "구", "라", 
    "민", "진", "지", "엄", "채", "원", "천", "방", "공", "현", "함", "변", "염", "여", "추", "도", "소", "석", "선", "설", 
    "마", "길", "연", "위", "표", "명", "기", "반", "왕", "금", "옥", "육", "인", "맹", "제", "모", "탁", "국", "어", "은", 
    "편", "용", "예", "경", "봉", "사", "부", "가", "복", "태", "목", "형", "계", "피", "두", "감", "음", "빈", "동", "온", 
    "호", "범", "좌", "팽", "승", "간", "상", "시", "갈", "단",
}

SIDO_SET = {
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", 
    "제주", "경기도", "강원도", "충청북도", "충청남도", "전라북도", "전라남도", "경상북도", "경상남도", "제주도", 
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시", "제주특별자치도",
}

#---------------------------------------------------------------
# 패턴/유효성 함수
#---------------------------------------------------------------
def get_detailed_pattern_value(value: str) -> str:
    # 1. Float 변환으로 인한 '.0' 현상 방지
    val = str(value).strip()
    if val.endswith('.0'):
        val = val[:-2]

    if not val or val.lower() in ['nan', 'null', '']:
        return "EMPTY"

    res = []
    for c in val:
        if c.isdigit():
            res.append('n')
        elif '\uac00' <= c <= '\ud7a3':
            res.append('K')
        elif ' ' == c:
            res.append(' ')
        elif 'a' <= c <= 'z':
            res.append('a')
        elif 'A' <= c <= 'Z':
            res.append('A')
        # 기호 처리: 정수라면 아래 조건에 걸리지 않아 오직 'n'만 쌓이게 됩니다.
        elif c in r"""-.:/\ """:
            res.append(c)
        elif c in r"""!@#$%^&*()-_=+[{]}\|;:'",.<>/?`~ """:
            res.append('S')
        else:
            res.append('U')
    return "".join(res)

#---------------------------------------------------------------
# 유효성 함수
#---------------------------------------------------------------
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

    # 폴백: 기존 로직
    try:
        y, m, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])
        if not (1900 <= y <= 9999 and 1 <= m <= 12 and 1 <= d <= 31):
            return False
        datetime(y, m, d)
        return True
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


def validate_yearmonth(value) -> bool:
    try:
        s = str(value)
        if s.endswith('.0'): s = s[:-2]
        nums = re.sub(r'[^0-9]', '', s)
        if len(nums) != 6: return False
        y, m = int(nums[:4]), int(nums[4:])
        return ((1900 <= y <= 2100) or (y == 9999)) and (1 <= m <= 12)
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
    s = str(value).strip()
    if s.endswith('.0'):
        s = s[:-2]
    digits = re.sub(r"[^0-9]", "", s)
    if len(digits) not in (10, 11):
        return False
    if digits[:3] not in ["010", "011", "016", "017", "018", "019"]:
        return False
    local = digits[3:]
    if len(local) not in (7, 8):
        return False
    # 국번이 전부 0인 경우는 무효 처리
    if set(local) == {"0"}:
        return False
    return True

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
        return bool(s) and (s[:1] in KOR_NAME_SET) and len(s) >= 2 and len(s) <= 5
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
      - 시군구는 세트 데이터 미 구축으로 검사 생략 
      - 주소의 값은 반드시 3개 이상의 토큰으로 구성됨
      - 전체 길이가 10 이상 20 이하인 경우만 유효
    """
    if not SIDO_SET:
        print("debuf 00 : SIDO_SET is empty")
        return True  # 참조 세트 미초기화 시 유효한 것으로 간주

    try:
        # 1. 기본적인 전처리 (공백 제거 및 정규화)
        s = str(value).strip()
        if not s: 
            print("debug 01 : s is empty")
            return False
            
        # 2. 전체 문자열 길이 체크 (10자 이상 20자 이하)
        if not (10 <= len(s) <= 50):
            print(f"debug 02 : s length is not between 10 and 50: len(s) = {len(s)}, s = {s}")
            return False
            
        # 3. 토큰 분리 및 개수 체크 (3개 이상의 단어/토큰)
        parts = s.split()
        if len(parts) < 3:
            print(f"debug 03 : parts length is less than 3: len(parts) = {len(parts)}, parts = {parts}")
            return False

        # 4. 첫 번째 토큰(시도) 유효성 검사
        tok = _normalize_sido_token(parts[0])
        if tok not in SIDO_SET:
            print(f"debug 04 : tok is not in SIDO_SET: tok = {tok}")
            return False
        return True

    except Exception:
        print(f"debug 05 : Exception: {e}")
        # 예외 발생 시 로직 중단을 방지하기 위해 True 반환 (기존 정책 유지)
        return True

def validate_gender(val: str) -> bool:
    return str(val) in ["남", "여"]

def validate_gender_en(val: str) -> bool:
    return str(val).upper() in ["M", "F"]

def validate_YN_Flag(val: str) -> bool:
    return str(val).upper() in ["Y", "N"]

def validate_01_Flag(val: str) -> bool:
    return str(val).upper() in ["0", "1"]

def validate_Alpha_Flag(val: str) -> bool:
    return str(val).upper() in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"]

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
    # 앞에 5자리를 잘라서 검증
    val = val[:5]
    pattern_1 = r"^\d{2}:\d{2}$"
    pattern_2 = r"^\d{1}:\d{2}$"
    pattern_3 = r"^\d{1}:\d{2}.$"

    if not re.fullmatch(pattern_1, str(val)) and not re.fullmatch(pattern_2, str(val)) and not re.fullmatch(pattern_3, str(val)):
        print(f"debug 13 : time is not valid: val = {val}")
        return False
    return True

# 타임스탬프 검증
# 값을 파싱하여 날짜와 시간으로 분리하여 검증
def validate_timestamp(val: str) -> bool:
    try:
        date, time = val.split(' ')
        if not validate_date(date):
            return False
        if not validate_time(time):
            return False
        return True
    except Exception:
        return True

#---------------------------------------------------------------
# Determine_Detail_Type helpers 함수
#---------------------------------------------------------------
# def is_datechar(pattern, format_stats):
#     return (pattern in DATECHAR_PATTERNS
#             and validate_date(str(format_stats['FormatMedian'])))
# def is_yearmonth(pattern, format_stats):
#     return (pattern in ['nnnnnn', 'nnnn-nn', 'nnnn/nn', 'nnnn.nn', 'nnnnKnnK']
#             and validate_yearmonth(str(format_stats['FormatMedian'])))

# def is_yymmdd(pattern, top10, top_n: int = 10) -> bool:
#     if pattern not in ['nnnnnn', 'nn-nn-nn', 'nn/nn/nn', 'nn.nn.nn', 'nn.nn.nn.']:
#         return False

#     if not top10:
#         return False

#     # Top10은 JSON 문자열 또는 리스트일 수 있음
#     if isinstance(top10, (list, tuple, set)):
#         values = [str(v) for v in top10]
#     else:
#         try:
#             values = json.loads(top10)
#         except Exception as e:
#             print(f"JSON 파싱 실패: {e}")
#             return False

#     top_values = [v for v in values if v != "__OTHER__"][:top_n]
#     if not top_values:
#         return False

#     valid_cnt = sum(1 for v in top_values if validate_YYMMDD(str(v)))
#     return (valid_cnt / len(top_values)) >= 0.9

# def is_year(pattern, format_stats, total_stats):
#     if pattern == 'nnnn' and format_stats['FormatMedian']:
#         try:
#             mode_val = float(total_stats['mode'])
#             return 1990 < mode_val < 2999
#         except Exception:
#             return False
#     return False

# def is_latitude(pattern, format_stats):
#     return (pattern in ['nn.nnnn','nn.nnnnn','nn.nnnnnn','nn.nnnnnnn','nn.nnnnnnnn']
#             and validate_latitude(format_stats['FormatMode']))

# def is_longitude(pattern, format_stats):
#     return (pattern in ['nnn.nnnn','nnn.nnnnn','nnn.nnnnnn','nnn.nnnnnnn','nnn.nnnnnnnn']
#             and validate_longitude(format_stats['FormatMode']))

# def is_tel(pattern: str, top10_json: str, top_n: int = 10) -> bool:
#     """
#     Top10 컬럼(JSON 문자열)을 읽어서 상위 N개가 모두 전화번호이면 True 반환
#     """
#     # 전화번호 패턴만 허용
#     tel_patterns = [
#         'nnn-nnn-nnnn','nn-nnnn-nnnn','nn-nnn-nnnn','nnn-nnnn',
#         'nnnn-nnnn','nnnnnnn','nnnnnnnn','nnnnnnnnnn'
#     ]
#     if pattern not in tel_patterns:
#         return False

#     # top10_json이 None이거나 빈 문자열인 경우 처리
#     if not top10_json or top10_json.strip() == '':
#         return False

#     try:
#         # JSON 문자열 → 리스트 변환
#         values = json.loads(top10_json)
#     except Exception as e:
#         print(f"JSON 파싱 실패: {e}")
#         return False

#     # 상위 N개 추출 ( "__OTHER__" 제외 )
#     top_values = [v for v in values if v != "__OTHER__"][:top_n]
    
#     if not top_values:  # 빈 리스트인 경우
#         return False

#     # 첫 번째 값 검증하여 반드시 전화번호 형식이어야 함
#     first_check = validate_tel(top_values[0])
#     if not first_check:
#         return False

#     # 전화번호 검증 결과 계산
#     valid_tel_count = sum(1 for val in top_values if validate_tel(val))
#     total_count = len(top_values)
    
#     return True if valid_tel_count / total_count >= 0.8 else False

# def is_cellphone(pattern, format_stats):
#     return (pattern in ['nnn-nnnn-nnnn','nnnnnnnnnnn']
#             and validate_cellphone(format_stats['FormatMedian']))

# def is_car_number(pattern, pattern_type_cnt):
#     return (
#         pattern in ['KKnnKnnnn', 'nnKnnnn', 'nnnKnnnn']
#     )

# def is_company(pattern, pattern_type_cnt):
#     return (
#         pattern in ['(K)KKKK', '(K)KKKKK', '(K)KKKKKK']
#         and pattern_type_cnt > 5
#     )

# def is_email(pattern):
#     return '@' in pattern and 1 <= pattern.count('.') <= 2

# def is_url(pattern):
#     return '://' in pattern and pattern.count('.') >= 1

# def is_flag(pattern, format_stats, total_stats):
#     if (format_stats['most_common_pattern'] == 'A' and
#         total_stats.get('min') == 'N' and total_stats.get('max') == 'Y' and
#         format_stats['pattern_type_cnt'] == 1): 
#         return 'YN_Flag'
#     if (format_stats['most_common_pattern'] == 'n' and
#         total_stats.get('min') == '0' and total_stats.get('max') == '1' and
#         format_stats['pattern_type_cnt'] == 1): 
#         return 'True_False_Flag'
#     if (format_stats['most_common_pattern'] in ['A','a'] and format_stats['pattern_type_cnt'] == 1): 
#         return 'Alpha_Flag'
#     if (format_stats['most_common_pattern'] == 'n' and format_stats['pattern_type_cnt'] == 1): 
#         return 'Num_Flag'
#     if (format_stats['most_common_pattern'] == 'K' and format_stats['pattern_type_cnt'] == 1): 
#         return 'Kor_Flag'
#     if ((format_stats['most_common_pattern'] == 'KKK') and format_stats['pattern_type_cnt'] < 6): 
#         return 'KOR_NAME'
#     return None

# def is_text(pattern, max_length, format_stats):
#     return (max_length > FORMAT_MAX_VALUE or
#             len(pattern) > FORMAT_AVG_LENGTH or
#             format_stats['pattern_type_cnt'] > 20)

# def is_sequence(total_stats, unique_count):
#     try:
#         total_min = total_stats.get('min'); total_max = total_stats.get('max')
#         if total_min not in (None,'') and total_max not in (None,''):
#             total_min_f = float(total_min); total_max_f = float(total_max)
#             if total_min_f.is_integer() and total_max_f.is_integer():
#                 total_min_i = int(total_min_f); total_max_i = int(total_max_f)
#                 expected_count = total_max_i - total_min_i + 1
#                 return expected_count > 0 and expected_count == unique_count
#     except (ValueError, TypeError):
#         pass
#     return False

def Detail_Type(format_top10, format_top10pct, mode_top10):
    """ 
    상위 10개 샘플(ModeTop10)을 검사하여 
    가장 많이 일치하는 데이터 타입과 그 유효율(10개 중 통과 개수 %)을 리턴합니다. 
    """
    detail_type = ''
    validation_rate = 0.0

    if not mode_top10:
        return detail_type, validation_rate

    # 리스트 변환 (공백 제거 및 필터링)
    format_top10_list = [fmt.strip() for fmt in str(format_top10).split(' | ') if str(fmt).strip() != '']
    mode_top10_list = [i.strip() for i in str(mode_top10).split(' | ') if str(i).strip() != '']
    format_for_modes = [get_detailed_pattern_value(m) for m in mode_top10_list]
    
    # 실제 검사할 샘플 개수 (ModeTop10 기준)
    sample_size = len(mode_top10_list)
    if sample_size == 0:
        return detail_type, validation_rate

    # 패턴 정의 (기존 유지) ([포맷, [Mmode] 구조임)
    patterns_map = {
        'TIMESTAMP': (['nnnn-nn-nn nn:nn:nn', 'nnnn-nn-nn nn:nn', 'nnnn-nn-nn n:nn', 'nnnn-nn-nn nn:nn:nn.nnnnnn', 'nnnn-nn-nn nn:nn:nn.'], validate_timestamp),
        'TIME': (['nn:nn.n', 'nn:nn:nn', 'nn:nn:nn.nnnnnn', 'nn:nn:nn.'], validate_time),
        'YYMMDD': (['nnnnnn', 'nn-nn-nn', 'nn/nn/nn', 'nn.nn.nn', 'nn.nn.nn.'], validate_YYMMDD),
        
        'DATECHAR': (['nnnnnnnn', 'nnnn-nn-nn', 'nnnn/nn/nn', 'nnnnKnnKnnK', 'nnnn.nn.nn', 'nnnn. n. nn.', 'nnnnK nK nnK KKK', 'nnnnK nnK nnK KKK', 'nnnnK nK nK KKK', 'nnnnK nnK nK KKK',], validate_date),
        'YEARMONTH': (['nnnnnn', 'nnnn-nn', 'nnnn/nn', 'nnnn.nn', 'nnnnKnnK'], validate_yearmonth),
        'YEAR': (['nnnn'], validate_year),
        'KOR_NAME': (['KKK'], validate_kor_name),
        'TEL': (['nnn-nnn-nnnn', 'nn-nnnn-nnnn', 'nn-nnn-nnnn', 'nnn-nnnn', 'nnnn-nnnn', 'nnnnnnn', 'nnnnnnnn', 'nnnnnnnnnn'], validate_tel),
        'CELLPHONE': (['nnn-nnnn-nnnn', 'nnnnnnnnnnn'], validate_cellphone),
        # 'CAR_NUMBER': (['KKnnKnnnn', 'nnKnnnn', 'nnnKnnnn'], validate_car_number),
        'EMAIL': (['@', '.', '..'], validate_email),
        'URL': (['://', '.', '..'], validate_url),
        '성별': (['K'], validate_gender),
        '성별(영문)': (['A', 'a'], validate_gender_en),
        'YN': (['A', 'a'], validate_YN_Flag),
        '01': (['n'], validate_01_Flag),
        'Alpha': (['A', 'a'], validate_Alpha_Flag),
    }

    # 각 타입별 '통과 개수' 카운트
    type_counts = {}
    
    for fmt, mode in zip(format_for_modes, mode_top10_list):
        # 1. 패턴 맵 검사
        for t_name, (p_list, v_func) in patterns_map.items():
            if t_name in {"EMAIL", "URL"}:
                format_match = all(token in fmt for token in p_list)
            else:
                format_match = fmt in p_list
            if format_match and v_func(mode):
                type_counts[t_name] = type_counts.get(t_name, 0) + 1
        
    # 가장 많이 통과한 타입을 선택하고 유효율 계산
    if type_counts:
        best_type = max(type_counts, key=type_counts.get)
        pass_count = type_counts[best_type]
        
        # 유효율 = (통과 개수 / 실제 검사한 샘플 수) * 100
        # 예: 10개 중 8개 통과 시 80.0
        validation_rate = round((pass_count / sample_size) * 100, 2)
        
        # 최소 기준 (예: 1개라도 맞으면 해당 타입으로 보거나, 필요시 10% 이상 조건 유지)
        if validation_rate >= 80.0:
            detail_type = best_type

    return detail_type, validation_rate

class DataLoader(ABC):
    @abstractmethod
    def load_data(self) -> list:
        """(파일명, DataFrame)의 리스트를 반환합니다."""
        pass

class CSVDataLoader(DataLoader):
    def __init__(self, input_path):
        self.input_path = Path(input_path)

    def load_data(self):
        file_list = glob(str(self.input_path / "*.csv"))
        loaded_data = []
        for file_path in file_list:
            file_name = os.path.basename(file_path)
            try:
                try:
                    # 숫자가 Float로 변환되는 것을 방지하기 위해 dtype=str 으로 설정    
                    df = pd.read_csv(file_path, dtype=str, encoding='utf-8-sig', low_memory=False)
                except:
                    df = pd.read_csv(file_path, dtype=str, encoding='cp949', low_memory=False)

                loaded_data.append((file_name, df))
            except Exception as e:
                print(f"❌ {file_name} 로드 실패: {e}")

        return loaded_data

# ---------------------------------------------------------------------------
# 2. Data Profiler 계층 (핵심 분석 로직)
# ---------------------------------------------------------------------------
class DataProfiler:
    def __init__(self, sample_size=10000):
        self.sample_size = sample_size
        self.special_pattern = r'[!@#$%^&*()\-_=+\[\]{}|\\;:\'\",.<>/?`~]'
        self.allowed_pattern = r'[a-zA-Z0-9가-힣ㄱ-ㅎㅏ-ㅣ\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\s' + re.escape(r"""!@#$%^&*()-_=+[{]}\|;:'",.<>/?`~""") + r']'

    def _get_detailed_pattern(self, value):
        return get_detailed_pattern_value(value)

    def _get_timestamp_score(self, series):
        if len(series) == 0: return 0
        reg = r'^\d{2,4}[-./]\d{1,2}[-./]\d{1,2}\s+\d{1,2}:\d{1,2}(:\d{1,2})?(\.\d+)?.*$'
        clean_series = series.astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
        match_count = sum(1 for v in clean_series if re.match(reg, v))
        return 100 if (match_count / len(series)) > 0.5 else 0

    def _analyze_quality_flags(self, series):
        valid_data = series.dropna().astype(str).str.strip()
        valid_data = valid_data[valid_data != '']
        base_res = {k: False for k in ['HasBlank', 'HasHangul', 'HasBrokenKorea', 'HasChinese', 'HasJapanese', 'HasUnicode', 'HasSpecial', 'OnlyAlpha', 'OnlyNumber', 'OnlyAlphaNumber']}
        base_res['CharCheck'] = False
        if valid_data.empty: return base_res
        
        combined_text = "".join(valid_data)
        res = {
            'HasBlank': series.str.contains(r'\s', na=False).any(),
            'HasHangul': bool(re.search(r'[가-힣]', combined_text)),
            'HasBrokenKorea': bool(re.search(r'[ㄱ-ㅎㅏ-ㅣ]', combined_text)),
            'HasChinese': bool(re.search(r'[\u4e00-\u9fff]', combined_text)),
            'HasJapanese': bool(re.search(r'[\u3040-\u30ff\u31f0-\u31ff]', combined_text)),
            'HasSpecial': bool(re.search(self.special_pattern, combined_text)),
            'HasUnicode': bool(re.sub(self.allowed_pattern, '', combined_text)),
            'OnlyAlpha': series.str.match(r'^[a-zA-Z\s]+$', na=False).all(),
            'OnlyNumber': series.str.match(r'^\d+$', na=False).all(),
            'OnlyAlphaNumber': series.str.match(r'^[a-zA-Z0-9\s]+$', na=False).all()
        }
        res['CharCheck'] = any([res['HasBrokenKorea'], res['HasChinese'], res['HasJapanese'], res['HasUnicode']])
        return res

    def profile_column(self, df, col, file_name):
        rec_cnt = len(df)
        full_series = df[col].fillna('').astype(str).str.strip()
        val_series_full = full_series[full_series != '']
        null_cnt = rec_cnt - len(val_series_full)
        
        if val_series_full.empty: return None

        # [A] 전수 조사 지표
        hangul_cnt = val_series_full.str.contains(r'[가-힣]', na=False).sum()
        special_cnt = val_series_full.str.contains(self.special_pattern, na=False).sum()
        chinese_cnt = val_series_full.str.contains(r'[\u4e00-\u9fff]', na=False).sum()
        broken_cnt = val_series_full.str.contains(r'[ㄱ-ㅎㅏ-ㅣ]', na=False).sum()
        japanese_cnt = val_series_full.str.contains(r'[\u3040-\u30ff\u31f0-\u31ff]', na=False).sum()
        unicode_cnt = val_series_full.apply(lambda x: bool(re.sub(self.allowed_pattern, '', x))).sum()
        blank_cnt = full_series.str.contains(r'\s', na=False).sum()
        
        min_string = val_series_full.min()
        max_string = val_series_full.max()
        mode_val = val_series_full.mode()[0] if not val_series_full.empty else ""
        unique_val_cnt = val_series_full.nunique()
        unique_pct = (unique_val_cnt / len(val_series_full) * 100)

        # [B] 샘플링 분석 지표
        sample_series = val_series_full.sample(n=min(len(val_series_full), self.sample_size), random_state=42)
        total_sample_cnt = len(sample_series)
        
        len_s = sample_series.map(len)
        l_counts = Counter(len_s)
        top_l_list = l_counts.most_common(10)
        
        patterns = sample_series.apply(self._get_detailed_pattern)
        f_counts = Counter(patterns)
        top_f_list = f_counts.most_common(10)

        # [C] 체크 로직
        first_l_ratio = (top_l_list[0][1] / total_sample_cnt * 100) if top_l_list else 0
        second_l_ratio = (top_l_list[1][1] / total_sample_cnt * 100) if len(top_l_list) > 1 else 0
        first_f_ratio = (top_f_list[0][1] / total_sample_cnt * 100) if top_f_list else 0
        second_f_ratio = (top_f_list[1][1] / total_sample_cnt * 100) if len(top_f_list) > 1 else 0
        
        is_ts = self._get_timestamp_score(sample_series) == 100
        quality_flags = self._analyze_quality_flags(sample_series)

        len_top10 = " | ".join([str(l) for l, cnt in top_l_list])
        len_top10_pct = " | ".join([f"{round(cnt/total_sample_cnt*100, 2)}%" for l, cnt in top_l_list])
        format_top10 = " | ".join([fmt for fmt, cnt in top_f_list])
        format_top10_pct = " | ".join([f"{round(cnt/total_sample_cnt*100, 2)}%" for fmt, cnt in top_f_list])
        # mode_top10: 전수 기준 상위 10개 추출 (샘플 편향 방지)
        # 소수점 .0 패턴 제거 후 집계 (예: 20121128.0 -> 20121128)
        mode_candidates = val_series_full.apply(
            lambda x: str(x)[:-2] if str(x).endswith('.0') else str(x)
        )
        mode_top10 = " | ".join(mode_candidates.value_counts().head(10).index.astype(str))

        detail_type, val_rate = Detail_Type(format_top10, format_top10_pct, mode_top10)

        return {
            'FileName': file_name, 'ColumnName': col,
            'IsTimestampCol': is_ts,
            'DataType': detail_type,
            'ValidationRate': val_rate,
            'RecCnt': rec_cnt, 'ValueCnt': len(val_series_full),
            'UniqueCnt': unique_val_cnt, 'Unique(%)': round(unique_pct, 2),
            'NullCnt': null_cnt, 'Null%': round(null_cnt/rec_cnt*100, 2),
            'LenCnt': len_s.nunique(),
            'MinLen': len_s.min(), 
            'MaxLen': len_s.max(), 
            'LenMode': int(len_s.mode()[0]) if not len_s.empty else 0,
            'LenTop10': len_top10,
            'LenTop10%': len_top10_pct,
            'FormatCnt': len(f_counts),
            'FormatTop10': format_top10,
            'FormatTop10%': format_top10_pct,
            # 'FormatTop10%_First': round(first_f_ratio, 2),
            'HangulCnt': hangul_cnt, 'SpecialCnt': special_cnt, 'ChineseCnt': chinese_cnt,
            'BrokenHangulCnt': broken_cnt, 'JapaneseCnt': japanese_cnt,
            'UnicodeCnt': unicode_cnt, 'BlankCnt': blank_cnt,
            'MinString': min_string, 'MaxString': max_string, 'ModeString': mode_val,
            'ModeTop10': mode_top10,
            'HasNull': null_cnt > 0, 
            **quality_flags
        }

# ---------------------------------------------------------------------------
# 3. Profiling Manager (전체 실행 제어)
# ---------------------------------------------------------------------------
class ProfilingManager:
    def __init__(self, loader: DataLoader, profiler: DataProfiler):
        self.loader = loader
        self.profiler = profiler
        self.summary_results = [] # 통계용 (Column 단위 요약)
        self.format_results = []  # 상세 포맷용 (File, Column, Format, Count)

    def run(self, summary_name="DataProfile.csv", detail_name="DataFormat.csv"):
        print("데이터 프로파일링 작업을 시작합니다. 시간이 많이 소요될 수 있습니다.")
        datasets = self.loader.load_data()
        
        for file_name, df in datasets:
            # if file_name != TEST_FILE_NAME:
            #     continue
            df.columns = [str(c).strip() for c in df.columns]
            for col in df.columns:
                # 1. 통계용 프로파일링 실행 (기존 로직)
                res = self.profiler.profile_column(df, col, file_name)
                if res:
                    self.summary_results.append(res)
                
                # 2. 상세 포맷 분석 실행 (요청하신 File, Column, Format, Count 정보)
                # 샘플링 데이터를 바탕으로 해당 컬럼 내 포맷 분포를 모두 추출
                valid_series = df[col].dropna().astype(str).str.strip()
                valid_series = valid_series[valid_series != '']
                
                if not valid_series.empty:
                    # 패턴 추출 및 카운트
                    patterns = valid_series.apply(self.profiler._get_detailed_pattern)
                    pattern_counts = patterns.value_counts()
                    
                    # 상위 20개의 Format 정보 추출
                    top_20_patterns = pattern_counts.head(20)
                    for fmt, count in top_20_patterns.items():
                        self.format_results.append({
                            'FileName': file_name,
                            'ColumnName': col,
                            'Format': fmt,
                            'Count': count
                        })
        
        # 파일 저장 로직
        output_path = ROOT_PATH / 'DS_Output'
        output_path.mkdir(parents=True, exist_ok=True)

        # [통계 저장]
        if self.summary_results:
            pd.DataFrame(self.summary_results).to_csv(output_path / summary_name, index=False, encoding='utf-8-sig')
            print(f"데이터 프로파일링 저장: {summary_name}")

        # [상세 포맷 저장] - 요청하신 규격 (File, Column, Format, Count)
        if self.format_results:
            pd.DataFrame(self.format_results).to_csv(output_path / detail_name, index=False, encoding='utf-8-sig')
            print(f"데이터 포맷 저장: {detail_name}")

# ---------------------------------------------------------------------------
# 실행부
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import time
    start_time = time.time()
    if getattr(sys, 'frozen', False):
        ROOT_PATH = Path(sys.executable).parent
    else:
        ROOT_PATH = Path(__file__).resolve().parents[1]

    # 1. 소스 읽기 객체 생성 (CSV)
    csv_loader = CSVDataLoader(ROOT_PATH / 'DS_Input' / 'Internal')
    
    # 2. 분석 엔진 객체 생성
    profiler_engine = DataProfiler(sample_size=10000)
    
    # 3. 매니저를 통한 실행
    manager = ProfilingManager(loader=csv_loader, profiler=profiler_engine)
    manager.run()

    end_time = time.time()
    print("-" * 30)
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print("-" * 30)