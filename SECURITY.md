# 보안

취약점은 공개 이슈 대신 GitHub의 **Private vulnerability reporting**(Security → Report a vulnerability)으로 알려 주세요.

설계상 원칙:
- 세션은 httpOnly·SameSite=Lax 쿠키, 비밀번호는 argon2id, 로그인 실패 횟수 제한.
- 토스 빌링키는 Fernet으로 암호화해 저장. 운영 비밀값은 Secret Manager, 배포는 Workload Identity Federation(JSON 키 없음).
- API는 프로덕션에서 내부 전용 ingress. Sentry 전송 전 쿠키·인증 헤더·키 값 제거.
