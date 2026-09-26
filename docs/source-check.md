# 조달청 API 실호출 점검 (자동 생성: `manage sources check`)

기준일 2026-09-26 · 최근 7일 · 오퍼레이션마다 첫 페이지 1회 호출

| 수집원 | 오퍼레이션 | 결과 | 전체 건수 | 받은 항목 | 레코드로 변환 | 기관명 | 연결·랭킹 필드 채움 비율 |
|---|---|---|---:|---:|---:|---:|---|
| `g2b_order_plan` | `getOrderPlanSttusListServc` | 성공 | 1152 | 20 | 20 | 100% | 금액 100%, 발주연도 100%, 발주월 100%, 부서 100% |
| `g2b_order_plan` | `getOrderPlanSttusListThng` | 성공 | 941 | 20 | 20 | 100% | 금액 100%, 발주연도 100%, 발주월 100%, 부서 100% |
| `g2b_order_plan` | `getOrderPlanSttusListCnstwk` | 성공 | 921 | 20 | 20 | 100% | 금액 100%, 발주연도 100%, 발주월 100%, 부서 100% |
| `g2b_prespec` | `getPublicPrcureThngInfoServc` | 성공 | 883 | 20 | 20 | 100% | 금액 100%, 발주계획번호 0%, 공고번호 목록 5%, 의견마감 100% |
| `g2b_prespec` | `getPublicPrcureThngInfoThng` | 성공 | 724 | 20 | 20 | 100% | 금액 100%, 발주계획번호 0%, 공고번호 목록 0%, 의견마감 100% |
| `g2b_prespec` | `getPublicPrcureThngInfoCnstwk` | 성공 | 43 | 20 | 20 | 100% | 금액 100%, 발주계획번호 0%, 공고번호 목록 15%, 의견마감 100% |
| `g2b_bid` | `getBidPblancListInfoServc` | 성공 | 2010 | 20 | 20 | 100% | 금액 100%, 사전규격번호 85%, 발주계획번호 90%, 입찰마감 80% |
| `g2b_bid` | `getBidPblancListInfoThng` | 성공 | 1756 | 20 | 20 | 100% | 금액 100%, 사전규격번호 60%, 발주계획번호 85%, 입찰마감 95% |
| `g2b_bid` | `getBidPblancListInfoCnstwk` | 성공 | 1416 | 20 | 20 | 100% | 금액 100%, 사전규격번호 0%, 발주계획번호 75%, 입찰마감 100% |

## 예시 레코드 (오퍼레이션별 첫 건)

- `getOrderPlanSttusListServc` 2026-09-22 · 경기도교육청 호연고등학교 · 호연고등학교 2027학년도 2학년 숙박형 현장체험학습(수련활동) 위탁 용역 · 96,140,000원
- `getOrderPlanSttusListThng` 2026-09-21 · 서울특별시중부교육청 선린중학교 · 2026학년도 선린중학교 신입생 교복(동복) · 29,315,000원
- `getOrderPlanSttusListCnstwk` 2026-09-23 · 대전광역시 대덕구 · 동춘당로 15번길 도로정비공사 · 200,000,000원
- `getPublicPrcureThngInfoServc` 2026-09-21 · 경기도 성남시 · 구미동 96-3번지 상수관 정비공사 폐기물처리용역 · 65,625,000원
- `getPublicPrcureThngInfoThng` 2026-09-20 · 농촌진흥청 국립원예특작과학원 · 시약초자류(RNaseZAP등 91품목) 입찰구매 · 96,777,000원
- `getPublicPrcureThngInfoCnstwk` 2026-09-21 · 한국수자원공사 · 유사조절지 월류부 시설개선공사 · 953,029,000원
- `getBidPblancListInfoServc` 2026-09-20 · 보령원도심 도시락상권 활성화사업단 · 보령원도심 도시락상권 시그니처 조형물 제작설치 · 100,000,000원
- `getBidPblancListInfoThng` 2026-09-20 · 전북특별자치도 완주군 · 소규모 공공하수처리시설 스마트통합관제시스템 구축사업(계장제어장치) · 843,722,000원
- `getBidPblancListInfoCnstwk` 2026-09-20 · 충북대학교병원 · UPS 노후부품(응급실, 수술장, 외상중환자실) 배터리교체 공사 · 76,230,000원
