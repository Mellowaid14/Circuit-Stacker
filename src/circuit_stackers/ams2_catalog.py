"""Read AMS2 class membership from the public car catalog."""

from __future__ import annotations

import re
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.parse import quote

from .ams2_content_scanner import PackedVehicle, scan_packed_vehicles
from .paths import user_data_dir


CATALOG_URL = "https://www.automobilista.gg/classes"
WIKI_BASE_URL = "https://automobilista2.wiki.gg/wiki/"
WIKI_CARS_URL = WIKI_BASE_URL + "AMS2_Cars"
CATALOG_CACHE_PATH = user_data_dir() / "ams2_catalog_cache.json"
_KNOWN_PACKAGE_ALIASES = {
    "passatclassicb": "Pas_ClassicB",
    "copafusca": "Fusca_Copa",
    "dallaraf301": "F301",
    "lotusrenault98t": "Lotus_98T",
    "audir8lmsgt3evoii": "Audi_R8_LMS_GT3_Evo2",
    "astonmartinvantagegt3evo": "Aston_Martin_Vantage_GT3_Evo",
    "chevroletcorvettez06gt3r": "Chevrolet_Corvette_Z06_GT3R",
    "lamborghinihuracangt3evo2": "Lamborghini_Huracan_GT3_Evo2",
    "mclaren720sgt3evo": "McLaren_720S_GT3_Evo",
    "mercedesamggt3evo": "Mercedes_AMG_GT3_Evo",
    "porsche992gt3r": "Porsche_992_GT3R",
}


class _CatalogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_class = ""
        self.text_parts: list[str] = []
        self.classes: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2"}:
            self.text_parts = []

    def handle_endtag(self, tag: str) -> None:
        text = " ".join(self.text_parts).strip()
        self.text_parts = []
        if not text:
            return
        if self.current_class and text.startswith("Car "):
            self.classes.setdefault(self.current_class, []).append(text.removeprefix("Car ").strip())
        elif tag in {"h1", "h2"} and text not in {"Cars", "Browse Cars"}:
            self.current_class = text

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.text_parts.append(cleaned)


class _WikiTableParser(HTMLParser):
    """Collect table rows from the Wiki's consolidated car-list page."""

    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self._row = []
        elif tag in {"th", "td"} and self.in_row:
            self.in_cell = True
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self.in_cell:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self._row:
                self.rows.append(self._row)
            self.in_row = False
        elif tag == "table":
            self.in_table = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self._cell.append(data)


@dataclass(frozen=True)
class CatalogCarMatch:
    car_name: str
    class_name: str
    package_name: str = ""
    candidates: tuple[str, ...] = ()


def wiki_car_url(car_name: str) -> str:
    """Build the public wiki page URL for a display-name car."""
    title = re.sub(r"\s+", "_", car_name.strip())
    return WIKI_BASE_URL + quote(title, safe="_()/")


def parse_wiki_car_features(html: str) -> dict[str, object]:
    """Extract stable feature flags from a rendered AMS2 Wiki car page.

    The wiki uses a human-readable table rather than a documented API schema.
    We intentionally keep this parser narrow: missing or changed fields simply
    remain absent and never get interpreted as a negative capability.
    """
    visible = unescape(re.sub(r"<[^>]+>", " ", html))
    visible = " ".join(visible.split())
    feature_labels = {
        "Headlights": "headlights",
        "Traction Control": "traction_control",
        "Anti-Lock Brakes": "anti_lock_brakes",
        "Tyre Blankets": "tyre_blankets",
        "Energy Recovery System": "energy_recovery_system",
        "Boost/Push-to-Pass": "boost_push_to_pass",
        "Active Aero/DRS": "active_aero_drs",
        "Boost Adjustment": "boost_adjustment",
    }
    features: dict[str, str] = {}
    for label, key in feature_labels.items():
        match = re.search(rf"{re.escape(label)}\s+(Yes|No)\b", visible, re.IGNORECASE)
        if match:
            features[key] = match.group(1).casefold() == "yes"
    return features


def fetch_wiki_car_features(car_name: str, timeout: float = 15.0) -> dict[str, object]:
    request = Request(wiki_car_url(car_name), headers={"User-Agent": "CircuitStackers AMS2 metadata updater"})
    with urlopen(request, timeout=timeout) as response:
        return parse_wiki_car_features(response.read().decode("utf-8", errors="replace"))


def fetch_wiki_features(car_names: list[str], timeout: float = 15.0) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Fetch feature flags opportunistically; return successful and failed pages."""
    features: dict[str, dict[str, object]] = {}
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_wiki_car_features, name, timeout): name for name in car_names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                parsed = future.result()
            except Exception:
                failed.append(name)
                continue
            if parsed:
                features[name] = parsed
    return features, failed


def fetch_catalog_html(url: str = CATALOG_URL, timeout: float = 15.0) -> str:
    request = Request(url, headers={"User-Agent": "CircuitStackers AMS2 metadata updater"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_wiki_catalog_html(timeout: float = 15.0) -> str:
    return fetch_catalog_html(WIKI_CARS_URL, timeout)


def parse_wiki_class_catalog(html: str) -> dict[str, list[str]]:
    """Parse the Wiki consolidated car table into class -> car membership."""
    parser = _WikiTableParser()
    parser.feed(html)
    for rows in (parser.rows,):
        header_index = next(
            (index for index, row in enumerate(rows) if any("car class" in cell.casefold() for cell in row)),
            None,
        )
        if header_index is None:
            continue
        header = [cell.casefold() for cell in rows[header_index]]
        class_index = next(index for index, cell in enumerate(header) if "car class" in cell)
        car_index = next((index for index, cell in enumerate(header) if cell in {"car", "cars", "vehicle"}), 0)
        catalog: dict[str, list[str]] = {}
        for row in rows[header_index + 1 :]:
            if len(row) <= max(class_index, car_index):
                continue
            car_name = row[car_index].strip()
            class_name = row[class_index].strip()
            if car_name and class_name and car_name.casefold() not in {"car", "cars"}:
                catalog.setdefault(class_name, []).append(car_name)
        if catalog:
            return {name: list(dict.fromkeys(cars)) for name, cars in catalog.items()}
    return {}


def parse_class_catalog(html: str) -> dict[str, list[str]]:
    parser = _CatalogParser()
    parser.feed(html)
    return {name: list(dict.fromkeys(cars)) for name, cars in parser.classes.items() if cars}


def parse_class_page(html: str) -> tuple[str, list[str]]:
    """Parse one catalog class page from its server-rendered HTML."""
    heading = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", html, re.IGNORECASE | re.DOTALL)
    class_name = re.sub(r"<[^>]+>", "", heading.group(1)).strip() if heading else ""
    matches = re.findall(
        r'<span[^>]*class="[^"]*listing-card-label[^"]*"[^>]*>\s*Car\s*</span>\s*'
        r'<span[^>]*>\s*(.*?)\s*</span>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    cars = [re.sub(r"<[^>]+>", "", value).strip() for value in matches]
    return class_name, list(dict.fromkeys(car for car in cars if car))


def fetch_full_catalog(timeout: float = 15.0) -> tuple[dict[str, list[str]], list[str]]:
    """Fetch every class page linked by the catalog index."""
    index = fetch_catalog_html(timeout=timeout)
    slugs = list(dict.fromkeys(re.findall(r'href="/classes/([a-z0-9-]+)"', index, re.IGNORECASE)))
    catalog: dict[str, list[str]] = {}
    failed: list[str] = []

    def fetch_class(slug: str) -> tuple[str, str, list[str]]:
        class_name, cars = parse_class_page(fetch_catalog_html(f"{CATALOG_URL}/{slug}", timeout))
        return slug, class_name, cars

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_class, slug) for slug in slugs]
        for future in as_completed(futures):
            try:
                slug, class_name, cars = future.result()
            except Exception as exc:  # Network failures should not discard the successful pages.
                failed.append(str(exc))
                continue
            if class_name and cars:
                catalog[class_name] = cars
            else:
                failed.append(slug)
    return catalog, failed


def load_cached_catalog(path: Path = CATALOG_CACHE_PATH) -> tuple[dict[str, list[str]], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        catalog = data.get("classes", {})
        if isinstance(catalog, dict) and catalog:
            return {str(name): [str(car) for car in cars] for name, cars in catalog.items()}, str(data.get("source", "cache"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}, ""


def save_cached_catalog(catalog: dict[str, list[str]], path: Path = CATALOG_CACHE_PATH, source: str = CATALOG_URL) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"source": source, "classes": catalog}, indent=2), encoding="utf-8")
    except OSError:
        # Cache failure must never make a valid live catalog unusable.
        return


def fetch_catalog_with_cache(timeout: float = 15.0) -> tuple[dict[str, list[str]], list[str], str]:
    try:
        wiki_catalog = parse_wiki_class_catalog(fetch_wiki_catalog_html(timeout))
        if wiki_catalog:
            save_cached_catalog(wiki_catalog, source=WIKI_CARS_URL)
            return wiki_catalog, [], "wiki-live"
    except Exception as wiki_error:
        wiki_failure = str(wiki_error)
    else:
        wiki_failure = "Wiki page contained no parseable car table"
    try:
        catalog, failed = fetch_full_catalog(timeout)
        if catalog and not failed:
            save_cached_catalog(catalog, source=CATALOG_URL)
            return catalog, [], "live"
        cached, source = load_cached_catalog()
        return (cached or catalog), failed + [wiki_failure], source or "partial-live"
    except Exception as exc:
        cached, source = load_cached_catalog()
        return cached, [str(exc), wiki_failure], source or "unavailable"


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold().replace("ii", "2").replace("iii", "3"))


def match_catalog_to_packages(catalog: dict[str, list[str]], packages: list[PackedVehicle]) -> list[CatalogCarMatch]:
    package_names = [item.package_name for item in packages]
    by_key = {_compact(name): name for name in package_names}
    results: list[CatalogCarMatch] = []
    for class_name, car_names in catalog.items():
        for car_name in car_names:
            exact = by_key.get(_compact(car_name)) or _KNOWN_PACKAGE_ALIASES.get(_compact(car_name))
            if exact not in package_names:
                exact = None
            if exact:
                results.append(CatalogCarMatch(car_name, class_name, exact))
                continue
            candidates = tuple(
                sorted(package_names, key=lambda name: SequenceMatcher(None, _compact(car_name), _compact(name)).ratio(), reverse=True)[:3]
            )
            results.append(CatalogCarMatch(car_name, class_name, candidates=candidates))
    return results


def build_catalog_report(install_root: Path | None, html: str) -> dict[str, object]:
    return build_catalog_report_from_catalog(install_root, parse_class_catalog(html))


def build_catalog_report_from_catalog(install_root: Path | None, catalog: dict[str, list[str]]) -> dict[str, object]:
    matches = match_catalog_to_packages(catalog, scan_packed_vehicles(install_root))
    return {
        "source": CATALOG_URL,
        "classes": catalog,
        "matches": [asdict(item) for item in matches],
        "matched_count": sum(bool(item.package_name) for item in matches),
        "unmatched_count": sum(not item.package_name for item in matches),
    }


def build_canonical_metadata(
    install_root: Path | None,
    catalog: dict[str, list[str]],
    wiki_features: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    matches = match_catalog_to_packages(catalog, scan_packed_vehicles(install_root))
    wiki_features = wiki_features or {}
    cars = [
        {
            "class_name": item.class_name,
            "car_name": item.car_name,
            "package_name": item.package_name,
            "livery_ids": [],
            "livery_ids_available": False,
            "features": wiki_features.get(item.car_name, {}),
            "features_source": wiki_car_url(item.car_name) if item.car_name in wiki_features else "",
        }
        for item in matches
        if item.package_name
    ]
    return {
        "schema_version": 1,
        "source": CATALOG_URL,
        "features_source": WIKI_BASE_URL,
        "livery_id_source": "optional-runtime-capture",
        "cars": cars,
    }


def update_metadata_files(install_root: Path | None, output_dir: Path) -> tuple[Path, Path, str, int]:
    """Refresh the catalog cache and write the review and canonical files."""
    catalog, failed_pages, source = fetch_catalog_with_cache()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "ams2_catalog_report.json"
    metadata_path = output_dir / "ams2_metadata.json"
    if not catalog:
        return report_path, metadata_path, source or "unavailable", len(failed_pages)
    report = build_catalog_report_from_catalog(install_root, catalog)
    report.update({"failed_pages": failed_pages, "catalog_source": source})
    matched_names = [item.car_name for item in match_catalog_to_packages(catalog, scan_packed_vehicles(install_root)) if item.package_name]
    wiki_features, failed_features = fetch_wiki_features(matched_names)
    report.update({"feature_source": WIKI_BASE_URL, "failed_feature_pages": failed_features})
    metadata = build_canonical_metadata(install_root, catalog, wiki_features)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return report_path, metadata_path, source, len(failed_pages)
