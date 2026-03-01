import math
from typing import Optional

from homeassistant.components.select import SelectEntity

from .core.const import DOMAIN
from .core.entity import XEntity
from .core.ewelink import SIGNAL_ADD_ENTITIES, XRegistry

PARALLEL_UPDATES = 0  # fix entity_platform parallel_updates Semaphore


async def async_setup_entry(hass, config_entry, add_entities):
    ewelink: XRegistry = hass.data[DOMAIN][config_entry.entry_id]
    ewelink.dispatcher_connect(
        SIGNAL_ADD_ENTITIES,
        lambda x: add_entities([e for e in x if isinstance(e, SelectEntity)]),
    )

class XSelectAutoGenerateOptions(XEntity, SelectEntity):
    _attr_options = []
    _correction_range: tuple[int | float] | None = None
    _correction_step: int | float | None = None

    def __init__(self, ewelink, device):
        super().__init__(ewelink, device)
        self._attr_options = self._generate_options()

    def _generate_options(self) -> list:
        if self._correction_range is None or self._correction_step is None:
            return

        min_val, max_val = self._correction_range
        if max_val <= min_val:
            return []

        if self._correction_step <= 0:
            return []

        options_count = math.floor((max_val - min_val) / self._correction_step) + 1
        options = []
        for i in range(options_count):
            option_value = min_val + (self._correction_step * i)
            formatted_value = round(option_value, 1)
            options.append(str(formatted_value))

        return options


class XSelectTRVTemperatureCorrection(XSelectAutoGenerateOptions):
    params = {"tempCorrection"}
    _correction_range = (-7, 7)
    _correction_step = 0.2

    def set_state(self, params: dict) -> Optional[str]:
        if not isinstance(params, dict):
            return None

        value = params.get(self.param)
        if not isinstance(value, (int, float)):
            return None

        try:
            corrected_value = 0.0 if value == 0 else round(value / 10.0, 1)
            self._attr_current_option = str(corrected_value)
        except (ValueError, ZeroDivisionError):
            return None

    async def async_select_option(self, option: str) -> None:
        try:
            if not option or not isinstance(option, str):
                return
            temp_correction = int(float(option) * 10)
            await self.ewelink.send(self.device, {self.param: temp_correction})
        except Exception:
            pass


class XSelectTRVEcoTargetTemperature(XSelectAutoGenerateOptions):
    params = {"ecoTargetTemp"}
    _correction_range = (4, 35)
    _correction_step = 0.5

    def __int__(self, ewelink, device):
        super().__init__(ewelink, device)

    def set_state(self, params: dict):
        if not isinstance(params, dict):
            return None

        value = params.get(self.param)
        if not isinstance(value, (int, float)):
            return None

        try:
            corrected_value = 0.0 if value == 0 else round(value / 10.0, 1)
            self._attr_current_option = str(corrected_value)
            return
        except (ValueError, ZeroDivisionError):
            return None

    async def async_select_option(self, option: str):
        try:
            if not option or not isinstance(option, str):
                return
            eco_target_temp = int(float(option) * 10)
            await self.ewelink.send(self.device, {self.param: eco_target_temp})
        except Exception:
            pass


class XSelectStartup(XEntity, SelectEntity):
    params = {"startup"}
    channel: int = 0

    get_params = {"configure": "get"}

    _attr_current_option = None
    _attr_options = ["off", "on", "stay"]

    def __init__(self, ewelink: XRegistry, device: dict):
        super().__init__(ewelink, device)

        if "params" in device and isinstance(device["params"], dict):
            configure_list = device["params"].get("configure")
            if isinstance(configure_list, list):
                for item in configure_list:
                    if item.get("outlet") == self.channel:
                        self._attr_current_option = item.get("startup", "stay")
                        break

        # Initialize a local dict if not present, to store each channel's startup config.
        if "channel_startups" not in device:
            device["channel_startups"] = {}

        try:
            self._attr_name = device["tags"]["ck_channel_name"][str(self.channel)]
        except KeyError:
            pass
        # backward compatibility
        self._attr_unique_id = f"{device['deviceid']}_{self.channel + 1}"

    def set_state(self, params: dict):
        # Just update _attr_current_option based on what the device reports
        if "params" in self.device and isinstance(self.device["params"], dict):
            configure_list = self.device["params"].get("configure")
            if isinstance(configure_list, list):
                for item in configure_list:
                    if item.get("outlet") == self.channel:
                        self._attr_current_option = item.get("startup", "stay")
                        break

    async def async_update(self):
        # Send a request to the device to get the latest state
        await self.ewelink.send(self.device, self.get_params, timeout_lan=5)

    async def async_select_option(self, option: str):
        # Update our local record for this channel
        self.device["channel_startups"][self.channel] = option

        # Rebuild the entire list for every known channel so they're all sent together
        configure_list = []
        for ch, startup_opt in self.device["channel_startups"].items():
            configure_list.append({
                "outlet": ch,
                "startup": startup_opt,
                "enableDelay": 0, # this should be exposed as a config option in the future, for inching devices
                "width": 1000 # i don't know what this is for, but it seems to not have any effect on the device
            })

        # Send all channels at once
        await self.ewelink.send(self.device, {"configure": configure_list})
