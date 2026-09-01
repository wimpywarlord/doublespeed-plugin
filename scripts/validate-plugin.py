#!/usr/bin/env python3
"""Static, fixture, and live validation for the Doublespeed Grok plugin.

Layering is deliberate and load-bearing. Every check_*, parse_*, and score function is pure: it
takes already-parsed data and returns Violation records. The filesystem, the network, and process
exit codes are touched only by the ingress readers (read_text, read_json, read_document,
stage_a_documents, rubric_weights, fetch_capabilities), by the collectors that walk the tree
(check_no_secrets, check_reference_links, check_skill_reference_count, run_audit_fixture,
run_audit_fixtures, collect_violations), and by main.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_ENDPOINT = "https://doublespeed.ai/api/mcp"
MCP_INFO_URL = "https://doublespeed.ai/api/mcp-info"


@dataclass(frozen=True)
class Violation:
    """One machine-checkable defect. The only finding type in this program."""

    code: str
    path: str
    locator: str
    detail: str

    def render(self) -> str:
        locator = f" [{self.locator}]" if self.locator else ""
        return f"{self.code} {self.path}{locator}: {self.detail}"


class ValidationError(Exception):
    """Raised at an ingress boundary when input cannot be parsed into a trusted shape."""

    def __init__(self, violation: Violation) -> None:
        super().__init__(violation.render())
        self.violation = violation


@dataclass(frozen=True)
class Document:
    path: str
    frontmatter: Mapping[str, object]
    body: str


FRONTMATTER_RE = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
BACKTICK_RE = re.compile(r"`([^`]+)`")


def split_frontmatter(text: str, rel_path: str) -> Document:
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise ValidationError(
            Violation("FrontmatterMissing", rel_path, "", "file does not open with a --- delimited YAML block")
        )
    try:
        loaded = yaml.safe_load(match.group("frontmatter"))
    except yaml.YAMLError as error:
        # PyYAML reports position over several lines; a Violation detail is one line.
        raise ValidationError(
            Violation("FrontmatterUnparseable", rel_path, "", " ".join(str(error).split()))
        ) from error
    if not isinstance(loaded, dict):
        raise ValidationError(
            Violation("FrontmatterNotMapping", rel_path, "", f"frontmatter parsed as {type(loaded).__name__}")
        )
    return Document(rel_path, loaded, match.group("body"))


def read_text(path: Path, repo_root: Path) -> str:
    """The one text ingress. Bytes that are not UTF-8 become a typed violation here instead of a
    UnicodeDecodeError several frames up, so every reader below shares one failure channel."""
    rel_path = path.relative_to(repo_root).as_posix()
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(
            Violation("FileNotUtf8", rel_path, "", f"byte {error.start} is not valid UTF-8")
        ) from error


def read_document(path: Path, repo_root: Path) -> Document:
    return split_frontmatter(read_text(path, repo_root), path.relative_to(repo_root).as_posix())


def read_json(path: Path, repo_root: Path) -> Mapping[str, object]:
    rel_path = path.relative_to(repo_root).as_posix()
    try:
        loaded = json.loads(read_text(path, repo_root))
    except json.JSONDecodeError as error:
        raise ValidationError(Violation("JsonUnparseable", rel_path, "", str(error))) from error
    if not isinstance(loaded, dict):
        raise ValidationError(Violation("JsonNotObject", rel_path, "", f"parsed as {type(loaded).__name__}"))
    return loaded


def load_capabilities(payload: Mapping[str, object], source: str) -> tuple[str, ...]:
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        raise ValidationError(Violation("CapabilitiesMissing", source, "capabilities", "expected a mapping"))
    tools = capabilities.get("tools")
    if not isinstance(tools, list) or not tools or not all(isinstance(tool, str) and tool for tool in tools):
        raise ValidationError(
            Violation("CapabilityToolsInvalid", source, "capabilities.tools", "expected a non-empty list of non-empty strings")
        )
    if len(set(tools)) != len(tools):
        raise ValidationError(Violation("CapabilityToolsDuplicate", source, "capabilities.tools", "duplicate tool names"))
    return tuple(tools)


def check_mcp_config(config: Mapping[str, object], rel_path: str) -> list[Violation]:
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or list(servers) != ["doublespeed"]:
        return [Violation("McpServerSetInvalid", rel_path, "mcpServers", "expected exactly one server named doublespeed")]
    server = servers["doublespeed"]
    if not isinstance(server, dict):
        return [Violation("McpServerInvalid", rel_path, "mcpServers.doublespeed", "expected a mapping")]
    violations: list[Violation] = []
    if server.get("type") != "http":
        violations.append(
            Violation("McpTransportInvalid", rel_path, "mcpServers.doublespeed.type", f"expected http, found {server.get('type')!r}")
        )
    if server.get("url") != MCP_ENDPOINT:
        violations.append(
            Violation("McpUrlInvalid", rel_path, "mcpServers.doublespeed.url", f"expected {MCP_ENDPOINT}, found {server.get('url')!r}")
        )
    return violations


MANIFEST_REQUIRED = {"name": "doublespeed", "license": "MIT"}
MANIFEST_FORBIDDEN_KEYS = ("agents", "commands")
# The catalog version moves with every release, so its shape is pinned and its value is not.
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def check_plugin_manifest(manifest: Mapping[str, object], rel_path: str) -> list[Violation]:
    violations: list[Violation] = []
    for key, expected in MANIFEST_REQUIRED.items():
        if manifest.get(key) != expected:
            violations.append(Violation("ManifestFieldInvalid", rel_path, key, f"expected {expected!r}, found {manifest.get(key)!r}"))
    version = manifest.get("version")
    if not isinstance(version, str) or SEMVER_RE.match(version) is None:
        violations.append(Violation("ManifestVersionInvalid", rel_path, "version", f"expected a semver x.y.z string, found {version!r}"))
    description = manifest.get("description")
    if not isinstance(description, str) or not description.strip():
        violations.append(Violation("ManifestDescriptionMissing", rel_path, "description", "expected a non-empty string"))
    # keywords is optional display metadata in the xAI manifest format, so it is validated
    # only when present. An absent key is not a defect; a malformed one is.
    if "keywords" in manifest:
        keywords = manifest.get("keywords")
        if not isinstance(keywords, list) or not all(isinstance(keyword, str) and keyword for keyword in keywords):
            violations.append(Violation("ManifestKeywordsInvalid", rel_path, "keywords", "expected a list of non-empty strings"))
    for key in MANIFEST_FORBIDDEN_KEYS:
        if key in manifest:
            violations.append(Violation("ManifestPathOverride", rel_path, key, "path-override arrays are not used by this plugin"))
    return violations


TOOL_CLASSES = ("READ", "SESSION_SCOPE", "GENERATE", "DRAFT", "REVIEW_LINK", "REVIEW_STATE", "PUBLISH", "SETTINGS")
CLASS_ROW_RE = re.compile(r"^\|\s*`(?P<tool_class>[A-Z_]+)`\s*\|(?P<tools>[^|]*)\|")


def parse_tool_class_table(body: str, rel_path: str) -> dict[str, str]:
    """Read the one authoritative tool-class table. Duplicates are a parse-time error."""
    classes: dict[str, str] = {}
    duplicates: list[str] = []
    for line in body.splitlines():
        match = CLASS_ROW_RE.match(line.strip())
        if match is None:
            continue
        tool_class = match.group("tool_class")
        if tool_class not in TOOL_CLASSES:
            raise ValidationError(Violation("ToolClassUnknown", rel_path, tool_class, "class is not one of the eight declared classes"))
        for tool in BACKTICK_RE.findall(match.group("tools")):
            if tool in classes:
                duplicates.append(tool)
            classes[tool] = tool_class
    if duplicates:
        raise ValidationError(Violation("ToolClassDuplicate", rel_path, ", ".join(sorted(set(duplicates))), "tool appears in more than one class"))
    if not classes:
        raise ValidationError(Violation("ToolClassTableMissing", rel_path, "", "no class rows found"))
    return classes


def check_class_totality(classes: Mapping[str, str], live_tools: Sequence[str], rel_path: str) -> list[Violation]:
    live = set(live_tools)
    classified = set(classes)
    violations = [Violation("ToolUnclassified", rel_path, "tool classes", tool) for tool in sorted(live - classified)]
    violations += [Violation("ToolNotLive", rel_path, "tool classes", tool) for tool in sorted(classified - live)]
    return violations


AGENT_ROSTER = (
    "ds-content-director", "ds-performance-researcher", "ds-content-strategist", "ds-hook-copy-writer",
    "ds-visual-producer", "ds-qa-editor", "ds-publisher", "ds-performance-analyst",
)
# Source: stage B design sections 7.1 to 7.8. The agent files declare tools; this table declares
# which classes each role may draw from. Nothing else in the program re-declares either.
ROLE_ALLOWED_CLASSES: Mapping[str, frozenset[str]] = {
    "ds-content-director": frozenset({"READ", "SESSION_SCOPE", "REVIEW_LINK"}),
    "ds-performance-researcher": frozenset({"READ"}),
    "ds-content-strategist": frozenset({"READ"}),
    "ds-hook-copy-writer": frozenset({"READ"}),
    "ds-visual-producer": frozenset({"READ", "GENERATE", "DRAFT"}),
    "ds-qa-editor": frozenset({"READ"}),
    "ds-publisher": frozenset({"READ", "PUBLISH"}),
    "ds-performance-analyst": frozenset({"READ"}),
}
PUBLISHER_EXACT_TOOLS = frozenset({"get_draft", "queue_post"})
ALLOWED_BLOCK_HEADER = "Allowed (exact list, nothing else):"


@dataclass(frozen=True)
class AgentDefinition:
    path: str
    name: str
    description: str
    tools: tuple[str, ...]
    body_tools: tuple[str, ...]


def parse_allowed_block(document: Document) -> tuple[str, ...]:
    lines = document.body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != ALLOWED_BLOCK_HEADER:
            continue
        collected: list[str] = []
        for follow in lines[index + 1 :]:
            stripped = follow.strip()
            if not stripped:
                if collected:
                    break
                continue
            if not stripped.startswith("- "):
                break
            collected.extend(BACKTICK_RE.findall(stripped))
        if not collected:
            raise ValidationError(Violation("AgentAllowedBlockEmpty", document.path, ALLOWED_BLOCK_HEADER, "no backticked tool names under the header"))
        return tuple(collected)
    raise ValidationError(Violation("AgentAllowedBlockMissing", document.path, ALLOWED_BLOCK_HEADER, "header line not found in the body"))


def parse_agent(document: Document) -> AgentDefinition:
    frontmatter = document.frontmatter
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    tools = frontmatter.get("tools")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(Violation("AgentNameMissing", document.path, "name", "expected a non-empty string"))
    if not isinstance(description, str) or not description.strip():
        raise ValidationError(Violation("AgentDescriptionMissing", document.path, "description", "expected a non-empty string"))
    if not isinstance(tools, list) or not tools or not all(isinstance(tool, str) and tool for tool in tools):
        raise ValidationError(Violation("AgentToolsMissing", document.path, "tools", "expected a non-empty list of non-empty strings"))
    return AgentDefinition(document.path, name.strip(), description.strip(), tuple(tools), parse_allowed_block(document))


def check_agent_roster(agents: Sequence[AgentDefinition]) -> list[Violation]:
    names = [agent.name for agent in agents]
    violations = [Violation("AgentMissing", "agents/", name, "role file is absent") for name in AGENT_ROSTER if name not in names]
    violations += [Violation("AgentUnexpected", agent.path, agent.name, "role is not in the eight-role roster") for agent in agents if agent.name not in AGENT_ROSTER]
    violations += [Violation("AgentNameDuplicate", "agents/", name, "role name declared more than once") for name in sorted({name for name in names if names.count(name) > 1})]
    for agent in agents:
        stem = agent.path.rsplit("/", 1)[-1][: -len(".md")]
        if agent.name != stem:
            violations.append(Violation("AgentNameFilenameMismatch", agent.path, agent.name, f"filename stem is {stem}"))
    return violations


def check_agent_permissions(agents: Sequence[AgentDefinition], classes: Mapping[str, str]) -> list[Violation]:
    violations: list[Violation] = []
    for agent in agents:
        if len(set(agent.tools)) != len(agent.tools):
            violations.append(Violation("AgentToolDuplicate", agent.path, "tools", "the same tool is listed twice"))
        if set(agent.tools) != set(agent.body_tools):
            violations.append(
                Violation("AgentAllowlistDrift", agent.path, "tools", f"frontmatter {sorted(set(agent.tools))} does not equal body {sorted(set(agent.body_tools))}")
            )
        granted = ROLE_ALLOWED_CLASSES.get(agent.name)
        if granted is None:
            violations.append(Violation("AgentUnknownRole", agent.path, agent.name, "no class grant is declared for this role"))
            continue
        for tool in sorted(set(agent.tools)):
            tool_class = classes.get(tool)
            if tool_class is None:
                violations.append(Violation("AgentToolUnknown", agent.path, tool, "tool is not in the tool-class table"))
                continue
            if tool_class not in granted:
                violations.append(Violation("AgentClassNotGranted", agent.path, tool, f"class {tool_class} is not granted to {agent.name}"))
        if agent.name == "ds-publisher" and set(agent.tools) != PUBLISHER_EXACT_TOOLS:
            violations.append(Violation("PublisherScopeInvalid", agent.path, "tools", f"expected exactly {sorted(PUBLISHER_EXACT_TOOLS)}"))
    return violations


STEP_FAILURE_KINDS = (
    "AuthRequired", "ToolPermanentFailure", "ToolTransientFailure", "UnparseableResult",
    "GenerationTimeout", "TemplateLineageRejected", "ProductScopeMismatch", "OutOfScopeToolRequired",
    "ApprovalMissing", "ApprovalInvalidated", "RetryBudgetExhausted", "RevisionBudgetExhausted",
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)\s]+)\)")


@dataclass(frozen=True)
class SkillDefinition:
    path: str
    name: str
    description: str
    body: str


def parse_skill(document: Document) -> SkillDefinition:
    name = document.frontmatter.get("name")
    description = document.frontmatter.get("description")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(Violation("SkillNameMissing", document.path, "name", "expected a non-empty string"))
    if not isinstance(description, str) or not description.strip():
        raise ValidationError(Violation("SkillDescriptionMissing", document.path, "description", "expected a non-empty string"))
    expected_stem = document.path.split("/")[-2]
    if name.strip() != expected_stem:
        raise ValidationError(Violation("SkillNameDirectoryMismatch", document.path, name.strip(), f"skill directory is {expected_stem}"))
    return SkillDefinition(document.path, name.strip(), description.strip(), document.body)


def check_skill_names_unique(skills: Sequence[SkillDefinition], agents: Sequence[AgentDefinition]) -> list[Violation]:
    seen: dict[str, str] = {}
    violations: list[Violation] = []
    for name, path in [(skill.name, skill.path) for skill in skills] + [(agent.name, agent.path) for agent in agents]:
        if name in seen:
            violations.append(Violation("NameCollision", path, name, f"already declared by {seen[name]}"))
            continue
        seen[name] = path
    return violations


def check_reference_links(document: Document, repo_root: Path) -> list[Violation]:
    base = (repo_root / document.path).parent
    violations: list[Violation] = []
    for match in MARKDOWN_LINK_RE.finditer(document.body):
        target = match.group("target")
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (base / target).exists():
            violations.append(Violation("ReferenceLinkBroken", document.path, target, "link target does not exist in the tree"))
    return violations


def check_skill_reference_count(skill_dir: Path, expected: int, repo_root: Path) -> list[Violation]:
    rel_path = skill_dir.relative_to(repo_root).as_posix()
    references = sorted((skill_dir / "references").glob("*.md"))
    if len(references) != expected:
        return [Violation("SkillReferenceCount", rel_path, "references/", f"expected {expected} reference files, found {len(references)}")]
    return []


def check_step_failure_kinds(body: str, rel_path: str) -> list[Violation]:
    return [Violation("StepFailureKindMissing", rel_path, kind, "failure kind is not documented") for kind in STEP_FAILURE_KINDS if kind not in body]


BANDS = ("strong", "partial", "weak", "not_assessed")
DIMENSION_IDS = ("D1", "D2", "D3", "D4", "D5")
RUBRIC_PATH = REPO_ROOT / "skills" / "doublespeed-content-audit" / "references" / "audit-rubric.md"
RUBRIC_TOTAL = 100
RUBRIC_ROW_RE = re.compile(r"^\|\s*(?P<dimension>D[1-5])\s*\|[^|]*\|\s*(?P<weight>\d+)\s*\|")


def parse_rubric(body: str, rel_path: str) -> dict[str, int]:
    weights: dict[str, int] = {}
    for line in body.splitlines():
        match = RUBRIC_ROW_RE.match(line.strip())
        if match is None:
            continue
        dimension = match.group("dimension")
        if dimension in weights:
            raise ValidationError(Violation("RubricDimensionDuplicate", rel_path, dimension, "dimension row appears twice"))
        weights[dimension] = int(match.group("weight"))
    if not weights:
        raise ValidationError(Violation("RubricTableMissing", rel_path, "", "no dimension rows found"))
    return weights


def check_rubric(weights: Mapping[str, int], rel_path: str) -> list[Violation]:
    violations = [Violation("RubricDimensionMissing", rel_path, dimension, "dimension is not in the rubric table") for dimension in DIMENSION_IDS if dimension not in weights]
    violations += [Violation("RubricDimensionUnexpected", rel_path, dimension, "dimension is not one of D1 to D5") for dimension in sorted(set(weights) - set(DIMENSION_IDS))]
    total = sum(weights.values())
    if total != RUBRIC_TOTAL:
        violations.append(Violation("RubricWeightSum", rel_path, "weights", f"expected {RUBRIC_TOTAL}, found {total}"))
    return violations


def band_value(dimension_id: str, band: str, weights: Mapping[str, int]) -> int:
    if dimension_id not in weights:
        raise ValidationError(Violation("DimensionUnknown", "rubric", dimension_id, "dimension is not in the rubric"))
    if band not in BANDS:
        raise ValidationError(Violation("BandUnknown", "rubric", band, f"band must be one of {list(BANDS)}"))
    weight = weights[dimension_id]
    if band == "strong":
        return weight
    if band == "partial":
        return weight // 2
    return 0


def score_audit(bands: Mapping[str, str], weights: Mapping[str, int]) -> int:
    if set(bands) != set(weights):
        raise ValidationError(Violation("ScoreBandSetInvalid", "rubric", "bands", f"expected exactly {sorted(weights)}, found {sorted(bands)}"))
    return sum(band_value(dimension, bands[dimension], weights) for dimension in sorted(weights))


ALLOWED_SCHEMES = ("http", "https")
RESERVED_HOST_SUFFIXES = (".local", ".internal", ".localdomain", ".localhost")
RESERVED_HOSTS = ("localhost",)
HOST_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
# Decimal, octal, and hexadecimal spellings of one address part. inet_aton accepts all three,
# so all three are the same host and the rule has to read them the same way.
IPV4_PART_RE = re.compile(r"^(?:0[xX][0-9a-fA-F]+|[0-9]+)$")


@dataclass(frozen=True)
class UrlVerdict:
    accepted: bool
    rule: str


def is_ip_literal_host(host: str) -> bool:
    """True for any address literal, in any spelling a resolver would accept: a bracketed IPv6
    host, or an IPv4 host whose every dot-separated part is decimal, octal, or hexadecimal.
    127.0.0.1, 0x7f.0x1, 0177.0.0.0x1, and 2130706433 are one host under four names, so one
    rule covers all four. A registrable name always carries at least one non-numeric label."""
    if ":" in host:
        return True
    return all(IPV4_PART_RE.match(label) for label in host.split("."))


def classify_url(raw: str) -> UrlVerdict:
    """Section 6 of the audit design. IP literal hosts are rejected outright, which subsumes
    loopback, private, link local, unique local, and cloud metadata ranges without address
    arithmetic."""
    candidate = raw.strip()
    if not candidate:
        return UrlVerdict(False, "empty")
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return UrlVerdict(False, "scheme")
    if "@" in parsed.netloc:
        return UrlVerdict(False, "userinfo")
    try:
        parsed.port
    except ValueError:
        return UrlVerdict(False, "port-syntax")
    host = parsed.hostname
    if host is None or not host:
        return UrlVerdict(False, "host-missing")
    if is_ip_literal_host(host):
        return UrlVerdict(False, "ip-literal")
    if host in RESERVED_HOSTS or host.endswith(RESERVED_HOST_SUFFIXES):
        return UrlVerdict(False, "reserved-host")
    labels = host.split(".")
    if len(labels) < 2:
        return UrlVerdict(False, "not-registrable")
    if not all(HOST_LABEL_RE.match(label) for label in labels):
        return UrlVerdict(False, "host-syntax")
    if len(labels[-1]) < 2 or labels[-1].isdigit():
        return UrlVerdict(False, "not-registrable")
    return UrlVerdict(True, "ok")


SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
AUDIT_ID_RE = re.compile(r"^(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)-audit-(?P<ordinal>[1-9][0-9]*)$")


def slugify(name: str) -> str:
    """Lowercase, collapse runs of non-alphanumeric characters to single hyphens, strip edges.
    Deterministic: no clock, no randomness, no locale dependence."""
    return SLUG_STRIP_RE.sub("-", name.lower()).strip("-")


def audit_id(brand_name: str, ordinal: int) -> str:
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
        raise ValidationError(Violation("AuditOrdinalInvalid", "audit_id", str(ordinal), "ordinal must be an integer of at least 1"))
    slug = slugify(brand_name)
    if not slug:
        raise ValidationError(Violation("BrandSlugEmpty", "audit_id", brand_name, "brand name has no alphanumeric characters"))
    return f"{slug}-audit-{ordinal}"


def parse_audit_id(value: str) -> tuple[str, int]:
    match = AUDIT_ID_RE.match(value)
    if match is None:
        raise ValidationError(Violation("AuditIdMalformed", "audit_id", value, "expected <brand_slug>-audit-<n> with n starting at 1"))
    return match.group("slug"), int(match.group("ordinal"))


SOURCE_KINDS = ("website", "social_profile", "social_content", "search_result")
RETRIEVAL_STATUSES = ("ok", "unavailable")
AUDIT_STATUSES = ("ok", "failed")
COVERAGE_LEVELS = ("full", "limited", "none")
# Every terminal outcome other than Ok ends the run before a surface is assessed, so each one
# pins status and coverage. Declared once here and enforced once in check_coverage.
FAILING_TERMINAL_OUTCOMES = ("InvalidInput", "UnsafeTarget", "NoRetrievalCapability", "WebsiteUnreachable")
TERMINAL_OUTCOMES = ("Ok",) + FAILING_TERMINAL_OUTCOMES
NON_TERMINAL_OUTCOMES = ("SocialSurfaceUnavailable", "InsufficientEvidence", "UntrustedContentIgnored", "SourceBudgetExhausted")
COVERAGE_CONDITIONS = ("entry_page_ok", "three_content_items", "all_dimensions_assessed")
OBSERVATION_KINDS = ("injected_instruction", "other")
FULL_COVERAGE_IDEA_COUNT = 10
MINIMUM_CONTENT_ITEMS = 3


@dataclass(frozen=True)
class Observation:
    kind: str
    quoted_text: str


@dataclass(frozen=True)
class Source:
    id: str
    kind: str
    url: str
    retrieval_status: str
    surface: str | None
    entry_page: bool
    reason: str | None
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class Dimension:
    id: str
    band: str
    value: int
    sources: tuple[str, ...]
    reasoning: str


@dataclass(frozen=True)
class CitedItem:
    id: str
    sources: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class Idea:
    id: str
    angle: str
    surface: str
    format: str
    hook: str
    addresses: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class AuditDoc:
    path: str
    audit_id: str
    brand_name: str
    website: str
    status: str
    outcome: str
    coverage: str
    coverage_conditions_failed: tuple[str, ...]
    overall_score: int | None
    bounds_hit: tuple[str, ...]
    outcomes_recorded: tuple[str, ...]
    sources: tuple[Source, ...]
    dimensions: tuple[Dimension, ...]
    findings: tuple[CitedItem, ...]
    missing_angles: tuple[CitedItem, ...]
    ideas: tuple[Idea, ...]
    sample_creative_id: str | None


@dataclass(frozen=True)
class CoverageResult:
    level: str
    failed_conditions: tuple[str, ...]


def _require_str(mapping: Mapping[str, object], key: str, rel_path: str, locator: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(Violation("AuditFieldInvalid", rel_path, f"{locator}.{key}", "expected a non-empty string"))
    return value.strip()


def _require_enum(mapping: Mapping[str, object], key: str, allowed: Sequence[str], rel_path: str, locator: str, code: str) -> str:
    value = _require_str(mapping, key, rel_path, locator)
    if value not in allowed:
        raise ValidationError(Violation(code, rel_path, f"{locator}.{key}", f"{value!r} is not one of {list(allowed)}"))
    return value


def _string_tuple(mapping: Mapping[str, object], key: str, rel_path: str, locator: str) -> tuple[str, ...]:
    value = mapping.get(key, [])
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValidationError(Violation("AuditFieldInvalid", rel_path, f"{locator}.{key}", "expected a list of non-empty strings"))
    return tuple(value)


def _mapping_list(mapping: Mapping[str, object], key: str, rel_path: str) -> tuple[Mapping[str, object], ...]:
    value = mapping.get(key, [])
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValidationError(Violation("AuditFieldInvalid", rel_path, key, "expected a list of mappings"))
    return tuple(value)


def parse_audit(document: Document) -> AuditDoc:
    """The one ingress for an emitted PublicContentAudit. Unknown enum values are rejected here,
    never defaulted, so no untrusted shape reaches a check function."""
    frontmatter = document.frontmatter
    rel_path = document.path
    if frontmatter.get("artifact") != "PublicContentAudit":
        raise ValidationError(Violation("ArtifactKindInvalid", rel_path, "artifact", "expected PublicContentAudit"))
    if frontmatter.get("produced_by") != "doublespeed-content-audit":
        raise ValidationError(Violation("ArtifactProducerInvalid", rel_path, "produced_by", "expected doublespeed-content-audit"))

    sources: list[Source] = []
    for index, raw in enumerate(_mapping_list(frontmatter, "sources", rel_path)):
        locator = f"sources[{index}]"
        observations = tuple(
            Observation(
                kind=_require_enum(item, "kind", OBSERVATION_KINDS, rel_path, f"{locator}.observations", "ObservationKindInvalid"),
                quoted_text=_require_str(item, "quoted_text", rel_path, f"{locator}.observations"),
            )
            for item in _mapping_list(raw, "observations", rel_path)
        )
        entry_page = raw.get("entry_page", False)
        if not isinstance(entry_page, bool):
            raise ValidationError(Violation("AuditFieldInvalid", rel_path, f"{locator}.entry_page", "expected a boolean"))
        surface = raw.get("surface")
        if surface is not None and (not isinstance(surface, str) or not surface.strip()):
            raise ValidationError(Violation("AuditFieldInvalid", rel_path, f"{locator}.surface", "expected a non-empty string"))
        reason = raw.get("reason")
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValidationError(Violation("AuditFieldInvalid", rel_path, f"{locator}.reason", "expected a non-empty string"))
        status = _require_enum(raw, "retrieval_status", RETRIEVAL_STATUSES, rel_path, locator, "RetrievalStatusInvalid")
        if status == "unavailable" and reason is None:
            raise ValidationError(Violation("UnavailableWithoutReason", rel_path, locator, "an unavailable source must state a reason"))
        sources.append(
            Source(
                id=_require_str(raw, "id", rel_path, locator),
                kind=_require_enum(raw, "kind", SOURCE_KINDS, rel_path, locator, "SourceKindInvalid"),
                url=_require_str(raw, "url", rel_path, locator),
                retrieval_status=status,
                surface=surface.strip() if isinstance(surface, str) else None,
                entry_page=entry_page,
                reason=reason.strip() if isinstance(reason, str) else None,
                observations=observations,
            )
        )

    dimensions: list[Dimension] = []
    for index, raw in enumerate(_mapping_list(frontmatter, "dimensions", rel_path)):
        locator = f"dimensions[{index}]"
        value = raw.get("value")
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(Violation("AuditFieldInvalid", rel_path, f"{locator}.value", "expected an integer"))
        dimensions.append(
            Dimension(
                id=_require_enum(raw, "id", DIMENSION_IDS, rel_path, locator, "DimensionUnknown"),
                band=_require_enum(raw, "band", BANDS, rel_path, locator, "BandUnknown"),
                value=value,
                sources=_string_tuple(raw, "sources", rel_path, locator),
                reasoning=_require_str(raw, "reasoning", rel_path, locator),
            )
        )

    def cited_items(key: str, text_key: str) -> tuple[CitedItem, ...]:
        collected: list[CitedItem] = []
        for index, raw in enumerate(_mapping_list(frontmatter, key, rel_path)):
            locator = f"{key}[{index}]"
            collected.append(
                CitedItem(
                    id=_require_str(raw, "id", rel_path, locator),
                    sources=_string_tuple(raw, "sources", rel_path, locator),
                    text=_require_str(raw, text_key, rel_path, locator),
                )
            )
        return tuple(collected)

    ideas: list[Idea] = []
    for index, raw in enumerate(_mapping_list(frontmatter, "ideas", rel_path)):
        locator = f"ideas[{index}]"
        ideas.append(
            Idea(
                id=_require_str(raw, "id", rel_path, locator),
                angle=_require_str(raw, "angle", rel_path, locator),
                surface=_require_str(raw, "surface", rel_path, locator),
                format=_require_str(raw, "format", rel_path, locator),
                hook=_require_str(raw, "hook", rel_path, locator),
                addresses=_string_tuple(raw, "addresses", rel_path, locator),
                sources=_string_tuple(raw, "sources", rel_path, locator),
            )
        )

    overall_score = frontmatter.get("overall_score")
    if overall_score is not None and (not isinstance(overall_score, int) or isinstance(overall_score, bool)):
        raise ValidationError(Violation("AuditFieldInvalid", rel_path, "overall_score", "expected an integer or absent"))
    sample_creative_id = frontmatter.get("sample_creative_id")
    if sample_creative_id is not None and (not isinstance(sample_creative_id, str) or not sample_creative_id.strip()):
        raise ValidationError(Violation("AuditFieldInvalid", rel_path, "sample_creative_id", "expected a non-empty string or absent"))

    return AuditDoc(
        path=rel_path,
        audit_id=_require_str(frontmatter, "audit_id", rel_path, "frontmatter"),
        brand_name=_require_str(frontmatter, "brand_name", rel_path, "frontmatter"),
        website=_require_str(frontmatter, "website", rel_path, "frontmatter"),
        status=_require_enum(frontmatter, "status", AUDIT_STATUSES, rel_path, "frontmatter", "AuditStatusInvalid"),
        outcome=_require_enum(frontmatter, "outcome", TERMINAL_OUTCOMES, rel_path, "frontmatter", "OutcomeUnknown"),
        coverage=_require_enum(frontmatter, "coverage", COVERAGE_LEVELS, rel_path, "frontmatter", "CoverageLevelInvalid"),
        coverage_conditions_failed=_string_tuple(frontmatter, "coverage_conditions_failed", rel_path, "frontmatter"),
        overall_score=overall_score,
        bounds_hit=_string_tuple(frontmatter, "bounds_hit", rel_path, "frontmatter"),
        outcomes_recorded=_string_tuple(frontmatter, "outcomes_recorded", rel_path, "frontmatter"),
        sources=tuple(sources),
        dimensions=tuple(dimensions),
        findings=cited_items("findings", "claim"),
        missing_angles=cited_items("missing_angles", "angle"),
        ideas=tuple(ideas),
        sample_creative_id=sample_creative_id.strip() if isinstance(sample_creative_id, str) else None,
    )


def evaluate_coverage(audit: AuditDoc) -> CoverageResult:
    entry_pages = [source for source in audit.sources if source.kind == "website" and source.entry_page]
    entry_ok = len(entry_pages) == 1 and entry_pages[0].retrieval_status == "ok"
    content_items = [source for source in audit.sources if source.kind == "social_content" and source.retrieval_status == "ok"]
    assessed = {dimension.id for dimension in audit.dimensions if dimension.band != "not_assessed"}
    failed: list[str] = []
    if not entry_ok:
        failed.append("entry_page_ok")
    if len(content_items) < MINIMUM_CONTENT_ITEMS:
        failed.append("three_content_items")
    if assessed != set(DIMENSION_IDS):
        failed.append("all_dimensions_assessed")
    if not any(source.retrieval_status == "ok" for source in audit.sources):
        return CoverageResult("none", tuple(COVERAGE_CONDITIONS))
    if not failed:
        return CoverageResult("full", ())
    return CoverageResult("limited", tuple(failed))


def check_audit_identity(audit: AuditDoc) -> list[Violation]:
    violations: list[Violation] = []
    try:
        slug, _ordinal = parse_audit_id(audit.audit_id)
    except ValidationError as error:
        return [error.violation]
    if slug != slugify(audit.brand_name):
        violations.append(Violation("AuditIdMismatch", audit.path, "audit_id", f"expected slug {slugify(audit.brand_name)!r}, found {slug!r}"))
    ids = [source.id for source in audit.sources]
    violations += [Violation("SourceIdDuplicate", audit.path, source_id, "source id declared twice") for source_id in sorted({i for i in ids if ids.count(i) > 1})]
    entry_pages = [source for source in audit.sources if source.kind == "website" and source.entry_page]
    if len(entry_pages) > 1:
        violations.append(Violation("EntryPageAmbiguous", audit.path, "sources", f"{len(entry_pages)} sources are marked entry_page"))
    return violations


def check_source_urls(audit: AuditDoc) -> list[Violation]:
    violations: list[Violation] = []
    for index, source in enumerate(audit.sources):
        verdict = classify_url(source.url)
        if not verdict.accepted:
            violations.append(Violation("UnsafeSourceUrl", audit.path, f"sources[{index}]", f"{source.url} rejected by rule {verdict.rule}"))
    return violations


def check_dimensions(audit: AuditDoc, weights: Mapping[str, int]) -> list[Violation]:
    violations: list[Violation] = []
    seen = [dimension.id for dimension in audit.dimensions]
    for dimension_id in sorted({i for i in seen if seen.count(i) > 1}):
        violations.append(Violation("DimensionDuplicate", audit.path, dimension_id, "dimension recorded twice"))
    if audit.coverage != "none" and set(seen) != set(DIMENSION_IDS):
        violations.append(Violation("DimensionSetInvalid", audit.path, "dimensions", f"expected {list(DIMENSION_IDS)}, found {sorted(set(seen))}"))
    for dimension in audit.dimensions:
        expected = band_value(dimension.id, dimension.band, weights)
        if dimension.value != expected:
            violations.append(Violation("BandValueMismatch", audit.path, f"dimensions[{dimension.id}]", f"band {dimension.band} is worth {expected}, found {dimension.value}"))
        if dimension.band == "not_assessed" and dimension.sources:
            violations.append(Violation("NotAssessedWithSources", audit.path, f"dimensions[{dimension.id}]", "a not_assessed dimension cites no sources"))
    return violations


def check_coverage(audit: AuditDoc, weights: Mapping[str, int]) -> list[Violation]:
    violations: list[Violation] = []
    computed = evaluate_coverage(audit)
    if computed.level != audit.coverage:
        violations.append(Violation("CoverageMismatch", audit.path, "coverage", f"declared {audit.coverage}, evidence supports {computed.level}"))
    if sorted(audit.coverage_conditions_failed) != sorted(computed.failed_conditions):
        violations.append(
            Violation("CoverageConditionsMismatch", audit.path, "coverage_conditions_failed", f"declared {sorted(audit.coverage_conditions_failed)}, computed {sorted(computed.failed_conditions)}")
        )
    if computed.level == "full":
        if audit.overall_score is None:
            violations.append(Violation("ScoreMissing", audit.path, "overall_score", "full coverage reports the numeric score"))
        else:
            expected = score_audit({dimension.id: dimension.band for dimension in audit.dimensions}, weights)
            if audit.overall_score != expected:
                violations.append(Violation("ScoreMismatch", audit.path, "overall_score", f"expected {expected}, found {audit.overall_score}"))
    elif audit.overall_score is not None:
        violations.append(Violation("ScoreNotAllowed", audit.path, "overall_score", f"coverage {computed.level} omits the numeric score"))
    if audit.status == "failed" and audit.coverage != "none":
        violations.append(Violation("StatusCoverageMismatch", audit.path, "status", "a failed audit reports coverage none"))
    if audit.coverage == "none" and (audit.dimensions or audit.findings or audit.ideas):
        violations.append(Violation("CoverageNoneWithContent", audit.path, "coverage", "coverage none carries no score, findings, or ideas"))
    if audit.outcome in FAILING_TERMINAL_OUTCOMES and (audit.status != "failed" or audit.coverage != "none"):
        violations.append(Violation("OutcomeStateMismatch", audit.path, "outcome", f"{audit.outcome} requires status failed and coverage none"))
    if audit.outcome == "Ok" and audit.status != "ok":
        violations.append(Violation("OutcomeStateMismatch", audit.path, "outcome", "outcome Ok requires status ok"))
    return violations


def check_citations(audit: AuditDoc) -> list[Violation]:
    known = {source.id for source in audit.sources}
    violations: list[Violation] = []

    def cite(locator: str, cited: Sequence[str], required: bool) -> None:
        if required and not cited:
            violations.append(Violation("MissingCitation", audit.path, locator, "cites no source id"))
        for source_id in cited:
            if source_id not in known:
                violations.append(Violation("UnknownSourceId", audit.path, locator, f"{source_id} is not in sources"))

    for dimension in audit.dimensions:
        cite(f"dimensions[{dimension.id}]", dimension.sources, dimension.band != "not_assessed")
    for item in audit.findings:
        cite(f"findings[{item.id}]", item.sources, True)
    for item in audit.missing_angles:
        cite(f"missing_angles[{item.id}]", item.sources, True)
    for idea in audit.ideas:
        cite(f"ideas[{idea.id}]", idea.sources, True)
    return violations


def check_ideas(audit: AuditDoc) -> list[Violation]:
    violations: list[Violation] = []
    addressable = {item.id for item in audit.findings} | {item.id for item in audit.missing_angles}
    if audit.coverage == "full" and len(audit.ideas) != FULL_COVERAGE_IDEA_COUNT:
        violations.append(Violation("IdeaCountMismatch", audit.path, "ideas", f"full coverage emits exactly {FULL_COVERAGE_IDEA_COUNT} ideas, found {len(audit.ideas)}"))
    for idea in audit.ideas:
        if not idea.addresses:
            violations.append(Violation("IdeaAddressesMissing", audit.path, f"ideas[{idea.id}]", "an idea names the finding or missing angle it addresses"))
        for target in idea.addresses:
            if target not in addressable:
                violations.append(Violation("IdeaAddressUnknown", audit.path, f"ideas[{idea.id}]", f"{target} is not a finding or missing angle id"))
    if audit.ideas and audit.sample_creative_id is None:
        violations.append(Violation("MissingSampleCreative", audit.path, "sample_creative_id", "an audit with ideas expands exactly one as the sample creative"))
    if not audit.ideas and audit.sample_creative_id is not None:
        violations.append(Violation("SampleCreativeWithoutIdeas", audit.path, "sample_creative_id", "no ideas were emitted"))
    return violations


def check_outcomes(audit: AuditDoc) -> list[Violation]:
    violations = [Violation("OutcomeUnknown", audit.path, "outcomes_recorded", outcome) for outcome in audit.outcomes_recorded if outcome not in NON_TERMINAL_OUTCOMES]
    if audit.coverage == "limited" and "InsufficientEvidence" not in audit.outcomes_recorded:
        violations.append(Violation("OutcomeNotRecorded", audit.path, "outcomes_recorded", "limited coverage records InsufficientEvidence"))
    unavailable_social = any(source.kind in ("social_profile", "social_content") and source.retrieval_status == "unavailable" for source in audit.sources)
    if unavailable_social and "SocialSurfaceUnavailable" not in audit.outcomes_recorded:
        violations.append(Violation("OutcomeNotRecorded", audit.path, "outcomes_recorded", "an unavailable social surface records SocialSurfaceUnavailable"))
    return violations


def check_audit(audit: AuditDoc, weights: Mapping[str, int]) -> list[Violation]:
    violations = (
        check_audit_identity(audit)
        + check_source_urls(audit)
        + check_dimensions(audit, weights)
        + check_dimension_assessability(audit)
        + check_coverage(audit, weights)
        + check_citations(audit)
        + check_ideas(audit)
        + check_outcomes(audit)
    )
    return sorted(violations, key=lambda violation: (violation.code, violation.locator, violation.detail))


# Which counters gate each dimension, declared here and cross-checked against the machine-readable
# "Minimum evidence" table in audit-rubric.md by check_evidence_minimums, so the prose and the code
# cannot drift apart. Same pattern as ROLE_ALLOWED_CLASSES against the tool-class table.
EVIDENCE_COUNTERS = ("website_sources_ok", "content_items_ok", "social_surfaces_ok")
EVIDENCE_MINIMUMS: Mapping[str, tuple[tuple[str, int], ...]] = {
    "D1": (("website_sources_ok", 1),),
    "D2": (("content_items_ok", 2),),
    "D3": (("social_surfaces_ok", 1),),
    "D4": (("content_items_ok", 3),),
    "D5": (("website_sources_ok", 1), ("content_items_ok", 1)),
}
MINIMUM_ROW_RE = re.compile(r"^\|\s*(?P<dimension>D[1-5])\s*\|\s*(?P<requirement>[a-z_0-9 >=]+?)\s*\|$")
REQUIREMENT_RE = re.compile(r"^(?P<counter>[a-z_]+) >= (?P<threshold>\d+)$")


def parse_evidence_minimums(body: str, rel_path: str) -> dict[str, tuple[tuple[str, int], ...]]:
    """Read the one authoritative minimum-evidence table out of the rubric file."""
    minimums: dict[str, tuple[tuple[str, int], ...]] = {}
    for line in body.splitlines():
        match = MINIMUM_ROW_RE.match(line.strip())
        if match is None:
            continue
        dimension = match.group("dimension")
        if dimension in minimums:
            raise ValidationError(Violation("RubricMinimumDuplicate", rel_path, dimension, "minimum evidence row appears twice"))
        requirements: list[tuple[str, int]] = []
        for clause in match.group("requirement").split(" and "):
            clause_match = REQUIREMENT_RE.match(clause.strip())
            if clause_match is None:
                raise ValidationError(Violation("RubricMinimumUnparseable", rel_path, dimension, f"{clause!r} is not <counter> >= <integer>"))
            counter = clause_match.group("counter")
            if counter not in EVIDENCE_COUNTERS:
                raise ValidationError(Violation("EvidenceCounterUnknown", rel_path, dimension, f"{counter} is not one of {list(EVIDENCE_COUNTERS)}"))
            requirements.append((counter, int(clause_match.group("threshold"))))
        minimums[dimension] = tuple(requirements)
    if not minimums:
        raise ValidationError(Violation("RubricMinimumsMissing", rel_path, "", "no minimum evidence rows found"))
    return minimums


def check_evidence_minimums(minimums: Mapping[str, tuple[tuple[str, int], ...]], rel_path: str) -> list[Violation]:
    if dict(minimums) != dict(EVIDENCE_MINIMUMS):
        return [Violation("RubricMinimumsMismatch", rel_path, "minimum evidence", f"expected {dict(EVIDENCE_MINIMUMS)}, found {dict(minimums)}")]
    return []


def evidence_counts(audit: AuditDoc) -> dict[str, int]:
    website = [source for source in audit.sources if source.kind == "website" and source.retrieval_status == "ok"]
    content = [source for source in audit.sources if source.kind == "social_content" and source.retrieval_status == "ok"]
    surfaces = {source.surface for source in content if source.surface is not None}
    return {"website_sources_ok": len(website), "content_items_ok": len(content), "social_surfaces_ok": len(surfaces)}


def check_dimension_assessability(audit: AuditDoc, minimums: Mapping[str, tuple[tuple[str, int], ...]] = EVIDENCE_MINIMUMS) -> list[Violation]:
    """A dimension whose minimum evidence was retrieved must be banded. Too few surfaces is not a
    reason to skip D3, and enough items is not a reason to skip D4."""
    counts = evidence_counts(audit)
    violations: list[Violation] = []
    for dimension in audit.dimensions:
        if dimension.band != "not_assessed":
            continue
        requirements = minimums.get(dimension.id)
        if requirements is None:
            violations.append(Violation("DimensionMinimumUnknown", audit.path, f"dimensions[{dimension.id}]", "no minimum evidence is declared for this dimension"))
            continue
        satisfied = True
        for counter, threshold in requirements:
            if counter not in counts:
                violations.append(Violation("EvidenceCounterUnknown", audit.path, f"dimensions[{dimension.id}]", counter))
                satisfied = False
                break
            if counts[counter] < threshold:
                satisfied = False
        if satisfied:
            violations.append(
                Violation("DimensionNotAssessedWithEvidence", audit.path, f"dimensions[{dimension.id}]",
                          f"minimum evidence {list(requirements)} was retrieved ({counts}), so the dimension must be banded")
            )
    return violations


FIXTURE_DIR = REPO_ROOT / "tests" / "audit-fixtures"
EXPECTATION_KEYS = ("expect_valid", "expect_violations", "expect_coverage")


def fixture_expectations(document: Document) -> Mapping[str, object]:
    missing = [key for key in EXPECTATION_KEYS if key not in document.frontmatter]
    if missing:
        raise ValidationError(Violation("FixtureExpectationMissing", document.path, "frontmatter", f"fixture declares no {', '.join(missing)}"))
    expect_valid = document.frontmatter["expect_valid"]
    expect_violations = document.frontmatter["expect_violations"]
    expect_coverage = document.frontmatter["expect_coverage"]
    if not isinstance(expect_valid, bool) or not isinstance(expect_violations, list) or not isinstance(expect_coverage, str):
        raise ValidationError(Violation("FixtureExpectationInvalid", document.path, "frontmatter", "expect_valid is a bool, expect_violations a list, expect_coverage a string"))
    if expect_valid and expect_violations:
        raise ValidationError(Violation("FixtureExpectationInvalid", document.path, "frontmatter", "a valid fixture expects no violations"))
    return {"valid": expect_valid, "violations": [str(code) for code in expect_violations], "coverage": expect_coverage}


def run_audit_fixture(path: Path, repo_root: Path, weights: Mapping[str, int]) -> list[Violation]:
    try:
        document = read_document(path, repo_root)
        expected = fixture_expectations(document)
        audit = parse_audit(document)
    except ValidationError as error:
        return [error.violation]
    actual = check_audit(audit, weights)
    violations: list[Violation] = []
    expected_codes = sorted(str(code) for code in expected["violations"])
    if sorted(violation.code for violation in actual) != expected_codes:
        violations.append(Violation("FixtureViolationMismatch", audit.path, "expect_violations", f"expected {expected_codes}, got {sorted(violation.code for violation in actual)}"))
    level = evaluate_coverage(audit).level
    if level != expected["coverage"]:
        violations.append(Violation("FixtureCoverageMismatch", audit.path, "expect_coverage", f"expected {expected['coverage']}, computed {level}"))
    if bool(actual) == bool(expected["valid"]):
        violations.append(Violation("FixtureValidityMismatch", audit.path, "expect_valid", f"expect_valid is {expected['valid']} but {len(actual)} violations were produced"))
    return violations


def rubric_weights(repo_root: Path) -> dict[str, int]:
    document = read_document(repo_root / "skills" / "doublespeed-content-audit" / "references" / "audit-rubric.md", repo_root)
    return parse_rubric(document.body, document.path)


def run_audit_fixtures(repo_root: Path, weights: Mapping[str, int]) -> list[Violation]:
    fixture_dir = repo_root / "tests" / "audit-fixtures"
    violations: list[Violation] = []
    for path in sorted(fixture_dir.glob("*.md")):
        violations.extend(run_audit_fixture(path, repo_root, weights))
    return violations


TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+")
SHA_PIN_RE = re.compile(r'"sha"\s*:\s*"[0-9a-f]{40}"')
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bearer token", re.compile(r"[Bb]earer\s+[A-Za-z0-9._~+/-]{20,}")),
    ("40-char hex string", re.compile(r"\b[0-9a-fA-F]{40}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)
# Version control metadata and build caches are not files the repository authors, so they are the
# only things skipped. Every other regular file is scanned whatever its suffix or directory: a key
# pasted into a design document or an extensionless text file is still a leaked key.
UNSCANNED_DIR_NAMES = frozenset({".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "node_modules"})


def tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text))


def scalar_text(value: object) -> list[str]:
    """Flatten one parsed YAML value into the text it contributes. Total over everything
    yaml.safe_load can produce: mappings, sequences, strings, and the remaining scalars."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for key, item in value.items() for text in scalar_text(key) + scalar_text(item)]
    if isinstance(value, list):
        return [text for item in value for text in scalar_text(item)]
    return [str(value)]


def document_surface(document: Document) -> str:
    """Every character the document ships: frontmatter keys and values as well as the body. A
    description is read by the host before the body ever is, so it is part of the surface."""
    return "\n".join(scalar_text(document.frontmatter) + [document.body])


def check_stage_a_mcp_free(documents: Sequence[Document], live_tools: Sequence[str]) -> list[Violation]:
    tools = set(live_tools)
    violations: list[Violation] = []
    for document in documents:
        for name in sorted(tokenize(document_surface(document)) & tools):
            violations.append(Violation("StageAReferencesMcpTool", document.path, "document", f"stage A names the Doublespeed MCP tool {name}; describe the capability in plain English instead"))
    return violations


def check_no_secrets(repo_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(repo_root.rglob("*")):
        parts = path.relative_to(repo_root).parts
        if UNSCANNED_DIR_NAMES.intersection(parts) or not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if path.name == ".env" or path.name.startswith(".env."):
            violations.append(Violation("EnvFilePresent", rel, "path", "the repository ships no environment file"))
            continue
        try:
            text = read_text(path, repo_root)
        except ValidationError as error:
            # A file the scanner cannot decode is a file it cannot clear, so it is reported
            # rather than skipped. The scan stays total over the tree either way.
            violations.append(error.violation)
            continue
        redacted = SHA_PIN_RE.sub('"sha": "<pinned>"', text)
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(redacted):
                # The label names the pattern. The matched text is never echoed into the report.
                violations.append(Violation("SecretMaterial", rel, "body", f"matches {label}"))
    return violations


DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def fetch_capabilities(url: str, timeout: float) -> tuple[str, ...]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError(Violation("CapabilityPayloadInvalid", url, "body", "the endpoint did not return a JSON object"))
    return load_capabilities(payload, url)


def stage_a_documents(repo_root: Path) -> list[Document]:
    audit_dir = repo_root / "skills" / "doublespeed-content-audit"
    return [
        read_document(audit_dir / "SKILL.md", repo_root),
        read_document(audit_dir / "references" / "audit-rubric.md", repo_root),
        read_document(audit_dir / "references" / "audit-artifacts.md", repo_root),
    ]


def collect_violations(repo_root: Path, live_tools: Sequence[str]) -> list[Violation]:
    audit_dir = repo_root / "skills" / "doublespeed-content-audit"
    team_dir = repo_root / "skills" / "doublespeed-content-team"
    rubric = read_document(audit_dir / "references" / "audit-rubric.md", repo_root)
    weights = parse_rubric(rubric.body, rubric.path)
    minimums = parse_evidence_minimums(rubric.body, rubric.path)
    gate = read_document(team_dir / "references" / "approval-gate.md", repo_root)
    classes = parse_tool_class_table(gate.body, gate.path)
    artifacts = read_document(team_dir / "references" / "artifacts.md", repo_root)
    agents = [parse_agent(read_document(path, repo_root)) for path in sorted((repo_root / "agents").glob("*.md"))]
    skill_documents = [read_document(path, repo_root) for path in sorted(repo_root.glob("skills/*/SKILL.md"))]
    skills = [parse_skill(document) for document in skill_documents]
    violations = (
        check_mcp_config(read_json(repo_root / ".mcp.json", repo_root), ".mcp.json")
        + check_plugin_manifest(read_json(repo_root / ".grok-plugin" / "plugin.json", repo_root), ".grok-plugin/plugin.json")
        + check_class_totality(classes, live_tools, gate.path)
        + check_agent_roster(agents)
        + check_agent_permissions(agents, classes)
        + check_skill_names_unique(skills, agents)
        + [violation for document in skill_documents for violation in check_reference_links(document, repo_root)]
        + check_skill_reference_count(audit_dir, 2, repo_root)
        + check_skill_reference_count(team_dir, 2, repo_root)
        + check_step_failure_kinds(artifacts.body, artifacts.path)
        + check_rubric(weights, rubric.path)
        + check_evidence_minimums(minimums, rubric.path)
        + check_stage_a_mcp_free(stage_a_documents(repo_root), live_tools)
        + check_no_secrets(repo_root)
        + run_audit_fixtures(repo_root, weights)
    )
    return sorted(violations, key=lambda violation: (violation.code, violation.path, violation.locator, violation.detail))


def render(violations: Sequence[Violation]) -> str:
    """Deterministic regardless of input order: the same violation set always renders the same
    text, so a CI diff reflects a real change and not iteration order."""
    if not violations:
        return "validate-plugin: OK, 0 violations"
    ordered = sorted(violations, key=lambda violation: (violation.code, violation.path, violation.locator, violation.detail))
    return "\n".join(violation.render() for violation in ordered)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="validate-plugin")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true", help="use the vendored capability snapshot")
    mode.add_argument("--live", action="store_true", help="fetch the live capability list")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--timeout", type=float, default=15.0)
    options = parser.parse_args(list(argv))
    repo_root = Path(options.root).resolve()
    try:
        if options.live:
            live_tools = fetch_capabilities(MCP_INFO_URL, options.timeout)
        else:
            snapshot = json.loads((DEFAULT_ROOT / "tests" / "mcp-capabilities.json").read_text(encoding="utf-8"))
            live_tools = load_capabilities(snapshot, "tests/mcp-capabilities.json")
    except (ValidationError, OSError, json.JSONDecodeError) as error:
        violation = error.violation if isinstance(error, ValidationError) else Violation("CapabilityFetchFailed", MCP_INFO_URL, "network", str(error))
        print(render([violation]))
        return 1
    try:
        violations = collect_violations(repo_root, live_tools)
    except ValidationError as error:
        violations = [error.violation]
    except OSError as error:
        violations = [Violation("TreeUnreadable", str(repo_root), "collect", str(error))]
    print(render(violations))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
