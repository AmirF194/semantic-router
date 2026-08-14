import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from cli.commands.runtime_support import (
    append_passthrough_env_vars,
    apply_runtime_mode_env_vars,
    config_env_references,
    configure_recipe_env_bindings,
    configure_runtime_override_env_vars,
    required_config_env_references,
    resolve_effective_config_path,
    sensitive_env_names,
    validate_config_recipe_env_bindings,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_runtime_support_import_does_not_load_optional_cli_dependencies():
    script = """
import sys

import cli.commands.runtime_support

assert "cli.commands.config" not in sys.modules
assert "cli.commands.model" not in sys.modules
assert "jinja2" not in sys.modules
assert "requests" not in sys.modules
"""

    subprocess.run([sys.executable, "-c", script], check=True)


def test_apply_runtime_mode_env_vars_sets_dashboard_readonly_when_requested():
    env_vars: dict[str, str] = {}

    apply_runtime_mode_env_vars(
        env_vars=env_vars,
        minimal=False,
        readonly=True,
        setup_mode=False,
        platform=None,
    )

    assert env_vars["DASHBOARD_READONLY"] == "true"


def test_apply_runtime_mode_env_vars_skips_dashboard_readonly_in_minimal_mode():
    env_vars: dict[str, str] = {}

    apply_runtime_mode_env_vars(
        env_vars=env_vars,
        minimal=True,
        readonly=True,
        setup_mode=False,
        platform=None,
    )

    assert env_vars["DISABLE_DASHBOARD"] == "true"
    assert "DASHBOARD_READONLY" not in env_vars


def test_apply_runtime_mode_env_vars_sets_router_log_level_when_requested():
    env_vars: dict[str, str] = {}

    apply_runtime_mode_env_vars(
        env_vars=env_vars,
        minimal=False,
        readonly=False,
        setup_mode=False,
        platform=None,
        log_level="DEBUG",
    )

    assert env_vars["SR_LOG_LEVEL"] == "debug"


def test_append_passthrough_env_vars_includes_router_logging_settings(monkeypatch):
    monkeypatch.setenv("SR_LOG_LEVEL", "debug")
    monkeypatch.setenv("SR_LOG_ENCODING", "console")

    env_vars: dict[str, str] = {}
    append_passthrough_env_vars(env_vars)

    assert env_vars["SR_LOG_LEVEL"] == "debug"
    assert env_vars["SR_LOG_ENCODING"] == "console"


def test_append_passthrough_env_vars_forwards_keys_named_by_trusted_source_config(
    monkeypatch, tmp_path
):
    """Operator-selected source config retains its established passthrough behavior."""
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "models": [{"name": "gemini", "api_key_env": "GEMINI_API_KEY"}]
                },
                "global": {
                    "stores": {"vector_store": {"password": "${VALKEY_PASSWORD}"}}
                },
            }
        )
    )
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test")
    monkeypatch.setenv("VALKEY_PASSWORD", "vp-test")
    monkeypatch.delenv("UNREFERENCED_API_KEY", raising=False)

    env_vars: dict[str, str] = {}
    append_passthrough_env_vars(env_vars, config)

    assert env_vars["GEMINI_API_KEY"] == "gk-test"
    assert env_vars["VALKEY_PASSWORD"] == "vp-test"
    assert "UNREFERENCED_API_KEY" not in env_vars


def test_config_env_references_reads_api_key_env_and_interpolations(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "providers": {"models": [{"api_key_env": "MISTRAL_API_KEY"}]},
                "embedding_models": {"endpoint": {"api_key_env": "EMBEDDING_API_KEY"}},
                "note": "uses ${REDIS_AUTH_TOKEN} at runtime",
                "bare": "postgres://$DATABASE_PASSWORD@db",
                "fallback": "${OPTIONAL_TOKEN:-development}",
            }
        )
    )

    assert config_env_references(config) == {
        "MISTRAL_API_KEY",
        "EMBEDDING_API_KEY",
        "REDIS_AUTH_TOKEN",
        "OPTIONAL_TOKEN",
    }
    assert config_env_references(None) == set()
    assert config_env_references(tmp_path / "missing.yaml") == set()


def test_required_config_env_references_includes_every_router_consulted_name(
    tmp_path: Path,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "provider": {"api_key_env": "PROVIDER_API_KEY"},
                "database": "postgres://$DATABASE_PASSWORD@db",
                "cache": "${CACHE_PASSWORD}",
                "optional": "${OPTIONAL_TOKEN:-development}",
                "unset_only": "${UNSET_ONLY_TOKEN-development}",
                "lowercase": "$lowercase_token",
                "escaped": "$$NOT_CONSULTED",
            }
        )
    )

    assert required_config_env_references(config) == {
        "PROVIDER_API_KEY",
        "DATABASE_PASSWORD",
        "CACHE_PASSWORD",
        "OPTIONAL_TOKEN",
        "UNSET_ONLY_TOKEN",
        "lowercase_token",
    }


def test_required_package_env_references_fail_closed_on_denied_host_names(
    tmp_path: Path,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "provider": {"api_key_env": "HOME"},
                "path": "${PATH}",
            }
        )
    )

    assert required_config_env_references(config) == {"HOME", "PATH"}
    with pytest.raises(ValueError, match="invalid Recipe environment binding"):
        validate_config_recipe_env_bindings(config, [])


@pytest.mark.parametrize(
    "reference",
    [
        "${lowercase_token}",
        "${lowercase-token}",
        "${PATH:-/usr/bin}",
        "${VLLM_SR_RECIPE_STORE_DIR}",
        "${VLLM_SR_MANAGED_STORAGE_BACKENDS-default}",
        "$VLLM_SR_STACK_NAME",
        "${VLLM_SR_ACTIVE_RECIPE_DIR}",
    ],
)
def test_required_package_env_references_reject_invalid_or_reserved_names(
    tmp_path: Path, reference: str
):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"value": reference}))

    with pytest.raises(ValueError, match="invalid Recipe environment binding"):
        validate_config_recipe_env_bindings(config, [])


def test_config_env_references_excludes_process_identity_vars(tmp_path):
    """A config referencing ${PATH}/${HOME} must not pull host process state into the container."""
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "note": "installed under ${HOME}/.cache, resolved via ${PATH}",
                "providers": {"models": [{"api_key_env": "MISTRAL_API_KEY"}]},
            }
        )
    )

    refs = config_env_references(config)
    assert refs == {"MISTRAL_API_KEY"}


def test_config_env_references_excludes_cli_controlled_override_vars(tmp_path):
    """A config that happens to mention a CLI override var must not preempt the CLI's own default."""
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({"note": "see ${DISABLE_DASHBOARD} and ${DASHBOARD_PLATFORM}"})
    )

    assert config_env_references(config) == set()


def test_append_passthrough_env_vars_does_not_forward_process_identity_vars(
    monkeypatch, tmp_path
):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"note": "runs from ${PATH}"}))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    env_vars: dict[str, str] = {}
    append_passthrough_env_vars(env_vars, config)

    assert "PATH" not in env_vars


def test_sensitive_env_names_covers_config_named_credentials(tmp_path):
    """A key the config names must be treated as a secret, not inlined into a manifest."""
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({"providers": {"models": [{"api_key_env": "GEMINI_API_KEY"}]}})
    )

    assert "GEMINI_API_KEY" in sensitive_env_names(config)
    assert "HF_TOKEN" in sensitive_env_names(config)
    assert "HF_ENDPOINT" not in sensitive_env_names(config)
    assert "GEMINI_API_KEY" not in sensitive_env_names(None)


def test_configure_recipe_env_bindings_requires_explicit_names_and_masks_values(
    monkeypatch, caplog
):
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test")
    monkeypatch.setenv("VALKEY_PASSWORD", "vp-test")
    env_vars: dict[str, str] = {}

    names = configure_recipe_env_bindings(
        env_vars, ["VALKEY_PASSWORD", "GEMINI_API_KEY", "GEMINI_API_KEY"]
    )

    assert names == ("GEMINI_API_KEY", "VALKEY_PASSWORD")
    assert env_vars["VLLM_SR_RECIPE_ENV_ALLOWLIST"] == (
        "GEMINI_API_KEY,VALKEY_PASSWORD"
    )
    assert env_vars["GEMINI_API_KEY"] == "gk-test"
    assert env_vars["VALKEY_PASSWORD"] == "vp-test"
    assert "gk-test" not in caplog.text
    assert "vp-test" not in caplog.text


def test_configure_recipe_env_bindings_rejects_values_and_missing_host_env(
    monkeypatch,
):
    monkeypatch.delenv("MISSING_API_KEY", raising=False)
    with pytest.raises(ValueError, match="without NAME=value"):
        configure_recipe_env_bindings({}, ["API_KEY=secret"])
    with pytest.raises(ValueError, match="no non-empty host value"):
        configure_recipe_env_bindings({}, ["MISSING_API_KEY"])


def test_configure_recipe_env_bindings_accepts_names_only_env_allowlist(monkeypatch):
    monkeypatch.setenv("VLLM_SR_RECIPE_ENV_ALLOWLIST", "SECOND_API_KEY,FIRST_API_KEY")
    monkeypatch.setenv("FIRST_API_KEY", "first")
    monkeypatch.setenv("SECOND_API_KEY", "second")
    env_vars: dict[str, str] = {}

    names = configure_recipe_env_bindings(env_vars, [])

    assert names == ("FIRST_API_KEY", "SECOND_API_KEY")
    assert env_vars["VLLM_SR_RECIPE_ENV_ALLOWLIST"] == ("FIRST_API_KEY,SECOND_API_KEY")


def test_validate_config_recipe_env_bindings_fails_closed(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "models": [{"name": "gemini", "api_key_env": "GEMINI_API_KEY"}]
                },
                "database": "postgres://$DATABASE_PASSWORD@db",
                "optional": "${OPTIONAL_TOKEN:-development}",
            }
        )
    )

    with pytest.raises(ValueError, match="--recipe-env GEMINI_API_KEY"):
        validate_config_recipe_env_bindings(config, ["DATABASE_PASSWORD"])

    with pytest.raises(ValueError, match="--recipe-env OPTIONAL_TOKEN"):
        validate_config_recipe_env_bindings(
            config, ["DATABASE_PASSWORD", "GEMINI_API_KEY"]
        )

    validate_config_recipe_env_bindings(
        config, ["DATABASE_PASSWORD", "GEMINI_API_KEY", "OPTIONAL_TOKEN"]
    )


@pytest.mark.parametrize(
    "reference", ["${OPTIONAL_TOKEN:-development}", "${OPTIONAL_TOKEN-development}"]
)
def test_package_restart_fallback_reference_requires_explicit_allowlist(
    tmp_path: Path, reference: str
):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"optional": reference}))

    with pytest.raises(ValueError, match="--recipe-env OPTIONAL_TOKEN"):
        validate_config_recipe_env_bindings(config, [])

    validate_config_recipe_env_bindings(config, ["OPTIONAL_TOKEN"])


def test_resolve_effective_config_path_enables_amd_gpu_by_default(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("VLLM_SR_AMD_FORCE_GPU", raising=False)
    monkeypatch.delenv("VLLM_SR_AMD_PRESERVE_CPU", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "v0.3",
                "global": {
                    "model_catalog": {
                        "embeddings": {
                            "semantic": {
                                "use_cpu": True,
                                "embedding_config": {"model_type": "mmbert"},
                            }
                        },
                        "modules": {
                            "prompt_guard": {"use_cpu": True},
                            "classifier": {
                                "domain": {"use_cpu": True},
                            },
                        },
                    }
                },
            },
            sort_keys=False,
        )
    )

    effective_path = resolve_effective_config_path(
        config_path=config_path,
        algorithm=None,
        setup_mode=False,
        platform="amd",
    )

    effective = yaml.safe_load(effective_path.read_text())
    assert (
        effective["global"]["model_catalog"]["embeddings"]["semantic"]["use_cpu"]
        is False
    )
    assert (
        effective["global"]["model_catalog"]["modules"]["prompt_guard"]["use_cpu"]
        is False
    )
    assert (
        effective["global"]["model_catalog"]["modules"]["classifier"]["domain"][
            "use_cpu"
        ]
        is False
    )


def test_resolve_effective_config_path_enables_nvidia_gpu_by_default(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("VLLM_SR_NVIDIA_FORCE_GPU", raising=False)
    monkeypatch.delenv("VLLM_SR_NVIDIA_PRESERVE_CPU", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "v0.3",
                "global": {
                    "model_catalog": {
                        "embeddings": {
                            "semantic": {
                                "use_cpu": True,
                                "embedding_config": {"model_type": "mmbert"},
                            }
                        },
                        "modules": {
                            "prompt_guard": {"use_cpu": True},
                            "classifier": {
                                "domain": {"use_cpu": True},
                            },
                        },
                    }
                },
            },
            sort_keys=False,
        )
    )

    effective_path = resolve_effective_config_path(
        config_path=config_path,
        algorithm=None,
        setup_mode=False,
        platform="nvidia",
    )

    effective = yaml.safe_load(effective_path.read_text())
    assert (
        effective["global"]["model_catalog"]["embeddings"]["semantic"]["use_cpu"]
        is False
    )
    assert (
        effective["global"]["model_catalog"]["modules"]["prompt_guard"]["use_cpu"]
        is False
    )
    assert (
        effective["global"]["model_catalog"]["modules"]["classifier"]["domain"][
            "use_cpu"
        ]
        is False
    )


def test_resolve_effective_config_path_preserves_nvidia_use_cpu_when_requested(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("VLLM_SR_NVIDIA_PRESERVE_CPU", "1")
    monkeypatch.delenv("VLLM_SR_NVIDIA_FORCE_GPU", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "v0.3",
                "global": {
                    "model_catalog": {
                        "embeddings": {
                            "semantic": {
                                "use_cpu": True,
                                "embedding_config": {"model_type": "mmbert"},
                            }
                        },
                        "modules": {
                            "prompt_guard": {"use_cpu": True},
                        },
                    }
                },
            },
            sort_keys=False,
        )
    )

    effective_path = resolve_effective_config_path(
        config_path=config_path,
        algorithm=None,
        setup_mode=False,
        platform="nvidia",
    )

    effective = yaml.safe_load(effective_path.read_text())
    assert (
        effective["global"]["model_catalog"]["embeddings"]["semantic"]["use_cpu"]
        is True
    )
    assert (
        effective["global"]["model_catalog"]["modules"]["prompt_guard"]["use_cpu"]
        is True
    )


def test_resolve_effective_config_path_preserves_amd_use_cpu_when_requested(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("VLLM_SR_AMD_PRESERVE_CPU", "1")
    monkeypatch.delenv("VLLM_SR_AMD_FORCE_GPU", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "v0.3",
                "global": {
                    "model_catalog": {
                        "embeddings": {
                            "semantic": {
                                "use_cpu": True,
                                "embedding_config": {"model_type": "mmbert"},
                            }
                        },
                        "modules": {
                            "prompt_guard": {"use_cpu": True},
                            "classifier": {
                                "domain": {"use_cpu": True},
                            },
                        },
                    }
                },
            },
            sort_keys=False,
        )
    )

    effective_path = resolve_effective_config_path(
        config_path=config_path,
        algorithm=None,
        setup_mode=False,
        platform="amd",
    )

    effective = yaml.safe_load(effective_path.read_text())
    assert (
        effective["global"]["model_catalog"]["embeddings"]["semantic"]["use_cpu"]
        is True
    )
    assert (
        effective["global"]["model_catalog"]["modules"]["prompt_guard"]["use_cpu"]
        is True
    )
    assert (
        effective["global"]["model_catalog"]["modules"]["classifier"]["domain"][
            "use_cpu"
        ]
        is True
    )


def test_resolve_effective_config_path_combines_algorithm_and_platform_overrides(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("VLLM_SR_AMD_FORCE_GPU", raising=False)
    monkeypatch.delenv("VLLM_SR_AMD_PRESERVE_CPU", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "v0.3",
                "routing": {"decisions": [{"name": "default"}]},
                "global": {
                    "model_catalog": {
                        "embeddings": {
                            "semantic": {
                                "use_cpu": True,
                                "embedding_config": {"model_type": "mmbert"},
                            }
                        }
                    }
                },
            },
            sort_keys=False,
        )
    )

    effective_path = resolve_effective_config_path(
        config_path=config_path,
        algorithm="multi_factor",
        setup_mode=False,
        platform="amd",
    )

    assert effective_path == tmp_path / ".vllm-sr" / "runtime-config.yaml"
    effective = yaml.safe_load(effective_path.read_text())
    assert effective["routing"]["decisions"][0]["algorithm"]["type"] == "multi_factor"
    assert (
        effective["global"]["model_catalog"]["embeddings"]["semantic"]["use_cpu"]
        is False
    )


def test_resolve_effective_config_path_injects_missing_amd_gpu_defaults_by_default(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("VLLM_SR_AMD_FORCE_GPU", raising=False)
    monkeypatch.delenv("VLLM_SR_AMD_PRESERVE_CPU", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "v0.3",
                "listeners": [
                    {
                        "name": "http",
                        "address": "0.0.0.0",
                        "port": 8899,
                    }
                ],
                "providers": {
                    "defaults": {"default_model": "test-model"},
                    "models": [
                        {
                            "name": "test-model",
                            "provider_model_id": "test-model",
                            "backend_refs": [{"endpoint": "127.0.0.1:8000"}],
                        }
                    ],
                },
                "routing": {
                    "modelCards": [{"name": "test-model"}],
                    "decisions": [
                        {
                            "name": "default-route",
                            "priority": 1,
                            "rules": {"operator": "AND", "conditions": []},
                            "modelRefs": [{"model": "test-model"}],
                        }
                    ],
                },
                "global": {},
            },
            sort_keys=False,
        )
    )

    effective_path = resolve_effective_config_path(
        config_path=config_path,
        algorithm=None,
        setup_mode=False,
        platform="amd",
    )

    effective = yaml.safe_load(effective_path.read_text())
    model_catalog = effective["global"]["model_catalog"]
    assert model_catalog["embeddings"]["semantic"]["use_cpu"] is False
    assert model_catalog["modules"]["prompt_guard"]["use_cpu"] is False
    assert model_catalog["modules"]["classifier"]["domain"]["use_cpu"] is False
    assert model_catalog["modules"]["classifier"]["pii"]["use_cpu"] is False
    assert model_catalog["modules"]["feedback_detector"]["use_cpu"] is False
    assert (
        model_catalog["modules"]["modality_detector"]["classifier"]["use_cpu"] is False
    )
    assert "bert" not in model_catalog["embeddings"]


def test_resolve_effective_config_path_keeps_bert_deprecated_with_amd_gpu_default(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("VLLM_SR_AMD_FORCE_GPU", raising=False)
    monkeypatch.delenv("VLLM_SR_AMD_PRESERVE_CPU", raising=False)
    config_path = tmp_path / "config.yaml"
    balance_recipe = REPO_ROOT / "config" / "recipes" / "balance" / "config.yaml"
    config_path.write_text(balance_recipe.read_text(encoding="utf-8"))

    effective_path = resolve_effective_config_path(
        config_path=config_path,
        algorithm=None,
        setup_mode=False,
        platform="amd",
    )

    effective = yaml.safe_load(effective_path.read_text())
    model_catalog = effective.get("global", {}).get("model_catalog", {})
    embeddings = model_catalog.get("embeddings", {})
    assert "bert" not in embeddings
    assert embeddings["semantic"]["use_cpu"] is False


def test_configure_runtime_override_env_vars_sets_internal_runtime_path(tmp_path: Path):
    env_vars: dict[str, str] = {}
    source_config = tmp_path / "config.yaml"
    source_config.write_text("version: v0.3\n")
    effective_config = tmp_path / ".vllm-sr" / "runtime-config.yaml"
    effective_config.parent.mkdir(parents=True, exist_ok=True)
    effective_config.write_text("version: v0.3\n")

    configure_runtime_override_env_vars(env_vars, source_config, effective_config)

    assert env_vars["VLLM_SR_SOURCE_CONFIG_PATH"] == "/app/.vllm-sr/runtime-config.yaml"
    assert (
        env_vars["VLLM_SR_RUNTIME_CONFIG_PATH"] == "/app/.vllm-sr/runtime-config.yaml"
    )
    assert "VLLM_SR_STATE_ROOT_DIR" not in env_vars


def test_resolve_effective_config_path_uses_state_root_for_runtime_override(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("VLLM_SR_STACK_NAME", raising=False)
    state_root = tmp_path / "state"
    monkeypatch.setenv("VLLM_SR_STATE_ROOT_DIR", str(state_root))

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "v0.3",
                "listeners": [
                    {
                        "name": "http-8899",
                        "address": "0.0.0.0",
                        "port": 8899,
                    }
                ],
            },
            sort_keys=False,
        )
    )

    effective_path = resolve_effective_config_path(
        config_path=config_path,
        algorithm=None,
        setup_mode=False,
        platform=None,
    )

    assert effective_path == state_root / ".vllm-sr" / "runtime-config.yaml"
    assert effective_path.exists()
    assert not (config_dir / ".vllm-sr" / "runtime-config.yaml").exists()

    env_vars: dict[str, str] = {}
    configure_runtime_override_env_vars(env_vars, config_path, effective_path)
    assert (
        env_vars["VLLM_SR_RUNTIME_CONFIG_PATH"] == "/app/.vllm-sr/runtime-config.yaml"
    )
