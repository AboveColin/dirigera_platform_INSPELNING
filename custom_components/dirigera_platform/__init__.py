"""Platform for IKEA dirigera hub integration."""
from __future__ import annotations

import asyncio
import logging

from dirigera import Hub 
from dirigera.devices.scene import Scene as DirigeraScene

import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.components.light import PLATFORM_SCHEMA
from homeassistant.const import CONF_IP_ADDRESS, CONF_TOKEN, CONF_ENTITY_ID, CONF_TYPE

# Import the device class from the component that you want to support
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, CONF_HIDE_DEVICE_SET_BULBS
from .hub_event_listener import hub_event_listener

logger = logging.getLogger("custom_components.dirigera_platform")

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_IP_ADDRESS): cv.string,
        vol.Required(CONF_TOKEN): cv.string,
        vol.Optional(CONF_HIDE_DEVICE_SET_BULBS, default=True): cv.boolean
    }
)

hub_events = None 

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    logger.error("Starting async_setup...")
    for k in config.keys():
        logger.error(f"config key: {k} value: {config[k]}")
    logger.error("Complete async_setup...")

    def handle_dump_data(call):
        import dirigera

        logger.info("=== START Devices JSON ===")

        # we could have multiple hubs set up
        for key in hass.data[DOMAIN].keys():
            logger.info("--------------")
            config_data = hass.data[DOMAIN][key]
            ip = config_data[CONF_IP_ADDRESS]
            token = config_data[CONF_TOKEN]
            if ip == "mock":
                logger.info("{ MOCK JSON }")
            else:
                hub = dirigera.Hub(token, ip)
                json_resp = hub.get("/devices")
                logger.info(json_resp)
            logger.info("--------------")

        logger.info("=== END Devices JSON ===")

    hass.services.async_register(DOMAIN, "dump_data", handle_dump_data)
    return True


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    global hub_events
    """Set up platform from a ConfigEntry."""
    logger.error("Staring async_setup_entry in init...")
    logger.error(dict(entry.data))
    logger.error(f"async_setup_entry {entry.unique_id} {entry.state} {entry.entry_id} {entry.title} {entry.domain}")
    hass.data.setdefault(DOMAIN, {})
    hass_data = dict(entry.data)

    logger.debug(f"hass_data : {hass_data}")

    # for backward compatibility
    hide_device_set_bulbs : bool = True 
    if CONF_HIDE_DEVICE_SET_BULBS in hass_data:
         logger.debug("Found HIDE_DEVICE_SET *****  ")
         logger.debug(hass_data)
         hide_device_set_bulbs = hass_data[CONF_HIDE_DEVICE_SET_BULBS]
    else:
        logger.debug("Not found HIDE_DEVICE_SET *****  ")
        # If its not with HASS update it
        hass_data[CONF_HIDE_DEVICE_SET_BULBS] = hide_device_set_bulbs

    logger.debug(f"******** HIDE : {hide_device_set_bulbs} ********")
    ip = hass_data[CONF_IP_ADDRESS]
    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)

    # Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
    hass_data["unsub_options_update_listener"] = unsub_options_update_listener
    hass.data[DOMAIN][entry.entry_id] = hass_data

    # Setup the entities
    setup_domains = ["switch", "binary_sensor", "light", "sensor", "cover", "fan", "scene"]
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, setup_domains)
    )

    # Now lets start the event listender too
    hub = Hub(hass_data[CONF_TOKEN], hass_data[CONF_IP_ADDRESS])
    
    if hass_data[CONF_IP_ADDRESS] != "mock":
        hub_events = hub_event_listener(hub, hass)
        hub_events.start()

    logger.debug("Complete async_setup_entry...")

    return True


async def options_update_listener(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
    logger.debug("In options_update_listener")
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    global hub_events
    # Called during re-load and delete
    logger.debug("Starting async_unload_entry")

    #Stop the listener
    if hub_events is not None:
        hub_events.stop()
        hub_events = None 

    hass_data = dict(entry.data)
    hub = Hub(hass_data[CONF_TOKEN], hass_data[CONF_IP_ADDRESS])
    
    # For each controller if there is an empty scene delete it
    logger.error("In unload so forcing delete of scenes...")
    scenes: list[DirigeraScene] = await hass.async_add_executor_job(hub.get_scenes)
    for scene in scenes:
        if scene.info.name is None or not scene.info.name.startswith("dirigera_platform_empty_scene_"):
            logger.error(f"Ignoring scene : {scene.info.name}, as not empty scene")
            continue
        logger.error(f"Deleting scene {scene.id}...")
        await hass.async_add_executor_job(hass.delete_scene,scene.id)
    logger.error("Done deleting scene....")
    
    """Unload a config entry."""
    unload_ok = all(
        [
            await asyncio.gather(
                *[
                    hass.config_entries.async_forward_entry_unload(entry, "light"),
                    hass.config_entries.async_forward_entry_unload(entry, "switch"),
                    hass.config_entries.async_forward_entry_unload(entry, "binary_sensor"),
                    hass.config_entries.async_forward_entry_unload(entry, "sensor"),
                    hass.config_entries.async_forward_entry_unload(entry, "cover"),
                    hass.config_entries.async_forward_entry_unload(entry, "fan"),
                    hass.config_entries.async_forward_entry_unload(entry, "scene"),
                ]
            )
        ]
    )
    
    hass.data[DOMAIN][entry.entry_id]["unsub_options_update_listener"]()
    hass.data[DOMAIN].pop(entry.entry_id)
    logger.debug("Successfully popped entry")
    logger.debug("Complete async_unload_entry")

    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    device_entry: config_entries.DeviceEntry,
) -> bool:

    logger.info("Got request to remove device")
    logger.info(config_entry)
    logger.info(device_entry)
    return True
