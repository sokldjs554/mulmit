# 추출 모델 비교 (자동 생성: `manage eval llm`)

수기 세트 54건(기대 신호 50건, 신호가 없어야 하는 사례 10건) · 프롬프트 `extract-v3` · 스키마 `signal-v3` · 실행일 2026-09-26 · 사용액 $1.65 (상한 $10.00)

점수는 **검증기를 거친 뒤 저장되는 값** 기준입니다. 금액·연도·확약 수준·분류는 짝지어진 신호 중 맞힌 비율이고, 비용은 목록 가격으로 계산한 실제 사용량입니다.

| 추출기 | 정밀도 | 재현율 | F1 | 금액 | 연도 | 확약 수준 | 분류 | 건당 비용 | 1,000건당 | 지연 p50 / p95 | 오류 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| heuristic | 92.0% | 46.0% | 0.613 | 78.3% | 91.3% | 82.6% | 82.6% | $0 | $0 | – | 없음 |
| claude-opus-5 · low | 100.0% | 100.0% | 1.0 | 100.0% | 98.0% | 98.0% | 86.0% | $0.0107 | $10.70 | 4.5s / 6.5s | 없음 |
| claude-opus-5 · medium | 100.0% | 100.0% | 1.0 | 100.0% | 98.0% | 98.0% | 90.0% | $0.0110 | $11.04 | 4.7s / 8.2s | 없음 |
| claude-sonnet-5 · low | 100.0% | 98.0% | 0.99 | 100.0% | 98.0% | 98.0% | 87.8% | $0.0042 | $4.16 | 3.6s / 5.3s | 없음 |
| claude-haiku-4-5 | 100.0% | 92.0% | 0.958 | 100.0% | 97.8% | 91.3% | 76.1% | $0.0046 | $4.58 | 3.4s / 4.4s | 없음 |

## 검증기가 한 일

| 추출기 | 원본 정밀도 → 저장 | 원본 금액 정확도 → 저장 | 근거 인용 모두 확인 | 버린 신호 | 검토 대기로 보낸 신호 | 파서가 고친 금액 | 캐시 읽기 비중 |
|---|---|---|---:|---:|---:|---:|---:|
| heuristic | 92.0% → 92.0% | 78.3% → 78.3% | 100.0% | 0 | 2 | 0 | – |
| claude-opus-5 · low | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% | 0 | 2 | 0 | 92.2% |
| claude-opus-5 · medium | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% | 0 | 2 | 0 | 92.2% |
| claude-sonnet-5 · low | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% | 0 | 2 | 0 | 92.3% |
| claude-haiku-4-5 | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% | 0 | 2 | 0 | 0.0% |

## 틀린 사례 (추출기별 최대 15건)

<details><summary>heuristic</summary>

- `r01` 놓침: 수요응답
- `r01` 없는 신호를 만듦: 차량 임차와 플랫폼 구축
- `r02` 놓침: 지하차도
- `r03` 다만 행안부 공통기반 전환: commitment committed (정답 declined), expected_year 2025 (정답 None)
- `r05` 놓침: 메타버스
- `r06` 독거어르신 돌봄 스피커 사업: commitment planned (정답 committed)
- `r07` 송도 쪽 스마트폴 설치: commitment committed (정답 reviewing), expected_year 2025 (정답 None), budget 950000000 (정답 None)
- `r07` 놓침: 선별관제
- `r09` 지난달 정부 AI 공모사업: category ai_data (정답 public_sw)
- `r10` 놓침: 태양광
- `r13` 디 지털트윈 기반 도시관리 플랫폼 구축: category public_sw (정답 smart_city)
- `r16` 놓침: 횡단보도
- `r16` 전 구간에 비상벨을 추가하는 사업: budget 120000000 (정답 None)
- `r16` 놓침: 보행자
- `r18` 해수욕장 AI 이안류 감시시스템 구축: category ai_data (정답 safety_cctv)

</details>

<details><summary>claude-opus-5 · low</summary>

- `r09` AI 민원상담 챗봇 구축: category ai_data (정답 public_sw)
- `r16` 스마트 횡단보도 설치: category safety_cctv (정답 smart_city)
- `r18` 해수욕장 AI 이안류 감시시스템 구축: category ai_data (정답 safety_cctv)
- `r31` AI 기반 치매 조기검진 앱 도입: category ai_data (정답 welfare_care)
- `r35` 구립도서관 무인 대출반납기 추가 설치: category public_sw (정답 education)
- `r36` 여객선터미널 대합실 리모델링 공사: commitment planned (정답 committed)
- `r41` 수요응답형 버스(DRT) 도입: expected_year 2025 (정답 None)
- `r43` 공영주차장 급속충전기 설치: category energy_env (정답 mobility)
- `r50` 태양광 압축 스마트 쓰레기통 설치: category smart_city (정답 energy_env)

</details>

<details><summary>claude-opus-5 · medium</summary>

- `r09` AI 민원상담 챗봇 구축: category ai_data (정답 public_sw)
- `r16` 스마트 횡단보도 설치: category safety_cctv (정답 smart_city)
- `r18` 해수욕장 AI 이안류 감시시스템 구축: category ai_data (정답 safety_cctv)
- `r31` AI 기반 치매 조기검진 앱 도입: category ai_data (정답 welfare_care)
- `r36` 여객선터미널 대합실 리모델링 공사: commitment planned (정답 committed)
- `r41` 수요응답형 버스(DRT) 도입: expected_year 2025 (정답 None)
- `r43` 공영주차장 급속충전기 설치: category energy_env (정답 mobility)

</details>

<details><summary>claude-sonnet-5 · low</summary>

- `r09` AI 민원상담 챗봇 구축: category ai_data (정답 public_sw)
- `r13` 디지털트윈 기반 도시관리 플랫폼 구축: category public_sw (정답 smart_city)
- `r24` RFID 음식물쓰레기 종량기 교체: category other (정답 energy_env)
- `r31` AI 기반 치매 조기검진 앱 도입: category ai_data (정답 welfare_care)
- `r35` 놓침: 대출
- `r36` 여객선터미널 대합실 리모델링 공사: commitment planned (정답 committed)
- `r40` 장애인복지관 홈페이지 웹 접근성 개선 용역: category welfare_care (정답 public_sw)
- `r41` 수요응답형 버스 도입: expected_year 2025 (정답 None)
- `r43` 공영주차장 급속충전기 설치: category energy_env (정답 mobility)

</details>

<details><summary>claude-haiku-4-5</summary>

- `r02` 지하차도 수위계 및 자동 차단시설 설치: category facility (정답 safety_cctv)
- `r03` 구청 홈페이지 모바일 개편: commitment reviewing (정답 declined)
- `r07` 놓침: 스마트폴
- `r07` CCTV 선별관제 시스템 구축: commitment planned (정답 committed)
- `r09` AI 민원상담 챗봇 구축: category ai_data (정답 public_sw)
- `r13` 디지털트윈 기반 도시관리 플랫폼 구축: category public_sw (정답 smart_city)
- `r14` 상권분석 플랫폼 구축: category public_sw (정답 ai_data)
- `r16` 스마트 횡단보도 설치: category safety_cctv (정답 smart_city)
- `r16` 보행자 우선 신호 시스템 검토: category safety_cctv (정답 mobility)
- `r17` 스마트 경로당 사업: commitment reviewing (정답 declined)
- `r18` 해수욕장 AI 이안류 감시시스템 구축: category ai_data (정답 safety_cctv)
- `r24` 음식물쓰레기 RFID 종량기 교체: category facility (정답 energy_env)
- `r26` 놓침: 가로등
- `r31` AI 기반 치매 조기검진 앱 도입: category ai_data (정답 welfare_care)
- `r35` 놓침: 대출

</details>

