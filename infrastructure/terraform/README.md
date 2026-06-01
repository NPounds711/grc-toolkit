# Docs site infrastructure

S3 + CloudFront + ACM + GitHub OIDC role for the public docs site. Costs
well under $1/month at low traffic.

## What this creates

- A private S3 bucket holding the rendered site (no public access; CloudFront-only reads via Origin Access Control)
- A CloudFront distribution serving the bucket over HTTPS
- An ACM cert in us-east-1 if you set `custom_domain`
- An IAM role that the `docs-deploy` GitHub Action can assume via OIDC (no static keys in the repo)

## First-time setup

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars — set site_bucket_name and github_org_repo

terraform init
terraform plan
terraform apply
```

Outputs you need afterward:

| Output | Where it goes |
|---|---|
| `deploy_role_arn` | GitHub repo secret named `AWS_DEPLOY_ROLE_ARN` |
| `site_bucket` | GitHub repo secret named `AWS_SITE_BUCKET` |
| `cloudfront_distribution_id` | GitHub repo secret named `AWS_CLOUDFRONT_DISTRIBUTION_ID` |
| `cloudfront_domain_name` | The default public URL (until you wire a custom domain) |

Set the secrets:

```bash
gh secret set AWS_DEPLOY_ROLE_ARN --body "<deploy_role_arn output>"
gh secret set AWS_SITE_BUCKET --body "<site_bucket output>"
gh secret set AWS_CLOUDFRONT_DISTRIBUTION_ID --body "<cloudfront_distribution_id output>"
gh variable set AWS_REGION --body "us-east-1"
```

## Custom domain

When you have a domain ready:

1. Set `custom_domain = "grc-toolkit.example.com"` in `terraform.tfvars`.
2. Run `terraform apply`. ACM cert request is created.
3. Add the DNS validation record from `acm_validation_records` output to your DNS provider.
4. Run `terraform apply` again once the cert validates (a few minutes).
5. Add the `CNAME grc-toolkit.example.com → <cloudfront_domain_name>` record at your DNS provider.

## Cost expectations

| Item | Monthly cost (light traffic) |
|---|---|
| S3 storage (~10 MB site) | < $0.01 |
| S3 requests | < $0.10 |
| CloudFront data transfer (first 1 TB free tier) | $0 |
| CloudFront requests | < $0.05 |
| ACM cert | $0 |

At ~100 visitors/day expect under $0.50/month total. Set CloudWatch
billing alarms if you want to be sure.

## Teardown

```bash
terraform destroy
```

The S3 bucket has versioning enabled, so `terraform destroy` may fail if
non-current versions remain. Empty the bucket first:

```bash
aws s3api list-object-versions --bucket <site_bucket> \
  --query 'Versions[].{Key:Key,VersionId:VersionId}' --output json \
  | jq -c '.[]' | while read obj; do
      aws s3api delete-object \
        --bucket <site_bucket> \
        --key "$(echo $obj | jq -r .Key)" \
        --version-id "$(echo $obj | jq -r .VersionId)"
    done
```
