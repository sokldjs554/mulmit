# 시장 조사: 왜 "입찰 이전 신호"인가

작성: 2026-09-25 · 방법: 국내·해외 웹 검색 결과와 각 서비스의 공개 페이지·기사 요약을 교차 확인했습니다. 일부 사이트(stepai.kr, clik.nanet.go.kr, data.go.kr)는 개발 컨테이너의 네트워크 정책으로 직접 열람하지 못했고, 검색 결과의 요약에 의존한 부분은 그렇게 표시했습니다.

## 1. 질문

채용 공고의 키워드(LLM 파이프라인, 대규모 공공 데이터 수집, 비정형 문서·OCR, 추천·랭킹, 알림, 정기결제·크레딧)를 모두 자연스럽게 쓰는 주제는 많습니다. 문제는 지원자 대부분이 같은 결론에 도달한다는 점입니다. 그래서 먼저 **이미 포화된 주제**를 확인하고, 그 바깥에서 **해외에서는 검증됐지만 국내에는 없는** 영역을 찾았습니다.

## 2. 국내: 포화된 두 영역

### 2-1. 정부지원사업 매칭·추천

| 서비스 | 내용 |
|---|---|
| 지원매치 (시너지앤) | AI가 지원사업 공고 중 기업 맞춤 사업을 추천하고 사업계획서 작성까지 지원 ([이데일리](https://edaily.co.kr/News/Read?mediaCodeNo=257&newsId=04880646645347568)) |
| 지원금AI | 중앙부처·지자체 공고 17,000건 이상을 매시간 수집해 조건 매칭 ([govmatch.kr](https://www.govmatch.kr/)) |
| K-Fund | 지원사업 공고 통합, 맞춤 필터·키워드 알림 ([kfund.ai](https://kfund.ai/)) |
| 커넥트웍스 | 정부지원사업 통합 안내·맞춤 검색 ([works.connect24.kr](https://works.connect24.kr/)) |
| THE VC 지원사업 탐색 | K-Startup·중소벤처24·기업마당 통합 검색 ([thevc.kr/grants](https://thevc.kr/grants)) |

공공 API(기업마당 [지원사업정보 API](https://www.bizinfo.go.kr/web/lay1/program/S1T175C174/apiDetail.do?id=bizinfoApi))가 잘 열려 있어 진입이 쉽고, 그만큼 비슷한 포트폴리오가 많습니다.

### 2-2. 나라장터 입찰공고 검색·낙찰가 예측

| 서비스 | 내용 |
|---|---|
| 클라이원트 | RFP 본문 문맥 분석, 나라장터 외 80여 기관 공고 키워드 매칭 메일, 발주계획·사전규격 기반 영업 시점 안내 ([블로그](https://blog.cliwant.com/aisearch/), [사전 영업 가이드](https://blog.cliwant.com/bid-pre-sales-activity-step-by-step/)) |
| 낙비 | 공공조달 5,300만 건 학습, 사정율 예측·자격 분석 ([naktal.me](https://naktal.me/)) |
| 디마툴즈 | 나라장터·D2B·한전·LH 낙찰가 예측 ([dima-g2b.com](https://dima-g2b.com/home)) |
| 일타비드 | 공고번호 입력 → 투찰가 구간 예측 ([ilta.kr](https://ilta.kr/)) |
| 지투비플러스, 모두입찰 | 입찰정보 통합 검색·알림 ([g2bplus.kr](https://www.g2bplus.kr/), [modoobid.co.kr](https://www.modoobid.co.kr/)) |

GitHub에도 같은 API를 감싼 수집·알림 프로젝트가 많습니다: [ppsfinding](https://github.com/pppeume/ppsfinding), [bid_monitor](https://github.com/dgilink/bid_monitor), [narajangteo-notify](https://github.com/agnes4970/-narajangteo-notify), [narajangteo-bid-mcp](https://github.com/opendata-kr/narajangteo-bid-mcp), [oksp-pipeline-radar](https://github.com/jboh0003-dev/oksp-pipeline-radar), [jodalfit](https://github.com/SSEUNGSSEUNGWOO/jodalfit), [g2b-education-dashboard](https://github.com/choiys2/g2b-education-dashboard).

**관찰:** 국내 서비스의 가장 이른 신호는 **발주계획·사전규격**입니다. 공고 몇 주~몇 달 전이지만, 이때는 이미 사업 내용과 예산이 거의 정해져 있습니다.

### 2-3. 지방의회 회의록 AI: 있지만 영업용이 아님

- 개혁연구원: 1991년 이후 지방의회 회의록 21만여 건을 모아 AI 검색 체계를 구축, 정책 설계 용도 ([시대](https://www.sidae.com/article/2026040314295767892))
- 충남도의회: 예·결산 분석자료 AI 열람·검색 시스템 자체 구축, 의정 활동 용도 ([네이트 뉴스](https://m.news.nate.com/view/20260818n27122))
- 정부 회의록 자동 작성(STT) 사례 ([아주경제](https://www.ajunews.com/view/20240321080836723)), 행정안전부 [AI 정부 서비스 사례집](https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000015&nttId=124688)

회의록을 AI로 읽는 시도는 있으나 **정책·의정 관점**이고, "이 발언이 몇 달 뒤 어떤 입찰이 되는가"를 **공급 기업의 영업 파이프라인**으로 바꾸는 서비스는 찾지 못했습니다.

## 3. 해외: 같은 틈새가 이미 검증됨

| 서비스 | 무엇을 읽나 | 규모·근거 |
|---|---|---|
| Starbridge (미국) | 이사회 회의록, 예산 문서, 보조금, 계약 만료 → "Buying Signals" | 32만+ 기관 모니터링, 신호는 RFP 6~18개월 전에 나타난다고 설명 ([Buying Signals Monitor](https://starbridge.ai/features/buying-signals-monitor), [How to win before the RFP](https://starbridge.ai/blog/how-to-win-public-sector-contracts), [Government buying signals](https://starbridge.ai/blog/government-buying-signals)) |
| GovSpend Meeting Intelligence (미국) | 공공 회의 영상 전사 + 안건·회의록 검색, 저장 검색 알림 | 7,900개 기관의 회의 63.2만 건 ([Meeting Intelligence](https://govspend.com/meeting-intelligence/), [소개 글](https://govspend.com/blog/meeting-intelligence-december-2023/)) |
| Hamlet (미국) | 지방정부 회의 전사·검색, 부동산·데이터센터 사업자 대상 | 6,600+ 의결기구, 누적 투자 1,000만 달러 ([myhamlet.com](https://www.myhamlet.com/about), [PublicCEO](https://www.publicceo.com/2026/02/hamlet-launches-nationwide-public-meeting-coverage-over-3000-local-governments-videos-now-discoverable/)) |
| Stotles (영국) | 공공 조달 데이터 기반 영업 파이프라인 | 2025년 시리즈 A 1,300만 달러, 고객 1,000+ ([TFN](https://techfundingnews.com/stotles-secures-13m-to-transform-how-businesses-win-government-contracts-with-ai-heres-how/)) |
| Tendium (스웨덴), Altura, Govly | 공고 검색·자격 판단·제안 작성 | ([tendium.com](https://tendium.com/), [Tracxn](https://tracxn.com/d/companies/tendium-systems/__BsrP7S5x_x5W2KWASCmblYfoODglBnCZO3H4uadjo5k)) |

비교 글: [Starbridge — GovSpend alternatives](https://starbridge.ai/blog/govspend-alternatives), [NationGraph — GovSpend alternatives](https://www.nationgraph.com/post/govspend-alternatives), [Civic IQ — tracking budget meetings with AI](https://blogs.civiciq.com/2026/06/03/how-to-track-government-budget-meetings-with-ai/).

**관찰:** 미국 SLED 시장에서는 "공고 이전 신호"가 독립된 제품 범주가 되었고 투자도 받았습니다. 한국 공공조달 시장에는 아직 이 층이 없습니다.

## 4. 한국에서 가능한가: 데이터가 열려 있다

| 단계 | 공개 경로 | 비고 |
|---|---|---|
| 지방의회 발언 | 국회도서관 지방의정포털 Open API ([안내](https://clik.nanet.go.kr/potal/guide/openApi.do)) | 인증키 1개당 하루 1,000회, 호출당 100건 제한 (검색 요약 기준) |
| 세출예산(사업명세서) | 지방재정365 ([개발자공간](https://lofin.mois.go.kr/portal/user/openApi.do?code=bbs&leftCd=13&subCd=12&depCd=)), 공공데이터포털 [세입세출현황](https://www.data.go.kr/data/15058182/openapi.do)·[재정공시](https://www.data.go.kr/data/15138709/openapi.do?recommendDataYn=Y) | 예산서 원문은 PDF(스캔 포함)·HWP로 배포 → OCR·HWP 파싱 필요 |
| 발주계획 | 조달청 [발주계획현황서비스](https://www.data.go.kr/data/15129462/openapi.do) | `orderPlanUntyNo` |
| 사전규격 | 조달청 [사전규격정보서비스](https://www.data.go.kr/data/15129437/openapi.do) | `bfSpecRgstNo` |
| 입찰공고 | 조달청 [입찰공고정보서비스](https://www.data.go.kr/data/15129394/openapi.do) | `bidNtceNo`, 조회 기간 제한 |
| 단계 연결 | 조달청 [계약과정통합공개서비스](https://www.data.go.kr/data/15129459/openapi.do) | 발주계획번호·사전규격번호·공고번호 상호 조회 |

## 5. 결론: 물밑

> 지방의회 회의록과 세출예산서에서 **공고 6~18개월 전의 수요 신호**를 추출하고, 이를 발주계획 → 사전규격 → 입찰공고로 이어지는 하나의 "기회"로 묶어, 공급 기업에게 **근거 문장과 함께** 추천합니다.

- **흔하지 않음:** 국내에서 지원사업 매칭·공고 검색은 포화 상태이고, 회의록 AI는 영업용이 아닙니다. 해외에서는 같은 틈새(Starbridge, GovSpend, Hamlet)가 검증됐습니다.
- **공고의 모든 기술을 필연적으로 사용:** 대규모 공공 데이터 수집(API 한도·장애), 비정형 문서(HWP·스캔 PDF → OCR), LLM 구조화 추출과 근거 검증, 문서 간 연결(임베딩 + 규칙), 추천·랭킹, 다채널 알림, 크레딧 과금(Deep Brief), 운영 콘솔.
- **측정 가능:** 합성 세계에 정답을 심어 추출·연결·OCR을 수치로 평가하고, 과거 공고 기준 백테스트로 "공고 전 몇 %를 먼저 잡았나"를 계산합니다.
