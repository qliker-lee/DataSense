# -*- coding: utf-8 -*-
"""
2025.12.17 Qliker
Streamlit import 전에 로깅 필터 설정 (경고 억제)
별도 파일로 분리하여 재사용 가능하도록 구성
"""

import logging
import warnings
import sys
import os


def setup_streamlit_warnings():
    """
    Streamlit 관련 경고 메시지를 억제합니다.
    Streamlit import 전에 호출해야 합니다.
    """
    # -------------------------------------------------------------------
    # 파이썬 컴파일시 Warning 억제
    # -------------------------------------------------------------------
    warnings.filterwarnings("ignore")

    # 환경 변수 설정 (Streamlit 최신 버전 대응)
    os.environ['STREAMLIT_LOGGER_LEVEL'] = 'ERROR'
    os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'

    # warnings 필터로도 억제 (더 포괄적으로)
    warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")
    warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="streamlit")
    warnings.filterwarnings("ignore", category=UserWarning)

    # 커스텀 필터 클래스 정의
    class ScriptRunContextFilter(logging.Filter):
        def filter(self, record):
            try:
                message = record.getMessage() if hasattr(record, 'getMessage') else str(record.msg)
            except:
                message = str(record.msg) if hasattr(record, 'msg') else str(record)
            
            # ScriptRunContext 관련 메시지 모두 필터링
            if 'ScriptRunContext' in message or 'missing ScriptRunContext' in message:
                return False
            return True

    # 루트 로거에 필터 추가 (Streamlit import 전)
    script_run_context_filter = ScriptRunContextFilter()
    logging.root.addFilter(script_run_context_filter)
    logging.root.setLevel(logging.ERROR)

    # 모든 기존 핸들러에 필터 추가
    for handler in logging.root.handlers:
        if hasattr(handler, 'addFilter'):
            handler.addFilter(script_run_context_filter)

    # sys.stderr에 직접 출력되는 경고도 억제하기 위한 래퍼
    class FilteredStderr:
        def __init__(self, original_stderr):
            self.original_stderr = original_stderr
        
        def write(self, message):
            msg_str = str(message)
            # ScriptRunContext 관련 메시지 필터링
            if 'ScriptRunContext' not in msg_str and 'missing ScriptRunContext' not in msg_str:
                self.original_stderr.write(message)
        
        def flush(self):
            self.original_stderr.flush()
        
        def __getattr__(self, name):
            return getattr(self.original_stderr, name)

    # stderr 필터링 활성화 (Streamlit 최신 버전 대응)
    sys.stderr = FilteredStderr(sys.stderr)

    # Streamlit import 후 로거 재설정 (경고 억제)
    # 모든 Streamlit 관련 로거의 경고 레벨을 ERROR로 설정
    streamlit_loggers = [
        'streamlit', 
        'streamlit.runtime', 
        'streamlit.runtime.scriptrunner', 
        'streamlit.runtime.scriptrunner.script_run_context',
        'streamlit.runtime.scriptrunner_utils',
        'streamlit.runtime.scriptrunner_utils.script_run_context',
        'streamlit.runtime.caching',
        'streamlit.runtime.caching.cache_utils',
        'streamlit.runtime.state',
        'streamlit.runtime.legacy_caching',
    ]

    for logger_name in streamlit_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.ERROR)
        logger.addFilter(script_run_context_filter)
        # 기존 핸들러에 필터 추가
        for handler in logger.handlers:
            handler.addFilter(script_run_context_filter)
            handler.setLevel(logging.ERROR)

    # 루트 로거의 모든 핸들러에 필터 추가 및 레벨 설정
    for handler in logging.root.handlers:
        if hasattr(handler, 'addFilter'):
            handler.addFilter(script_run_context_filter)
        if hasattr(handler, 'setLevel'):
            handler.setLevel(logging.ERROR)

