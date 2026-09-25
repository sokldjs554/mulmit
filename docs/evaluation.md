# 평가 결과 (자동 생성: `mulmit eval all --report`)

> 합성 세계(synthetic world) 결과는 파이프라인이 설계대로 동작하는지 보여줄 뿐, 실제 데이터에서의
> 정확도를 주장하지 않습니다. 실제 문장에 가까운 수기 작성 세트(realistic)를 따로 둔 이유입니다.

조건: 기준일 2026-09-25 · 시드 7 · 규모 1.0 · 스캔 비율 기본값 · 추출기 `heuristic`

## 추출 (합성 정답 대비)
- 정밀도 100.0% · 재현율 100.0% (정답 106건, 예측 106건)
- 필드 정확도: budget 100.0%, expected_year 100.0%, commitment 100.0%, category 97.2%, institution 100.0%
- 트리아지: 청크 807개 중 59.4%를 LLM 호출 없이 건너뜀, 그 상태에서 정답 신호 재현율 99.1%

## 기회 연결 (linking)
- 쌍(pairwise) 정밀도 100.0% · 재현율 100.0% · F1 1.0
- 한 기회로 온전히 묶인 실제 사업 비율 100.0%, 순수한 기회 비율 100.0%

## OCR (스캔 예산서)
- 문서 6건 · CER 0.0113 → 보정 후 0.0099
- 금액 토큰 정확도 100.0% → 100.0%

## 수기 작성 세트 (extractor: heuristic-v2)
- 정밀도 88.9% · 재현율 61.5% (기대 13건, 예측 9건)
- 필드 정확도: category 75.0%, commitment 62.5%, budget 75.0%, expected_year 75.0%

## 백테스트
- 입찰공고 48건 중 75.0%가 공고 이전에 공개 신호를 가짐
- 선행 기간 중앙값 308.0일 (p25 194.75, p75 378.75)
- 첫 신호 유형별 입찰 전환율:
  - `budget_line:*` n=13 → 100.0%
  - `council_mention:*` n=33 → 63.6%
  - `budget_line:committed` n=13 → 100.0%
  - `council_mention:planned` n=3 → 100.0%
  - `council_mention:declined` n=3 → 33.3%
  - `council_mention:committed` n=17 → 88.2%
  - `council_mention:reviewing` n=10 → 20.0%
