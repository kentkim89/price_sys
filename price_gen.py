import streamlit as st
import pandas as pd
import os

# --- 페이지 설정 ---
st.set_page_config(page_title="고래미 단가 관리 시스템", page_icon="🐟", layout="wide")

# --- 데이터 로딩 함수 ---
@st.cache_data
def load_data(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path).fillna(0) # NaN 값을 0으로 채움
    return pd.DataFrame()

# --- 채널 정보 정의 ---
CHANNEL_INFO = {
    "일반 도매": {"description": "용차/택배 -> 거래선 물류창고 입고", "cost_items": ["운송비 (%)"]},
    "쿠팡 로켓프레시": {"description": "용차 -> 쿠팡 물류창고 입고", "cost_items": ["입고 운송비 (%)", "쿠팡 매입수수료 (%)"]},
    "마트": {"description": "3PL -> 지역별 물류창고 -> 점포 (복합 물류비)", "cost_items": ["3PL 기본료 (%)", "지역 간선비 (%)", "점포 배송비 (%)"]},
    "프랜차이즈 본사": {"description": "용차 -> 지정 물류창고 입고", "cost_items": ["지정창고 입고비 (%)"]},
    "케이터링사": {"description": "3PL -> 지역별 물류창고 (복합 수수료)", "cost_items": ["3PL 기본료 (%)", "피킹 수수료 (%)", "Zone 분류 수수료 (%)"]},
    "기타 채널": {"description": "기본 배송 프로세스", "cost_items": ["기본 물류비 (%)"]}
}

# --- 데이터 로드 ---
products_df = load_data('products.csv')
customers_df = load_data('customers.csv')

if products_df.empty or customers_df.empty:
    st.error("오류: `products.csv` 또는 `customers.csv` 파일을 찾을 수 없습니다. GitHub에 파일이 올바르게 업로드되었는지 확인해주세요.")
    st.stop()

# --- 사이드바 UI ---
st.sidebar.title("🐟 고래미 단가 시뮬레이터")

# 1. 제품 선택
selected_product_name = st.sidebar.selectbox("1. 분석할 제품을 선택하세요.", products_df['product_name'])
selected_product = products_df[products_df['product_name'] == selected_product_name].iloc[0]

# 2. 거래처 선택
selected_customer_name = st.sidebar.selectbox("2. 조건을 불러올 거래처를 선택하세요.", customers_df['customer_name'])
selected_customer = customers_df[customers_df['customer_name'] == selected_customer_name].iloc[0]

# --- 세션 상태를 이용한 가변 가격 및 조건 관리 ---
# 제품이나 거래처가 바뀌면 세션 상태 초기화
if 'current_customer' not in st.session_state or st.session_state.current_customer != selected_customer_name:
    st.session_state.current_product = selected_product_name
    st.session_state.current_customer = selected_customer_name
    
    # 가격 정보 초기화
    st.session_state.editable_cost = selected_product['cost_price']
    st.session_state.editable_standard_price = selected_product['standard_price']
    
    # 채널 조건 초기화 (DB 값으로)
    st.session_state.conditions = {col: selected_customer[col] for col in customers_df.columns if col not in ['customer_name', 'channel_type']}

st.sidebar.markdown("---")
st.sidebar.subheader("3. 기준 가격 시뮬레이션")
st.session_state.editable_cost = st.sidebar.number_input("제품 원가 (VAT 별도)", value=float(st.session_state.editable_cost))
st.session_state.editable_standard_price = st.sidebar.number_input("표준 공급가 (VAT 별도)", value=float(st.session_state.editable_standard_price))
if st.sidebar.button("🔄 원래 가격으로 복원"):
    st.session_state.editable_cost = selected_product['cost_price']
    st.session_state.editable_standard_price = selected_product['standard_price']
    st.rerun()

st.sidebar.markdown("---")
# 4. 계산 기준 선택
calculation_method = st.sidebar.radio("4. 계산 기준을 선택하세요.", ('원가 기반 계산', '표준 공급가 기반 계산'))
if '원가 기반' in calculation_method:
    goraemi_target_margin = st.sidebar.slider("고래미 목표 마진율 (%)", 1, 100, 30)

# --- 메인 대시보드 ---
st.title("📊 단가 분석 대시보드")
st.markdown(f"**제품:** `{selected_product_name}` | **거래처:** `{selected_customer_name}`")

# --- 조건 입력 UI (DB 값으로 자동 채워짐) ---
st.header("1. 거래처 계약 조건 (수정 가능)")

channel_type = selected_customer['channel_type']
info = CHANNEL_INFO.get(channel_type, {"description": "정의되지 않음", "cost_items": []})
st.info(f"**채널 유형:** {channel_type} | **배송 방법:** {info['description']}")

# 두 개의 컬럼으로 조건 입력 필드 배치
col1, col2 = st.columns(2)

# 각 조건에 대해 입력 필드를 만들고, 세션 상태와 연결
with col1:
    st.session_state.conditions['vendor_fee'] = st.number_input("벤더(유통) 수수료 (%)", value=st.session_state.conditions.get('vendor_fee', 0.0))
with col2:
    st.session_state.conditions['discount'] = st.number_input("프로모션 할인율 (%)", value=st.session_state.conditions.get('discount', 0.0))

st.markdown("---")
st.subheader("채널별 특수 비용")
cost_item_cols = st.columns(len(info['cost_items']))
for i, item in enumerate(info['cost_items']):
    with cost_item_cols[i]:
        st.session_state.conditions[item] = st.number_input(item, value=st.session_state.conditions.get(item, 0.0))

# --- 계산 로직 (세션 상태의 조건 값 사용) ---
total_deduction_rate = (st.session_state.conditions['vendor_fee'] + st.session_state.conditions['discount']) / 100
for item in info['cost_items']:
    total_deduction_rate += st.session_state.conditions.get(item, 0.0) / 100

cost_price = st.session_state.editable_cost
standard_price = st.session_state.editable_standard_price
supply_price = 0
goraemi_margin = 0

if '원가 기반' in calculation_method:
    if (1 - goraemi_target_margin / 100) > 0 and (1 - total_deduction_rate) > 0:
        price_for_margin = cost_price / (1 - goraemi_target_margin / 100)
        supply_price = price_for_margin / (1 - total_deduction_rate)
        net_received = supply_price * (1 - total_deduction_rate)
        if net_received > 0: goraemi_margin = (net_received - cost_price) / net_received * 100
else: # 표준 공급가 기반
    supply_price = standard_price
    net_received = supply_price * (1 - total_deduction_rate)
    if net_received > 0: goraemi_margin = (net_received - cost_price) / net_received * 100

# --- 결과 요약 표시 ---
st.header("2. 시뮬레이션 결과")
res_col1, res_col2, res_col3 = st.columns(3)
res_col1.metric("최종 공급단가 (VAT 별도)", f"{supply_price:,.0f} 원")
res_col2.metric("고래미 실현 마진율", f"{goraemi_margin:.1f} %", delta=f"{(goraemi_margin - goraemi_target_margin if '원가 기반' in calculation_method else goraemi_margin):.1f}%")
res_col3.metric("총 비용률 (수수료+할인)", f"{total_deduction_rate * 100:.1f} %")

# ... (최종 소비자가 예측 로직은 변경 없이 사용 가능)
