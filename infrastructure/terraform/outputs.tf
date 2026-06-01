output "site_bucket" {
  description = "S3 bucket holding the static site contents."
  value       = aws_s3_bucket.site.bucket
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID. Use this for cache invalidations."
  value       = aws_cloudfront_distribution.site.id
}

output "cloudfront_domain_name" {
  description = "Public URL of the site (CloudFront default domain). Custom domain takes precedence if set."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "deploy_role_arn" {
  description = "IAM role ARN the GitHub Actions docs-deploy workflow assumes via OIDC."
  value       = aws_iam_role.docs_deploy.arn
}

output "acm_validation_records" {
  description = "DNS records to add to validate the ACM cert (only set when custom_domain is configured)."
  value       = var.custom_domain == null ? [] : [for d in aws_acm_certificate.site[0].domain_validation_options : d]
  sensitive   = false
}
