from vos_studio_mcp.services.providers.base import ProviderAdapter
from vos_studio_mcp.services.providers.freepik import FreepikAdapter
from vos_studio_mcp.services.providers.higgsfield import HiggsFieldAdapter
from vos_studio_mcp.services.providers.higgsfield_mcp import HiggsFieldMcpAdapter
from vos_studio_mcp.services.providers.magnific import MagnificAdapter
from vos_studio_mcp.services.providers.manual_dashboard import ManualDashboardAdapter

_registry: dict[str, ProviderAdapter] = {
    "manual_dashboard": ManualDashboardAdapter(),
    "higgsfield": HiggsFieldAdapter(),
    "higgsfield_mcp": HiggsFieldMcpAdapter(),
    "freepik": FreepikAdapter(),
    "magnific": MagnificAdapter(),
}


def get_adapter(provider_id: str) -> ProviderAdapter:
    adapter = _registry.get(provider_id)
    if adapter is None:
        raise ValueError(f"Unknown provider: {provider_id}")
    return adapter
