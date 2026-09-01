---
artifact: PublicContentAudit
audit_id: gamma-audit-1
produced_by: doublespeed-content-audit
brand_name: Gamma
website: https://gamma.example
status: ok
outcome: Ok
coverage: limited
coverage_conditions_failed: [three_content_items, all_dimensions_assessed]
bounds_hit: []
outcomes_recorded: [InsufficientEvidence]
expect_valid: true
expect_violations: []
expect_coverage: limited
sources:
  - { id: S1, kind: website, url: "https://gamma.example/", entry_page: true, retrieval_status: ok }
  - { id: S2, kind: social_profile, surface: tiktok, url: "https://www.tiktok.com/@gamma", retrieval_status: ok }
  - { id: S3, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@gamma/video/1", retrieval_status: ok }
  - { id: S4, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@gamma/video/2", retrieval_status: ok }
dimensions:
  - { id: D1, band: strong, value: 20, sources: [S1], reasoning: "Audience, product, and one primary action sit within the first screen" }
  - { id: D2, band: partial, value: 12, sources: [S3, S4], reasoning: "One item opens on a number, the other opens on the brand name" }
  - { id: D3, band: strong, value: 20, sources: [S3, S4], reasoning: "Both items use formats native to the surface they were published on" }
  - { id: D4, band: not_assessed, value: 0, sources: [], reasoning: "Fewer than three retrieved items, so consistency across items cannot be assessed" }
  - { id: D5, band: partial, value: 10, sources: [S1, S3], reasoning: "A bio link exists, neither item carries an on-screen call to action" }
findings:
  - { id: F1, sources: [S3, S4], claim: "Both retrieved posts open on the brand name rather than a specific claim" }
  - { id: F2, sources: [S1, S2], claim: "The entry page action does not appear anywhere in retrieved content" }
missing_angles:
  - { id: M1, sources: [S1, S2], angle: "Proof of outcome, absent from the retrieved surface" }
ideas:
  - { id: I1, angle: "Specific claim opener", surface: tiktok, format: slideshow, hook: "three numbers we stopped hiding", addresses: [F1], sources: [S3, S4] }
  - { id: I2, angle: "Outcome proof", surface: tiktok, format: video, hook: "same setup, four weeks apart", addresses: [M1], sources: [S1, S3] }
  - { id: I3, angle: "Conversion path fix", surface: tiktok, format: slideshow, hook: "the link nobody could find", addresses: [F2], sources: [S1, S2] }
  - { id: I4, angle: "Named audience opener", surface: tiktok, format: slideshow, hook: "for teams still doing this by hand", addresses: [F1], sources: [S2, S4] }
sample_creative_id: X1
---
Four ideas rather than ten, because only two content items were retrievable. The count is stated
rather than padded with uncited ideas, and the numeric score is omitted because coverage is
limited. No media was generated, no draft was persisted, and no review link was created.
