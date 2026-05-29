import pandas as pd
import datetime
import os
import sys
from pathlib import Path
from glob import glob

# [1. 경로 설정]
if getattr(sys, 'frozen', False):
    ROOT_PATH = Path(sys.executable).parent
else:
    ROOT_PATH = Path(__file__).resolve().parents[1]

INPUT_PATH = ROOT_PATH / 'DS_Input' / 'Internal'
OUTPUT_PATH = INPUT_PATH / 'output'

def create_unique_timestamp_files():
    # 출력 폴더 생성
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    
    # CSV 파일 목록 가져오기
    file_list = glob(str(INPUT_PATH / "*.csv"))
    
    if not file_list:
        print("❌ 처리할 CSV 파일이 INPUT 폴더에 없습니다.")
        return

    print(f"🚀 총 {len(file_list)}개의 파일 처리를 시작합니다. (30초 간격 생성)")

    # 시작 기준 시간 설정
    base_time = datetime.datetime.now().replace(microsecond=0)

    for file_path in file_list:
        file_name = os.path.basename(file_path)
        try:
            # 인코딩 대응
            try:
                df = pd.read_csv(file_path, encoding='utf-8-sig')
            except:
                df = pd.read_csv(file_path, encoding='cp949')

            # [2. 기존 GEN_TIMESTAMP 컬럼 제거]
            if 'GEN_TIMESTAMP' in df.columns:
                df = df.drop(columns=['GEN_TIMESTAMP'])

            # [3. 새 TimeStamp 컬럼 생성]
            # 행 번호(i)에 30초를 곱하여 시간 간격을 벌립니다.
            df['TimeStamp'] = [
                (base_time + datetime.timedelta(seconds=i * 30)).strftime('%Y-%m-%d %H:%M:%S')
                for i in range(len(df))
            ]

            # [4. 파일 저장]
            save_path = OUTPUT_PATH / file_name
            df.to_csv(save_path, index=False, encoding='utf-8-sig')
            
            # 다음 파일의 시작 시간은 현재 파일의 마지막 시간 다음부터 시작되도록 설정 (옵션)
            # base_time = base_time + datetime.timedelta(seconds=len(df) * 30)
            
            print(f"✅ 완료: {file_name} (행 수: {len(df)}) -> 'TimeStamp' (30s interval)")

        except Exception as e:
            print(f"❌ 오류 발생 ({file_name}): {e}")

    print(f"\n✨ 모든 작업이 완료되었습니다!")
    print(f"📂 저장 경로: {OUTPUT_PATH}")

if __name__ == "__main__":
    create_unique_timestamp_files()