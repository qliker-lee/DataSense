# DS_31_DataProfilingForQuality.py
# 컬럼 프로파일링 통계
# 2026.02.05 최초 작성, Qiler
# Author: Qiler

import pandas as pd
import numpy as np
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
# 1. Data Loader 계층 (데이터 로드)
# ---------------------------------------------------------------------------
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

        return {
            'FileName': file_name, 'ColumnName': col,
            'IsTimestampCol': is_ts,
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
                
                # 2. 상세 포맷 분석 실행 (File, Column, Format, Count 정보)
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
        if getattr(sys, 'frozen', False):
            root_path = Path(sys.executable).parent
        else:
            root_path = Path(__file__).resolve().parents[1]

        output_path = root_path / 'DS_Output'
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

def main():
    import time
    start_time = time.time()
    if getattr(sys, 'frozen', False):
        ROOT_PATH = Path(sys.executable).parent
    else:
        ROOT_PATH = Path(__file__).resolve().parents[1]

    print("-" * 50)
    print("* DataProfile.csv 생성")
    # 1. 소스 읽기 객체 생성 (CSV)
    csv_loader = CSVDataLoader(ROOT_PATH / 'DS_Input' / 'Internal')
    
    # 2. 분석 엔진 객체 생성
    profiler_engine = DataProfiler(sample_size=10000)
    
    # 3. 매니저를 통한 실행
    manager = ProfilingManager(loader=csv_loader, profiler=profiler_engine)
    manager.run()

    end_time = time.time()
    
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print("-" * 50)

if __name__ == "__main__":
    main()