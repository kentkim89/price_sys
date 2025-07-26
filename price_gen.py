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
CLIENT_DB_NAME = "Goremi Clients DB"
PRICE_DB_NAME = "Goremi Price DB"
PRODUCTS_FILE = 'products.csv'

REQUIRED_CLIENT_COLS = [
    'customer_name', 'channel_type', 'vendor_fee', 'discount', '운송비 (%)',
    '입고 운송비 (%)', '쿠팡 매입수수료 (%)', '3PL 기본료 (%)', '지역 간선비 (%)',
    '점포 배송비 (%)', '지정창고 입고비 (%)', '피킹 수수료 (%)', 'Zone 분류 수수료 (%)'
]
NUMERIC_CLIENT_COLS = [col for col in REQUIRED_CLIENT_COLS if col not in ['customer_name', 'channel_type']]

# =============================== 여기가 핵심 수정 부분 ===============================
# --- 비밀번호 잠금 기능 ---
def check_password():
    """비밀번호가 맞을 때까지 앱의 나머지 부분을 실행하지 않고 대기합니다."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if not st.session_state.password_correct:
        st.title("🐟 goremi 가격결정 시스템")
        st.header("비밀번호를 입력하세요")

        with st.form("password_form"):
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("입장")

            if submitted:
                # 비밀번호를 "0422"로 설정
                if password == "0422":
                    st.session_state.password_correct = True
                    st.rerun()  # 비밀번호가 맞으면 앱을 다시 실행하여 메인 화면 표시
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
        
        # 비밀번호가 맞지 않으면 아래 코드 실행을 중단
        st.stop()
# =================================================================================

# --- 구글 시트 연동 및 데이터 로딩 함수 (이전과 동일) ---
def get_gsheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_data_from_gsheet(db_name, worksheet_name, required_cols, is_client_db=False):
    try:
        client = get_gsheet_client()
        spreadsheet = client.open(db_name)
        worksheet = spreadsheet.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=required_cols)
        for col in required_cols:
            if col not in df.columns: df[col] = 0
        if is_client_db:
            numeric_cols_in_df = [col for col in NUMERIC_CLIENT_COLS if col in df.columns]
            for col in numeric_cols_in_df: df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.fillna(0)
    except Exception as e:
        st.error(f"'{db_name}' DB 로딩 중 오류 발생: {e}")
        return pd.DataFrame()

@st.cache_data
def load_local_data(file_path):
    if os.path.exists(file_path): return pd.read_csv(file_path).fillna(0)
    return pd.DataFrame()

# --- 메인 앱 실행 ---
check_password() # 모든 것보다 먼저 비밀번호 확인 실행

# --- 이하는 비밀번호를 정확히 입력해야만 실행되는 코드들 ---
CHANNEL_INFO = { "일반 도매": {"description": "용차/택배 -> 거래선 물류창고 입고", "cost_items": ["운송비 (%)"]}, "쿠팡 로켓프레시": {"description": "용차 -> 쿠팡 물류창고 입고", "cost_items": ["입고 운송비 (%)", "쿠팡 매입수수료 (%)"]}, "마트": {"description": "3PL -> 지역별 물류창고 -> 점포", "cost_items": ["3PL 기본료 (%)", "지역 간선비 (%)", "점포 배송비 (%)"]}, "프랜차이즈 본사": {"description": "용차 -> 지정 물류창고 입고", "cost_items": ["지정창고 입고비 (%)"]}, "케이터링사": {"description": "3PL -> 지역별 물류창고 (복합 수수료)", "cost_items": ["3PL 기본료 (%)", "피킹 수수료 (%)", "Zone 분류 수수료 (%)"]}, "기타 채널": {"description": "기본 배송 프로세스", "cost_items": ["기본 물류비 (%)"]} }
customers_df = load_data_from_gsheet(CLIENT_DB_NAME, "confirmed_clients", REQUIRED_CLIENT_COLS, is_client_db=True)
confirmed_prices_df = load_data_from_gsheet(PRICE_DB_NAME, "confirmed_prices", ['confirm_date', 'product_name', 'customer_name', 'cost_price', 'standard_price', 'supply_price', 'margin_rate', 'total_fee_rate'])
products_df = load_local_data(PRODUCTS_FILE)

# --- 사이드바 ---
st.sidebar.title("📄 작업 공간")
if st.sidebar.button("🔒 잠금화면으로 돌아가기"):
    st.session_state.password_correct = False
    st.rerun()
st.sidebar.markdown("---")

with st.sidebar.expander("➕ 신규 거래처 추가"):
    with st.form("new_client_form", clear_on_submit=True):
        new_customer_name = st.text_input("거래처명")
        new_channel_type = st.selectbox("채널 유형", options=list(CHANNEL_INFO.keys()))
        submitted = st.form_submit_button("✅ 신규 거래처 저장")
        if submitted:
            if not new_customer_name: st.warning("거래처명을 입력해주세요.")
            elif new_customer_name in customers_df['customer_name'].values: st.error("이미 존재하는 거래처명입니다.")
            else:
                with st.spinner("신규 거래처를 DB에 저장 중입니다..."):
                    try:
                        client = get_gsheet_client()
                        worksheet = client.open(CLIENT_DB_NAME).worksheet("confirmed_clients")
                        new_row = [new_customer_name, new_channel_type] + [0.0] * len(NUMERIC_CLIENT_COLS)
                        worksheet.append_row(new_row, value_input_option='USER_ENTERED')
                        st.success(f"'{new_customer_name}'이(가) 추가되었습니다.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e: st.error(f"저장 중 오류 발생: {e}")

# (이하 나머지 코드는 이전 버전과 동일합니다)
st.sidebar.markdown("---")
st.sidebar.subheader("1. 분석 대상 선택")
selected_product_name = st.sidebar.selectbox("제품 선택", products_df['product_name'])
if not customers_df.empty:
    selected_customer_name = st.sidebar.selectbox("거래처 선택", customers_df['customer_name'])
    selected_product = products_df.loc[products_df['product_name'] == selected_product_name].iloc[0]
    selected_customer = customers_df.loc[customers_df['customer_name'] == selected_customer_name].iloc[0]
else:
    st.sidebar.error("선택할 거래처가 없습니다.")
    st.stop()
if 'current_customer' not in st.session_state or st.session_state.current_customer != selected_customer_name or st.session_state.current_product != selected_product_name:
    st.session_state.current_product = selected_product_name
    st.session_state.current_customer = selected_customer_name
    st.session_state.editable_cost = selected_product['cost_price']
    st.session_state.editable_standard_price = selected_product['standard_price']
    st.session_state.conditions = {col: selected_customer[col] for col in NUMERIC_CLIENT_COLS}
st.sidebar.markdown("---")
st.sidebar.subheader("2. 기준 가격 시뮬레이션")
st.session_state.editable_cost = st.sidebar.number_input("제품 원가", value=float(st.session_state.editable_cost))
st.session_state.editable_standard_price = st.sidebar.number_input("표준 공급가", value=float(st.session_state.editable_standard_price))
if st.sidebar.button("🔄 가격 복원"):
    st.session_state.editable_cost = selected_product['cost_price']
    st.session_state.editable_standard_price = selected_product['standard_price']
    st.rerun()
st.sidebar.markdown("---")
st.sidebar.subheader("3. 계산 기준 선택")
calculation_method = st.sidebar.radio("계산 기준 선택", ('원가 기반 계산', '표준 공급가 기반 계산'))
goremi_target_margin = st.sidebar.slider("goremi 목표 마진율 (%)", 1, 100, 30) if '원가 기반' in calculation_method else 0
st.title("🐟 goremi 가격 결정 및 관리 시스템")
tab_simulate, tab_db_view = st.tabs(["가격 시뮬레이션 & 확정", "DB 조회"])
with tab_simulate:
    st.header("1. 시뮬레이션 조건")
    st.markdown(f"**제품:** `{selected_product_name}` | **거래처:** `{selected_customer_name}`")
    channel_type = selected_customer['channel_type']
    info = CHANNEL_INFO.get(channel_type, {"description": "정의되지 않음", "cost_items": []})
    st.info(f"**채널 유형:** {channel_type} | **배송 방법:** {info['description']}")
    with st.container(border=True):
        st.subheader("계약 조건 (수정 시 DB에 자동 반영됨)")
        cost_cols = st.columns(4)
        idx = 0
        for key, value in st.session_state.conditions.items():
            with cost_cols[idx % 4]:
                st.session_state.conditions[key] = st.number_input(key, value=float(value), key=f"cond_{key}")
            idx += 1
    total_deduction_rate = sum(st.session_state.conditions.values()) / 100
    cost_price, standard_price = st.session_state.editable_cost, st.session_state.editable_standard_price
    supply_price, goremi_margin = 0, 0
    if '원가 기반' in calculation_method:
        if (1 - goremi_target_margin / 100) > 0 and (1 - total_deduction_rate) > 0:
            price_for_margin = cost_price / (1 - goremi_target_margin / 100)
            supply_price = price_for_margin / (1 - total_deduction_rate)
            net_received = supply_price * (1 - total_deduction_rate)
            if net_received > 0: goremi_margin = (net_received - cost_price) / net_received * 100
    else:
        supply_price = standard_price
        net_received = supply_price * (1 - total_deduction_rate)
        if net_received > 0: goremi_margin = (net_received - cost_price) / net_received * 100
    st.header("2. 시뮬레이션 결과")
    res_col1, res_col2, res_col3 = st.columns(3)
    res_col1.metric("계산된 최종 공급단가", f"{supply_price:,.0f} 원")
    res_col2.metric("예상 마진율", f"{goremi_margin:.1f} %")
    res_col3.metric("총 비용률", f"{total_deduction_rate * 100:.1f} %")
    st.markdown("---")
    if st.button("✅ 이 가격으로 확정하고 DB에 자동 저장", type="primary", use_container_width=True):
        with st.spinner("DB에 데이터를 저장하는 중입니다..."):
            try:
                client = get_gsheet_client()
                client_sheet = client.open(CLIENT_DB_NAME).worksheet("confirmed_clients")
                all_clients_df = load_data_from_gsheet(CLIENT_DB_NAME, "confirmed_clients", REQUIRED_CLIENT_COLS, is_client_db=True)
                condition_keys = list(st.session_state.conditions.keys())
                condition_values = list(st.session_state.conditions.values())
                all_clients_df.loc[all_clients_df['customer_name'] == selected_customer_name, condition_keys] = condition_values
                set_with_dataframe(client_sheet, all_clients_df)
                price_sheet = client.open(PRICE_DB_NAME).worksheet("confirmed_prices")
                new_price_entry = { "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"), "product_name": selected_product_name, "customer_name": selected_customer_name, "cost_price": cost_price, "standard_price": standard_price, "supply_price": round(supply_price), "margin_rate": round(goremi_margin, 2), "total_fee_rate": round(total_deduction_rate * 100, 2) }
                all_prices_df = load_data_from_gsheet(PRICE_DB_NAME, "confirmed_prices", list(new_price_entry.keys()))
                new_df = pd.DataFrame([new_price_entry])
                combined_df = pd.concat([all_prices_df, new_df]).drop_duplicates(subset=['product_name', 'customer_name'], keep='last')
                set_with_dataframe(price_sheet, combined_df)
                st.success("계약 조건 및 확정 가격이 DB에 성공적으로 저장되었습니다.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e: st.error(f"DB 저장 중 오류 발생: {e}")
with tab_db_view:
    st.header("전체 확정 가격 DB")
    st.dataframe(confirmed_prices_df, use_container_width=True)
    st.header("전체 거래처 목록")
    st.dataframe(customers_df, use_container_width=True)
