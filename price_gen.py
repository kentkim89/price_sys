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
@st.cache_data(ttl=300)
def load_and_prep_data():
    client = get_gsheet_client()
    # 제품 DB 로드
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

    # 거래처 DB 로드
    clients_ws = client.open(CLIENT_DB_NAME).worksheet("confirmed_clients")
    clients_df = pd.DataFrame(clients_ws.get_all_records())
    numeric_client_cols = [col for col in clients_df.columns if col not in ['customer_name', 'channel_type']]

    # ================== 여기가 최종 핵심 수정 부분 ==================
    # '%' 기호를 제거하는 로직을 추가하여 숫자 변환이 실패하지 않도록 합니다.
    for col in numeric_client_cols:
        clients_df[col] = clients_df[col].astype(str)          # 1. 컬럼을 문자로 변환
        clients_df[col] = clients_df[col].str.replace('%', '') # 2. '%' 기호 제거
        clients_df[col] = clients_df[col].str.replace(',', '') # 3. 쉼표 제거
        clients_df[col] = pd.to_numeric(clients_df[col], errors='coerce') # 4. 숫자로 변환
    # ==============================================================
    clients_df = clients_df.fillna(0)

    # 가격 DB 로드
    prices_ws = client.open(PRICE_DB_NAME).worksheet("confirmed_prices")
    prices_df = pd.DataFrame(prices_ws.get_all_records())
    return products_df, clients_df, prices_df

def get_gsheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

# --- 메인 앱 실행 ---
try:
    products_df, customers_df, prices_df = load_and_prep_data()
except Exception as e:
    st.error(f"데이터베이스 로딩 중 오류가 발생했습니다: {e}")
    st.stop()

if not prices_df.empty and 'unique_name' not in prices_df.columns:
    st.error("🚨 데이터베이스 구조 업데이트 필요!")
    st.warning("`Goremi Price DB`의 `confirmed_prices` 시트를 삭제하고, 앱에서 다시 설정해주세요.")
    st.stop()

# --- UI 탭 정의 ---
st.title("🐟 goremi 가격 관리 시스템")
tab_simulate, tab_matrix, tab_db_view = st.tabs(["가격 시뮬레이션", "거래처별 품목 관리", "DB 원본 조회"])

# ==================== 가격 시뮬레이션 탭 ====================
with tab_simulate:
    st.header("거래처별 품목 가격 일괄 시뮬레이션")
    if customers_df.empty:
        st.warning("등록된 거래처가 없습니다.")
    else:
        selected_customer_sim = st.selectbox("가격을 조정할 거래처를 선택하세요", customers_df['customer_name'].unique(), key="sim_customer")

        active_prices_df = pd.DataFrame()
        if not prices_df.empty:
            active_prices_df = prices_df[prices_df['customer_name'] == selected_customer_sim].copy()

        if active_prices_df.empty:
            st.warning(f"'{selected_customer_sim}'이(가) 취급하는 품목이 없습니다. '거래처별 품목 관리' 탭에서 먼저 설정해주세요.")
        else:
            prices_to_merge = active_prices_df[['unique_name', 'supply_price']]
            products_to_merge = products_df[['unique_name', 'stand_cost', 'stand_price_ea', 'box_ea']]
            sim_df = pd.merge(prices_to_merge, products_to_merge, on='unique_name', how='inner')

            original_item_count = len(active_prices_df)
            merged_item_count = len(sim_df)
            if original_item_count > merged_item_count:
                st.error("데이터 불일치 경고!")
                merged_items = set(sim_df['unique_name'])
                all_items = set(active_prices_df['unique_name'])
                missing_items = all_items - merged_items
                st.warning("아래 품목은 '제품 마스터 DB'에 없어 시뮬레이션에서 제외되었습니다.")
                st.dataframe({"제외된 품목": list(missing_items)})

            if sim_df.empty:
                st.warning("시뮬레이션할 유효한 품목이 없습니다.")
            else:
                st.markdown("---")
                st.subheader(f"Step 1: '{selected_customer_sim}'의 공급 단가 수정")
                sim_df['supply_price'] = pd.to_numeric(sim_df['supply_price'], errors='coerce').fillna(0)
                edited_df = st.data_editor(
                    sim_df[['unique_name', 'stand_cost', 'supply_price']],
                    column_config={
                        "unique_name": st.column_config.TextColumn("품목명", disabled=True),
                        "stand_cost": st.column_config.NumberColumn("제품 원가", format="%d원", disabled=True),
                        "supply_price": st.column_config.NumberColumn("최종 공급 단가", format="%d원", required=True),
                    },
                    hide_index=True, use_container_width=True, key="price_editor"
                )

                st.markdown("---")
                st.subheader("Step 2: 실시간 손익 분석 결과 확인")
                customer_info = customers_df[customers_df['customer_name'] == selected_customer_sim].iloc[0]

                # 1. 거래처의 '지역 간선비(%)' 비율 값을 가져옴 (없으면 0)
                #    ※ 시트의 실제 컬럼명과 정확히 일치해야 합니다.
                trunk_fee_rate = float(customer_info.get('지역 간선비 (%)', 0))

                # 2. '지역 간선비(%)' 적용 여부를 결정할 체크박스 생성
                apply_trunk_fee = False
                if trunk_fee_rate > 0:
                    apply_trunk_fee = st.checkbox(f"**지역 간선비 적용 (비율: {trunk_fee_rate:,.1f}%)**", key="apply_trunk_fee")

                # '기타 수수료' 등 간선비 외의 공제 항목 계산
                numeric_cols = [col for col in customer_info.index if col not in ['customer_name', 'channel_type', '지역 간선비 (%)']]
                conditions = {col: float(customer_info.get(col, 0)) for col in numeric_cols}
                total_deduction_rate = sum(conditions.values()) / 100
                
                analysis_df = pd.merge(edited_df, products_df[['unique_name', 'stand_price_ea', 'box_ea']], on='unique_name', how='left')
                analysis_df['supply_price'] = pd.to_numeric(analysis_df['supply_price'], errors='coerce').fillna(0)
                analysis_df['stand_price_ea'] = pd.to_numeric(analysis_df['stand_price_ea'], errors='coerce').fillna(0)
                
                analysis_df['실정산액'] = analysis_df['supply_price'] * (1 - total_deduction_rate)

                # 3. 체크박스 상태에 따라 품목별 간선비 금액을 계산
                if apply_trunk_fee:
                    analysis_df['적용된 간선비'] = analysis_df['supply_price'] * (trunk_fee_rate / 100)
                else:
                    analysis_df['적용된 간선비'] = 0
                
                # 4. '개당 이익' 계산 시, '적용된 간선비'를 추가로 차감
                analysis_df['개당 이익'] = analysis_df['실정산액'] - analysis_df['stand_cost'] - analysis_df['적용된 간선비']

                def format_difference(row):
                    difference = row['실정산액'] - row['stand_price_ea']
                    if row['stand_price_ea'] > 0:
                        percentage = (difference / row['stand_price_ea']) * 100
                        return f"{difference:+,.0f}원 ({percentage:+.1f}%)"
                    else:
                        return f"{difference:+,.0f}원 (N/A)"

                analysis_df['기준가 대비 차액'] = analysis_df.apply(format_difference, axis=1)
                analysis_df['마진율 (%)'] = analysis_df.apply(lambda row: (row['개당 이익'] / row['실정산액'] * 100) if row['실정산액'] > 0 else 0, axis=1)
                analysis_df['박스당 이익'] = analysis_df['개당 이익'] * analysis_df['box_ea']

                display_cols = [
                    'unique_name', 'stand_price_ea', 'supply_price', '실정산액', '기준가 대비 차액',
                    '마진율 (%)', '개당 이익', '박스당 이익'
                ]
                st.dataframe(
                    analysis_df[display_cols],
                    column_config={
                        "unique_name": "품목명",
                        "stand_price_ea": st.column_config.NumberColumn("기준 도매가", format="%d원"),
                        "supply_price": st.column_config.NumberColumn("공급 단가", format="%d원"),
                        "실정산액": st.column_config.NumberColumn("실정산액", format="%d원"),
                        "기준가 대비 차액": st.column_config.TextColumn("기준가 대비 차액"),
                        "마진율 (%)": st.column_config.NumberColumn("마진율", format="%.1f%%"),
                        "개당 이익": st.column_config.NumberColumn("개당 이익", format="%d원"),
                        "박스당 이익": st.column_config.NumberColumn("박스당 이익", format="%d원"),
                    },
                    hide_index=True, use_container_width=True
                )

                st.markdown("---")
                if st.button(f"✅ '{selected_customer_sim}'의 모든 가격 변경사항 DB에 저장", key="save_all_sim", type="primary"):
                    with st.spinner("DB에 가격 정보를 업데이트합니다..."):
                        _, _, current_total_prices = load_and_prep_data()
                        other_customer_prices = current_total_prices[current_total_prices['customer_name'] != selected_customer_sim].copy()
                        updated_data_to_save = analysis_df.rename(columns={
                            '마진율 (%)': 'margin_rate',
                            '개당 이익': 'profit_per_ea',
                            '박스당 이익': 'profit_per_box'
                        })
                        updated_data_to_save['customer_name'] = selected_customer_sim
                        updated_data_to_save['confirm_date'] = datetime.now().strftime("%Y-%m-%d %H:%M")

                        if not current_total_prices.empty:
                            save_columns = list(current_total_prices.columns)
                            final_save_df = updated_data_to_save[[col for col in save_columns if col in updated_data_to_save.columns]]
                        else:
                            final_save_df = updated_data_to_save

                        final_prices_df = pd.concat([other_customer_prices, final_save_df], ignore_index=True)
                        price_sheet = get_gsheet_client().open(PRICE_DB_NAME).worksheet("confirmed_prices")
                        set_with_dataframe(price_sheet, final_prices_df, allow_formulas=False)

                        st.success(f"'{selected_customer_sim}'의 가격 정보가 성공적으로 업데이트되었습니다.")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()

# ==================== 거래처별 품목 관리 탭 ====================
with tab_matrix:
    st.header("거래처별 취급 품목 설정")
    if customers_df.empty:
        st.warning("등록된 거래처가 없습니다.")
    else:
        manage_customer = st.selectbox("관리할 거래처를 선택하세요", customers_df['customer_name'].unique(), key="manage_customer")
        if manage_customer:
            st.markdown(f"#### 📄 **{manage_customer}** 의 취급 품목 목록")
            active_products_set = set()
            if not prices_df.empty and 'unique_name' in prices_df.columns:
                active_products_set = set(prices_df[prices_df['customer_name'] == manage_customer]['unique_name'])

            checkbox_states = {}
            for _, product in products_df.iterrows():
                is_checked = product['unique_name'] in active_products_set
                checkbox_states[product['unique_name']] = st.checkbox(
                    product['unique_name'], value=is_checked, key=f"check_{manage_customer}_{product['unique_name']}"
                )

            if st.button(f"✅ **{manage_customer}** 의 품목 정보 저장", use_container_width=True, type="primary"):
                with st.spinner("DB를 업데이트하는 중입니다..."):
                    _, _, current_prices = load_and_prep_data()
                    other_customer_prices = current_prices[current_prices['customer_name'] != manage_customer].copy()
                    newly_active_products = {name for name, checked in checkbox_states.items() if checked}
                    reconstructed_entries = []
                    for unique_name in newly_active_products:
                        existing_entry = current_prices[
                            (current_prices['customer_name'] == manage_customer) &
                            (current_prices['unique_name'] == unique_name)
                        ]
                        if not existing_entry.empty:
                            reconstructed_entries.append(existing_entry.iloc[0].to_dict())
                        else:
                            product_info = products_df.loc[products_df['unique_name'] == unique_name].iloc[0]
                            reconstructed_entries.append({
                                "confirm_date": datetime.now().strftime("%Y-%m-%d %H:%M"), "unique_name": unique_name, "customer_name": manage_customer,
                                "stand_cost": product_info['stand_cost'], "supply_price": product_info['stand_price_ea'],
                                "margin_rate": 0, "profit_per_ea": 0, "profit_per_box": 0
                            })

                    reconstructed_df = pd.DataFrame(reconstructed_entries)
                    final_df = pd.concat([other_customer_prices, reconstructed_df], ignore_index=True)
                    price_sheet = get_gsheet_client().open(PRICE_DB_NAME).worksheet("confirmed_prices")
                    set_with_dataframe(price_sheet, final_df, allow_formulas=False)

                    st.success(f"'{manage_customer}'의 취급 품목 정보가 DB에 성공적으로 업데이트되었습니다!")
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
