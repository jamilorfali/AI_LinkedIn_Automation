# Source Governance

## Trust Tiers

- `primary`: Original source of a claim.
- `high_trust`: Reputable reporting, research, analyst, or expert synthesis.
- `useful_but_verify`: Interesting but needs backup.
- `social_signal_only`: Useful signal, not claim support.
- `blocked`: Do not use.

## Rules

- Do not scrape LinkedIn or X.
- Manual social links can inspire research, but cannot support factual claims.
- New recurring sources require human approval.
- Publishable topics need at least one primary or high-trust source.
- Discovery queue sources are candidates only until approved.

## Local Governance Commands

Run a source audit:

```bash
ai-linkedin audit-sources --week current
```

Build topic clusters and the verification queue:

```bash
ai-linkedin cluster-topics --week current
ai-linkedin build-discovery-queue --week current
```

Build a citation matrix for a draft:

```bash
ai-linkedin build-citation-matrix --draft-id DRAFT_ID --week current
```

Outputs are written under `data/review_packets/YYYY-Www/intelligence/`.
