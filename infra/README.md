# AWS deployment runbook (Lambda + Terraform)

This is the actual step-by-step sequence to stand up the AWS deployment
described by the `.tf` files in this directory. It requires AWS credentials
and a GitHub CLI/UI session — none of this can be run by an AI assistant on
your behalf; every step here is something you run yourself.

Render and Vercel keep serving production traffic through every step below.
Nothing here touches `render.yaml` or the Vercel project until the final
cutover step.

## Cost

This design targets genuine near-$0 hosting — Lambda's free tier (1M
requests + 400,000 GB-seconds/month) and CloudFront's "Always Free" tier
(1TB egress + 10M requests/month, frontend only) are both *permanent*, not
12-month-limited:

| Component | Cost | Basis |
|---|---|---|
| Lambda compute | **$0** | Permanent free tier. At 2048MB and even a generous 500 req/month x 10s avg, that's ~10,000 GB-seconds — ~2.5% of the free tier. |
| Lambda Function URL | **$0** | No charge beyond the invocation itself — no ALB-style hourly base fee. |
| CloudFront (frontend only) | **$0** | "Always Free" tier, permanent. |
| S3 (data + frontend buckets) | **~$0.001-0.01/month** | A few MB total footprint at Standard storage rates. Genuinely non-zero, just imperceptibly so. |
| CloudWatch Logs (14-day retention) | **~$0.01-0.05/month** | This app's tiny structured-JSON log volume. |
| DynamoDB (state lock table) | **~$0.0001/month** | On-demand mode has no request-level free tier, but usage is a handful of requests per `terraform apply`. |
| ECR image storage | **$0 for 12 months, then ~$0.05-0.90/month** | 500MB/month free for year 1, then ~$0.10/GB-month on a ~590MB image. |
| **Total** | **≈ $0/month for year 1, then ≈ $0.05-1/month** | Never claim "$0 forever" — state the year-1-vs-after distinction plainly. |

## Step 0 — Terraform state backend (already done, don't touch)

The state S3 bucket (`insightai-rag-tfstate-618788620038`) and DynamoDB
lock table (`insightai-rag-tf-locks`) already exist and are referenced in
`versions.tf`. Nothing here needs to change for the Lambda redesign.

## Step 1 — verify locally before touching AWS

Confirm the Dockerfile/entrypoint.sh changes don't regress local dev —
`AWS_LAMBDA_FUNCTION_NAME` is never set locally, so `entrypoint.sh`'s
Lambda-specific branch should be entirely inert:

```bash
docker compose up --build
curl http://localhost:8000/health
# upload a PDF, ask a question, submit feedback via the frontend at
# http://localhost:8080 — confirm the full round trip still works.
```

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

Read the plan before applying. Expect **~20 resources**: 1 Lambda function
+ function URL + log group, 1 S3 data bucket + its 2 sub-resources, 1 IAM
role + 2 policies, 1 ECR repo + lifecycle policy, 1 S3 frontend bucket + 2
sub-resources, 1 CloudFront distribution (frontend only) + OAC + bucket
policy, 1 OIDC provider + IAM role + policy for GitHub Actions. Notably
**no VPC, no ALB, no ECS, no EFS, no autoscaling resources, and no backend
CloudFront distribution** — none of that exists in this design.

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

This should show only an in-place update to the Lambda function's
`environment` block — not any resource replacement.

## Step 6 — populate GitHub repo Variables/Secrets

From `terraform output`, set (repo Settings → Actions → Variables, unless noted):

| Variable | From |
|---|---|
| `AWS_REGION` | `terraform output aws_region` |
| `AWS_GITHUB_ACTIONS_ROLE_ARN` | `terraform output github_actions_role_arn` |
| `LAMBDA_FUNCTION_NAME` | `terraform output lambda_function_name` |
| `LAMBDA_FUNCTION_URL` | `terraform output lambda_function_url` (includes trailing slash) |
| `FRONTEND_BUCKET_NAME` | `terraform output frontend_s3_bucket_name` |
| `FRONTEND_CLOUDFRONT_DISTRIBUTION_ID` | `terraform output frontend_cloudfront_distribution_id` |
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
curl -i "$(terraform output -raw lambda_function_url)health"
# expect 200

curl -i -H "X-API-Key: <your api_key>" "$(terraform output -raw lambda_function_url)documents"
# expect 200, not 401
```

Then, by hand:
- `curl -N -H "X-API-Key: <your api_key>" "$(terraform output -raw lambda_function_url)chat/stream" -d '{"query": "hello"}' -H "Content-Type: application/json"` and confirm chunks arrive incrementally, not all at once at the end — proves `AWS_LWA_INVOKE_MODE`/the function URL's `invoke_mode` are both correctly wired to `RESPONSE_STREAM`, not just declared.
- Open the frontend, upload a real PDF, then force a cold start (`aws lambda update-function-configuration --function-name <fn> --environment "Variables={...current vars...,FORCE_COLD=1}"` or simply wait out the idle-recycle window) and confirm the upload + vector-store entries + a feedback event **survive** — this is the test that actually proves S3-sync persistence works, not just that it's declared in Terraform.
- Submit a chat query, confirm retrieval returns both the demo corpus and the freshly uploaded document.
- Fire two requests at the function URL at the same time (e.g. two terminal tabs) and confirm the second gets `429`, not a hang or a corrupted index — validates `reserved_concurrent_executions=1` is actually doing its job.
- Load a deep-linked frontend route directly (e.g. `/documents`) — expect `200`, not S3's raw `403`.
- Run `gh workflow run monitoring.yml` and confirm it reports both endpoints as up.

## Step 9 — cutover (only after Step 8 passes)

1. Merge the `aws-migration` branch to `main`.
2. Delete `render.yaml` from `main`.
3. Pause (don't delete yet) the Render service and the Vercel project — keep them as a fast rollback path for a few days.
4. Update `README.md`'s live-URL lines with the real Lambda Function URL / CloudFront domain.

After a confidence period, delete the Render service and Vercel project for
real.

## Rollback

The deployed function is pinned directly to a sha-tagged image (not a
mutable `:latest` the way the superseded ECS design worked). To roll back a
bad backend deploy:

```bash
aws lambda update-function-code \
  --function-name "$(terraform output -raw lambda_function_name)" \
  --image-uri "$(terraform output -raw ecr_repository_url):<known-good-sha>"
aws lambda wait function-updated --function-name "$(terraform output -raw lambda_function_name)"
```

Simpler than the ECS design's retag-and-force-deploy dance — no `:latest`
mutation involved. Not automated as its own pipeline — this scale doesn't
need one.
