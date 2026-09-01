---
artifact: PublicContentAudit
audit_id: epsilon-audit-1
produced_by: doublespeed-content-audit
brand_name: Epsilon
website: https://epsilon.example
status: ok
outcome: Ok
coverage: full
coverage_conditions_failed: []
overall_score: 69
bounds_hit: []
outcomes_recorded: []
expect_valid: false
expect_violations: [MissingCitation, MissingCitation, MissingCitation]
expect_coverage: full
sources:
  - { id: S1, kind: website, url: "https://epsilon.example/", entry_page: true, retrieval_status: ok }
  - { id: S2, kind: website, url: "https://epsilon.example/pricing", entry_page: false, retrieval_status: ok }
  - { id: S3, kind: social_profile, surface: tiktok, url: "https://www.tiktok.com/@epsilon", retrieval_status: ok }
  - { id: S4, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@epsilon/video/1", retrieval_status: ok }
  - { id: S5, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@epsilon/video/2", retrieval_status: ok }
  - { id: S6, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@epsilon/video/3", retrieval_status: ok }
dimensions:
  - { id: D1, band: strong, value: 20, sources: [S1], reasoning: "Audience, product, and one primary action sit within the first screen" }
  - { id: D2, band: partial, value: 12, sources: [S4, S5, S6], reasoning: "Two items open on a number, one opens on the brand name" }
  - { id: D3, band: strong, value: 20, sources: [S4, S5, S6], reasoning: "All three items use formats native to the surface they were published on" }
  - { id: D4, band: partial, value: 7, sources: [], reasoning: "Banded without naming the items it was banded from, which is the defect this fixture isolates" }
  - { id: D5, band: partial, value: 10, sources: [S3, S4], reasoning: "A bio link exists, no item carries an on-screen call to action" }
findings:
  - { id: F1, sources: [S4, S5, S6], claim: "Every retrieved post opens with the brand name rather than a specific claim" }
  - { id: F2, sources: [], claim: "Pricing is never referenced in retrieved content, stated without citing a source" }
missing_angles:
  - { id: M1, sources: [S1, S3], angle: "Pricing objection, absent from all retrieved content" }
  - { id: M2, sources: [S4, S6], angle: "Before and after proof, never shown" }
ideas:
  - { id: I1, angle: "Cost objection reframe", surface: tiktok, format: slideshow, hook: "1,400 a month for a thing you use twice", addresses: [M1], sources: [S1, S4] }
  - { id: I2, angle: "Pricing math walkthrough", surface: tiktok, format: slideshow, hook: "here is the line item we cut first", addresses: [M1], sources: [S2, S5] }
  - { id: I3, angle: "Before and after proof", surface: tiktok, format: video, hook: "same room, six weeks apart", addresses: [M2], sources: [] }
  - { id: I4, angle: "Specific claim opener", surface: tiktok, format: slideshow, hook: "three numbers we stopped hiding", addresses: [F1], sources: [S4, S5] }
  - { id: I5, angle: "Named audience opener", surface: tiktok, format: slideshow, hook: "for teams still doing this by hand", addresses: [F1], sources: [S1, S4] }
  - { id: I6, angle: "Objection stack", surface: tiktok, format: slideshow, hook: "the four reasons people say no", addresses: [M1], sources: [S2, S6] }
  - { id: I7, angle: "Process teardown", surface: tiktok, format: video, hook: "we rebuilt this in one afternoon", addresses: [M2], sources: [S5, S6] }
  - { id: I8, angle: "Conversion path fix", surface: tiktok, format: slideshow, hook: "the link nobody could find", addresses: [F2], sources: [S3, S4] }
  - { id: I9, angle: "Recurring format", surface: tiktok, format: slideshow, hook: "every friday, one number", addresses: [F1], sources: [S4, S5] }
  - { id: I10, angle: "Second page rescue", surface: tiktok, format: slideshow, hook: "what the pricing page will not say", addresses: [F2], sources: [S2, S5] }
sample_creative_id: X1
---
Negative fixture. Three citation holes, each at its own locator: a scored dimension, a finding, and
an idea. Everything else is well formed, so this fixture isolates citation enforcement and nothing
else.
