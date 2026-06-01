# grc-toolkit

**Pick your FedRAMP path — Rev 5 or 20x. Either way, your source of truth doesn't change.** Deterministic Python aggregators pull live state from AWS / GCP / Azure / Okta / SIEM / IdP, turn it into reproducible per-control determinations, and emit whichever output format the PMO expects: Word SSP for traditional Rev 5 review, OSCAL JSON for machine-readable Rev 5, FRMR JSON for 20x.

## What problem this solves

**Compliance documentation is hand-typed today.** An engineer reads the AWS console, types a paragraph in Word that says "we use FIDO2 hardware keys," and a 3PAO reads that paragraph and tries to verify it. The paragraph and the live system drift the moment someone changes an Okta policy. Nobody catches it until the next assessment.

The fix is to **never let a human hand-type the implementation status**. Instead, the toolkit:

1. **Connectors** call the source system directly (Okta, AWS IAM, KMS, CloudTrail, …) and return raw evidence.
2. **Aggregators** apply deterministic rules to that evidence and emit one per-control determination, timestamped, with the live numbers ("3/3 privileged users compliant; 4/4 total humans compliant").
3. **Renderers** take those determinations and emit whatever FedRAMP-shaped document the CSP needs.

The implementation status is **observed**, not asserted. A 3PAO can re-run the tool and get byte-identical output, because it's deterministic Python — not an LLM reasoning over the evidence.

## Pick your FedRAMP path

A CSP picks **one** FedRAMP path. The toolkit supports both today, so you don't have to refactor your authoring layer if you change paths or migrate from Rev 5 to 20x later:

- **Rev 5 (traditional)** — Submit a Word SSP for 3PAO review. What most CSPs do today.
- **Rev 5 (machine-readable)** — FedRAMP PMO has stated machine-readable Rev 5 submissions can be in **JSON, YAML, or OSCAL**. The toolkit emits all three from the same source.
- **20x** — Submit a FRMR JSON package keyed by KSI. Optional today (Phase 2 pilot ended March 2026); general availability later in 2026.

You **don't run more than one path at a time** — that's not how FedRAMP works. But because the source is the same set of aggregators, switching paths later doesn't require rewriting any compliance logic. That's the actual value: **future-proofing your evidence pipeline against PMO direction.**

The renderers all consume the same determinations:

| Output | Format | Audience | Status |
|---|---|---|---|
| `rev5_ssp.py` | Word (`.docx`) | Traditional Rev 5 3PAO review | Working |
| `rev5_machine_readable.py` | JSON or YAML | PMO-permitted machine-readable Rev 5 | Working |
| `oscal_ssp.py` | OSCAL 1.2.0 JSON | PMO-permitted machine-readable Rev 5 (NIST schema) | Working |
| `fedramp_20x.py` | FRMR JSON | FedRAMP 20x submission | Working |

Same capability authored once. Render to whichever output your customer demands.

## Architecture

```
        ┌────────────────────────────────────────────────────┐
        │  Connectors                                        │
        │  - aws_iam, aws_kms, aws_s3, aws_cloudtrail        │
        │  - gcp_iam, gcp_storage, gcp_audit                 │
        │  - azure_identity, azure_storage                   │
        │  - okta, github, siem, knowbe4                     │
        └──────────────────────┬─────────────────────────────┘
                               │ raw evidence (normalized JSON)
                               ▼
        ┌────────────────────────────────────────────────────┐
        │  Aggregators (deterministic Python, one per area)  │
        │  - mfa.py         → IA-2, IA-2(1), IA-2(2), IA-2(8)│
        │                     KSI-IAM-01, KSI-IAM-02         │
        │  - encryption.py  → SC-13, SC-28, KSI-SVC-04       │
        │  - logging.py     → AU-*, KSI-MLA-*                │
        │  - net_seg.py     → SC-7, KSI-CNA-01               │
        └──────────────────────┬─────────────────────────────┘
                               │ ControlDetermination per control
                               │ {status, observed_at, statement, metrics}
                               ▼
        ┌────────────────────────────────────────────────────┐
        │  Manual controls (separate first-class artifact)   │
        │  - personnel/background-checks.yaml                │
        │  - physical/cloud-provider-attestation.yaml        │
        │  Human-attested + attached evidence documents      │
        └──────────────────────┬─────────────────────────────┘
                               │ merged corpus
                               ▼
        ┌────────────────────────────────────────────────────┐
        │  Renderers                                         │
        │  - rev5_ssp.py    → Rev 5 SSP (Word)               │
        │  - fedramp_20x.py → FRMR machine-readable package  │
        │  - oscal_ssp.py   → OSCAL 1.2.0 SSP   (planned)    │
        │  - dashboard.py   → HTML coverage matrix (planned) │
        └────────────────────────────────────────────────────┘
```

Three properties make this hold up over time:

1. **Aggregators are deterministic Python**, not LLM prompts. Same inputs
   → same outputs, byte for byte. A 3PAO can reproduce your submission
   by re-running the tool. No model variance.
2. **Capabilities don't embed framework text.** They reference IDs.
   When FedRAMP renames a KSI, the loader's drift tests fail at PR time,
   not at customer time.
3. **Aggregator-backed vs declared capabilities are clearly separated.**
   Live-state controls go through aggregators (timestamped, reproducible).
   Manual controls live under `manual-controls/` with prose + attached
   evidence documents and a signed attestation.

## Repo layout

| Path | Purpose | Who edits |
|---|---|---|
| `aggregators/` | Deterministic per-control-area modules. Each declares the controls it determines and the connectors it needs. | Engineers |
| `connectors/` | Boundary to cloud / SaaS APIs. No interpretation. Returns raw evidence dicts. Supports fixture mode for CI/demos. | Engineers |
| `capabilities/` | Routing manifests — point at an aggregator and declare framework mappings | Engineers |
| `manual-controls/` | Human-attested controls + attached document evidence | GRC / compliance leads |
| `renderers/` | One output format per file (Rev 5 Word, Rev 5 JSON/YAML, OSCAL, 20x FRMR) | Engineers (one per format) |
| `sync/` | Daily sync of FedRAMP/docs and RFC watchers | Maintainers |
| `schemas/` | JSON Schemas (finding schema borrowed from GRCEngClub with attribution) | Engineers |
| `tests/` | Schema validation, drift tests, aggregator tests with fixtures | Engineers |
| `tests/fixtures/` | Sample connector outputs so renderers and tests run without real creds | Engineers |
| `policies/` | OPA / Rego rules used by aggregators or by external validators | Engineers |
| `terraform/` | Reference modules per cloud (greenfield only) | Engineers |
| `infrastructure/terraform/` | AWS infra for hosting the docs site | Maintainers |

## Quick start

```bash
pip install -r requirements.txt

# Validate every capability against the schema, build the index
python -m renderers.shared.capability_loader

# Run all tests (uses tests/fixtures/ — no AWS/Okta credentials required)
pytest -v

# --- Rev 5 path ---
# Word SSP for traditional 3PAO review
python -m renderers.rev5_ssp --out samples/rev5_ssp.docx --fixtures tests/fixtures

# Machine-readable Rev 5 — JSON, YAML, or OSCAL (PMO permits all three)
python -m renderers.rev5_machine_readable --out samples/rev5.json --fixtures tests/fixtures
python -m renderers.rev5_machine_readable --out samples/rev5.yaml --fixtures tests/fixtures
python -m renderers.oscal_ssp --out samples/rev5_oscal.json --fixtures tests/fixtures \
    --csp "Acme Federal" --cso "Acme Workspace" --impact Moderate

# --- 20x path ---
# FRMR machine-readable package
python -m renderers.fedramp_20x --out samples/20x.json --fixtures tests/fixtures \
    --csp "Acme Federal" --cso "Acme Workspace" --impact Low
```

To run against real cloud / SaaS state, set the connector environment
variables (`OKTA_DOMAIN`, `OKTA_API_TOKEN`, AWS profile, etc.) and omit
the `--fixtures` flag.

## Adding a new aggregator

1. Pick a control area (encryption-at-rest, audit logging, network
   segmentation, etc.).
2. Create `aggregators/<area>.py`. Subclass `BaseAggregator`. Declare
   `SUPPORTED_CONTROLS_REV5`, `SUPPORTED_KSIS`, `SUPPORTED_SOC2`,
   `SUPPORTED_CSF2`. Implement `determine(ctx)` returning a list of
   `ControlDetermination` objects, one per control.
3. Reuse existing connectors under `connectors/`, or add new ones with
   matching fixture files under `tests/fixtures/<connector_id>/`.
4. Create `capabilities/<area>/<slug>.yaml` with `aggregator: aggregators.<area>`
   and a `satisfies:` block listing the controls (must be a subset of
   the aggregator's `SUPPORTED_*` lists).
5. Add tests under `tests/test_aggregator_<area>.py`. CI requires them.

## Adding a manual control

1. Create `manual-controls/<area>/<slug>.yaml`. Validate against
   `manual-controls/_schema.yaml`.
2. Drop supporting evidence documents (PDFs, screenshots, etc.) under
   `manual-controls/artifacts/`. **Do not commit anything containing PII
   or live federal customer data.**
3. Set `attestation.declared_by` and `attestation.declared_at`. CI
   warns on attestations >12 months old.

## How updates flow

```
FedRAMP publishes a new FRMR release
       │
       ▼
Daily sync workflow opens a PR
       │
       ▼
Drift tests run on the PR
       │
       ├──► All pass → merge, nothing else to do
       │
       └──► Fail → comment names the broken capabilities / aggregators
                   → engineer updates the affected aggregator
                   → drift tests pass → merge → next render cycle picks up
                     the new control text from the synced framework data
```

The cost of a FedRAMP release becomes a PR review, not a content rewrite.

## Related work

This project sits in a small ecosystem. The closest existing project,
`GRCEngClub/claude-grc-engineering`, takes a different architectural
approach (Claude Code plugins, LLM-driven determinations). We borrowed
their finding schema with attribution and explicitly cite them and
several other projects in [`docs/related-work.md`](docs/related-work.md).

## License

Apache 2.0. **This tool produces evidence and artifacts. A 3PAO must
still attest. Nothing in this repo is legal or compliance advice.**

## See also

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — deeper dive on each layer
- [`docs/related-work.md`](docs/related-work.md) — how we relate to other GRC engineering projects
- [`docs/3pao-validated.md`](docs/3pao-validated.md) — assessment provenance map
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to add aggregators, connectors, manual controls
- [`infrastructure/terraform/`](infrastructure/terraform/) — AWS S3 + CloudFront + OIDC for the docs site
