import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.dess_monitor.api import helpers as api_helpers
from custom_components.dess_monitor.api.helpers import resolve_ctrl_field_id
from custom_components.dess_monitor.api.resolvers.data_resolvers import (
    resolve_active_load_percentage,
    resolve_active_load_power,
    resolve_battery_charging_current,
    resolve_battery_charging_power,
    resolve_battery_charging_voltage,
    resolve_battery_discharge_current,
    resolve_battery_discharge_power,
    resolve_battery_voltage,
    resolve_charge_priority,
    resolve_grid_frequency,
    resolve_grid_in_power,
    resolve_output_priority,
)

devcode = 2376

base_dir = Path(__file__).resolve().parent / "devcodes" / str(devcode)


def extract_output_priority(last_data_dat: dict) -> str | None:
    pars = (last_data_dat or {}).get("pars") or {}
    for group in pars.values():
        if not isinstance(group, list):
            continue
        for entry in group:
            if not isinstance(entry, dict):
                continue
            if entry.get("par") == "Output priority" or entry.get("id") == "sy_eybond_read_49":
                val = entry.get("val")
                if val is None:
                    return None
                code = str(val).upper()
                return {
                    "UTI": "Utility",
                    "SOL": "Solar",
                    "SBU": "SBU",
                    "SUB": "SUB",
                    "SUF": "SUF",
                }.get(code, code)
    return None


with open(base_dir / "queryDeviceCtrlField.json", encoding="utf-8") as queryDeviceCtrlField:
    ctrl_fields = json.load(queryDeviceCtrlField)
    resolved_id = resolve_ctrl_field_id(ctrl_fields, "output_priority_option")
    assert resolved_id == "bse_eybond_ctrl_49", resolved_id
    ctrl_fields_dat = ctrl_fields.get("dat") or ctrl_fields


async def _fake_get_device_ctrl_value(_token: str, _secret: str, _device_data, _param_id: str):
    return {"val": "0"}


api_helpers.get_device_ctrl_value = _fake_get_device_ctrl_value
device_data = {"devcode": devcode}
resolved = asyncio.run(api_helpers.get_inverter_output_priority("t", "s", ctrl_fields_dat, device_data))
assert resolved == "Utility", resolved


async def _fake_get_device_ctrl_value_float(_token: str, _secret: str, _device_data, _param_id: str):
    return {"val": "0.0"}


api_helpers.get_device_ctrl_value = _fake_get_device_ctrl_value_float
resolved = asyncio.run(api_helpers.get_inverter_output_priority("t", "s", ctrl_fields_dat, device_data))
assert resolved == "Utility", resolved


async def _fake_get_device_ctrl_value_code(_token: str, _secret: str, _device_data, _param_id: str):
    return {"val": "UTI"}


api_helpers.get_device_ctrl_value = _fake_get_device_ctrl_value_code
resolved = asyncio.run(api_helpers.get_inverter_output_priority("t", "s", ctrl_fields_dat, device_data))
assert resolved == "Utility", resolved

with open(base_dir / "querySPDeviceLastData.json", encoding="utf-8") as querySPDeviceLastData:
    with open(base_dir / "webQueryDeviceEnergyFlowEs.json", encoding="utf-8") as webQueryDeviceEnergyFlowEs:
        last_data = json.load(querySPDeviceLastData)
        energy_flow = json.load(webQueryDeviceEnergyFlowEs)
        output_priority = extract_output_priority(last_data.get("dat") or {})
        data = {
            'last_data': last_data['dat'],
            'energy_flow': energy_flow['dat'],
            'device_extra': {
                'output_priority': output_priority,
                'ctrl_values': {},
            }
        }
        device_data = {
            'devcode': devcode
        }
        assert resolve_output_priority(data, device_data) is not None
        print('resolve_battery_voltage', resolve_battery_voltage(data, device_data))
        print('resolve_grid_in_power', resolve_grid_in_power(data, device_data))
        print('resolve_grid_frequency', resolve_grid_frequency(data, device_data))
        print('resolve_output_priority', resolve_output_priority(data, device_data))
        print('resolve_charge_priority', resolve_charge_priority(data, device_data))
        print('resolve_battery_charging_voltage', resolve_battery_charging_voltage(data, device_data))
        print('resolve_battery_charging_current', resolve_battery_charging_current(data, device_data))
        print('resolve_battery_discharge_current', resolve_battery_discharge_current(data, device_data))
        print('resolve_battery_charging_power', resolve_battery_charging_power(data, device_data))
        print('resolve_battery_discharge_power', resolve_battery_discharge_power(data, device_data))
