# AWS deployment runbook (ECS Fargate + Terraform)

This is the actual step-by-step sequence to stand up the AWS deployment
described by the `.tf` files in this directory. It requires AWS credentials
and a GitHub CLI/UI session — none of this can be run by an AI assistant on
your behalf; every step here is something you run yourself.

Render and Vercel keep serving production traffic through every step below.
Nothing here touches `render.yaml` or the Vercel project until the final
cutover step.

## Cost

Rough monthly floor once this is live (`us-east-1`, one always-on Fargate
task, CloudFront `PriceClass_100`):

| Component | Est. monthly cost |
|---|---|
| ALB (base + LCUs at low traffic) | ~$16-20 |
| Fargate (0.5 vCPU / 1GB, 24/7) | ~$10-15 |
| EFS (a few GB) | <$1 |
| CloudFront (2 distributions, low traffic) | ~$1-3 |
| S3 (static build) | <$1 |
| CloudWatch Logs (14-day retention) | ~$1-2 |
| ECR storage | <$1 |
| SSM Parameter Store | $0 (within free tier at this volume) |
| **Total** | **≈ $30-45/month minimum** |

This is a real jump from Render/Vercel's $0 free tier. Go in with that
expectation. If `autoscaling_max_capacity` (default 2) is ever actually hit,
add roughly another Fargate task's worth of compute on top.

## Step 0 — Terraform state backend (manual, one-time)

Terraform can't create the S3 bucket/DynamoDB table it stores its own state
in, in the same config that references them. Create both first, with a
globally-unique bucket name:

```bash
aws s3api create-bucket --bucket insightai-rag-tfstate-<your-unique-suffix> --region us-east-1
aws s3api put-bucket-versioning --bucket insightai-rag-tfstate-<your-unique-suffix> --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket insightai-rag-tfstate-<your-unique-suffix> --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket insightai-rag-tfstate-<your-unique-suffix> --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws dynamodb create-table \
  --table-name insightai-rag-tf-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

Then edit `versions.tf`'s `backend "s3"` block and replace
`insightai-rag-tfstate-REPLACE_WITH_UNIQUE_SUFFIX` with the real bucket name.

## Step 1 — verify the container's UID

`efs.tf`'s access points assume `appuser` (created in `backend/Dockerfile`
via `useradd --create-home --shell /usr/sbin/nologin appuser`, no explicit
`--uid`) lands on UID/GID 1000, the usual first free UID on
`python:3.11-slim`. Verify this against the real image before applying —
if it's wrong, the container won't be able to write to its EFS mounts:

```bash
cd backend
docker build -t insightai-rag-backend .
docker run --rm insightai-rag-backend id appuser
```

If the UID/GID isn't 1000, update `local.efs_owner_uid` / `local.efs_owner_gid`
in `infra/efs.tf` to match before applying.

## Step 2 — init and configure

```bash
cd infra
terraform init
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: real gemini_api_key, api_key, groq_api_key,
# database_url (optional). Leave frontend_url = "" for now.
```

## Step 3 — validate and plan

```bash
terraform fmt -check -recursive .
terraform validate
terraform plan
```

Read the plan before applying. Expect roughly 35-45 resources to create:
one VPC (2 public subnets, IGW, route table), 3 security groups, 1 ECR
repo, up to 4 SSM parameters, 2 IAM roles + policies, 1 EFS filesystem + 2
mount targets + 3 access points, 1 ALB + target group + listener, 1 ECS
cluster + task definition + service, 2 autoscaling resources, 2 CloudFront
distributions, 1 S3 bucket + policy, 1 OIDC provider + IAM role for GitHub
Actions.

## Step 4 — apply (phase 1)

```bash
terraform apply
```

At this point the backend's `FRONTEND_URL` env var is empty — harmless,
since nothing is calling it from a real browser yet.

## Step 5 — apply (phase 2, fill in frontend_url)

```bash
terraform output frontend_cloudfront_domain
# add to terraform.tfvars:  frontend_url = "https://<that domain>"
terraform apply
```

This should show only an in-place update to the ECS task definition
(new revision with correct CORS) and a forced new deployment — not any
resource replacement.

## Step 6 — populate GitHub repo Variables/Secrets

From `terraform output`, set (repo Settings → Actions → Variables, unless noted):

| Variable | From |
|---|---|
| `AWS_REGION` | `terraform output aws_region` |
| `AWS_GITHUB_ACTIONS_ROLE_ARN` | `terraform output github_actions_role_arn` |
| `ECS_CLUSTER_NAME` | `terraform output ecs_cluster_name` |
| `ECS_SERVICE_NAME` | `terraform output ecs_service_name` |
| `FRONTEND_BUCKET_NAME` | `terraform output frontend_s3_bucket_name` |
| `FRONTEND_CLOUDFRONT_DISTRIBUTION_ID` | `terraform output frontend_cloudfront_distribution_id` |
| `BACKEND_CLOUDFRONT_DOMAIN` | `terraform output backend_cloudfront_domain` |
| `FRONTEND_CLOUDFRONT_DOMAIN` | `terraform output frontend_cloudfront_domain` |

And one repo **Secret**: `VITE_API_KEY` — same value as `terraform.tfvars`'s
`api_key`.

Via `gh` CLI, e.g.:

```bash
gh variable set AWS_REGION --body "$(terraform output -raw aws_region)"
gh variable set AWS_GITHUB_ACTIONS_ROLE_ARN --body "$(terraform output -raw github_actions_role_arn)"
# ...repeat for the rest
gh secret set VITE_API_KEY --body "your-api-key-value"
```

## Step 7 — first deploy (manual trigger, not a live push)

```bash
gh workflow run deploy-backend.yml
gh workflow run deploy-frontend.yml
```

Confirm both complete successfully before trusting the `push`-triggered path.

## Step 8 — smoke test

```bash
curl -i https://<backend_cloudfront_domain>/health
# expect 200

curl -i -H "X-API-Key: <your api_key>" https://<backend_cloudfront_domain>/documents
# expect 200, not 401 — confirms CloudFront is forwarding X-API-Key end to end
```

Then, by hand:
- Open `https://<frontend_cloudfront_domain>/`, upload a real PDF.
- Force a new ECS deployment (`aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment`) and confirm the uploaded document and its vector-store entries **survive** — this is the test that actually proves EFS persistence works, not just that it's declared in Terraform.
- Submit a chat query — confirm retrieval returns both the demo corpus and the freshly uploaded document.
- Submit a thumbs-up/down feedback event, confirm it lands in the EFS-backed feedback store.
- Load a deep-linked frontend route directly (e.g. `/documents`) — expect `200`, not S3's raw `403`.
- Run `gh workflow run monitoring.yml` and confirm it reports both AWS endpoints as up.

## Step 9 — cutover (only after Step 8 passes)

1. Merge the `aws-migration` branch to `main`.
2. Delete `render.yaml` from `main`.
3. Pause (don't delete yet) the Render service and the Vercel project — keep them as a fast rollback path for a few days.
4. Update `README.md`'s live-URL lines with the real CloudFront domains.

After a confidence period, delete the Render service and Vercel project for
real.

## Rollback

The running task always points at the `:latest` image tag. To roll back a
bad backend deploy:

```bash
# find a known-good sha tag in ECR, then:
docker pull <ecr_repository_url>:<known-good-sha>
docker tag <ecr_repository_url>:<known-good-sha> <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment
```

Not automated as its own pipeline — this scale doesn't need one.
