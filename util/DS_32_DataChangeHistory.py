import pandas as pd
import sys
import time
import re
from pathlib import Path
from collections import Counter

# ---------------------------------------------------------------------------
# 1. Config & Utilities (패턴 생성 및 환경 설정)
# ---------------------------------------------------------------------------
class Config:
    if getattr(sys, 'frozen', False):
        ROOT_PATH = Path(sys.executable).parent
    else:
        ROOT_PATH = Path(__file__).resolve().parents[1]
    
    INPUT_PATH = ROOT_PATH / 'DS_Input' / 'Internal'
    OUTPUT_PATH = ROOT_PATH / 'DS_Output'
    
    # 분석 임계값
    MAX_CHANGE_COUNT = 10
    MIN_TOTAL_ROWS = 100
    MIN_FORMAT_LEN = 3

class PatternUtility:
    @staticmethod
    def get_detailed_pattern(value):
        val = str(value).strip()
        if val.endswith('.0'): val = val[:-2]
        if not val or val.lower() in ['nan', 'null', '']: return "EMPTY"
        
        res = []
        for c in val:
            if c.isdigit(): res.append('n')
            elif 'a' <= c <= 'z': res.append('a')
            elif 'A' <= c <= 'Z': res.append('A')
            elif '\uac00' <= c <= '\ud7a3': res.append('K')
            elif c in r"""-.:/\ """: res.append(c)
            else: res.append('S')
        return "".join(res)

# ---------------------------------------------------------------------------
# 2. Data Processor (실제 분석 엔진)
# ---------------------------------------------------------------------------
class DataChangeAnalyzer:
    def __init__(self):
        self.all_column_timelines = []
        self.volatility_stats = []
    
    def _safe_to_csv(self, df, path: Path) -> Path:
        """
        CSV 저장 중 PermissionError 발생 시 타임스탬프 파일로 대체 저장.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            df.to_csv(path, index=False, encoding='utf-8-sig')
            return path
        except PermissionError:
            ts = time.strftime("%Y%m%d_%H%M%S")
            alt_path = path.with_name(f"{path.stem}_{ts}{path.suffix}")
            df.to_csv(alt_path, index=False, encoding='utf-8-sig')
            return alt_path

    def load_profile(self):
        profile_file = Config.OUTPUT_PATH / 'DataProfile.csv'
        if not profile_file.exists():
            print(f"❌ {profile_file} 파일을 찾을 수 없습니다.")
            return None
        return pd.read_csv(profile_file)

    def analyze_file(self, file_name, profile_df):
        # 1. 타임스탬프 및 분석 대상 컬럼 필터링
        ts_info = profile_df[(profile_df['FileName'] == file_name) & (profile_df['IsTimestampCol'] == True)]
        if ts_info.empty: return
        
        actual_ts_col = ts_info['ColumnName'].iloc[0]
        
        # 2. 분석 대상 컬럼 필터링
        col_mask = (
            (profile_df['FileName'] == file_name) & 
            (profile_df['FormatCnt'].between(2, 9)) & 
            (profile_df['MaxLen'].between(Config.MIN_FORMAT_LEN + 1, 19)) & 
            (profile_df['HasBlank'] == False) &
            (profile_df['HangulCnt'] / profile_df['RecCnt'] < 0.9) &  # 한글 비율 90% 이하 (한글명칭컬럼 제외)
            (profile_df['Unique(%)'] > 90)  # 유니크 비율 90% 이상 (유니크 비율이 낮은 컬럼 제외)
        )
        target_cols = profile_df[col_mask]['ColumnName'].tolist()
        
        data_file = Config.INPUT_PATH / file_name
        if not data_file.exists() or not target_cols: return

        # 2. 필요한 컬럼만 로드하여 메모리 및 시간 절약
        try:
            df = pd.read_csv(data_file, usecols=[actual_ts_col] + target_cols, dtype=str, encoding='utf-8-sig')
        except Exception as e:
            print(f"⚠️ {file_name} 로드 중 오류: {e}")
            return

        if len(df) <= Config.MIN_TOTAL_ROWS: return

        # 3. 시간 순 정렬
        df[actual_ts_col] = pd.to_datetime(df[actual_ts_col], errors='coerce')
        df = df.dropna(subset=[actual_ts_col]).sort_values(by=actual_ts_col).reset_index(drop=True)

        # 4. 컬럼별 변동 분석 (Sliding Window)
        for col_name in target_cols:
            self._process_column(df, file_name, col_name, actual_ts_col)

    def _process_column(self, df, file_name, col_name, ts_col):
        # 패턴 생성 및 Shift
        fmt_series = df[col_name].apply(PatternUtility.get_detailed_pattern)
        prev_fmt = fmt_series.shift(1)
        prev_val = df[col_name].shift(1)

        # 변동 조건 마스크
        diff_mask = (
            (fmt_series != prev_fmt) & 
            (fmt_series != "EMPTY") & 
            (prev_fmt.notna()) & 
            (prev_fmt != "EMPTY") &
            (fmt_series.str.len() > Config.MIN_FORMAT_LEN) & 
            (prev_fmt.str.len() > Config.MIN_FORMAT_LEN)
        )
        
        total_changes = diff_mask.sum()
        is_meaningful = (0 < total_changes < Config.MAX_CHANGE_COUNT)

        # 통계 저장
        self.volatility_stats.append({
            'FileName': file_name,
            'ColumnName': col_name,
            'TotalRows': len(df),
            'ChangeCount': total_changes,
            'ChangeCode': 1 if is_meaningful else (2 if total_changes >= Config.MAX_CHANGE_COUNT else 3),
            'ChangeStatus': 'Changed' if is_meaningful else ('Variable' if total_changes >= Config.MAX_CHANGE_COUNT else 'Fixed')
        })

        # 상세 내역 저장
        if is_meaningful:
            changes = df[diff_mask].copy()
            for idx, row in changes.iterrows():
                self.all_column_timelines.append({
                    'FileName': file_name,
                    'ColumnName': col_name,
                    'TimestampColumn': ts_col,
                    'EventTimestamp': row[ts_col],
                    'BeforeFormat': prev_fmt[idx],
                    'AfterFormat': fmt_series[idx],
                    'BeforeValue': prev_val[idx],
                    'AfterValue': row[col_name],
                    'ChangeCountInCol': total_changes
                })

    def save_results(self):
        if self.all_column_timelines:
            history_path = self._safe_to_csv(
                pd.DataFrame(self.all_column_timelines),
                Config.OUTPUT_PATH / 'DataChangeHistory.csv'
            )
            stats_path = self._safe_to_csv(
                pd.DataFrame(self.volatility_stats),
                Config.OUTPUT_PATH / 'DataChangeStats.csv'
            )
            print(f"분석 완료! ({len(self.all_column_timelines)}건 추출)")
            print(f"통계 결과: {stats_path}")
            print(f"상세 내역: {history_path}")
        else:
            print("⚠️ DataChangeHistory 분석 결과가 없습니다.")

def main():
    start_time = time.time()
    print("-" * 30)
    print(f"Start Data Change History Analysis...")

    analyzer = DataChangeAnalyzer()
    profile_df = analyzer.load_profile()

    if profile_df is not None:
        target_files = profile_df[profile_df['IsTimestampCol'] == True]['FileName'].unique()
        for f_name in target_files:
            analyzer.analyze_file(f_name, profile_df)
        analyzer.save_results()

    end_time = time.time()
    print(f"Total Time: {end_time - start_time:.2f} seconds")
    print("-" * 30)
# ---------------------------------------------------------------------------
# 3. Main Orchestrator
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()