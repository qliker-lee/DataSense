# DS_31_DataProfilingForQuality.py
# 컬럼 프로파일링 통계 클래스 
# 2026.02.05 최초 작성, Qiler
# Author: Qiler

import pandas as pd
import re
import os
import sys
from glob import glob
from pathlib import Path
from collections import Counter
from abc import ABC, abstractmethod

# ---------------------------------------------------------------------------
# 2. Data Profiler 계층 (핵심 분석 로직)
# ---------------------------------------------------------------------------
class DataProfiler:
    def __init__(self, sample_size=10000):
        self.sample_size = sample_size
        self.special_pattern = r'[!@#$%^&*()\-_=+\[\]{}|\\;:\'\",.<>/?`~]'
        self.allowed_pattern = r'[a-zA-Z0-9가-힣ㄱ-ㅎㅏ-ㅣ\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\s' + re.escape(r"""!@#$%^&*()-_=+[{]}\|;:'",.<>/?`~""") + r']'

    def _get_detailed_pattern(self, value):
        val = str(value).strip()
        if not val or val.lower() in ['nan', 'null', '']: return "EMPTY"
        res = []
        for c in val:
            if c.isdigit(): res.append('n')
            elif '\uac00' <= c <= '\ud7a3': res.append('K')
            elif ' ' == c: res.append(' ')
            elif 'a' <= c <= 'z': res.append('a')
            elif 'A' <= c <= 'Z': res.append('A')
            elif c in r"""-.:/\ """: res.append(c)
            elif c in r"""!@#$%^&*()-_=+[{]}\|;:'",.<>/?`~ """: res.append('S')
            else: res.append('U')
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
        res['CharCheck'] = any([res['HasBrokenKorea'], res['HasChinese'], res['HasJapanese'], res['HasBlank'], res['HasUnicode']])
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

        return {
            'FileName': file_name, 'ColumnName': col,
            'IsTimestampCol': is_ts,
            'CodeCandidate': (not is_ts and unique_pct == 100 and len_s.max() < 30 and len(f_counts) < 10),
            'ValueCheck': (len(f_counts) > 1 and first_f_ratio > 90),
            'ValueCheck2': (len(f_counts) > 1 and (first_f_ratio + second_f_ratio) > 90),
            'LenCheck': (len(l_counts) > 1 and first_l_ratio > 90),
            'LenCheck2': (len(l_counts) > 1 and (first_l_ratio + second_l_ratio) > 90),
            'MinString': min_string, 'MaxString': max_string, 'ModeString': mode_val,
            'RecCnt': rec_cnt, 'ValueCnt': len(val_series_full),
            'UniqueCnt': unique_val_cnt, 'Unique(%)': round(unique_pct, 2),
            'MinLen': len_s.min(), 'MaxLen': len_s.max(),
            'LenTop10': " | ".join([str(l) for l, cnt in top_l_list]),
            'LenTop10%': " | ".join([f"{round(cnt/total_sample_cnt*100, 2)}%" for l, cnt in top_l_list]),
            'FormatCnt': len(f_counts),
            'FormatTop10': " | ".join([fmt for fmt, cnt in top_f_list]),
            'FormatTop10%': " | ".join([f"{round(cnt/total_sample_cnt*100, 2)}%" for fmt, cnt in top_f_list]),
            'FormatTop10%_First': round(first_f_ratio, 2),
            'HasNull': null_cnt > 0, 'NullCnt': null_cnt, 'Null%': round(null_cnt/rec_cnt*100, 2),
            'HangulCnt': hangul_cnt, 'SpecialCnt': special_cnt, 'ChineseCnt': chinese_cnt,
            'BrokenHangulCnt': broken_cnt, 'JapaneseCnt': japanese_cnt,
            'UnicodeCnt': unicode_cnt, 'BlankCnt': blank_cnt,
            'ModeTop10': " | ".join([str(i) for i in sample_series.value_counts().head(10).index]),
            **quality_flags
        }
