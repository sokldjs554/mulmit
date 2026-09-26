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

## 짧게 올렸다 내리기 (데모)

면접이나 검증용으로 몇 시간만 띄웠다가 지우는 순서입니다. 비용은 켜 둔 시간만큼 붙고, 대부분 Cloud SQL·Memorystore·상시 워커 1대에서 나옵니다. 결제 계정의 **예산 알림**을 먼저 걸어 두세요(알림일 뿐 자동으로 멈추지는 않습니다).

```bash
# 0. 새 프로젝트: Terraform이 켜는 API 중 IAM·Resource Manager는 첫 apply에서 전파를 못 기다릴 수 있어 미리 켭니다
gcloud config set project procurement-forecast-2026
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com iam.googleapis.com

# 1. 상태 버킷과 설정
gcloud storage buckets create gs://procurement-forecast-2026-tfstate --location=asia-northeast3 --uniform-bucket-level-access
cp demo.tfvars.example terraform.tfvars          # project_id 확인
terraform init -backend-config="bucket=procurement-forecast-2026-tfstate" -backend-config="prefix=app"
terraform apply                                  # 15~20분, Cloud SQL이 가장 오래 걸립니다

# 2. GitHub 연결: 출력된 4개 값을 Settings → Secrets and variables → Actions → Variables에
terraform output github_actions_variables
```

3. GitHub Actions에서 `Deploy (Cloud Run)`을 **main**에서 실행합니다(배포 자격은 main과 `v*` 태그에만 발급됩니다). 이미지 빌드 → 마이그레이션 → worker·api·web 배포 → 스모크 테스트까지 돕니다.

```bash
# 4. 데모 데이터 (README 둘러보기와 같은 규모 1.5 세계)
gcloud run jobs execute app-migrate --region asia-northeast3 --args=seed,--scale,1.5 --wait
gcloud run jobs execute app-migrate --region asia-northeast3 --args=demo,run --wait
gcloud run services describe app-web --region asia-northeast3 --format 'value(status.url)'

# 5. 내리기
terraform destroy
```

- 첫 `apply`가 "API has not been used in project … or it is disabled"로 멈추면 API 활성화가 전파되는 중입니다. 1~2분 뒤 `terraform apply`를 다시 실행하면 이어서 만듭니다.
- `destroy`가 `google_service_networking_connection`에서 "Producer services … still using this connection"으로 멈추면, Cloud SQL 삭제가 뒤에서 끝나길 기다리는 중입니다. 5~10분 뒤 `terraform destroy`를 다시 실행하세요. 이 시점에는 과금되는 자원(Cloud SQL·Redis·Cloud Run)은 이미 지워져 있습니다.
- 같은 프로젝트에서 일주일 안에 다시 올리면 Cloud SQL 인스턴스 이름(`app-pg16`)을 재사용할 수 없어 실패합니다. 새 프로젝트를 쓰거나 이름을 바꾸세요.
- `destroy`는 1단계에서 켠 API를 끄지 않습니다(`disable_on_destroy = false`). 켜진 API만으로는 비용이 없고, 프로젝트를 통째로 지우려면 `gcloud projects delete <프로젝트ID>`를 씁니다.
- `allow_destroy = true`는 Cloud SQL 삭제 보호를 끄고 원문 버킷을 비울 수 있게 합니다. 지우면 안 되는 데이터가 있는 스택에서는 켜지 마세요.

## 외부 키 켜기

```bash
printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets versions add anthropic-api-key --data-file=-
```

`terraform.tfvars`의 `mounted_external_secrets`에 `APP_ANTHROPIC_API_KEY = "anthropic-api-key"`를 넣고 `llm_provider = "anthropic"`으로 바꾼 뒤 `terraform apply`. 버전이 없는 시크릿을 참조하면 Cloud Run이 리비전을 띄우지 않으므로 순서가 중요합니다.

## 검증 범위

`terraform fmt -check`와 `terraform validate`(google provider 6.50.0)를 통과했습니다. 실제 GCP 프로젝트에 `plan/apply`한 적은 아직 없습니다. 위 "짧게 올렸다 내리기"가 첫 실제 적용의 순서입니다.
