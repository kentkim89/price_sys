# create_user.py
import bcrypt
import getpass

# 사용자로부터 아이디와 비밀번호를 입력받습니다.
username = input("생성할 사용자 아이디를 입력하세요: ")
password = getpass.getpass("사용할 비밀번호를 입력하세요 (화면에 보이지 않습니다): ")

# 비밀번호를 바이트로 인코딩합니다.
password_bytes = password.encode('utf-8')

# salt를 생성하고 비밀번호를 해싱합니다.
salt = bcrypt.gensalt()
hashed_password = bcrypt.hashpw(password_bytes, salt)

# 해시된 비밀번호를 화면에 출력합니다 (이 값을 구글 시트에 복사).
print("\n--- 사용자 정보 생성 완료 ---")
print(f"사용자 아이디: {username}")
print(f"해시된 비밀번호 (이 값을 복사하세요): {hashed_password.decode('utf-8')}")
print("\n위 '해시된 비밀번호' 값을 복사하여 Goremi Users DB 시트의 'hashed_password' 열에 붙여넣으세요.")
