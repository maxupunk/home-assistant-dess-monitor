from typing import Any, Dict, Optional

from custom_components.dess_monitor.api.commands.direct_commands import decode_direct_response, get_command_hex
from custom_components.dess_monitor.api.resolvers.data_keys_map import SENSOR_KEYS_MAP

try:
    from custom_components.dess_monitor.api import set_ctrl_device_param, get_device_ctrl_value, send_device_direct_command
except ModuleNotFoundError:
    set_ctrl_device_param = None
    get_device_ctrl_value = None
    send_device_direct_command = None


def resolve_param(data, where, case_insensitive=False, find_all=False, default=None, root_keys=None):
    """
    Recursively searches for elements in a nested structure that satisfy 'where'.

    Args:
      data: The input data (dict, list, etc.).
      where: A dict of conditions (AND mode) or a list of dicts (OR mode).
      case_insensitive: Compare strings in lower-case if True.
      find_all: Return all matching elements if True; otherwise, first match.
      default: Value to return if no match is found.
      root_keys: List of keys at root to start the search; if None, search full structure.

    Returns:
      A matching element (or list of elements) or default if not found.
    """
    found = []

    def _matches_conditions(item):
        # OR mode if where is a list; AND mode if dict.
        if isinstance(where, list):
            for condition in where:
                if not isinstance(condition, dict):
                    continue
                match = True
                for key, value in condition.items():
                    if key not in item:
                        match = False
                        break
                    item_val = item[key]
                    if case_insensitive and isinstance(item_val, str) and isinstance(value, str):
                        if item_val.lower() != value.lower():
                            match = False
                            break
                    else:
                        if item_val != value:
                            match = False
                            break
                if match:
                    return True
            return False
        elif isinstance(where, dict):
            for key, value in where.items():
                if key not in item:
                    return False
                item_val = item[key]
                if case_insensitive and isinstance(item_val, str) and isinstance(value, str):
                    if item_val.lower() != value.lower():
                        return False
                else:
                    if item_val != value:
                        return False
            return True
        return False

    def _search(current):
        nonlocal found
        if isinstance(current, dict):
            if _matches_conditions(current):
                found.append(current)
                if not find_all:
                    return True
            for v in current.values():
                if isinstance(v, (dict, list)):
                    if _search(v) and not find_all:
                        return True
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    if _search(item) and not find_all:
                        return True
        return False

    if root_keys is not None and isinstance(data, dict):
        for key in root_keys:
            if key in data:
                _search(data[key])
    else:
        _search(data)

    if find_all:
        return found if found else default
    else:
        return found[0] if found else default


def safe_float(val: Optional[str], default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def get_sensor_value_simple(
        name: str,
        data: Dict[str, Any],
        device_data: Dict[str, Any]
) -> Optional[str]:
    keys = SENSOR_KEYS_MAP.get(name, [])

    ctrl_values = (data.get('device_extra') or {}).get('ctrl_values') or {}

    for key in keys:
        res = resolve_param(data, {"id": key}, case_insensitive=True)
        if res:
            val = res.get("val")
            if val is not None:
                return val
        res = resolve_param(data, {"par": key}, case_insensitive=True)
        if res:
            if res.get("status", 1) != 0:
                val = res.get("val")
                if val is not None:
                    return val

        # Some values are only available via queryDeviceCtrlValue.
        if key in ctrl_values and ctrl_values.get(key) is not None:
            return str(ctrl_values.get(key))
    return None


def get_sensor_value_simple_entry(
        name: str,
        data: Dict[str, Any],
        device_data: Dict[str, Any]
) -> tuple[str, Any, Any] | None:
    """
    Ищет значение сенсора по ключам из SENSOR_KEYS_MAP[name].
    Возвращает кортеж (имя_поля, значение), где имя_поля — "id" или "par".
    """
    keys = SENSOR_KEYS_MAP.get(name, [])
    for key in keys:
        res = resolve_param(data, {"id": key}, case_insensitive=True)
        if res:
            val = res.get("val")
            if val is not None:
                return res.get("id"), val, res.get("unit", None)
        res = resolve_param(data, {"par": key}, case_insensitive=True)
        if res:
            if res.get("status", 1) == 0:
                continue
            val = res.get("val")
            if val is not None:
                return res.get("par"), val, res.get("unit", None)
    return None


def resolve_ctrl_field_id(ctrl_fields, sensor_key: str) -> str | None:
    keys = SENSOR_KEYS_MAP.get(sensor_key, [])
    for key in keys:
        res = resolve_param(ctrl_fields, {"id": key}, case_insensitive=True)
        if res and res.get("id"):
            return str(res.get("id"))
        res = resolve_param(ctrl_fields, {"name": key}, case_insensitive=True)
        if res and res.get("id"):
            return str(res.get("id"))
        res = resolve_param(ctrl_fields, {"par": key}, case_insensitive=True)
        if res and res.get("id"):
            return str(res.get("id"))
    return None


def normalize_output_priority_label(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().upper()
    map_code = {
        "UTILITY FIRST": "Utility",
        "UTILITY": "Utility",
        "UTI": "Utility",
        "SOLAR FIRST": "Solar",
        "SOLAR": "Solar",
        "SOL": "Solar",
        "SBU FIRST": "SBU",
        "SBU": "SBU",
        "SUB": "SUB",
        "SUF": "SUF",
    }
    return map_code.get(s, s)


async def set_inverter_output_priority(
    token: str,
    secret: str,
    device_data,
    value: str,
    ctrl_fields=None,
):
    if set_ctrl_device_param is None:
        raise RuntimeError("aiohttp/homeassistant dependencies not available")
    if ctrl_fields is not None:
        try:
            param_id = resolve_ctrl_field_id(ctrl_fields, "output_priority_option")
            if param_id:
                ctrl_field_entry = resolve_param(ctrl_fields, {"id": param_id}, case_insensitive=True) or {}
                wanted = normalize_output_priority_label(value)
                wanted_candidates = [wanted]
                if wanted == "SUB":
                    has_sub = False
                    for item in ctrl_field_entry.get("item") or []:
                        if normalize_output_priority_label(item.get("val")) == "SUB":
                            has_sub = True
                            break
                    if not has_sub:
                        wanted_candidates.append("Utility")
                for item in ctrl_field_entry.get("item") or []:
                    if normalize_output_priority_label(item.get("val")) not in wanted_candidates:
                        continue
                    item_key = item.get("key")
                    if item_key is None:
                        break
                    return await set_ctrl_device_param(token, secret, device_data, param_id, str(item_key))
        except Exception:
            pass
    match device_data['devcode']:
        case 2341:
            map_param_value = {
                'Utility': '0',
                'SUB': '0',
                'Solar': '1',
                'SBU': '2'
            }
            param_value = map_param_value.get(value)

            if param_value is None:
                return

            param_id = 'los_output_source_priority'
        case 2428:
            map_param_value = {
                'Utility': '12336',
                'SUB': '12336',
                'Solar': '12337',
                'SBU': '12338'
            }
            param_value = map_param_value.get(value)

            if param_value is None:
                return

            param_id = 'bse_output_source_priority'
        case 2376:
            map_param_value = {
                'Utility': '0',
                'Solar': '1',
                'SBU': '2',
                'SUB': '3',
                'SUF': '4',
            }
            param_value = map_param_value.get(value)

            if param_value is None:
                return

            param_id = 'bse_eybond_ctrl_49'

        case _:
            return
    return await set_ctrl_device_param(token, secret, device_data, param_id, param_value)


async def get_inverter_output_priority(token: str, secret: str, ctrl_fields, device_data):
    if get_device_ctrl_value is None:
        raise RuntimeError("aiohttp/homeassistant dependencies not available")
    def _normalize_key(value: Any) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        try:
            f = float(s)
            if f.is_integer():
                return str(int(f))
        except Exception:
            pass
        return s

    param_id = resolve_ctrl_field_id(ctrl_fields, "output_priority_option")
    if param_id is None:
        return None

    ctrl_field_entry = resolve_param(ctrl_fields, {"id": param_id}, case_insensitive=True) or {}
    item_key_to_val: dict[str, str] = {}
    for item in ctrl_field_entry.get("item") or []:
        try:
            k = str(item.get("key")).strip().upper()
            v = str(item.get("val")).strip().upper()
            item_key_to_val[k] = v
        except Exception:
            continue

    result = await get_device_ctrl_value(token, secret, device_data, param_id)
    raw = result.get("val") if isinstance(result, dict) else None
    if raw is None:
        return None

    raw_n = _normalize_key(raw)
    raw_u = str(raw_n).strip().upper() if raw_n is not None else None
    if raw_u is None:
        return None

    code = item_key_to_val.get(raw_u, raw_u)

    normalized = normalize_output_priority_label(code)
    return normalized if normalized is not None else code


async def get_direct_data(token: str, secret: str, device_data, cmd_name):
    if send_device_direct_command is None:
        raise RuntimeError("aiohttp/homeassistant dependencies not available")
    result = await send_device_direct_command(token, secret, device_data, get_command_hex(cmd_name))
    return decode_direct_response(cmd_name, result['dat'])
