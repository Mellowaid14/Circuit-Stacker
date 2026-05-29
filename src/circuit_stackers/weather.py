from __future__ import annotations

import random


AMS2_CLEAR = "Clear"
AMS2_LIGHT_CLOUD = "Light Cloud"
AMS2_MEDIUM_CLOUD = "Medium Cloud"
AMS2_HEAVY_CLOUD = "Heavy Cloud"
AMS2_OVERCAST = "Overcast"
AMS2_LIGHT_RAIN = "Light Rain"
AMS2_RAIN = "Rain"
AMS2_STORM = "Storm"
AMS2_THUNDERSTORM = "Thunderstorm"
AMS2_HEAVY_FOG = "Heavy Fog"
AMS2_HEAVY_FOG_AND_RAIN = "Heavy Fog and Rain"
AMS2_HAZY = "Hazy"

AMS2_WEATHER_NAMES = {
    AMS2_CLEAR,
    AMS2_LIGHT_CLOUD,
    AMS2_MEDIUM_CLOUD,
    AMS2_HEAVY_CLOUD,
    AMS2_OVERCAST,
    AMS2_LIGHT_RAIN,
    AMS2_RAIN,
    AMS2_STORM,
    AMS2_THUNDERSTORM,
    AMS2_HEAVY_FOG,
    AMS2_HEAVY_FOG_AND_RAIN,
    AMS2_HAZY,
}


def generate_ams2_weather(style: str = "") -> str:
    normalized_style = str(style).strip().casefold()
    rain_chance = 0.012 if normalized_style in {"oval", "rallycross"} else 0.025
    fog_chance = 0.045
    roll = random.random()

    if roll < rain_chance:
        return " | ".join(_trim_weather_slots(_wet_ams2_weather_blocks()))
    if roll < rain_chance + fog_chance:
        return " | ".join(_trim_weather_slots(random.choice(_foggy_ams2_weather_patterns())))
    return " | ".join(_trim_weather_slots(random.choice(_dry_ams2_weather_patterns())))


def parse_weather_slots(weather: str, *, expand_ams2_legacy: bool = False) -> list[str]:
    raw_weather = str(weather or "").strip()
    if not raw_weather:
        return []
    slots = [slot.strip() for slot in raw_weather.split("|") if slot.strip()]
    if not expand_ams2_legacy:
        return slots
    if len(slots) == 1 and slots[0] == "Cloudy":
        return [AMS2_LIGHT_CLOUD, AMS2_MEDIUM_CLOUD, AMS2_LIGHT_CLOUD, AMS2_CLEAR]
    if len(slots) == 1 and slots[0] == "Sunny":
        return [AMS2_CLEAR]
    if len(slots) == 1 and slots[0] == "Overcast":
        return [AMS2_OVERCAST, AMS2_HEAVY_CLOUD, AMS2_OVERCAST, AMS2_HEAVY_CLOUD]
    if len(slots) == 1 and slots[0] == "Foggy":
        return [AMS2_HEAVY_FOG, AMS2_HAZY, AMS2_LIGHT_CLOUD, AMS2_CLEAR]
    if len(slots) == 1 and slots[0] == "Light Rain":
        return [AMS2_OVERCAST, AMS2_LIGHT_RAIN, AMS2_MEDIUM_CLOUD, AMS2_LIGHT_CLOUD]
    if len(slots) == 1 and slots[0] == "Heavy Rain":
        return [AMS2_OVERCAST, AMS2_RAIN, AMS2_STORM, AMS2_HEAVY_CLOUD]
    return slots


def display_weather(weather: str, *, expand_ams2_legacy: bool = False) -> str:
    slots = parse_weather_slots(weather, expand_ams2_legacy=expand_ams2_legacy)
    if len(slots) <= 1:
        return slots[0] if slots else "-"
    return f"{len(slots)} " + " | ".join(slots)


def weather_timeline_text(weather: str, *, expand_ams2_legacy: bool = False) -> str:
    slots = parse_weather_slots(weather, expand_ams2_legacy=expand_ams2_legacy)
    if not slots:
        return "-"
    if len(slots) == 1:
        return f"Use one weather slot: {slots[0]}"
    return " | ".join(f"Slot {index + 1}: {slot}" for index, slot in enumerate(slots))


def _dry_ams2_weather_patterns() -> list[list[str]]:
    return [
        [AMS2_CLEAR, AMS2_LIGHT_CLOUD, AMS2_CLEAR, AMS2_LIGHT_CLOUD],
        [AMS2_CLEAR, AMS2_CLEAR, AMS2_LIGHT_CLOUD, AMS2_CLEAR],
        [AMS2_LIGHT_CLOUD, AMS2_CLEAR, AMS2_LIGHT_CLOUD, AMS2_CLEAR],
        [AMS2_LIGHT_CLOUD, AMS2_MEDIUM_CLOUD, AMS2_LIGHT_CLOUD, AMS2_CLEAR],
        [AMS2_MEDIUM_CLOUD, AMS2_LIGHT_CLOUD, AMS2_CLEAR, AMS2_LIGHT_CLOUD],
        [AMS2_MEDIUM_CLOUD, AMS2_HEAVY_CLOUD, AMS2_MEDIUM_CLOUD, AMS2_LIGHT_CLOUD],
        [AMS2_HEAVY_CLOUD, AMS2_MEDIUM_CLOUD, AMS2_HEAVY_CLOUD, AMS2_OVERCAST],
        [AMS2_OVERCAST, AMS2_HEAVY_CLOUD, AMS2_MEDIUM_CLOUD, AMS2_HEAVY_CLOUD],
    ]


def _foggy_ams2_weather_patterns() -> list[list[str]]:
    return [
        [AMS2_HAZY, AMS2_LIGHT_CLOUD, AMS2_CLEAR, AMS2_LIGHT_CLOUD],
        [AMS2_HEAVY_FOG, AMS2_HAZY, AMS2_LIGHT_CLOUD, AMS2_CLEAR],
        [AMS2_HAZY, AMS2_MEDIUM_CLOUD, AMS2_LIGHT_CLOUD, AMS2_CLEAR],
    ]


def _wet_ams2_weather_blocks() -> list[str]:
    wet_patterns = [
        [AMS2_OVERCAST, AMS2_LIGHT_RAIN, AMS2_MEDIUM_CLOUD, AMS2_LIGHT_CLOUD],
        [AMS2_HEAVY_CLOUD, AMS2_LIGHT_RAIN, AMS2_LIGHT_RAIN, AMS2_OVERCAST],
        [AMS2_OVERCAST, AMS2_RAIN, AMS2_LIGHT_RAIN, AMS2_HEAVY_CLOUD],
        [AMS2_HEAVY_FOG, AMS2_HEAVY_FOG_AND_RAIN, AMS2_LIGHT_RAIN, AMS2_HAZY],
        [AMS2_OVERCAST, AMS2_STORM, AMS2_RAIN, AMS2_HEAVY_CLOUD],
        [AMS2_HEAVY_CLOUD, AMS2_THUNDERSTORM, AMS2_RAIN, AMS2_OVERCAST],
    ]
    return random.choices(wet_patterns, weights=[35, 25, 20, 10, 7, 3], k=1)[0]


def _trim_weather_slots(slots: list[str]) -> list[str]:
    if not slots:
        return [AMS2_CLEAR]
    slot_count = random.choices([1, 2, 3, 4], weights=[30, 35, 25, 10], k=1)[0]
    return slots[:slot_count]
