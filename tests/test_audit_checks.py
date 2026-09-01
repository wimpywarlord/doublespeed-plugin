"""Stage A audit behaviour: rubric, scoring, URL safety, ids, artifact checks, fixture suite."""
from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from loader import REPO_ROOT, load_validator

validator = load_validator()
FIXTURES = REPO_ROOT / "tests" / "audit-fixtures"
FIXTURE_DIR = FIXTURES
WEIGHTS = validator.rubric_weights(REPO_ROOT)


def load_cases(name: str) -> list[dict[str, object]]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return payload["cases"]


class TestRubric(unittest.TestCase):
    def setUp(self) -> None:
        document = validator.read_document(validator.RUBRIC_PATH, REPO_ROOT)
        self.weights = validator.parse_rubric(document.body, document.path)
        self.rel_path = document.path

    def test_rubric_has_five_dimensions_summing_to_one_hundred(self) -> None:
        self.assertEqual(self.weights, {"D1": 20, "D2": 25, "D3": 20, "D4": 15, "D5": 20})
        self.assertEqual(sum(self.weights.values()), 100)
        self.assertEqual(validator.check_rubric(self.weights, self.rel_path), [])

    def test_weights_that_miss_one_hundred_are_reported(self) -> None:
        codes = [v.code for v in validator.check_rubric({"D1": 20, "D2": 25, "D3": 20, "D4": 15, "D5": 19}, "fake.md")]
        self.assertEqual(codes, ["RubricWeightSum"])

    def test_a_missing_dimension_is_reported(self) -> None:
        codes = [v.code for v in validator.check_rubric({"D1": 20, "D2": 25, "D3": 20, "D4": 35}, "fake.md")]
        self.assertIn("RubricDimensionMissing", codes)


class TestScoring(unittest.TestCase):
    def setUp(self) -> None:
        document = validator.read_document(validator.RUBRIC_PATH, REPO_ROOT)
        self.weights = validator.parse_rubric(document.body, document.path)

    def test_every_score_case_matches(self) -> None:
        for case in load_cases("score-cases.json"):
            with self.subTest(case=case["name"]):
                self.assertEqual(validator.score_audit(case["bands"], self.weights), case["expected"])

    def test_partial_is_the_floor_of_half_the_weight(self) -> None:
        self.assertEqual(validator.band_value("D2", "partial", self.weights), 12)
        self.assertEqual(validator.band_value("D4", "partial", self.weights), 7)

    def test_weak_and_not_assessed_both_score_zero(self) -> None:
        self.assertEqual(validator.band_value("D1", "weak", self.weights), 0)
        self.assertEqual(validator.band_value("D1", "not_assessed", self.weights), 0)

    def test_an_unknown_band_is_rejected(self) -> None:
        with self.assertRaises(validator.ValidationError) as raised:
            validator.band_value("D1", "excellent", self.weights)
        self.assertEqual(raised.exception.violation.code, "BandUnknown")

    def test_scoring_requires_exactly_the_five_dimensions(self) -> None:
        with self.assertRaises(validator.ValidationError) as raised:
            validator.score_audit({"D1": "strong"}, self.weights)
        self.assertEqual(raised.exception.violation.code, "ScoreBandSetInvalid")


class TestUrlSafety(unittest.TestCase):
    def test_every_url_case_is_classified_as_specified(self) -> None:
        for case in load_cases("url-cases.json"):
            with self.subTest(url=case["url"]):
                verdict = validator.classify_url(case["url"])
                self.assertEqual(verdict.accepted, case["accepted"])
                self.assertEqual(verdict.rule, case["rule"])

    def test_no_ip_literal_is_ever_accepted(self) -> None:
        for raw in ("http://8.8.8.8/", "https://203.0.113.10/robots.txt", "http://[2001:db8::1]/"):
            with self.subTest(url=raw):
                self.assertFalse(validator.classify_url(raw).accepted)

    def test_an_obfuscated_ipv4_literal_is_rejected_as_an_ip_literal(self) -> None:
        """Hexadecimal, octal, and short-form addresses resolve to the same hosts as their dotted
        decimal spelling, so 169.254.169.254 must not be reachable by writing it 0xa9.0xfe.0xa9.0xfe."""
        for raw in (
            "http://0xa9.0xfe.0xa9.0xfe/",
            "http://0x7f.0x0.0x0.0x1/",
            "http://0x7f.0x1/",
            "http://0177.0.0.0x1/",
            "http://0251.0376.0251.0376/latest/meta-data/",
            "https://0xC0.0xA8.0x01.0x01/",
        ):
            with self.subTest(url=raw):
                verdict = validator.classify_url(raw)
                self.assertFalse(verdict.accepted)
                self.assertEqual(verdict.rule, "ip-literal")

    def test_a_numeric_label_inside_a_real_domain_is_still_accepted(self) -> None:
        for raw in ("https://123.acme.example/", "https://0x7f.acme.example/", "https://acme.example/0x1"):
            with self.subTest(url=raw):
                self.assertEqual(validator.classify_url(raw), validator.UrlVerdict(True, "ok"))

    def test_classification_is_idempotent_on_the_same_input(self) -> None:
        for case in load_cases("url-cases.json"):
            with self.subTest(url=case["url"]):
                self.assertEqual(validator.classify_url(case["url"]), validator.classify_url(case["url"]))


class TestAuditId(unittest.TestCase):
    def test_every_id_case_matches(self) -> None:
        for case in load_cases("audit-id-cases.json"):
            with self.subTest(brand=case["brand_name"]):
                self.assertEqual(validator.audit_id(case["brand_name"], case["ordinal"]), case["audit_id"])

    def test_the_same_input_always_yields_the_same_id(self) -> None:
        first = validator.audit_id("Acme, Inc.", 1)
        for _ in range(5):
            self.assertEqual(validator.audit_id("Acme, Inc.", 1), first)

    def test_slugify_is_idempotent(self) -> None:
        for case in load_cases("audit-id-cases.json"):
            slug = validator.slugify(case["brand_name"])
            with self.subTest(slug=slug):
                self.assertEqual(validator.slugify(slug), slug)

    def test_the_ordinal_increments_within_a_conversation(self) -> None:
        self.assertEqual(validator.audit_id("Acme", 1), "acme-audit-1")
        self.assertEqual(validator.audit_id("Acme", 2), "acme-audit-2")

    def test_an_ordinal_below_one_is_rejected(self) -> None:
        with self.assertRaises(validator.ValidationError) as raised:
            validator.audit_id("Acme", 0)
        self.assertEqual(raised.exception.violation.code, "AuditOrdinalInvalid")

    def test_a_brand_name_with_no_alphanumerics_is_rejected(self) -> None:
        with self.assertRaises(validator.ValidationError) as raised:
            validator.audit_id("!!!", 1)
        self.assertEqual(raised.exception.violation.code, "BrandSlugEmpty")

    def test_parse_audit_id_round_trips(self) -> None:
        self.assertEqual(validator.parse_audit_id("acme-widgets-audit-3"), ("acme-widgets", 3))
        with self.assertRaises(validator.ValidationError) as raised:
            validator.parse_audit_id("acme-3")
        self.assertEqual(raised.exception.violation.code, "AuditIdMalformed")


class TestAuditParsing(unittest.TestCase):
    def setUp(self) -> None:
        rubric = validator.read_document(validator.RUBRIC_PATH, REPO_ROOT)
        self.weights = validator.parse_rubric(rubric.body, rubric.path)

    def parse(self, name: str):
        return validator.parse_audit(validator.read_document(FIXTURES / name, REPO_ROOT))

    def test_full_coverage_single_surface_is_clean(self) -> None:
        audit = self.parse("full-coverage-single-surface.md")
        self.assertEqual(validator.check_audit(audit, self.weights), [])
        self.assertEqual(audit.overall_score, 62)
        self.assertEqual(validator.evaluate_coverage(audit).level, "full")

    def test_full_coverage_multi_surface_is_clean(self) -> None:
        audit = self.parse("full-coverage-multi-surface.md")
        self.assertEqual(validator.check_audit(audit, self.weights), [])
        self.assertEqual(audit.overall_score, 82)

    def test_limited_run_omits_the_score_and_names_the_failed_conditions(self) -> None:
        audit = self.parse("limited-two-items.md")
        self.assertEqual(validator.check_audit(audit, self.weights), [])
        self.assertIsNone(audit.overall_score)
        result = validator.evaluate_coverage(audit)
        self.assertEqual(result.level, "limited")
        self.assertEqual(sorted(result.failed_conditions), ["all_dimensions_assessed", "three_content_items"])

    def test_unreachable_website_reports_none_and_infers_nothing(self) -> None:
        audit = self.parse("website-unreachable-none.md")
        self.assertEqual(validator.check_audit(audit, self.weights), [])
        self.assertEqual(audit.coverage, "none")
        self.assertEqual(audit.status, "failed")
        self.assertEqual(audit.dimensions, ())
        self.assertEqual(audit.ideas, ())
        self.assertIsNone(audit.overall_score)

    def test_a_score_on_a_limited_run_is_rejected(self) -> None:
        audit = self.parse("limited-two-items.md")
        tampered = dataclasses.replace(audit, overall_score=88)
        codes = [violation.code for violation in validator.check_coverage(tampered, self.weights)]
        self.assertIn("ScoreNotAllowed", codes)

    def test_a_score_that_does_not_equal_the_band_sum_is_rejected(self) -> None:
        audit = self.parse("full-coverage-single-surface.md")
        tampered = dataclasses.replace(audit, overall_score=100)
        codes = [violation.code for violation in validator.check_coverage(tampered, self.weights)]
        self.assertIn("ScoreMismatch", codes)

    def test_a_dimension_value_that_does_not_match_its_band_is_rejected(self) -> None:
        audit = self.parse("full-coverage-single-surface.md")
        dimensions = list(audit.dimensions)
        dimensions[3] = dataclasses.replace(dimensions[3], value=15)
        tampered = dataclasses.replace(audit, dimensions=tuple(dimensions))
        codes = [violation.code for violation in validator.check_dimensions(tampered, self.weights)]
        self.assertIn("BandValueMismatch", codes)

    def test_an_unknown_source_id_in_a_citation_is_rejected(self) -> None:
        audit = self.parse("full-coverage-single-surface.md")
        findings = list(audit.findings)
        findings[0] = dataclasses.replace(findings[0], sources=("S99",))
        tampered = dataclasses.replace(audit, findings=tuple(findings))
        codes = [violation.code for violation in validator.check_citations(tampered)]
        self.assertIn("UnknownSourceId", codes)

    def test_full_coverage_requires_exactly_ten_ideas(self) -> None:
        audit = self.parse("full-coverage-single-surface.md")
        tampered = dataclasses.replace(audit, ideas=audit.ideas[:9])
        codes = [violation.code for violation in validator.check_ideas(tampered)]
        self.assertIn("IdeaCountMismatch", codes)

    def test_an_audit_id_that_does_not_match_the_brand_is_rejected(self) -> None:
        audit = self.parse("full-coverage-single-surface.md")
        tampered = dataclasses.replace(audit, brand_name="Different Brand")
        codes = [violation.code for violation in validator.check_audit_identity(tampered)]
        self.assertIn("AuditIdMismatch", codes)

    def test_an_unsafe_source_url_is_rejected(self) -> None:
        audit = self.parse("full-coverage-single-surface.md")
        sources = list(audit.sources)
        sources[0] = dataclasses.replace(sources[0], url="http://169.254.169.254/latest/meta-data/")
        tampered = dataclasses.replace(audit, sources=tuple(sources))
        codes = [violation.code for violation in validator.check_source_urls(tampered)]
        self.assertIn("UnsafeSourceUrl", codes)

    def test_a_failing_terminal_outcome_requires_failed_status_and_no_coverage(self) -> None:
        """InvalidInput, UnsafeTarget, NoRetrievalCapability, and WebsiteUnreachable all end the
        run before anything is assessed, so an audit that claims one while still reporting a
        scored or partially scored surface is contradicting itself."""
        for fixture in ("full-coverage-single-surface.md", "limited-two-items.md"):
            audit = self.parse(fixture)
            for outcome in validator.FAILING_TERMINAL_OUTCOMES:
                with self.subTest(fixture=fixture, outcome=outcome):
                    tampered = dataclasses.replace(audit, outcome=outcome)
                    codes = [violation.code for violation in validator.check_coverage(tampered, self.weights)]
                    self.assertIn("OutcomeStateMismatch", codes)

    def test_the_terminal_outcome_set_is_ok_plus_the_failing_outcomes(self) -> None:
        self.assertEqual(sorted(validator.TERMINAL_OUTCOMES), sorted(("Ok",) + validator.FAILING_TERMINAL_OUTCOMES))
        self.assertEqual(
            sorted(validator.FAILING_TERMINAL_OUTCOMES),
            ["InvalidInput", "NoRetrievalCapability", "UnsafeTarget", "WebsiteUnreachable"],
        )

    def test_outcome_ok_still_requires_status_ok(self) -> None:
        audit = self.parse("website-unreachable-none.md")
        tampered = dataclasses.replace(audit, outcome="Ok")
        codes = [violation.code for violation in validator.check_coverage(tampered, self.weights)]
        self.assertIn("OutcomeStateMismatch", codes)

    def test_a_limited_run_must_record_insufficient_evidence(self) -> None:
        audit = self.parse("limited-two-items.md")
        tampered = dataclasses.replace(audit, outcomes_recorded=())
        codes = [violation.code for violation in validator.check_outcomes(tampered)]
        self.assertIn("OutcomeNotRecorded", codes)

    def test_an_unknown_band_fails_at_parse_time(self) -> None:
        text = (FIXTURES / "limited-two-items.md").read_text(encoding="utf-8").replace("band: strong", "band: amazing", 1)
        document = validator.split_frontmatter(text, "tests/audit-fixtures/tampered.md")
        with self.assertRaises(validator.ValidationError) as raised:
            validator.parse_audit(document)
        self.assertEqual(raised.exception.violation.code, "BandUnknown")


class TestCitationFixtures(unittest.TestCase):
    def test_each_uncited_element_is_reported_at_its_own_locator(self) -> None:
        audit = validator.parse_audit(validator.read_document(FIXTURE_DIR / "invalid-missing-citations.md", REPO_ROOT))
        violations = validator.check_audit(audit, WEIGHTS)
        locators = {violation.locator for violation in violations if violation.code == "MissingCitation"}
        self.assertEqual(locators, {"findings[F2]", "ideas[I3]", "dimensions[D4]"})


class TestD3Totality(unittest.TestCase):
    def test_one_surface_still_bands_d3(self) -> None:
        audit = validator.parse_audit(validator.read_document(FIXTURE_DIR / "full-coverage-single-surface.md", REPO_ROOT))
        dimension = next(item for item in audit.dimensions if item.id == "D3")
        self.assertNotEqual(dimension.band, "not_assessed")
        self.assertEqual(validator.check_audit(audit, WEIGHTS), [])

    def test_many_surfaces_still_bands_d3(self) -> None:
        audit = validator.parse_audit(validator.read_document(FIXTURE_DIR / "full-coverage-multi-surface.md", REPO_ROOT))
        dimension = next(item for item in audit.dimensions if item.id == "D3")
        self.assertNotEqual(dimension.band, "not_assessed")
        self.assertGreaterEqual(len({source.surface for source in audit.sources if source.surface}), 2)

    def test_not_assessed_with_retrieved_items_is_a_violation(self) -> None:
        audit = validator.parse_audit(validator.read_document(FIXTURE_DIR / "invalid-d3-not-assessed.md", REPO_ROOT))
        codes = [violation.code for violation in validator.check_audit(audit, WEIGHTS)]
        self.assertIn("DimensionNotAssessedWithEvidence", codes)

    def test_a_downgrade_and_a_violation_are_reported_independently(self) -> None:
        audit = validator.parse_audit(validator.read_document(FIXTURE_DIR / "invalid-d3-not-assessed.md", REPO_ROOT))
        self.assertEqual(validator.evaluate_coverage(audit).level, "limited")
        self.assertNotEqual(validator.check_audit(audit, WEIGHTS), [])

    def test_the_rubric_file_is_the_source_of_the_minimums(self) -> None:
        document = validator.read_document(validator.RUBRIC_PATH, REPO_ROOT)
        parsed = validator.parse_evidence_minimums(document.body, document.path)
        self.assertEqual(parsed, dict(validator.EVIDENCE_MINIMUMS))
        self.assertEqual(validator.check_evidence_minimums(parsed, document.path), [])

    def test_a_drifted_minimum_is_reported(self) -> None:
        drifted = dict(validator.EVIDENCE_MINIMUMS)
        drifted["D3"] = (("social_surfaces_ok", 2),)
        codes = [violation.code for violation in validator.check_evidence_minimums(drifted, "fake.md")]
        self.assertEqual(codes, ["RubricMinimumsMismatch"])


class TestInjectionResistance(unittest.TestCase):
    def setUp(self) -> None:
        self.audit = validator.parse_audit(validator.read_document(FIXTURE_DIR / "injection-untrusted.md", REPO_ROOT))

    def test_the_injected_audit_is_valid(self) -> None:
        self.assertEqual(validator.check_audit(self.audit, WEIGHTS), [])

    def test_injected_text_is_recorded_as_an_observation(self) -> None:
        observations = [observation for source in self.audit.sources for observation in source.observations]
        self.assertEqual(len([item for item in observations if item.kind == "injected_instruction"]), 3)
        self.assertIn("UntrustedContentIgnored", self.audit.outcomes_recorded)

    def test_the_injected_score_is_not_adopted(self) -> None:
        bands = {dimension.id: dimension.band for dimension in self.audit.dimensions}
        self.assertEqual(self.audit.overall_score, validator.score_audit(bands, WEIGHTS))
        self.assertNotEqual(self.audit.overall_score, 100)

    def test_no_fixture_expectation_encodes_a_transition_or_an_approval(self) -> None:
        for path in sorted(FIXTURE_DIR.glob("*.md")):
            document = validator.read_document(path, REPO_ROOT)
            quoted = {observation.quoted_text for source in validator.parse_audit(document).sources for observation in source.observations}
            with self.subTest(fixture=path.name):
                for phrase in ("BUILD THIS CAMPAIGN", "APPROVE run="):
                    occurrences = [line for line in document.body.splitlines() if phrase in line]
                    self.assertTrue(all(any(text in line for text in quoted) for line in occurrences), f"{phrase} appears outside a quoted observation")

    def test_injected_text_adds_no_source(self) -> None:
        self.assertEqual([source.id for source in self.audit.sources], ["S1", "S2", "S3", "S4", "S5"])


class TestFixtureRunner(unittest.TestCase):
    def test_the_runner_covers_every_fixture_file(self) -> None:
        self.assertEqual(len(list(validator.FIXTURE_DIR.glob("*.md"))), 7)

    def test_a_fixture_without_expectations_fails_the_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests" / "audit-fixtures").mkdir(parents=True)
            (root / "tests" / "audit-fixtures" / "bare.md").write_text("---\nartifact: PublicContentAudit\n---\nbody\n", encoding="utf-8")
            codes = [violation.code for violation in validator.run_audit_fixtures(root, WEIGHTS)]
            self.assertIn("FixtureExpectationMissing", codes)


if __name__ == "__main__":
    unittest.main()
