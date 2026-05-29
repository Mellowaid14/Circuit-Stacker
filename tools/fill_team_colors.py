from __future__ import annotations

import colorsys
import csv
import hashlib
import re
import shutil
from pathlib import Path


WORKING_CSV = Path(r"C:\Users\hfaur\Downloads\CS- Working Doc - Teams (1).csv")
DATA_CSV = Path(__file__).resolve().parents[1] / "src" / "circuit_stackers" / "data" / "Teams.csv"


REAL_WORLD_COLORS = {
    "Richard Childress Racing": ("CE1126", "000000", "FFFFFF"),
    "Rick Ware Racing": ("000000", "FFFFFF", "D71920"),
    "Spire Motorsports": ("003DA5", "00A651", "FFFFFF"),
    "Team Penske": ("ED1C24", "FFFFFF", "002D72"),
    "Trackhouse Racing": ("0057B8", "E31B23", "101820"),
    "Wood Brothers Racing": ("D71920", "FFFFFF", "B9975B"),
    "23XI": ("000000", "00A3E0", "6F2DA8"),
    "Front Row Motorsports": ("0057B8", "E31B23", "FFFFFF"),
    "Haas": ("000000", "E6002D", "FFFFFF"),
    "Hendrick Motorsports": ("003DA5", "E31837", "FFFFFF"),
    "Joe Gibbs Racing": ("CE1126", "000000", "FFFFFF"),
    "Kaulig Racing": ("00A651", "000000", "FFFFFF"),
    "Legacy Motor Club": ("000000", "C8A951", "00A3E0"),
    "RFK Racing": ("001F5B", "D71920", "FFFFFF"),
    "Alpine": ("00A1E8", "FF87BC", "061A4D"),
    "Aston Martin": ("229971", "000000", "FFFFFF"),
    "Audi": ("E00000", "000000", "C0C0C0"),
    "Cadillac": ("D4AF37", "000000", "B31B1B"),
    "Ferrari": ("ED1131", "000000", "FFFFFF"),
    "Haas F1 Team": ("B6BABD", "E6002D", "000000"),
    "McLaren": ("FF8000", "000000", "FFFFFF"),
    "Mercedes": ("00D2BE", "000000", "C0C0C0"),
    "Racing Bulls": ("6C98FF", "070B36", "FFFFFF"),
    "Red Bull Racing": ("3671C6", "DB0A40", "FFCC00"),
    "Williams": ("00A3E0", "001489", "FFFFFF"),
}


COLOR_WORDS = {
    "black": "050505",
    "white": "FFFFFF",
    "red": "D71920",
    "blue": "0057B8",
    "green": "009B77",
    "yellow": "FFD100",
    "gold": "D4AF37",
    "silver": "C0C0C0",
    "gray": "6D6E71",
    "grey": "6D6E71",
    "orange": "FF6A00",
    "purple": "5B2C83",
    "violet": "6F2DA8",
    "pink": "FF4FA3",
    "teal": "00A3AD",
    "cyan": "00AEEF",
    "aqua": "00AEEF",
    "lime": "78BE20",
    "bronze": "A97142",
    "crimson": "9E1B32",
    "scarlet": "BB1E10",
    "maroon": "800020",
    "navy": "001F5B",
    "azure": "007FFF",
    "jade": "00A86B",
    "emerald": "009B77",
    "sapphire": "0F52BA",
    "ruby": "9B111E",
    "amber": "FFBF00",
    "copper": "B87333",
}


KEYWORD_PALETTES = {
    "phoenix": ("FF6A00", "D71920", "111111"),
    "eclipse": ("111111", "6D6E71", "FFD100"),
    "thunder": ("2D2F7F", "FFD100", "FFFFFF"),
    "storm": ("243B53", "00AEEF", "C0C0C0"),
    "shadow": ("111111", "3A3A3A", "8A8F98"),
    "velocity": ("0057B8", "FF6A00", "FFFFFF"),
    "vortex": ("4B0082", "00AEEF", "FFFFFF"),
    "apex": ("ED1C24", "111111", "FFFFFF"),
    "summit": ("0B6623", "C0C0C0", "FFFFFF"),
    "titan": ("2F3A4A", "D4AF37", "FFFFFF"),
    "falcon": ("003DA5", "C0C0C0", "FFFFFF"),
    "eagle": ("002D72", "D71920", "FFFFFF"),
    "wolf": ("3A3A3A", "C0C0C0", "111111"),
    "dragon": ("D71920", "FF6A00", "111111"),
    "tiger": ("FF6A00", "111111", "FFFFFF"),
    "lion": ("D4AF37", "111111", "FFFFFF"),
    "cobra": ("009B77", "111111", "FFFFFF"),
    "panther": ("111111", "5B2C83", "C0C0C0"),
    "shark": ("0057B8", "C0C0C0", "FFFFFF"),
    "rocket": ("D71920", "0057B8", "FFFFFF"),
    "nova": ("6F2DA8", "00AEEF", "FFFFFF"),
    "solar": ("FFD100", "FF6A00", "111111"),
    "lunar": ("1B1F3B", "C0C0C0", "FFFFFF"),
    "heritage": ("002D72", "B9975B", "FFFFFF"),
    "racing": ("ED1C24", "111111", "FFFFFF"),
    "motorsport": ("0057B8", "111111", "FFFFFF"),
    "autosport": ("0057B8", "C0C0C0", "FFFFFF"),
}


ACCENTS = [
    "ED1C24",
    "0057B8",
    "FF6A00",
    "009B77",
    "6F2DA8",
    "00AEEF",
    "D4AF37",
    "FF4FA3",
    "78BE20",
    "B87333",
    "2D2F7F",
    "9B111E",
]


def clean_hex(value: str) -> str:
    value = str(value).strip().upper().lstrip("#")
    return value if re.fullmatch(r"[0-9A-F]{6}", value) else ""


def stable_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def shift_color(hex_color: str, amount: float) -> str:
    red = int(hex_color[0:2], 16) / 255
    green = int(hex_color[2:4], 16) / 255
    blue = int(hex_color[4:6], 16) / 255
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    lightness = max(0.16, min(0.82, lightness + amount))
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def color_word_palette(name: str) -> tuple[str, str, str] | None:
    normalized = re.sub(r"[^a-z]+", "", name.casefold())
    words = re.findall(r"[a-z]+", name.casefold())
    found = [COLOR_WORDS[word] for word in words if word in COLOR_WORDS]
    if not found:
        found = [
            color
            for word, color in sorted(COLOR_WORDS.items(), key=lambda item: len(item[0]), reverse=True)
            if word in normalized
        ]
    if not found:
        return None
    primary = found[0]
    secondary = found[1] if len(found) > 1 else ("111111" if primary != "111111" else "FFFFFF")
    tertiary = "FFFFFF" if primary not in {"FFFFFF", "FFD100", "C0C0C0"} else "111111"
    if tertiary == secondary:
        tertiary = "0057B8" if primary in {"FFFFFF", "C0C0C0"} else "FFFFFF"
    return primary, secondary, tertiary


def keyword_palette(name: str) -> tuple[str, str, str] | None:
    normalized = name.casefold()
    for keyword, palette in KEYWORD_PALETTES.items():
        if keyword in normalized:
            return palette
    return None


def generated_palette(row: dict[str, str]) -> tuple[str, str, str]:
    name = row.get("Team", "")
    explicit = color_word_palette(name)
    if explicit:
        return explicit
    keyword = keyword_palette(name)
    if keyword:
        return keyword

    seed = stable_int(f"{row.get('Team_ID', '')}|{name}|{row.get('Base_Style', '')}")
    primary = ACCENTS[seed % len(ACCENTS)]
    style = row.get("Base_Style", "").casefold()
    if style == "oval":
        secondary = "111111" if seed % 2 else "FFFFFF"
        tertiary = "FFFFFF" if secondary == "111111" else "111111"
    elif style == "open wheel":
        secondary = shift_color(primary, -0.18)
        tertiary = "FFFFFF"
    elif style == "rallycross":
        secondary = "111111"
        tertiary = shift_color(primary, 0.20)
    else:
        secondary = "1F2933"
        tertiary = "FFFFFF"
    return primary, secondary, tertiary


def fill_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in rows:
        team_name = row.get("Team", "").strip()
        colors = REAL_WORLD_COLORS.get(team_name) or generated_palette(row)
        row["Color 1"], row["Color 2"], row["Color 3"] = [clean_hex(color) for color in colors]
    return rows


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as file_obj:
        reader = csv.DictReader(file_obj)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    for color_header in ("Color 1", "Color 2", "Color 3"):
        if color_header not in fieldnames:
            fieldnames.append(color_header)
    return fieldnames, rows


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not WORKING_CSV.exists():
        raise FileNotFoundError(WORKING_CSV)
    fieldnames, rows = read_rows(WORKING_CSV)
    rows = fill_rows(rows)
    write_rows(WORKING_CSV, fieldnames, rows)
    shutil.copyfile(WORKING_CSV, DATA_CSV)
    print(f"Updated {len(rows)} teams in {WORKING_CSV}")
    print(f"Copied updated teams to {DATA_CSV}")


if __name__ == "__main__":
    main()
