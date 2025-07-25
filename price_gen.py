import streamlit as st
import pandas as pd
import os
from datetime import datetime
from github import Github, GithubException

# --- 페이지 설정 및 데이터 파일 경로 ---
st.set_page_config(page_title="고래미 가격결정 시스템", page_icon="🐟", layout="wide")
PRODUCTS_FILE = 'products.csv'
CUSTOMERS_FILE = 'customers.csv'
CONFIRMED_PRICES_FILE = 'confirmed_prices.csv'
REPO_NAME = "your_github_username/your_repo_name" # 예: "goraemi-kim/pricing-app" (본인 것으로 수정!)


# --- GitHub 파일 업데이트 함수 ---
def update_github_file(file_path, df_to_save):
    try:
        # Streamlit secrets에서 토큰 가져오기
        token = st.secrets["github_token"]
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        
        # 데이터프레임을 CSV 문자열로 변환
        csv_content = df_to_save.to_csv(index=False)
        
        # 파일이 이미 있는지 확인
        try:
            contents = repo.get_contents(file_path, ref="main")
            # 파일이 있으면 업데이트
            repo.update_file(contents.path, f"Update {file_path}", csv_content, contents.sha, branch="main")
            st.success(f"✅ DB 파일(`{file_path}`)이 GitHub에 성공적으로 업데이트되었습니다!")
        except GithubException:
            # 파일이 없으면 새로 생성
            repo.create_file(file_path, f"Create {file_path}", csv_content, branch="main")
            st.success(f"✅ DB 파일(`{file_path}`)을 GitHub에 성공적으로 생성했습니다!")

    except Exception as e:
        st.error(f"DB 업데이트 중 오류가 발생했습니다: {e}")
        st.error("GitHub 토큰과 저장소 이름을 정확히 설정했는지 확인해주세요.")

# --- 데이터 로딩 (기존 로직과 동일) ---
@st.cache_data
def load_data(file_path):
    # (이 부분은 수정 없음)
    if os.path.exists(file_path):
        return pd.read_csv(file_path).fillna(0)
    return pd.DataFrame()

# (이하 채널 정보, 데이터 로딩, UI 코드 등은 이전 답변과 거의 동일합니다)
# ... (이전 코드의 UI 및 계산 로직 부분을 여기에 그대로 붙여넣으세요) ...
# ... (단, 마지막 '가격 확정' 부분의 버튼 로직이 변경됩니다) ...


# (이전 코드의 마지막 섹션인 '가격 확정 목록 및 DB 관리'를 아래 내용으로 교체합니다)

# --- ✨ 신규 기능: 확정 목록 및 DB 관리 ---
st.header("3. 가격 확정 목록 및 DB 저장")

tab1, tab2 = st.tabs(["이번 세션에서 확정한 목록", "기존 확정 가격 DB"])

with tab1:
    st.subheader("이번 세션에서 확정한 목록")
    if not st.session_state.get('confirmed_list', []):
        st.info("아직 이번 세션에서 확정한 가격이 없습니다. 위에서 '✅ 이 가격으로 확정하기' 버튼을 눌러 추가하세요.")
    else:
        session_df = pd.DataFrame(st.session_state.confirmed_list)
        st.dataframe(session_df, use_container_width=True)
        
        st.markdown("---")
        st.warning("**중요:** 아래 버튼을 누르면 이번 세션의 작업 내용이 GitHub DB에 영구적으로 저장됩니다.")
        
        # DB 저장 버튼
        if st.button("💾 이번 세션의 확정 목록을 DB에 저장하기", type="primary"):
            # 기존 DB와 세션 목록을 병합하고, 중복은 최신 것으로 유지
            combined_df = pd.concat([confirmed_prices_df, session_df]).drop_duplicates(
                subset=['product_name', 'customer_name'], keep='last'
            )
            # GitHub 파일 업데이트 함수 호출
            update_github_file(CONFIRMED_PRICES_FILE, combined_df)
            # 성공적으로 저장 후 세션 목록 비우기
            st.session_state.confirmed_list = []
            st.info("저장이 완료되었습니다. 페이지가 새로고침되어 최신 DB를 반영합니다.")
            # st.rerun() # 앱을 다시 실행하여 변경사항 즉시 반영


with tab2:
    st.subheader(f"기존 확정 가격 DB (`{CONFIRMED_PRICES_FILE}`)")
    if confirmed_prices_df.empty:
        st.info("기존에 저장된 확정 가격 DB가 없습니다.")
    else:
        # 최신 데이터를 반영하기 위해 GitHub에서 직접 다시 로드할 수도 있으나, 우선 로드된 데이터를 보여줌
        st.dataframe(confirmed_prices_df, use_container_width=True)
