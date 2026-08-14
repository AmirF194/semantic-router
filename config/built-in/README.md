# Built-in virtual models

This directory is the distribution source for virtual models installed with
`vllm-sr`. The user-facing object is a model; `entrypoints` and `recipes` remain
the implementation-facing policy objects inside the referenced canonical YAML.

- `latest/` tracks the reviewed catalog on `main`. Each declared asset is a
  normal exact-five Recipe directory containing `metadata.yaml`, `config.yaml`,
  `recipe.dsl`, `probes.yaml`, and `README.md`; there is no duplicate authoring
  copy under `config/recipes/`. Its catalog identity is `latest` / `unreleased`.
- `vX.Y/` directories are immutable release snapshots. They do not exist before
  that release is prepared and are never rewritten after the matching release.
- `catalog.yaml` contains discovery, compatibility, role, trait, recommendation,
  and verification metadata. It is not merged into Router runtime YAML.
- A referenced `config.yaml` can contain multiple isolated recipes. The default
  catalog enables only `vllm-sr/chorus-v1`; `vllm-sr model fork --enable ...`
  can select any compatible subset.

The generated package copy under `src/vllm-sr/cli/model_assets/` is verified by
CI and must never be hand-edited. `tools/release/sync_model_catalog.py` updates
it from this directory or rejects drift with `--check`.

Immediately before creating a stable tag, freeze `latest` into the tag's minor
version and generate its package binding:

```bash
make built-in-model-snapshot RELEASE_VERSION=X.Y.Z
```

The target refuses to overwrite an existing snapshot, rewrites only the
release channel/path bindings, recomputes the complete five-file bundle digest,
syncs the installable resources, and verifies source/package parity. Commit the
generated `config/built-in/vX.Y/` and `cli/model_assets/vX.Y/` trees with the
release commit. Release CI derives `vX.Y` from the tag and fails if that exact
snapshot is missing or has drifted from `latest`. On later changes, catalog CI
uses reachable stable tags as the authority and rejects any file, inventory, or
byte change to a snapshot that has already been published; a new unpublished
`vX.Y/` remains allowed.

## Family evolution

The family major is part of the public model ID. A future
`vllm-sr/chorus-v2` is a new catalog entry and can coexist with Chorus V1. The
catalog declares CLI, Router config-schema, and feature compatibility explicitly;
the CLI never infers compatibility from a `chorus-vN` string. By default,
`model list` shows the `latest` channel and only compatible entries. Use a
release snapshot for reproducibility, `--all-versions` for history, and `--all`
to include incompatible entries with their reason.

Recommendations describe model traits and candidate pools, not mandatory vendor
IDs. Maintainer verification is valid only while the catalog asset digest and
generated binding match. A user may bind or edit any model after `model fork`;
the result remains valid canonical YAML but is reported as custom/unverified.
