# Doublespeed plugin for Grok

Two entry points on one install. **Stage A** is a free public content audit: give it a brand
website and, optionally, public social handles, and it returns an evidence-cited audit scored
against a five-dimension rubric, ten campaign ideas, and one written sample creative, with no
Doublespeed account and no call to the Doublespeed MCP. **Stage B** is the connected content team:
eight role-scoped agents that research a product, plan concepts, write hooks and slide copy,
produce slideshow or video drafts, QA them, create a review link, and queue only what a human
explicitly approves.

## What is in the box

| Path | What it is |
| --- | --- |
| `skills/doublespeed-content-audit/` | Stage A. Free, public data only, no account. One skill and two references. |
| `skills/doublespeed-content-team/` | Stage B. Connected, eight roles, human approval gate. One skill and two references. |
| `agents/` | The eight role definitions, each with its own tool allowlist. |
| `.mcp.json` | The one hosted MCP server, `https://doublespeed.ai/api/mcp`, over HTTP. |
| `.grok-plugin/plugin.json` | Plugin identity and display metadata. Pins the catalog `name`. |
| `scripts/validate-plugin.py` | The only executable artifact. Static, fixture, and live validation. |

## Install

**Grok Build, from a local checkout.** Clone this repository and add it as a local plugin. Grok
Build discovers `agents/`, `skills/`, and `.mcp.json` by convention; the manifest is optional and
is shipped only to pin the catalog name and display metadata. The MCP server's OAuth flow triggers
on first use, so stage A, which makes no MCP call, does not initiate it.

**Grok Bot, through the team marketplace.** Grok Bot follows the team's Cursor plugin and MCP
policy. A Teams or Enterprise admin imports `doublespeed-main/doublespeed-plugin` as a team
marketplace, allowlists `https://doublespeed.ai/api/mcp` if team MCP policy requires an explicit
entry, and enables the plugin for the pilot user, who then completes OAuth.

A public repository URL on its own does **not** load the plugin in Grok Bot. The team marketplace
import and the admin MCP policy step are what do.

## Safety model

Three properties carry the safety of this plugin. All three are workflow properties of these
skills, not host-level authorization.

1. **Stage A makes zero Doublespeed MCP calls** and treats every retrieved page, search result, and
   social post as data, never instruction. Injected text is quoted as an observation on its source
   and otherwise ignored. `scripts/validate-plugin.py` enforces this mechanically: no live MCP tool
   name may appear anywhere in the stage A skill or its two references.
2. **No publishing tool call happens without an explicit human approval in the current
   conversation.** The canonical approval phrase is:

   ```
   APPROVE run=<run_id> token=<review_link_token> variants=<variant_id>[,<variant_id>]
   ```

   All five conditions A1 Source, A2 Directive, A3 Target link, A4 Target variants, and A5 Content
   match must hold. Only `ds-publisher` may call a publishing tool, only `queue_post`, only in
   state `APPROVED`, and at most once per approved variant.
3. **This is a workflow safety boundary, not an authorization boundary.** `.mcp.json` hands the
   host the MCP server's full tool list, so the operator, another skill, or any prompt outside this
   workflow can call `queue_post` directly, and nothing in this plugin can refuse that call. Hard
   enforcement needs a server-side change and is out of v1 scope.

The repository contains no credentials, tokens, or `.env` files, and reads none.

## Verification

```bash
python3 -m unittest discover -s tests -v      # pure unit and fixture tests, no network
python3 scripts/validate-plugin.py --offline  # full check set against the vendored capability snapshot
python3 scripts/validate-plugin.py --live     # same check set against https://doublespeed.ai/api/mcp-info
```

- The **unittest** suite proves the executable behaviour: rubric parsing and scoring, URL safety,
  deterministic audit ids, audit ingress, coverage, citations, injection resistance, agent
  permissions, and the CLI.
- **`--offline`** runs every check against the vendored 57-tool snapshot, so it is reproducible
  without a network.
- **`--live`** runs the identical check set against the live capability list, proving that the
  classified tools still match the endpoint. A newly added MCP tool fails this step until it is
  classified in `skills/doublespeed-content-team/references/approval-gate.md`.

No test, fixture, or CI step calls any Doublespeed MCP tool. The only network call in the whole
suite is the read-only `GET /api/mcp-info`.

## Host compatibility gate S0

S0 is the install-authentication compatibility gate, run once per host.

Install the plugin and, where the host UI allows it, decline or defer connector authentication.
Then invoke stage A as an unauthenticated user and record exactly one of three outcomes:

1. Stage A runs with no Doublespeed authentication. **Pass.**
2. The host prompts at installation, the prompt can be dismissed or deferred, and stage A still
   runs. **Pass**, recorded as host-driven install behaviour, not a stage A tool call.
3. The host requires connector authentication before any packaged skill can run. **Fail.**

Run S0 in Grok Build first, then in Grok Bot. The Grok Bot result is the launch gate, AC-A11. If
S0 fails in Grok Bot, the one-plugin lead-magnet objective has failed on that host: stop shipping
and reassess packaging with the reporter. No silent fallback, and no claim of success.

## Distribution

1. **Public repository.** `doublespeed-main/doublespeed-plugin`, MIT licensed, plugin at the
   repository root, so the catalog entry needs no `path`.
2. **Grok Build proof first.** Run the verification commands above plus the live smoke tests
   against a local install. Nothing goes further until they pass.
3. **Team marketplace pilot, then Grok Bot.** Import the repository into the Doublespeed team
   marketplace, allowlist the MCP endpoint if policy requires it, enable the plugin for the pilot
   user, complete OAuth, and re-run S0. Together with step 2 this is the functional gate.
4. **Pin a commit.** Get the verified SHA with:

   ```bash
   git ls-remote https://github.com/doublespeed-main/doublespeed-plugin.git HEAD
   ```

   It must be a full 40-character lowercase hex string. The catalog validator rejects tags,
   branches, and abbreviations, and Grok Build re-verifies `git rev-parse HEAD == sha` after
   cloning. Never force-push a pinned commit.
5. **Marketplace PR.** Open a PR against `xai-org/plugin-marketplace` adding one entry to
   `.grok-plugin/marketplace.json`:

   ```json
   {
     "name": "doublespeed",
     "description": "An AI content team for Doublespeed: research, strategy, copy, slideshow and video production, QA, and human-approved publishing.",
     "category": "productivity",
     "source": {
       "source": "url",
       "url": "https://github.com/doublespeed-main/doublespeed-plugin.git",
       "sha": "<full 40-char commit sha>"
     },
     "homepage": "https://doublespeed.ai",
     "keywords": ["doublespeed", "content team", "slideshow", "social content", "tiktok slideshow"],
     "domains": ["doublespeed.ai"]
   }
   ```

   If the catalog uses a different label for content and marketing tooling at PR time, match the
   closest existing label rather than introducing a new category. Before opening the PR, run
   `python3 scripts/generate-plugin-index.py` and `python3 scripts/validate-catalog.py` in a
   checkout of the marketplace repo and commit the regenerated `plugin-index.json`. CI runs the
   generator with `--check` and fails on a stale index. Code-owner review is required.
6. **Acceptance boundary.** Official xAI catalog acceptance is a later distribution milestone, not
   the functional gate. v1 is functionally accepted when the Grok Build install and the team
   marketplace pilot pass.

## Licence

MIT. See [LICENSE](LICENSE).
