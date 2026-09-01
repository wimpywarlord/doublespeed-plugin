---
artifact: PublicContentAudit
audit_id: delta-audit-1
produced_by: doublespeed-content-audit
brand_name: Delta
website: https://delta.example
status: failed
outcome: WebsiteUnreachable
coverage: none
coverage_conditions_failed: [entry_page_ok, three_content_items, all_dimensions_assessed]
bounds_hit: []
outcomes_recorded: []
expect_valid: true
expect_violations: []
expect_coverage: none
sources:
  - { id: S1, kind: website, url: "https://delta.example/", entry_page: true, retrieval_status: unavailable, reason: "Two attempts returned HTTP 503" }
dimensions: []
findings: []
missing_angles: []
ideas: []
---
The entry page failed after two attempts, so nothing was retrieved and nothing is inferred. This
brand was not audited from memory: there is no score, there are no findings, and there are no
ideas. Re-run the audit when the website responds.
