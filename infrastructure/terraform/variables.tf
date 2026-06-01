variable "aws_region" {
  description = "Primary AWS region. CloudFront ACM cert is always in us-east-1 regardless."
  type        = string
  default     = "us-east-1"
}

variable "site_bucket_name" {
  description = "S3 bucket name for the docs site origin. Must be globally unique."
  type        = string
}

variable "custom_domain" {
  description = "Optional custom domain (e.g. grc-toolkit.example.com). Set to null to use the default *.cloudfront.net URL."
  type        = string
  default     = null
}

variable "github_org_repo" {
  description = "GitHub <org>/<repo> string allowed to assume the deploy role. Example: nicolepounds/grc-toolkit"
  type        = string
}

variable "create_github_oidc_provider" {
  description = "Set true on the first run if no GitHub OIDC provider exists in this account yet. Set false thereafter."
  type        = bool
  default     = true
}
