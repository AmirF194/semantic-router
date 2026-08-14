"""Management API config helpers used by local runtime orchestration."""

from cli.consts import DEFAULT_API_PORT

_MAX_PORT = 65_535


def _configured_management_port(user_config: dict) -> int:
    global_config = user_config.get("global")
    if global_config is None:
        global_config = {}
    elif not isinstance(global_config, dict):
        raise ValueError("global must be a mapping")
    services = global_config.get("services")
    if services is None:
        services = {}
    elif not isinstance(services, dict):
        raise ValueError("global.services must be a mapping")
    management = services.get("management_api")
    if management is None:
        management = {}
    elif not isinstance(management, dict):
        raise ValueError("global.services.management_api must be a mapping")
    port = management.get("port", DEFAULT_API_PORT)
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError("management API port must be between 1 and 65535")
    if port == 0:
        port = DEFAULT_API_PORT
    if not 1 <= port <= _MAX_PORT:
        raise ValueError("management API port must be between 1 and 65535")
    return port
