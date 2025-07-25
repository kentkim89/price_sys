import streamlit as st
import pandas as pd
import os
from datetime import datetime
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials

# --- 페이지 설정 ---
st.set_page_config(page_title="goremi 가격결정 시스템", page_icon="🐟", layout="wide")

# --- 구글 시트 연동 설정 ---
# =============================== 여기를 수정! ===============================
# Streamlit의 Secrets에서 서비스 계정 정보 가져오기
# Google Sheets와 Google Drive API를 모두 사용할 수 있도록 권한 범위(scopes)를 설정합니다.
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
# ==========================================================================

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scopes
)
client = gspread.authorize(creds)

# 연결할 구글 시트 이름
GOOGLE_SHEET_NAME = "Goremi Price DB"
# 구글 시트 열기
try:
    spreadsheet = client.open(GOOGLE_SHEET_NAME)
    worksheet = spreadsheet.worksheet("confirmed_prices") # 시트 이름 지정
    st.sidebar.success(f"'{GOOGLE_SHEET_NAME}' DB에 연결되었습니다.")
except gspread.exceptions.SpreadsheetNotFound:
    st.error(f"'{GOOGLE_SHEET_NAME}'라는 이름의 구글 시트를 찾을 수 없습니다. 시트가 존재하는지, 서비스 계정에 공유되었는지 확인해주세요.")
    st.stop()
except gspread.exceptions.WorksheetNotFound:
    st.error("'confirmed_prices' 워크시트를 찾을 수 없습니다. 구글 시트에 해당 이름의 시트를 생성해주세요.")
    st.stop()
except Exception as e:
    st.error(f"DB 연결 중 예상치 못한 오류가 발생했습니다: {e}")
    st.stop()


# --- 데이터 로딩 함수 ---
@st.cache_data(ttl=600) # 10분마다 데이터 갱신
def load_data_from_gsheet(worksheet):
    """구글 시트에서 데이터를 DataFrame으로 로드합니다."""
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    # 데이터가 없을 경우를 대비하여 필수 컬럼을 포함한 빈 DataFrame 생성
    required_cols = ['confirm_date', 'product_name', 'customer_name', 'cost_price', 'standard_price', 'supply_price', 'margin_rate', 'total_fee_rate']
    if df.empty:
        return pd.DataFrame(columns=required_cols).fillna(0)
    # 누락된 컬럼이 있다면 0으로 채워서 추가
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0
    return df.fillna(0)

@st.cache_data
def load_local_data(file_path):
    """로컬 CSV 파일(제품, 거래처 정보)을 로드합니다."""
    if os.path.exists(file_path):
        return pd.read_csv(file_path).fillna(0)
    return pd.DataFrame()

# --- 데이터 파일 경로 ---
PRODUCTS_FILE = 'products.csv'
CUSTOMERS_FILE = 'customers.csv'

# --- 데이터 로드 ---
products_df = load_local_data(PRODUCTS_FILE)
customers_df = load_local_data(CUSTOMERS_FILE)
# 구글 시트에서 확정 가격 데이터 로드
confirmed_prices_df = load_data_from_gsheet(worksheet)


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
goremi_target_margin = st.sidebar.slider("goremi 목표 마진율 (%)", 1, 100, 30) if '원가 기반' in calculation_method else 0

# --- 메인 대시보드 ---
st.title("🐟 goremi 가격 결정 및 관리 시스템")

tab_simulate, tab_db_view = st.tabs(["가격 시뮬레이션 & 확정", "전체 확정 DB 조회"])


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

    # --- 결과 및 확정 버튼 ---
    st.header("2. 시뮬레이션 결과")
    res_col1, res_col2, res_col3 = st.columns(3)
    res_col1.metric("계산된 최종 공급단가", f"{supply_price:,.0f} 원")
    res_col2.metric("예상 마진율", f"{goremi_margin:.1f} %")
    res_col3.metric("총 비용률", f"{total_deduction_rate * 100:.1f} %")

    st.markdown("---")
    if st.button("✅ 이 가격으로 확정하고 DB에 자동 저장", type="primary", use_container_width=True):
        new_price_entry = {
            "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "product_name": selected_product_name,
            "customer_name": selected_customer_name,
            "cost_price": cost_price,
            "standard_price": standard_price,
            "supply_price": round(supply_price),
            "margin_rate": round(goremi_margin, 2),
            "total_fee_rate": round(total_deduction_rate * 100, 2)
        }
        
        # 새로운 데이터를 기존 DB와 통합 (중복 시 최신 데이터로 덮어쓰기)
        new_df = pd.DataFrame([new_price_entry])
        # 인덱스를 기준으로 데이터를 합치기 위해 기존 데이터의 인덱스를 재설정
        updated_df = pd.concat([confirmed_prices_df.set_index(['product_name', 'customer_name']), new_df.set_index(['product_name', 'customer_name'])])
        # 중복된 인덱스 중 마지막 것만 남기고, 인덱스를 다시 컬럼으로 변환
        final_df = updated_df[~updated_df.index.duplicated(keep='last')].reset_index()

        # 구글 시트에 데이터 업데이트
        try:
            with st.spinner("DB에 데이터를 저장하는 중입니다..."):
                # DataFrame을 구글 시트에 쓰기 (기존 내용 전체 덮어쓰기)
                set_with_dataframe(worksheet, final_df)
            st.success("가격이 확정되어 DB에 성공적으로 저장되었습니다! '전체 확정 DB 조회' 탭에서 확인하세요.")
            # 캐시된 데이터 삭제하여 다음 로드 시 최신 정보 반영
            st.cache_data.clear()
        except Exception as e:
            st.error(f"DB 저장 중 오류가 발생했습니다: {e}")

# ==================== DB 조회 탭 ====================
with tab_db_view:
    st.header("전체 확정 가격 DB (읽기 전용)")
    st.info("이 데이터는 'Goremi Price DB' 구글 시트에서 직접 가져온 최신 정보입니다.")
    
    if st.button("🔄 DB 새로고침"):
        st.cache_data.clear()
        st.rerun()

    st.dataframe(confirmed_prices_df, use_container_width=True)
