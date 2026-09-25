# 기여 가이드

## 브랜치 전략: 짧게 사는 브랜치 + 트렁크

- `main`은 항상 배포 가능한 상태입니다. 직접 푸시하지 않고 PR로만 병합합니다(브랜치 보호: CI 통과 + 리뷰 1명).
- 작업 브랜치는 `feat/…`, `fix/…`, `chore/…`, `docs/…`처럼 목적을 앞에 두고, 가능하면 하루~이틀 안에 병합합니다. 오래 걸리는 기능은 플래그나 작은 단위로 나눠 먼저 병합합니다.
- 병합은 **squash merge**. PR 제목이 곧 커밋 메시지이므로 Conventional Commits 형식을 따릅니다.
- 릴리스는 `main`에서 `vX.Y.Z` 태그를 푸시하면 [배포 워크플로](.github/workflows/deploy.yml)가 돕니다. 되돌릴 때는 이전 리비전으로 트래픽을 옮기고([런북](docs/runbook.md)), 수정은 새 PR로 합니다.

## 커밋 메시지

```
feat(api): link 사전규격 to opportunities by bidNtceNoList
fix(web): keep BudgetLine labels readable in narrow cards
docs(adr): 0004 postgres-only search
```

범위(scope): `api`, `worker`, `web`, `infra`, `demo`, `eval`, `docs`, `ci`.

## PR 체크리스트
- [ ] 로컬에서 `make lint test` 통과
- [ ] 파이프라인·프롬프트·파서·랭킹 변경이면 `manage eval all` 전후 수치 첨부
- [ ] API 스키마 변경이면 `make gen-api` 결과 커밋
- [ ] 마이그레이션이 있으면 직전 버전 코드와 호환(확장 → 배포 → 축소)
- [ ] 되돌리기 어려운 결정이면 `docs/adr/`에 ADR 추가

## 코드 리뷰
- 리뷰어는 "동작하는가"보다 **"틀렸을 때 어떻게 드러나는가"**를 먼저 봅니다: 로그·메트릭·검토 대기열·테스트 중 어디서 보이는지.
- 외부 효과(결제·알림·외부 API 호출)는 멱등성과 재시도 경로를 확인합니다.
- 제안은 `nit:`(선택), `suggest:`(권장), `blocker:`(병합 전 필수)로 구분합니다.
