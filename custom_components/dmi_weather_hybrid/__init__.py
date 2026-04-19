"""The DMI Weather Hybrid integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_FORECAST_ENTITY,
    CONF_STATION_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import DMIWeatherCoordinator
from .dmi_api import DMIWeatherAPI

PLATFORMS: list[Platform] = [Platform.WEATHER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DMI Weather Hybrid from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    station_id = entry.options.get(CONF_STATION_ID, entry.data[CONF_STATION_ID])
    update_interval = entry.options.get(
        CONF_UPDATE_INTERVAL,
        entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    )
    forecast_entity = entry.options.get(
        CONF_FORECAST_ENTITY,
        entry.data.get(CONF_FORECAST_ENTITY, ""),
    )

    api = DMIWeatherAPI(
        hass,
        entry.data[CONF_LATITUDE],
        entry.data[CONF_LONGITUDE],
        station_id,
    )
    coordinator = DMIWeatherCoordinator(hass, api, update_interval, forecast_entity)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
