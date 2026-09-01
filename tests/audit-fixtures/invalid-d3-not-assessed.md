---
artifact: PublicContentAudit
audit_id: zeta-audit-1
produced_by: doublespeed-content-audit
brand_name: Zeta
website: https://zeta.example
status: ok
outcome: Ok
coverage: limited
coverage_conditions_failed: [all_dimensions_assessed]
bounds_hit: []
outcomes_recorded: [InsufficientEvidence]
expect_valid: false
expect_violations: [DimensionNotAssessedWithEvidence]
expect_coverage: limited
sources:
  - { id: S1, kind: website, url: "https://zeta.example/", entry_page: true, retrieval_status: ok }
  - { id: S2, kind: social_profile, surface: tiktok, url: "https://www.tiktok.com/@zeta", retrieval_status: ok }
  - { id: S3, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@zeta/video/1", retrieval_status: ok }
  - { id: S4, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@zeta/video/2", retrieval_status: ok }
  - { id: S5, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@zeta/video/3", retrieval_status: ok }
  - { id: S6, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@zeta/video/4", retrieval_status: ok }
  - { id: S7, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@zeta/video/5", retrieval_status: ok }
dimensions:
  - { id: D1, band: strong, value: 20, sources: [S1], reasoning: "Audience, product, and one primary action sit within the first screen" }
  - { id: D2, band: strong, value: 25, sources: [S3, S4, S5], reasoning: "Every retrieved item opens on a number or a named audience" }
  - { id: D3, band: not_assessed, value: 0, sources: [], reasoning: "Skipped for having only one social surface, which is not a valid reason to skip it" }
  - { id: D4, band: strong, value: 15, sources: [S3, S4, S5], reasoning: "Voice, treatment, and recurring angle are consistent across five items" }
  - { id: D5, band: partial, value: 10, sources: [S1, S3], reasoning: "A bio link exists, no item carries an on-screen call to action" }
findings:
  - { id: F1, sources: [S3, S4, S5], claim: "Every retrieved item is shot vertically and cut for the surface it was published on" }
missing_angles:
  - { id: M1, sources: [S1, S2], angle: "Pricing objection, absent from all retrieved content" }
ideas:
  - { id: I1, angle: "Cost objection reframe", surface: tiktok, format: slideshow, hook: "the number we stopped hiding", addresses: [M1], sources: [S1, S3] }
  - { id: I2, angle: "Format doubling down", surface: tiktok, format: slideshow, hook: "same cut, new argument", addresses: [F1], sources: [S4, S5] }
  - { id: I3, angle: "Objection stack", surface: tiktok, format: video, hook: "the four reasons people say no", addresses: [M1], sources: [S6, S7] }
sample_creative_id: X1
---
Negative fixture. Five content items were retrieved from one social surface, and format fit was
recorded as not assessed anyway. Having only one surface is not a reason to skip that dimension:
with one surface it is banded on native-format fit alone. The audit is both invalid and limited,
and neither masks the other.
