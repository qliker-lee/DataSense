import pandas as pd
import numpy as np
import sys
from pathlib import Path

from dq_datatype import Data_Type_Analysis

#---------------------------------------------------------------------------
# 1. Data Profile Processor 계층 (데이터 프로파일링 전처리)
#---------------------------------------------------------------------------
class DataQualityAnalysis:
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

    def dataqualityanalysis_1st(self, df: pd.DataFrame) -> pd.DataFrame:
        # csv 파일을 읽어오면 모든 컬럼을 문자열로 변환한 경우에는 아래 함수를 사용해야 합니다. 
        # 숫자 비교에 사용하는 컬럼은 타입을 정규화
        # numeric_cols = ['ValueCnt', 'Unique(%)', 'MaxLen']
        # for col in numeric_cols:
        #     if col in df.columns:
        #         df[col] = (
        #             pd.to_numeric(
        #                 df[col].astype(str).str.replace(",", ""),
        #                 errors='coerce'
        #             )
        #             .fillna(0)
        #         )

        # # 불리언 비교에 사용하는 컬럼은 타입을 정규화
        # def _to_bool(value: object) -> bool:
        #     if isinstance(value, bool):
        #         return value
        #     s = str(value).strip().lower()
        #     if s in ('true', '1', 'y', 'yes', 't'):
        #         return True
        #     if s in ('false', '0', 'n', 'no', 'f', ''):
        #         return False
        #     return False

        # bool_cols = ['IsTimestampCol', 'HasBlank', 'HasBrokenKorea', 'HasUnicode', 'HasNull']
        # for col in bool_cols:
        #     if col in df.columns:
        #         df[col] = df[col].apply(_to_bool)

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

        df['CodeCandidate'] = df.apply(self._code_candidate_analysis, axis=1)
        df['DetailDataType'] = df.apply(self._detail_datatype, axis=1)

        # IsTimestampCol 가 False 이고 MaxLen > 1 이고 HasBlank = False 이고 LenCnt >95% Index 가 1~5 사이이면 CodeFlag 를 True 로 한다.
        df['CodeFlag'] = np.where((df['IsTimestampCol'] == False) &
                        (df['UniqueCnt'] >=  10) &
                        (df['HasBlank'] == False) & 
                        (df['MaxLen'] > 1) &
                        (df['Len_95%_Idx'].between(1, 5, inclusive="both")),
                        True, False)

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
        
    def create_dataqualityanalysis(self) -> pd.DataFrame:

        df = self.load_input_data()
        if df is None: return

        df_processed = self.dataqualityanalysis_1st(df)

        base_cols = [
            'FileName', 'ColumnName', 'IsTimestampCol', 'ValueCnt', 'Unique(%)', 'CodeFlag', 'CodeCandidate', 
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
            print(f"DataQualityAnalysis.csv 생성 완료: {output_file}")
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
class DataQualityReport:
    """Quality_Advanced_Report.csv 생성 클래스"""
    def __init__(self):
        if getattr(sys, 'frozen', False):
            self.root_path = Path(sys.executable).parent
        else:
            self.root_path = Path(__file__).resolve().parents[1]
            
        self.input_file = self.root_path / 'DS_Output' / 'DataQualityAnalysis.csv'
        self.output_path = self.root_path / 'DS_Output'

    def create_dataqualityreport(self):
        if not self.input_file.exists(): return
        df = pd.read_csv(self.input_file)
        
        reports = []
        for _, row in df.iterrows():
            # 분석 단계별 세부 로직 호출
            status_level = self._get_status_level(row)
            reports.append({
                'FileName': row['FileName'],
                'ColumnName': row['ColumnName'],
                '유일성(Unique(%))': row['Unique(%)'],
                'UniqueCnt': row['UniqueCnt'],
                '무결성(Integrity)': round((100 - row['Null%']), 2),
                'Code Flag': row['CodeFlag'],
                'HasBlank': row['HasBlank'],
                'Grade': self._calculate_grade(row),
                'Value Issue': self._analyze_value(row),
                # 'Quality Issue': self._analyze_quality(row),
                # 'Summary': self._analyze_distribution(row),
                'Character Issue': self._analyze_character_issue(row)[0],
                'Character Issue Score': self._analyze_character_issue(row)[1],
                # 'RiskAssessment': self._assess_risk(row),
                # 'ActionPlan': self._get_action_plan(row, status_level)
            })

        result_df = pd.DataFrame(reports)
        save_file = self.output_path / 'DataQualityReport.csv'
        try:
            result_df.to_csv(save_file, index=False, encoding='utf-8-sig')
            print(f"DataQualityReport.csv 생성 완료: {save_file}")
        except Exception as e:
            print(f"DataQualityReport.csv 저장 실패: {e}")


    def _calculate_grade(self, row):
        """가중치 기반의 정교한 점수 산정"""
        score = 100
        if row['NullCnt'] > 0: score -= (row['Null%'] * 0.5 + 10)
        if row['HasBrokenKorea']: score -= 30
        if row['Format_95%_Sum'] > 3: score -= 15
        if row['Code Has Null']: score -= 20
        
        if score >= 95: return "S (최상)"
        elif score >= 85: return "A (우수)"
        elif score >= 70: return "B (일반)"
        elif score >= 50: return "C (주의)"
        else: return "D (심각)"

    def _analyze_value(self, row):
        """데이터 값 진단"""
        desc = ""
        value_issue_score = 0
        if row['HasHangul'] and row['HasBlank'] and row['HasNull']:
            desc += f"Text 형태로서 Null ({row['Null%']}%)이 존재합니다."
        if row['HasHangul'] and row['HasBlank'] == False and row['HasNull']:
            desc += f"한글이 포함된 명칭 컬럼으로서 Null ({row['Null%']}%)이 존재합니다."

        elif row['DataType'] == 'TIMESTAMP' and row['HasNull']:
            desc += f"데이터 타입이 'TIMESTAMP' 이나 Null ({row['Null%']}%)이 존재합니다. (심각)"
            value_issue_score = 20
        elif row['DataType'] == 'TIMESTAMP' and row['Unique(%)'] < 100:
            desc += f"데이터 타입이 'TIMESTAMP' 이나 유니크한 값이 아닙니다."
            value_issue_score = 10

        elif row['DataType'] == 'TIMESTAMP' and row['UniqueCnt'] == 1:
            desc += f"데이터 타입이 'TIMESTAMP' 이나 단일값만 존재합니다."
            value_issue_score = 10
        elif row['DataType'] == 'YN_Flag' and row['UniqueCnt'] == 1:
            desc += f"데이터 타입이 'YN_Flag' 이나 단일값만 존재합니다."
            value_issue_score = 10
        elif row['DataType'] == 'YN_Flag' and row['UniqueCnt'] > 2:
            desc += f"데이터 타입이 'YN_Flag' 이나 'Y' 또는 'N' 이 아닌 값이 존재합니다."
            value_issue_score = 10
        elif row['ValueCnt'] > 0 and row['UniqueCnt'] == 1:
            desc += f"모두 동일한 값입니다."
            value_issue_score = 10
        elif row['CodeFlag'] == True and row['DataType'] != 'TIMESTAMP' and row['ValueCnt'] > 0 and row['Unique(%)'] == 100:
            desc += f"유일성 100% PK 후보컬럼입니다."
        elif row['DataType'] != 'TIMESTAMP' and row['ValueCnt'] > 0 and row['Unique(%)'] == 100:
            desc += f"유일성 100% 이나, PK는 고려대상입니다."

        return desc

    def _analyze_quality(self, row):
        """데이터 품질 진단"""

        good_data_pct = row['Format_95%_Sum']
        # 소수점 두자리로 변환
        bad_data_pct = round(100 - good_data_pct, 2)

        desc = ""

        if row['Quality Check'] == True and row['CodeFlag'] == True:
            desc += f"코드 후보 컬럼으로서 데이터 포맷은 {row['FormatCnt']} 종류인데 {row['Format_95%_Idx']} 종류가 {row['Format_95%_Sum']}% 차지하며 {bad_data_pct}%는 검사가 필요합니다."
        
        return desc

    def _analyze_distribution(self, row):
        """데이터 분포 및 형상의 안정성 진단"""
        desc = f"현재 {row['ValueCnt']}건의 데이터가 존재하며, "
        
        # 분포 안정성 진단
        if row['Format_95%_Sum'] == 1:
            desc += "단일 데이터 포맷으로 구성된 매우 안정적인 구조입니다."
        elif row['Format_95%_Sum'] <= 3:
            desc += f"주요 {row['Format_95%_Sum']}개 패턴이 전체의 95%를 차지하는 표준화된 상태입니다."
        else:
            desc += f"데이터 패턴이 {row['Format_95%_Sum']}종으로 파편화되어 있어 입력 규칙 확인이 시급합니다."
        
        return desc

    def _analyze_character_issue(self, row):
        """기술적 결함의 구체적 원인 추정"""
        issues = ""
        character_issue_score = 0
        if row['HasBrokenKorea'] == True and row['HasUnicode'] == True:
            issues += f"한글 미완성 문자 ({row['BrokenHangulCnt']}건) 와 비표준 유니코드 ({row['UnicodeCnt']}건)"
            character_issue_score = 10
        elif row['HasUnicode'] == True:
            issues += f"비표준 유니코드 ({row['UnicodeCnt']}건)"
            character_issue_score = 10
        elif row['HasBrokenKorea'] == True:
            issues += f"한글 미완성 문자 ({row['BrokenHangulCnt']}건)"
            character_issue_score = 10

        return issues, character_issue_score

    def _assess_risk(self, row):
        """비즈니스 및 분석적 관점의 리스크 평가"""
        if row['IsTimestampCol'] and row['NullCnt'] > 0:
            return "Critical: 시간 데이터 누락으로 인해 일자별 통계 및 추세 분석 시 데이터 왜곡 발생 위험."
        if row['CodeFlag'] and row['Code Has Null']:
            return "High: 마스터 코드와 매핑되지 않는 데이터 발생으로 인해 참조 무결성 오류 위험."
        if row['Unique(%)'] > 95 and row['Unique(%)'] < 100:
            return "Medium: PK 성격의 컬럼이나 미세한 중복이 존재함. 중복 입력 로직 점검 필요."
        return "Low: 분석에 영향을 주는 특이 리스크 없음."

    def _get_action_plan(self, row, level):
        """단계별 구체적 조치 가이드"""
        plans = []
        if row['NullCnt'] > 0:
            plans.append(f"1. 누락 데이터({row['NullCnt']}건)에 대한 기본값(Default) 채우기 또는 소스 재추출.")
        if row['Format_95%_Sum'] > 2:
            plans.append(f"2. {row['FormatTop10']} 외 비표준 포맷 데이터 클렌징.")
        if row['CharCheck']:
            plans.append("3. 정규표현식을 이용한 특수문자 및 깨진 글자 일괄 치환 스크립트 실행.")
        
        return "\n".join(plans) if plans else "현재 데이터 품질 정책 유지"

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
    # 1. 데이터 프로파일링 객체 생성
    dataqualityanalysis = DataQualityAnalysis()
    dataqualityanalysis.create_dataqualityanalysis()

    # 2. 고도화 리포트 생성 엔진 객체 생성
    dataqualityreport = DataQualityReport()
    dataqualityreport.create_dataqualityreport()
    
    end_time = time.time()
    print(f"\nTime taken: {end_time - start_time:.2f} seconds")
    print("-" * 50)

if __name__ == "__main__":
    main()