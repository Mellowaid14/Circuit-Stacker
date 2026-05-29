from __future__ import annotations

import ctypes
import re
from dataclasses import dataclass


FILE_MAP_READ = 0x0004
IRSDK_MEMORY_NAMES = ("Local\\IRSDKMemMapFileName", "IRSDKMemMapFileName")
ALLOCATION_GRANULARITY = 64 * 1024
HEADER_VIEW_SIZE = 1024 * 1024
HEADER_SIZE = 112
VAR_HEADER_SIZE = 144
BUFFER_HEADER_SIZE = 16
VAR_TYPE_BOOL = 1
VAR_TYPE_INT = 2
VAR_TYPE_BITFIELD = 3
VAR_TYPE_FLOAT = 4
VAR_TYPE_DOUBLE = 5


@dataclass(frozen=True)
class IRacingLiveParticipant:
    name: str
    position: int
    car_idx: int
    car_number: str = ""
    class_name: str = ""


@dataclass(frozen=True)
class IRacingLiveSnapshot:
    participants: list[IRacingLiveParticipant]
    session_state: int
    session_name: str


@dataclass(frozen=True)
class _VarHeader:
    var_type: int
    offset: int
    count: int
    name: str


def read_iracing_live_snapshot() -> tuple[IRacingLiveSnapshot, str]:
    memory_name, header_data, error = _read_memory_view(0, HEADER_VIEW_SIZE)
    if not header_data:
        return IRacingLiveSnapshot([], 0, "Disconnected"), f"iRacing telemetry unavailable: {error or 'not found'}"

    header = _read_header(header_data)
    if not header:
        return IRacingLiveSnapshot([], 0, "Disconnected"), "iRacing telemetry header could not be read."

    session_info = _read_session_info(header_data, header)
    drivers = _parse_driver_info(session_info)
    if not drivers:
        return IRacingLiveSnapshot([], 0, "Connected"), "iRacing telemetry did not expose driver info yet."

    variables = _read_var_headers(header_data, header)
    buffer_offset = _latest_buffer_offset(header_data, header)
    buffer_length = int(header.get("buf_len", 0) or 0)
    if buffer_offset <= 0 or buffer_length <= 0:
        return IRacingLiveSnapshot([], 0, "Connected"), "iRacing telemetry has no active live buffer yet."

    _buffer_name, buffer_data, buffer_error = _read_memory_view(buffer_offset, buffer_length)
    if not buffer_data:
        return IRacingLiveSnapshot([], 0, "Connected"), f"iRacing telemetry live buffer could not be read: {buffer_error}"

    session_num = _read_var_value(buffer_data, variables, "SessionNum", default=0)
    session_state = _read_var_value(buffer_data, variables, "SessionState", default=0)
    session_name = _parse_session_name(session_info, int(session_num or 0))
    positions = _read_var_array(buffer_data, variables, "CarIdxPosition")
    class_positions = _read_var_array(buffer_data, variables, "CarIdxClassPosition")

    participants: list[IRacingLiveParticipant] = []
    for car_idx, driver in drivers.items():
        position = _safe_int(positions[car_idx] if car_idx < len(positions) else 0, 0)
        if position <= 0:
            position = _safe_int(class_positions[car_idx] if car_idx < len(class_positions) else 0, 0)
        if position <= 0:
            continue
        participants.append(
            IRacingLiveParticipant(
                name=driver.get("UserName", ""),
                position=position,
                car_idx=car_idx,
                car_number=driver.get("CarNumber", ""),
                class_name=driver.get("CarClassShortName", "") or driver.get("CarClassName", ""),
            )
        )

    participants.sort(key=lambda participant: participant.position)
    if not participants:
        return IRacingLiveSnapshot([], int(session_state or 0), session_name), "iRacing telemetry has no live positions yet."
    return IRacingLiveSnapshot(participants, int(session_state or 0), session_name), ""


def _read_memory_view(offset: int, size: int) -> tuple[str, bytes, str]:
    last_error = ""
    aligned_offset = max(0, int(offset) - (int(offset) % ALLOCATION_GRANULARITY))
    offset_delta = int(offset) - aligned_offset
    mapped_size = int(size) + offset_delta
    for name in IRSDK_MEMORY_NAMES:
        handle = _open_file_mapping(name)
        if not handle:
            last_error = _last_windows_error()
            continue
        view = None
        try:
            view = _map_view_of_file(handle, aligned_offset, mapped_size)
            if not view:
                last_error = _last_windows_error()
                continue
            mapped_data = ctypes.string_at(view, mapped_size)
            return name, mapped_data[offset_delta : offset_delta + int(size)], ""
        finally:
            if view:
                ctypes.windll.kernel32.UnmapViewOfFile(ctypes.c_void_p(view))
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))
    return "", b"", last_error


def _open_file_mapping(name: str) -> int:
    ctypes.windll.kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    ctypes.windll.kernel32.OpenFileMappingW.restype = ctypes.c_void_p
    handle = ctypes.windll.kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
    return int(handle or 0)


def _map_view_of_file(handle: int, offset: int, size: int) -> int:
    ctypes.windll.kernel32.MapViewOfFile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_size_t,
    ]
    ctypes.windll.kernel32.MapViewOfFile.restype = ctypes.c_void_p
    high = (int(offset) >> 32) & 0xFFFFFFFF
    low = int(offset) & 0xFFFFFFFF
    view = ctypes.windll.kernel32.MapViewOfFile(ctypes.c_void_p(handle), FILE_MAP_READ, high, low, int(size))
    return int(view or 0)


def _last_windows_error() -> str:
    error_code = ctypes.windll.kernel32.GetLastError()
    return f"WinError {error_code}" if error_code else ""


def _read_header(data: bytes) -> dict[str, int]:
    if len(data) < HEADER_SIZE:
        return {}
    return {
        "session_info_len": _read_int32(data, 16),
        "session_info_offset": _read_int32(data, 20),
        "num_vars": _read_int32(data, 24),
        "var_header_offset": _read_int32(data, 28),
        "num_buf": _read_int32(data, 32),
        "buf_len": _read_int32(data, 36),
    }


def _latest_buffer_offset(data: bytes, header: dict[str, int]) -> int:
    latest_tick = -1
    latest_offset = 0
    for index in range(max(0, int(header.get("num_buf", 0) or 0))):
        offset = 48 + (index * BUFFER_HEADER_SIZE)
        if len(data) < offset + 8:
            break
        tick_count = _read_int32(data, offset)
        buffer_offset = _read_int32(data, offset + 4)
        if tick_count > latest_tick and buffer_offset > 0:
            latest_tick = tick_count
            latest_offset = buffer_offset
    return latest_offset


def _read_var_headers(data: bytes, header: dict[str, int]) -> dict[str, _VarHeader]:
    variables: dict[str, _VarHeader] = {}
    base = header.get("var_header_offset", 0)
    num_vars = header.get("num_vars", 0)
    for index in range(max(0, num_vars)):
        offset = base + (index * VAR_HEADER_SIZE)
        if len(data) < offset + VAR_HEADER_SIZE:
            break
        var_type = _read_int32(data, offset)
        value_offset = _read_int32(data, offset + 4)
        count = _read_int32(data, offset + 8)
        name = _decode_c_string(data[offset + 16 : offset + 48])
        if name:
            variables[name] = _VarHeader(var_type=var_type, offset=value_offset, count=count, name=name)
    return variables


def _read_session_info(data: bytes, header: dict[str, int]) -> str:
    offset = header.get("session_info_offset", 0)
    length = header.get("session_info_len", 0)
    if offset <= 0 or length <= 0 or len(data) < offset:
        return ""
    return data[offset : offset + length].split(b"\x00", 1)[0].decode("utf-8", errors="ignore")


def _read_var_value(buffer_data: bytes, variables: dict[str, _VarHeader], name: str, default=0):
    values = _read_var_array(buffer_data, variables, name)
    return values[0] if values else default


def _read_var_array(buffer_data: bytes, variables: dict[str, _VarHeader], name: str) -> list:
    header = variables.get(name)
    if header is None:
        return []
    type_size = _var_type_size(header.var_type)
    if type_size <= 0:
        return []
    values = []
    count = max(1, header.count)
    for index in range(count):
        offset = header.offset + (index * type_size)
        if len(buffer_data) < offset + type_size:
            break
        values.append(_read_typed_value(buffer_data, offset, header.var_type))
    return values


def _read_typed_value(data: bytes, offset: int, var_type: int):
    if var_type == VAR_TYPE_BOOL:
        return data[offset] != 0
    if var_type in {VAR_TYPE_INT, VAR_TYPE_BITFIELD}:
        return _read_int32(data, offset)
    if var_type == VAR_TYPE_FLOAT:
        return ctypes.c_float.from_buffer_copy(data[offset : offset + 4]).value
    if var_type == VAR_TYPE_DOUBLE:
        return ctypes.c_double.from_buffer_copy(data[offset : offset + 8]).value
    return _read_int32(data, offset)


def _var_type_size(var_type: int) -> int:
    if var_type == VAR_TYPE_BOOL:
        return 1
    if var_type in {VAR_TYPE_INT, VAR_TYPE_BITFIELD, VAR_TYPE_FLOAT}:
        return 4
    if var_type == VAR_TYPE_DOUBLE:
        return 8
    return 4


def _parse_driver_info(session_info: str) -> dict[int, dict[str, str]]:
    drivers_section = _extract_nested_yaml_list_section(session_info, "DriverInfo", "Drivers")
    drivers: dict[int, dict[str, str]] = {}
    for item in _parse_simple_yaml_list(drivers_section):
        car_idx = _safe_int(item.get("CarIdx", ""), -1)
        user_name = item.get("UserName", "").strip()
        if car_idx >= 0 and user_name:
            drivers[car_idx] = item
    return drivers


def _parse_session_name(session_info: str, session_num: int) -> str:
    sessions_section = _extract_nested_yaml_list_section(session_info, "SessionInfo", "Sessions")
    for item in _parse_simple_yaml_list(sessions_section):
        if _safe_int(item.get("SessionNum", ""), -1) == session_num:
            return item.get("SessionName", "") or item.get("SessionType", "") or f"Session {session_num}"
    return f"Session {session_num}"


def _extract_nested_yaml_list_section(text: str, parent_name: str, section_name: str) -> str:
    parent_match = re.search(rf"(?m)^{re.escape(parent_name)}:\s*\n(?P<body>.*?)(?=^[A-Za-z0-9_]+:\s*$|\Z)", text, re.S)
    if not parent_match:
        return ""
    parent_body = parent_match.group("body")
    section_match = re.search(
        rf"(?m)^ {re.escape(section_name)}:\s*\n(?P<body>.*?)(?=^ [A-Za-z0-9_]+:\s*$|\Z)",
        parent_body,
        re.S,
    )
    return section_match.group("body") if section_match else ""


def _parse_simple_yaml_list(section: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            if current:
                rows.append(current)
            current = {}
            line = line[2:].strip()
            if ":" in line:
                key, value = line.split(":", 1)
                current[key.strip()] = _clean_yaml_value(value)
            continue
        if current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.strip()] = _clean_yaml_value(value)
    if current:
        rows.append(current)
    return rows


def _clean_yaml_value(value: str) -> str:
    return value.strip().strip("'\"")


def _read_int32(data: bytes, offset: int) -> int:
    if len(data) < offset + 4:
        return 0
    return int.from_bytes(data[offset : offset + 4], "little", signed=True)


def _decode_c_string(value: bytes) -> str:
    return value.split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default
