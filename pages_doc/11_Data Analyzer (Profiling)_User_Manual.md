# DataSense 사용설명서

## 실행 방법

### 패키지 설치
```bash
pip install streamlit pandas numpy plotly scikit-learn
```

### 프로그램 실행
```bash
streamlit run "11_Data Analyzer (Profiling).py"
```

## 사용 방법

### 1. 비밀번호 입력
화면 좌측 비밀번호 입력창에 비밀번호를 입력합니다.

### 2. Data Analyzer 실행
'실행' 버튼을 클릭하면 다음 순서로 분석이 수행됩니다.
1. Data Quality Analyzer
2. Data Type & Rule Analyzer
3. Code Relationship Analyzer

### 3. KPI Dashboard 확인
- 전체 파일 수
- 전체 레코드 수
- 전체 컬럼 수
- 전체 파일 크기

### 4. 파일 선택
Select 체크박스로 상세 분석할 파일을 선택합니다.

### 5. 상세 분석 탭
- Data Profile
- Value Info
- Value Type Info
- Top10 Info
- Length Info
- Character Info
- DQ Score Info

## 결과 파일
결과는 DS_Output 폴더에 저장됩니다.

### 생성 파일
- FileFormat.csv
- FileAttribute.csv
- RuleDataType.csv
- CodeMapping.csv
- PII_Columns.csv
