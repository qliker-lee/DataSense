# DataSense 기능 설명서

DataSense는 데이터 품질 분석, 데이터 프로파일링, 코드 관계 분석, 개인정보 분석 등을 수행하는 통합 데이터 분석 플랫폼입니다.

## 주요 기능

### 1. Data Profiling
- 데이터 타입 분석
- Null/Unique 비율 분석
- Length 분석
- Pattern 분석
- Top10 빈도 분석

### 2. Data Quality Analyzer
- DQ Score 계산
- 중복/Null 분석
- 데이터 품질 위험 탐지

### 3. Data Type & Rule Analyzer
- Rule 기반 데이터 의미 분석
- 이메일/전화번호/날짜 자동 탐지

### 4. Code Relationship Analyzer
- 컬럼 간 관계 탐지
- 코드 매핑 분석

### 5. Data Consistency Analysis
- 시스템 간 데이터 정합성 분석
- OracleType/Format 비교

### 6. Code Change Analysis
- 코드 변동 이력 분석
- Before/After 비교

### 7. Character Analysis
- 깨진 한글 탐지
- Unicode 분석
- 한자/제어문자 탐지

### 8. PII Analyzer
- 개인정보 컬럼 자동 탐지
- 컬럼명 및 값 기반 분석

## 기술 스택
- Python
- Streamlit
- pandas
- plotly
- scikit-learn
