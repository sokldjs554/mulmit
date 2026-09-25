## 무엇을, 왜

## 어떻게 확인했나
- [ ] `make lint test`
- [ ] 평가 수치 (파이프라인·프롬프트·파서·랭킹 변경 시): `manage eval all` 전 → 후
- [ ] 쿼리·인덱스 변경 시: `make bench` 실행 계획 전 → 후

## 영향
- [ ] DB 마이그레이션 (직전 코드와 호환)
- [ ] API 스키마 변경 (`make gen-api` 커밋)
- [ ] 과금·알림 등 외부 효과 (멱등성 확인)
- [ ] 새 환경 변수·시크릿 (`.env.example`, Terraform 반영)
