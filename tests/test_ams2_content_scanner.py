from pathlib import Path

from circuit_stackers.ams2_content_scanner import (
    compare_cars_csv_to_packages,
    discover_roots,
    scan_ams2_content,
    scan_custom_ai_liveries,
    scan_custom_liveries,
    scan_packed_vehicles,
)


def _make_ams2_tree(root: Path) -> None:
    (root / "Pakfiles" / "Vehicles").mkdir(parents=True)
    (root / "UserData" / "CustomAIDrivers").mkdir(parents=True)
    archive = root / "Pakfiles" / "Vehicles" / "Cadillac_V-Series_R_Livery.bff"
    archive.write_bytes(b" KAP\x04\x00\x40\x10\x00Cadillac_V-Series_R_Livery\x00")
    (root / "Vehicles" / "Textures" / "CustomLiveries" / "Overrides" / "Cadillac").mkdir(parents=True)
    (root / "Vehicles" / "Textures" / "CustomLiveries" / "Overrides" / "Cadillac" / "custom.xml").write_text(
        '<livery_override NAME="Test Livery" ID="17" />', encoding="utf-8"
    )
    (root / "UserData" / "CustomAIDrivers" / "F-Test.xml").write_text(
        '<drivers><driver name="A" livery_name="AI Livery" /></drivers>', encoding="utf-8"
    )


def test_scans_packed_and_xml_content(tmp_path: Path) -> None:
    _make_ams2_tree(tmp_path)
    roots = discover_roots(tmp_path)

    assert roots.install == tmp_path
    assert roots.user_data == tmp_path
    assert scan_packed_vehicles(roots.install)[0].package_name == "Cadillac_V-Series_R"
    assert scan_packed_vehicles(roots.install)[0].header_name == "Cadillac_V-Series_R_Livery"
    assert scan_custom_liveries(roots)[0].livery_id == "17"
    assert scan_custom_ai_liveries(roots)[0].name == "AI Livery"


def test_scan_result_marks_default_ids_as_unresolved(tmp_path: Path) -> None:
    _make_ams2_tree(tmp_path)
    result = scan_ams2_content(tmp_path)

    assert result["default_livery_ids_available"] is False
    assert len(result["packed_vehicles"]) == 1


def test_csv_package_comparison_reports_exact_and_unresolved_rows(tmp_path: Path) -> None:
    _make_ams2_tree(tmp_path)
    csv_path = tmp_path / "Cars.csv"
    csv_path.write_text(
        "id,Car,Game,ams2_livery_folder\n9001,Cadillac,AMS2,Cadillac_V-Series_R\n"
        "9002,Unknown,AMS2,unknown_car\n",
        encoding="utf-8",
    )

    matches = compare_cars_csv_to_packages(tmp_path, csv_path)

    assert matches[0].package_name == "Cadillac_V-Series_R"
    assert matches[1].package_name == ""
    assert matches[1].candidates == ("Cadillac_V-Series_R",)
