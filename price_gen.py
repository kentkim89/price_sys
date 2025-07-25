import streamlit as st
import pandas as pd
import os
from datetime import datetime
from github import Github, GithubException

# --- 1. 페이지 설정 및 기본 정보 ---
st.set_page_config(page_title="고래미 가격결정 시스템", page_icon="🐟", layout="wide")


# --- 2. 파일 경로 및 GitHub 저장소 정보 ---
# ⚠️ 중요: 아래 REPO_NAME을 본인의 GitHub 유저이름/저장소이름으로 반드시 수정하세요!
# 예시: "goraemi-kim/goraemi-pricing-app"
REPO_NAME = "kentkim89/price_sys" 
PRODUCTS_FILE = 'products.csv'
CUSTOMERS_FILE = 'customers.csv'
CONFIRMED_PRICES_FILE = 'confirmed_prices.csv'


# --- 3. GitHub 파일 업데이트/생성 함수 ---
def update_github_file(file_path, df_to_save):
    """GitHub에 있는 CSV 파일을 업데이트하거나 새로 생성합니다."""
    try:
        # Streamlit secrets에서 토큰 가져오기 (사전에 Streamlit Cloud에 등록해야 함)
        token = st.secrets["github_token"]
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        
        # 데이터프레임을 CSV 형식의 문자열로 변환
        csv_content = df_to_save.to_csv(index=False)
        
        # 파일이 이미 있는지 확인하고, 있으면 업데이트, 없으면 생성
        try:
            contents = repo.get_contents(file_path, ref="main")
            repo.update_file(contents.path, f"Update {file_path}", csv_content, contents.sha, branch="main")
            st.success(f"✅ DB 파일(`{file_path}`)이 GitHub에 성공적으로 업데이트되었습니다!")
        except GithubException: # 파일이 존재하지 않을 때 발생하는 예외
            repo.create_file(file_path, f"Create {file_path}", csv_content, branch="main")
            st.success(f"✅ DB 파일(`{file_path}`)을 GitHub에 성공적으로 생성했습니다!")

    except Exception as e:
        st.error(f"DB 업데이트 중 오류가 발생했습니다: {e}")
        st.error("GitHub 토큰과 저장소 이름을 정확히 설정했는지, 토큰에 repo 권한이 있는지 확인해주세요.")


# --- 4. 데이터 로딩 함수 ---
@st.cache_data
def load_data(file_path):
    """CSV 파일을 로드합니다. 파일이 없으면 빈 데이터프레임을 반환합니다."""
    if os.path.exists(file_path):
        return pd.read_csv(file_path).fillna(0)
    return pd.DataFrame()


# --- 5. 데이터 로드 및 세션 초기화 ---
products_df = load_data(PRODUCTS_FILE)
customers_df = load_data(CUSTOMERS_FILE)
confirmed_prices_df = load_data(CONFIRMED_PRICES_FILE) # NameError 해결: 변수 사용 전에 정의

# 세션 상태 초기화 (앱 실행 시 한 번만 실행)
if 'confirmed_list' not in st.session_state:
    st.session_state.confirmed_list = []

# 필수 파일 확인
if products_df.empty or customers_df.empty:
    st.error(f"`{PRODUCTS_FILE}` 또는 `{CUSTOMERS_FILE}` 파일을 찾을 수 없습니다. GitHub 저장소에 파일이 올바르게 업로드되었는지 확인해주세요.")
    st.stop()
    
# 채널 정보 정의
CHANNEL_INFO = {
    "일반 도매": {"description": "용차/택배 -> 거래선 물류창고 입고", "cost_items": ["운송비 (%)"]},
    "쿠팡 로켓프레시": {"description": "용차 -> 쿠팡 물류창고 입고", "cost_items": ["입고 운송비 (%)", "쿠팡 매입수수료 (%)"]},
    "마트": {"description": "3PL -> 지역별 물류창고 -> 점포 (복합 물류비)", "cost_items": ["3PL 기본료 (%)", "지역 간선비 (%)", "점포 배송비 (%)"]},
    "프랜차이즈 본사": {"description": "용차 -> 지정 물류창고 입고", "cost_items": ["지정창고 입고비 (%)"]},
    "케이터링사": {"description": "3PL -> 지역별 물류창고 (복합 수수료)", "cost_items": ["3PL 기본료 (%)", "피킹 수수료 (%)", "Zone 분류 수수료 (%)"]},
    "기타 채널": {"description": "기본 배송 프로세스", "cost_items": ["기본 물류비 (%)"]}
}


# --- 6. 사이드바 UI 및 입력 로직 ---
st.sidebar.title("🐟 고래미 가격결정 시스템")

selected_product_name = st.sidebar.selectbox("1. 분석할 제품 선택", products_df['product_name'])
selected_product = products_df[products_df['product_name'] == selected_product_name].iloc[0]
selected_customer_name = st.sidebar.selectbox("2. 거래처 선택", customers_df['customer_name'])
selected_customer = customers_df[customers_df['customer_name'] == selected_customer_name].iloc[0]

# 제품이나 거래처가 바뀌면 세션 상태 초기화
if 'current_customer' not in st.session_state or st.session_state.current_customer != selected_customer_name or st.session_state.current_product != selected_product_name:
    st.session_state.current_product = selected_product_name
    st.session_state.current_customer = selected_customer_name
    st.session_state.editable_cost = selected_product['cost_price']
    st.session_state.editable_standard_price = selected_product['standard_price']
    st.session_state.conditions = {col: selected_customer[col] for col in customers_df.columns if col not in ['customer_name', 'channel_type']}

st.sidebar.markdown("---")
st.sidebar.subheader("3. 기준 가격 시뮬레이션")
st.session_state.editable_cost = st.sidebar.number_input("제품 원가", value=float(st.session_state.editable_cost))
st.session_state.editable_standard_price = st.sidebar.number_input("표준 공급가", value=float(st.session_state.editable_standard_price))
if st.sidebar.button("🔄 가격 복원"):
    st.session_state.editable_cost = selected_product['cost_price']
    st.session_state.editable_standard_price = selected_product['standard_price']
    st.rerun()

st.sidebar.markdown("---")
calculation_method = st.sidebar.radio("4. 계산 기준 선택", ('원가 기반 계산', '표준 공급가 기반 계산'))
goraemi_target_margin = st.sidebar.slider("고래미 목표 마진율 (%)", 1, 100, 30) if '원가 기반' in calculation_method else 0


# --- 7. 메인 대시보드 UI 및 계산 로직 ---
st.title("📊 단가 분석 및 가격 결정")
st.markdown(f"**제품:** `{selected_product_name}` | **거래처:** `{selected_customer_name}`")

st.header("1. 거래처 계약 조건 (수정 가능)")
channel_type = selected_customer['channel_type']
info = CHANNEL_INFO.get(channel_type, {"description": "정의되지 않음", "cost_items": []})
st.info(f"**채널 유형:** {channel_type} | **배송 방법:** {info['description']}")
col1, col2 = st.columns(2)
with col1: st.session_state.conditions['vendor_fee'] = st.number_input("벤더 수수료 (%)", value=st.session_state.conditions.get('vendor_fee', 0.0))
with col2: st.session_state.conditions['discount'] = st.number_input("프로모션 할인율 (%)", value=st.session_state.conditions.get('discount', 0.0))
st.markdown("---")
st.subheader("채널별 특수 비용")
cost_items = info.get('cost_items', [])
if cost_items:
    cost_item_cols = st.columns(len(cost_items))
    for i, item in enumerate(cost_items):
        with cost_item_cols[i]: st.session_state.conditions[item] = st.number_input(item, value=st.session_state.conditions.get(item, 0.0))

total_deduction_rate = (st.session_state.conditions.get('vendor_fee', 0.0) + st.session_state.conditions.get('discount', 0.0) + sum(st.session_state.conditions.get(item, 0.0) for item in cost_items)) / 100
cost_price = st.session_state.editable_cost
standard_price = st.session_state.editable_standard_price
supply_price, goraemi_margin = 0.0, 0.0

if '원가 기반' in calculation_method:
    if (1 - goraemi_target_margin / 100) > 0 and (1 - total_deduction_rate) > 0:
        price_for_margin = cost_price / (1 - goraemi_target_margin / 100)
        supply_price = price_for_margin / (1 - total_deduction_rate)
        net_received = supply_price * (1 - total_deduction_rate)
        if net_received > 0: goraemi_margin = (net_received - cost_price) / net_received * 100
else:
    supply_price = standard_price
    net_received = supply_price * (1 - total_deduction_rate)
    if net_received > 0 and cost_price > 0: goraemi_margin = (net_received - cost_price) / net_received * 100

# --- 8. 가격 확정 및 DB 저장 섹션 ---
st.header("2. 시뮬레이션 결과 및 가격 확정")
res_col1, res_col2, res_col3 = st.columns(3)
res_col1.metric("계산된 최종 공급단가", f"{supply_price:,.0f} 원")
res_col2.metric("예상 마진율", f"{goraemi_margin:.1f} %")
res_col3.metric("총 비용률", f"{total_deduction_rate * 100:.1f} %")

st.markdown("---")
if st.button("✅ 이 가격으로 확정하기", type="primary"):
    new_price_entry = {
        "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"), "product_name": selected_product_name,
        "customer_name": selected_customer_name, "cost_price": cost_price, "standard_price": standard_price,
        "supply_price": round(supply_price), "margin_rate": round(goraemi_margin, 2),
        "total_fee_rate": round(total_deduction_rate * 100, 2)
    }
    st.session_state.confirmed_list.append(new_price_entry)
    st.success(f"**[{selected_customer_name}]**의 **[{selected_product_name}]** 가격이 아래 '확정 목록'에 추가되었습니다.")

st.header("3. 가격 확정 목록 및 DB 저장")
tab1, tab2 = st.tabs(["이번 세션에서 확정한 목록", "기존 확정 가격 DB"])

with tab1:
    st.subheader("이번 세션에서 확정한 목록")
    if not st.session_state.get('confirmed_list', []):
        st.info("아직 이번 세션에서 확정한 가격이 없습니다.")
    else:
        session_df = pd.DataFrame(st.session_state.confirmed_list)
        st.dataframe(session_df, use_container_width=True)
        st.markdown("---")
        st.warning("**중요:** 아래 버튼을 누르면 이번 세션의 작업 내용이 GitHub DB에 영구적으로 저장됩니다.")
        
        if st.button("💾 이번 세션의 확정 목록을 DB에 저장하기", type="primary"):
            # 기존 DB와 세션 목록을 병합하고, 중복은 최신 것으로 유지
            combined_df = pd.concat([confirmed_prices_df, session_df]).drop_duplicates(
                subset=['product_name', 'customer_name'], keep='last'
            )
            # GitHub 파일 업데이트 함수 호출
            update_github_file(CONFIRMED_PRICES_FILE, combined_df)
            # 성공적으로 저장 후 세션 목록 비우기
            st.session_state.confirmed_list = []
            st.info("저장이 완료되었습니다. 잠시 후 새로고침하여 최신 DB를 확인하세요.")
            # st.rerun() # 필요시 주석 해제하여 즉시 새로고침

with tab2:
    st.subheader(f"기존 확정 가격 DB (`{CONFIRMED_PRICES_FILE}`)")
    if confirmed_prices_df.empty:
        st.info("기존에 저장된 확정 가격 DB가 없습니다. 가격을 확정하고 저장하면 이곳에 표시됩니다.")
    else:
        st.dataframe(confirmed_prices_df, use_container_width=True)
