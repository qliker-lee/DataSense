# -*- coding: utf-8 -*-
"""
DataSense DQ Profiling System 
Qliker, 2026.01.02 Version 2.0 
"""

import os
import re
import sys
import yaml
import time
import json
import traceback
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from multiprocessing import Pool, cpu_count
from collections import Counter

#---------------------------------------------------------------
# Path & Directory 설정
#---------------------------------------------------------------

if getattr(sys, 'frozen', False):  # A. 실행파일(.exe) 상태일 때: .exe 파일이 있는 위치가 루트입니다.
    ROOT_PATH = Path(sys.executable).parent
else:  # B. 소스코드(.py) 상태일 때: 현재 파일(util/..)의 상위 폴더가 루트입니다.   
    ROOT_PATH = Path(__file__).resolve().parents[1]

if str(ROOT_PATH) not in sys.path: # # 시스템 경로에 루트 추가 (어디서 실행해도 모듈을 찾을 수 있게 함)
    sys.path.insert(0, str(ROOT_PATH))

# ---------------------------------------------------------------
# [2. 모듈 Import] 어떤 환경에서도 에러 없이 불러오도록 예외 처리
# ---------------------------------------------------------------
try:
    # 정석적인 패키지 호출 방식 시도
    from util.dq_columnprofiler import ColumnProfiler, Get_Oracle_Type, Determine_Detail_Type, add_dq_scores
except ImportError:
    # 로컬에서 직접 실행할 때(같은 폴더 내 참조) 방식 시도
    from dq_columnprofiler import ColumnProfiler, Get_Oracle_Type, Determine_Detail_Type, add_dq_scores

META_PATH = ROOT_PATH / 'DS_Meta' / 'CodeList_Meta.csv'
YAML_PATH = ROOT_PATH / 'DS_Meta' / 'DS_Master.yaml'
OUTPUT_DIR = ROOT_PATH / 'DS_Output'
FORMAT_FILE = OUTPUT_DIR / 'FileFormat.csv'
STATS_FILE = OUTPUT_DIR / 'FileStats.csv'
SAMPLE_ROWS = 10000
FORMAT_MAX_VALUE = 10000

#---------------------------------------------------------------
# MasterCodeFormatEngine Class
#---------------------------------------------------------------
class MasterCodeFormatEngine:
    def __init__(self, chunk_size=100000, large_file_threshold_mb=500):
        """
        Args:
            chunk_size: 청크 단위 처리 시 한 번에 읽을 행 수 (기본값: 100000)
            large_file_threshold_mb: 대용량 파일 판단 기준 (MB, 기본값: 500MB)
                                    작은 파일은 청크 처리하지 않아 더 빠름
        """
        self.output_path = OUTPUT_DIR
        self.SAMPLE_ROWS = 10000
        self.chunk_size = chunk_size
        self.large_file_threshold_mb = large_file_threshold_mb

    def _get_file_size_mb(self, file_path):
        """파일 크기를 MB 단위로 반환"""
        try:
            size_bytes = os.path.getsize(file_path)
            return size_bytes / (1024 * 1024)
        except Exception:
            return 0
    
    def _is_large_file(self, file_path):
        """대용량 파일 여부 판단 (최적화: 작은 파일은 빠르게 제외)"""
        try:
            # 파일 크기 체크를 최적화: 작은 파일은 즉시 False 반환
            size_bytes = os.path.getsize(file_path)
            size_mb = size_bytes / (1024 * 1024)
            return size_mb > self.large_file_threshold_mb
        except Exception:
            return False

    def load_source_file(self, file_path, ext) -> pd.DataFrame:
        """ 소스 파일 읽기 (작은 파일용) """
        # ext . 이 있으면 제거하고, 소문자로 변환하여 extension 변수에 저장, source 는 변환하지 않음 
        extension = str(ext.lower().strip('.'))
        file_ext = str(os.path.splitext(file_path)[1]).lower().strip('.')

        encoding_list = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']

        # extension 이 all 이나, 지정하지 않거나 파일의 extension이 동일하면 파일을 읽어서 처리함. 
        if file_ext == extension or extension == '' or extension == 'all':
            try:
                if file_ext == 'csv':
                    for encoding in encoding_list:
                        try:
                            df = pd.read_csv(file_path, dtype=str, low_memory=False, encoding=encoding)
                            return df
                        except Exception as e:
                            continue
                    return None
                elif file_ext == 'xlsx':
                    df = pd.read_excel(file_path, dtype=str)
                    return df
                elif file_ext == 'pkl':
                    df = pd.read_pickle(file_path)
                    return df

                return None
            except Exception as e:
                print(f"메타 파일 점검 : 파일 읽기 실패: {file_path}, 오류: {e}")
                return None
    
    def _process_large_file_chunked(self, file_path, ext, m_type='Master', file_no=1):
        """대용량 파일을 청크 단위로 처리 (최적화: 샘플만 수집, 불필요한 복사 제거)"""
        col_results = []
        file_ext = str(os.path.splitext(file_path)[1]).lower().strip('.')
        encoding_list = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']
        
        if file_ext != 'csv':
            # CSV가 아니면 기존 방식 사용
            return self._process_file_normal(file_path, ext, m_type)
        
        # CSV 파일 청크 단위 처리 (최적화: 샘플만 수집)
        sampled_chunks = []
        encoding_used = None
        column_cnt = 0
        
        # 인코딩 확인 및 첫 청크에서 컬럼 정보 얻기 (최적화: 첫 청크 재사용)
        for encoding in encoding_list:
            try:
                test_chunk = pd.read_csv(file_path, nrows=100, dtype=str, encoding=encoding, low_memory=False)
                encoding_used = encoding
                column_cnt = len(test_chunk.columns)
                break
            except Exception:
                continue
        
        if encoding_used is None:
            print(f"메타 파일 점검 : 파일 인코딩 확인 실패: {file_path}")
            return [], []
        
        # 청크 단위로 읽으면서 샘플 수집 (최적화: 필요한 샘플만 수집, .copy() 제거)
        try:
            chunk_reader = pd.read_csv(file_path, chunksize=self.chunk_size, dtype=str, 
                                     encoding=encoding_used, low_memory=False)
            
            accumulated_samples = 0
            total_rows = 0
            for chunk_idx, chunk in enumerate(chunk_reader):
                chunk_rows = len(chunk)
                total_rows += chunk_rows
                
                # 필요한 샘플만 수집 (SAMPLE_ROWS에 도달하면 중단)
                remaining_samples = self.SAMPLE_ROWS - accumulated_samples
                if remaining_samples > 0:
                    chunk_sample_size = min(chunk_rows, remaining_samples)
                    if chunk_sample_size > 0:
                        if chunk_rows <= chunk_sample_size:
                            # 전체 청크가 필요하면 그대로 사용 (복사 제거)
                            sampled_chunks.append(chunk)
                            accumulated_samples += chunk_rows
                        else:
                            # 샘플링만 수행 (복사 제거)
                            sampled_chunks.append(chunk.sample(n=chunk_sample_size, random_state=42))
                            accumulated_samples += chunk_sample_size
                else:
                    # 필요한 샘플을 모두 수집했으면 청크 읽기 중단
                    # pandas chunksize는 전체 파일을 읽어야 하지만, 
                    # 실제로는 샘플 수집 후에는 더 이상 처리할 필요 없음
                    # 하지만 chunksize는 전체를 읽어야 하므로 break는 불가능
                    # 대신 나머지 청크는 빠르게 건너뛰기
                    pass
            
            # 수집된 샘플들을 합쳐서 프로파일링
            actual_sample_size = 0
            if sampled_chunks:
                sample_df = pd.concat(sampled_chunks, ignore_index=True)
                actual_sample_size = len(sample_df)
                
                # 컬럼별 프로파일링
                for col in sample_df.columns:
                    try:
                        res = ColumnProfiler(sample_df, col, actual_sample_size).profile()
                        if res:
                            res.update({
                                'MasterType': m_type,
                                'FileName': os.path.basename(file_path),
                                'FilePath': file_path,
                                'RecordCnt': total_rows  # 전체 레코드 수 사용
                            })
                            col_results.append(res)
                    except Exception as e:
                        print(f"컬럼 프로파일링 실패 (파일: {file_path}, 컬럼: {col}): {e}")
                        continue
        except Exception as e:
            print(f"청크 단위 파일 처리 실패: {file_path}, 오류: {e}")
            return [], []
        
        # SamplingRows와 Sampling(%) 계산
        sampling_pct = round((actual_sample_size / total_rows * 100) if total_rows > 0 else 0, 2)
        
        file_stats = [{
            'FileNo': file_no,
            'FilePath': file_path,
            'FileName': os.path.basename(file_path),
            'MasterType': m_type,
            'RecordCnt': total_rows,
            'ColumnCnt': column_cnt,
            'SamplingRows': actual_sample_size,
            'Sampling(%)': sampling_pct,
            'FileSize': self._get_file_size_mb(file_path),
            'WorkDate': datetime.now().strftime('%Y-%m-%d')
        }]
        
        return col_results, file_stats
    
    def _process_file_normal(self, file_path, ext, m_type='Master', file_no=1):
        """일반 파일 처리 (기존 방식 - 최적화: 불필요한 복사 제거)"""
        col_results, file_stats = [], []
        
        df = self.load_source_file(file_path, ext)
        if df is None:
            return [], []
        
        total_rows = len(df)
        sample_rows = min(total_rows, self.SAMPLE_ROWS)
        # 샘플링이 필요하면 샘플링, 아니면 원본 사용 (복사 제거)
        if total_rows <= self.SAMPLE_ROWS:
            sample_df = df
        else:
            sample_df = df.sample(n=self.SAMPLE_ROWS, random_state=42)
        
        # SamplingRows와 Sampling(%) 계산
        actual_sample_size = len(sample_df)
        sampling_pct = round((actual_sample_size / total_rows * 100) if total_rows > 0 else 0, 2)
        
        file_stats.append({
            'FileNo': file_no,
            'FilePath': file_path,
            'FileName': os.path.basename(file_path),
            'MasterType': m_type,
            'RecordCnt': total_rows,
            'ColumnCnt': len(df.columns),
            'SamplingRows': actual_sample_size,
            'Sampling(%)': sampling_pct,
            'FileSize': self._get_file_size_mb(file_path),
            'WorkDate': datetime.now().strftime('%Y-%m-%d')
        })
        
        # 컬럼별 프로파일링
        for col in sample_df.columns:
            try:
                res = ColumnProfiler(sample_df, col, sample_rows).profile()
                if res:
                    res.update({
                        'MasterType': m_type,
                        'FileName': os.path.basename(file_path),
                        'FilePath': file_path
                    })
                    col_results.append(res)
            except Exception as e:
                print(f"컬럼 프로파일링 실패 (파일: {file_path}, 컬럼: {col}): {e}")
                continue
        
        return col_results, file_stats

    def run_profile(self, m_type, source, ext):
        """ 
        m_type: Master, Reference, Rule 
        source: 파일 경로
        ext: 파일 확장자
        """

        col_results, file_stats = [], []
        try:
            target_files = []
            try:
                if not os.path.exists(source):
                    print(f"메타 파일 점검 : 경로가 존재하지 않습니다: {META_PATH}/{source}")
                    return [], []
                
                if os.path.isdir(source):
                    for f in os.listdir(source):
                        if f.lower().endswith(ext):
                            target_files.append(os.path.join(source, f))
                else:
                    target_files.append(source)
            except Exception as e:
                print(f"메타 파일 점검 : 파일 목록 조회 오류 (경로: {META_PATH}/{source}): {e}")
                return [], []

            if not target_files:
                print(f"메타 파일 점검 : 처리할 파일이 없습니다 (경로: {META_PATH}/ {source}, 확장자: {ext})")
                return [], []

            for file_no, f_path in enumerate(target_files, start=1):
                try:                    
                    # 대용량 파일 여부 확인 (최적화: 파일 크기 체크 최소화)
                    file_size_mb = self._get_file_size_mb(f_path)
                    if file_size_mb > self.large_file_threshold_mb:
                        print(f"대용량 파일 감지 (청크 처리): {os.path.basename(f_path)} ({file_size_mb:.1f}MB)")
                        file_col_results, file_file_stats = self._process_large_file_chunked(f_path, ext, m_type, file_no)
                        col_results.extend(file_col_results)
                        file_stats.extend(file_file_stats)
                    else:
                        # 일반 파일 처리 (기존 방식 - 더 빠름)
                        file_col_results, file_file_stats = self._process_file_normal(f_path, ext, m_type, file_no)
                        col_results.extend(file_col_results)
                        file_stats.extend(file_file_stats)
                        
                except Exception as e:
                    print(f"파일 처리 실패: {f_path}, 오류: {e}")
                    print(traceback.format_exc())
                    continue
                    
        except Exception as e:
            print(f"run_profile 전체 오류: {e}")
        
        return col_results, file_stats

    def Profiling(self, source_list):
        """source_list의 모든 항목에 대해 프로파일링을 수행하고 결과를 저장합니다."""
        try:
            if not source_list:
                print("처리할 파일 목록이 비어있습니다.")
                return False
            
            # 멀티프로세싱 또는 순차 처리로 모든 source 처리
            try:
                with Pool(cpu_count()) as pool:
                    # run_profile을 멀티프로세싱으로 실행하기 위해 래퍼 함수 필요
                    # 현재는 순차 처리로 구현
                    combined = []
                    for item in source_list:
                        col_results, file_stats = self.run_profile(item['type'], item['source'], item['extension'])
                        combined.append((col_results, file_stats))
            except Exception as e:
                print(f"멀티프로세싱 오류: {e}")
                print("순차 처리로 전환")
                combined = []
                for item in source_list:
                    col_results, file_stats = self.run_profile(item['type'], item['source'], item['extension'])
                    combined.append((col_results, file_stats))
            
            # 결과 수집
            flat_cols, flat_file_stats = [], []
            for col_results, file_stats in combined:
                if col_results:
                    flat_cols.extend(col_results)
                if file_stats:
                    flat_file_stats.extend(file_stats)
            
            print(f"총 {len(flat_cols)}개 컬럼 결과 수집 완료")
            
            if not flat_cols:
                print("처리된 컬럼 결과가 없습니다.")
                return False
            
            # DataFrame 변환
            final_df = pd.DataFrame(flat_cols)
            print(f"수행 결과 완료: {len(final_df)}행 x {len(final_df.columns)}열")

            # DQ 점수 추가
            try:
                final_df = add_dq_scores(final_df)
            except Exception as e:
                print(f"DQ 점수 추가 실패 (계속 진행): {e}")
            
            # FileFormat_2.csv 헤더 규격 강제 적용
            cols_spec = [
                'FilePath', 'FileName', 'ColumnName', 'MasterType', 'PK', 'DataType', 'OracleType', 'DetailDataType',
                'LenCnt', 'LenMin', 'LenMax', 'LenAvg', 'LenMode', 'RecordCnt', 'SampleRows',
                'ValueCnt', 'NullCnt', 'Null(%)', 'UniqueCnt', 'Unique(%)', 'FormatCnt',
                'Format', 'FormatValue', 'Format(%)', 'Format2nd', 'Format2ndValue', 'Format2nd(%)',
                'Format3rd', 'Format3rdValue', 'Format3rd(%)', 'MinString', 'MaxString',
                'ModeString', 'MedianString', 'ModeCnt', 'Mode(%)', 'FormatMin', 'FormatMax',
                'FormatMode', 'FormatMedian', 'Format2ndMin', 'Format2ndMax', 'Format2ndMode',
                'Format2ndMedian', 'Format3rdMin', 'Format3rdMax', 'Format3rdMode', 'Format3rdMedian'
            ]
            ordered = [c for c in cols_spec if c in final_df.columns]
            ordered += [c for c in final_df.columns if c not in ordered]
            
            # 결과 저장
            try:
                self.output_path.mkdir(parents=True, exist_ok=True)
                save_path = FORMAT_FILE
                
                final_df[ordered].to_csv(save_path, index=False, encoding='utf-8-sig')
                print(f"수행 결과 저장: {save_path}")

                # flat_file_stats 사용 (누적된 파일 통계 데이터)
                if flat_file_stats:
                    file_stats_df = pd.DataFrame(flat_file_stats)
                    file_stats_df.to_csv(STATS_FILE, index=False, encoding='utf-8-sig')
                    print(f"파일 통계 결과 저장: {STATS_FILE} ({len(file_stats_df)}행)")
                else:
                    print("파일 통계 데이터가 없어 저장하지 않습니다.")
                return True
            except Exception as e:
                print(f"파일 저장 실패: {save_path}, 오류: {e}")
                print(traceback.format_exc())
                return False
                
        except Exception as e:
            print(f"Profiling 오류: {e}")
            print(traceback.format_exc())
            return False

#-----------------------------------------------------------------------
# Load CodeMapping File ( CodeFormat을 수행할 Source Folder Path )
#-----------------------------------------------------------------------
def load_codemapping_validate() -> list[dict]:
        try:    
            print(f"META_PATH: {META_PATH}")
            source_list = pd.read_csv(META_PATH)
            # source_list의 필수 컬럼 점검  ( execution_flag,type, source, extension 존재 여부)
            required_columns = ['execution_flag', 'type', 'source', 'extension']
            for col in required_columns:
                if col not in source_list.columns:
                    print(f"{META_PATH} 파일 구조 점검 : {col} 컬럼이 없습니다.")
                    return []
            
            filtered = source_list[source_list['execution_flag'] == 'Y']
            if filtered.empty:
                print(f"수행할 폴더가 없습니다.")
                return []

            # meta 파일에서 type이 Master, Reference, Rule 인 경우만 수행
            if not filtered['type'].isin(['Master', 'Reference', 'Rule']).all():
                print(f"meta 파일에서 type이 Master, Reference, Rule 이 아닌 경우는 수행하지 않습니다.")
                return []

            print(f"수행할 폴더 수: {len(filtered)} 개 (Master: {len(filtered[filtered['type'] == 'Master'])}, Reference: {len(filtered[filtered['type'] == 'Reference'])}, Rule: {len(filtered[filtered['type'] == 'Rule'])})")
            return filtered.to_dict(orient='records')
        except Exception as e:
            print(f"{META_PATH} 파일 점검 : 메타데터 파일 읽기 실패: {e}")
            return []
#-----------------------------------------------------------------------
# Main
#-----------------------------------------------------------------------
def main():
    """
    DataSense Data Profiling 메인 함수
    """
    start_time = time.time()
    
    try:
        print("=" * 60)
        print("DataSense Data Profiling 시작")
        print("=" * 60)
               
        source_list = load_codemapping_validate()
        if  source_list is None or len(source_list) == 0:
            print(f"메타 파일 점검 : {META_PATH}")
            return None
        
        # MasterCodeFormatEngine 엔진 실행
        # engine = MasterCodeFormatEngine_new()  
        engine = MasterCodeFormatEngine(large_file_threshold_mb=1000)  # 1GB 이상만 청크 처리
        engine.Profiling(source_list)
                    
        end_time = time.time()
        processing_time = end_time - start_time
        print("=" * 60)
        print(f"총 처리 시간: {processing_time:.2f}초")
        print("=" * 60)
        
    except Exception as e:
        print(f"MasterCodeFormat 오류 발생: {e}")
        return None

if __name__ == "__main__":
    # 단독 실행 모드
    result = main()


        