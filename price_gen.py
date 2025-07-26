import streamlit as st
import pandas as pd
import os
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

# --- 비밀번호 잠금 기능 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if not st.session_state.password_correct:
        st.title("🐟 goremi 가격결정 시스템")
        st.header("비밀번호를 입력하세요")
        with st.form("password_form"):
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("입장")
            if submitted:
                if password == "0422":
                    st.session_state.password_correct = True
                    st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
        st.stop()

# --- 구글 시트 연동 및 데이터 로딩 함수 ---
def get_gsheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_data_from_gsheet(db_name, worksheet_name, required_cols, numeric_cols=None):
    try:
        client = get_gsheet_client()
        spreadsheet = client.open(db_name)
        worksheet = spreadsheet.worksheet(worksheet_name)
        df = pd.DataFrame(worksheet.get_all_records())

        if df.empty: return pd.DataFrame(columns=required_cols)
        
        for col in required_cols:
            if col not in df.columns: df[col] = 0
        
        # 숫자여야 하는 모든 열에 대해, 쉼표를 제거하고 숫자로 변환
        if numeric_cols:
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace(',', '')
                    df[col] = pd.to_numeric(df[col], errors='coerce')

        return df.fillna(0)
    except Exception as e:
        st.error(f"'{db_name}' DB 로딩 중 오류 발생: {e}")
        return pd.DataFrame()

# --- 메인 앱 실행 ---
check_password()

# --- 이하는 비밀번호를 정확히 입력해야만 실행되는 코드들 ---
# DB에서 데이터 로드
products_df = load_data_from_gsheet(PRODUCT_DB_NAME, "products", [], numeric_cols=['stand_cost', 'stand_price_ea', 'box_ea'])
customers_df = load_data_from_gsheet(CLIENT_DB_NAME, "confirmed_clients", REQUIRED_CLIENT_COLS, numeric_cols=NUMERIC_CLIENT_COLS)
confirmed_prices_df = load_data_from_gsheet(PRICE_DB_NAME, "confirmed_prices", [])


# 필수 데이터 확인
if products_df.empty:
    st.error(f"'{PRODUCT_DB_NAME}'에서 제품 정보를 불러올 수 없습니다. DB를 확인해주세요.")
    st.stop()
if customers_df.empty:
    st.warning(f"'{CLIENT_DB_NAME}'에서 거래처 정보를 불러오지 못했습니다.")

# --- 사이드바 ---
st.sidebar.title("📄 작업 공간")
if st.sidebar.button("🔒 잠금화면으로 돌아가기"):
    st.session_state.password_correct = False
    st.rerun()
st.sidebar.markdown("---")

# 신규 거래처 추가 (이전과 동일)
with st.sidebar.expander("➕ 신규 거래처 추가"):
    with st.form("new_client_form", clear_on_submit=True):
        # ... (이전과 동일한 코드)
        pass

# 분석 대상 선택
st.sidebar.subheader("1. 분석 대상 선택")
selected_product_name = st.sidebar.selectbox("제품 선택", products_df['product_name_kr'])
selected_product = products_df.loc[products_df['product_name_kr'] == selected_product_name].iloc[0]

if not customers_df.empty:
    selected_customer_name = st.sidebar.selectbox("거래처 선택", customers_df['customer_name'])
    selected_customer = customers_df.loc[customers_df['customer_name'] == selected_customer_name].iloc[0]
else:
    st.sidebar.error("선택할 거래처가 없습니다.")
    st.stop()

# --- 메인 대시보드 ---
st.title("🐟 goremi 가격 결정 및 관리 시스템")

# 세션 상태 초기화 (선택 변경 시)
if 'current_customer' not in st.session_state or st.session_state.current_customer != selected_customer_name or st.session_state.current_product != selected_product_name:
    st.session_state.current_product = selected_product_name
    st.session_state.current_customer = selected_customer_name
    # 공급 단가의 초기값을 DB의 표준가로 설정
    st.session_state.supply_price = float(selected_product['stand_price_ea'])
    # 계약 조건 로드
    st.session_state.conditions = {col: selected_customer[col] for col in NUMERIC_CLIENT_COLS}


tab_simulate, tab_db_view = st.tabs(["가격 시뮬레이션 & 확정", "DB 조회"])

with tab_simulate:
    st.header("1. 기본 정보")
    col1, col2, col3 = st.columns(3)
    col1.metric("제품명", selected_product_name)
    col2.metric("거래처명", selected_customer_name)
    col3.metric("제품 표준 원가", f"{selected_product['stand_cost']:,.0f} 원")

    st.markdown("---")

    st.header("2. 시뮬레이션 입력")
    # 계약 조건 및 최종 공급가 입력
    with st.container(border=True):
        st.subheader("계약 조건 (수수료, %)")
        cost_cols = st.columns(4)
        idx = 0
        for key, value in st.session_state.conditions.items():
            with cost_cols[idx % 4]:
                st.session_state.conditions[key] = st.number_input(key, value=float(value), key=f"cond_{key}")
            idx += 1
        
        st.divider()
        st.subheader("최종 공급 단가 (VAT별도)")
        # 최종 공급 단가를 직접 입력받음. 초기값은 제품의 표준가.
        st.session_state.supply_price = st.number_input(
            "공급 단가 입력 (원)",
            value=st.session_state.supply_price,
            help="이 가격을 기준으로 모든 손익이 계산됩니다."
        )

    # --- 계산 로직 ---
    # 입력된 값을 기준으로 손익 분석
    supply_price = st.session_state.supply_price
    stand_cost = float(selected_product['stand_cost'])
    box_ea = int(selected_product['box_ea'])

    # 총 비용률 및 비용액 계산
    total_deduction_rate = sum(st.session_state.conditions.values()) / 100
    total_deduction_amount = supply_price * total_deduction_rate

    # 실정산액 계산
    net_settlement_amount = supply_price - total_deduction_amount

    # 개당 이익 및 마진율 계산
    profit_per_ea = net_settlement_amount - stand_cost
    margin_rate = (profit_per_ea / net_settlement_amount * 100) if net_settlement_amount > 0 else 0

    # 박스당 이익 계산
    profit_per_box = profit_per_ea * box_ea

    st.markdown("---")
    st.header("3. 손익 분석 결과")
    res_col1, res_col2, res_col3, res_col4 = st.columns(4)
    res_col1.metric("마진율", f"{margin_rate:.1f} %")
    res_col2.metric("개당 이익", f"{profit_per_ea:,.0f} 원")
    res_col3.metric("박스당 이익", f"{profit_per_box:,.0f} 원")
    res_col4.metric("실정산액", f"{net_settlement_amount:,.0f} 원", help="공급가에서 모든 수수료를 제외하고 실제 정산받는 금액")

    st.markdown("---")
    # DB 저장 버튼
    if st.button("✅ 이 가격으로 확정하고 DB에 저장", type="primary", use_container_width=True):
        with st.spinner("DB에 데이터를 저장하는 중입니다..."):
            try:
                client = get_gsheet_client()
                
                # --- 계약 조건 업데이트 (Goremi Clients DB) ---
                client_sheet = client.open(CLIENT_DB_NAME).worksheet("confirmed_clients")
                all_clients_df = load_data_from_gsheet(CLIENT_DB_NAME, "confirmed_clients", REQUIRED_CLIENT_COLS, numeric_cols=NUMERIC_CLIENT_COLS)
                condition_keys = list(st.session_state.conditions.keys())
                condition_values = list(st.session_state.conditions.values())
                all_clients_df.loc[all_clients_df['customer_name'] == selected_customer_name, condition_keys] = condition_values
                set_with_dataframe(client_sheet, all_clients_df, allow_formulas=False)

                # --- 확정 가격 저장 (Goremi Price DB) ---
                price_sheet = client.open(PRICE_DB_NAME).worksheet("confirmed_prices")
                new_price_entry = {
                    "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"), "product_name": selected_product_name,
                    "customer_name": selected_customer_name, "stand_cost": stand_cost, 
                    "supply_price": round(supply_price), "margin_rate": round(margin_rate, 2),
                    "profit_per_ea": round(profit_per_ea), "profit_per_box": round(profit_per_box)
                }
                
                # 중복은 최신으로 갱신하며 합치기
                price_df = pd.DataFrame(price_sheet.get_all_records())
                new_df = pd.DataFrame([new_price_entry])
                combined_df = pd.concat([price_df, new_df]).drop_duplicates(
                    subset=['product_name', 'customer_name'], keep='last'
                )
                set_with_dataframe(price_sheet, combined_df, allow_formulas=False)

                st.success("계약 조건 및 확정 가격이 DB에 성공적으로 저장되었습니다.")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

            except Exception as e:
                st.error(f"DB 저장 중 오류 발생: {e}")

with tab_db_view:
    st.header("전체 확정 가격 DB")
    st.dataframe(confirmed_prices_df, use_container_width=True)
    st.header("전체 거래처 목록")
    st.dataframe(customers_df, use_container_width=True)
    st.header("제품 마스터 DB")
    st.dataframe(products_df, use_container_width=True)
