import pandas as pd
import numpy as np
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from util.dq_datatype import Data_Type_Analysis

#---------------------------------------------------------------------------
# 1. Data Profile Processor 계층 (데이터 프로파일링 전처리)
#---------------------------------------------------------------------------
class DataQualityAnalysisClass:
    """DataQualityAnalysis.csv 생성 클래스"""

    def __init__(self):
        if getattr(sys, 'frozen', False):
            self.root_path = Path(sys.executable).parent
        else:
            self.root_path = Path(__file__).resolve().parents[1]
            
        self.input_file = self.root_path / 'DS_Output' / 'DataProfile.csv'

    def load_input_data(self):
        if not self.input_file.exists(): return
        try:
            df = pd.read_csv(self.input_file, encoding='utf-8-sig', low_memory=False)
        except:
            df = pd.read_csv(self.input_file, encoding='cp949', low_memory=False)
        return df

    @staticmethod
    def _get_over_95_index(value: object) -> int:
        if not isinstance(value, str) or not value.strip():
            return 0
        parts = [p.strip() for p in value.split("|")]
        nums = []
        for p in parts:
            p = p.replace("%", "").strip()
            if not p:
                continue
            try:
                nums.append(float(p))
            except ValueError:
                continue
        if not nums:
            return 0
        cumulative = 0.0
        for i, num in enumerate(nums, start=1):
            cumulative += num
            if cumulative > 95:
                return i
        return 0

    @staticmethod
    def _get_over_95_index_value_sum(value: object, upto_index: object) -> float:
        if not isinstance(value, str) or not value.strip():
            return 0
        parts = [p.strip() for p in value.split("|")]
        nums = []
        for p in parts:
            p = p.replace("%", "").strip()
            if not p:
                continue
            try:
                nums.append(float(p))
            except ValueError:
                continue
        if not nums:
            return 0
        try:
            idx = int(upto_index)
        except (TypeError, ValueError):
            return 0
        if idx <= 0:
            return 0
        return sum(nums[:idx])

    def run_dataqualityanalysis(self, df: pd.DataFrame) -> pd.DataFrame:

        if df is None:
            df = self.load_input_data()
        if df is None: return

        # 데이터 타입 분석에 df 전체를 전달하여 처리
        data_type_results = df.apply(
            lambda r: Data_Type_Analysis(df=df, row_index=r.name),
            # lambda r: Data_Type_Analysis(df['FormatTop10%'], df['FormatTop10%'], df['ModeTop10'], df=df),
            axis=1,
            result_type='expand'
        )
        df['DataType'] = data_type_results[0]
        df['ValidationRate'] = data_type_results[1]


        # Lencnt 가 95% 를 만족하는 값의 인덱스
        df['Len_95%_Idx'] = df['LenTop10%'].apply(self._get_over_95_index)
        # FormatCnt 가 95% 를 만족하는 값의 인덱스
        df['Format_95%_Idx'] = df['FormatTop10%'].apply(self._get_over_95_index)

        # 처음부터 df['LenCnt >95% Index'] 까지의 합계값 
        df['Len_95%_Sum'] = df.apply(
            lambda r: self._get_over_95_index_value_sum(r['LenTop10%'], r['Len_95%_Idx']), 
            axis=1
        )
        # 처음부터 df['FormatCnt >95% Index'] 까지의 합계값 
        df['Format_95%_Sum'] = df.apply(
            lambda r: self._get_over_95_index_value_sum(r['FormatTop10%'], r['Format_95%_Idx']), 
            axis=1
        )

        df['CodeFlag'] = df.apply(self._code_candidate_analysis, axis=1)
        df['DetailDataType'] = df.apply(self._detail_datatype, axis=1)


        df['Quality'] = np.where(((df['Unique(%)'] == 100) & (df['CodeFlag'] == True) & 
                        ((df['HasBrokenKorea'] == True) | (df['HasUnicode'] == True))) | 
                        ((df['CodeFlag'] == True) & (df['Unique(%)'] < 100) & (df['Format_95%_Sum'] < 100))
                        , '🚨', '')

        df['Quality Check'] = np.where(((df['Unique(%)'] == 100) & (df['CodeFlag'] == True) & 
                        ((df['HasBrokenKorea'] == True) | (df['HasUnicode'] == True))) | 
                        ((df['CodeFlag'] == True) & (df['Unique(%)'] < 100) & (df['Format_95%_Sum'] < 100))
                        , True, False)

        # df['Unique(%)'] < 100 이고 df['CodeFlag'] 가 True 이고 df['LenCnt >95% ValueSum'] < 100 이면 LenCheck 를 True 로 한다.
        df['Len Q'] = np.where(((df['Unique(%)'] == 100) & (df['CodeFlag'] == True) & 
                        ((df['HasBrokenKorea'] == True) | (df['HasUnicode'] == True))) | 
                        ((df['CodeFlag'] == True) & (df['Unique(%)'] < 100) & (df['Len_95%_Sum'] < 100))
                       ,  '👎', '')
        df['Len Q Check'] = np.where(((df['Unique(%)'] == 100) & (df['CodeFlag'] == True) & 
                        ((df['HasBrokenKorea'] == True) | (df['HasUnicode'] == True))) | 
                        ((df['CodeFlag'] == True) & (df['Unique(%)'] < 100) & (df['Len_95%_Sum'] < 100))
                       ,  True, False)


        df['Format Q'] = np.where(((df['Unique(%)'] == 100) & (df['CodeFlag'] == True) & 
                        ((df['HasBrokenKorea'] == True) | (df['HasUnicode'] == True))) | 
                        ((df['CodeFlag'] == True) & (df['Unique(%)'] < 100) & (df['Format_95%_Sum'] < 100))
                        , '👎', '')
        df['Format Q Check'] = np.where(((df['Unique(%)'] == 100) & (df['CodeFlag'] == True) & 
                        ((df['HasBrokenKorea'] == True) | (df['HasUnicode'] == True))) | 
                        ((df['CodeFlag'] == True) & (df['Unique(%)'] < 100) & (df['Format_95%_Sum'] < 100))
                       ,  True, False)

        df['Char Q'] = np.where( (df['HasBrokenKorea'] == True)  
                        | (df['HasUnicode'] == True)
                        , '⚠️', '')

        df['Char Q Check'] = np.where( (df['HasBrokenKorea'] == True)   
                        | (df['HasUnicode'] == True)
                       ,  True, False)

        df['Code Has Null'] = np.where( (df['CodeFlag'] == True) &   
                        (df['HasNull'] == True)
                       ,  True, False)

   
        base_cols = [
            'FileName', 'ColumnName', 'IsTimestampCol', 'ValueCnt', 'Unique(%)', 'CodeFlag', 
            'DetailDataType', 'DataType', 'ValidationRate', 'Quality', 'Len Q', 'Format Q',
            'Char Q', 'HasNull', 'LenCnt', 'Len_95%_Idx', 'Format_95%_Idx',
            'Quality Check', 'Len Q Check', 'Format Q Check', 'Char Q Check'
        ]
        processed_df = df[base_cols].copy()

        # df 에서 processed_df 에 없는 컬럼을 processed_df 에 추가함
        for col in df.columns:
            if col not in processed_df.columns:
                processed_df.loc[:, col] = df[col].values

        # 생성된 processed_df 를 CSV 파일로 저장
        output_path = self.root_path / 'DS_Output'
        output_file = output_path / 'DataQualityAnalysis.csv'
        try:
            processed_df.to_csv(output_file, index=False, encoding='utf-8-sig')
            # print(f"DataQualityAnalysis.csv 생성 완료: {output_file}")
        except Exception as e:
            print(f"DataQualityAnalysis.csv 저장 실패: {e}")

        return processed_df
     

    def _code_candidate_analysis(self, row):
        if row['DataType'] in ['DATECHAR', 'TIMECHAR', 'TIMESTAMP', 'TIME', 'YEAR', 'YEARMONTH']:
            return False
        if row['HasBlank']:
            return False
        if row['UniqueCnt'] < 10:
            return False
        if row['MaxLen'] < 2:
            return False
        if row['Len_95%_Idx'] not in [1, 2, 3, 4, 5]:
            return False
        return True

    def _detail_datatype(self, row):
        data_type = row.get('DataType')
        if isinstance(data_type, str) and data_type.strip():
            return data_type
        if pd.notna(data_type) and not isinstance(data_type, str):
            return str(data_type)

        if row['UniqueCnt'] == 1:
            return "Single Value"

        if row['HasHangul'] and row['HasBlank']:
            return "Hangul Text"
        elif row['HasHangul'] and row['FormatCnt'] < 10:
            return "명칭"

#---------------------------------------------------------------------------
# 2. Advanced Quality Engine 계층 (고도화 리포트 생성)
#---------------------------------------------------------------------------
class DataQualityReportClass:
    """Quality_Advanced_Report.csv 생성 클래스"""
    def __init__(self):
        if getattr(sys, 'frozen', False):
            self.root_path = Path(sys.executable).parent
        else:
            self.root_path = Path(__file__).resolve().parents[1]
            
        self.input_file = self.root_path / 'DS_Output' / 'DataQualityAnalysis.csv'
        self.output_path = self.root_path / 'DS_Output'

    def run_dataqualityreport(self, df: pd.DataFrame):
        if df is None: 
            if not self.input_file.exists(): return
            df = pd.read_csv(self.input_file)
        
        reports = []
        for _, row in df.iterrows():
            # 분석 단계별 세부 로직 호출
            status_level = self._get_status_level(row)
            value_issue = self._analyze_value(row)[0]
            value_score = self._analyze_value(row)[1]
            format_issue = self._analyze_format(row)[0]
            format_score = self._analyze_format(row)[1]
            length_issue = self._analyze_length(row)[0]
            length_score = self._analyze_length(row)[1]
            character_issue = self._analyze_character_issue(row)[0]
            character_score = self._analyze_character_issue(row)[1]
            format_length_issue = self._analyze_format_length(row)[0]
            format_length_score = self._analyze_format_length(row)[1]


            quality_grade, quality_score = self._calculate_quality_score(value_score, format_score, character_score)

            reports.append({
                'FileName': row['FileName'],
                'ColumnName': row['ColumnName'],
                # '유일성(Unique(%))': row['Unique(%)'],
                # 'UniqueCnt': row['UniqueCnt'],
                # '무결성(Integrity)': round((100 - row['Null%']), 2),
                'Quality Grade': quality_grade,
                'Quality Score': quality_score,
                'Value Issue': value_issue,
                'Value Score': value_score,
                'Format Issue': format_issue,
                'Format Score': format_score,
                'Length Issue': length_issue,
                'Length Score': length_score,
                'Character Issue': character_issue,
                'Character Score': character_score,
                'Format Length Issue': format_length_issue,
                'Format Length Score': format_length_score,
            })

        result_df = pd.DataFrame(reports)

        save_file = self.output_path / 'DataQualityReport.csv'
        try:
            result_df.to_csv(save_file, index=False, encoding='utf-8-sig')
            # print(f"DataQualityReport.csv 생성 완료: {save_file}")
        except Exception as e:
            print(f"DataQualityReport.csv 저장 실패: {e}")

        return result_df


    def _calculate_quality_score(self, value_score, format_score, character_score):
        """가중치 기반의 정교한 점수 산정"""
        total_score = 100 - (value_score + format_score + character_score)
        if total_score >= 96: return "S (최상)", 5
        elif total_score >= 86: return "A (양호)", 4
        elif total_score >= 76: return "B (점검)", 3
        elif total_score >= 61: return "C (위험)", 2
        else: return "D (심각)", 1

    def _analyze_value(self, row):
        """데이터 값 진단"""
        desc = ""
        score = 0
        if row['CodeFlag'] == True and row['HasNull'] == True and row['Unique(%)'] == 100:
            desc += f"코드 후보. 유일성 100% 입니다."
            score = score + 40
        elif row['CodeFlag'] == True and row['HasHangul'] == True and row['HasBlank'] == True:
            desc += f"코드 후보. 한글 및 공백(Space)문자가 있습니다."
            score = score + 40
        elif row['CodeFlag'] == True and row['HasHangul'] == False and row['HasBlank'] == True:
            desc += f"코드 후보. 공백(Space)문자가 있습니다."
            score = score + 30
        elif row['CodeFlag'] == True and row['HasHangul'] == True and row['HasBlank'] == False:
            desc += f"코드 후보. 한글 문자가 있습니다."
            score = score + 15

        elif row['DataType'] == 'TIMESTAMP' and row['UniqueCnt'] == 1:
            desc += f"TIMESTAMP 형식이며, 단일값만 있습니다."
            score = score + 10

        elif row['DataType'] == 'TIMESTAMP' and row['Unique(%)'] < 100:
            desc += f"TIMESTAMP 형식이며, 유니크한 값이 아닙니다."
            score = score + 20

        elif row['DataType'] == 'YN_Flag' and row['UniqueCnt'] == 1:
            desc += f"YN_Flag 형식이며, 단일값만 있습니다."
            score = score + 5

        elif row['DataType'] in ['DATECHAR', 'YEAR', 'YEARMONTH'] and row['UniqueCnt'] == 1:
            desc += f"{row['DataType']} 형식이며, 단일값만 있습니다."
            score = score + 10
        elif row['DataType'] in ['DATECHAR', 'YEAR', 'YEARMONTH'] and row['HasBlank'] == 1:
            desc += f"{row['DataType']} 형식이며, 공백(Space)문자가 있습니다."
            score = score + 10
        elif row['DataType'] in ['DATECHAR', 'YEAR', 'YEARMONTH'] and row['HasHangul']:
            desc += f"{row['DataType']} 형식이며, 한글 문자가 있습니다."
            score = score + 10
        elif row['DataType'] in ['DATECHAR', 'YEAR', 'YEARMONTH'] and row['UniqueCnt'] == 1:
            desc += f"{row['DataType']} 형식이며, 단일값만 있습니다."
            score = score + 10

        elif row['UniqueCnt'] == 1:
            desc += f"단일값만 있습니다."
            score = score + 5

        if score <= 10 and row['HasNull'] == True:
            desc += f" Null ({row['Null%']}%)이 있습니다."
            score = score + 5

        return desc, score

    def _analyze_format(self, row):
        """데이터 품질 진단"""
        score = 0
        formatcnt = row['FormatCnt']
        format_95_idx = row['Format_95%_Idx']
        format_95_sum = row['Format_95%_Sum']

        good_data_pct = round(row['Format_95%_Sum'], 2)
        bad_data_pct = round(100 - good_data_pct, 2) # 소수점 두자리로 변환

        issues = ""

        if row['Quality Check'] == True and row['CodeFlag'] == True and row['Format_95%_Idx'] < 6:
            issues += f"데이터 포맷은 {row['FormatCnt']} 종류인데 {row['Format_95%_Idx']} 개가 {good_data_pct}% 차지하며 \n{bad_data_pct}%는 검사가 필요합니다."
            score = score + 20
        elif row['Quality Check'] == True and row['Format_95%_Idx'] < 6 and format_95_idx < formatcnt:
            issues += f"데이터 포맷은 {row['FormatCnt']} 종류인데 {row['Format_95%_Idx']} 개가 {good_data_pct}% 차지하며 \n{bad_data_pct}%는 검사가 필요합니다."
            score = score + 10
        elif row['Quality Check'] == True and row['Format_95%_Idx'] < 11 and format_95_idx < formatcnt:
            issues += f"데이터 포맷은 {row['FormatCnt']} 종류인데 {row['Format_95%_Idx']} 개가 {good_data_pct}% 차지하며 \n{bad_data_pct}%는 검사가 필요합니다."
            score = score + 5
        return issues, score

    def _analyze_length(self, row):
        """데이터 길이 진단"""
        score = 0
        lengthcnt = row['LenCnt']
        length_95_idx = row['Len_95%_Idx']
        length_95_sum = row['Len_95%_Sum']
        good_length_pct = round(row['Len_95%_Sum'], 2)
        bad_length_pct = round(100 - good_length_pct, 2) # 소수점 두자리로 변환

        issues = ""

        if row['Len Q Check'] == True and row['CodeFlag'] == True and length_95_idx < 6:
            issues += f"데이터 길이는 {lengthcnt} 종류인데 {length_95_idx} 개가 {good_length_pct}% 차지하며 \n{bad_length_pct}%는 검사가 필요합니다."
            score = score + 20
        elif row['Len Q Check'] == True and length_95_idx < 6 and length_95_idx < lengthcnt:
            issues += f"데이터 길이는 {lengthcnt} 종류인데 {length_95_idx} 개가 {good_length_pct}% 차지하며 \n{bad_length_pct}%는 검사가 필요합니다."
            score = score + 10
        elif row['Len Q Check'] == True and length_95_idx < 11 and length_95_idx < lengthcnt:
            issues += f"데이터 길이는 {lengthcnt} 종류인데 {length_95_idx} 개가 {good_length_pct}% 차지하며 \n{bad_length_pct}%는 검사가 필요합니다."
            score = score + 5
        return issues, score

    def _analyze_character_issue(self, row):
        """기술적 결함의 구체적 원인 추정"""
        issues = ""
        score = 0
        if row['HasBrokenKorea'] == True and row['HasUnicode'] == True:
            issues += f"한글 미완성 문자 ({row['BrokenHangulCnt']}건) 와 비표준 유니코드 ({row['UnicodeCnt']}건)"
            score = score + 20
        elif row['HasUnicode'] == True:
            issues += f"비표준 유니코드 ({row['UnicodeCnt']}건)"
            score = score + 10
        elif row['HasBrokenKorea'] == True:
            issues += f"한글 미완성 문자 ({row['BrokenHangulCnt']}건)"
            score = score + 10

        if score > 0 and (row['HasChinese'] == True or row['HasJapanese'] == True):
            issues += ", "

        if row['HasChinese'] == True and row['HasJapanese'] == True:
            issues += f" 한자 ({row['ChineseCnt']}건) 와 일본어 ({row['JapaneseCnt']}건) 문자가 있습니다."
        elif row['HasChinese'] == True:
            issues += f" 한자 ({row['ChineseCnt']}건) 문자가 있습니다."
        elif row['HasJapanese'] == True:
            issues += f" 일본어 ({row['JapaneseCnt']}건) 문자가 있습니다."

        return issues, score

    def _analyze_format_length(self, row):
        """데이터 포맷 및 길이 진단"""
        score = 0
        formatcnt = row['FormatCnt']
        format_95_idx = row['Format_95%_Idx']
        format_95_sum = row['Format_95%_Sum']
        lengthcnt = row['LenCnt']
        length_95_idx = row['Len_95%_Idx']
        length_95_sum = row['Len_95%_Sum']

        good_format_pct = round(row['Format_95%_Sum'], 2)
        bad_format_pct = round(100 - good_format_pct, 2) # 소수점 두자리로 변환

        issues = ""

        if row['Quality Check'] == True and formatcnt > lengthcnt:
            issues += f"데이터 길이는 {lengthcnt} 종류인데 데이터 포맷은 {formatcnt} 종류가 있습니다."
            score = score + 1
        return issues, score

    def _analyze_integrity(self, row):
        """무결성 진단"""
        desc = ""
        score = 0
        if row['Null%'] == 100:
            desc += f"값이 Null ({row['Null%']}%) 입니다."
            score = score + 50
        elif row['CodeFlag'] == True and row['HasNull'] == True:
            desc += f"코드 후보, Null ({row['Null%']}%)이 있습니다."
            score = score + 10
        elif row['Null%'] > 50 and row['HasBlank'] == False and row['OnlyAlphaNumber'] == True:
            desc += f"Null ({row['Null%']}%)이 있으며, 공백(Space)문자는 없고, 알파벳과 숫자로만 구성되어 있습니다."
            score = score + 30
        elif row['Null%'] > 50 and row['HasBlank'] == False and row['HasHangul'] == True:
            desc += f"Null ({row['Null%']}%)이 있으며, 공백(Space)문자는 없고, 한글 문자가 있습니다."
            score = score + 20
        elif row['Null%'] > 50 and row['HasBlank'] == True and row['HasHangul'] == True:
            desc += f"Null ({row['Null%']}%)이 있으며, 공백(Space)문자가 있고, 한글 문자가 있습니다."
            score = score + 10
        elif row['Null%'] > 0:
            desc += f"Null ({row['Null%']}%)이 있습니다."
            score = score + 5
            
        return desc, score

    def _get_status_level(self, row):
        # 내부 로직용 상태 분류
        if row['HasBrokenKorea'] or (row['Null%'] > 30): return "Emergency"
        if row['Format_95%_Sum'] > 5: return "Warning"
        return "Normal"

#---------------------------------------------------------------------------
# 3. Main 함수
#---------------------------------------------------------------------------
def main():
    import time
    start_time = time.time()
    if getattr(sys, 'frozen', False):
        ROOT_PATH = Path(sys.executable).parent
    else:
        ROOT_PATH = Path(__file__).resolve().parents[1]

    print("-" * 50)
    print("* DataProfile -> DataQualityAnalysis.csv 생성 - > DataQualityReport.csv 생성")

    # load DataProfile.csv
    df = pd.read_csv(ROOT_PATH / 'DS_Output' / 'DataProfile.csv')

    # 1. 데이터 프로파일링 객체 생성
    dataqualityanalysis = DataQualityAnalysisClass()
    processed_df = dataqualityanalysis.run_dataqualityanalysis(df)

    # 2. 고도화 리포트 생성 엔진 객체 생성
    dataqualityreport = DataQualityReportClass()
    report_df = dataqualityreport.run_dataqualityreport(processed_df)
    
    end_time = time.time()
    print(f"\nTime taken: {end_time - start_time:.2f} seconds")
    print("-" * 50)

if __name__ == "__main__":
    main()