from app.provider_mcp import create_provider_mcp


def test_create_provider_scoped_mcp() -> None:
    mcp = create_provider_mcp("travis_county_parcels")

    assert mcp.name == "Travis County Parcels MCP"


def test_create_provider_scoped_mcp_rejects_unknown_provider() -> None:
    try:
        create_provider_mcp("missing")
    except KeyError as exc:
        assert "Unknown provider" in str(exc)
    else:
        raise AssertionError("Expected missing provider to raise KeyError")
