# -*- coding: utf-8 -*-
"""
DataSense DQ Profiling System - Architecture Refactored
Qliker, 2026.05.28 Version 3.0 (Modular & Extensible)
"""

import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from abc import ABC, abstractmethod
import pandas as pd
from multiprocessing import Pool, cpu_count

#---------------------------------------------------------------
# Path & Directory 설정
#---------------------------------------------------------------
if getattr(sys, 'frozen', False): 
    ROOT_PATH = Path(sys.executable).parent
else:   
    ROOT_PATH = Path(__file__).resolve().parents[1]

if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

# ColumnProfiler 인터페이스 임포트
from util.DS_11_Columnprofiler import ColumnProfiler, add_dq_scores

# 글로벌 설정값 유지
FORMAT_FILE = ROOT_PATH / 'DS_Output' / 'FileFormat.csv'
STATS_FILE = ROOT_PATH / 'DS_Output' / 'FileStats.csv'
META_PATH = ROOT_PATH / 'DS_Meta' / 'CodeList_Meta.csv'

def normalize_path(path_str):
    if path_str is None or str(path_str).strip() == "":
        return path_str
    path_str = os.path.expanduser(os.path.expandvars(str(path_str)))
    if not os.path.isabs(path_str):
        path_str = str((ROOT_PATH / path_str).resolve())
    else:
        path_str = str(Path(path_str).resolve())
    return path_str.replace('\\', '/')

#=======================================================================
# [MODULE 1] DATA INPUT LAYER (데이터 입력 부분)
#=======================================================================

class BaseInputReader(ABC):
    """모든 데이터 소스(파일, DB 등) 입력을 위한 추상 베이스 클래스"""
    
    @abstractmethod
    def get_targets(self, meta_item: dict) -> list[dict]:
        """분석 대상을 조회하여 메타 및 청크 처리를 위한 단위를 리스트로 반환"""
        pass

    @abstractmethod
    def read_data_sample(self, target_info: dict, sample_rows: int) -> tuple[pd.DataFrame, dict]:
        """
        분석에 필요한 샘플링된 DataFrame과 해당 소스의 통계(stats) 정보를 반환
        Returns:
            df: 분석 대상 데이터프레임
            stats: 소스 통계 스펙 딕셔너리
        """
        pass


class FileInputReader(BaseInputReader):
    """기존 CSV, XLSX, PKL 파일 로드 및 대용량 청크 샘플링 담당 클래스"""
    
    def __init__(self, large_file_threshold_mb=1000, chunk_size=100000):
        self.large_file_threshold_mb = large_file_threshold_mb
        self.chunk_size = chunk_size
        self.encoding_list = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']

    def _get_file_size_mb(self, file_path):
        try: return os.path.getsize(file_path) / (1024 * 1024)
        except Exception: return 0

    def get_targets(self, meta_item: dict) -> list[dict]:
        target_files = []
        source_path = normalize_path(meta_item['source'])
        ext = meta_item['extension']
        m_type = meta_item['type']
        
        if not os.path.exists(source_path):
            print(f"[Reader] 경로가 존재하지 않습니다: {source_path}")
            return []

        if os.path.isdir(source_path):
            for f in os.listdir(source_path):
                if f.lower().endswith(ext.lower()):
                    target_files.append(os.path.join(source_path, f))
        else:
            target_files.append(source_path)
            
        return [{
            'file_path': f_path, 
            'extension': ext, 
            'master_type': m_type,
            'file_no': idx
        } for idx, f_path in enumerate(target_files, start=1)]

    def read_data_sample(self, target_info: dict, sample_rows: int) -> tuple[pd.DataFrame, dict]:
        file_path = target_info['file_path']
        m_type = target_info['master_type']
        file_no = target_info['file_no']
        
        file_ext = str(os.path.splitext(file_path)[1]).lower().strip('.')
        file_size_mb = self._get_file_size_mb(file_path)
        
        # 대용량 CSV 파일 청크 처리 분기
        if file_ext == 'csv' and file_size_mb > self.large_file_threshold_mb:
            print(f"[Reader] 대용량 파일 청크 샘플링 적용: {os.path.basename(file_path)} ({file_size_mb:.1f}MB)")
            return self._read_csv_chunked(file_path, m_type, file_no, sample_rows, file_size_mb)
        else:
            return self._read_normal(file_path, file_ext, m_type, file_no, sample_rows, file_size_mb)

    def _read_csv_chunked(self, file_path, m_type, file_no, sample_rows, file_size_mb):
        encoding_used = None
        column_cnt = 0
        
        for encoding in self.encoding_list:
            try:
                test_chunk = pd.read_csv(file_path, nrows=100, dtype=str, encoding=encoding, low_memory=False)
                encoding_used = encoding
                column_cnt = len(test_chunk.columns)
                break
            except Exception: continue
            
        if not encoding_used:
            raise ValueError(f"지원하는 인코딩이 없습니다: {file_path}")

        sampled_chunks = []
        total_rows = 0
        accumulated_samples = 0
        
        chunk_reader = pd.read_csv(file_path, chunksize=self.chunk_size, dtype=str, 
                                   encoding=encoding_used, low_memory=False)
        
        for chunk in chunk_reader:
            chunk_rows = len(chunk)
            total_rows += chunk_rows
            
            remaining_samples = sample_rows - accumulated_samples
            if remaining_samples > 0:
                chunk_sample_size = min(chunk_rows, remaining_samples)
                if chunk_rows <= chunk_sample_size:
                    sampled_chunks.append(chunk)
                    accumulated_samples += chunk_rows
                else:
                    sampled_chunks.append(chunk.sample(n=chunk_sample_size, random_state=42))
                    accumulated_samples += chunk_sample_size

        sample_df = pd.concat(sampled_chunks, ignore_index=True) if sampled_chunks else pd.DataFrame()
        
        stats = self._build_stats(file_no, file_path, m_type, total_rows, column_cnt, len(sample_df), file_size_mb)
        return sample_df, stats

    def _read_normal(self, file_path, file_ext, m_type, file_no, sample_rows, file_size_mb):
        df = None
        if file_ext == 'csv':
            for encoding in self.encoding_list:
                try:
                    df = pd.read_csv(file_path, dtype=str, low_memory=False, encoding=encoding)
                    break
                except Exception: continue
        elif file_ext == 'xlsx':
            df = pd.read_excel(file_path, dtype=str)
        elif file_ext == 'pkl':
            df = pd.read_pickle(file_path)
            
        if df is None:
            return pd.DataFrame(), {}
            
        total_rows = len(df)
        sample_df = df if total_rows <= sample_rows else df.sample(n=sample_rows, random_state=42)
        
        stats = self._build_stats(file_no, file_path, m_type, total_rows, len(df.columns), len(sample_df), file_size_mb)
        return sample_df, stats

    def _build_stats(self, file_no, file_path, m_type, total_rows, col_cnt, sample_rows, file_size):
        sampling_pct = round((sample_rows / total_rows * 100) if total_rows > 0 else 0, 2)
        return {
            'FileNo': file_no,
            'FilePath': normalize_path(file_path),
            'FileName': os.path.basename(file_path),
            'MasterType': m_type,
            'RecordCnt': total_rows,
            'ColumnCnt': col_cnt,
            'SamplingRows': sample_rows,
            'Sampling(%)': sampling_pct,
            'FileSize': file_size,
            'WorkDate': datetime.now().strftime('%Y-%m-%d')
        }


class DatabaseInputReader(BaseInputReader):
    """[확장 예시] 향후 RDBMS(Oracle, PostgreSQL 등) 테이블 매핑용 입력 리더"""
    def __init__(self, connection_string=None):
        self.connection_string = connection_string

    def get_targets(self, meta_item: dict) -> list[dict]:
        # 데이터베이스의 경우 source 필드에 테이블명 혹은 스키마명을 기재하여 활용
        return [{'table_name': meta_item['source'], 'master_type': meta_item['type'], 'file_no': 1}]

    def read_data_sample(self, target_info: dict, sample_rows: int) -> tuple[pd.DataFrame, dict]:
        # TODO: SQLAlchemy 혹은 쿼리를 사용한 샘플 및 통계 추출 구현부
        # 예시: "SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT {sample_rows}"
        print(f"[Reader] 데이터베이스 매핑 작동 예정: {target_info['table_name']}")
        return pd.DataFrame(), {}


#=======================================================================
# [MODULE 2] DATA PROCESSING LAYER (데이터 처리 부분)
#=======================================================================

class MasterCodeFormatEngine:
    """순수 비즈니스 로직 연산 가동 엔진 (I/O에 종속되지 않음)"""
    
    def __init__(self, sample_rows=10000):
        self.sample_rows = sample_rows

    def profile_dataframe(self, df: pd.DataFrame, target_info: dict) -> list[dict]:
        """전달받은 순수 데이터프레임과 메타정보를 기반으로 고속 컬럼 프로파일링 가동"""
        col_results = []
        if df.empty:
            return col_results
            
        actual_sample_size = len(df)
        file_name = target_info.get('file_name') or os.path.basename(target_info.get('file_path', 'DB_TABLE'))
        file_path = target_info.get('file_path') or target_info.get('table_name', 'UNKNOWN')
        m_type = target_info.get('master_type', 'Master')
        total_rows = target_info.get('total_rows', actual_sample_size)

        for col in df.columns:
            try:
                # 유틸 모듈 핵심 연산 작동
                res = ColumnProfiler(df, col, actual_sample_size).profile()
                if res:
                    res.update({
                        'MasterType': m_type,
                        'FileName': file_name,
                        'FilePath': normalize_path(file_path),
                        'RecordCnt': total_rows
                    })
                    col_results.append(res)
            except Exception as e:
                print(f"[Engine] 컬럼 프로파일링 연산 실패 (컬럼: {col}): {e}")
                continue
                
        return col_results


#=======================================================================
# [MODULE 3] DATA OUTPUT LAYER (결과물 최종 저장 부분)
#=======================================================================

class BaseOutputWriter(ABC):
    """프로파일링 결과 적재용 추상 베이스 클래스"""
    
    @abstractmethod
    def write_results(self, final_df: pd.DataFrame, file_stats: list[dict]) -> bool:
        pass


class FileOutputWriter(BaseOutputWriter):
    """기존 로컬 파일 시스템(.csv) 출력 적재 클래스"""
    
    def __init__(self, format_file_path=FORMAT_FILE, stats_file_path=STATS_FILE):
        self.format_file_path = Path(format_file_path)
        self.stats_file_path = Path(stats_file_path)
        self.cols_spec = [
            'FilePath', 'FileName', 'ColumnName', 'MasterType', 'PK', 'DataType', 'OracleType', 'DetailDataType',
            'LenCnt', 'LenMin', 'LenMax', 'LenAvg', 'LenMode', 'RecordCnt', 'SampleRows',
            'ValueCnt', 'NullCnt', 'Null(%)', 'UniqueCnt', 'Unique(%)', 'FormatCnt',
            'Format', 'FormatValue', 'Format(%)', 'Format2nd', 'Format2ndValue', 'Format2nd(%)',
            'Format3rd', 'Format3rdValue', 'Format3rd(%)', 'FormatTop10', 'FormatTopRate', 'MinString', 'MaxString',
            'ModeString', 'MedianString', 'ModeCnt', 'Mode(%)', 'FormatMin', 'FormatMax',
            'FormatMode', 'FormatMedian', 'Format2ndMin', 'Format2ndMax', 'Format2ndMode',
            'Format2ndMedian', 'Format3rdMin', 'Format3rdMax', 'Format3rdMode', 'Format3rdMedian'
        ]

    def write_results(self, final_df: pd.DataFrame, file_stats: list[dict]) -> bool:
        try:
            self.format_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 컬럼 스펙 순서 보정 정렬
            ordered = [c for c in self.cols_spec if c in final_df.columns]
            ordered += [c for c in final_df.columns if c not in ordered]
            
            # 1. 컬럼별 분석 결과 스토리지 저장
            final_df[ordered].to_csv(self.format_file_path, index=False, encoding='utf-8-sig')
            print(f"[Writer] 수행 상세 결과 파일 저장 완료: {self.format_file_path}")

            # 2. 파일 통계 결과 스토리지 저장
            if file_stats:
                file_stats_df = pd.DataFrame(file_stats)
                file_stats_df.to_csv(self.stats_file_path, index=False, encoding='utf-8-sig')
                print(f"[Writer] 수행 마스터 통계 파일 저장 완료: {self.stats_file_path} ({len(file_stats_df)}행)")
            return True
        except Exception as e:
            print(f"[Writer] 파일 스토리지 적재 실패: {e}")
            print(traceback.format_exc())
            return False


class DatabaseOutputWriter(BaseOutputWriter):
    """[확장 예시] 향후 RDBMS 품질 시스템 테이블에 직접 Direct 적재하기 위한 클래스"""
    def __init__(self, connection_string=None):
        self.connection_string = connection_string

    def write_results(self, final_df: pd.DataFrame, file_stats: list[dict]) -> bool:
        # TODO: final_df.to_sql('TB_DQ_COLUMN_RESULT', con=engine, if_exists='append') 구현부
        print("[Writer] 데이터베이스 결과 적재 가동 예정")
        return True


#=======================================================================
# [CONTROLLER] 오케스트레이션 파이프라인 제어 관리자
#=======================================================================

class DataSenseProfileController:
    """정의된 InputReader, Engine, OutputWriter 인스턴스를 주입받아 파이프라인을 운영하는 컨트롤러"""
    
    def __init__(self, reader: BaseInputReader, engine: MasterCodeFormatEngine, writer: BaseOutputWriter):
        self.reader = reader
        self.engine = engine
        self.writer = writer

    def execute_pipeline(self, source_list: list[dict]) -> bool:
        if not source_list:
            print("[Controller] 처리할 타겟 리스트가 존재하지 않습니다.")
            return False

        flat_cols = []
        flat_file_stats = []

        # 메타 리스트 루프 수행
        for item in source_list:
            try:
                # 1. 데이터 입력 계층 호출 (타겟 리스트 세분화 분할 받아옴)
                targets = self.reader.get_targets(item)
                
                for target_info in targets:
                    try:
                        # 2. 데이터 세그먼트/샘플 추출 및 통계 수집
                        sample_df, stats = self.reader.read_data_sample(target_info, self.engine.sample_rows)
                        if sample_df.empty:
                            continue
                            
                        if stats:
                            flat_file_stats.append(stats)
                            target_info['total_rows'] = stats.get('RecordCnt', len(sample_df))

                        # 3. 비즈니스 로직 프로세싱 엔진 구동
                        col_results = self.engine.profile_dataframe(sample_df, target_info)
                        flat_cols.extend(col_results)
                        
                    except Exception as e:
                        print(f"[Controller] 소스 타겟 단위 처리 실패: {target_info}, 오류: {e}")
                        continue
            except Exception as e:
                print(f"[Controller] 메타 태스크 그룹 처리 중 치명적 에러: {item}, 오류: {e}")
                continue

        if not flat_cols:
            print("[Controller] 프로파일링 연산 결과 데이터셋이 생성되지 않았습니다.")
            return False

        # DataFrame 가공 및 품질 스코어 보정 연산
        final_df = pd.DataFrame(flat_cols)
        try:
            final_df = add_dq_scores(final_df)
        except Exception as e:
            print(f"[Controller] DQ 스코어 마이그레이션 예외 발생: {e}")

        # 4. 결과 저장 계층 호출
        return self.writer.write_results(final_df, flat_file_stats)


#-----------------------------------------------------------------------
# 메타 데이터 밸리데이터 및 로더
#-----------------------------------------------------------------------
def load_codemapping_validate() -> list[dict]:
    try:    
        print(f"META_PATH: {META_PATH}")
        source_list = pd.read_csv(META_PATH)
        required_columns = ['execution_flag', 'type', 'source', 'extension']
        for col in required_columns:
            if col not in source_list.columns:
                print(f"[Meta] 파일 구조 오류 : {col} 컬럼 누락")
                return []
        
        filtered = source_list[source_list['execution_flag'] == 'Y']
        if filtered.empty:
            print("[Meta] execution_flag 가 'Y'인 타겟이 존재하지 않습니다.")
            return []

        print(f"[Meta] 활성화된 작업 폴더/소스 수: {len(filtered)} 개")
        return filtered.to_dict(orient='records')
    except Exception as e:
        print(f"[Meta] 메타데이터 로드 실패: {e}")
        return []

#-----------------------------------------------------------------------
# 시스템 진입점 Main
#-----------------------------------------------------------------------
def main():
    start_time = time.time()
    print("=" * 60)
    print("DataSense Architecture 3.0 Pipeline Engine Core Start")
    print("=" * 60)
    
    source_list = load_codemapping_validate()
    if not source_list:
        return None
        
    #-------------------------------------------------------------------
    # [의존성 주입(Dependency Injection) 존]
    # 플러그인 교체하듯이 Reader와 Writer를 DB 인터페이스 클래스로 교체 가능합니다.
    #-------------------------------------------------------------------
    reader_plugin = FileInputReader(large_file_threshold_mb=1000, chunk_size=100000)
    engine_plugin = MasterCodeFormatEngine(sample_rows=10000)
    writer_plugin = FileOutputWriter()
    
    # 예시: 향후 DB로 변경 시 하단 주석만 해제하면 됨
    # reader_plugin = DatabaseInputReader(connection_string="oracle+cx_oracle://...")
    # writer_plugin = DatabaseOutputWriter(connection_string="postgresql://...")

    # 파이프라인 조립 후 컨트롤러 가동
    pipeline_controller = DataSenseProfileController(
        reader=reader_plugin,
        engine=engine_plugin,
        writer=writer_plugin
    )
    
    success = pipeline_controller.execute_pipeline(source_list)
    
    print("=" * 60)
    print(f"종료 상태: {'성공' if success else '실패'} | 총 소요시간: {time.time() - start_time:.2f}초")
    print("=" * 60)

if __name__ == "__main__":
    main()

# SOLID 원칙 중 '단일 책임 원칙(SRP)'과 '개방-폐쇄 원칙(OCP)' 극대화

# 과거: 한 개의 대형 클래스(MasterCodeFormatEngine) 내부에서 경로를 검증하고, CSV 인코딩을 트라이하고, 
# Pandas 샘플링을 한 뒤 연산 처리를 하고 직접 로컬 파일로 저장하는 고결합 상태였습니다.

# 현재: 입력은 Reader가, 저장은 Writer가 전담합니다. 
# 데이터 처리를 수행하는 Engine은 들어오는 입력 소스가 파일 시스템인지 클라우드 DB인지 알 필요가 없으며, 
# 오직 pd.DataFrame 연산에만 엄격하게 집중하게 되어 소프트웨어 안정성이 대폭 향상되었습니다.

# Database 연동 및 마이그레이션 확장성 보장

# 프로젝트 요구사항에 맞춰 향후 Oracle 환경이나 PostgreSQL 등 클라이언트 환경 인프라가 변동되더라도 
# 하단의 주석 처리된 주입 부분(DatabaseInputReader, DatabaseOutputWriter) 클래스의 추상 메서드 바디만 구현해 채워 넣으면, 
# 중앙 연산 엔진 코드 수정률 0% 상태로 시스템 DB 전환이 즉시 가능합니다.