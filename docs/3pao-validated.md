# 3PAO Validation Provenance

This page is the audit trail for which capability patterns have been
exercised in a real FedRAMP assessment. **A capability that appears here
has cleared a 3PAO once for one CSP** — it is not a guarantee for your
environment, but it is evidence the pattern is defensible.

The data is sourced from each capability's `provenance.validated_in_assessment`
field. When a CSP publishes their submission to a public repository, we
treat that as citable evidence of the pattern's validity.

## How to read this

| Column | Meaning |
|---|---|
| Capability | The internal `cap-*` ID |
| CSP | The cloud service provider whose submission validated the pattern |
| 3PAO | The third-party assessor |
| Date | When the assessment occurred |
| FRMR version | Which release of the FedRAMP machine-readable docs the pattern was exercised against |
| Link | Public submission URL |

## Current provenance

| Capability | CSP | 3PAO | Date | FRMR version | Link |
|---|---|---|---|---|---|
| cap-mfa-phishing-resistant | Paramify | Coalfire | 2025-07-10 | v0.9.0-beta | [paramify/fedramp-20x-pilot](https://github.com/paramify/fedramp-20x-pilot) |

## How to add provenance

When a 3PAO accepts a capability's evidence in a public submission, add an
entry to that capability's YAML:

```yaml
provenance:
  validated_in_assessment:
    - csp: "Acme Federal"
      assessor_3pao: "Coalfire"
      date: 2026-01-15
      url: "https://github.com/acme/fedramp-20x-submission"
```

This page is rebuilt by `renderers/provenance_page.py` (planned) from those
entries, so you don't edit this Markdown directly in the long run — you
update the capability and regenerate.

## Why this matters

Compliance is a trust market. A toolkit nobody has used in a real
assessment is unproven. Naming the CSP and 3PAO behind each pattern
makes that evidence concrete and citable. CSPs evaluating this toolkit
should look at provenance before they look at the code.

## What this is not

- **Not a 3PAO endorsement of the toolkit itself.** The 3PAO assessed a CSP
  who used the pattern. That's not the same as the 3PAO certifying that
  the pattern works in your environment.
- **Not legal or compliance advice.** Apache 2.0 with explicit
  no-warranty applies. A 3PAO must still attest your specific implementation.
- **Not a guarantee of future acceptance.** FedRAMP guidance evolves; a
  pattern that cleared assessment in 2025 may need revision in 2026.

When in doubt, talk to your 3PAO before depending on a capability for an
authorization package.
