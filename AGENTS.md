# AGENTS.md — 이 저장소에서 일하는 코딩 에이전트를 위한 안내

## 구조
- `apps/api` — Python 3.11, FastAPI, SQLAlchemy 2 async, arq, Alembic. 패키지 `mulmit`.
- `apps/web` — Next.js 16 App Router, React 19, TypeScript, Tailwind v4, TanStack Query. 이 디렉터리의 `AGENTS.md`(Next.js 제공)를 먼저 읽을 것: 버전별 API가 학습 데이터와 다릅니다.
- `infra/terraform` — GCP. `docs/` — ADR, 아키텍처, 평가, 런북.

## 자주 쓰는 명령
```bash
make infra                      # PostgreSQL(pgvector)·Redis·Mailpit
cd apps/api && uv sync && uv run pytest          # 통합 테스트는 위 인프라 필요
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run mulmit seed && uv run mulmit demo run && uv run mulmit eval all
cd apps/web && pnpm install && pnpm typecheck && pnpm lint && pnpm test && pnpm build
make gen-api                    # FastAPI 스키마가 바뀌면 반드시 실행하고 결과를 커밋
```

## 규칙
- 파이프라인·파서·프롬프트·연결·랭킹을 바꾸면 `mulmit eval all` 전후 수치를 PR에 적습니다. CI 품질 게이트(추출·연결 P/R ≥ 0.95 등)를 낮추지 마세요.
- **정답 누수 금지**: 합성 레코드의 `structured["truth_id"]` 등 평가용 필드는 파이프라인 코드에서 읽지 않습니다.
- LLM 출력은 반드시 `domain/grounding.py` 검증을 거칩니다. 검증을 우회하는 경로를 만들지 마세요.
- 시간은 `mulmit.clock`(`now_utc`, `today_kst`, `KST`)으로. `date.today()`·naive datetime 금지.
- 금액은 원 단위 `int`. 파싱은 `domain/krw.py`만 사용.
- 과금·알림처럼 외부 효과가 있는 코드는 멱등 키를 가집니다. 새 경로를 만들면 중복 호출 테스트를 추가합니다.
- 테스트를 건너뛰거나(`skip`, `xfail`) 기준을 낮춰 CI를 통과시키지 않습니다.
- 커밋은 Conventional Commits(`feat(api): …`, `fix(web): …`). 비밀값·`.env`는 커밋하지 않습니다.
