# dq_datatype.py
# 데이터 타입 분석 함수
# 2026.02.17 최초 작성, Qiler
# DS_31_Quality_Rule.py 에서 사용됨 (Data_Type_Analysis 함수)

import pandas as pd
from datetime import datetime
import re
from typing import Set

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
# 유효성 검증 함수
#---------------------------------------------------------------
def validate_date(value) -> bool:
    """
    YYYYMMDD 유효성 검증
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

    if int(s[0:2]) > 30: 
        return False
    # 폴백: 기존 로직
    try:
        datetime.strptime(digits, "%y%m%d")
        return True
    except ValueError:
        return False


def validate_yearmonth(value) -> bool:
    try:
        s = str(value)
        if s.endswith('.0'):
            s = s[:-2]
        nums = re.sub(r'[^0-9]', '', s)
        if len(nums) != 6:
            return False
        y, m = int(nums[:4]), int(nums[4:])
        return ((1900 <= y <= 2100) or (y == 9999)) and (1 <= m <= 12)
    except Exception:
        return False


def validate_year(value) -> bool:
    try:
        s = str(value)
        if s.endswith('.0'):
            s = s[:-2]
        y = int(s)
        return 1900 <= y <= 2999
    except Exception:
        return False


def validate_YN_Flag(val: str) -> bool:
    return str(val).upper() in ["Y", "N"]


def validate_01_Flag(val: str) -> bool:
    return str(val).upper() in ["0", "1"]


def validate_Alpha_Flag(val: str) -> bool:
    return str(val).upper() in [
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
        "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    ]


def validate_time(val: str) -> bool:
    # 앞에 5자리를 잘라서 검증
    val = val[:5]
    pattern_1 = r"^\d{2}:\d{2}$"
    pattern_2 = r"^\d{1}:\d{2}$"
    pattern_3 = r"^\d{1}:\d{2}.$"

    if (
        not re.fullmatch(pattern_1, str(val))
        and not re.fullmatch(pattern_2, str(val))
        and not re.fullmatch(pattern_3, str(val))
    ):
        print(f"debug 13 : time is not valid: val = {val}")
        return False
    return True


def validate_timestamp(val: str) -> bool:
    # 타임스탬프 검증 값을 파싱하여 날짜와 시간으로 분리하여 검증
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
# 데이터 타입 분석 (Main Function)
#---------------------------------------------------------------
def Data_Type_Analysis(df: pd.DataFrame, row_index: int):
    """
    상위 10개 샘플(ModeTop10)을 검사하여
    가장 많이 일치하는 데이터 타입과 그 유효율(10개 중 통과 개수 %)을 리턴합니다.
    """
    data_type = ''
    validation_rate = 0.0

    format_top10 = df.at[row_index, 'FormatTop10%']
    format_top10pct = df.at[row_index, 'FormatTop10%']
    mode_top10 = df.at[row_index, 'ModeTop10']

    # 리스트 변환 (공백 제거 및 필터링)
    format_top10_list = [fmt.strip() for fmt in str(format_top10).split(' | ') if str(fmt).strip() != '']
    mode_top10_list = [i.strip() for i in str(mode_top10).split(' | ') if str(i).strip() != '']
    format_for_modes = [get_detailed_pattern_value(m) for m in mode_top10_list]

    # 실제 검사할 샘플 개수 (ModeTop10 기준)
    sample_size = len(mode_top10_list)
    if sample_size == 0:
        return data_type, validation_rate

    # 패턴 정의 (기존 유지) ([포맷, [Mmode] 구조임)
    patterns_map = {
        'TIMESTAMP': (['nnnn-nn-nn nn:nn:nn', 'nnnn-nn-nn nn:nn', 'nnnn-nn-nn n:nn', 'nnnn-nn-nn nn:nn:nn.nnnnnn', 'nnnn-nn-nn nn:nn:nn.'], validate_timestamp),
        'TIME': (['nn:nn.n', 'nn:nn:nn', 'nn:nn:nn.nnnnnn', 'nn:nn:nn.'], validate_time),
        # 'YYMMDD': (['nnnnnn', 'nn-nn-nn', 'nn/nn/nn', 'nn.nn.nn', 'nn.nn.nn.'], validate_YYMMDD),
        'DATECHAR': (['nnnnnnnn', 'nnnn-nn-nn', 'nnnn/nn/nn', 'nnnnKnnKnnK', 'nnnn.nn.nn', 'nnnn. n. nn.', 'nnnnK nK nnK KKK', 'nnnnK nnK nnK KKK', 'nnnnK nK nK KKK', 'nnnnK nnK nK KKK',], validate_date),
        'YEARMONTH': (['nnnnnn', 'nnnn-nn', 'nnnn/nn', 'nnnn.nn', 'nnnnKnnK'], validate_yearmonth),
        'YEAR': (['nnnn'], validate_year),
        'YN_Flag': (['A', 'a'], validate_YN_Flag),
        '01_Flag': (['n'], validate_01_Flag),
        'Alpha_Flag': (['A', 'a'], validate_Alpha_Flag),
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
        if validation_rate >= 70.0:
            data_type = best_type

        # data_type = best_type

    return data_type, validation_rate
