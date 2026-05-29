# -*- coding: utf-8 -*-
"""
dq_validate.py 검증기 — 각 validate_* 함수에 샘플 값을 넣어 적합 여부를 표로 확인합니다.

실행 (프로젝트 루트에서):
  python util/dq_validate_selftest.py
  python util/dq_validate_selftest.py --no-init
  python util/dq_validate_selftest.py --root C:/path/to/project

참조 CSV(시도/시군구 등)가 없으면 --no-init 으로도 대부분의 순수 형식 검증은 테스트 가능합니다.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

# 이 파일 위치: .../QDQM/util/dq_validate_selftest.py
ROOT = Path(__file__).resolve().parents[1]
UTIL = Path(__file__).resolve().parent


def _load_dq_validate():
    """이 저장소의 util/dq_validate.py 를 항상 파일 경로로 로드 (sys.modules 충돌 방지)."""
    path = UTIL / "dq_validate.py"
    if not path.is_file():
        raise ImportError(f"dq_validate 를 찾을 수 없습니다: {path}")

    for p in (str(ROOT), str(UTIL)):
        if p not in sys.path:
            sys.path.insert(0, p)

    mod_name = "_qdqm_dq_validate_runtime"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"dq_validate spec 생성 실패: {path}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    print(f"dq_validate.py 로드 성공: {path}")
    return m


def _run_bool_cases(
    label: str,
    fn: Callable[..., Any],
    cases: Iterable[tuple[Any, Optional[bool]]],
    failures: list[str],
) -> None:
    print(f"\n=== {label} ===")
    for val, expected in cases:
        try:
            got = fn(val)
        except Exception as e:
            msg = f"  FAIL {label}({val!r}) raised {type(e).__name__}: {e}"
            print(msg)
            failures.append(msg)
            continue
        if expected is None:
            print(f"  .. {val!r} -> {got!r}  (기대값 검증 생략)")
            continue
        ok = bool(got) == expected
        sym = "OK " if ok else "XX "
        print(f"  {sym} {val!r} -> {got!r}  (기대: {expected})")
        if not ok:
            failures.append(f"{label}({val!r}) got={got!r} expected_bool={expected}")


def _run_freeform(label: str, fn: Callable[..., Any], values: Iterable[Any]) -> None:
    print(f"\n=== {label} (기대값 없음 / 결과만 표시) ===")
    for val in values:
        try:
            got = fn(val)
            print(f"  {val!r} -> {got!r}")
        except Exception as e:
            print(f"  {val!r} -> ERROR {type(e).__name__}: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="dq_validate 모듈 자가 점검")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="프로젝트 루트 (init_reference_globals 기준 경로)",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        help="참조 CSV 로드 생략 (SIDO/Sigungu 등 전역 세트 비어 있음)",
    )
    parser.add_argument(
        "--strict-csv",
        action="store_true",
        help="시도/시군구 CSV 에서 엄격 컬럼명 요구 (기본: 완화)",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    dv = _load_dq_validate()

    if not args.no_init and hasattr(dv, "init_reference_globals"):
        print(f"[INIT] root={root}")
        dv.init_reference_globals(
            root, strict_columns=args.strict_csv, verbose=True
        )
        if hasattr(dv, "SIDO_SET"):
            print(
                f"       SIDO:{len(dv.SIDO_SET)} SIGUNGU:{len(dv.SIGUNGU_SET)} "
                f"KOR_NAME:{len(dv.KOR_NAME_SET)} ISO3:{len(dv.COUNTRY_ISO3_SET)} "
                f"YMD8:{len(getattr(dv, 'YMD8_SET', set()))} "
                f"YYMMDD:{len(getattr(dv, 'YYMMDD_SET', set()))}"
            )
    else:
        print("[INIT] 생략 (--no-init)")

    failures: list[str] = []

    # _run_bool_cases(
    #     "validate_email",
    #     dv.validate_email,
    #     [
    #         ("user.name+tag@example.co.kr", True),
    #         ("qliker@", False),
    #         ("qliker.com", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_url",
    #     dv.validate_url,
    #     [
    #         ("https://example.com/path?q=1", True),
    #         ("http://localhost:8080/", True),
    #         ("not-a-url", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_year",
    #     dv.validate_year,
    #     [
    #         ("2024", True),
    #         ("1899", False),
    #         ("abc", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_yearmonth",
    #     dv.validate_yearmonth,
    #     [
    #         ("202405", True),
    #         ("202413", False),
    #         ("20240", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_latitude",
    #     dv.validate_latitude,
    #     [
    #         ("37.5", True),
    #         ("91", False),
    #         ("x", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_longitude",
    #     dv.validate_longitude,
    #     [
    #         ("127.0", True),
    #         ("200", False),
    #     ],
    #     failures,
    # )

    _run_bool_cases(
        "validate_tel",
        dv.validate_tel,
        [
            # 서울 국번 뒤 로컬 첫 자리는 0·1 불가 → 3456… 형태 사용
            ("02-3456-7890", True),
            ("010-2345-6789", True),
            ("010-0234-5678", False),
            ("3456-7890", True),
            ("3387890", True),
            ("a3387890", True),
            ("123", False),
        ],
        failures,
    )

    # _run_bool_cases(
    #     "validate_tel_old",
    #     dv.validate_tel_old,
    #     [
    #         # 서울 국번 뒤 로컬 첫 자리는 0·1 불가 → 3456… 형태 사용
    #         ("02-3456-7890", True),
    #         ("010-2345-6789", True),
    #         ("010-0234-5678", False),
    #         ("3456-7890", True),
    #         ("3387890", True),
    #         ("a3387890", True),
    #         ("123", False),
    #     ],
    #     failures,
    # )

    _run_bool_cases(
        "validate_cellphone",
        dv.validate_cellphone,
        [
            ("010-2345-6789", True),
            ("010-0234-5678", False),
            ("0212345678", False),
        ],
        failures,
    )

    # _run_bool_cases(
    #     "validate_gender",
    #     dv.validate_gender,
    #     [
    #         ("남", True),
    #         ("여", True),
    #         ("M", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_gender_en",
    #     dv.validate_gender_en,
    #     [
    #         ("M", True),
    #         ("f", True),
    #         ("남", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_car_number",
    #     dv.validate_car_number,
    #     [
    #         ("12가1234", True),
    #         ("가나12다1234", True),
    #         ("1234가321", False),
    #         ("12a321", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_time",
    #     dv.validate_time,
    #     [
    #         ("12:30:45", True),
    #         ("12:30.1", True),
    #         # 현재 구현은 HH 범위(0–23)를 검사하지 않고 정규식만 맞춤
    #         ("25:00:00", True),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_timestamp",
    #     dv.validate_timestamp,
    #     [
    #         ("anything", True),
    #         ("", True),
    #     ],
    #     failures,
    # )

    _run_bool_cases(
        "validate_strict_date",
        dv.validate_strict_date,
        [
            ("2024-06-15", True),
            ("20240615", True),
            ("2024/06/15", True),
            ("2024.06.15", True),
            ("20240230", False),
            ("a2024021", False),
        ],
        failures,
    )

    # 날짜: 세트가 비어 있으면 달력/파싱 폴백으로 동작
    # _run_bool_cases(
    #     "validate_YYYYMMDD",
    #     dv.validate_YYYYMMDD,
    #     [
    #         ("20240615", True),
    #         ("20240431", False),
    #         ("20240230", False),
    #         ("20240", False),
    #     ],
    #     failures,
    # )

    # _run_bool_cases(
    #     "validate_YYMMDD",
    #     dv.validate_YYMMDD,
    #     [
    #          ("2024-06-15", True),
    #         ("20240615", True),
    #         ("2024/06/15", True),
    #         ("2024.06.15", True),
    #         ("20240230", False),
    #         ("2024021", False),
    #     ],
    #     failures,
    # )

    _run_bool_cases(
        "validate_date (8자리 추출)",
        dv.validate_date,
        [
            ("2024-06-15", True),
            ("20240615", True),
            ("2024/06/15", True),
            ("2024.06.15", True),
            ("20240230", False),
            ("2024021", False),
        ],
        failures,
    )

    # _run_bool_cases(
    #     "validate_zip_code",
    #     dv.validate_zip_code,
    #     [
    #         ("12345", True),
    #         ("01000", True),
    #         ("63644", True),
    #         ("00000", False),
    #         ("64000", False),
    #         ("a12345", False),
    #     ],
    #     failures,
    # )

    # # ISO3 세트가 로드되면 목록에 없는 코드는 False 가 될 수 있음
    # iso = getattr(dv, "COUNTRY_ISO3_SET", set()) or set()
    # kor_expected = ("KOR" in iso) if iso else True
    # _run_bool_cases(
    #     "validate_country_code",
    #     dv.validate_country_code,
    #     [
    #         ("KOR", kor_expected),
    #         ("kor", kor_expected),
    #         ("USA", True),
    #         ("XX", False),
    #         ("abcd", False),
    #     ],
    #     failures,
    # )

    # validate_kor_name: KOR_NAME_SET 비어 있으면 완화하여 항상 True (dq_validate 구현과 동일)
    kor_set = getattr(dv, "KOR_NAME_SET", set()) or set()
    if not kor_set:
        print("KOR_NAME_SET is empty")
        kor_cases: list[tuple[Any, Optional[bool]]] = [
            ("김철수", True),
            ("김 철수", True),
            ("황보철수", True),
            ("남궁 철수", True),
            ("꽝철수", False),
            ("희딩크", False),
            ("a철수", False),
        ]
    else:
        kor_cases = [
            ("김철수", True),
            ("김 철수", True),
            ("황보철수", True),
            ("남궁 철수", True),
            ("꽝철수", False),
            ("희딩크", False),
            ("a철수", False),
        ]
    _run_bool_cases("validate_kor_name", dv.validate_kor_name, kor_cases, failures)

    # 법정동/행정동/도로명 코드: 참조 CSV가 로드된 경우 목록 의존이므로 기대값 검증을 생략할 수 있음
    b_dong_set = getattr(dv, "B_DONG_SET", set()) or set()
    h_dong_set = getattr(dv, "H_DONG_SET", set()) or set()
    road_set = getattr(dv, "ROAD_CODE_SET", set()) or set()
    _run_bool_cases(
        "validate_b_dong_code",
        dv.validate_b_dong_code,
        [
            ("11680101", True if b_dong_set else True),   # 8자리
            ("11680100", False if h_dong_set else True),  # not found
            ("00-680101", False if b_dong_set else False), # 00 시작은 fallback에서 False
            ("1168010", None if b_dong_set else False),   # 7자리
        ],
        failures,
    )

    _run_bool_cases(
        "validate_h_dong_code",
        dv.validate_h_dong_code,
        [
            ("11110515", True if h_dong_set else True),
            ("11680100", False if h_dong_set else True),    # not found
            ("00-680101", None if h_dong_set else False),
            ("1168010", None if h_dong_set else False),
        ],
        failures,
    )

    _run_bool_cases(
        "validate_road_name_code",
        dv.validate_road_name_code,
        [
            ("12345678", None if road_set else True),     # fallback: 길이>=8
            ("1234-5678", None if road_set else True),    # 숫자만 추출 후 길이>=8
            ("1234567", None if road_set else False),     # 7자리
        ],
        failures,
    )

    # 주소: 참조 CSV 미로드 시 True; 로드 시 시군구 목록에 따라 달라짐
    sid = getattr(dv, "SIDO_SET", set()) or set()
    sgg = getattr(dv, "SIGUNGU_SET", set()) or set()
    addr_expect: Optional[bool] = True
    if sid and sgg:
        addr_expect = None
    _run_bool_cases(
        "validate_address",
        dv.validate_address,
        [
            ("서울특별시 강남구 테헤란로 1", addr_expect),
            ("서울 강남구 테헤란로 1", addr_expect),
            ("서 강남구 테헤란로 1", addr_expect),
            ("경북 안동시 풍산읍", addr_expect),
            ("경상북도 안동시 풍산읍 1", addr_expect),
        ],
        failures,
    )

    _run_bool_cases(
        "validate_rrn (형식+체크섬)",
        dv.validate_rrn,
        [
            ("990101-1000000", False),
            ("620101-3120214", False),
            ("620101-2120215", True),
            ("620101-212021", True),
            ("620230-2120215", False),
            ("abcdefgh", False),
        ],
        failures,
    )

    _run_bool_cases(
        "validate_biz_no",
        dv.validate_biz_no,
        [
            ("1234567890", False),
            ("3380302068", True),
            ("338-03-02068", True),
            ("338815123", False),
            ("a388151234", False),
        ],
        failures,
    )

    _run_bool_cases(
        "validate_corp_no",
        dv.validate_corp_no,
        [
            ("1234567890123", False),
            ("110111-0003204", True),
            ("123456789012", False),
            ("a234567890123", False),
            ("123", False),
        ],
        failures,
    )

    _run_bool_cases(
        "validate_unit_code",
        dv.validate_unit_code,
        [
            ("KG", True),
            ("KGS", True),
            ("개", True),
            ("개수", True),
            ("박스", True),
            ("BOX", True),
            ("KGSS", False),
            ("aKG", False),
        ],
        failures,
    )    

    _run_freeform(
        "validate_korean_number",
        dv.validate_korean_number,
        ["010-2345-6789", "+82 10-2345-6789", "02-2345-6789", "338-2869", "3388134567", "085-338-2869", "02-999-6789"],
    )

    _run_freeform(
        "validate_korean_number_enhanced",
        dv.validate_korean_number_enhanced,
        ["010-2345-6789", "+82 10-2345-6789", "02-2345-6789", "338-2869", "3388134567", "085-338-2869", "02-999-6789"],
    )

    print("\n" + "=" * 60)
    if failures:
        print(f"실패 {len(failures)}건:")
        for f in failures:
            print("  -", f)
        return 1
    print("모든 기대값 비교 테스트 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
