# grc-toolkit

Dual-format GRC tooling for FedRAMP Rev 5 and 20x. **Author once, render to any framework.**

## Why this exists

CSPs running both Rev 5 and 20x today maintain two parallel sets of compliance
artifacts. The SSP says "we use FIDO2 MFA," the 20x KSI package says "WebAuthn
enforced," and they drift over time because they have no single source of truth.

This tool fixes that. You author a **capability** once — the actual security
claim about your system — and the tool generates whatever framework artifact
the audience needs: Rev 5 SSP control statements (Word), 20x machine-readable
packages (FRMR JSON), OSCAL, SOC 2 descriptions, whatever comes next.

When FedRAMP updates the KSI structure (which they do every couple of months),
nothing in your authored content breaks. The mapping layer absorbs the change.

## Architecture

```
                         ┌─────────────────────────────────┐
                         │  capabilities/*.yaml            │
                         │  (single source of truth)       │
                         └────────────────┬────────────────┘
                                          │
                         ┌────────────────┼────────────────┐
                         │                │                │
                         ▼                ▼                ▼
                  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
                  │ Rev 5 SSP    │ │ 20x FRMR    │ │ OSCAL / SOC2 │
                  │ Renderer     │ │ Renderer    │ │ Renderers    │
                  │ → .docx      │ │ → .json     │ │ → .json      │
                  └──────────────┘ └─────────────┘ └──────────────┘
                         ▲                ▲
                         │                │
                  ┌──────┴────────────────┴──────┐
                  │ sync/ — keeps frameworks/    │
                  │ up to date with upstream      │
                  │ (FRMR, NIST 800-53, RFCs)     │
                  └──────────────────────────────┘
```

Three rules that keep this from going stale:

1. **Capabilities never reference framework text verbatim.** They reference
   IDs (`KSI-IAM-01`, `IA-2(1)`). Framework text is pulled from `frameworks/`
   at render time.
2. **`frameworks/` is sync output, never hand-edited.** A daily GitHub Action
   pulls from `github.com/FedRAMP/docs` and the NIST OSCAL content repo.
3. **Drift tests fail PRs when a capability references something that no
   longer exists upstream.** You find out at PR time, not at customer time.

## Repo layout

| Path | Purpose | Who edits it |
|---|---|---|
| `capabilities/` | Source-of-truth security claims | Humans (authored content) |
| `frameworks/` | Synced framework definitions | Sync workflow only |
| `evidence/` | Per-cloud evidence collectors (bash, py, sql) | Humans (per cloud expertise) |
| `policies/` | OPA/Rego validation rules | Humans |
| `terraform/` | Reference modules per cloud | Humans (greenfield only) |
| `renderers/` | Framework-specific output generators | Humans (one per output format) |
| `sync/` | Upstream watchers + adapters | Humans (rarely) |
| `tests/` | Schema validation + drift tests | Humans |
| `samples/` | Generated example output (gitignored in production) | Renderers |

## Quick start

```bash
pip install -r requirements.txt

# Validate every capability against the schema, build the index
python -m renderers.shared.capability_loader

# Generate a Rev 5 SSP fragment (Word)
python -m renderers.rev5_ssp --out samples/ssp.docx

# Generate a 20x machine-readable package (JSON)
python -m renderers.fedramp_20x --out samples/20x.json \
    --csp "Acme Federal" --cso "Acme Workspace" --impact Low

# Run the drift tests (requires frameworks/ to be synced)
pytest tests/test_drift.py
```

## Adding a new capability

1. Copy `capabilities/iam/mfa-phishing-resistant.yaml` as a template.
2. Edit the `capability_statement` to describe what's actually true about
   your system. No framework jargon. Just the engineering reality.
3. Add the framework mappings under `satisfies:` — which KSIs, which Rev 5
   controls (and parts), which SOC 2 criteria.
4. List the evidence collectors that prove the claim.
5. Run `python -m renderers.shared.capability_loader` to validate.
6. Open a PR. CI runs schema validation + drift tests.

## Adding a new framework (e.g., HIPAA, PCI DSS 4.0)

1. Extend `capabilities/_schema.yaml` with a new key under `satisfies`.
2. Add a sync source under `sync/`.
3. Write a renderer under `renderers/<framework_name>.py`.
4. Existing capabilities pick up the new framework via additive mapping —
   no rewrite required.

## How updates flow

```
FedRAMP publishes new FRMR release
       │
       ▼
Daily sync workflow opens PR
       │
       ▼
Drift tests run on the PR
       │
       ├──► All pass → merge, nothing else to do
       │
       └──► Fail → comment names the broken capabilities → you update them
                   → drift tests pass → merge → renderers regenerate cleanly
```

The cost of a FedRAMP release is now a PR review, not a content rewrite.

## License

Apache 2.0. **This tool produces evidence and artifacts. A 3PAO must still
attest. Nothing in this repo is legal or compliance advice.**

## See also

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — deeper dive on each layer
- [`docs/3pao-validated.md`](docs/3pao-validated.md) — assessment provenance map
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to add capabilities, evidence, renderers
- [`infrastructure/terraform/`](infrastructure/terraform/) — AWS S3 + CloudFront + OIDC for the docs site
