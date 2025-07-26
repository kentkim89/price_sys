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
def get_gsheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_and_prep_data():
    client = get_gsheet_client()

    # 제품 DB 로드 및 고유 이름 생성
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
    products_df = products_df.fillna(0)

    # 거래처 DB 로드
    clients_ws = client.open(CLIENT_DB_NAME).worksheet("confirmed_clients")
    clients_df = pd.DataFrame(clients_ws.get_all_records())

    # 가격 DB 로드
    prices_ws = client.open(PRICE_DB_NAME).worksheet("confirmed_prices")
    prices_df = pd.DataFrame(prices_ws.get_all_records())
    
    return products_df, clients_df, prices_df

# --- 메인 앱 실행 ---
try:
    products_df, customers_df, prices_df = load_and_prep_data()
except Exception as e:
    st.error(f"데이터베이스 로딩 중 심각한 오류가 발생했습니다: {e}")
    st.info("구글 시트의 이름, 탭 이름, 공유 설정을 다시 확인해주세요.")
    st.stop()

# 데이터 마이그레이션을 위한 안내
if not prices_df.empty and 'unique_name' not in prices_df.columns:
    st.error("🚨 데이터베이스 구조 업데이트 필요!")
    st.warning(
        """
        앱의 데이터 저장 방식이 개선되었습니다. 기존 데이터를 새 구조로 전환해야 합니다.
        
        **아래 절차를 따라주세요:**
        1. **[이곳을 클릭하여 'Goremi Price DB' 시트로 이동합니다.](https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit)** (본인의 시트 링크로 수정하세요)
        2. `confirmed_prices` 탭에 있는 **모든 데이터를 삭제합니다.** (헤더 행은 남겨두세요)
        3. 앱으로 돌아와 **새로고침(F5)** 합니다.
        4. '거래처별 품목 관리' 탭에서 취급 품목을 다시 체크하고 저장하면, 새 데이터 형식으로 정상 작동합니다.
        """
    )
    st.stop()

# --- UI 탭 정의 ---
st.title("🐟 goremi 가격 관리 시스템")
tab_matrix, tab_simulate, tab_db_view = st.tabs(["거래처별 품목 관리", "가격 시뮬레이션", "DB 원본 조회"])

# ==================== 거래처별 품목 관리 탭 ====================
with tab_matrix:
    st.header("거래처별 취급 품목 설정")
    st.info("거래처가 취급하는 품목의 체크박스를 선택하거나 해제하세요. 변경 후 반드시 '변경사항 저장' 버튼을 눌러야 DB에 반영됩니다.")

    # 피벗 테이블 생성
    if not prices_df.empty:
        pivot_df = prices_df.pivot_table(index='unique_name', columns='customer_name', aggfunc='size', fill_value=0) > 0
    else:
        pivot_df = pd.DataFrame()

    full_matrix = pd.DataFrame(
        False,
        index=products_df['unique_name'].unique(),
        columns=customers_df['customer_name'].unique()
    )
    full_matrix.update(pivot_df)
    full_matrix = full_matrix.sort_index()

    edited_matrix = st.data_editor(full_matrix, height=800)

    if st.button("✅ 변경사항 저장", use_container_width=True, type="primary"):
        with st.spinner("DB를 업데이트하는 중입니다..."):
            # 현재 DB 상태 다시 로드 (혹시 모를 동시 작업 대비)
            _, _, current_prices = load_and_prep_data()

            changed_items = edited_matrix.reset_index().melt(
                id_vars='index', var_name='customer_name', value_name='is_active'
            ).rename(columns={'index': 'unique_name'})

            # 최종적으로 DB에 있어야 할 모든 조합 (unique_name, customer_name)
            active_combinations = set(tuple(x) for x in changed_items[changed_items['is_active']][['unique_name', 'customer_name']].to_numpy())
            
            # 현재 DB에 있는 조합
            current_combinations = set()
            if not current_prices.empty and 'unique_name' in current_prices.columns:
                current_combinations = set(tuple(x) for x in current_prices[['unique_name', 'customer_name']].to_numpy())

            # 새로 추가해야 할 조합
            to_add_combinations = active_combinations - current_combinations
            # 유지해야 할 기존 조합
            to_keep_combinations = active_combinations.intersection(current_combinations)
            
            # 유지할 데이터 필터링
            final_df = pd.DataFrame()
            if not current_prices.empty and to_keep_combinations:
                final_df = current_prices[current_prices.apply(lambda r: (r['unique_name'], r['customer_name']) in to_keep_combinations, axis=1)]

            # 새로 추가할 데이터 생성
            new_entries = []
            for unique_name, customer_name in to_add_combinations:
                product_info = products_df[products_df['unique_name'] == unique_name].iloc[0]
                new_entry = {
                    "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "unique_name": unique_name,
                    "customer_name": customer_name,
                    "stand_cost": product_info['stand_cost'],
                    "supply_price": product_info['stand_price_ea'],
                    "margin_rate": 0, "profit_per_ea": 0, "profit_per_box": 0
                }
                new_entries.append(new_entry)

            # 데이터 합치기
            if new_entries:
                final_df = pd.concat([final_df, pd.DataFrame(new_entries)], ignore_index=True)
            
            # 구글 시트에 업데이트
            price_sheet = get_gsheet_client().open(PRICE_DB_NAME).worksheet("confirmed_prices")
            set_with_dataframe(price_sheet, final_df, allow_formulas=False)
            
            st.success("취급 품목 정보가 DB에 성공적으로 업데이트되었습니다!")
            st.cache_data.clear()
            time.sleep(1)
            st.rerun()

# ==================== 가격 시뮬레이션 탭 ====================
with tab_simulate:
    st.header("거래처별 품목 가격 시뮬레이션")

    if not customers_df.empty:
        selected_customer_sim = st.selectbox("거래처 선택", customers_df['customer_name'].unique(), key="sim_customer")
    else:
        st.warning("등록된 거래처가 없습니다.")
        st.stop()
    
    if not prices_df.empty:
        active_products_list = prices_df[prices_df['customer_name'] == selected_customer_sim]['unique_name'].unique()
    else:
        active_products_list = []

    if len(active_products_list) == 0:
        st.warning(f"'{selected_customer_sim}'이(가) 취급하는 품목이 없습니다. '거래처별 품목 관리' 탭에서 먼저 설정해주세요.")
    else:
        selected_product_sim = st.selectbox("품목 선택", active_products_list, key="sim_product")
        
        product_info = products_df[products_df['unique_name'] == selected_product_sim].iloc[0]
        customer_info = customers_df[customers_df['customer_name'] == selected_customer_sim].iloc[0]
        
        # price_info를 찾을 때, prices_df가 비어있지 않은지 확인
        if not prices_df.empty:
            price_info_rows = prices_df[(prices_df['unique_name'] == selected_product_sim) & (prices_df['customer_name'] == selected_customer_sim)]
            if not price_info_rows.empty:
                price_info = price_info_rows.iloc[0]
            else: # 혹시 모를 예외 처리: prices_df에 해당 조합이 없는 경우
                price_info = pd.Series({'supply_price': product_info['stand_price_ea']}) # 기본값 설정
        else:
            price_info = pd.Series({'supply_price': product_info['stand_price_ea']})

        st.markdown("---")
        st.subheader(f"'{selected_product_sim}' - '{selected_customer_sim}'")

        col1, col2 = st.columns(2)
        with col1:
            st.write("##### 계약 조건 (수수료, %)")
            numeric_cols = [col for col in customer_info.index if col not in ['customer_name', 'channel_type']]
            conditions = {col: float(customer_info.get(col, 0)) for col in numeric_cols}
            st.dataframe(pd.Series(conditions, name="값"), use_container_width=True)
        
        with col2:
            st.write("##### 가격 입력")
            supply_price = st.number_input(
                "최종 공급 단가 (VAT별도)", value=float(price_info['supply_price'])
            )
        
        stand_cost = float(product_info['stand_cost'])
        box_ea = int(product_info['box_ea'])
        total_deduction_rate = sum(conditions.values()) / 100
        net_settlement_amount = supply_price * (1 - total_deduction_rate)
        profit_per_ea = net_settlement_amount - stand_cost
        margin_rate = (profit_per_ea / net_settlement_amount * 100) if net_settlement_amount > 0 else 0
        profit_per_box = profit_per_ea * box_ea

        st.markdown("---")
        st.subheader("손익 분석 결과")
        res_col1, res_col2, res_col3, res_col4 = st.columns(4)
        res_col1.metric("마진율", f"{margin_rate:.1f} %")
        res_col2.metric("개당 이익", f"{profit_per_ea:,.0f} 원")
        res_col3.metric("박스당 이익", f"{profit_per_box:,.0f} 원")
        res_col4.metric("실정산액", f"{net_settlement_amount:,.0f} 원")

        if st.button("✅ 시뮬레이션 가격 저장", key="save_sim", type="primary"):
            with st.spinner("DB에 가격 정보를 업데이트합니다..."):
                idx_to_update = prices_df[
                    (prices_df['unique_name'] == selected_product_sim) & 
                    (prices_df['customer_name'] == selected_customer_sim)
                ].index
                
                prices_df.loc[idx_to_update, 'supply_price'] = supply_price
                prices_df.loc[idx_to_update, 'margin_rate'] = round(margin_rate, 2)
                prices_df.loc[idx_to_update, 'profit_per_ea'] = round(profit_per_ea)
                prices_df.loc[idx_to_update, 'profit_per_box'] = round(profit_per_box)
                prices_df.loc[idx_to_update, 'confirm_date'] = datetime.now().strftime("%Y-%m-%d %H:%M")

                price_sheet = get_gsheet_client().open(PRICE_DB_NAME).worksheet("confirmed_prices")
                set_with_dataframe(price_sheet, prices_df, allow_formulas=False)
                st.success("가격 정보가 성공적으로 업데이트되었습니다.")
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
