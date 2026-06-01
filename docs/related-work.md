# Related work

This page describes how `grc-toolkit` relates to existing projects in the
GRC engineering space — what we borrow, what we do differently, and why.

## Direct attribution

### `GRCEngClub/claude-grc-engineering`

The [GRC Engineering Club](https://grcengclub.com) maintains the closest
existing project in this space:
[GRCEngClub/claude-grc-engineering](https://github.com/GRCEngClub/claude-grc-engineering)
(MIT licensed). Their work pre-dates this project and informed several
architectural decisions here.

**What we adopted directly from them:**

- **The finding schema** (`schemas/finding.schema.json`) is adapted from
  their [schemas/finding.schema.json](https://github.com/GRCEngClub/claude-grc-engineering/blob/main/schemas/finding.schema.json)
  with only the `$id` re-homed. Connector interoperability is more
  valuable than schema novelty. See `schemas/NOTICE.md`.
- **The connector lifecycle** — every connector module exposes setup,
  status, and collect entry points. This is convention rather than code.
- **The connector / framework / persona separation** as a directory
  structure idea, though we implement it differently.

**Where we diverge — and why:**

| Aspect | claude-grc-engineering | grc-toolkit |
|---|---|---|
| Primary execution environment | Claude Code plugin marketplace | Standalone Python CLI |
| Implementation-status determination | LLM-driven (a Claude prompt reads evidence and reasons about whether a control is implemented) | Deterministic Python aggregators (auditable code; same inputs → same outputs, byte for byte) |
| FedRAMP Rev 5 SSP output | Not a primary output | First-class — Word doc generated from the same source as the 20x package |
| FedRAMP 20x machine-readable (FRMR) output | Guidance plugin; output via LLM | Native renderer that emits FRMR-shaped JSON |
| OSCAL output | LLM-mediated | Renderer (planned) that emits OSCAL 1.2.0 directly |
| Reproducibility for 3PAOs | Bounded by model variance | Byte-identical given the same inputs |
| Dependency footprint | Requires Claude Code | Python 3.12 + a few libraries; no external AI runtime |

The differentiator that matters most for FedRAMP-specifically is
reproducibility. A 3PAO must be able to verify a CSP's submission by
re-running the tool and getting an identical result. LLM outputs are
not bitwise reproducible — Claude's response varies between runs even
at temperature 0 on the same prompt. Deterministic Python is. That's
the line we draw, and the reason we don't depend on Claude Code at
runtime.

We use them as the reference connector / evidence schema; they remain
the canonical "compliance-as-an-agentic-workflow" project. Different
tools for different jobs.

## Other projects worth knowing about

| Repo | What it does | How it relates |
|---|---|---|
| [prowler-cloud/prowler](https://github.com/prowler-cloud/prowler) | Mature multi-cloud security scanner (~580 AWS checks, plus Azure / GCP / K8s). Apache 2.0. | Best raw input for our aggregators. Future versions will support reading Prowler JSON as evidence in addition to direct API calls. |
| [turbot/steampipe](https://github.com/turbot/steampipe) + [turbot/powerpipe](https://github.com/turbot/powerpipe) | SQL queries against cloud APIs via Postgres FDW | Same architectural role as Prowler — a possible evidence source. We don't wrap Steampipe directly today; the aggregator pattern means we could. |
| [cloudquery/cloudquery](https://github.com/cloudquery/cloudquery) | ELT framework, cloud state into a warehouse | The Confluent FedRAMP 20x submission used this pattern. Suitable for organizations already running a data warehouse. |
| [paramify/fedramp-20x-pilot](https://github.com/paramify/fedramp-20x-pilot) | Paramify's Phase 1 submission. AWS-only. | The clearest public example of a real 20x submission. Their evidence-collection pattern (bash + AWS CLI + JSON) informs our `evidence/` directory. |
| [paramify/evidence-fetchers](https://github.com/paramify/evidence-fetchers) | Python evidence collectors extracted from the pilot | Conceptual sibling to our `connectors/` directory. |
| [FedRAMP/docs](https://github.com/FedRAMP/docs) | Official FedRAMP machine-readable documentation | Authoritative source. Our `sync/frmr_sync.py` pulls from here daily. |
| [FedRAMP/community](https://github.com/FedRAMP/community) | FedRAMP working groups + discussions | Watch for RFC adoption signals. Our `sync/rfc_watcher.py` scans for new RFCs. |
| [NIST/oscal-content](https://github.com/usnistgov/oscal-content) | Official OSCAL catalogs (800-53r5, etc.) | Source for the OSCAL renderer (planned). |

## What's not in here that you might expect

- **Commercial GRC platforms** (Drata, Vanta, Tugboat, Paramify Cloud,
  InfusionPoints AuditShield, etc.) — these are excellent tools and many
  CSPs use them. They are closed-source and pay-to-play; the audience
  for an open-source toolkit is people who can't or don't want to use
  them.
- **General OPA / Rego policy libraries** (e.g. open-policy-agent/library)
  — referenced indirectly via the `policies/` directory's Rego rules but
  not depended on as a project.

## How to update this page

When adopting a new pattern from an external project, add it to "Direct
attribution" above with what was borrowed and the upstream commit / file
reference. Add a NOTICE entry if a license requires it. License
compatibility check is part of every PR that touches `schemas/` or any
folder containing borrowed code.
