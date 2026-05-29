from __future__ import annotations

from pathlib import Path

from PIL import Image
from rembg import new_session, remove


ROOT = Path(__file__).resolve().parents[1] / "src" / "circuit_stackers" / "assets" / "Cars" / "Iracing"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def process_image(path: Path, session) -> Path:
    base_name = path.stem if path.suffix.casefold() in IMAGE_EXTENSIONS else path.name
    output = path.with_name(f"{base_name}_cutout.png")
    source = Image.open(path).convert("RGBA")
    cutout = remove(source, session=session)
    output.parent.mkdir(parents=True, exist_ok=True)
    cutout.save(output)
    return output


def _is_supported_source_image(path: Path) -> bool:
    if path.suffix.casefold() in IMAGE_EXTENSIONS:
        return True
    try:
        with Image.open(path) as image:
            return image.format in {"JPEG", "PNG", "WEBP"}
    except Exception:
        return False


def main() -> None:
    paths = [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and _is_supported_source_image(path)
        and not path.stem.endswith("_cutout")
        and not path.stem.endswith("_cutout_preview")
    ]
    session = new_session("u2net")
    for index, path in enumerate(paths, start=1):
        output = process_image(path, session)
        print(f"{index:03d}/{len(paths):03d} {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
