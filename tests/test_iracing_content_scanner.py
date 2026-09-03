from pathlib import Path

from circuit_stackers.iracing_content_scanner import compare_iracing_car_images, scan_iracing_car_packages


def test_scanner_ignores_category_directories(tmp_path: Path) -> None:
    category = tmp_path / "cars" / "v8supercars"
    (category / "ford2014").mkdir(parents=True)
    (category / "holden2014").mkdir()
    (category / "ford2014" / "ford2014.dat").write_bytes(b"data")
    (category / "holden2014" / "holden2014.dat").write_bytes(b"data")
    (category / "v8supercars.dat").write_bytes(b"group")

    packages = scan_iracing_car_packages(tmp_path)

    assert [package.relative_path for package in packages] == ["v8supercars/ford2014", "v8supercars/holden2014"]


def test_scanner_reports_missing_csv_and_images(tmp_path: Path) -> None:
    package = tmp_path / "cars" / "v8supercars" / "ford2014"
    package.mkdir(parents=True)
    (package / "ford2014.dat").write_bytes(b"data")
    csv_path = tmp_path / "Cars.csv"
    csv_path.write_text("Game,FILEPATH,image file\niRacing,\\v8supercars\\ford2014,Missing\n", encoding="utf-8")

    report = compare_iracing_car_images(tmp_path, tmp_path / "assets", csv_path)

    assert report["installed_count"] == 1
    assert report["missing_csv_entries"] == []
    assert len(report["missing_images"]) == 1
