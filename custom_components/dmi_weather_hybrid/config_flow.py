"""Config flow for DMI Weather Hybrid integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

_LOGGER = logging.getLogger(__name__)
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_FORECAST_ENTITY,
    CONF_STATION_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    STATION_LOOKUP_URL,
)
from .dmi_api import DMIWeatherAPI


class DMIWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DMI Weather Hybrid."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return DMIWeatherHybridOptionsFlow(config_entry)

    def _build_schema(self, user_input: dict[str, Any] | None = None) -> vol.Schema:
        """Return the config form schema."""
        user_input = user_input or {}
        return vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=user_input.get(CONF_NAME, DEFAULT_NAME)
                ): str,
                vol.Required(
                    CONF_LATITUDE,
                    default=user_input.get(
                        CONF_LATITUDE, str(self.hass.config.latitude)
                    ),
                ): str,
                vol.Required(
                    CONF_LONGITUDE,
                    default=user_input.get(
                        CONF_LONGITUDE, str(self.hass.config.longitude)
                    ),
                ): str,
                vol.Required(
                    CONF_STATION_ID, default=user_input.get(CONF_STATION_ID, "")
                ): str,
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=user_input.get(
                        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                    ),
                ): vol.All(int, vol.Range(min=5, max=1440)),
                vol.Optional(
                    CONF_FORECAST_ENTITY,
                    default=user_input.get(CONF_FORECAST_ENTITY, ""),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                station_id = str(user_input[CONF_STATION_ID]).strip()

                # Convert coordinates to float, handling comma format
                try:
                    lat = float(str(user_input[CONF_LATITUDE]).replace(",", "."))
                    lon = float(str(user_input[CONF_LONGITUDE]).replace(",", "."))
                except ValueError:
                    errors["base"] = "invalid_coordinates"
                    lat = None
                    lon = None

                # Validate coordinates are reasonable
                if lat is None or lon is None:
                    pass
                elif not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    errors["base"] = "invalid_coordinates"
                elif not station_id:
                    errors["base"] = "invalid_station_id"
                else:
                    api = DMIWeatherAPI(self.hass, lat, lon, station_id)
                    if not await api.validate_station_id():
                        errors["base"] = "invalid_station_id"

                if not errors:
                    # Create the config entry with converted coordinates
                    config_data = user_input.copy()
                    config_data[CONF_LATITUDE] = lat
                    config_data[CONF_LONGITUDE] = lon
                    config_data[CONF_STATION_ID] = station_id

                    return self.async_create_entry(
                        title=user_input[CONF_NAME], data=config_data
                    )

            except Exception as e:
                _LOGGER.error("Config flow error: %s", e)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(user_input),
            errors=errors,
            description_placeholders={
                "docs_url": STATION_LOOKUP_URL,
            },
        )


class DMIWeatherHybridOptionsFlow(config_entries.OptionsFlow):
    """Handle DMI Weather Hybrid options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    def _build_schema(self, user_input: dict[str, Any] | None = None) -> vol.Schema:
        """Return the options form schema."""
        user_input = user_input or {}
        return vol.Schema(
            {
                vol.Required(
                    CONF_STATION_ID,
                    default=user_input.get(
                        CONF_STATION_ID,
                        self.config_entry.options.get(
                            CONF_STATION_ID, self.config_entry.data[CONF_STATION_ID]
                        ),
                    ),
                ): str,
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=user_input.get(
                        CONF_UPDATE_INTERVAL,
                        self.config_entry.options.get(
                            CONF_UPDATE_INTERVAL,
                            self.config_entry.data.get(
                                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                            ),
                        ),
                    ),
                ): vol.All(int, vol.Range(min=5, max=1440)),
                vol.Optional(
                    CONF_FORECAST_ENTITY,
                    default=user_input.get(
                        CONF_FORECAST_ENTITY,
                        self.config_entry.options.get(
                            CONF_FORECAST_ENTITY,
                            self.config_entry.data.get(CONF_FORECAST_ENTITY, ""),
                        ),
                    ),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the integration options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                station_id = str(user_input[CONF_STATION_ID]).strip()
                if not station_id:
                    errors["base"] = "invalid_station_id"
                else:
                    api = DMIWeatherAPI(
                        self.hass,
                        self.config_entry.data[CONF_LATITUDE],
                        self.config_entry.data[CONF_LONGITUDE],
                        station_id,
                    )
                    if not await api.validate_station_id():
                        errors["base"] = "invalid_station_id"

                if not errors:
                    return self.async_create_entry(
                        title="",
                        data={
                            CONF_STATION_ID: station_id,
                            CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                            CONF_FORECAST_ENTITY: user_input.get(
                                CONF_FORECAST_ENTITY, ""
                            ),
                        },
                    )
            except Exception as err:
                _LOGGER.error("Options flow error: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_schema(user_input),
            errors=errors,
            description_placeholders={
                "docs_url": STATION_LOOKUP_URL,
            },
        )
