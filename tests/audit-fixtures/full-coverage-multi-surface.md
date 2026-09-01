---
artifact: PublicContentAudit
audit_id: beta-labs-audit-1
produced_by: doublespeed-content-audit
brand_name: Beta Labs
website: https://betalabs.example
status: ok
outcome: Ok
coverage: full
coverage_conditions_failed: []
overall_score: 82
bounds_hit: []
outcomes_recorded: []
expect_valid: true
expect_violations: []
expect_coverage: full
sources:
  - { id: S1, kind: website, url: "https://betalabs.example/", entry_page: true, retrieval_status: ok }
  - { id: S2, kind: social_profile, surface: tiktok, url: "https://www.tiktok.com/@betalabs", retrieval_status: ok }
  - { id: S3, kind: social_profile, surface: instagram, url: "https://www.instagram.com/betalabs", retrieval_status: ok }
  - { id: S4, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@betalabs/video/1", retrieval_status: ok }
  - { id: S5, kind: social_content, surface: tiktok, url: "https://www.tiktok.com/@betalabs/video/2", retrieval_status: ok }
  - { id: S6, kind: social_content, surface: instagram, url: "https://www.instagram.com/p/betalabs1", retrieval_status: ok }
  - { id: S7, kind: social_content, surface: instagram, url: "https://www.instagram.com/p/betalabs2", retrieval_status: ok }
dimensions:
  - { id: D1, band: strong, value: 20, sources: [S1], reasoning: "Audience, product, and one primary action sit within the first screen" }
  - { id: D2, band: strong, value: 25, sources: [S4, S5, S6, S7], reasoning: "Every retrieved item opens on a number or a named audience" }
  - { id: D3, band: partial, value: 10, sources: [S4, S6], reasoning: "The same idea appears on both surfaces and is adapted to each rather than copied unchanged" }
  - { id: D4, band: partial, value: 7, sources: [S4, S5, S6], reasoning: "Voice is consistent, visual treatment drifts on the second surface" }
  - { id: D5, band: strong, value: 20, sources: [S1, S4], reasoning: "Every item routes to the bio link and the entry page carries the matching action" }
findings:
  - { id: F1, sources: [S6, S7], claim: "The second surface reuses vertical crops that read as reposted rather than native" }
  - { id: F2, sources: [S1, S4], claim: "The entry page action and the on-screen call to action use different wording" }
missing_angles:
  - { id: M1, sources: [S1, S2], angle: "Onboarding time, never quantified in public content" }
  - { id: M2, sources: [S5, S7], angle: "Customer objection handling, absent from both surfaces" }
ideas:
  - { id: I1, angle: "Onboarding clock", surface: tiktok, format: slideshow, hook: "eleven minutes, start to first result", addresses: [M1], sources: [S1, S4] }
  - { id: I2, angle: "Objection stack", surface: tiktok, format: slideshow, hook: "the three reasons teams said no", addresses: [M2], sources: [S5, S2] }
  - { id: I3, angle: "Native crop rebuild", surface: instagram, format: slideshow, hook: "we stopped reposting the same crop", addresses: [F1], sources: [S6, S7] }
  - { id: I4, angle: "Matching call to action", surface: instagram, format: video, hook: "one sentence, on the page and on the post", addresses: [F2], sources: [S1, S6] }
  - { id: I5, angle: "Surface-specific adaptation", surface: instagram, format: slideshow, hook: "same idea, built twice on purpose", addresses: [F1], sources: [S4, S6] }
  - { id: I6, angle: "Onboarding teardown", surface: tiktok, format: video, hook: "watch the first eleven minutes", addresses: [M1], sources: [S1, S5] }
  - { id: I7, angle: "Objection reframe", surface: instagram, format: slideshow, hook: "the objection we used to lose on", addresses: [M2], sources: [S7, S3] }
  - { id: I8, angle: "Conversion path fix", surface: tiktok, format: slideshow, hook: "the link that finally matched the page", addresses: [F2], sources: [S1, S2] }
  - { id: I9, angle: "Recurring number format", surface: tiktok, format: slideshow, hook: "every week, one number", addresses: [M1], sources: [S4, S5] }
  - { id: I10, angle: "Cross-surface series", surface: instagram, format: slideshow, hook: "the version built for this feed", addresses: [F1], sources: [S6, S3] }
sample_creative_id: X1
---
Two surfaces retrieved, so format fit is banded on native fit and on how a repeated idea is
adapted to each surface. No media was generated, no draft was persisted, and no review link was
created.
