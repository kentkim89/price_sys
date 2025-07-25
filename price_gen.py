import streamlit as st
import pandas as pd
import os
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# --- 페이지 설정 ---
st.set_page_config(page_title="고레미 가격결정 시스템", page_icon="🐟", layout="wide")

# --- 데이터 로딩 (정적 파일) ---
@st.cache_data
def load_static_data(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path).fillna(0)
    return pd.DataFrame()

PRODUCTS_FILE = 'products.csv'
CUSTOMERS_FILE = 'customers.csv'

products_df = load_static_data(PRODUCTS_FILE)
customers_df = load_static_data(CUSTOMERS_FILE)

# --- Google Sheets 연결 생성 및 데이터 로드 ---
try:
    conn = st.gsheets.connection()
    confirmed_prices_df = conn.read(worksheet="confirmed_prices", usecols=list(range(8)), ttl=5)
    confirmed_prices_df = confirmed_prices_df.dropna(how="all") # 빈 행 제거
except Exception as e:
    st.error(f"Google Sheets 연결에 실패했습니다. 설정(Secrets)을 확인해주세요. 오류: {e}")
    confirmed_prices_df = pd.DataFrame() # 에러 시 빈 데이터프레임으로 시작

# 필수 파일 확인
if products_df.empty or customers_df.empty:
    st.error(f"`{PRODUCTS_FILE}` 또는 `{CUSTOMERS_FILE}` 파일을 찾을 수 없습니다.")
    st.stop()

# --- (설정) 채널 정보 정의 ---
CHANNEL_INFO = {
    "일반 도매": {"description": "용차/택배 -> 거래선 물류창고 입고", "cost_items": ["운송비 (%)"]},
    "쿠팡 로켓프레시": {"description": "용차 -> 쿠팡 물류창고 입고", "cost_items": ["입고 운송비 (%)", "쿠팡 매입수수료 (%)"]},
    "마트": {"description": "3PL -> 지역별 물류창고 -> 점포", "cost_items": ["3PL 기본료 (%)", "지역 간선비 (%)", "점포 배송비 (%)"]},
    "프랜차이즈 본사": {"description": "용차 -> 지정 물류창고 입고", "cost_items": ["지정창고 입고비 (%)"]},
    "케이터링사": {"description": "3PL -> 지역별 물류창고 (복합 수수료)", "cost_items": ["3PL 기본료 (%)", "피킹 수수료 (%)", "Zone 분류 수수료 (%)"]},
    "기타 채널": {"description": "기본 배송 프로세스", "cost_items": ["기본 물류비 (%)"]}
}

# --- 사이드바 ---
st.sidebar.title("📄 작업 공간")
selected_product_name = st.sidebar.selectbox("1. 분석할 제품 선택", products_df['product_name'])
selected_product = products_df[products_df['product_name'] == selected_product_name].iloc[0]
selected_customer_name = st.sidebar.selectbox("2. 거래처 선택", customers_df['customer_name'])
selected_customer = customers_df[customers_df['customer_name'] == selected_customer_name].iloc[0]

# --- 세션 관리 (선택 변경 시 값 초기화) ---
if 'current_customer' not in st.session_state or st.session_state.current_customer != selected_customer_name or st.session_state.current_product != selected_product_name:
    st.session_state.current_product = selected_product_name
    st.session_state.current_customer = selected_customer_name
    st.session_state.editable_cost = selected_product['cost_price']
    st.session_state.editable_standard_price = selected_product['standard_price']
    st.session_state.conditions = {col: selected_customer[col] for col in customers_df.columns if col not in ['customer_name', 'channel_type']}

# 3. 기준 가격 시뮬레이션 UI
st.sidebar.markdown("---")
st.sidebar.subheader("3. 기준 가격 시뮬레이션")
st.session_state.editable_cost = st.sidebar.number_input("제품 원가", value=float(st.session_state.editable_cost))
st.session_state.editable_standard_price = st.sidebar.number_input("표준 공급가", value=float(st.session_state.editable_standard_price))
if st.sidebar.button("🔄 가격 복원"):
    st.session_state.editable_cost = selected_product['cost_price']
    st.session_state.editable_standard_price = selected_product['standard_price']
    st.rerun()

# 4. 계산 기준 선택 UI
st.sidebar.markdown("---")
calculation_method = st.sidebar.radio("4. 계산 기준 선택", ('원가 기반 계산', '표준 공급가 기반 계산'))
goremi_target_margin = st.sidebar.slider("고레미 목표 마진율 (%)", 1, 100, 30) if '원가 기반' in calculation_method else 0

# --- 메인 대시보드 (탭 UI) ---
st.title("🐟 고레미 가격결정 시스템 (Google Sheets 연동)")
tab_simulate, tab_db_view = st.tabs(["가격 시뮬레이션 & 확정", "확정 가격 DB 보기 (실시간)"])

with tab_simulate:
    # (시뮬레이션 UI 및 계산 로직)
    st.header("1. 시뮬레이션 조건")
    st.markdown(f"**제품:** `{selected_product_name}` | **거래처:** `{selected_customer_name}`")
    channel_type = selected_customer['channel_type']
    info = CHANNEL_INFO.get(channel_type, {"description": "정의되지 않음", "cost_items": []})
    st.info(f"**채널 유형:** {channel_type} | **배송 방법:** {info['description']}")
    
    with st.container(border=True):
        st.subheader("계약 조건 (수정 가능)")
        col1, col2 = st.columns(2)
        with col1: st.session_state.conditions['vendor_fee'] = st.number_input("벤더 수수료 (%)", value=st.session_state.conditions.get('vendor_fee', 0.0), key='vendor_fee_input')
        with col2: st.session_state.conditions['discount'] = st.number_input("프로모션 할인율 (%)", value=st.session_state.conditions.get('discount', 0.0), key='discount_input')
        
        cost_items = info['cost_items']
        if cost_items:
            st.markdown("---")
            st.write("**채널별 특수 비용**")
            cost_item_cols = st.columns(len(cost_items))
            for i, item in enumerate(cost_items):
                with cost_item_cols[i]: st.session_state.conditions[item] = st.number_input(item, value=st.session_state.conditions.get(item, 0.0), key=f"cost_{item}")
    
    total_deduction_rate = (st.session_state.conditions['vendor_fee'] + st.session_state.conditions['discount'] + sum(st.session_state.conditions.get(item, 0.0) for item in cost_items)) / 100
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

    # --- 데이터 쓰기(Write) 로직 ---
    st.markdown("---")
    if st.button("✅ 이 가격으로 DB에 영구 저장하기", type="primary", use_container_width=True):
        with st.spinner("Google Sheets에 데이터를 저장하는 중입니다..."):
            new_price_entry_df = pd.DataFrame([{
                "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"), "product_name": selected_product_name,
                "customer_name": selected_customer_name, "cost_price": cost_price, "standard_price": standard_price,
                "supply_price": round(supply_price), "margin_rate": round(goremi_margin, 2), "total_fee_rate": round(total_deduction_rate * 100, 2)
            }])
            
            updated_df = pd.concat([confirmed_prices_df, new_price_entry_df], ignore_index=True).drop_duplicates(
                subset=['product_name', 'customer_name'], keep='last'
            )

            conn.update(worksheet="confirmed_prices", data=updated_df)
            st.success("✓ 저장이 완료되었습니다! '확정 가격 DB 보기' 탭에서 실시간으로 확인할 수 있습니다.")
            st.cache_data.clear()

with tab_db_view:
    st.header("확정 가격 DB (Google Sheets 실시간 데이터)")
    st.dataframe(confirmed_prices_df, use_container_width=True, height=600)
