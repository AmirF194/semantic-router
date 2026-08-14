# PL-0041 Managed Recipe Dashboard

## Goal

Evolve the maintained five-file recipe directory into the single active
Mixture-of-Models management surface for local `vllm-sr serve`: expose recipe
metadata and probes through the Dashboard, validate probes against the live
Router Eval API, launch exact probe requests in the existing Playground, and
discover or activate curated models from the installed `vllm-sr model`
catalog. Curated out-of-box scenarios live once under `config/built-in`, are
bound into the `vllm-sr` package, and are never separately published as Recipe
archives.

## Scope

- Add and validate required `metadata.yaml` files for maintained recipes.
- Change maintained-recipe conformance from four required files to five.
- Make the local serve stack expose fixed sibling recipe assets to Dashboard.
- Add a narrow, process-scoped active Recipe service and read APIs.
- Extend the existing Mixture-of-Models page with Overview and Probes views.
- Add server-side probe pagination, detail loading, and strict route validation.
- Add a typed Playground invocation for probe Run and Edit actions.
- Keep any deterministic five-file Recipe ZIP support as a backend-only
  compatibility seam for custom packages, not a curated distribution or
  primary Dashboard workflow.
- Make `config/built-in/latest` the single reviewed source for the complete
  catalog plus five-file Recipe bundles, and bind it into the `vllm-sr`
  package with source-to-package drift validation and CI receipts.
- Generate immutable `config/built-in/vX.Y` release snapshots explicitly from
  `latest` immediately before a tag; unreleased version directories do not
  exist in the repository.
- List installed catalog versions and their virtual models in the existing MoM
  page, with explicit activation controls and exactly one active Recipe per
  local stack.
- Present catalog and Mixture-of-Models metadata on the Unified Models surface
  instead of duplicating entrypoint and Recipe creation lists.
- Cache one immutable parsed exact-five source snapshot per Recipe service and
  invalidate all derived views together on any fixed-file change.
- Bind each live probe validation to pre/post Router source, generated-runtime,
  and active hashes without conflating provenance with assertion success.
- Preview and reconcile listener, managed-storage, and Router-auth topology as
  one journaled activation/deactivation transaction with explicit confirmation.
- Add focused backend, frontend, CLI, contract, and E2E coverage.

## Non-goals

- No Dashboard repository scanning, dependency resolution, or general package
  manager. Dashboard consumes the same installed catalog contract as
  `vllm-sr model`; it does not establish a second distribution channel.
- No multi-tenant package, credential, or provider isolation.
- No new provider-model or credential schema.
- No Kubernetes Recipe store or activation controller in this plan.
- No publisher-signature or transparency-log trust system; v1 provides digest
  integrity for custom transport without claiming publisher identity.
- No benchmark scorecard or Evaluation schema change in this plan.
- No generated response during probe validation.

## Exit Criteria

- Every maintained recipe has schema-valid metadata and passes exact five-file
  conformance.
- `vllm-sr serve --config <recipe>/config.yaml` exposes only that recipe's
  fixed sibling assets to Dashboard without scanning adjacent directories.
- `GET /api/recipe` reports the active recipe descriptor and source health.
- Probe list and detail endpoints handle large manifests with server paging and
  filtering.
- Validate calls the live Router `/api/v1/eval` contract and never simulates a
  successful result.
- Repeated reads reuse one immutable parsed snapshot keyed by a stable
  content-derived fingerprint of all five fixed files; invalid, oversized,
  symlinked, or changed sources invalidate every derived index and facet
  together while action digest preconditions remain authoritative.
- Validate records package and config hashes plus Router `/config/hash`
  observations before and after Eval. Only a stable active runtime bound to the
  package is `verified`; old, unavailable, mismatched, pending, or changing
  Router provenance is explicitly `unverified` and never changes `passed`.
- Run opens a clean Playground conversation and sends the materialized probe;
  Edit creates an editable draft without sending it.
- Any backend-only custom Recipe compatibility transport remains deterministic
  and never produces or publishes a curated archive from CI.
- Curated model discovery, YAML materialization, compatibility, and verification
  metadata ship in the `vllm-sr` wheel and release images from the complete
  five-file bundles under `config/built-in/latest`. `latest` tracks the reviewed
  catalog on `main`; a release-snapshot Make target creates immutable `vX.Y`
  assets immediately before publishing `vX.Y.Z`, and release CI fails unless
  channel, release, catalog version, and packaged bytes agree. GitHub Releases
  do not attach separate Recipe or catalog artifacts.
- Relevant catalog changes validate maintained Recipe conformance and exact
  `config/built-in` to `cli/model_assets` binding, then retain only a short-lived
  checksum and installed-CLI output receipt. The receipt is not a registry.
- Dashboard lists installed catalog versions and virtual models without asking
  the user for a ZIP URL. A legacy custom-import API, if retained, is not linked
  from the primary experience and never expands or persists credential values.
- Activation validates and applies the selected config plus active Recipe
  pointer as one rollback-capable operation; failed activation leaves the
  previous Router and Recipe active.
- Restore source verifies the original source runtime before clearing the
  active pointer, so ordinary configuration editing is never permanently
  disabled by a successful package activation.
- Package credential dependencies are names-only environment references.
  Literal credential values are rejected before packaging or installation,
  and runtime bindings require explicit operator authorization.
- Package YAML indirection and local-process MCP transports are rejected before
  packaging or installation. CLI restart, Dashboard activation, and Router
  config writers share one cross-process lock through runtime readiness.
- Existing entrypoint/recipe editing, provider model management, topology, and
  ordinary Playground behavior remain compatible.
- Activation and source restoration preview an exact plan digest, reconcile
  listeners plus the required managed storage set (including crashed-sidecar
  repair), use a scoped Dashboard-owned Router identity, and recover commit or
  rollback cleanup without losing the durable transaction marker.
- Applicable harness, CLI, recipe, Dashboard, integration, and local smoke
  gates pass.

## Task List

- [x] MRD-01: Create a clean worktree and branch from current `upstream/main`.
- [x] MRD-02: Add metadata schema, maintained metadata files, and five-file
      conformance.
- [x] MRD-03: Add active recipe path resolution and local container mounts.
- [x] MRD-04: Add Recipe service, descriptor API, and focused backend tests.
- [x] MRD-05: Add paginated probe list/detail and strict Eval validation APIs.
- [x] MRD-06: Refactor the existing MoM page and add Overview and Probes views.
- [x] MRD-07: Add Playground invocation support for probe Run and Edit.
- [x] MRD-08: Add behavior-visible integration/E2E coverage.
- [x] MRD-09: Run the complete validation ladder and fix all regressions.
- [x] MRD-10: Prepare signed-off reviewable commits.
- [x] MRD-11: Add deterministic custom Recipe ZIP transport, then migrate
      curated distribution to the versioned built-in model catalog and package
      validation receipt.
- [x] MRD-12: Add safe remote import and immutable local Recipe storage.
- [x] MRD-13: Add rollback-capable single-Recipe activation and runtime wiring.
- [x] MRD-14: Add custom-package inventory and lifecycle UI, then replace the
      primary import experience with installed built-in model discovery.
- [x] MRD-15: Add custom-transport and activation security, contract, and E2E
      coverage without exposing ZIP import in the primary Dashboard workflow.
- [ ] MRD-16: Run the complete gate and real AMD regression ladder on the
      remote AMD host, capture the catalog/package validation receipt, and
      return the ready experience endpoint.
- [x] MRD-17: Add the process-scoped immutable parsed Recipe snapshot cache,
      atomic source invalidation, and cache-boundary security/concurrency tests.
- [x] MRD-18: Add typed pre/post Router runtime provenance to Validate results,
      including package activation and platform-realization bindings.
- [x] MRD-19: Add confirmed runtime-topology activation plans, scoped Router
      service authentication, exact storage reconciliation, and durable
      commit/rollback recovery.
- [x] MRD-20: Consolidate the complete Chorus bundle under
      `config/built-in/latest`, remove duplicate and unreleased snapshot trees,
      and add the explicit pre-tag release-snapshot Make target.
- [x] MRD-21: Replace the Dashboard ZIP-import workspace with installed catalog
      version/model discovery and catalog-backed Mixture-of-Models metadata.
- [ ] MRD-22: Rebase the complete change on current `main`, squash it into one
      signed-off commit, rerun the full validation ladder, and deploy that exact
      commit to the AMD experience hosts.

## Next Action

Complete MRD-22, then hold the completion boundary at green CI plus the
recorded AMD experience run for the exact squashed commit.

## Validation

- Remote `agent-validate`, `workflow-ci-validate`, and canonical `agent-lint`
  passed, including formatting, structural, config-contract, AST, and privacy
  checks.
- Recipe conformance: 35 Python tests passed; all 7 maintained recipes,
  58 decisions, 11 entrypoints, and 275 probe variants validated.
- CLI: the full frozen suite passed 708 tests; the standard CLI gate passed
  36 tests with its 6 container-only cases skipped by that target.
- Semantic Router: all Rust bindings built; 53 Go packages and both Ginkgo
  suites passed with zero failures.
- Dashboard: ESLint, TypeScript, module checks, Go lint/vet/tests, and 109
  frontend test files with 412 tests passed.
- Managed Recipe Playwright coverage: 7 tests passed for Overview/probe
  browsing, remote import/activation, safe error handling, repair, Validate,
  Edit, and Run.
- The isolated runtime smoke passed Router, Envoy, and Dashboard readiness,
  authentication, paging/filtering, Run/Edit planning, and live route
  validation. Remote artifact import and generated chat remain in MRD-16.

## Operating Rules

- One Router/Dashboard process owns one active recipe directory.
- Installed objects are content-addressed and immutable; package installation
  does not silently activate or mutate the current Router.
- The complete curated bundle lives once under `config/built-in`; generated
  Python package resources and release snapshots are byte-bound derivatives.
- Catalog discovery is shared by `vllm-sr model` and Dashboard. The primary
  Dashboard workflow never imports a curated ZIP or becomes a second catalog.
- Untrusted package config cannot use YAML anchors, aliases, merge keys, or a
  local-process MCP transport to bypass credential and environment policy.
- Runtime recovery, materialization, activation, config mutation, container
  replacement, and readiness verification use the same stack-scoped lock.
- Production code does not import `tools/agent`; CI and production validation
  consume the same versioned contract from an owned schema seam.
- Keep handlers thin, keep `ChatComponent.tsx` orchestration narrow, and split
  the existing large MoM section before adding new views.
- Never put provider credentials or expanded secret values in metadata or
  Recipe API responses.
- Keep cached Recipe state source-only: never retain runtime-normalized config
  bytes, expanded environment values, or credentials in parsed snapshots.
- Treat validation assertions and runtime provenance as separate result axes;
  an assertion pass must not promote unavailable or changing hashes to verified.
- Strip browser credentials at every Router proxy boundary; only explicit
  Dashboard management routes may receive the scoped server-side credential.
- Preserve bare-config compatibility; only a managed Recipe receives metadata,
  probes, and Recipe identity.
- Keep this plan current until the branch is ready for review or the work is
  explicitly blocked.

## Related Docs

- [Agent harness](../README.md)
- [Module boundaries](../module-boundaries.md)
- [Testing strategy](../testing-strategy.md)
- [Feature complete checklist](../feature-complete-checklist.md)
- [Entrypoints and multi-recipe routing](pl-0038-entrypoints-recipes.md)
- [Maintained recipe conformance CI](pl-0040-recipe-conformance-ci.md)
