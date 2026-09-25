# 0008. 웹은 BFF 프록시 + httpOnly 쿠키 + OpenAPI 생성 타입

## 맥락
Next.js 웹과 FastAPI가 다른 오리진에서 돕니다. 토큰을 JS에서 다루면 XSS 한 번에 세션이 샙니다. 백엔드 스키마가 바뀌면 프런트가 조용히 깨지기 쉽습니다.

## 결정
- 브라우저는 같은 오리진의 `/api/*`만 호출하고, Next.js Route Handler(`app/api/[...path]/route.ts`)가 FastAPI로 전달합니다. 세션은 FastAPI가 발급하는 **httpOnly·SameSite=Lax JWT 쿠키**이며 JS는 볼 수 없습니다. CORS가 필요 없습니다.
- 프로덕션에서 FastAPI는 **내부 전용 ingress**입니다. 인터넷에서 닿는 것은 웹 서비스뿐입니다(토스 웹훅도 웹의 `/api/webhooks/toss`를 거쳐 들어옵니다).
- FastAPI의 OpenAPI 스키마를 커밋하고(`apps/web/openapi.json`) `openapi-typescript`로 타입을 생성해 `openapi-fetch` + TanStack Query 훅에서 씁니다. CI가 (1) 코드 ↔ `openapi.json`, (2) `openapi.json` ↔ 생성 타입의 불일치를 실패로 처리합니다.
- 변경 요청 중 과금이 걸린 것(브리프 생성, 플랜 변경, 크레딧 구매)은 클라이언트가 `Idempotency-Key`를 만들어 보내고 프록시가 그대로 전달합니다.

## 결과
- 얻은 것: 인증 토큰이 JS에 노출되지 않음, 스키마 불일치가 PR 단계에서 드러남.
- 치른 비용: 요청이 한 홉 늘어납니다(같은 리전 내부 통신).
