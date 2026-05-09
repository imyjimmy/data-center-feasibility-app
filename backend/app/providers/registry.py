from collections.abc import Iterable

from app.providers.models import Concern, DataProviderDefinition
from app.providers.texas import TEXAS_OPEN_DATA_PROVIDERS


class ProviderRegistry:
    def __init__(self, providers: Iterable[DataProviderDefinition]) -> None:
        self._providers = {provider.id: provider for provider in providers}

    def list(self, concern: Concern | None = None, state: str | None = None) -> list[DataProviderDefinition]:
        providers = self._providers.values()

        if concern is not None:
            providers = [provider for provider in providers if provider.concern == concern]

        if state is not None:
            state_upper = state.upper()
            providers = [provider for provider in providers if provider.coverage.state.upper() == state_upper]

        return sorted(providers, key=lambda provider: (provider.concern.value, provider.name))

    def get(self, provider_id: str) -> DataProviderDefinition:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            msg = f"Unknown provider: {provider_id}"
            raise KeyError(msg) from exc


def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry(TEXAS_OPEN_DATA_PROVIDERS)
