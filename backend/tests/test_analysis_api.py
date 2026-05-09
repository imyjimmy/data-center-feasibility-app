import time

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_analysis_run_populates_provider_insights_in_background() -> None:
    response = client.post(
        "/api/analysis-runs",
        json={"question": "Find Texas parcels with power, water, fiber, and zoning context."},
    )

    assert response.status_code == 200
    created = response.json()
    assert created["question"].startswith("Find Texas parcels")

    run_response = client.get(f"/api/analysis-runs/{created['run_id']}")
    for _ in range(20):
        if run_response.json()["status"] == "complete":
            break
        time.sleep(0.05)
        run_response = client.get(f"/api/analysis-runs/{created['run_id']}")

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "complete"
    insight_ids = {insight["provider_id"] for insight in run["provider_insights"]}
    assert "ercot_market_data_transparency" in insight_ids
    assert "travis_county_parcels" in insight_ids


def test_unknown_analysis_run_returns_404() -> None:
    response = client.get("/api/analysis-runs/missing")

    assert response.status_code == 404
