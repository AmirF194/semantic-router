"""CLI contracts for built-in catalog discovery and explicit config inspection.

The command must:
- Be discoverable from the top-level CLI help.
- Print provider models + model cards for a valid config (exit 0).
- Mark the default model so users can spot the routing target at a glance.
- Never leak `api_key` / `api_key_env` values from backend refs - those are
  secrets and the whole point of this command is safe inspection.
- Fail with a clear error message when the config file is missing.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from click.testing import CliRunner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

main = importlib.import_module("cli.main").main
README_PATH = PROJECT_ROOT / "README.md"

DEFAULT_CATALOG_MODEL = "vllm-sr/chorus-v1"
LITE_CATALOG_MODEL = "vllm-sr/chorus-v1-lite"
FLASH_CATALOG_MODEL = "vllm-sr/chorus-v1-flash"


_VALID_CONFIG = {
    "version": "v0.3",
    "listeners": [{"name": "http-8899", "address": "0.0.0.0", "port": 8899}],
    "providers": {
        "defaults": {"default_model": "gpt-4o-mini"},
        "models": [
            {
                "name": "gpt-4o-mini",
                "provider_model_id": "gpt-4o-mini",
                "backend_refs": [
                    {
                        "name": "openai-primary",
                        "provider": "openai",
                        "base_url": "https://api.openai.com/v1",
                        "protocol": "http",
                        "weight": 100,
                        "api_key": "SECRET_API_KEY_DO_NOT_LEAK",
                    }
                ],
            },
            {
                "name": "llama-3-8b",
                "backend_refs": [
                    {
                        "name": "vllm-local",
                        "provider": "openai",
                        "base_url": "http://localhost:8000/v1",
                        "protocol": "http",
                        "weight": 50,
                        "api_key_env": "SECRET_ENV_VAR_NAME_DO_NOT_LEAK",
                    }
                ],
            },
        ],
    },
    "routing": {
        "modelCards": [
            {
                "name": "gpt-4o-mini",
                "modality": "text",
                "capabilities": ["chat", "tools"],
                "param_size": "8B",
                "context_window_size": 128000,
            },
            {"name": "llama-3-8b", "modality": "text"},
        ],
        "decisions": [
            {
                "name": "default",
                "description": "fallback",
                "priority": 0,
                "rules": {"operator": "AND", "conditions": []},
                "modelRefs": [{"model": "gpt-4o-mini"}],
            }
        ],
    },
}


def _write_config(tmp_path: Path, data: dict | None = None) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(data or _VALID_CONFIG, sort_keys=False))
    return config_path


def _run_cli_subprocess(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_model_list_registered_on_top_level_help():
    runner = CliRunner()

    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "model" in result.output


def test_model_list_help_describes_subcommand():
    runner = CliRunner()

    result = runner.invoke(main, ["model", "--help"])

    assert result.exit_code == 0
    assert "list" in result.output


def test_bare_model_list_prints_latest_builtin_catalog(caplog):
    runner = CliRunner()

    with caplog.at_level("INFO"):
        result = runner.invoke(main, ["model", "list"])

    assert result.exit_code == 0
    combined = "\n".join(record.message for record in caplog.records)
    assert "vLLM Semantic Router - Built-in Models" in combined
    assert DEFAULT_CATALOG_MODEL in combined
    assert LITE_CATALOG_MODEL in combined
    assert "verified" in combined
    assert "Provider models" not in combined


def test_model_list_json_reports_latest_catalog_contract():
    runner = CliRunner()

    result = runner.invoke(main, ["model", "list", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["catalogs"] == [
        {
            "catalog_version": "latest",
            "channel": "latest",
            "default_model": DEFAULT_CATALOG_MODEL,
            "enabled_models": [DEFAULT_CATALOG_MODEL],
        }
    ]
    models = {model["id"]: model for model in payload["models"]}
    assert models[DEFAULT_CATALOG_MODEL]["default"] is True
    assert models[DEFAULT_CATALOG_MODEL]["enabled_by_default"] is True
    assert models[LITE_CATALOG_MODEL]["default"] is False
    assert all(model["verification"] == "verified" for model in models.values())
    assert payload["configured"] is None


def test_bare_model_list_merges_cwd_config_with_builtin_catalog():
    runner = CliRunner()

    with runner.isolated_filesystem():
        Path("config.yaml").write_text(
            yaml.safe_dump(_VALID_CONFIG, sort_keys=False), encoding="utf-8"
        )
        result = runner.invoke(main, ["model", "list", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert {model["id"] for model in payload["models"]} >= {
        DEFAULT_CATALOG_MODEL,
        LITE_CATALOG_MODEL,
    }
    assert payload["configured"]["default_model"] == "gpt-4o-mini"
    provider = payload["configured"]["provider_models"][0]
    assert provider["kind"] == "provider"
    assert provider["source"].startswith("config:")
    assert provider["backends"][0]["base_url"] == "https://api.openai.com/v1"


def test_bare_model_list_json_is_not_contaminated_by_parser_logs(tmp_path: Path):
    _write_config(tmp_path)

    result = _run_cli_subprocess(tmp_path, "model", "list", "--output", "json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["configured"]["default_model"] == "gpt-4o-mini"
    assert "Configuration parsed successfully" not in result.stdout


def test_model_list_all_versions_contains_only_latest_before_a_release_snapshot():
    runner = CliRunner()

    result = runner.invoke(
        main, ["model", "list", "--all-versions", "--output", "json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["catalogs"] == [
        {
            "catalog_version": "latest",
            "channel": "latest",
            "default_model": DEFAULT_CATALOG_MODEL,
            "enabled_models": [DEFAULT_CATALOG_MODEL],
        }
    ]
    assert {model["channel"] for model in payload["models"]} == {"latest"}


def test_model_list_table_identifies_the_latest_channel(caplog):
    runner = CliRunner()

    with caplog.at_level("INFO"):
        result = runner.invoke(main, ["model", "list", "--all-versions"])

    assert result.exit_code == 0
    lines = [record.message for record in caplog.records]
    assert any("VERSION" in line and "CHANNEL" in line for line in lines)
    chorus_rows = [line for line in lines if DEFAULT_CATALOG_MODEL in line]
    assert any(" latest " in line for line in chorus_rows)
    assert not any(" release " in line for line in chorus_rows)


def test_model_show_json_uses_the_latest_snapshot():
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "model",
            "show",
            FLASH_CATALOG_MODEL,
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["catalog_version"] == "latest"
    assert payload["channel"] == "latest"
    assert payload["models"][0]["id"] == FLASH_CATALOG_MODEL
    assert payload["models"][0]["entrypoint"] == FLASH_CATALOG_MODEL
    assert payload["models"][0]["recipe"] == "speed"


def test_model_show_table_includes_public_requirements(caplog):
    runner = CliRunner()

    with caplog.at_level("INFO"):
        result = runner.invoke(main, ["model", "show", DEFAULT_CATALOG_MODEL])

    assert result.exit_code == 0
    combined = "\n".join(record.message for record in caplog.records)
    assert f"Name:            {DEFAULT_CATALOG_MODEL}" in combined
    assert "Catalog:         latest (latest)" in combined
    assert "Recipe:          balance" in combined
    assert "Verification:    verified" in combined


def test_readme_documents_model_list_usage():
    content = README_PATH.read_text(encoding="utf-8")

    assert "vllm-sr model list" in content
    assert "vllm-sr model list --config my-config.yaml" in content
    assert "Provider models" in content
    assert "Model cards" in content


def test_model_list_prints_provider_models_and_model_cards(tmp_path: Path, caplog):
    runner = CliRunner()
    config_path = _write_config(tmp_path)

    with caplog.at_level("INFO"):
        result = runner.invoke(main, ["model", "list", "--config", str(config_path)])

    assert result.exit_code == 0
    combined = "\n".join(record.message for record in caplog.records)

    # Provider models present, with the default flagged so users can tell at
    # a glance which one routing falls back to.
    assert "gpt-4o-mini" in combined
    assert "[default]" in combined
    assert "llama-3-8b" in combined
    # Backend identity (safe fields) is printed.
    assert "openai-primary" in combined
    assert "https://api.openai.com/v1" in combined
    # Model cards section is rendered.
    assert "Model cards" in combined
    assert "modality:" in combined


def test_explicit_config_json_is_scoped_and_safe(tmp_path: Path):
    runner = CliRunner()
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        main,
        ["model", "list", "--config", str(config_path), "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["default_model"] == "gpt-4o-mini"
    assert {model["id"] for model in payload["provider_models"]} == {
        "gpt-4o-mini",
        "llama-3-8b",
    }
    rendered = result.output
    assert "SECRET_API_KEY_DO_NOT_LEAK" not in rendered
    assert "SECRET_ENV_VAR_NAME_DO_NOT_LEAK" not in rendered
    assert "catalogs" not in payload


def test_model_list_never_leaks_api_key_or_env_var(tmp_path: Path, caplog):
    runner = CliRunner()
    config_data = yaml.safe_load(yaml.safe_dump(_VALID_CONFIG, sort_keys=False))
    config_data["providers"]["models"][0]["backend_refs"][0][
        "base_url"
    ] = "https://sk-url-secret@api.openai.com/v1?api_key=SECRET_QUERY_KEY&project=public"
    config_data["providers"]["models"][1]["backend_refs"][0][
        "base_url"
    ] = "http://localhost:8000/v1?token=SECRET_QUERY_TOKEN&tenant=dev"
    config_path = _write_config(tmp_path, config_data)

    with caplog.at_level("INFO"):
        result = runner.invoke(main, ["model", "list", "--config", str(config_path)])

    assert result.exit_code == 0
    combined = result.output + "\n".join(record.message for record in caplog.records)
    # The whole point of the command: inspection without credential exposure.
    assert "SECRET_API_KEY_DO_NOT_LEAK" not in combined
    assert "SECRET_ENV_VAR_NAME_DO_NOT_LEAK" not in combined
    assert "sk-url-secret" not in combined
    assert "SECRET_QUERY_KEY" not in combined
    assert "SECRET_QUERY_TOKEN" not in combined
    assert "https://***@api.openai.com/v1?api_key=***&project=public" in combined
    assert "http://localhost:8000/v1?token=***&tenant=dev" in combined


def test_model_list_tolerates_malformed_backend_url(tmp_path: Path, caplog):
    runner = CliRunner()
    config_data = yaml.safe_load(yaml.safe_dump(_VALID_CONFIG, sort_keys=False))
    config_data["providers"]["models"][0]["backend_refs"][0]["base_url"] = "http://[::1"
    config_path = _write_config(tmp_path, config_data)

    with caplog.at_level("INFO"):
        result = runner.invoke(main, ["model", "list", "--config", str(config_path)])

    assert result.exit_code == 0
    combined = "\n".join(record.message for record in caplog.records)
    assert "http://[::1" in combined


def test_model_list_reports_missing_config(tmp_path: Path, caplog):
    runner = CliRunner()
    missing = tmp_path / "does-not-exist.yaml"

    with caplog.at_level("ERROR"):
        result = runner.invoke(main, ["model", "list", "--config", str(missing)])

    assert result.exit_code == 1
    combined = "\n".join(record.message for record in caplog.records)
    assert "Config file not found" in combined


def test_model_fork_single_model_writes_canonical_yaml(tmp_path: Path):
    runner = CliRunner()
    destination = tmp_path / "chorus.yaml"

    result = runner.invoke(
        main, ["model", "fork", DEFAULT_CATALOG_MODEL, str(destination)]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["path"] == str(destination.resolve())
    assert payload["catalog_version"] == "latest"
    assert payload["enabled"] == [DEFAULT_CATALOG_MODEL]
    assert payload["default"] == DEFAULT_CATALOG_MODEL
    assert payload["verification"] == "verified"
    document = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert document["entrypoints"] == [
        {"model_names": [DEFAULT_CATALOG_MODEL], "recipe": "balance"}
    ]
    assert [recipe["name"] for recipe in document["recipes"]] == ["balance"]


def test_model_fork_multiple_models_honors_explicit_default_and_channel(
    tmp_path: Path,
):
    runner = CliRunner()
    destination = tmp_path / "custom.yaml"

    result = runner.invoke(
        main,
        [
            "model",
            "fork",
            LITE_CATALOG_MODEL,
            str(destination),
            "--enable",
            FLASH_CATALOG_MODEL,
            "--default",
            FLASH_CATALOG_MODEL,
            "--catalog-version",
            "latest",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["catalog_version"] == "latest"
    assert payload["enabled"] == [FLASH_CATALOG_MODEL, LITE_CATALOG_MODEL]
    assert payload["default"] == FLASH_CATALOG_MODEL
    assert payload["verification"] == "verified"
    document = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert document["entrypoints"] == [
        {"model_names": [FLASH_CATALOG_MODEL], "recipe": "speed"},
        {"model_names": [LITE_CATALOG_MODEL], "recipe": "cost"},
    ]

    validate_result = runner.invoke(
        main,
        ["model", "validate", str(destination), "--catalog-version", "latest"],
    )
    assert validate_result.exit_code == 0
    validation = json.loads(validate_result.output)
    assert validation["catalog_models"] == [
        FLASH_CATALOG_MODEL,
        LITE_CATALOG_MODEL,
    ]
    assert validation["default_model"] == FLASH_CATALOG_MODEL
    assert validation["verification"] == "verified"


def test_model_fork_does_not_overwrite_existing_file(tmp_path: Path, caplog):
    runner = CliRunner()
    destination = tmp_path / "existing.yaml"
    destination.write_text("sentinel\n", encoding="utf-8")

    with caplog.at_level("ERROR"):
        result = runner.invoke(
            main, ["model", "fork", DEFAULT_CATALOG_MODEL, str(destination)]
        )

    assert result.exit_code == 1
    assert destination.read_text(encoding="utf-8") == "sentinel\n"
    assert "refusing to overwrite" in "\n".join(
        record.message for record in caplog.records
    )


def test_model_validate_reports_untouched_default_fork_as_verified(tmp_path: Path):
    runner = CliRunner()
    destination = tmp_path / "verified.yaml"
    fork_result = runner.invoke(
        main, ["model", "fork", DEFAULT_CATALOG_MODEL, str(destination)]
    )
    assert fork_result.exit_code == 0

    result = runner.invoke(main, ["model", "validate", str(destination)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {
        "valid": True,
        "catalog_version": "latest",
        "catalog_models": [DEFAULT_CATALOG_MODEL],
        "default_model": DEFAULT_CATALOG_MODEL,
        "verification": "verified",
    }


def test_model_validate_json_is_not_contaminated_by_parser_logs(tmp_path: Path):
    destination = tmp_path / "verified.yaml"
    fork_result = CliRunner().invoke(
        main, ["model", "fork", DEFAULT_CATALOG_MODEL, str(destination)]
    )
    assert fork_result.exit_code == 0

    result = _run_cli_subprocess(tmp_path, "model", "validate", str(destination))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["verification"] == "verified"
    assert "Configuration parsed successfully" not in result.stdout


def test_model_validate_reports_untouched_nondefault_subset_as_verified(tmp_path: Path):
    runner = CliRunner()
    destination = tmp_path / "lite.yaml"
    fork_result = runner.invoke(
        main,
        [
            "model",
            "fork",
            LITE_CATALOG_MODEL,
            str(destination),
            "--catalog-version",
            "latest",
        ],
    )
    assert fork_result.exit_code == 0

    result = runner.invoke(
        main,
        ["model", "validate", str(destination), "--catalog-version", "latest"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["valid"] is True
    assert payload["catalog_models"] == [LITE_CATALOG_MODEL]
    assert payload["default_model"] == LITE_CATALOG_MODEL
    assert payload["verification"] == "verified"


def test_model_validate_reports_edited_default_fork_as_custom(tmp_path: Path):
    runner = CliRunner()
    destination = tmp_path / "edited.yaml"
    fork_result = runner.invoke(
        main, ["model", "fork", DEFAULT_CATALOG_MODEL, str(destination)]
    )
    assert fork_result.exit_code == 0
    document = yaml.safe_load(destination.read_text(encoding="utf-8"))
    document["recipes"][0]["description"] += " User customized."
    destination.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    result = runner.invoke(main, ["model", "validate", str(destination)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["valid"] is True
    assert payload["catalog_models"] == [DEFAULT_CATALOG_MODEL]
    assert payload["verification"] == "custom/unverified"
