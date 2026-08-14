"""Model command implementations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

from cli.model_catalog import (
    DEFAULT_CHANNEL,
    ModelCatalogError,
    catalog_model_to_dict,
    catalog_to_json,
    find_catalog_model,
    fork_catalog_models,
    load_all_model_catalogs,
    load_model_catalog,
    materialize_catalog_models,
)
from cli.parser import ConfigParseError, parse_user_config
from cli.utils import get_logger
from cli.validator import validate_user_config

log = get_logger(__name__)

_SENSITIVE_QUERY_KEY_FRAGMENTS = ("key", "token", "secret", "password")


def model_list_command(
    config_path: str | None = None,
    *,
    catalog_version: str = DEFAULT_CHANNEL,
    include_all_versions: bool = False,
    include_incompatible: bool = False,
    output: str = "table",
) -> None:
    """Print built-ins, optionally merged with or scoped to runtime config.

    Args:
        config_path: Explicit path to user config.yaml. When omitted, list the
            installed catalog and merge ``./config.yaml`` when it exists.
    """
    if config_path is None:
        try:
            catalogs = (
                load_all_model_catalogs()
                if include_all_versions
                else (load_model_catalog(catalog_version),)
            )
        except ModelCatalogError as error:
            log.error(str(error))
            sys.exit(1)
        models = [
            model
            for catalog in catalogs
            for model in catalog.models
            if include_incompatible or model.compatibility.compatible
        ]
        default_config = Path("config.yaml")
        configured = None
        if default_config.is_file():
            configured = _configured_models_payload(
                _parse_config_or_exit(default_config, log_summary=output != "json"),
                default_config,
            )
        payload = {
            "catalogs": [
                {
                    "catalog_version": catalog.version,
                    "channel": catalog.channel,
                    "default_model": catalog.default_model,
                    "enabled_models": list(catalog.enabled_models),
                }
                for catalog in catalogs
            ],
            "models": [catalog_model_to_dict(model) for model in models],
            "configured": configured,
        }
        if output == "json":
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        _print_builtin_models(models)
        if configured is not None:
            log.info("")
            _print_configured_models(configured)
        return

    explicit_path = Path(config_path)
    if not explicit_path.exists():
        log.error(f"Config file not found: {config_path}")
        log.error(
            "Run 'vllm-sr serve' to bootstrap setup mode and create a config file"
        )
        sys.exit(1)

    user_config = _parse_config_or_exit(explicit_path, log_summary=output != "json")
    configured = _configured_models_payload(user_config, explicit_path)
    if output == "json":
        print(json.dumps(configured, indent=2, sort_keys=True))
        return

    _print_configured_models(configured, user_config=user_config)


def model_show_command(
    model_id: str,
    *,
    catalog_version: str = DEFAULT_CHANNEL,
    output: str = "table",
) -> None:
    try:
        catalog, model = find_catalog_model(model_id, catalog_version=catalog_version)
    except ModelCatalogError as error:
        log.error(str(error))
        sys.exit(1)
    if output == "json":
        print(catalog_to_json(catalog, [model]))
        return
    details = catalog_model_to_dict(model)
    log.info(f"Name:            {details['id']}")
    log.info(f"Display name:    {details['display_name']}")
    log.info(f"Kind:            {details['kind']}")
    log.info(f"Family:          {details['family']} v{details['generation']}")
    log.info(f"Policy version:  {details['policy_version']}")
    log.info(f"Catalog:         {details['catalog_version']} ({details['channel']})")
    log.info(f"Entrypoint:      {details['entrypoint']}")
    log.info(f"Recipe:          {details['recipe']}")
    log.info(f"Protocols:       {', '.join(details['protocols'])}")
    log.info(f"Traits:          {', '.join(details['traits'])}")
    log.info(f"Compatibility:   {details['compatibility_reason']}")
    log.info(f"Verification:    {details['verification']}")
    log.info("Backend roles:")
    for role in details["roles"]:
        required = "required" if role["required"] else "optional"
        log.info(
            f"  - {role['name']} ({required}, min {role['minimum_candidates']}): "
            + ", ".join(role["traits"])
        )
        log.info("      recommended: " + ", ".join(role["recommended_pool"]))


def model_fork_command(
    model_ids: tuple[str, ...],
    destination: str,
    *,
    catalog_version: str = DEFAULT_CHANNEL,
    default_model: str | None = None,
) -> None:
    try:
        result = fork_catalog_models(
            model_ids,
            Path(destination),
            catalog_version=catalog_version,
            default_model=default_model,
        )
    except (ModelCatalogError, OSError) as error:
        log.error(str(error))
        sys.exit(1)
    print(json.dumps(result, indent=2, sort_keys=True))


def model_validate_command(
    config_path: str,
    *,
    catalog_version: str = DEFAULT_CHANNEL,
) -> None:
    path = Path(config_path)
    if not path.is_file():
        log.error(f"Config file not found: {config_path}")
        sys.exit(1)
    try:
        user_config = parse_user_config(str(path), log_summary=False)
    except ConfigParseError as error:
        log.error(f"Failed to parse configuration: {error}")
        sys.exit(1)
    errors = validate_user_config(user_config, log_summary=False)
    if errors:
        for error in errors:
            log.error(str(error))
        sys.exit(1)

    try:
        catalog = load_model_catalog(catalog_version)
    except ModelCatalogError as error:
        log.error(str(error))
        sys.exit(1)
    models_by_entrypoint = {model.entrypoint: model for model in catalog.models}
    selected: list[str] = []
    for entrypoint in user_config.entrypoints:
        for name in entrypoint.model_names:
            model = models_by_entrypoint.get(name)
            if model is not None and model.id not in selected:
                selected.append(model.id)

    raw_document = yaml.safe_load(path.read_text(encoding="utf-8"))
    matches_catalog = False
    if selected and isinstance(raw_document, dict):
        try:
            expected = materialize_catalog_models(
                selected,
                catalog_version=catalog_version,
                default_model=selected[0],
            )
            matches_catalog = raw_document == expected.document
        except ModelCatalogError:
            matches_catalog = False
    status = "verified" if matches_catalog else "custom/unverified"
    print(
        json.dumps(
            {
                "valid": True,
                "catalog_version": catalog.version,
                "catalog_models": selected,
                "default_model": selected[0] if selected else None,
                "verification": status,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _print_builtin_models(models) -> None:
    log.info("vLLM Semantic Router - Built-in Models")
    log.info(
        "NAME                           VERSION   CHANNEL  DEFAULT  STATUS       TRAITS"
    )
    for model in models:
        default = "yes" if model.default else "-"
        status = "verified" if model.verified else model.compatibility.reason
        log.info(
            f"{model.id:<30} {model.catalog_version:<9} {model.channel:<8} "
            f"{default:<8} "
            f"{status:<12} {','.join(model.traits)}"
        )


def _parse_config_or_exit(path: Path, *, log_summary: bool = True):
    try:
        return parse_user_config(str(path), log_summary=log_summary)
    except ConfigParseError as error:
        log.error(f"Failed to parse configuration: {error}")
        sys.exit(1)


def _configured_models_payload(user_config, path: Path) -> dict:
    source = f"config:{path.resolve()}"
    providers = getattr(user_config, "providers", None)
    default_model = (
        providers.defaults.default_model
        if providers is not None and providers.defaults is not None
        else None
    )
    provider_models = []
    for model in list(getattr(providers, "models", []) or []):
        provider_models.append(
            {
                "id": model.name,
                "kind": "provider",
                "source": source,
                "default": model.name == default_model,
                "provider_model_id": model.provider_model_id,
                "reasoning_family": model.reasoning_family,
                "api_format": model.api_format,
                "backends": [
                    {
                        "name": ref.name,
                        "provider": ref.provider,
                        "base_url": _redact_url(ref.base_url or ref.endpoint or ""),
                        "protocol": ref.protocol,
                        "weight": ref.weight,
                    }
                    for ref in list(model.backend_refs or [])
                ],
            }
        )

    routing = getattr(user_config, "routing", None)
    model_cards = []
    for card in list(getattr(routing, "model_cards", []) or []):
        model_cards.append(
            {
                "id": card.name,
                "kind": "model_card",
                "source": source,
                "modality": card.modality,
                "capabilities": list(card.capabilities or []),
                "tags": list(card.tags or []),
                "context_window_size": card.context_window_size,
                "param_size": card.param_size,
            }
        )
    return {
        "source": source,
        "path": str(path.resolve()),
        "default_model": default_model,
        "provider_models": provider_models,
        "model_cards": model_cards,
    }


def _print_configured_models(configured: dict, *, user_config=None) -> None:
    log.info("=" * 60)
    log.info("vLLM Semantic Router - Configured Models")
    log.info("=" * 60)
    log.info(f"Source: {configured['source']}")
    log.info("")
    if user_config is not None:
        _print_provider_models(user_config)
        log.info("")
        _print_model_cards(user_config)
        return
    log.info(f"Provider models ({len(configured['provider_models'])}):")
    for model in configured["provider_models"]:
        default = " [default]" if model["default"] else ""
        log.info(f"  - {model['id']}{default}  source={model['source']}")
    log.info("")
    log.info(f"Model cards ({len(configured['model_cards'])}):")
    for card in configured["model_cards"]:
        log.info(f"  - {card['id']}  source={card['source']}")


def _print_provider_models(user_config) -> None:
    providers = getattr(user_config, "providers", None)
    models = list(getattr(providers, "models", []) or []) if providers else []

    log.info(f"Provider models ({len(models)}):")
    if not models:
        log.info("  (none configured)")
        return

    default_model = None
    if providers and providers.defaults:
        default_model = providers.defaults.default_model

    for model in models:
        is_default = " [default]" if model.name == default_model else ""
        log.info(f"  - {model.name}{is_default}")
        if model.provider_model_id and model.provider_model_id != model.name:
            log.info(f"      provider_model_id: {model.provider_model_id}")
        if model.reasoning_family:
            log.info(f"      reasoning_family:  {model.reasoning_family}")
        if model.api_format:
            log.info(f"      api_format:        {model.api_format}")

        backends = list(model.backend_refs or [])
        if backends:
            log.info(f"      backends ({len(backends)}):")
            for ref in backends:
                # Never print api_key / api_key_env values; expose only the
                # transport identity so credentials cannot leak via CLI output.
                provider = ref.provider or "-"
                base_url = _redact_url(ref.base_url or ref.endpoint or "-")
                label = ref.name or "(unnamed)"
                log.info(
                    f"        * {label}  provider={provider}  base_url={base_url}  "
                    f"protocol={ref.protocol}  weight={ref.weight}"
                )


def _print_model_cards(user_config) -> None:
    routing = getattr(user_config, "routing", None)
    cards = list(getattr(routing, "model_cards", []) or []) if routing else []

    log.info(f"Model cards ({len(cards)}):")
    if not cards:
        log.info("  (none configured)")
        return

    for card in cards:
        log.info(f"  - {card.name}")
        if card.modality:
            log.info(f"      modality:        {card.modality}")
        if card.param_size:
            log.info(f"      param_size:      {card.param_size}")
        if card.context_window_size:
            log.info(f"      context_window:  {card.context_window_size}")
        if card.capabilities:
            log.info(f"      capabilities:    {', '.join(card.capabilities)}")
        if card.tags:
            log.info(f"      tags:            {', '.join(card.tags)}")
        if card.loras:
            lora_names = ", ".join(a.name for a in card.loras)
            log.info(f"      loras:           {lora_names}")


def _redact_url(value: str) -> str:
    """Return a display-safe URL without embedded credentials."""
    if value == "-":
        return value

    try:
        parsed = urlsplit(value)
    except ValueError:
        return value

    netloc = parsed.netloc
    if "@" in netloc:
        netloc = "***@" + netloc.rsplit("@", 1)[1]

    query_items = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        if any(fragment in key.lower() for fragment in _SENSITIVE_QUERY_KEY_FRAGMENTS):
            query_items.append((key, "***"))
        else:
            query_items.append((key, item_value))

    redacted_query = urlencode(query_items, doseq=True, safe="*")
    return urlunsplit(
        (parsed.scheme, netloc, parsed.path, redacted_query, parsed.fragment)
    )
