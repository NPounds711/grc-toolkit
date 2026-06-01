# Architecture

## The core idea

A compliance artifact (Rev 5 SSP, 20x package, OSCAL doc, SOC 2 description)
is **a view over a set of capability claims**. The claim doesn't change when
the framework does — only the rendering does.

So the architecture is three layers, kept rigorously separate:

```
┌───────────────────────────────────────────────────────────────┐
│  Layer 1: capabilities/                                       │
│  Source of truth. What is actually true about the system.     │
│  Authored by humans. Never references framework text verbatim.│
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│  Layer 2: frameworks/                                         │
│  Synced from upstream (FedRAMP/docs, NIST OSCAL content).     │
│  Never hand-edited. Provides the authoritative ID list, KSI   │
│  descriptions, control text, retirement status.               │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│  Layer 3: renderers/                                          │
│  One per output format. Joins (1) and (2) at render time and  │
│  emits a Word doc, JSON package, OSCAL doc, HTML site, etc.   │
└───────────────────────────────────────────────────────────────┘
```

Three invariants make this work:

1. **A capability never embeds framework text.** It says
   `satisfies: { fedramp_rev5: [{ control: IA-2 }] }`. The control title and
   prose come from `frameworks/fedramp-rev5/controls.json` at render time.
2. **`frameworks/` is sync output.** A daily workflow refreshes it. Drift
   tests fail if a referenced ID no longer exists upstream.
3. **Renderers are pure functions of (capabilities, frameworks).** Two
   developers running the same renderer on the same inputs get byte-identical
   output.

## Data flow during a render

```
load_all() → list[Capability]                         (Layer 1)
       │
       │  (drift tests reconcile this against frameworks/)
       │
       ▼
index_by_rev5_control() / index_by_ksi()              (joiners)
       │
       ▼
renderer.render(index, frameworks_data) → artifact    (Layer 3)
```

`renderers/shared/capability_loader.py` is the only file that knows the
on-disk YAML layout. Renderers consume the `Capability` object, never the
raw YAML. Schema changes flow through the loader and stay invisible to
everything downstream.

## Data flow during a sync

```
upstream repo (FedRAMP/docs)
       │
       ▼
sync/frmr_sync.py                                     (transforms upstream
       │                                               shape → internal schema)
       ▼
frameworks/fedramp-20x/ksis.json
       │
       ▼
tests/test_drift.py runs on PR                        (catches breaking changes)
       │
       ├── pass → merge → renderers regenerate cleanly
       └── fail → comment names broken capabilities
                  → human updates them
                  → drift tests pass → merge
```

## Why this survives FedRAMP's release cadence

Three properties together:

| Property | What it buys |
|---|---|
| Capabilities reference IDs, not text | When FedRAMP rewrites a KSI description, capability content doesn't change |
| Drift tests fail PRs on breaking ID changes | We find out at PR time, not at customer time |
| Adding a framework is additive | New `satisfies:` key, new renderer; existing content untouched |

The architectural property: **adding new framework support is purely additive,
never destructive.**

## When to put something where

| You want to... | Put it in... |
|---|---|
| Describe what the system does | `capabilities/<area>/<slug>.yaml` |
| Collect proof from a cloud or vendor API | `evidence/<source>/<verb>.sh` (or .py) |
| Validate evidence programmatically | `policies/<area>/<slug>.rego` |
| Show how to build it (greenfield) | `terraform/<cloud>/modules/<slug>/` |
| Generate a new artifact format | `renderers/<format>.py` |
| Watch an upstream source for drift | `sync/<source>.py` + workflow |

## What goes nowhere

| Thing | Why it's wrong here |
|---|---|
| KSI prose text in a capability YAML | Use the ID; the loader pulls text from `frameworks/` |
| A renderer that reads YAML directly | Renderers must consume the `Capability` object via the loader |
| Hand-edited files under `frameworks/` | Will be wiped on next sync |
| Real credentials in evidence collectors | Use env vars; collectors must be public-safe |
| Customer data in samples/ | Use generic example names like "Acme Federal" |

## Future renderers

The schema already supports SOC 2 and NIST CSF 2.0 mappings. Adding
renderers for either is purely additive:

```bash
# Add renderer
touch renderers/soc2.py
# Existing capabilities pick up the new framework automatically because
# they already declare satisfies.soc2.criterion mappings.
```

OSCAL is the same story, with the wrinkle that the OSCAL schema is large.
Recommend treating it as an export target — convert the internal model to
OSCAL on demand rather than maintaining OSCAL as an internal format.
