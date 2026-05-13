import json

from agent.utils.service_catalog import load_service_catalog


def test_load_service_catalog_from_json(tmp_path) -> None:
    path = tmp_path / "service-catalog.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "repos": [
                    {
                        "repo": "clinikk/subscription-service",
                        "aliases": ["subscription", "ola"],
                    }
                ],
            }
        )
    )

    catalog = load_service_catalog(path)

    assert catalog["repos"][0]["repo"] == "clinikk/subscription-service"


def test_load_service_catalog_returns_empty_for_missing_path(tmp_path) -> None:
    catalog = load_service_catalog(tmp_path / "missing.json")

    assert catalog == {}
