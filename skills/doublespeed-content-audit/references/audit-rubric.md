---
name: audit-rubric
description: Five scored dimensions, bands, and evidence criteria for the free public content audit.
---

# Audit rubric

Five dimensions, 100 points. Each dimension takes exactly one band from retrieved evidence and
each band is a fixed integer, so the total is a pure function of the bands.

## Bands

| Band | Value | Meaning |
| --- | --- | --- |
| `strong` | full weight | The evidence criteria are met across the cited sources |
| `partial` | `floor(weight / 2)` | Some cited sources meet the criteria, others do not |
| `weak` | 0 | Sources were retrieved and they show the criteria are not met |
| `not_assessed` | 0 | No qualifying source was retrieved for this dimension |

`weak` and `not_assessed` both score 0 and are never merged in the report: one is a finding about
the brand, the other is a gap in coverage.

## Dimensions

| Id | Dimension | Weight | Evidence criteria |
| --- | --- | --- | --- |
| D1 | Offer clarity | 20 | The retrieved website states who the product is for, what it does, and one primary action, within the first screen of the entry page. Needs at least one website source with `retrieval_status: ok`. |
| D2 | Hook craft | 25 | The opening line, title, or first frame text of retrieved content items leads with a specific claim, number, tension, or named audience rather than a generic brand statement. Needs at least two retrieved content items. |
| D3 | Format and platform fit | 20 | Total over however many surfaces were retrieved. With items from exactly one social surface, band on native-format fit alone: the items use formats native to the surface they were published on. With items from two or more social surfaces, band on native-format fit and, additionally, on whether an idea that repeats across surfaces is adapted to each rather than copied unchanged. Needs items from at least one social surface. |
| D4 | Consistency | 15 | Retrieved items share a recognizable voice, visual treatment, and recurring angle across at least three items. Needs at least three retrieved content items. |
| D5 | Conversion path | 20 | Retrieved public content routes to a destination (profile link, bio link, pinned comment, on-screen call to action) and the website entry page carries a matching action. Needs at least one website source and one content item. |

## Minimum evidence to assess

The machine-readable restatement of the "Needs" clause in each row above. A dimension banded
`not_assessed` while its minimum evidence was in fact retrieved is a defect, not a coverage gap:
having only one social surface is not a reason to skip D3, and having three items is not a reason
to skip D4. Counters are `website_sources_ok`, `content_items_ok`, and `social_surfaces_ok`, each
counting only sources whose `retrieval_status` is `ok`.

| Id | Minimum evidence |
| --- | --- |
| D1 | website_sources_ok >= 1 |
| D2 | content_items_ok >= 2 |
| D3 | social_surfaces_ok >= 1 |
| D4 | content_items_ok >= 3 |
| D5 | website_sources_ok >= 1 and content_items_ok >= 1 |

## Recording a band

Every dimension record carries its band, its integer value, the source ids justifying the band,
and one sentence of reasoning.

A band with no cited source ids is invalid and must be recorded as `not_assessed` instead. A
`not_assessed` dimension cites no sources, because there were none that qualified.

The number describes only what was publicly retrievable for this brand on this date. It is neither
an industry comparison nor a competitor ranking, and it is reported at all only when coverage is
`full`.
