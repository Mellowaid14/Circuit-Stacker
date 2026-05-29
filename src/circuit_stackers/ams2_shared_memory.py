from __future__ import annotations

import ctypes
import socket
import struct
import time
from dataclasses import dataclass


FILE_MAP_READ = 0x0004
SHARED_MEMORY_NAMES = ("$pcars2$", "Local\\$pcars2$")
READ_SIZES = (64 * 1024, 32 * 1024, 16 * 1024)
STORED_PARTICIPANTS_MAX = 64
SHARED_MEMORY_HEADER_SIZE = 28
PARTICIPANT_INFO_SIZE = 100
PARTICIPANT_ACTIVE_OFFSET = 0
PARTICIPANT_NAME_OFFSET = 1
PARTICIPANT_NAME_LENGTH = 64
PARTICIPANT_WORLD_POSITION_OFFSET = 68
PARTICIPANT_LAP_DISTANCE_OFFSET = 80
PARTICIPANT_RACE_POSITION_OFFSET = 84
PARTICIPANT_LAPS_COMPLETED_OFFSET = 88
PARTICIPANT_CURRENT_LAP_OFFSET = 92
PARTICIPANT_CURRENT_SECTOR_OFFSET = 96
SESSION_STATE_OFFSET = 12
RACE_STATE_OFFSET = 16
VIEWED_PARTICIPANT_INDEX_OFFSET = 20
LAPS_IN_EVENT_OFFSET = 6572
TRACK_LENGTH_OFFSET = 6704
CURRENT_TIME_OFFSET = 6724
EVENT_TIME_REMAINING_OFFSET = 6740
CURRENT_SECTOR1_TIMES_OFFSET = 7408
CURRENT_SECTOR2_TIMES_OFFSET = 7664
CURRENT_SECTOR3_TIMES_OFFSET = 7920
FASTEST_LAP_TIMES_OFFSET = 8944
LAST_LAP_TIMES_OFFSET = 9200
SPEEDS_OFFSET = 10800
SESSION_DURATION_OFFSET = 20576
NUM_PARTICIPANTS_OFFSET = 24
AMS2_UDP_PORT = 5606
UDP_PACKET_TYPE_PARTICIPANTS = 2
UDP_PACKET_TYPE_TIMINGS = 3
UDP_PARTICIPANTS_PER_PACKET = 16
UDP_PARTICIPANT_NAME_LENGTH = 64
UDP_TIMINGS_PARTICIPANTS_MAX = 32
UDP_TIMING_PARTICIPANT_OFFSET = 33
UDP_TIMING_PARTICIPANT_SIZE = 32
UDP_TIMING_LAP_DISTANCE_OFFSET = 12
UDP_TIMING_RACE_POSITION_OFFSET = 14
UDP_TIMING_CURRENT_LAP_OFFSET = 21
UDP_TIMING_CURRENT_TIME_OFFSET = 22
UDP_TIMING_MP_INDEX_OFFSET = 30
_UDP_SOCKET: socket.socket | None = None
_UDP_NAME_BY_INDEX: dict[int, str] = {}
_UDP_TIMING_BY_NAME: dict[str, "Ams2TimingInfo"] = {}
_UDP_LAST_PACKET_AT = 0.0

SESSION_NAMES = {
    0: "Invalid",
    1: "Practice",
    2: "Test",
    3: "Qualifying",
    4: "Formation Lap",
    5: "Race",
    6: "Time Attack",
}


@dataclass(frozen=True)
class Ams2SyncStatus:
    available: bool
    all_found: bool
    found: list[str]
    missing: list[str]
    message: str
    expected_count: int = 0
    packet_count: int = 0


@dataclass(frozen=True)
class Ams2LiveParticipant:
    name: str
    position: int
    is_active: bool
    current_time: float = 0.0
    current_sector_time: float = 0.0
    lap_distance: float = 0.0
    laps_completed: int = 0
    current_lap: int = 0
    speed: float = 0.0
    fastest_lap_time: float = 0.0
    last_lap_time: float = 0.0


@dataclass(frozen=True)
class Ams2LiveSnapshot:
    participants: list[Ams2LiveParticipant]
    session_state: int
    session_name: str
    event_time_remaining: float = 0.0
    laps_in_event: int = 0
    track_length: float = 0.0
    session_duration_minutes: float = 0.0


@dataclass(frozen=True)
class Ams2TimingInfo:
    name: str
    position: int
    lap_distance: float
    current_lap: int
    current_time: float
    is_active: bool


def check_ams2_driver_sync(expected_driver_names: list[str]) -> Ams2SyncStatus:
    expected = _unique_clean_names(expected_driver_names)
    if not expected:
        return Ams2SyncStatus(False, False, [], [], "No AMS2 drivers are available to check.", 0, 0)

    memory_name, data, error = _read_shared_memory()
    if not data:
        message = (
            "AMS2 shared memory detected: No\n"
            f"Maps checked: {', '.join(SHARED_MEMORY_NAMES)}\n"
            f"Drivers found: 0 / {len(expected)}"
        )
        if error:
            message = f"{message}\nLast error: {error}"
        return Ams2SyncStatus(False, False, [], expected, message, len(expected), 0)

    decoded_names = _extract_printable_names(data)
    raw_matches = _raw_name_matches(expected, data)
    decoded_matches = {
        name
        for name in expected
        if any(_clean_name(decoded).casefold() == name.casefold() for decoded in decoded_names)
    }
    found = [name for name in expected if name in raw_matches or name in decoded_matches]
    missing = [name for name in expected if name not in found]
    all_found = not missing

    message = "\n".join(
        [
            "AMS2 shared memory detected: Yes",
            f"Map: {memory_name}",
            f"Names decoded: {_format_decoded_names(decoded_names)}",
            f"Drivers found: {len(found)} / {len(expected)}",
            f"Missing: {_format_missing_names(missing)}",
        ]
    )
    return Ams2SyncStatus(True, all_found, found, missing, message, len(expected), 1)


def read_ams2_live_order() -> tuple[list[Ams2LiveParticipant], str]:
    snapshot, error = read_ams2_live_snapshot()
    if error:
        return [], error
    return snapshot.participants, ""


def read_ams2_live_snapshot() -> tuple[Ams2LiveSnapshot, str]:
    _drain_udp_packets()
    _memory_name, data, error = _read_shared_memory()
    if not data:
        return Ams2LiveSnapshot([], 0, "Invalid"), f"AMS2 shared memory unavailable: {error or 'not found'}"

    participants: list[Ams2LiveParticipant] = []
    session_state = _read_uint32(data, SESSION_STATE_OFFSET)
    session_name = SESSION_NAMES.get(session_state, f"Unknown {session_state}")
    laps_in_event = _read_int32(data, LAPS_IN_EVENT_OFFSET)
    track_length = _read_float32(data, TRACK_LENGTH_OFFSET)
    player_current_time = _read_float32(data, CURRENT_TIME_OFFSET)
    session_duration_minutes = _read_float32(data, SESSION_DURATION_OFFSET)
    event_time_remaining = _normal_event_time_remaining(
        _read_float32(data, EVENT_TIME_REMAINING_OFFSET),
        session_duration_minutes,
    )
    viewed_participant_index = _read_int32(data, VIEWED_PARTICIPANT_INDEX_OFFSET)
    num_participants = _read_int32(data, NUM_PARTICIPANTS_OFFSET)
    if num_participants <= 0:
        return (
            Ams2LiveSnapshot(
                [],
                session_state,
                session_name,
                event_time_remaining,
                laps_in_event,
                track_length,
                session_duration_minutes,
            ),
            "AMS2 shared memory has no active participants.",
        )

    count = min(num_participants, STORED_PARTICIPANTS_MAX)
    for index in range(count):
        offset = SHARED_MEMORY_HEADER_SIZE + (index * PARTICIPANT_INFO_SIZE)
        if len(data) < offset + PARTICIPANT_INFO_SIZE:
            break
        is_active = data[offset + PARTICIPANT_ACTIVE_OFFSET] != 0
        name = _decode_c_string(data[offset + PARTICIPANT_NAME_OFFSET : offset + PARTICIPANT_NAME_OFFSET + PARTICIPANT_NAME_LENGTH])
        current_time = player_current_time if index == viewed_participant_index else 0.0
        current_sector_time = (
            _read_float32(data, CURRENT_SECTOR1_TIMES_OFFSET + (index * 4))
            + _read_float32(data, CURRENT_SECTOR2_TIMES_OFFSET + (index * 4))
            + _read_float32(data, CURRENT_SECTOR3_TIMES_OFFSET + (index * 4))
        )
        lap_distance = _read_float32(data, offset + PARTICIPANT_LAP_DISTANCE_OFFSET)
        position = _read_uint32(data, offset + PARTICIPANT_RACE_POSITION_OFFSET)
        laps_completed = _read_uint32(data, offset + PARTICIPANT_LAPS_COMPLETED_OFFSET)
        current_lap = _read_uint32(data, offset + PARTICIPANT_CURRENT_LAP_OFFSET)
        speed = _read_float32(data, SPEEDS_OFFSET + (index * 4))
        fastest_lap_time = _read_float32(data, FASTEST_LAP_TIMES_OFFSET + (index * 4))
        last_lap_time = _read_float32(data, LAST_LAP_TIMES_OFFSET + (index * 4))
        if name and position > 0:
            participants.append(
                Ams2LiveParticipant(
                    name=name,
                    position=position,
                    is_active=is_active,
                    current_time=current_time,
                    current_sector_time=current_sector_time,
                    lap_distance=lap_distance,
                    laps_completed=laps_completed,
                    current_lap=current_lap,
                    speed=speed,
                    fastest_lap_time=fastest_lap_time,
                    last_lap_time=last_lap_time,
                )
            )

    if not participants:
        return (
            Ams2LiveSnapshot(
                [],
                session_state,
                session_name,
                event_time_remaining,
                laps_in_event,
                track_length,
                session_duration_minutes,
            ),
            "AMS2 shared memory did not expose participant positions yet.",
        )
    participants.sort(key=lambda participant: participant.position)
    return (
        Ams2LiveSnapshot(
            participants,
            session_state,
            session_name,
            event_time_remaining,
            laps_in_event,
            track_length,
            session_duration_minutes,
        ),
        "",
    )


def ams2_timing_by_name() -> dict[str, Ams2TimingInfo]:
    _drain_udp_packets()
    if time.monotonic() - _UDP_LAST_PACKET_AT > 5:
        return {}
    return dict(_UDP_TIMING_BY_NAME)


def ams2_timing_by_position() -> dict[int, Ams2TimingInfo]:
    _drain_udp_packets()
    if time.monotonic() - _UDP_LAST_PACKET_AT > 5:
        return {}
    return {
        int(timing.position): timing
        for timing in _UDP_TIMING_BY_NAME.values()
        if int(timing.position) > 0
    }


def _drain_udp_packets() -> None:
    udp_socket = _udp_socket()
    if udp_socket is None:
        return
    for _ in range(80):
        try:
            packet, _address = udp_socket.recvfrom(1500)
        except BlockingIOError:
            break
        except OSError:
            break
        _handle_udp_packet(packet)


def _udp_socket() -> socket.socket | None:
    global _UDP_SOCKET
    if _UDP_SOCKET is not None:
        return _UDP_SOCKET
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(("", AMS2_UDP_PORT))
        udp_socket.setblocking(False)
    except OSError:
        return None
    _UDP_SOCKET = udp_socket
    return _UDP_SOCKET


def _handle_udp_packet(packet: bytes) -> None:
    global _UDP_LAST_PACKET_AT
    if len(packet) < 12:
        return
    packet_type = packet[10]
    if packet_type == UDP_PACKET_TYPE_PARTICIPANTS:
        _parse_udp_participants(packet)
        _UDP_LAST_PACKET_AT = time.monotonic()
    elif packet_type == UDP_PACKET_TYPE_TIMINGS:
        _parse_udp_timings(packet)
        _UDP_LAST_PACKET_AT = time.monotonic()


def _parse_udp_participants(packet: bytes) -> None:
    partial_index = packet[8] if len(packet) > 8 else 0
    base_driver_index = int(partial_index) * UDP_PARTICIPANTS_PER_PACKET
    for index in range(UDP_PARTICIPANTS_PER_PACKET):
        name_offset = 16 + (index * UDP_PARTICIPANT_NAME_LENGTH)
        index_offset = 1104 + (index * 2)
        if len(packet) < name_offset + UDP_PARTICIPANT_NAME_LENGTH or len(packet) < index_offset + 2:
            break
        name = _decode_c_string(packet[name_offset : name_offset + UDP_PARTICIPANT_NAME_LENGTH])
        session_index = _read_uint16(packet, index_offset)
        if name:
            _UDP_NAME_BY_INDEX[session_index or (base_driver_index + index)] = name


def _parse_udp_timings(packet: bytes) -> None:
    if len(packet) < UDP_TIMING_PARTICIPANT_OFFSET:
        return
    count = min(max(0, int.from_bytes(packet[12:13], "little", signed=True)), UDP_TIMINGS_PARTICIPANTS_MAX)
    for index in range(count):
        offset = UDP_TIMING_PARTICIPANT_OFFSET + (index * UDP_TIMING_PARTICIPANT_SIZE)
        if len(packet) < offset + UDP_TIMING_PARTICIPANT_SIZE:
            break
        raw_position = packet[offset + UDP_TIMING_RACE_POSITION_OFFSET]
        is_active = bool(raw_position & 0x80)
        position = raw_position & 0x7F
        mp_index = _read_uint16(packet, offset + UDP_TIMING_MP_INDEX_OFFSET)
        name = _UDP_NAME_BY_INDEX.get(mp_index) or _UDP_NAME_BY_INDEX.get(index) or ""
        if not name or position <= 0:
            continue
        current_lap = int(packet[offset + UDP_TIMING_CURRENT_LAP_OFFSET])
        current_time = _read_float32(packet, offset + UDP_TIMING_CURRENT_TIME_OFFSET)
        lap_distance = float(_read_uint16(packet, offset + UDP_TIMING_LAP_DISTANCE_OFFSET))
        _UDP_TIMING_BY_NAME[_clean_name(name).casefold()] = Ams2TimingInfo(
            name=name,
            position=position,
            lap_distance=lap_distance,
            current_lap=current_lap,
            current_time=current_time,
            is_active=is_active,
        )


def _read_shared_memory() -> tuple[str, bytes, str]:
    last_error = ""
    for name in SHARED_MEMORY_NAMES:
        handle = _open_file_mapping(name)
        if not handle:
            last_error = _last_windows_error()
            continue
        try:
            for read_size in READ_SIZES:
                view = None
                try:
                    view = _map_view_of_file(handle, read_size)
                    if not view:
                        last_error = _last_windows_error()
                        continue
                    return name, ctypes.string_at(view, read_size), ""
                finally:
                    if view:
                        ctypes.windll.kernel32.UnmapViewOfFile(ctypes.c_void_p(view))
        finally:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))
    return "", b"", last_error


def _open_file_mapping(name: str) -> int:
    ctypes.windll.kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    ctypes.windll.kernel32.OpenFileMappingW.restype = ctypes.c_void_p
    handle = ctypes.windll.kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
    return int(handle or 0)


def _map_view_of_file(handle: int, read_size: int) -> int:
    ctypes.windll.kernel32.MapViewOfFile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_size_t,
    ]
    ctypes.windll.kernel32.MapViewOfFile.restype = ctypes.c_void_p
    view = ctypes.windll.kernel32.MapViewOfFile(ctypes.c_void_p(handle), FILE_MAP_READ, 0, 0, read_size)
    return int(view or 0)


def _last_windows_error() -> str:
    error_code = ctypes.windll.kernel32.GetLastError()
    return f"WinError {error_code}" if error_code else ""


def _extract_printable_names(data: bytes) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    current = bytearray()
    for value in data:
        if 32 <= value <= 126:
            current.append(value)
            continue
        if current:
            _append_printable_name(names, seen, bytes(current))
            current.clear()
    if current:
        _append_printable_name(names, seen, bytes(current))
    return names


def _read_int32(data: bytes, offset: int) -> int:
    if len(data) < offset + 4:
        return 0
    return int.from_bytes(data[offset : offset + 4], "little", signed=True)


def _read_uint32(data: bytes, offset: int) -> int:
    if len(data) < offset + 4:
        return 0
    return int.from_bytes(data[offset : offset + 4], "little", signed=False)


def _read_uint16(data: bytes, offset: int) -> int:
    if len(data) < offset + 2:
        return 0
    return int.from_bytes(data[offset : offset + 2], "little", signed=False)


def _read_float32(data: bytes, offset: int) -> float:
    if len(data) < offset + 4:
        return 0.0
    try:
        return float(struct.unpack_from("<f", data, offset)[0])
    except struct.error:
        return 0.0


def _normal_event_time_remaining(raw_value: float, session_duration_minutes: float) -> float:
    if raw_value <= 0:
        return 0.0
    duration_seconds = max(0.0, float(session_duration_minutes or 0.0) * 60.0)
    if duration_seconds > 0:
        max_reasonable = max(60.0, duration_seconds * 1.25)
        if 0 < raw_value <= max_reasonable:
            return raw_value
        milliseconds_value = raw_value / 1000.0
        if 0 < milliseconds_value <= max_reasonable:
            return milliseconds_value
        return 0.0
    if raw_value > 24 * 60 * 60:
        return raw_value / 1000.0
    return raw_value


def _decode_c_string(value: bytes) -> str:
    raw = value.split(b"\x00", 1)[0]
    for encoding in ("utf-8", "latin-1"):
        decoded = raw.decode(encoding, errors="ignore")
        cleaned = _clean_name(decoded)
        if cleaned:
            return cleaned
    return ""


def _append_printable_name(names: list[str], seen: set[str], raw: bytes) -> None:
    if len(raw) < 3:
        return
    text = _clean_name(raw.decode("latin-1", errors="ignore"))
    if not text or not any(character.isalpha() for character in text):
        return
    key = text.casefold()
    if key in seen:
        return
    names.append(text)
    seen.add(key)


def _raw_name_matches(expected_names: list[str], data: bytes) -> set[str]:
    lower_data = data.lower()
    matches: set[str] = set()
    for name in expected_names:
        lower_name = name.casefold()
        candidates = {
            lower_name.encode("utf-8", errors="ignore"),
            lower_name.encode("latin-1", errors="ignore"),
            lower_name.encode("utf-16-le", errors="ignore"),
        }
        raw_candidates = {
            name.encode("utf-8", errors="ignore"),
            name.encode("latin-1", errors="ignore"),
            name.encode("utf-16-le", errors="ignore"),
        }
        if any(candidate and candidate in lower_data for candidate in candidates) or any(
            candidate and candidate in data for candidate in raw_candidates
        ):
            matches.add(name)
    return matches


def _format_decoded_names(names: list[str]) -> str:
    if not names:
        return "none"
    preview = ", ".join(names[:4])
    extra = f" +{len(names) - 4} more" if len(names) > 4 else ""
    return f"{len(names)} ({preview}{extra})"


def _format_missing_names(missing: list[str]) -> str:
    if not missing:
        return "None"
    preview = ", ".join(missing[:4])
    extra = f" +{len(missing) - 4} more" if len(missing) > 4 else ""
    return f"{preview}{extra}"


def _unique_clean_names(names: list[str]) -> list[str]:
    cleaned_names: list[str] = []
    seen: set[str] = set()
    for name in names:
        cleaned = _clean_name(name)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            cleaned_names.append(cleaned)
            seen.add(key)
    return cleaned_names


def _clean_name(name: str) -> str:
    return " ".join(str(name).strip().split())
