# Architecture

## The core idea

A FedRAMP control is either:

- **Technical** — observable from a live cloud / SaaS API. MFA enrolment,
  TLS configuration, encryption coverage, audit-log integrity, etc.
- **Manual** — a human assertion plus document evidence. Background
  checks, physical security at the cloud provider, executive policy
  approvals, etc.

This toolkit treats them as two separate kinds of artifact and renders
them into a single output package alongside each other.

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 1 — Connectors                                        │
│  Boundary to live source systems. No interpretation.         │
│  AWS / GCP / Azure / Okta / GitHub / SIEM / KnowBe4 / etc.   │
└──────────────────────────────────┬───────────────────────────┘
                                   │ raw evidence
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 2 — Aggregators                                       │
│  Deterministic Python per control area. Pull from connectors,│
│  apply rules, emit one ControlDetermination per control.     │
└──────────────────────────────────┬───────────────────────────┘
                                   │ ControlDetermination
                                   │ {status, observed_at, statement, metrics}
                                   ▼
                                   │            ┌──────────────────────────────┐
                                   │            │ Layer 3 — Manual controls    │
                                   │            │ Human-attested + attached    │
                                   │            │ document evidence.           │
                                   │            └──────────────────────────────┘
                                   │                          │
                                   └────────┬─────────────────┘
                                            ▼
                          ┌──────────────────────────────────┐
                          │  Layer 4 — Renderers             │
                          │  Rev 5 SSP (.docx)               │
                          │  FedRAMP 20x (FRMR JSON)         │
                          │  OSCAL SSP (planned)             │
                          │  Coverage matrix HTML (planned)  │
                          └──────────────────────────────────┘
```

## Why deterministic Python and not an LLM

The closest existing project, `GRCEngClub/claude-grc-engineering`, uses
LLM prompts as the determination engine. Their commands like
`/grc-engineer:gap-assessment` send evidence to Claude and read the
response. That's a perfectly reasonable architecture for many GRC
problems.

For FedRAMP authorization specifically it doesn't work, because:

1. A 3PAO must be able to **reproduce** the CSP's submission. They re-run
   the tool, expect identical output. LLM outputs vary at temperature 0.
   Deterministic Python doesn't.
2. The implementation logic must be **inspectable**. A 3PAO can read the
   Python code that decides "this user counts as privileged" and disagree
   with it. They cannot inspect a model's reasoning the same way.
3. The tool runs in environments that **cannot install Claude Code**.
   A hardened bastion in a FedRAMP boundary doesn't have unrestricted
   network access; calling an external API per render is a non-starter.

See `docs/related-work.md` for the full comparison.

## Connector responsibilities (and non-responsibilities)

A connector:

- Authenticates to a source system (AWS profile, Okta API token, etc.).
- Returns raw evidence dicts that mirror the source system's native shape.
- Supports **fixture mode** — when `ctx.fixture_mode=True`, reads the
  same shape from JSON files under `tests/fixtures/<connector_id>/`
  instead of calling APIs.

A connector NEVER:

- Decides whether a configuration is compliant.
- Mutates source-system state.
- Mixes data from multiple sources (cross-source synthesis is the
  aggregator's job).

The single-responsibility separation is what makes the architecture
swappable. Future versions can replace bespoke connectors with Prowler
JSON / CloudQuery rows / Steampipe queries without aggregators needing
to change.

## Aggregator responsibilities

An aggregator:

- Declares which controls it determines (as Python class attributes
  the loader uses for validation):
  - `SUPPORTED_CONTROLS_REV5: list[str]`
  - `SUPPORTED_KSIS: list[str]`
  - `SUPPORTED_SOC2: list[str]`
  - `SUPPORTED_CSF2: list[str]`
- Pulls raw evidence by instantiating the connectors it needs.
- Applies deterministic rules to produce one `ControlDetermination`
  per control it covers. Each carries:
  - `status` — Implemented / Partially Implemented / Planned / Inconclusive / Not Applicable / Alternative Implementation
  - `observed_at` — ISO 8601 UTC timestamp
  - `statement` — auto-generated narrative with real numbers
  - `metrics` — structured details (counts, percentages, lists of non-compliant resources)
  - `evidence_refs` — pointers to the connector calls / files that backed the determination
  - `non_compliant` — list of resources that failed the rule
  - `rationale` — optional free-text justification

Aggregators are pure functions of (evidence, configuration). No I/O
side effects outside connector calls. Easily testable with fixtures.

## Capability YAML — a thin manifest

For aggregator-backed capabilities, the YAML is just a routing manifest:

```yaml
id: cap-mfa-phishing-resistant
title: Phishing-resistant MFA for all human users
aggregator: aggregators.mfa

satisfies:
  fedramp_rev5: [{control: IA-2}, {control: IA-2(1)}, ...]
  fedramp_20x:  [{ksi: KSI-IAM-01}, {ksi: KSI-IAM-02}]
  soc2:         [{criterion: CC6.1}]

provenance:
  last_reviewed: 2026-06-01
```

The loader validates that everything in `satisfies:` is a subset of the
aggregator's `SUPPORTED_*` lists. If you add a control to the YAML that
the aggregator can't determine, CI fails — before a customer sees a
"Not Documented" entry in an SSP.

## Manual controls — separate first-class artifact

Manual controls live under `manual-controls/<area>/<slug>.yaml`. They
carry the human-authored prose, framework mappings, and pointers to
attached document evidence under `manual-controls/artifacts/`.

The renderer sections them distinctly so a 3PAO can tell at a glance
which controls are **automatically verified** vs. **attested**.

A manual control's attestation expires (`attestation.next_review`).
CI warns when attestations are stale.

## Render-time flow

```
caps = capability_loader.load_all()         # validates + indexes
ctx  = AggregatorRunContext(
           fixture_mode=...,
           fixture_dir=...,
           strict_freshness=...,
       )
resolver = DeterminationResolver(ctx)

for control_id in idx:
    entries = resolver.for_rev5_control(control_id, caps_for_this_control)
    # entries is a list of ResolvedCapabilityEntry — aggregator-backed
    # ones carry a ControlDetermination; declared ones carry the prose
    render_section(control_id, entries)
```

Aggregators are cached per render — each aggregator runs at most once
per output document even if it serves many controls.

## Drift and freshness

Two distinct concepts:

- **Drift** = upstream FedRAMP renamed / retired a control we depend on.
  Daily sync workflow checks `frameworks/fedramp-20x/ksis.json` against
  capability mappings. PR fails when a referenced ID disappears upstream.
- **Freshness** = the live-state determination is too old to render.
  Each aggregator's `determine()` returns a fresh result on every render,
  so this is normally non-issue. When CSPs persist aggregator output to
  disk (caching across renders), an optional `strict_freshness` mode
  refuses to emit a document whose determinations are older than the
  capability's declared window.

## Where to put new things

| You want to... | Put it in... |
|---|---|
| Pull from a new cloud / SaaS API | `connectors/<source>.py` + fixtures under `tests/fixtures/<source>/` |
| Determine a new technical control | `aggregators/<area>.py` (new module or extend existing) |
| Add a manual-attested control | `manual-controls/<area>/<slug>.yaml` |
| Add a new framework's mapping | `capabilities/_schema.yaml` → new `satisfies` key, then add a renderer under `renderers/<framework>.py` |
| Watch a new upstream signal | `sync/<source>.py` + workflow under `.github/workflows/` |

## Future renderers

The schema and the determination contract already support every output
shape we plan:

- **OSCAL SSP (1.2.0)** — same determinations, different output schema.
  Targets eMASS / FedRAMP automated-authorization workflows.
- **HTML coverage matrix** — for the docs site at `infrastructure/`.
  Shows which KSIs and controls have aggregators vs. declared vs. manual.
- **Sarif / GitHub Code Scanning** — render aggregator non-compliant
  lists as alerts in PRs.

Each is a new file under `renderers/`; nothing else changes.
