# mulmit (API · worker · pipeline)

Python 3.11 · FastAPI · SQLAlchemy 2 (async) · Alembic · arq · pgvector. 전체 소개는 [루트 README](../../README.md).

```bash
uv sync
uv run mulmit db upgrade                 # 마이그레이션
uv run mulmit seed --anchor 2026-09-25   # 기관 사전 · 수집원 · 데모 테넌트 · 합성 세계
uv run mulmit demo run                   # 전체 파이프라인을 프로세스 안에서 실행
uv run mulmit eval all --record          # 추출·연결·OCR·수기 세트 평가
uv run uvicorn mulmit.api.app:create_app --factory --reload
uv run mulmit worker                     # arq 워커 + cron (Cloud Run에서는 $PORT에 /healthz)
uv run pytest                            # 통합 테스트는 PostgreSQL(pgvector)·Redis 필요 (make infra)
uv run ruff check . && uv run mypy
```

설정은 모두 `MULMIT_` 환경 변수입니다([`settings.py`](src/mulmit/settings.py)). 기본값만으로 오프라인에서 동작합니다: 규칙 기반 추출기, 해싱 임베더, 테스트 결제사, 합성 수집원.
