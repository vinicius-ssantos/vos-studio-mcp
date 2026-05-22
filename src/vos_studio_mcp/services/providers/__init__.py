from src.vos_studio_mcp.services.providers.base import ProviderAdapter
from src.vos_studio_mcp.services.providers.manual_dashboard import ManualDashboardAdapter

_registry: dict[str, ProviderAdapter] = {
    "manual_dashboard": ManualDashboardAdapter(),
}


def get_adapter(provider_id: str) -> ProviderAdapter:
    adapter = _registry.get(provider_id)
    if adapter is None:
        raise ValueError(f"Unknown provider: {provider_id}")
    return adapter
