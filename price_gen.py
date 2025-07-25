import pandas as pd
import re

def process_price_list(input_file, output_file):
    """
    고래미 도매단가표를 읽어 Streamlit 앱용 products.csv를 생성합니다.
    - 제품명과 규격을 조합하여 고유한 제품명을 만듭니다.
    - /ea 가격을 standard_price로 사용합니다.
    - 원가(cost_price)는 standard_price의 70%로 임시 생성합니다.
    """
    try:
        # utf-8-sig로 인코딩하여 파일 시작 부분의 BOM 문자 제거
        df = pd.read_csv(input_file, header=None, encoding='utf-8-sig')
    except Exception as e:
        print(f"파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    processed_data = []
    
    for index, row in df.iterrows():
        # 첫 행(헤더)은 건너뛰고, 비어있는 행 건너뛰기
        if index == 0 or row.isnull().all():
            continue

        try:
            # 데이터 추출
            product_name_base = str(row.iloc[1]).strip()
            
            # 제품명이 비어있으면 해당 행 건너뛰기
            if not product_name_base:
                continue

            # 규격 조합 (숫자 + 단위)
            spec_value = str(row.iloc[2]).strip()
            spec_unit = str(row.iloc[3]).strip()
            
            # 80g*4ea 같은 복합 규격 처리
            if '*' in spec_value:
                 # '간장새우비빔장 80g*4ea' 와 같이 기본 이름에 규격이 포함된 경우
                 full_name = product_name_base
            else:
                 full_name = f"{product_name_base} {spec_value}{spec_unit}"

            # /ea 가격 추출 및 정제
            ea_price_raw = str(row.iloc[10]).strip()
            ea_price = int(re.sub(r'[^\d]', '', ea_price_raw))

            # SKU 코드 생성
            sku_code = f"GRM-{len(processed_data) + 1:03d}"

            # 임시 원가 계산 (도매가의 70%)
            cost_price = int(ea_price * 0.7)

            processed_data.append({
                "sku_code": sku_code,
                "product_name": full_name,
                "cost_price": cost_price,
                "standard_price": ea_price
            })

        except (ValueError, IndexError) as e:
            print(f"{index+1}번째 행 처리 중 오류 발생 (건너뜁니다): {row.values}, 오류: {e}")
            continue
            
    # 데이터프레임 생성 및 CSV로 저장
    output_df = pd.DataFrame(processed_data)
    output_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"성공적으로 '{output_file}' 파일을 생성했습니다. 총 {len(output_df)}개의 제품이 처리되었습니다.")
    print("⚠️ 중요: 생성된 파일의 cost_price는 임시값이므로, 실제 원가로 수정해주세요.")


# 스크립트 실행 (예시)
# process_price_list('2025.07 도매단가표 4.csv', 'products.csv')
