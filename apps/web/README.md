# @mulmit/web

물밑의 고객용 웹과 운영 콘솔 (Next.js 16 App Router · React 19 · TypeScript · Tailwind v4 · TanStack Query).

```bash
pnpm install
API_ORIGIN=http://localhost:8000 pnpm dev   # http://localhost:3000
pnpm typecheck && pnpm lint && pnpm test && pnpm build
pnpm gen:api                                # FastAPI OpenAPI → src/lib/api/schema.d.ts
```

- `src/app/api/[...path]/route.ts` — BFF 프록시. 브라우저는 같은 오리진의 `/api/*`만 부르고, 세션 쿠키(httpOnly)와 `Idempotency-Key`를 FastAPI로 그대로 전달합니다.
- `src/lib/api/` — OpenAPI에서 생성한 타입 + `openapi-fetch` 클라이언트 + TanStack Query 훅. 백엔드 스키마가 바뀌면 CI의 드리프트 검사가 실패합니다.
- `src/components/charts/` — 외부 차트 라이브러리 없이 SVG로 그린 단일 시리즈 차트(툴팁·표 보기·다크 모드 포함).

환경 변수: `API_ORIGIN`(서버 측 프록시 대상), `NEXT_PUBLIC_SENTRY_DSN`(선택). 토스페이먼츠 클라이언트 키는 API의 `/api/billing`이 내려주며, 백엔드가 `fake` 결제 제공자로 설정되어 있으면 SDK 없이 테스트 결제 흐름을 탑니다.
