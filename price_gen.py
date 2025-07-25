import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 페이지 설정 ---
st.set_page_config(page_title="고래미 가격결정 시스템", page_icon="🐟", layout="wide")

# --- 데이터 로딩 함수 ---
@st.cache_data
def load_data(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path).fillna(0)
    return pd.DataFrame()

# --- 데이터 파일 경로 ---
PRODUCTS_FILE = 'products.csv'
CUSTOMERS_FILE = 'customers.csv'
CONFIRMED_PRICES_FILE = 'confirmed_prices.csv'

# --- 데이터 로드 ---
products_df = load_data(PRODUCTS_FILE)
customers_df = load_data(CUSTOMERS_FILE)
confirmed_prices_df = load_data(CONFIRMED_PRICES_FILE)

# --- 세션 상태 초기화: 앱 세션 동안 확정 목록을 저장할 리스트 ---
if 'confirmed_list' not in st.session_state:
    st.session_state.confirmed_list = []

# 필수 파일 확인
if products_df.empty or customers_df.empty:
    st.error(f"`{PRODUCTS_FILE}` 또는 `{CUSTOMERS_FILE}` 파일을 찾을 수 없습니다. GitHub에 파일이 올바르게 업로드되었는지 확인해주세요.")
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

# 1. 제품 및 거래처 선택
selected_product_name = st.sidebar.selectbox("1. 분석할 제품 선택", products_df['product_name'])
selected_product = products_df[products_df['product_name'] == selected_product_name].iloc[0]
selected_customer_name = st.sidebar.selectbox("2. 거래처 선택", customers_df['customer_name'])
selected_customer = customers_df[customers_df['customer_name'] == selected_customer_name].iloc[0]

# --- 세션 상태 관리 (선택 변경 시 값 초기화) ---
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
goraemi_target_margin = st.sidebar.slider("고래미 목표 마진율 (%)", 1, 100, 30) if '원가 기반' in calculation_method else 0

# --- 메인 대시보드 (탭으로 UI 분리) ---
st.title("🐟 고래미 가격 결정 및 관리 시스템")

tab_simulate, tab_manage = st.tabs(["가격 시뮬레이션 & 확정", "확정 목록 관리 & DB 업데이트"])

# ==================== 시뮬레이션 탭 ====================
with tab_simulate:
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

    # --- 계산 로직 ---
    total_deduction_rate = (st.session_state.conditions['vendor_fee'] + st.session_state.conditions['discount'] + sum(st.session_state.conditions.get(item, 0.0) for item in cost_items)) / 100
    cost_price, standard_price = st.session_state.editable_cost, st.session_state.editable_standard_price
    supply_price, goraemi_margin = 0, 0
    if '원가 기반' in calculation_method:
        if (1 - goraemi_target_margin / 100) > 0 and (1 - total_deduction_rate) > 0:
            price_for_margin = cost_price / (1 - goraemi_target_margin / 100)
            supply_price = price_for_margin / (1 - total_deduction_rate)
            net_received = supply_price * (1 - total_deduction_rate)
            if net_received > 0: goraemi_margin = (net_received - cost_price) / net_received * 100
    else:
        supply_price = standard_price
        net_received = supply_price * (1 - total_deduction_rate)
        if net_received > 0: goraemi_margin = (net_received - cost_price) / net_received * 100

    # --- 결과 및 확정 버튼 ---
    st.header("2. 시뮬레이션 결과")
    res_col1, res_col2, res_col3 = st.columns(3)
    res_col1.metric("계산된 최종 공급단가", f"{supply_price:,.0f} 원")
    res_col2.metric("예상 마진율", f"{goraemi_margin:.1f} %")
    res_col3.metric("총 비용률", f"{total_deduction_rate * 100:.1f} %")

    st.markdown("---")
    if st.button("✅ 이 가격으로 확정하기", type="primary", use_container_width=True):
        new_price_entry = {
            "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"), "product_name": selected_product_name,
            "customer_name": selected_customer_name, "cost_price": cost_price, "standard_price": standard_price,
            "supply_price": round(supply_price), "margin_rate": round(goraemi_margin, 2), "total_fee_rate": round(total_deduction_rate * 100, 2)
        }
        st.session_state.confirmed_list.append(new_price_entry)
        st.success(f"가격이 확정되었습니다! '확정 목록 관리' 탭에서 확인하고 모든 작업 후 DB를 업데이트해주세요.")


# ==================== DB 관리 탭 ====================
with tab_manage:
    st.header("이번 세션에서 확정한 목록")
    if not st.session_state.confirmed_list:
        st.info("아직 이번 세션에서 확정한 가격이 없습니다. '가격 시뮬레이션 & 확정' 탭에서 가격을 확정해주세요.")
    else:
        session_df = pd.DataFrame(st.session_state.confirmed_list)
        st.dataframe(session_df, use_container_width=True)

    st.header("영구 저장을 위한 DB 업데이트")
    st.warning("**매우 중요:** 아래 절차를 따라야 데이터가 영구적으로 저장(누적)됩니다.")

    with st.container(border=True):
        st.markdown("""
        **데이터 영구 저장 방법 (필수 절차)**

        1.  **데이터 종합 및 다운로드**
            *   모든 가격 확정 작업을 마친 후, 아래의 `[📥 DB 업데이트용 파일 다운로드]` 버튼을 클릭하여 `new_confirmed_prices.csv` 파일을 다운로드합니다.
            *   이 파일 안에는 **과거의 모든 기록**과 **오늘 새로 확정한 기록**이 모두 합쳐져 있습니다.

        2.  **GitHub 파일 업데이트**
            *   [여기를 클릭하여 GitHub의 `confirmed_prices.csv` 파일로 이동합니다.](https://github.com/YOUR_USERNAME/YOUR_REPOSITORY/blob/main/confirmed_prices.csv)  <!-- 링크를 본인 것으로 수정하세요 -->
            *   파일 우측 상단의 **연필(✏️) 아이콘**을 클릭하여 편집 모드로 들어갑니다.
            *   **기존 내용을 모두 삭제**하고, 방금 다운로드한 `new_confirmed_prices.csv` 파일의 내용을 **전체 복사하여 붙여넣습니다.**

        3.  **저장 완료**
            *   페이지 하단의 초록색 **`Commit changes`** 버튼을 누르면 모든 변경사항이 영구적으로 저장됩니다. 앱을 새로고침하면 '기존 확정 가격 DB'에 반영된 것을 볼 수 있습니다.
        """)

    # --- 다운로드 버튼 로직 ---
    # 누적을 위한 데이터 결합
    session_df_to_save = pd.DataFrame(st.session_state.confirmed_list)
    combined_df = pd.concat([confirmed_prices_df, session_df_to_save]).drop_duplicates(
        subset=['product_name', 'customer_name'], keep='last'
    )

    @st.cache_data
    def convert_df_to_csv(df):
        return df.to_csv(index=False, encoding='utf-8-sig')

    csv_data = convert_df_to_csv(combined_df)

    st.download_button(
       label="📥 DB 업데이트용 파일 다운로드",
       data=csv_data,
       file_name="new_confirmed_prices.csv",
       mime="text/csv",
       use_container_width=True,
       disabled=not st.session_state.confirmed_list # 확정한 내용이 없으면 비활성화
    )
    
    st.header("기존 확정 가격 DB (읽기 전용)")
    st.dataframe(confirmed_prices_df, use_container_width=True)
