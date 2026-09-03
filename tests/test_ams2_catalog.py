from pathlib import Path

from circuit_stackers.ams2_catalog import (
    build_canonical_metadata,
    match_catalog_to_packages,
    parse_class_catalog,
    parse_class_page,
    parse_wiki_class_catalog,
    parse_wiki_car_features,
)
from circuit_stackers.ams2_content_scanner import PackedVehicle


def test_parse_class_catalog() -> None:
    html = "<h1>Cars</h1><h2>GT3 Gen2</h2><div>Car BMW M4 GT3</div><div>Car Porsche 992 GT3 R</div>"

    assert parse_class_catalog(html) == {"GT3 Gen2": ["BMW M4 GT3", "Porsche 992 GT3 R"]}


def test_match_catalog_to_packages() -> None:
    packages = [PackedVehicle("BMW_M4_GT3", Path("BMW_M4_GT3_Livery.bff"))]

    matches = match_catalog_to_packages({"GT3 Gen2": ["BMW M4 GT3", "Audi R8 LMS GT3 evo II"]}, packages)

    assert matches[0].package_name == "BMW_M4_GT3"
    assert matches[1].package_name == ""
    assert matches[1].candidates == ("BMW_M4_GT3",)


def test_parse_class_page() -> None:
    html = '<h1>GT3 Gen2</h1><span class="listing-card-label">Car</span><span>BMW M4 GT3</span>'

    assert parse_class_page(html) == ("GT3 Gen2", ["BMW M4 GT3"])


def test_parse_wiki_car_features() -> None:
    html = "<table><tr><th>Headlights</th><td>Yes</td></tr><tr><th>Anti-Lock Brakes</th><td>No</td></tr></table>"

    assert parse_wiki_car_features(html) == {"headlights": True, "anti_lock_brakes": False}


def test_parse_wiki_class_catalog() -> None:
    html = """
    <table><tr><th>Cars</th><th>Manufacturer</th><th>Car class</th></tr>
    <tr><td>BMW M4 GT3</td><td>BMW</td><td>GT3 Gen2</td></tr>
    <tr><td>Porsche 992 GT3 R</td><td>Porsche</td><td>GT3 Gen2</td></tr></table>
    """

    assert parse_wiki_class_catalog(html) == {
        "GT3 Gen2": ["BMW M4 GT3", "Porsche 992 GT3 R"]
    }


def test_canonical_metadata_keeps_livery_ids_optional(tmp_path: Path) -> None:
    vehicle_dir = tmp_path / "Pakfiles" / "Vehicles"
    vehicle_dir.mkdir(parents=True)
    (vehicle_dir / "BMW_M4_GT3_Livery.bff").write_bytes(b" KAP")
    metadata = build_canonical_metadata(tmp_path, {"GT3 Gen2": ["BMW M4 GT3"]})

    assert metadata["cars"][0]["package_name"] == "BMW_M4_GT3"
    assert metadata["cars"][0]["livery_ids_available"] is False
