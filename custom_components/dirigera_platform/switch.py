import logging

from .dirigera_new import Hub
from .dirigera_new.devices.outlet import Outlet

from homeassistant import config_entries, core
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_IP_ADDRESS, CONF_TOKEN
from homeassistant.core import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .mocks.ikea_outlet_mock import ikea_outlet_mock
from .base_classes import ikea_base_device
logger = logging.getLogger("custom_components.dirigera_platform")


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    logger.debug("SWITCH Starting async_setup_entry")
    config = hass.data[DOMAIN][config_entry.entry_id]
    hub = Hub(config[CONF_TOKEN], config[CONF_IP_ADDRESS])

    outlets = []

    if config[CONF_IP_ADDRESS] == "mock":
        logger.warning("Setting up mock outlets...")
        mock_outlet1 = ikea_outlet_mock(hub, "mock_outlet1")
        outlets = [mock_outlet1]
    else:
        hub_outlets: list[Outlet] = await hass.async_add_executor_job(hub.get_outlets)
        for outlet in hub_outlets:
            outlet_entity = ikea_outlet(hass, hub, outlet)
            outlets.append(outlet_entity)

    logger.debug(f"Found {len(outlets)} outlet entities to setup...")
    async_add_entities(outlets)
    logger.debug("SWITCH Complete async_setup_entry")

class ikea_outlet(ikea_base_device, SwitchEntity):
    def __init__(self, hass, hub, json_data):
        super().__init__(hass, hub, json_data, hub.get_outlet_by_id)

    async def async_turn_on(self):
        logger.debug("outlet turn_on")
        try:
            await self.hass.async_add_executor_job(self._json_data.set_on, True)
        except Exception as ex:
            logger.error(f"Error turning on {self.name}: {ex}")
            raise HomeAssistantError(ex, DOMAIN, "hub_exception")

    async def async_turn_off(self):
        logger.debug("outlet turn_off")
        try:
            await self.hass.async_add_executor_job(self._json_data.set_on, False)
        except Exception as ex:
            logger.error(f"Error turning off {self.name}: {ex}")
            raise HomeAssistantError(ex, DOMAIN, "hub_exception")

    @property
    def is_on(self):
        return self._json_data.attributes.is_on

    @property
    def icon(self):
        return "mdi:power-plug"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=self.name,
            manufacturer="IKEA",
            model=self._json_data.attributes.model,
            sw_version=self._json_data.attributes.firmware_version,
        )
    
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        non_sensor_attributes = {
            "custom_name": getattr(self._json_data.attributes, 'custom_name', None),
            "model": getattr(self._json_data.attributes, 'model', None),
            "manufacturer": getattr(self._json_data.attributes, 'manufacturer', None),
            "firmware_version": getattr(self._json_data.attributes, 'firmware_version', None),
            "hardware_version": getattr(self._json_data.attributes, 'hardware_version', None),
            "serial_number": getattr(self._json_data.attributes, 'serial_number', None),
            "product_code": getattr(self._json_data.attributes, 'product_code', None),
            "ota_status": getattr(self._json_data.attributes, 'ota_status', None),
            "ota_state": getattr(self._json_data.attributes, 'ota_state', None),
        }
        return non_sensor_attributes