import pytest

from app.providers.models import Concern
from app.providers.registry import get_provider_registry


def test_registry_lists_texas_providers_by_concern() -> None:
    registry = get_provider_registry()

    water_providers = registry.list(concern=Concern.WATER, state="TX")

    assert {provider.id for provider in water_providers} == {
        "austin_water_utility_service_area",
        "twdb_water_data_for_texas",
    }


def test_registry_raises_for_unknown_provider() -> None:
    registry = get_provider_registry()

    with pytest.raises(KeyError, match="Unknown provider"):
        registry.get("missing")
