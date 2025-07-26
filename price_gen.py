import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
import time

# --- 페이지 설정 ---
st.set_page_config(page_title="goremi 가격결정 시스템", page_icon="🐟", layout="wide")

# --- (설정) DB 정보 및 컬럼 정의 ---
PRODUCT_DB_NAME = "Goremi Products DB"
CLIENT_DB_NAME = "Goremi Clients DB"
PRICE_DB_NAME = "Goremi Price DB"

REQUIRED_CLIENT_COLS = [
    'customer_name', 'channel_type', 'vendor_fee', 'discount', '운송비 (%)',
    '입고 운송비 (%)', '쿠팡 매입수수료 (%)', '3PL 기본료 (%)', '지역 간선비 (%)',
    '점포 배송비 (%)', '지정창고 입고비 (%)', '피킹 수수료 (%)', 'Zone 분류 수수료 (%)'
]
NUMERIC_CLIENT_COLS = [col for col in REQUIRED_CLIENT_COLS if col not in ['customer_name', 'channel_type']]


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
    products_df = products_df.fillna(0).sort_values(by='unique_name').reset_index(drop=True)

    # =============================== 여기가 핵심 수정 부분 ===============================
    # 거래처 DB 로드
    clients_ws = client.open(CLIENT_DB_NAME).worksheet("confirmed_clients")
    clients_df = pd.DataFrame(clients_ws.get_all_records())
    
    # 거래처 DB의 숫자 컬럼들도 안전하게 숫자형으로 변환
    for col in NUMERIC_CLIENT_COLS:
        if col in clients_df.columns:
            clients_df[col] = pd.to_numeric(clients_df[col], errors='coerce')
    clients_df = clients_df.fillna(0)
    # =================================================================================
    
    # 가격 DB 로드
    prices_ws = client.open(PRICE_DB_NAME).worksheet("confirmed_prices")
    prices_df = pd.DataFrame(prices_ws.get_all_records())
    
    return products_df, clients_df, prices_df

# --- 메인 앱 실행 ---
try:
    products_df, customers_df, prices_df = load_and_prep_data()
except Exception as e:
    st.error(f"데이터베이스 로딩 중 오류가 발생했습니다: {e}")
    st.stop()

# 데이터 마이그레이션 안내
if not prices_df.empty and 'unique_name' not in prices_df.columns:
    st.error("🚨 데이터베이스 구조 업데이트 필요!")
    st.warning("`Goremi Price DB`의 `confirmed_prices` 시트에 `unique_name` 열이 없습니다. 데이터 저장 방식이 개선되었으므로, 기존 데이터를 삭제하고 앱에서 다시 설정해주세요.")
    st.stop()

# --- UI 탭 정의 ---
st.title("🐟 goremi 가격 관리 시스템")
tab_matrix, tab_simulate, tab_db_view = st.tabs(["거래처별 품목 관리", "가격 시뮬레이션", "DB 원본 조회"])

# ==================== 거래처별 품목 관리 탭 ====================
with tab_matrix:
    st.header("거래처별 취급 품목 설정")
    selected_customer = st.selectbox(
        "관리할 거래처를 선택하세요", customers_df['customer_name'].unique(), key="manage_customer"
    )

    if selected_customer:
        st.markdown(f"#### 📄 **{selected_customer}** 의 취급 품목 목록")
        st.info("아래 목록에서 이 거래처가 취급하는 모든 품목을 체크한 후, '저장' 버튼을 누르세요.")

        active_products_set = set()
        if not prices_df.empty and 'customer_name' in prices_df.columns and 'unique_name' in prices_df.columns:
            active_products_set = set(prices_df[prices_df['customer_name'] == selected_customer]['unique_name'])

        checkbox_states = {}
        for _, product in products_df.iterrows():
            is_checked = product['unique_name'] in active_products_set
            checkbox_states[product['unique_name']] = st.checkbox(
                product['unique_name'], value=is_checked, key=f"check_{selected_customer}_{product['unique_name']}"
            )
        
        st.markdown("---")
        if st.button(f"✅ **{selected_customer}** 의 품목 정보 저장", use_container_width=True, type="primary"):
            with st.spinner("DB를 업데이트하는 중입니다..."):
                _, _, current_prices = load_and_prep_data()
                newly_active_products = {name for name, checked in checkbox_states.items() if checked}
                
                original_active_products = set()
                if not current_prices.empty and 'customer_name' in current_prices.columns and 'unique_name' in current_prices.columns:
                    original_active_products = set(current_prices[current_prices['customer_name'] == selected_customer]['unique_name'])

                to_add = newly_active_products - original_active_products
                
                final_df = pd.DataFrame()
                if not current_prices.empty and 'customer_name' in current_prices.columns:
                    final_df = current_prices[current_prices['customer_name'] != selected_customer].copy()
                
                to_keep = original_active_products.intersection(newly_active_products)
                if not current_prices.empty and to_keep:
                    final_df = pd.concat([final_df, current_prices[current_prices['unique_name'].isin(to_keep) & (current_prices['customer_name'] == selected_customer)]])

                new_entries = []
                for unique_name in to_add:
                    product_info = products_df[products_df['unique_name'] == unique_name].iloc[0]
                    new_entry = {
                        "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "unique_name": unique_name, "customer_name": selected_customer,
                        "stand_cost": product_info['stand_cost'], "supply_price": product_info['stand_price_ea'],
                        "margin_rate": 0, "profit_per_ea": 0, "profit_per_box": 0
                    }
                    new_entries.append(new_entry)
                
                if new_entries:
                    final_df = pd.concat([final_df, pd.DataFrame(new_entries)], ignore_index=True)

                price_sheet = get_gsheet_client().open(PRICE_DB_NAME).worksheet("confirmed_prices")
                set_with_dataframe(price_sheet, final_df, allow_formulas=False)
                
                st.success(f"'{selected_customer}'의 취급 품목 정보가 DB에 성공적으로 업데이트되었습니다!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

# ==================== 가격 시뮬레이션 탭 ====================
with tab_simulate:
    st.header("거래처별 품목 가격 시뮬레이션")
    if customers_df.empty:
        st.warning("등록된 거래처가 없습니다.")
        st.stop()

    selected_customer_sim = st.selectbox("거래처 선택", customers_df['customer_name'].unique(), key="sim_customer")
    
    active_products_list = []
    if not prices_df.empty and 'customer_name' in prices_df.columns and 'unique_name' in prices_df.columns:
        active_products_list = sorted(prices_df[prices_df['customer_name'] == selected_customer_sim]['unique_name'].unique())

    if not active_products_list:
        st.warning(f"'{selected_customer_sim}'이(가) 취급하는 품목이 없습니다. '거래처별 품목 관리' 탭에서 먼저 설정해주세요.")
    else:
        selected_product_sim = st.selectbox("품목 선택", active_products_list, key="sim_product")
        
        product_info = products_df[products_df['unique_name'] == selected_product_sim].iloc[0]
        customer_info = customers_df[customers_df['customer_name'] == selected_customer_sim].iloc[0]
        price_info = prices_df[(prices_df['unique_name'] == selected_product_sim) & (prices_df['customer_name'] == selected_customer_sim)].iloc[0]

        st.markdown("---")
        st.subheader(f"'{selected_product_sim}' - '{selected_customer_sim}'")

        col1, col2 = st.columns(2)
        with col1:
            st.write("##### 계약 조건 (수수료, %)")
            # 이 부분은 이제 안전하게 작동합니다.
            conditions = {col: float(customer_info.get(col, 0)) for col in NUMERIC_CLIENT_COLS}
            st.dataframe(pd.Series(conditions, name="값"), use_container_width=True)
        
        with col2:
            st.write("##### 가격 입력")
            supply_price = st.number_input(
                "최종 공급 단가 (VAT별도)", value=float(price_info.get('supply_price', 0))
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
