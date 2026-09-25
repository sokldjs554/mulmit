# 데이터 소스

| 키 | 제공처 | 문서 유형 | 주기 (KST) | 어댑터 |
|---|---|---|---|---|
| `clik_minutes` | 국회도서관 지방의정포털 Open API | 지방의회 회의록 | 매일 03:10 | `sources/clik.py` |
| `lofin_budget` | 행정안전부 지방재정365 | 세출예산서(PDF·스캔 PDF·HWP/HWPX) | 매주 일 02:40 | `sources/lofin.py` |
| `g2b_order_plan` | 조달청 발주계획현황서비스 | 발주계획 | 매시 7분 | `sources/g2b.py` |
| `g2b_prespec` | 조달청 사전규격정보서비스 | 사전규격 | 매시 7분 | `sources/g2b.py` |
| `g2b_bid` | 조달청 입찰공고정보서비스 | 입찰공고 | 매시 7분 | `sources/g2b.py` |
| `fixture_*` | 합성 세계 (`demo/synth.py`) | 위 다섯 가지 | 수동/데모 | `sources/registry.py` |

## 검증 상태 — 먼저 읽어 주세요

개발 컨테이너의 네트워크 정책 때문에 `clik.nanet.go.kr`, `data.go.kr`, `lofin.mois.go.kr`에 직접 접속하지 못했습니다. 그래서 세 어댑터의 **엔드포인트 경로와 필드명은 공개 명세·검색 결과·공개 저장소를 근거로 작성**했고, `tests/unit/test_sources.py`의 계약 픽스처로만 검증했습니다. 실제 키로 처음 돌릴 때는 운영 콘솔 *수집원* 화면에서 첫 실행 결과(가져온 수·신규·오류)를 확인하세요.

어긋나는 부분이 있으면 코드 수정 없이 `sources.config`(DB, JSON)에서 덮어쓸 수 있습니다.

```sql
UPDATE sources SET config = config || '{"list_path": "/openapi/minutes.do", "date_fields": ["MTG_DE"]}'
WHERE key = 'clik_minutes';
```

## 호출 제약과 대응

| 제약 | 대응 | 코드 |
|---|---|---|
| CLIK: 키당 하루 1,000회, 호출당 100건 | 회의 날짜로 페이지 이동, 저장하지 않은 회의록만 본문 호출 | `clik.py` |
| data.go.kr: 개발 키 오퍼레이션당 하루 1,000회, 조회 기간 제한 | 7일 창으로 쪼개 페이지네이션, KST 일일 한도 카운터 | `g2b.py`, `resilience.py` |
| 한도 초과·오류를 **HTTP 200 + 오류 본문**으로 응답 | `resultCode`/`OpenAPI_ServiceResponse` 분류: 한도(22) → KST 자정 이후로 재예약, 키·파라미터(10~33) → 즉시 실패(운영자 확인), 일시 오류 → 재시도 | `http.py` |
| 429/5xx/타임아웃 | 지수 백오프 + full jitter, `Retry-After` 존중 | `http.py` |
| 제공처 장애 | 수집원별 서킷 브레이커(연속 5회 실패 → 10분 차단 → 1회 탐침) | `resilience.py` |
| 워커 여러 대가 한도 공유 | 토큰 버킷·일일 카운터·서킷 상태 모두 Redis(Lua로 원자적 처리) | `resilience.py` |

## 조달청 오퍼레이션과 매핑

업무구분(용역 `Servc` / 물품 `Thng` / 공사 `Cnstwk`)마다 오퍼레이션이 따로 있어 세 개를 모두 호출합니다. 경로는 `g2b.py`의 `OPERATIONS`.

| 유형 | 경로 | 외부 ID | 연결에 쓰는 필드 |
|---|---|---|---|
| 발주계획 | `/ao/OrderPlanSttusService/getOrderPlanSttusList{Servc,Thng,Cnstwk}` | `orderPlanUntyNo` | `bizNm`, `sumOrderAmt`, `orderYear`·`orderMnth`, `orderInsttNm`, `deptNm` |
| 사전규격 | `/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfo{Servc,Thng,Cnstwk}` | `bfSpecRgstNo` | `prdctClsfcNoNm`, `asignBdgtAmt`, `orderPlanUntyNo`, `bidNtceNoList`, `rlDminsttNm` |
| 입찰공고 | `/ad/BidPublicInfoService/getBidPblancListInfo{Servc,Thng,Cnstwk}` | `bidNtceNo`-`bidNtceOrd` | `bidNtceNm`, `asignBdgtAmt`/`presmptPrce`, `bfSpecRgstNo`, `orderPlanUntyNo`, `dminsttNm` |

- 참조번호(`orderPlanUntyNo`, `bfSpecRgstNo`, 공고번호)가 있으면 **유사도보다 먼저** 그 번호로 기회를 잇습니다.
- 조달청 기관코드는 우리 기관 사전의 코드와 체계가 달라 이름으로 해석합니다. "중구청"처럼 광역시가 빠진 이름은 모호로 처리해 검토 대기열로 보냅니다.

## 원문 파일

- 원문 바이트는 SHA-256 콘텐츠 주소로 저장합니다(`storage.py`: 로컬 `file://`, 프로덕션 `gs://`). 같은 파일은 한 번만 저장·처리됩니다.
- 예산서 PDF: 페이지별로 텍스트층 글자 수를 보고, 부족한 페이지만 OCR합니다(스캔본과 텍스트본이 섞인 권도 처리).
- HWP 5.x: OLE 컨테이너의 `BodyText/Section*` 레코드를 풀어 `PARA_TEXT`(태그 67)에서 글자를 읽고 제어 문자를 제거합니다. HWPX: ZIP 안의 섹션 XML.

## 합성 세계

`manage seed`가 `fixture_*` 수집원을 만들고, 어댑터는 시드·기준일·규모로 결정되는 합성 세계를 실제 제공처처럼 내어 줍니다. 21개 사업 원형, 동명 기관, 스캔 예산서, 약한 발언, 공고로 이어지지 않는 사업, 무관한 공고가 섞여 있고, 정답은 평가에만 쓰입니다([ADR-0007](adr/0007-synthetic-world-evaluation.md)).
