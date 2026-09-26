# 조달청 API 실호출 점검 (자동 생성: `manage sources check`)

기준일 2026-09-26 · 최근 7일 · 오퍼레이션마다 첫 페이지 1회 호출

| 수집원 | 오퍼레이션 | 결과 | 전체 건수 | 받은 항목 | 레코드로 변환 | 기관명 | 연결·랭킹 필드 채움 비율 |
|---|---|---|---:|---:|---:|---:|---|
| `g2b_order_plan` | `getOrderPlanSttusListServc` | 실패: FatalSourceError: g2b-check:getOrderPlanSttusListServc: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |
| `g2b_order_plan` | `getOrderPlanSttusListThng` | 실패: FatalSourceError: g2b-check:getOrderPlanSttusListThng: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |
| `g2b_order_plan` | `getOrderPlanSttusListCnstwk` | 실패: FatalSourceError: g2b-check:getOrderPlanSttusListCnstwk: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |
| `g2b_prespec` | `getPublicPrcureThngInfoServc` | 실패: FatalSourceError: g2b-check:getPublicPrcureThngInfoServc: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |
| `g2b_prespec` | `getPublicPrcureThngInfoThng` | 실패: FatalSourceError: g2b-check:getPublicPrcureThngInfoThng: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |
| `g2b_prespec` | `getPublicPrcureThngInfoCnstwk` | 실패: FatalSourceError: g2b-check:getPublicPrcureThngInfoCnstwk: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |
| `g2b_bid` | `getBidPblancListInfoServc` | 실패: FatalSourceError: g2b-check:getBidPblancListInfoServc: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |
| `g2b_bid` | `getBidPblancListInfoThng` | 실패: FatalSourceError: g2b-check:getBidPblancListInfoThng: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |
| `g2b_bid` | `getBidPblancListInfoCnstwk` | 실패: FatalSourceError: g2b-check:getBidPblancListInfoCnstwk: provider error 30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 등록되지 않은 서비스키 (HTTP 403) | – | 0 | 0 | – | – |

## 활용신청이 필요한 서비스

오류 30(`SERVICE_KEY_IS_NOT_REGISTERED_ERROR`)은 이 키로 그 서비스를 활용신청하지 않았거나, 승인이 아직 게이트웨이에 반영되지 않았다는 뜻입니다. 공공데이터포털에서 서비스마다 신청한 뒤(개발계정은 보통 자동승인, 반영까지 1~2시간) 다시 점검합니다.

- [조달청_나라장터 입찰공고정보서비스](https://www.data.go.kr/data/15129394/openapi.do) (`BidPublicInfoService`)
- [조달청_나라장터 사전규격정보서비스](https://www.data.go.kr/data/15129437/openapi.do) (`HrcspSsstndrdInfoService`)
- [조달청_나라장터 발주계획현황서비스](https://www.data.go.kr/data/15129462/openapi.do) (`OrderPlanSttusService`)
