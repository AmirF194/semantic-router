# Maintained routing recipes

`config/recipes/` contains complete, executable use-case deliveries. Directory
names describe the user outcome; implementation names such as Router Flow,
SAARS, or MMLU belong inside the recipe documentation rather than in the
catalog taxonomy.

## Delivery contract

Every child directory has the same five files:

- `metadata.yaml` — versioned identity, authorship, license, tags, and links.
- `config.yaml` — canonical v0.3 runtime configuration.
- `recipe.dsl` — reviewable routing policy that compiles back into the same
  dynamic routing surface.
- `probes.yaml` — backend-independent `/api/v1/eval` correctness probes.
- `README.md` — intended use, routing policy, tradeoffs, and validation steps.

The repository contract tests reject incomplete directories, invalid YAML or
DSL, YAML/DSL drift, missing decision reachability, stale aliases, and loss of
YAML-only decision adaptation policy during DSL merge.

Managed recipe metadata uses `schema_version: vllm-sr/recipe-metadata/v1` and
is validated against `config/schemas/recipe-metadata-v1.schema.json`. Its `id`
must match the recipe directory. Probe manifests use `schema_version: v1` and
are validated against `tools/agent/schemas/recipe-probes-v1.schema.json`. The
conformance inventory discovers every immediate child directory automatically
and includes its metadata identity. Adding a recipe therefore adds it to static
and live CI without a workflow or Go allowlist change.

See [CONFORMANCE.md](CONFORMANCE.md) for the short contributor checklist,
coverage tiers, tag conventions, and local commands.

## Built-in models and custom Recipe transport

`config/recipes/` contains standalone maintained examples and user-oriented
Recipe sources. Curated out-of-box models live only under
[`config/built-in/latest/`](../built-in/README.md), using the same five-file
contract plus version/catalog metadata, and are copied into the `vllm-sr` wheel
and release images. Curated models therefore require no GitHub download or
Dashboard HTTPS import:

```bash
vllm-sr model list
vllm-sr model show vllm-sr/chorus-v1
vllm-sr model fork vllm-sr/chorus-v1 chorus-v1.yaml
vllm-sr model validate chorus-v1.yaml
```

The catalog enables `vllm-sr/chorus-v1` by default. Fork can select more than
one compatible entrypoint from the same bundled config and choose which selected
model is the default:

```bash
vllm-sr model fork vllm-sr/chorus-v1 chorus-custom.yaml \
  --enable vllm-sr/chorus-v1-vault \
  --default vllm-sr/chorus-v1
```

`latest/` tracks the reviewed catalog on `main`. Immutable `vX.Y/` directories
are generated only while preparing that release:

```bash
make built-in-model-snapshot RELEASE_VERSION=X.Y.Z
```

The target refuses to overwrite an existing snapshot. A tag `vX.Y.Z` cannot
publish unless
`config/built-in/vX.Y/catalog.yaml` exists with `channel: release`,
`release: vX.Y`, and `catalog_version: vX.Y`. The wheel checks the catalog and
every exact-five bundle resource discovered in that snapshot rather than a
hard-coded version list. Use `--catalog-version vX.Y` to inspect or fork a
published snapshot, `model list --all-versions` to see installed history, and
`model list --all` to
include incompatible entries with their reason. A future
`vllm-sr/chorus-v2` coexists as a new policy generation; compatibility is
declared by catalog metadata rather than inferred from the name.

Each model declares traits, required backend roles, minimum pool sizes, and
recommended candidates. Recommendations are not a vendor lock: users can fork
and bind any suitable models. The `verified` status applies only to the exact
maintainer-bound asset digest; a modified or differently bound fork is valid
canonical YAML but is reported as `custom/unverified`.

Built-in catalogs and Recipe YAML are not attached to GitHub Releases as ZIP
assets. The **Built-in Model Catalog** workflow validates authoring conformance,
source-to-wheel drift, and installed CLI discovery. Its short-lived artifact is
a checksum and command-output receipt, not a package registry.

`vllm-sr recipe pack` remains available only as a compatibility transport for
a custom five-file Recipe directory. Built-in model discovery and the Dashboard
catalog never import this archive; they list the packaged `latest` and released
`vX.Y` catalogs directly:

```bash
vllm-sr recipe pack path/to/custom-recipe
```

The deterministic ZIP contains the same `metadata.yaml`, `config.yaml`,
`probes.yaml`, `recipe.dsl`, and `README.md`; it is not a built-in catalog
format. Teams may host a custom archive at a trusted HTTPS location for the
custom transport API, or extract it and serve its `config.yaml` directly. The
command emits the archive path, SHA-256, and content-addressed `recipe_digest`.
It rejects missing files, symlinks, unrelated entries, literal credentials,
embedded URL credentials, sensitive query parameters, credential-carrying
headers, YAML indirection/explicit tags, and local-process MCP transports.

Treat every shared custom archive as public source. Use `api_key_env` or a pure
environment reference such as `${PROVIDER_API_KEY}`; the packer never expands
environment variables or exports runtime state, and its errors never print a
rejected secret value.

Bind each required name explicitly when the local stack starts:

```bash
export PROVIDER_API_KEY=...  # keep the value outside the Recipe
vllm-sr serve --config path/to/recipe/config.yaml \
  --recipe-env PROVIDER_API_KEY
```

The value is inherited by the Router and Dashboard containers without being
written into the archive, API responses, runtime config, logs, or container
command arguments.

Single-profile recipes expose their `routing` block through the default
`global.router.auto_model_names` entrypoint. Multi-profile configurations can
disable that default and expose named `entrypoints` instead. Conformance counts
and exercises both forms, so a default auto alias is not reported as zero
entrypoints.

## Use an authoring or custom recipe in Dashboard

Serve the recipe's canonical config through the existing local stack:

```bash
vllm-sr serve --config config/recipes/<use-case>/config.yaml
```

The command remains compatible with bare configs and managed Recipe paths, but
the supplied `--config` is now a read-only source. Each local stack runs from a
runtime-owned `.vllm-sr/runtime-config[.<stack>].yaml`. Dashboard edits and
package activations change that active file and survive a restart. When the
active file has diverged, a later source edit is not silently copied over it;
`serve` preserves the active version and logs a warning.

The Dashboard mounts only that directory's five fixed files and treats it as
the single active Recipe; it does not scan sibling recipes or catalog paths. In
the existing **Mixture-of-Models** page, **Overview** shows identity, source
health, inventory, and README content, while **Probes** provides server-paged
filtering and lazy detail. **Run** starts a clean Playground conversation,
**Edit** prepares the terminal user turn without sending it, and **Validate**
calls the live Router Eval API without generating an answer. A bare
`config.yaml` remains supported and is reported as unmanaged.

## Catalog

| Use case | Purpose |
| --- | --- |
| [`accuracy`](accuracy/README.md) | Spend bounded multi-model orchestration only where it has an expected quality benefit; keep long context single-model. |
| [`agent`](agent/README.md) | Route agent, coding, specialist, privacy, and security work across local and frontier lanes. |
| [`balance`](balance/README.md) | General-purpose quality, latency, and cost balance for a single default routing profile. |
| [`feedback`](feedback/README.md) | Recover from corrections, repeated dissatisfaction, failed code, and verification requests. |
| [`knowledge`](knowledge/README.md) | Use KB evidence to decide whether a knowledge-domain question merits frontier escalation. |
| [`multi-objective`](multi-objective/README.md) | Expose isolated balanced, speed, cost, accuracy, and privacy recipes as request-facing entrypoints. |
| [`privacy`](privacy/README.md) | Keep sensitive, suspicious, and private-context traffic on policy-compatible models. |

`bounded-candidate-iteration.dsl` and other syntax-only demonstrations are not
deployable recipes. Their behavior is covered by DSL unit tests instead of
being mixed into this catalog.

The curated model index is separate:
[Chorus V1](../built-in/latest/chorus-v1/README.md) is canonical only under
`config/built-in/latest/` and uses the same exact-five Recipe contract plus
catalog/version bindings.

## Maintained acceptance baseline

The blocking August 2026 standalone-recipe baseline covers 275 base probes,
58 decisions, and 11 recipe-entrypoint bindings across seven recipes. Decision,
entrypoint, fallback, algorithm, and plugin coverage is complete; signal and
projection assertions use checked-in per-recipe ratchets that cannot decrease:

- Accuracy: 13 probes, 4 decisions.
- Agent: 27 probes, 11 decisions.
- Balance: 57 probes, 14 decisions.
- Feedback: 23 probes, 7 decisions.
- Knowledge: 15 probes, 2 decisions.
- Privacy: 20 probes, 4 decisions.
- Multi-objective: 120 probes, 16 decisions, 5 named entrypoints.

The live CPU gate requires router readiness and exact `/api/v1/eval?trace=true`
results. Framing expansion, upstream generation, GPU parity, and latency SLOs
are T4 reporting concerns rather than PR acceptance criteria.

## Validate a recipe

From the repository root:

```bash
make recipe-conformance-static

vllm-sr validate --config config/recipes/<use-case>/config.yaml

(cd src/semantic-router && \
  go run ./cmd/dsl validate ../../config/recipes/<use-case>/recipe.dsl)

(cd src/semantic-router && \
  go run ./cmd/dsl compile \
    --base ../../config/recipes/<use-case>/config.yaml \
    -o /tmp/<use-case>.yaml \
    ../../config/recipes/<use-case>/recipe.dsl)
```

Run the backend-independent calibration suite against a live router:

```bash
make recipe-conformance-eval \
  RECIPE_CONFORMANCE_RECIPE=<use-case> \
  RECIPE_CONFORMANCE_ROUTER_URL=http://127.0.0.1:8080

# Build the local CPU image and evaluate every maintained recipe.
make recipe-conformance-live-cpu-all
```

Pull requests that touch recipes or their router semantics run the base probes
through the reusable Recipe Conformance CI domain. Framing/whitespace
expansion, real generation, GPU execution, and timing baselines remain
scheduled or manual workloads rather than PR blockers.

Each CI run publishes the coverage matrix in the GitHub Actions job summary and
uploads a `recipe-conformance-report` artifact for 30 days. The consolidated
artifact contains the inventory, per-recipe Eval reports, summaries, and
failure logs, including partial results when a live shard fails. Its inventory
lists configured, asserted, and uncovered signals, projections, algorithms,
and plugins; live summaries include the T3 robustness pass-rate receipts.

The multi-objective profile additionally checks requested model, selected
recipe, decision, algorithm, plugins, signal evidence, multilingual variants,
multi-turn/tool shapes, and long-context boundaries. Every maintained manifest
also declares bounded concurrency, so the same report records end-to-end p50,
p95, and p99 Eval latency, throughput, and transport errors alongside routing
accuracy.
