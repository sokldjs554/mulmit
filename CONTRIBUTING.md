# 기여 가이드

## 브랜치 전략: 짧게 사는 브랜치 + 트렁크

- `main`은 항상 배포 가능한 상태입니다. 변경은 PR로만 병합하고, CI 5개 잡(API·Web·Terraform·Docker 이미지 2개)이 PR의 최신 커밋에서 통과해야 병합합니다. base가 앞서 있으면 main을 병합해 CI를 다시 돌린 뒤 병합합니다.
- 권장 저장소 설정(Settings → Branches → `main`): "Require a pull request before merging", "Require status checks to pass"에 위 5개 잡.
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
- [ ] 파이프라인·프롬프트·파서·랭킹 변경이면 `manage eval all` 전후 수치 첨부 (프롬프트·모델 설정 변경은 `make eval-llm` 비교표도)
- [ ] API 스키마 변경이면 `make gen-api` 결과 커밋
- [ ] 마이그레이션이 있으면 직전 버전 코드와 호환(확장 → 배포 → 축소), 인덱스는 `CONCURRENTLY`
- [ ] 쿼리·인덱스 변경이면 `make bench` 전후 실행 계획 첨부
- [ ] 되돌리기 어려운 결정이면 `docs/adr/`에 ADR 추가

## 코드 리뷰
- 지금은 1인 저장소라 다른 사람의 승인을 받을 수 없습니다. 그래서 PR마다 자동 코드 리뷰를 돌려 결과를 PR에 남기고, 지적마다 반영하거나 반영하지 않는 이유를 답글로 단 뒤 병합합니다. #7은 Claude Code `/code-review`의 지적 15건 중 13건을 반영하고 2건은 이유를 남겼습니다. 봇이 올린 의존성 PR도 검토합니다(#6은 액션 10개의 깨지는 변경을 우리 입력값과 대조).
- 초기 구축(2026-09-25까지, 커밋 34개)은 main에 직접 커밋했습니다. #6부터 PR로 병합합니다.
- 리뷰어는 "동작하는가"보다 **"틀렸을 때 어떻게 드러나는가"**를 먼저 봅니다: 로그·메트릭·검토 대기열·테스트 중 어디서 보이는지.
- 외부 효과(결제·알림·외부 API 호출)는 멱등성과 재시도 경로를 확인합니다.
- 제안은 `nit:`(선택), `suggest:`(권장), `blocker:`(병합 전 필수)로 구분합니다.
