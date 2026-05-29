# DS_32_Similarity Analysis.py
# 컬럼 유사도 분석
# 미완성.  전체 로직 재 검토해야 함.  
# 2026.02.04
import pandas as pd
import itertools
import re
from pathlib import Path

# [경로 설정]
ROOT_PATH = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT_PATH / 'DS_Output' / '통합_컬럼_프로파일링_통계.csv'  # DS_31_Sliding Window.py 에서 생성한 파일
SIMILARITY_OUTPUT = ROOT_PATH / 'DS_Output' / '상세_컬럼_유사도_분석_결과.csv'

def is_temporal_data(mode_string):
    """시계열 데이터 노이즈 판별 (nn:nn.n 및 주요 날짜 패턴)"""
    if pd.isna(mode_string) or mode_string == "": return False
    modes = [m.strip() for m in str(mode_string).split('|')]
    temporal_patterns = [
        r'^\d{2}:\d{2}\.\d+$', r'^\d{4}-\d{2}-\d{2}$', r'^\d{8}$',
        r'^\d{2}:\d{2}:\d{2}$', r'^\d{4}-\d{2}-\d{2}.*', r'^\d{2}:\d{2}$'
    ]
    match_count = sum(1 for val in modes if any(re.match(pat, val) for pat in temporal_patterns))
    return (match_count / len(modes)) >= 0.3 if modes else False

def get_refined_format_set(format_str, ratio_str, min_ratio=0.1):
    """10% 미만 점유율 포맷 제거"""
    if pd.isna(format_str) or pd.isna(ratio_str): return set()
    formats = [f.strip() for f in str(format_str).split('|')]
    try:
        ratios = [float(r.strip().replace('%', '')) / 100 for r in str(ratio_str).split('|')]
        return {f for f, r in zip(formats, ratios) if r >= min_ratio}
    except:
        return set(formats)

def calculate_jaccard(set_a, set_b):
    if not set_a or not set_b: return 0.0
    return len(set_a.intersection(set_b)) / len(set_a.union(set_b))

def run_precision_analysis(threshold=0.3):
    if not INPUT_FILE.exists():
        print(f"❌ 입력 파일 없음: {INPUT_FILE}")
        return

    # 데이터 로드
    df = pd.read_csv(INPUT_FILE)
    
    # MaxLen 필터링 및 UniqueRate 계산
    df['MaxLen'] = pd.to_numeric(df['MaxLen'], errors='coerce').fillna(0)
    df_filtered = df[(df['MaxLen'] > 1) & (df['MaxLen'] <= 100)].copy()
    df_filtered['UniqueRate'] = (df_filtered['UniqueCnt'] / df_filtered['ValueCnt']).round(4)
    
    cols = df_filtered.to_dict('records')
    results = []
    
    print(f"🚀 분석 시작 (Threshold: {threshold}, 순차 처리 중...)")

    # 순서 보존을 위해 combinations를 그대로 사용 (내부적으로 입력 순서 유지)
    for col1, col2 in itertools.combinations(cols, 2):
        # 1. 시계열 데이터 스킵
        if is_temporal_data(col1['ModeTop10']) or is_temporal_data(col2['ModeTop10']):
            continue

        # 2. Format 유사도 계산
        f1_set = get_refined_format_set(col1['FormatTop10'], col1['FormatTop10%'])
        f2_set = get_refined_format_set(col2['FormatTop10'], col2['FormatTop10%'])
        if not f1_set or not f2_set: continue
        s_format = calculate_jaccard(f1_set, f2_set)
        
        # 3. Mode 유사도 계산
        m1_set = set([m.strip() for m in str(col1['ModeTop10']).split('|')])
        m2_set = set([m.strip() for m in str(col2['ModeTop10']).split('|')])
        s_mode = calculate_jaccard(m1_set, m2_set)
        
        # 4. 종합 점수 및 페널티
        similarity_score = (s_format * 0.5) + (s_mode * 0.5)
        if col1['OnlyNumber'] != col2['OnlyNumber']:
            similarity_score *= 0.8

        if similarity_score >= threshold:
            results.append({
                'Similarity_Score': round(similarity_score, 4),
                'Format_Score': round(s_format, 4),
                'Mode_Score': round(s_mode, 4),
                'File_A': col1['FileName'],
                'Col_A': col1['ColumnName'],
                'A_Unique%': col1['UniqueRate'],
                'A_ModeTop10': col1['ModeTop10'],
                'File_B': col2['FileName'],
                'Col_B': col2['ColumnName'],
                'B_Unique%': col2['UniqueRate'],
                'B_ModeTop10': col2['ModeTop10'],
                'Common_Formats': " | ".join(f1_set.intersection(f2_set)), # 복원
                'Common_Values': " | ".join(m1_set.intersection(m2_set))
            })

    # 정렬 없이 결과 저장
    result_df = pd.DataFrame(results)
    result_df.to_csv(SIMILARITY_OUTPUT, index=False, encoding='utf-8-sig')
    print(f"✅ 리포트 생성 완료 (정렬 미적용): {SIMILARITY_OUTPUT}")

if __name__ == "__main__":
    run_precision_analysis(threshold=0.3)