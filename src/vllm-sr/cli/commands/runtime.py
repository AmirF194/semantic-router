"""Runtime-oriented Click command entrypoints."""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path

import click

from cli.bootstrap import (
    ensure_bootstrap_workspace,
    is_setup_mode_config,
)
from cli.commands.common import exit_with_logged_error
from cli.commands.runtime_config_mutation import (
    ALGORITHM_TYPES,
)
from cli.commands.runtime_config_mutation import (
    inject_algorithm_into_config as _inject_algorithm_into_config,
)
from cli.commands.runtime_help import SERVE_HELP
from cli.commands.runtime_paths import (
    _runtime_config_output_path,
    materialize_runtime_config,
)
from cli.commands.runtime_support import (
    append_passthrough_env_vars,
    apply_container_runtime_override,
    apply_runtime_mode_env_vars,
    build_effective_config_bytes,
    configure_recipe_env_bindings,
    configure_runtime_override_env_vars,
    log_bootstrap_result,
    resolve_effective_config_path,
    validate_config_recipe_env_bindings,
    validate_setup_mode_flags,
)
from cli.consts import (
    DEFAULT_IMAGE_PULL_POLICY,
    IMAGE_PULL_POLICY_ALWAYS,
    IMAGE_PULL_POLICY_IF_NOT_PRESENT,
    IMAGE_PULL_POLICY_NEVER,
    SUPPORTED_CONTAINER_RUNTIMES,
    VLLM_SR_CONTAINER_IMAGE_DEFAULT,
)
from cli.container_services import container_status_strict
from cli.deployment_backend import DEFAULT_TARGET, VALID_TARGETS, resolve_target
from cli.recipe_activation_recovery import (
    active_recipe_package_for_stack,
    recover_pending_recipe_activation_for_stack,
)
from cli.runtime_config_lock import acquire_runtime_config_lock
from cli.runtime_stack import resolve_runtime_stack
from cli.utils import get_logger

log = get_logger(__name__)


def inject_algorithm_into_config(config_path: Path, algorithm: str) -> Path:
    """Compatibility wrapper for callers importing from cli.commands.runtime."""
    return _inject_algorithm_into_config(config_path, algorithm)


TARGET_HELP = (
    f"Deployment target: {', '.join(VALID_TARGETS)} (default: {DEFAULT_TARGET})"
)

RUNTIME_HELP = (
    "Container runtime for the local Docker target: "
    f"{', '.join(SUPPORTED_CONTAINER_RUNTIMES)}. "
    "Equivalent to setting CONTAINER_RUNTIME=<runtime>. Has no effect on the k8s target."
)


def _build_backend(target: str | None, **k8s_kwargs):
    """Instantiate the right DeploymentBackend for *target*."""
    resolved = resolve_target(target)
    if resolved == "k8s":
        from cli.k8s_backend import K8sBackend  # noqa: PLC0415

        return K8sBackend(**{k: v for k, v in k8s_kwargs.items() if v is not None})

    from cli.container_backend import ContainerBackend  # noqa: PLC0415

    return ContainerBackend()


def _prepare_docker_runtime_config(
    config_path: Path,
    algorithm: str | None,
    source_setup_mode: bool,
    platform: str | None,
    recipe_env_bindings: tuple[str, ...],
):
    stack_layout = resolve_runtime_stack()
    state_root_dir = (
        Path(os.environ["VLLM_SR_STATE_ROOT_DIR"]).expanduser().absolute()
        if os.getenv("VLLM_SR_STATE_ROOT_DIR", "").strip()
        else config_path.expanduser().absolute().parent
    )
    effective_config_path = _runtime_config_output_path(
        config_path,
        state_root_dir=state_root_dir,
        stack_name=stack_layout.stack_name,
    )
    runtime_lock = acquire_runtime_config_lock(
        runtime_config_path=effective_config_path,
        state_root_dir=state_root_dir,
        stack_name=stack_layout.stack_name,
    )
    try:
        recover_pending_recipe_activation_for_stack(
            runtime_config_path=effective_config_path,
            state_root_dir=state_root_dir,
            stack_name=stack_layout.stack_name,
            managed_container_names=stack_layout.runtime_container_names,
            status_provider=container_status_strict,
        )
        package_active = active_recipe_package_for_stack(
            state_root_dir=state_root_dir, stack_name=stack_layout.stack_name
        )
        if package_active:
            validate_config_recipe_env_bindings(
                effective_config_path, recipe_env_bindings
            )
        else:
            effective_config_bytes = build_effective_config_bytes(
                config_path, algorithm, source_setup_mode, platform
            )
            effective_config_path = materialize_runtime_config(
                config_path,
                effective_config_bytes,
                state_root_dir=state_root_dir,
                stack_name=stack_layout.stack_name,
            )
        setup_mode = is_setup_mode_config(effective_config_path)
        return effective_config_path, setup_mode, runtime_lock
    except Exception:
        runtime_lock.close()
        raise


def _execute_serve(
    config: str,
    image: str | None,
    router_image: str | None,
    envoy_image: str | None,
    dashboard_image: str | None,
    sim_image: str | None,
    image_pull_policy: str,
    readonly: bool,
    minimal: bool,
    log_level: str | None,
    platform: str | None,
    algorithm: str | None,
    target: str | None,
    namespace: str | None,
    context: str | None,
    profile: str | None,
    chart_dir: str | None,
    runtime: str | None,
    recipe_env_names: tuple[str, ...] = (),
) -> None:
    """Bootstrap workspace, resolve config, and delegate to the deployment backend."""
    apply_container_runtime_override(runtime)
    requested_config = config
    bootstrap = ensure_bootstrap_workspace(Path(config))
    config_path = bootstrap.config_path
    source_setup_mode = bootstrap.setup_mode

    log_bootstrap_result(requested_config, bootstrap)
    log.info(f"Using config file: {config_path}")

    env_vars: dict[str, str] = {}
    append_passthrough_env_vars(env_vars, config_path)
    recipe_env_bindings = configure_recipe_env_bindings(env_vars, recipe_env_names)

    resolved_target = resolve_target(target)
    if resolved_target != "docker" and recipe_env_bindings:
        raise ValueError(
            "--recipe-env is supported only for local Docker Recipe packages"
        )
    runtime_lock = None
    try:
        if resolved_target == "docker":
            effective_config_path, setup_mode, runtime_lock = (
                _prepare_docker_runtime_config(
                    config_path,
                    algorithm,
                    source_setup_mode,
                    platform,
                    recipe_env_bindings,
                )
            )
        else:
            # Kubernetes remains a deployment translation flow. Its effective
            # local file is not a Dashboard-owned persistent runtime workspace.
            effective_config_path = resolve_effective_config_path(
                config_path, algorithm, source_setup_mode, platform
            )
            setup_mode = source_setup_mode
        validate_setup_mode_flags(setup_mode, minimal, readonly)
        apply_runtime_mode_env_vars(
            env_vars,
            minimal,
            readonly,
            setup_mode,
            platform,
            algorithm,
            log_level=log_level,
        )
        configure_runtime_override_env_vars(
            env_vars,
            config_path,
            effective_config_path,
            runtime_owned=resolved_target == "docker",
        )

        backend = _build_backend(
            resolved_target,
            namespace=namespace,
            context=context,
            profile=profile,
            chart_dir=chart_dir,
        )
        backend.deploy(
            config_file=str(effective_config_path.absolute()),
            source_config_file=str(config_path.absolute()),
            runtime_config_file=str(effective_config_path.absolute()),
            runtime_config_lock=runtime_lock,
            env_vars=env_vars,
            image=image,
            router_image=router_image,
            envoy_image=envoy_image,
            dashboard_image=dashboard_image,
            sim_image=sim_image,
            pull_policy=image_pull_policy,
            enable_observability=not minimal,
        )
    finally:
        if runtime_lock is not None:
            runtime_lock.close()


@click.command(help=SERVE_HELP)
@click.option(
    "--config",
    default="config.yaml",
    help="Path to config file (default: config.yaml)",
)
@click.option(
    "--image",
    default=None,
    help=f"Docker image to use (default: {VLLM_SR_CONTAINER_IMAGE_DEFAULT})",
)
@click.option(
    "--router-image",
    default=None,
    help="Docker image for the router container (Docker target only; defaults to --image or VLLM_SR_IMAGE)",
)
@click.option(
    "--envoy-image",
    default=None,
    help="Docker image for the Envoy container (Docker target only; defaults to --image or VLLM_SR_IMAGE)",
)
@click.option(
    "--dashboard-image",
    default=None,
    help="Docker image for the dashboard container (Docker target only; defaults to --image or VLLM_SR_IMAGE)",
)
@click.option(
    "--sim-image",
    default=None,
    help="Docker image for the simulator sidecar (Docker target only; defaults to VLLM_SR_SIM_IMAGE)",
)
@click.option(
    "--image-pull-policy",
    type=click.Choice(
        [
            IMAGE_PULL_POLICY_ALWAYS,
            IMAGE_PULL_POLICY_IF_NOT_PRESENT,
            IMAGE_PULL_POLICY_NEVER,
        ],
        case_sensitive=False,
    ),
    default=DEFAULT_IMAGE_PULL_POLICY,
    help=f"Image pull policy: always, ifnotpresent, never (default: {DEFAULT_IMAGE_PULL_POLICY})",
)
@click.option(
    "--readonly",
    is_flag=True,
    default=False,
    help="Run dashboard in read-only mode (disable config editing, allow playground only)",
)
@click.option(
    "--minimal",
    is_flag=True,
    default=False,
    help="Start in minimal mode: only router + envoy, no dashboard or observability (Jaeger, Prometheus, Grafana)",
)
@click.option(
    "--log-level",
    type=click.Choice(
        ["debug", "info", "warn", "warning", "error", "dpanic", "panic", "fatal"],
        case_sensitive=False,
    ),
    default=None,
    help="Router log level override (debug, info, warn, error, dpanic, panic, fatal)",
)
@click.option(
    "--platform",
    default=None,
    help="Platform for GPU deployments: 'amd' enables ROCm passthrough, "
    "'nvidia' enables NVIDIA GPU passthrough (--gpus all). "
    "When set to amd or nvidia, serve defaults to the matching GPU image "
    "(ROCm / CUDA) and flips use_cpu to false for router internal models under "
    "global.model_catalog, unless --image or VLLM_SR_IMAGE is provided. "
    "Set VLLM_SR_<PLATFORM>_PRESERVE_CPU=1 to keep CPU settings.",
)
@click.option(
    "--algorithm",
    type=click.Choice(ALGORITHM_TYPES, case_sensitive=False),
    default=None,
    help="Request-time base algorithm override: static, router_dc, automix, hybrid, "
    "workflows, latency_aware, knn, kmeans, svm, mlp, or multi_factor. "
    "Cross-request learning uses global.router.learning.adaptation/protection.",
)
@click.option("--target", default=None, help=TARGET_HELP)
@click.option(
    "--namespace", default=None, help="Kubernetes namespace (k8s target only)"
)
@click.option(
    "--context", default=None, help="kubectl / Helm context (k8s target only)"
)
@click.option(
    "--profile",
    default=None,
    help="Deployment profile: dev, prod (k8s target only). Selects values-<profile>.yaml defaults.",
)
@click.option(
    "--chart-dir", default=None, help="Path to Helm chart directory (k8s target only)"
)
@click.option(
    "--runtime",
    type=click.Choice(SUPPORTED_CONTAINER_RUNTIMES, case_sensitive=False),
    default=None,
    help=RUNTIME_HELP,
)
@click.option(
    "--recipe-env",
    "recipe_env_names",
    multiple=True,
    metavar="NAME",
    help=(
        "Explicitly bind one host environment variable for the active Recipe. "
        "Repeat for multiple names; NAME=value is rejected."
    ),
)
@exit_with_logged_error(log, interrupt_message="\nInterrupted by user")
def serve(
    config: str,
    image: str | None,
    router_image: str | None,
    envoy_image: str | None,
    dashboard_image: str | None,
    sim_image: str | None,
    image_pull_policy: str,
    readonly: bool,
    minimal: bool,
    log_level: str | None,
    platform: str | None,
    algorithm: str | None,
    target: str | None,
    namespace: str | None,
    context: str | None,
    profile: str | None,
    chart_dir: str | None,
    runtime: str | None,
    recipe_env_names: tuple[str, ...],
) -> None:
    _execute_serve(
        config,
        image,
        router_image,
        envoy_image,
        dashboard_image,
        sim_image,
        image_pull_policy,
        readonly,
        minimal,
        log_level,
        platform,
        algorithm,
        target,
        namespace,
        context,
        profile,
        chart_dir,
        runtime,
        recipe_env_names,
    )


@click.command()
@click.argument(
    "service",
    type=click.Choice(["envoy", "router", "dashboard", "simulator", "all"]),
    default="all",
)
@click.option("--target", default=None, help=TARGET_HELP)
@click.option(
    "--namespace", default=None, help="Kubernetes namespace (k8s target only)"
)
@click.option(
    "--context", default=None, help="kubectl / Helm context (k8s target only)"
)
@click.option(
    "--runtime",
    type=click.Choice(SUPPORTED_CONTAINER_RUNTIMES, case_sensitive=False),
    default=None,
    help=RUNTIME_HELP,
)
@exit_with_logged_error(log)
def status(
    service: str,
    target: str | None,
    namespace: str | None,
    context: str | None,
    runtime: str | None,
) -> None:
    """
    Show status of vLLM Semantic Router services.

    Examples:
        vllm-sr status              # Show all services (Docker)
        vllm-sr status all          # Show all services
        vllm-sr status router       # Show router status
        vllm-sr status dashboard    # Show dashboard status
        vllm-sr status simulator    # Show simulator status
        vllm-sr status --target k8s # Show Kubernetes status
    """
    apply_container_runtime_override(runtime)
    backend = _build_backend(target, namespace=namespace, context=context)
    backend.status(service)


@click.command()
@click.argument(
    "service", type=click.Choice(["envoy", "router", "dashboard", "simulator"])
)
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.option("--target", default=None, help=TARGET_HELP)
@click.option(
    "--namespace", default=None, help="Kubernetes namespace (k8s target only)"
)
@click.option(
    "--context", default=None, help="kubectl / Helm context (k8s target only)"
)
@click.option(
    "--runtime",
    type=click.Choice(SUPPORTED_CONTAINER_RUNTIMES, case_sensitive=False),
    default=None,
    help=RUNTIME_HELP,
)
@exit_with_logged_error(log, interrupt_message="\nLog streaming stopped")
def logs(
    service: str,
    follow: bool,
    target: str | None,
    namespace: str | None,
    context: str | None,
    runtime: str | None,
) -> None:
    """
    Show logs from vLLM Semantic Router service.

    Examples:
        vllm-sr logs envoy
        vllm-sr logs router
        vllm-sr logs dashboard
        vllm-sr logs simulator
        vllm-sr logs envoy --follow
        vllm-sr logs router -f
        vllm-sr logs router --target k8s        # Kubernetes logs
        vllm-sr logs router --target k8s -f     # Follow K8s logs
    """
    apply_container_runtime_override(runtime)
    backend = _build_backend(target, namespace=namespace, context=context)
    backend.logs(service, follow=follow)


@click.command()
@click.option("--target", default=None, help=TARGET_HELP)
@click.option(
    "--namespace", default=None, help="Kubernetes namespace (k8s target only)"
)
@click.option(
    "--context", default=None, help="kubectl / Helm context (k8s target only)"
)
@click.option(
    "--runtime",
    type=click.Choice(SUPPORTED_CONTAINER_RUNTIMES, case_sensitive=False),
    default=None,
    help=RUNTIME_HELP,
)
@exit_with_logged_error(log)
def stop(
    target: str | None,
    namespace: str | None,
    context: str | None,
    runtime: str | None,
) -> None:
    """
    Stop vLLM Semantic Router.

    Examples:
        vllm-sr stop                # Stop Docker stack
        vllm-sr stop --target k8s   # Uninstall Helm release
    """
    apply_container_runtime_override(runtime)
    backend = _build_backend(target, namespace=namespace, context=context)
    backend.teardown()


@click.command()
@click.option("--no-open", is_flag=True, help="Don't open browser, just show URL")
@click.option("--target", default=None, help=TARGET_HELP)
@click.option(
    "--namespace", default=None, help="Kubernetes namespace (k8s target only)"
)
@click.option(
    "--context", default=None, help="kubectl / Helm context (k8s target only)"
)
@click.option(
    "--runtime",
    type=click.Choice(SUPPORTED_CONTAINER_RUNTIMES, case_sensitive=False),
    default=None,
    help=RUNTIME_HELP,
)
@exit_with_logged_error(log)
def dashboard(
    no_open: bool,
    target: str | None,
    namespace: str | None,
    context: str | None,
    runtime: str | None,
) -> None:
    """
    Open the dashboard in your default web browser.

    Examples:
        vllm-sr dashboard                   # Docker dashboard
        vllm-sr dashboard --target k8s      # Show K8s dashboard URL
        vllm-sr dashboard --no-open
    """
    apply_container_runtime_override(runtime)
    backend = _build_backend(target, namespace=namespace, context=context)
    if not backend.is_running():
        raise ValueError("vLLM Semantic Router is not running")

    dashboard_url = backend.get_dashboard_url()
    if dashboard_url is None:
        log.info("Dashboard URL could not be determined")
        return

    if no_open:
        log.info(f"Dashboard URL: {dashboard_url}")
        return

    log.info(f"Opening dashboard: {dashboard_url}")
    webbrowser.open(dashboard_url)
    log.info("Dashboard opened in browser")
