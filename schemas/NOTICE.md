# Schema attribution

`finding.schema.json` in this directory is adapted from the
[GRCEngClub/claude-grc-engineering](https://github.com/GRCEngClub/claude-grc-engineering/blob/main/schemas/finding.schema.json)
project, used under the terms of the MIT License.

The only modifications made are to the `$id` field (re-homed to this repo).
The substantive schema — required fields, evaluation structure, status enum,
narrative finding structure — is unchanged. We adopt this contract verbatim
because connector interoperability across the GRC engineering ecosystem is
more valuable than schema novelty.

See `docs/related-work.md` for a fuller discussion of how this project
relates to claude-grc-engineering and what we do differently.

## Original copyright

> MIT License
>
> Copyright (c) 2025-2026 GRC Engineering Club contributors
>
> Permission is hereby granted, free of charge, to any person obtaining a
> copy of this software and associated documentation files (the "Software"),
> to deal in the Software without restriction...

(Full text: https://github.com/GRCEngClub/claude-grc-engineering/blob/main/LICENSE)
