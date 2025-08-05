 +  import streamlit as st
         2 +  import pandas as pd
         3 +  from datetime import datetime
         4 +  import gspread
         5 +  from gspread_dataframe import set_with_dataframe
         6 +  from google.oauth2.service_account import
           + Credentials
         7 +  import time
         8 +
         9 +  # --- 페이지 설정 ---
        10 +  st.set_page_config(page_title="고래미 가격결정
           + 시스템", layout="wide")
        11 +
        12 +  # --- (설정) DB 정보 ---
        13 +  PRODUCT_DB_NAME = "Goremi Products DB"
        14 +  CLIENT_DB_NAME = "Goremi Clients DB"
        15 +  PRICE_DB_NAME = "Goremi Price DB"
        16 +
        17 +  # --- 구글 시트 연동 및 데이터 로딩 ---
        18 +  @st.cache_data(ttl=300)
        19 +  def load_and_prep_data():
        20 +      client = get_gsheet_client()
        21 +      # 제품 DB 로드
        22 +      products_ws =
           + client.open(PRODUCT_DB_NAME).worksheet("products")
        23 +      products_df =
           + pd.DataFrame(products_ws.get_all_records())
        24 +      products_df['unique_name'] = (
        25 +
     products_df['product_name_kr'].astype(str).
           + str.strip() + " (" +
        26 +
           + products_df['weight'].astype(str).str.strip() +
        27 +
           + products_df['ea_unit'].astype(str).str.strip() +
     ")"
        28 +      )
        29 +      for col in ['stand_cost', 'stand_price_ea',
           + 'box_ea']:
        30 +          products_df[col] = pd.to_numeric(
        31 +
           + products_df[col].astype(str).str.replace(',', '',
           + regex=False), errors='coerce'
        32 +          )
        33 +      products_df =
     products_df.fillna(0).sort_values
           + (by='unique_name').reset_index(drop=True)
        34 +
        35 +      # 거래처 DB 로드
        36 +      clients_ws =
     client.open(CLIENT_DB_NAME).worksh
           + eet("confirmed_clients")
        37 +      clients_df =
           + pd.DataFrame(clients_ws.get_all_records())
        38 +      numeric_client_cols = [col for col in
           + clients_df.columns if col not in ['customer_name',
           + 'channel_type']]
        39 +
        40 +      # '%' 기호를 포함한 데이터 클리닝
        41 +      for col in numeric_client_cols:
        42 +          clients_df[col] =
           + clients_df[col].astype(str)
        43 +          clients_df[col] =
           + clients_df[col].str.replace('%', '', regex=False)
        44 +          clients_df[col] =
           + clients_df[col].str.replace(',', '', regex=False)
        45 +          clients_df[col] =
           + pd.to_numeric(clients_df[col], errors='coerce')
        46 +      clients_df = clients_df.fillna(0)
        47 +
        48 +      # 가격 DB 로드
        49 +      prices_ws =
     client.open(PRICE_DB_NAME).workshee
           + t("confirmed_prices")
        50 +      prices_df =
           + pd.DataFrame(prices_ws.get_all_records())
        51 +      return products_df, clients_df, prices_df
        52 +
        53 +  def get_gsheet_client():
        54 +      scopes =
           + ["https://www.googleapis.com/auth/spreadsheets",
           + "https://www.googleapis.com/auth/drive"]
        55 +      creds =
     Credentials.from_service_account_info(s
           + t.secrets["gcp_service_account"], scopes=scopes)
        56 +      return gspread.authorize(creds)
        57 +
        58 +  # --- 메인 앱 실행 ---
        59 +  try:
        60 +      products_df, customers_df, prices_df =
           + load_and_prep_data()
        61 +  except Exception as e:
        62 +      st.error(f"데이터베이스 로딩 중 오류가
           + 발생했습니다: {e}")
        63 +      st.stop()
        64 +
        65 +  if not prices_df.empty and 'unique_name' not in
           + prices_df.columns:
        66 +      st.error("🚨 데이터베이스 구조 업데이트
     필요!")
        67 +      st.warning("`Goremi Price DB`의
           + `confirmed_prices` 시트를 삭제하고, 앱에서 다시
           + 설정해주세요.")
        68 +      st.stop()
        69 +
        70 +  # --- UI 탭 정의 ---
        71 +  st.title("🐟 goremi 가격 관리 시스템")
        72 +  tab_simulate, tab_matrix, tab_db_view =
           + st.tabs(["가격 시뮬레이션", "거래처별 품목 관리",
           + "DB 원본 조회"])
        73 +
        74 +  # ==================== 가격 시뮬레이션 탭
           + ====================
        75 +  with tab_simulate:
        76 +      st.header("거래처별 품목 가격 일괄
     시뮬레이션")
        77 +      if customers_df.empty:
        78 +          st.warning("등록된 거래처가 없습니다.")
        79 +      else:
        80 +          selected_customer_sim =
           + st.selectbox("가격을 조정할 거래처를 선택하세요",
           + customers_df['customer_name'].unique(),
           + key="sim_customer")
        81 +
        82 +          active_prices_df = pd.DataFrame()
        83 +          if not prices_df.empty:
        84 +              active_prices_df =
           + prices_df[prices_df['customer_name'] ==
           + selected_customer_sim].copy()
        85 +
        86 +          if active_prices_df.empty:
        87 +
           + st.warning(f"'{selected_customer_sim}'이(가)
           + 취급하는 품목이 없습니다. '거래처별 품목 관리'
           + 탭에서 먼저 설정해주세요.")
        88 +          else:
        89 +              prices_to_merge =
           + active_prices_df[['unique_name', 'supply_price']]
        90 +              products_to_merge =
           + products_df[['unique_name', 'stand_cost',
           + 'stand_price_ea', 'box_ea']]
        91 +              sim_df = pd.merge(prices_to_merge,
           + products_to_merge, on='unique_name', how='inner')
        92 +
        93 +              if sim_df.empty:
        94 +                  st.warning("시뮬레이션할 유효한
           + 품목이 없습니다.")
        95 +              else:
        96 +                  st.markdown("---")
        97 +                  st.subheader(f"Step 1:
           + '{selected_customer_sim}'의 공급 단가 수정")
        98 +
        99 +                  edited_df = st.data_editor(
       100 +                      sim_df,
       101 +                      column_config={
       102 +                          "unique_name":
           + st.column_config.TextColumn("품목명",
           + disabled=True),
       103 +                          "stand_cost":
           + st.column_config.NumberColumn("제품 원가",
           + format="%d원", disabled=True),
       104 +                          "supply_price":
           + st.column_config.NumberColumn("최종 공급 단가",
           + format="%d원", required=True),
       105 +                          "stand_price_ea": None,
           + "box_ea": None,
       106 +                      },
       107 +                      hide_index=True,
           + use_container_width=True,
       108 +
           + key=f"price_editor_{selected_customer_sim}"
       109 +                  )
       110 +
       111 +                  st.markdown("---")
       112 +                  st.subheader("Step 2: 실시간 손익
           + 분석 결과 확인")
       113 +                  customer_info =
           + customers_df[customers_df['customer_name'] ==
           + selected_customer_sim].iloc[0]
       114 +
       115 +                  trunk_fee_rate =
           + float(customer_info.get('지역 간선비 (%)', 0))
       116 +
       117 +                  apply_trunk_fee = False
       118 +                  if trunk_fee_rate > 0:
       119 +                      apply_trunk_fee =
           + st.checkbox(f"**지역 간선비 적용 (비율:
           + {trunk_fee_rate:,.1f}%)**",
           + key=f"apply_trunk_fee_{selected_customer_sim}")
       120 +
       121 +                  # ===============================
           + 여기가 핵심 수정 부분
           + ===============================
       122 +                  # 1. 기타 수수료율 계산
       123 +                  other_fee_cols = [col for col in
           + customer_info.index if col not in ['customer_name',
           + 'channel_type', '지역 간선비 (%)']]
       124 +                  other_fee_conditions = {col:
           + float(customer_info.get(col, 0)) for col in
           + other_fee_cols}
       125 +                  other_fee_rate =
           + sum(other_fee_conditions.values()) / 100
       126 +
       127 +                  # 2. 최종 공제율 계산 (기타
           + 수수료율 + 간선비율)
       128 +                  final_deduction_rate =
           + other_fee_rate
       129 +                  if apply_trunk_fee:
       130 +                      final_deduction_rate +=
           + (trunk_fee_rate / 100)
       131 +
       132 +                  # 3. 분석에 사용할 데이터프레임
           + 복사 및 타입 정리
       133 +                  analysis_df = edited_df.copy()
       134 +                  analysis_df['supply_price'] =
           + pd.to_numeric(analysis_df['supply_price'],
           + errors='coerce').fillna(0)
       135 +                  analysis_df['stand_price_ea'] =
           + pd.to_numeric(analysis_df['stand_price_ea'],
           + errors='coerce').fillna(0)
       136 +
       137 +                  # 4. 최종 공제율을 사용하여
           + '실정산액' 계산
       138 +                  analysis_df['실정산액'] =
           + analysis_df['supply_price'] * (1 -
           + final_deduction_rate)
       139 +
       140 +                  # 5. 이제 '개당 이익'은 올바르게
           + 계산된 '실정산액'에서 원가만 빼면 됨
       141 +                  analysis_df['개당 이익'] =
           + analysis_df['실정산액'] - analysis_df['stand_cost']
       142 +                  #
           +
     ====================================================
           + =====================================
       143 +
       144 +                  # 이하 다른 계산들은 자동으로
           + 올바르게 연동됨
       145 +                  def format_difference(row):
       146 +                      difference = row['실정산액'] -
           + row['stand_price_ea']
       147 +                      if row['stand_price_ea'] > 0:
       148 +                          percentage = (difference /
           + row['stand_price_ea']) * 100
       149 +                          return
           + f"{difference:+,.0f}원 ({percentage:+.1f}%)"
       150 +                      else:
       151 +                          return
           + f"{difference:+,.0f}원 (N/A)"
       152 +
       153 +                  analysis_df['기준가 대비 차액'] =
           + analysis_df.apply(format_difference, axis=1)
       154 +                  analysis_df['마진율 (%)'] =
           + analysis_df.apply(lambda row: (row['개당 이익'] /
           + row['실정산액'] * 100) if row['실정산액'] > 0 else
           + 0, axis=1)
       155 +                  analysis_df['박스당 이익'] =
           + analysis_df['개당 이익'] * analysis_df['box_ea']
       156 +
       157 +                  display_cols = ['unique_name',
           + 'stand_cost', 'stand_price_ea', 'supply_price',
           + '실정산액', '기준가 대비 차액', '마진율 (%)', '개당
           + 이익', '박스당 이익']
       158 +                  st.dataframe(
       159 +                      analysis_df[display_cols],
       160 +                      column_config={
       161 +                          "unique_name": "품목명",
       162 +                          "stand_cost":
           + st.column_config.NumberColumn("제품 원가",
           + format="%d원"),
       163 +                          "stand_price_ea":
           + st.column_config.NumberColumn("기준 도매가",
           + format="%d원"),
       164 +                          "supply_price":
           + st.column_config.NumberColumn("공급 단가",
           + format="%d원"),
       165 +                          "실정산액":
           + st.column_config.NumberColumn("실정산액",
           + format="%d원"),
       166 +                          "기준가 대비 차액":
           + st.column_config.TextColumn("기준가 대비 차액"),
       167 +                          "마진율 (%)":
           + st.column_config.NumberColumn("마진율",
           + format="%.1f%%"),
       168 +                          "개당 이익":
           + st.column_config.NumberColumn("개당 이익",
           + format="%d원"),
       169 +                          "박스당 이익":
           + st.column_config.NumberColumn("박스당 이익",
           + format="%d원"),
       170 +                      },
       171 +                      hide_index=True,
           + use_container_width=True
       172 +                  )
       173 +
       174 +                  st.markdown("---")
       175 +                  if st.button(f"✅
           + '{selected_customer_sim}'의 모든 가격 변경사항 DB에
           + 저장", key="save_all_sim", type="primary"):
       176 +                      with st.spinner("DB에 가격
           + 정보를 업데이트합니다..."):
       177 +                          _, _, current_total_prices
           + = load_and_prep_data()
       178 +                          other_customer_prices =
           +
     current_total_prices[current_total_prices['customer_
           + name'] != selected_customer_sim].copy()
       179 +                          updated_data_to_save =
           + analysis_df.rename(columns={'마진율 (%)':
           + 'margin_rate', '개당 이익': 'profit_per_ea',
     '박스당
           +  이익': 'profit_per_box'})
       180 +
           + updated_data_to_save['customer_name'] =
           + selected_customer_sim
       181 +
           + updated_data_to_save['confirm_date'] =
           + datetime.now().strftime("%Y-%m-%d %H:%M")
       182 +
       183 +                          if not
           + current_total_prices.empty:
       184 +                              save_columns =
           + list(current_total_prices.columns)
       185 +                              # 분석에만 사용된
           + 컬럼은 저장하지 않도록 필터링
       186 +                              final_save_df =
           + updated_data_to_save[[col for col in save_columns
     if
           +  col in updated_data_to_save.columns]]
       187 +                          else:
       188 +                              final_save_df =
           + updated_data_to_save
       189 +
       190 +                          final_prices_df =
           + pd.concat([other_customer_prices, final_save_df],
           + ignore_index=True)
       191 +                          price_sheet =
           +
     get_gsheet_client().open(PRICE_DB_NAME).worksheet("c
           + onfirmed_prices")
       192 +
           + set_with_dataframe(price_sheet, final_prices_df,
           + allow_formulas=False)
       193 +
       194 +
           + st.success(f"'{selected_customer_sim}'의 가격
     정보가
           +  성공적으로 업데이트되었습니다.")
       195 +                          st.cache_data.clear()
       196 +                          time.sleep(1)
       197 +                          st.rerun()
       198 +
       199 +  # ==================== 거래처별 품목 관리 탭
           + ====================
       200 +  with tab_matrix:
       201 +      st.header("거래처별 취급 품목 설정")
       202 +      if customers_df.empty:
       203 +          st.warning("등록된 거래처가 없습니다.")
       204 +      else:
       205 +          manage_customer = st.selectbox("관리할
           + 거래처를 선택하세요",
           + customers_df['customer_name'].unique(),
           + key="manage_customer")
       206 +          if manage_customer:
       207 +              st.markdown(f"#### 📄
           + **{manage_customer}** 의 취급 품목 목록")
       208 +              active_products_set = set()
       209 +              if not prices_df.empty and
           + 'unique_name' in prices_df.columns:
       210 +                  active_products_set =
           + set(prices_df[prices_df['customer_name'] ==
           + manage_customer]['unique_name'])
       211 +
       212 +              checkbox_states = {}
       213 +              for _, product in
           + products_df.iterrows():
       214 +                  is_checked =
     product['unique_name']
           +  in active_products_set
       215 +
           + checkbox_states[product['unique_name']] =
           + st.checkbox(
       216 +                      product['unique_name'],
           + value=is_checked,
     key=f"check_{manage_customer}_{pro
           + duct['unique_name']}"
       217 +                  )
       218 +
       219 +              if st.button(f"✅
     **{manage_customer}**
           +  의 품목 정보 저장", use_container_width=True,
           + type="primary"):
       220 +                  with st.spinner("DB를 업데이트하는
           + 중입니다..."):
       221 +                      _, _, current_prices =
           + load_and_prep_data()
       222 +                      other_customer_prices =
           + current_prices[current_prices['customer_name'] !=
           + manage_customer].copy()
       223 +                      newly_active_products = {name
           + for name, checked in checkbox_states.items() if
           + checked}
       224 +                      reconstructed_entries = []
       225 +                      for unique_name in
           + newly_active_products:
       226 +                          existing_entry =
           + current_prices[
       227 +
           + (current_prices['customer_name'] ==
     manage_customer)
           +  &
       228 +
           + (current_prices['unique_name'] == unique_name)
       229 +                          ]
       230 +                          if not
           + existing_entry.empty:
       231 +
     reconstructed_entries.a
           + ppend(existing_entry.iloc[0].to_dict())
       232 +                          else:
       233 +                              product_info =
           + products_df.loc[products_df['unique_name'] ==
           + unique_name].iloc[0]
       234 +
           + reconstructed_entries.append({
       235 +                                  "confirm_date":
           + datetime.now().strftime("%Y-%m-%d %H:%M"),
           + "unique_name": unique_name, "customer_name":
           + manage_customer,
       236 +                                  "stand_cost":
           + product_info['stand_cost'], "supply_price":
           + product_info['stand_price_ea'],
       237 +                                  "margin_rate": 0,
           + "profit_per_ea": 0, "profit_per_box": 0
       238 +                              })
       239 +
       240 +                      reconstructed_df =
           + pd.DataFrame(reconstructed_entries)
       241 +                      final_df =
           + pd.concat([other_customer_prices,
     reconstructed_df],
           +  ignore_index=True)
       242 +                      price_sheet =
     get_gsheet_client
           +
     ().open(PRICE_DB_NAME).worksheet("confirmed_prices")
       243 +
     set_with_dataframe(price_sheet,
           +  final_df, allow_formulas=False)
       244 +
       245 +
           + st.success(f"'{manage_customer}'의 취급 품목 정보가
           + DB에 성공적으로 업데이트되었습니다!")
       246 +                      st.cache_data.clear()
       247 +                      time.sleep(1)
       248 +                      st.rerun()
       249 +
       250 +  # ==================== DB 원본 조회 탭
           + ====================
       251 +  with tab_db_view:
       252 +      st.header("제품 마스터 DB")
       253 +      st.dataframe(products_df)
       254 +      st.header("거래처 목록 DB")
       255 +      st.dataframe(customers_df)
       256 +      st.header("확정 가격 DB (취급 품목 목록)")
       257 +      st.dataframe(prices_df)
