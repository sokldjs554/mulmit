# infra/terraform — GCP (서울 리전)

```
             인터넷
               │
        ┌──────▼───────┐   VPC egress(ALL)   ┌──────────────┐  Private IP  ┌──────────────┐
        │ Cloud Run    ├────────────────────►│ Cloud Run    ├─────────────►│ Cloud SQL    │
        │ app-web   │   run.app(내부)      │ app-api   │              │ PG16+pgvector│
        └──────────────┘                     │ (internal)   ├──────┐       └──────────────┘
                                             └──────────────┘      │       ┌──────────────┐
        ┌──────────────┐  Private IP                               └──────►│ Memorystore  │
        │ Cloud Run    ├───────────────────────────────────────────────────►│ Redis 7.2    │
        │ app-worker│  arq 큐 + cron, CPU 상시 할당, 1대                  └──────────────┘
        └──────┬───────┘
               └── GCS(원문 PDF/HWP), Secret Manager, 공공 API·Claude API(직접 egress)
```

| 리소스 | 파일 | 메모 |
|---|---|---|
| Artifact Registry, GCS 버킷, API 활성화 | `main.tf` | 30일 지난 이미지 정리, 원문은 90일 후 Nearline |
| VPC, 서브넷(Direct VPC egress), Private Service Access | `network.tf` | 커넥터 없이 Cloud Run → VPC |
| Cloud SQL PostgreSQL 16, Memorystore Redis | `data.tf` | 공인 IP 없음, TLS 강제, PITR 백업(03:00 KST) |
| Secret Manager | `secrets.tf` | DB/Redis URL·JWT·Fernet 키는 생성, 외부 키는 빈 시크릿으로 생성 |
| Cloud Run api / worker / web, 마이그레이션 Job | `run.tf` | 이미지·명령은 배포 워크플로가 소유(`ignore_changes`) |
| 서비스 계정·IAM | `iam.tf` | 런타임/웹/배포자 분리, 최소 권한 |
| Workload Identity Federation | `wif.tf` | 이 저장소의 `main`·`v*` 태그만 배포 자격 획득, JSON 키 없음 |

## 처음 올리기

```bash
gcloud storage buckets create gs://<project>-tfstate --location=asia-northeast3 --uniform-bucket-level-access
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # project_id 등 수정
terraform init -backend-config="bucket=<project>-tfstate" -backend-config="prefix=app"
terraform apply                                 # 서비스는 placeholder 이미지로 먼저 뜹니다
terraform output github_actions_variables       # GitHub Actions Variables에 등록
```

그다음 GitHub에서 `Deploy (Cloud Run)` 워크플로를 실행하거나 `v*` 태그를 푸시하면 이미지 빌드 → 마이그레이션 Job → worker·api·web 순으로 배포됩니다.

## 외부 키 켜기

```bash
printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets versions add anthropic-api-key --data-file=-
```

`terraform.tfvars`의 `mounted_external_secrets`에 `APP_ANTHROPIC_API_KEY = "anthropic-api-key"`를 넣고 `llm_provider = "anthropic"`으로 바꾼 뒤 `terraform apply`. 버전이 없는 시크릿을 참조하면 Cloud Run이 리비전을 띄우지 않으므로 순서가 중요합니다.

## 검증 범위

`terraform fmt -check`와 `terraform validate`(google provider 6.50.0)를 통과했습니다. 실제 GCP 프로젝트에 `plan/apply`한 적은 없습니다.
