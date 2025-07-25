import streamlit as st
import pandas as pd
import os

# --- 페이지 설정 ---
st.set_page_config(
    page_title="고래미 단가 관리 시스템",
    page_icon="🐟",
    layout="wide"
)

# --- 데이터 로딩 함수 ---
@st.cache_data
def load_data(file_path):
    """CSV 파일에서 제품 데이터를 로드합니다."""
    if os.path.exists(file_path):
        return pd.read_csv(file_path)
    else:
        sample_data = {
            'sku_code': ['SKU-001'],
            'product_name': ['제품 샘플 (products.csv 파일 필요)'],
            'cost_price': [5000],
            'standard_price': [7000]
        }
        return pd.DataFrame(sample_data)

# --- 채널별 정보 및 비용 구조 정의 ---
# 나중에 채널이 추가되면 이 딕셔너리에 추가하기만 하면 됩니다.
CHANNEL_INFO = {
    "일반 도매": {
        "description": "용차배송 또는 택배발송 -> 거래선 물류창고 입고",
        "cost_items": ["운송비 (%)"] # 간단한 비용 구조
    },
    "쿠팡 로켓프레시": {
        "description": "용차배송 -> 쿠팡 물류창고 입고",
        "cost_items": ["입고 운송비 (%)", "쿠팡 매입수수료 (%)"]
    },
    "마트": {
        "description": "용차배송 -> 3PL 물류창고 -> 각 지역별 물류창고 (지역별/점포별 물류비 발생)",
        "cost_items": ["3PL 기본료 (%)", "지역 간선비 (%)", "점포 배송비 (%)"]
    },
    "프랜차이즈 본사": {
        "description": "용차배송 -> 지정 물류창고 입고",
        "cost_items": ["지정창고 입고비 (%)"]
    },
    "케이터링사": {
        "description": "용차배송 -> 3PL 물류창고 -> 각 지역별 물류창고 (복합 수수료 발생 가능)",
        "cost_items": ["3PL 기본료 (%)", "피킹 수수료 (%)", "Zone 분류 수수료 (%)"]
    },
    # 나중에 채널이 추가될 경우를 대비한 예시
    "기타 채널": {
        "description": "기본적인 배송 프로세스",
        "cost_items": ["기본 물류비 (%)"]
    }
}

# 채널 목록은 위에서 정의한 키 값으로 자동 생성
CHANNELS = list(CHANNEL_INFO.keys())

# 주요 케이터링사 예상 이익률 (기본값)
B2B_MARGINS = { "현대그린푸드": 3.0, "삼성웰스토리": 4.5, "아워홈": 2.5, "CJ프레시웨이": 2.0 }
# 케이터링사 채널명에 아래 키워드가 포함되어 있는지 확인하기 위함
CATERING_KEYWORDS = ["현대", "웰스토리", "푸디스트", "아워홈", "CJ"]


# --- 데이터 로드 ---
products_df = load_data('products.csv')

# --- 사이드바 ---
st.sidebar.title("🐟 고래미 단가 시뮬레이터")
product_list = products_df['product_name'].tolist()
selected_product_name = st.sidebar.selectbox("1. 분석할 제품을 선택하세요.", product_list)
selected_product = products_df[products_df['product_name'] == selected_product_name].iloc[0]

st.sidebar.markdown("---")
st.sidebar.subheader("제품 기본 정보")
st.sidebar.metric(label="제품 원가 (VAT 별도)", value=f"{selected_product['cost_price']:,} 원")
st.sidebar.metric(label="표준 공급가 (VAT 별도)", value=f"{selected_product['standard_price']:,} 원")

st.sidebar.markdown("---")
calculation_method = st.sidebar.radio(
    "2. 계산 기준을 선택하세요.",
    ('원가 기반 계산 (목표 마진율 중심)', '표준 공급가 기반 계산 (할인율 중심)'),
    help="""
    - **원가 기반**: 설정한 목표 마진을 달성하기 위해 공급가를 얼마로 해야 할지 계산합니다.
    - **표준가 기반**: 정해진 표준가에서 각 채널의 비용을 차감하여 실제 마진이 얼마인지 계산합니다.
    """
)

goraemi_target_margin = 0
if '원가 기반' in calculation_method:
    goraemi_target_margin = st.sidebar.slider(
        "고래미 목표 마진율 (%)", min_value=1, max_value=100, value=30, step=1
    )

# --- 메인 대시보드 ---
st.title("📊 채널별 단가 분석 대시보드")
st.markdown(f"**선택된 제품:** `{selected_product_name}` | **계산 기준:** `{calculation_method.split(' ')[0]}`")

st.header("1. 채널별 조건 입력")

channel_inputs = {}
# 2개 컬럼으로 나누어 채널 표시
col1, col2 = st.columns(2)
columns = [col1, col2]

for i, channel_name in enumerate(CHANNELS):
    with columns[i % 2]:
        with st.expander(f"⚙️ {channel_name} 조건 설정"):
            # 채널 정보에서 설명과 비용 항목 가져오기
            info = CHANNEL_INFO.get(channel_name, {"description": "정의되지 않은 채널입니다.", "cost_items": []})
            
            st.info(f"**배송 방법:** {info['description']}")
            
            # 공통 비용 항목
            vendor_fee = st.number_input(f"벤더(유통) 수수료 (%)", min_value=0.0, value=0.0, step=0.1, key=f"vendor_{channel_name}")
            discount = st.number_input(f"프로모션 할인율 (%)", min_value=0.0, value=0.0, step=0.1, key=f"discount_{channel_name}")
            
            # 채널별 동적 비용 항목
            dynamic_costs = {}
            for cost_item in info['cost_items']:
                dynamic_costs[cost_item] = st.number_input(cost_item, min_value=0.0, value=0.0, step=0.1, key=f"{channel_name}_{cost_item}")

            channel_inputs[channel_name] = {
                "vendor_fee": vendor_fee,
                "discount": discount,
                "dynamic_costs": dynamic_costs
            }

# --- 계산 로직 및 결과 표시 ---
st.header("2. 시뮬레이션 결과 요약")

results_data = []
cost_price = selected_product['cost_price']
standard_price = selected_product['standard_price']

for channel, inputs in channel_inputs.items():
    # 모든 비용 항목의 합계 계산
    total_dynamic_cost_rate = sum(inputs['dynamic_costs'].values())
    total_deduction_rate = (inputs['vendor_fee'] + inputs['discount'] + total_dynamic_cost_rate) / 100
    
    supply_price = 0
    goraemi_margin = 0
    
    if '원가 기반' in calculation_method:
        target_margin_rate = goraemi_target_margin / 100
        if (1 - target_margin_rate) > 0 and (1 - total_deduction_rate) > 0:
            price_for_margin = cost_price / (1 - target_margin_rate)
            supply_price = price_for_margin / (1 - total_deduction_rate)
            net_received = supply_price * (1 - total_deduction_rate)
            if net_received > 0:
                goraemi_margin = (net_received - cost_price) / net_received * 100
            else:
                goraemi_margin = -100
    else: # 표준 공급가 기반
        supply_price = standard_price
        net_received = supply_price * (1 - total_deduction_rate)
        if net_received > 0:
             goraemi_margin = (net_received - cost_price) / net_received * 100
        else:
             goraemi_margin = ((net_received - cost_price) / cost_price) * 100 if cost_price > 0 else 0

    results_data.append({
        "채널명": channel,
        "공급단가 (VAT 별도)": supply_price,
        "고래미 실현 마진율 (%)": goraemi_margin,
        "총 비용률 (%)": total_deduction_rate * 100
    })

results_df = pd.DataFrame(results_data)

st.dataframe(results_df.style.format({
    "공급단가 (VAT 별도)": "{:,.0f} 원",
    "고래미 실현 마진율 (%)": "{:.1f}%",
    "총 비용률 (%)": "{:.1f}%"
}).highlight_max(subset=['고래미 실현 마진율 (%)'], color='lightgreen').highlight_min(subset=['고래미 실현 마진율 (%)'], color='#ffcccb'),
use_container_width=True)


# --- 최종 소비자가 예측 ---
st.header("3. 주요 케이터링사 최종 소비자가 예측")

# 예측 가능한 채널 목록 (채널명에 케이터링 키워드가 포함된 경우)
predictable_channels = [ch for ch in CHANNELS if any(keyword in ch for keyword in CATERING_KEYWORDS + ["케이터링사"])]

predict_channel = st.selectbox(
    "분석할 케이터링 채널을 선택하세요.",
    predictable_channels
)

if predict_channel and not results_df[results_df['채널명'] == predict_channel].empty:
    goraemi_supply_price = results_df[results_df['채널명'] == predict_channel]['공급단가 (VAT 별도)'].iloc[0]
    
    # 케이터링사 이름으로 기본 마진율 찾아오기 (없으면 5.0)
    default_margin = 5.0
    for name, margin in B2B_MARGINS.items():
        if name in predict_channel:
            default_margin = margin
            break

    caterer_margin = st.slider(
        f"{predict_channel}의 예상 이익률 (%)",
        min_value=0.0, max_value=50.0, value=default_margin, step=0.1
    )

    final_customer_price = 0
    if (1 - caterer_margin / 100) > 0:
        final_customer_price = goraemi_supply_price / (1 - caterer_margin / 100)

    st.markdown("#### **가격 구조 분석**")
    col1, col2, col3 = st.columns(3)
    col1.metric(label="고래미 공급가", value=f"{goraemi_supply_price:,.0f} 원")
    col2.metric(label=f"{predict_channel} 마진", value=f"{caterer_margin:.1f}%")
    col3.metric(label="예상 최종 소비자가", value=f"{final_customer_price:,.0f} 원", help="단체급식 고객사 등 최종 고객에게 제공되는 추정 가격입니다.")

st.markdown("---")
st.info("ℹ️ 본 시뮬레이터의 모든 금액은 부가세 별도 기준이며, 채널별 특성을 반영한 동적 비용 항목을 기반으로 계산됩니다.")
