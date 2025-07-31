import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
import time

# --- 페이지 설정 ---
st.set_page_config(page_title="goremi 가격결정 시스템", page_icon="🐟", layout="wide")

# --- (설정) DB 정보 ---
PRODUCT_DB_NAME = "Goremi Products DB"
CLIENT_DB_NAME = "Goremi Clients DB"
PRICE_DB_NAME = "Goremi Price DB"

# --- 구글 시트 연동 및 데이터 로딩 ---
@st.cache_data(ttl=300)
def load_and_prep_data():
    client = get_gsheet_client()
    # 제품 DB 로드
    products_ws = client.open(PRODUCT_DB_NAME).worksheet("products")
    products_df = pd.DataFrame(products_ws.get_all_records())
    products_df['unique_name'] = (
        products_df['product_name_kr'].astype(str).str.strip() + " (" +
        products_df['weight'].astype(str).str.strip() +
        products_df['ea_unit'].astype(str).str.strip() + ")"
    )
    for col in ['stand_cost', 'stand_price_ea', 'box_ea']:
        products_df[col] = products_df[col].astype(str).str.replace(',', '')
        products_df[col] = pd.to_numeric(products_df[col], errors='coerce')
    products_df = products_df.fillna(0).sort_values(by='unique_name').reset_index(drop=True)

    # 거래처 DB 로드
    clients_ws = client.open(CLIENT_DB_NAME).worksheet("confirmed_clients")
    clients_df = pd.DataFrame(clients_ws.get_all_records())
    numeric_client_cols = [col for col in clients_df.columns if col not in ['customer_name', 'channel_type']]
    for col in numeric_client_cols:
        clients_df[col] = pd.to_numeric(clients_df[col], errors='coerce')
    clients_df = clients_df.fillna(0)

    # 가격 DB 로드
    prices_ws = client.open(PRICE_DB_NAME).worksheet("confirmed_prices")
    prices_df = pd.DataFrame(prices_ws.get_all_records())
    return products_df, clients_df, prices_df

def get_gsheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

# --- 메인 앱 실행 ---
try:
    products_df, customers_df, prices_df = load_and_prep_data()
except Exception as e:
    st.error(f"데이터베이스 로딩 중 오류가 발생했습니다: {e}")
    st.stop()

if not prices_df.empty and 'unique_name' not in prices_df.columns:
    st.error("🚨 데이터베이스 구조 업데이트 필요!")
    st.warning("`Goremi Price DB`의 `confirmed_prices` 시트를 삭제하고, 앱에서 다시 설정해주세요.")
    st.stop()

# --- UI 탭 정의 ---
st.title("🐟 goremi 가격 관리 시스템")
tab_simulate, tab_matrix, tab_db_view = st.tabs(["가격 시뮬레이션", "거래처별 품목 관리", "DB 원본 조회"])

# ==================== 가격 시뮬레이션 탭 ====================
with tab_simulate:
    st.header("거래처별 품목 가격 일괄 시뮬레이션")
    if customers_df.empty:
        st.warning("등록된 거래처가 없습니다.")
    else:
        selected_customer_sim = st.selectbox("가격을 조정할 거래처를 선택하세요", customers_df['customer_name'].unique(), key="sim_customer")

        active_prices_df = pd.DataFrame()
        if not prices_df.empty:
            active_prices_df = prices_df[prices_df['customer_name'] == selected_customer_sim].copy()

        if active_prices_df.empty:
            st.warning(f"'{selected_customer_sim}'이(가) 취급하는 품목이 없습니다. '거래처별 품목 관리' 탭에서 먼저 설정해주세요.")
        else:
            prices_to_merge = active_prices_df[['unique_name', 'supply_price']]
            # stand_price_ea도 함께 가져오도록 수정
            products_to_merge = products_df[['unique_name', 'stand_cost', 'stand_price_ea', 'box_ea']]
            sim_df = pd.merge(prices_to_merge, products_to_merge, on='unique_name', how='inner')

            original_item_count = len(active_prices_df)
            merged_item_count = len(sim_df)
            if original_item_count > merged_item_count:
                st.error("데이터 불일치 경고!")
                merged_items = set(sim_df['unique_name'])
                all_items = set(active_prices_df['unique_name'])
                missing_items = all_items - merged_items
                st.warning("아래 품목은 '제품 마스터 DB'에 없어 시뮬레이션에서 제외되었습니다.")
                st.dataframe({"제외된 품목": list(missing_items)})

            if sim_df.empty:
                st.warning("시뮬레이션할 유효한 품목이 없습니다.")
            else:
                st.markdown("---")
                st.subheader(f"Step 1: '{selected_customer_sim}'의 공급 단가 수정")
                sim_df['supply_price'] = pd.to_numeric(sim_df['supply_price'], errors='coerce').fillna(0)
                edited_df = st.data_editor(
                    sim_df[['unique_name', 'stand_cost', 'supply_price']],
                    column_config={
                        "unique_name": st.column_config.TextColumn("품목명", disabled=True),
                        "stand_cost": st.column_config.NumberColumn("제품 원가", format="%d원", disabled=True),
                        "supply_price": st.column_config.NumberColumn("최종 공급 단가", format="%d원", required=True),
                    },
                    hide_index=True, use_container_width=True, key="price_editor"
                )

                st.markdown("---")
                st.subheader("Step 2: 실시간 손익 분석 결과 확인")
                customer_info = customers_df[customers_df['customer_name'] == selected_customer_sim].iloc[0]
                numeric_cols = [col for col in customer_info.index if col not in ['customer_name', 'channel_type']]
                conditions = {col: float(customer_info.get(col, 0)) for col in numeric_cols}
                total_deduction_rate = sum(conditions.values()) / 100
                
                # =============================== 여기가 핵심 수정 부분 (Step 2 분석) ===============================
                # 1. products_df에서 필요한 전체 컬럼('unique_name', 'stand_price_ea', 'box_ea')을 가져와서 merge
                analysis_df = pd.merge(edited_df, products_df[['unique_name', 'stand_price_ea', 'box_ea']], on='unique_name', how='left')
                
                # 2. 분석에 필요한 컬럼들 계산
                analysis_df['supply_price'] = pd.to_numeric(analysis_df['supply_price'], errors='coerce').fillna(0)
                analysis_df['stand_price_ea'] = pd.to_numeric(analysis_df['stand_price_ea'], errors='coerce').fillna(0)
                analysis_df['실정산액'] = analysis_df['supply_price'] * (1 - total_deduction_rate)
                
                # 3. (신규) '기준가 대비 차액' 컬럼 추가
                analysis_df['기준가 대비 차액'] = analysis_df['실정산액'] - analysis_df['stand_price_ea']
                
                analysis_df['개당 이익'] = analysis_df['실정산액'] - analysis_df['stand_cost']
                analysis_df['마진율 (%)'] = analysis_df.apply(lambda row: (row['개당 이익'] / row['실정산액'] * 100) if row['실정산액'] > 0 else 0, axis=1)
                analysis_df['박스당 이익'] = analysis_df['개당 이익'] * analysis_df['box_ea']
                
                # 4. 화면에 표시할 컬럼 순서 재정의 및 컬럼 설정
                display_cols = [
                    'unique_name', 'stand_price_ea', 'supply_price', '실정산액', '기준가 대비 차액',
                    '마진율 (%)', '개당 이익', '박스당 이익'
                ]
                st.dataframe(
                    analysis_df[display_cols],
                    column_config={
                        "unique_name": "품목명",
                        "stand_price_ea": st.column_config.NumberColumn("기준 도매가", format="%d원"),
                        "supply_price": st.column_config.NumberColumn("공급 단가", format="%d원"),
                        "실정산액": st.column_config.NumberColumn("실정산액", format="%d원"),
                        "기준가 대비 차액": st.column_config.NumberColumn("기준가 대비 차액", format="%+d원"),
                        "마진율 (%)": st.column_config.NumberColumn("마진율", format="%.1f%%"),
                        "개당 이익": st.column_config.NumberColumn("개당 이익", format="%d원"),
                        "박스당 이익": st.column_config.NumberColumn("박스당 이익", format="%d원"),
                    },
                    hide_index=True, use_container_width=True
                )
                # =================================================================================================

                st.markdown("---")
                if st.button(f"✅ '{selected_customer_sim}'의 모든 가격 변경사항 DB에 저장", key="save_all_sim", type="primary"):
                    with st.spinner("DB에 가격 정보를 업데이트합니다..."):
                        # =============================== 여기가 핵심 수정 부분 (시뮬레이션 저장) ===============================
                        # 1. DB를 다시 로드하여 최신 상태 확보
                        _, _, current_total_prices = load_and_prep_data()

                        # 2. 다른 거래처 데이터는 그대로 분리
                        other_customer_prices = current_total_prices[current_total_prices['customer_name'] != selected_customer_sim].copy()

                        # 3. 현재 화면에서 수정한 데이터(edited_df)를 기반으로 저장할 데이터 '재구성'
                        #    저장 시에는 분석에만 사용된 '기준 도매가', '기준가 대비 차액' 등은 제외하고 필요한 컬럼만 저장합니다.
                        updated_data_to_save = analysis_df.rename(columns={
                            '마진율 (%)': 'margin_rate',
                            '개당 이익': 'profit_per_ea',
                            '박스당 이익': 'profit_per_box'
                        })
                        updated_data_to_save['customer_name'] = selected_customer_sim
                        updated_data_to_save['confirm_date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        # 저장할 최종 컬럼만 선택 (분석용 컬럼 제외)
                        save_columns = [
                            'confirm_date', 'unique_name', 'customer_name', 'stand_cost', 
                            'supply_price', 'margin_rate', 'profit_per_ea', 'profit_per_box'
                        ]
                        # 혹시 모를 누락에 대비하여 DB에 있는 모든 컬럼을 포함시키도록 처리
                        if not current_total_prices.empty:
                            save_columns = list(current_total_prices.columns)
                        
                        # 최종 저장 DF에서 필요한 컬럼만 남김
                        final_save_df = updated_data_to_save[[col for col in save_columns if col in updated_data_to_save.columns]]


                        # 4. 다른 거래처 데이터와 재구성된 현재 거래처 데이터를 합침
                        final_prices_df = pd.concat([other_customer_prices, final_save_df], ignore_index=True)

                        # 5. DB에 덮어쓰기
                        price_sheet = get_gsheet_client().open(PRICE_DB_NAME).worksheet("confirmed_prices")
                        set_with_dataframe(price_sheet, final_prices_df, allow_formulas=False)

                        st.success(f"'{selected_customer_sim}'의 가격 정보가 성공적으로 업데이트되었습니다.")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()

# ==================== 거래처별 품목 관리 탭 ====================
with tab_matrix:
    st.header("거래처별 취급 품목 설정")
    manage_customer = st.selectbox("관리할 거래처를 선택하세요", customers_df['customer_name'].unique(), key="manage_customer")
    if manage_customer:
        st.markdown(f"#### 📄 **{manage_customer}** 의 취급 품목 목록")
        active_products_set = set()
        if not prices_df.empty and 'unique_name' in prices_df.columns:
            active_products_set = set(prices_df[prices_df['customer_name'] == manage_customer]['unique_name'])

        checkbox_states = {}
        for _, product in products_df.iterrows():
            is_checked = product['unique_name'] in active_products_set
            checkbox_states[product['unique_name']] = st.checkbox(
                product['unique_name'], value=is_checked, key=f"check_{manage_customer}_{product['unique_name']}"
            )

        if st.button(f"✅ **{manage_customer}** 의 품목 정보 저장", use_container_width=True, type="primary"):
            with st.spinner("DB를 업데이트하는 중입니다..."):
                # =============================== 여기가 핵심 수정 부분 (품목 관리 저장) ===============================
                # 1. DB를 다시 로드하여 최신 상태 확보
                _, _, current_prices = load_and_prep_data()

                # 2. 다른 거래처 데이터는 그대로 분리
                other_customer_prices = current_prices[current_prices['customer_name'] != manage_customer].copy()

                # 3. 현재 체크박스 상태를 기반으로 이 거래처의 데이터를 '재구성'
                newly_active_products = {name for name, checked in checkbox_states.items() if checked}

                # 재구성할 데이터를 담을 리스트
                reconstructed_entries = []
                for unique_name in newly_active_products:
                    # 기존에 데이터가 있었는지 확인
                    existing_entry = current_prices[
                        (current_prices['customer_name'] == manage_customer) &
                        (current_prices['unique_name'] == unique_name)
                    ]

                    if not existing_entry.empty:
                        # 기존 데이터가 있으면 그대로 사용
                        reconstructed_entries.append(existing_entry.iloc[0].to_dict())
                    else:
                        # 기존 데이터가 없으면 새로 생성
                        product_info = products_df.loc[products_df['unique_name'] == unique_name].iloc[0]
                        reconstructed_entries.append({
                            "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"), "unique_name": unique_name, "customer_name": manage_customer,
                            "stand_cost": product_info['stand_cost'], "supply_price": product_info['stand_price_ea'],
                            "margin_rate": 0, "profit_per_ea": 0, "profit_per_box": 0
                        })

                # 4. 다른 거래처 데이터와 재구성된 현재 거래처 데이터를 합침
                reconstructed_df = pd.DataFrame(reconstructed_entries)
                final_df = pd.concat([other_customer_prices, reconstructed_df], ignore_index=True)

                # 5. DB에 덮어쓰기
                price_sheet = get_gsheet_client().open(PRICE_DB_NAME).worksheet("confirmed_prices")
                set_with_dataframe(price_sheet, final_df, allow_formulas=False)

                st.success(f"'{manage_customer}'의 취급 품목 정보가 DB에 성공적으로 업데이트되었습니다!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

# ==================== DB 원본 조회 탭 ====================
with tab_db_view:
    st.header("제품 마스터 DB")
    st.dataframe(products_df)
    st.header("거래처 목록 DB")
    st.dataframe(customers_df)
    st.header("확정 가격 DB (취급 품목 목록)")
    st.dataframe(prices_df)
