# 0003. 작업 큐는 arq(Redis), 스케줄은 워커 안의 cron

## 맥락
수집(시간 단위·일 단위·주 단위), 문서 처리, 연결, 추천 갱신, 알림 발송, 정기결제 갱신이 모두 비동기 작업입니다. 파이프라인 코드는 전부 `async`(SQLAlchemy async, httpx, Anthropic async client)입니다.

## 결정
- **arq**: asyncio 네이티브라 파이프라인 함수를 그대로 작업으로 씁니다. Celery처럼 동기 워커 안에서 이벤트 루프를 따로 돌릴 필요가 없습니다.
- **작업 ID = 작업 대상**(`process:<doc>:<hash>`, `ingest:<source>:<window>`): 같은 일을 두 번 넣어도 한 번만 실행됩니다(웹훅 재전송, 겹친 cron, 더블 클릭).
- **cron은 워커 안에서** KST 기준으로 실행합니다. arq는 cron 실행도 작업 ID로 중복 제거하므로 워커가 여러 대여도 한 번만 돕니다. Cloud Scheduler + HTTP 엔드포인트 조합보다 움직이는 부품이 적습니다.
- 모든 실행은 `job_runs` 테이블에 기록(`tracked` 데코레이터): 상태, 시도 횟수, 결과 요약, 오류, 원래 인자(재실행용). 한도 초과는 KST 자정 이후로, 서킷 오픈은 쿨다운 이후로, 일시 오류는 지수 백오프로 `Retry`.
- Cloud Run에서는 `mulmit worker`가 `$PORT`에 `/healthz`를 열고, arq의 Redis 하트비트가 끊기면 503을 돌려 인스턴스를 교체하게 합니다. 워커는 CPU 상시 할당 1대.

## 결과
- 얻은 것: 코드 한 벌(API와 워커가 같은 이미지), 운영 콘솔에서 작업 로그·재실행.
- 치른 비용: Redis가 큐의 진실 공급원이 됩니다. 재시작으로 잃은 작업은 `sweep_pending_documents` cron이 DB의 `pending` 문서를 다시 넣어 복구합니다.

## 다시 볼 조건
처리량이 워커 한 대를 넘으면 cron 전용 워커와 처리 워커를 나누고 처리 워커만 수평 확장합니다.
