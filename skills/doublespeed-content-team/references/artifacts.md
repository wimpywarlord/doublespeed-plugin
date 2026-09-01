---
name: artifacts
description: Handoff artifact schemas for the Doublespeed content team.
---

# Artifact schemas

Every artifact is a fenced Markdown block with YAML frontmatter, emitted directly in the
conversation. In-conversation transport is canonical: it is portable across hosts, inspectable
without tooling, and visible to the operator at the moment a role hands off, which is what makes
the approval gate reviewable.

The frontmatter always carries `artifact`, `run_id`, `product_id`, `product_name`, `produced_by`,
and `status` (`ok`, `failed`, or `halted`). Bodies are short Markdown.

The single exception is `AuditHandoff`, produced by `doublespeed-content-audit` before
authentication and therefore before a product exists, which carries no `product_id` and no
`product_name`. Its schema lives in
`skills/doublespeed-content-audit/references/audit-artifacts.md`.

A mirror of these artifacts under `.doublespeed/runs/<run_id>/` is optional, is a work artifact
bounded to the run, may be deleted at any time, and is never read back as authority. The source of
truth for all content is Doublespeed: drafts, review links, and posts.

## RunManifest

Emitted by `ds-content-director` on entry. Fields: `format`, `variant_count`, `publish_status`,
`goal`, `retry_budget`.

```markdown
---
artifact: RunManifest
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-content-director
status: ok
format: slideshow
variant_count: 2
publish_status: scheduled
goal: Drive saves on the pricing objection angle
retry_budget: { per_step: 2, revision_cycles: 2, generation_polls: 10 }
---
Active product set once for this run. Roles dispatched in order.
```

## EvidencePack

Emitted by `ds-performance-researcher`. Fields: `findings` (each `id`, `claim`, `source_tool`,
`confidence`), `unavailable` (each `signal`, `reason`), `templates_available`.

```markdown
---
artifact: EvidencePack
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-performance-researcher
status: ok
findings:
  - { id: F1, claim: "Slideshows outperform video on saves per view by 2.4x over 30 days", source_tool: get_post_metrics, confidence: high }
  - { id: F2, claim: "Top 3 posts all open with a cost objection hook", source_tool: list_account_posts, confidence: medium }
unavailable:
  - { signal: trending_audio, reason: "search_trending_audio returned no results for the product niche" }
templates_available: 4
---
```

Items seeded by an `AuditHandoff` are recorded here with `source_tool: doublespeed-content-audit`
and `confidence: low`, because they were never verified against authenticated product data.

## ProductionBrief

Emitted by `ds-content-strategist`. Fields: `format`, `slide_count`, `concepts` (each `id`,
`angle`, `hook_direction`, `evidence`, `speculative`), `brand_rules_applied`.

```markdown
---
artifact: ProductionBrief
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-content-strategist
status: ok
format: slideshow
slide_count: 6
concepts:
  - { id: C1, angle: "Cost objection reframe", hook_direction: "Open on the number, not the promise", evidence: [F1, F2], speculative: false }
brand_rules_applied: [no superlatives, lowercase headings, no emoji in slide text]
---
```

## CopySet

Emitted by `ds-hook-copy-writer`. Fields: `concept_id`, `variants` (each `label`, `slides`,
`caption`, `score10`), `scored_with`.

```markdown
---
artifact: CopySet
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-hook-copy-writer
status: ok
concept_id: C1
variants:
  - { label: A, slides: ["$1,400 a month", "for a thing you use twice", "here is the math"], caption: "the pricing math nobody shows you", score10: 8.1 }
  - { label: B, slides: ["we cut this line item first", "here is what replaced it", "the new number"], caption: "the first line item we cut", score10: 6.4 }
scored_with: score_slideshow_copy
---
```

## DraftPackage

Emitted by `ds-visual-producer`. Fields: `group_id`, `source_template_id`, `variants` (each
`variant_id`, `label`, `slides`, `caption`), `preview_image_urls`, `share_link_created`.

```markdown
---
artifact: DraftPackage
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-visual-producer
status: ok
group_id: 2b7a6c40-0000-4000-8000-0000000000aa
source_template_id: 91d3f8b2-0000-4000-8000-0000000000bb
variants:
  - { variant_id: c4e5a1f0-0000-4000-8000-0000000000c1, label: A, slides: ["$1,400 a month", "for a thing you use twice", "here is the math"], caption: "the pricing math nobody shows you" }
preview_image_urls: ["https://doublespeed.ai/media/preview-1.png"]
share_link_created: false
---
```

## QAReport

Emitted by `ds-qa-editor`. Fields: `results` (each `variant_id`, `verdict`, `findings` with
`check`, `slide_index`, `detail`, `instruction`).

```markdown
---
artifact: QAReport
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-qa-editor
status: ok
results:
  - { variant_id: c4e5a1f0-0000-4000-8000-0000000000c1, verdict: pass, findings: [] }
  - variant_id: c4e5a1f0-0000-4000-8000-0000000000c2
    verdict: fail
    findings:
      - { check: factual_consistency, slide_index: 3, detail: "Slide claims 3x, EvidencePack F1 says 2.4x", instruction: 'Change slide 3 text to "2.4x" to match F1' }
---
```

## ApprovalRequest

Emitted by `ds-content-director`. Fields: `group_id`, `review_link`, `review_link_token`,
`awaiting_variants` (each `variant_id`, `label`, `slides`, `caption`), `default_publish_status`,
`canonical_phrase`. Only variants whose QA verdict is `pass` appear.

```markdown
---
artifact: ApprovalRequest
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-content-director
status: ok
group_id: 2b7a6c40-0000-4000-8000-0000000000aa
review_link: https://doublespeed.ai/review/7d9e2f11-0000-4000-8000-0000000000dd
review_link_token: 7d9e2f11-0000-4000-8000-0000000000dd
awaiting_variants:
  - { variant_id: c4e5a1f0-0000-4000-8000-0000000000c1, label: A, slides: ["$1,400 a month", "for a thing you use twice", "here is the math"], caption: "the pricing math nobody shows you" }
default_publish_status: scheduled
canonical_phrase: "APPROVE run=acme-1 token=7d9e2f11-0000-4000-8000-0000000000dd variants=c4e5a1f0-0000-4000-8000-0000000000c1"
---
Nothing is queued until you reply with an explicit approval naming this review link and the variants.
```

## ApprovalRecord

Emitted by `ds-content-director` when a human message satisfies A1 through A5. Fields:
`review_link_token`, `variant_ids`, `publish_status`, `human_message_quote`, `conditions`.

```markdown
---
artifact: ApprovalRecord
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-content-director
status: ok
review_link_token: 7d9e2f11-0000-4000-8000-0000000000dd
variant_ids: [c4e5a1f0-0000-4000-8000-0000000000c1]
publish_status: scheduled
human_message_quote: "APPROVE run=acme-1 token=7d9e2f11 variants=c4e5a1f0"
conditions: { A1: pass, A2: pass, A3: pass, A4: pass, A5: deferred_to_publisher }
---
```

## PublishReceipt

Emitted by `ds-publisher`. Fields: `queued` (each `variant_id`, `post_id`, `status`), `preflight`.

```markdown
---
artifact: PublishReceipt
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-publisher
status: ok
queued:
  - { variant_id: c4e5a1f0-0000-4000-8000-0000000000c1, post_id: 5a0b9c33-0000-4000-8000-0000000000e1, status: scheduled }
preflight: { content_match: pass, qa_verdict: pass }
---
```

## StepFailure

Emitted by any role. Fields: `kind`, `tool`, `classification` (`transient` or `permanent`),
`attempts`, `detail`, `recommendation`, `returns_control_to`.

```markdown
---
artifact: StepFailure
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-visual-producer
status: failed
kind: GenerationTimeout
tool: check_generation_status
classification: permanent
attempts: 10
detail: Asset job 44c1 did not reach a terminal state within the poll budget
recommendation: Reduce to 4 slides and retry once, or select an existing media asset
returns_control_to: ds-content-director
---
```

`kind` is one of exactly these twelve values, and nothing else:

| Kind | Meaning |
| --- | --- |
| AuthRequired | A tool returned 401. The run pauses in AUTH_REQUIRED and is never retried in a loop. |
| ToolPermanentFailure | 4xx, validation error, missing required field, or a server-side rejection. |
| ToolTransientFailure | Timeout, 5xx, rate limit, or a generation job still pending. |
| UnparseableResult | A result that does not match the expected shape. Treated as permanent. |
| GenerationTimeout | An asset did not reach a terminal state within 10 polls. |
| TemplateLineageRejected | The server rejected a rebuilt lookalike draft. Permanent, never retried identically. |
| ProductScopeMismatch | An input artifact carries a different `product_id` than the run's active product. |
| OutOfScopeToolRequired | The task appears to require a tool outside the role's allowlist. |
| ApprovalMissing | The Publisher lacks a valid record, request, draft package, or passing QA report. |
| ApprovalInvalidated | The live draft no longer matches the approved slide texts and caption. |
| RetryBudgetExhausted | Three attempts at one call site all failed transiently. Permanent. |
| RevisionBudgetExhausted | A third QA failure after two automatic revision cycles. The run HALTs. |

## LearningsReport

Emitted by `ds-performance-analyst`. Fields: `phase` (`baseline` or `outcome`), `post_ids`,
`measurement_plan`, `baseline`, `learnings`.

```markdown
---
artifact: LearningsReport
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-performance-analyst
status: ok
phase: baseline
post_ids: [5a0b9c33-0000-4000-8000-0000000000e1]
measurement_plan: Read post metrics for these post ids against the trailing 30 day product baseline
baseline: { median_views: 4120, median_saves: 61 }
learnings: []
---
```

## RunSummary

The Content Director's termination artifact. Fields: `final_state`, `artifacts_emitted`,
`queued_post_ids`, `halt_reason` (null on success).

```markdown
---
artifact: RunSummary
run_id: acme-1
product_id: 8f1c1d2e-0000-4000-8000-000000000001
product_name: Acme
produced_by: ds-content-director
status: ok
final_state: ANALYZED
artifacts_emitted: [RunManifest, EvidencePack, ProductionBrief, CopySet, DraftPackage, QAReport, ApprovalRequest, ApprovalRecord, PublishReceipt, LearningsReport]
queued_post_ids: [5a0b9c33-0000-4000-8000-0000000000e1]
halt_reason: null
---
```
