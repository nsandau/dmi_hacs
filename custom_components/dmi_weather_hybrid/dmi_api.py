"""DMI Weather Hybrid API client."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_TIMEOUT,
    DMI_EDR_BASE_URL,
    DMI_METOBS_BASE_URL,
    EDR_COLLECTIONS_ENDPOINT,
    EDR_PARAMETERS,
    EDR_POSITION_QUERY,
    MAX_FORECAST_DAYS,
    METOBS_OBSERVATION_ENDPOINT,
    METOBS_STATION_ENDPOINT,
    OBSERVATION_PARAMETERS,
)

_LOGGER = logging.getLogger(__name__)


class DMIWeatherAPI:
    """DMI weather client using metObs for current values and EDR for forecast."""

    def __init__(
        self,
        hass: HomeAssistant,
        latitude: float,
        longitude: float,
        station_id: str,
    ) -> None:
        self.hass = hass
        self.latitude = latitude
        self.longitude = longitude
        self.station_id = station_id
        self.current_data: dict[str, Any] = {}
        self.hourly_forecast_data: list[dict[str, Any]] = []
        self.forecast_data: list[dict[str, Any]] = []
        self.daily_forecast_data: list[dict[str, Any]] = []
        self._last_request_time = 0.0
        self._rate_limit_delay = 1.0
        self._update_lock = asyncio.Lock()

    async def _rate_limit(self) -> None:
        """Ensure a minimum delay between requests."""
        now = asyncio.get_running_loop().time()
        time_since_last = now - self._last_request_time
        if time_since_last < self._rate_limit_delay:
            await asyncio.sleep(self._rate_limit_delay - time_since_last)
        self._last_request_time = asyncio.get_running_loop().time()

    async def _make_request(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make API request using Home Assistant's shared HTTP session."""
        await self._rate_limit()
        session = async_get_clientsession(self.hass)
        url = f"{base_url}{endpoint}"

        try:
            async with session.get(
                url, params=params, timeout=DEFAULT_TIMEOUT
            ) as response:
                if response.status == 404:
                    raise RuntimeError("Requested DMI resource was not found")
                if response.status == 429:
                    raise RuntimeError("Rate limit exceeded, please try again later")
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"API request failed with status {response.status}: {error_text}"
                    )
                return await response.json()
        except asyncio.TimeoutError as err:
            raise RuntimeError("Timeout connecting to DMI API") from err

    async def validate_station_id(self) -> bool:
        """Validate that the configured station exists and is active."""
        data = await self._make_request(
            DMI_METOBS_BASE_URL,
            METOBS_STATION_ENDPOINT,
            {"stationId": self.station_id, "status": "Active", "limit": 20},
        )
        features = data.get("features", [])
        return any(
            feature.get("properties", {}).get("stationId") == self.station_id
            for feature in features
        )

    async def test_connection(self) -> bool:
        """Test that both required DMI APIs can be reached."""
        try:
            await self.validate_station_id()
            await self._make_request(DMI_EDR_BASE_URL, EDR_COLLECTIONS_ENDPOINT)
        except Exception as err:  # pragma: no cover - network failures are runtime only
            _LOGGER.error("Connection test failed: %s", err)
            return False
        return True

    async def update(self) -> None:
        """Fetch current observations and forecast data."""
        if self._update_lock.locked():
            _LOGGER.debug("Update already in progress, skipping concurrent request")
            return

        async with self._update_lock:
            await self._fetch_current_observations()
            await self._fetch_forecast_data("harmonie_dini_sf")

    async def _fetch_current_observations(self) -> None:
        """Fetch recent observation data for the configured station."""
        params = {
            "stationId": self.station_id,
            "period": "latest-10-minutes",
            "limit": 100,
            "sortorder": "observed,DESC",
        }
        data = await self._make_request(
            DMI_METOBS_BASE_URL, METOBS_OBSERVATION_ENDPOINT, params
        )
        features = data.get("features", [])
        if not features:
            params["period"] = "latest-hour"
            data = await self._make_request(
                DMI_METOBS_BASE_URL, METOBS_OBSERVATION_ENDPOINT, params
            )
            features = data.get("features", [])

        if not features:
            raise RuntimeError(
                f"No recent observation data available for station {self.station_id}"
            )

        latest_by_parameter: dict[str, dict[str, Any]] = {}
        for feature in features:
            properties = feature.get("properties", {})
            parameter_id = properties.get("parameterId")
            observed = properties.get("observed")
            if not parameter_id or observed is None:
                continue

            previous = latest_by_parameter.get(parameter_id)
            if previous is None or observed > previous.get("observed", ""):
                latest_by_parameter[parameter_id] = properties

        weather_code = self._safe_int(
            self._observation_value(latest_by_parameter, "weather")
        )
        precipitation = self._observation_value(latest_by_parameter, "precipitation")
        cloud_cover = self._observation_value(latest_by_parameter, "cloud_cover")
        visibility = self._observation_value(
            latest_by_parameter, "visibility"
        ) or self._observation_value(latest_by_parameter, "visibility_mean")

        observed_at = max(
            (
                properties.get("observed")
                for properties in latest_by_parameter.values()
                if properties.get("observed")
            ),
            default=None,
        )

        self.current_data = {
            "time": self._parse_datetime(observed_at),
            "temperature": self._observation_value(latest_by_parameter, "temperature"),
            "dew_point": self._observation_value(latest_by_parameter, "dew_point"),
            "humidity": self._observation_value(latest_by_parameter, "humidity"),
            "pressure": self._observation_value(latest_by_parameter, "pressure")
            or self._observation_value(latest_by_parameter, "pressure_station"),
            "wind_speed": self._observation_value(latest_by_parameter, "wind_speed"),
            "wind_gust": self._observation_value(latest_by_parameter, "wind_gust"),
            "wind_direction": self._observation_value(
                latest_by_parameter, "wind_direction"
            ),
            "visibility": visibility,
            "cloud_cover": cloud_cover,
            "precipitation": precipitation,
            "weather_code": self._map_condition(
                weather_code, cloud_cover, precipitation, visibility
            ),
            "station_id": self.station_id,
        }

    def _observation_value(
        self,
        latest_by_parameter: dict[str, dict[str, Any]],
        key: str,
    ) -> float | None:
        """Return a normalized observation value for a logical key."""
        parameter_id = OBSERVATION_PARAMETERS[key]
        properties = latest_by_parameter.get(parameter_id)
        if properties is None:
            return None

        value = properties.get("value")
        if value is None:
            return None
        return float(value)

    async def _fetch_forecast_data(self, collection_id: str) -> None:
        """Fetch forecast data from the DMI EDR API."""
        now = dt_util.utcnow()
        end_time = now + timedelta(days=MAX_FORECAST_DAYS)

        params = {
            "coords": f"POINT({self.longitude} {self.latitude})",
            "datetime": f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "parameter-name": ",".join(EDR_PARAMETERS.values()),
            "crs": "crs84",
            "f": "CoverageJSON",
        }
        endpoint = f"{EDR_COLLECTIONS_ENDPOINT}/{collection_id}{EDR_POSITION_QUERY}"
        data = await self._make_request(DMI_EDR_BASE_URL, endpoint, params)
        self._process_edr_data(data)

    def _process_edr_data(self, data: dict[str, Any]) -> None:
        """Process CoverageJSON forecast data from the EDR API."""
        if not data or "ranges" not in data:
            raise RuntimeError("No forecast data received from DMI EDR API")

        ranges = data["ranges"]
        time_values = (
            data.get("domain", {}).get("axes", {}).get("t", {}).get("values", [])
        )
        if not time_values:
            raise RuntimeError("No time values found in DMI EDR response")

        hourly_data: list[dict[str, Any]] = []
        for index, time_str in enumerate(time_values):
            time_obj = self._parse_datetime(time_str)
            cloud_cover = self._extract_parameter_value(
                ranges, EDR_PARAMETERS["cloud_cover"], index
            )
            precipitation = self._extract_parameter_value(
                ranges, EDR_PARAMETERS["precipitation"], index
            )

            hourly_data.append(
                {
                    "time": time_obj,
                    "temperature": self._extract_parameter_value(
                        ranges, EDR_PARAMETERS["temperature"], index
                    ),
                    "pressure": self._extract_parameter_value(
                        ranges, EDR_PARAMETERS["pressure"], index
                    ),
                    "humidity": self._extract_parameter_value(
                        ranges, EDR_PARAMETERS["humidity"], index
                    ),
                    "wind_speed": self._extract_parameter_value(
                        ranges, EDR_PARAMETERS["wind_speed"], index
                    ),
                    "wind_gust": self._extract_parameter_value(
                        ranges, EDR_PARAMETERS["wind_gust"], index
                    ),
                    "wind_direction": None,
                    "precipitation": precipitation,
                    "cloud_cover": cloud_cover,
                    "dew_point": self._extract_parameter_value(
                        ranges, EDR_PARAMETERS["dew_point"], index
                    ),
                    "weather_code": self._map_condition(
                        None, cloud_cover, precipitation, None
                    ),
                }
            )

        if not hourly_data:
            raise RuntimeError("No usable forecast entries returned by DMI EDR API")

        self.hourly_forecast_data = hourly_data[1:25]
        self.forecast_data = hourly_data[1:]

        daily_groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for entry in hourly_data[1:]:
            daily_groups[entry["time"].date()].append(entry)

        daily_data: list[dict[str, Any]] = []
        condition_priority = [
            "lightning-rainy",
            "snowy-rainy",
            "snowy",
            "rainy",
            "fog",
            "cloudy",
            "partlycloudy",
            "sunny",
        ]
        for day_date in sorted(daily_groups.keys()):
            entries = daily_groups[day_date]
            temps = [e["temperature"] for e in entries if e["temperature"] is not None]
            precips = [
                e["precipitation"] for e in entries if e["precipitation"] is not None
            ]
            winds = [e["wind_speed"] for e in entries if e["wind_speed"] is not None]
            gusts = [e["wind_gust"] for e in entries if e["wind_gust"] is not None]
            humidities = [e["humidity"] for e in entries if e["humidity"] is not None]
            pressures = [e["pressure"] for e in entries if e["pressure"] is not None]
            dew_points = [e["dew_point"] for e in entries if e["dew_point"] is not None]
            clouds = [e["cloud_cover"] for e in entries if e["cloud_cover"] is not None]
            conditions = [
                e["weather_code"] for e in entries if e["weather_code"] is not None
            ]
            dominant = next(
                (
                    condition
                    for condition in condition_priority
                    if condition in conditions
                ),
                "sunny",
            )

            daily_data.append(
                {
                    "time": datetime.combine(day_date, datetime.min.time()).replace(
                        tzinfo=dt_util.UTC
                    ),
                    "temperature_max": max(temps) if temps else None,
                    "temperature_min": min(temps) if temps else None,
                    "precipitation": sum(precips) if precips else None,
                    "wind_speed": max(winds) if winds else None,
                    "wind_gust": max(gusts) if gusts else None,
                    "wind_direction": None,
                    "humidity": round(sum(humidities) / len(humidities), 1)
                    if humidities
                    else None,
                    "pressure": round(sum(pressures) / len(pressures), 1)
                    if pressures
                    else None,
                    "dew_point": round(sum(dew_points) / len(dew_points), 1)
                    if dew_points
                    else None,
                    "cloud_cover": round(sum(clouds) / len(clouds), 1)
                    if clouds
                    else None,
                    "weather_code": dominant,
                }
            )

        self.daily_forecast_data = daily_data

    def _extract_parameter_value(
        self,
        ranges: dict[str, Any],
        parameter: str,
        time_index: int,
    ) -> float | None:
        """Extract and normalize one forecast value from the EDR ranges block."""
        values = ranges.get(parameter, {}).get("values")
        if values is None or time_index >= len(values):
            return None

        value = values[time_index]
        if value is None:
            return None

        if (
            parameter in {EDR_PARAMETERS["temperature"], EDR_PARAMETERS["dew_point"]}
            and value > 200
        ):
            value = value - 273.15
        if parameter == EDR_PARAMETERS["cloud_cover"] and value <= 1:
            value = value * 100

        return float(value)

    def _map_condition(
        self,
        weather_code: int | None,
        cloud_cover: float | None,
        precipitation: float | None,
        visibility: float | None,
    ) -> str:
        """Map DMI weather/observation values to Home Assistant weather conditions."""
        if weather_code is not None:
            if weather_code in {
                13,
                17,
                29,
                95,
                96,
                97,
                98,
                99,
                112,
                126,
                190,
                191,
                192,
                193,
                194,
                195,
                196,
            }:
                return (
                    "lightning-rainy"
                    if precipitation and precipitation > 0
                    else "lightning"
                )
            if weather_code in {
                20,
                21,
                23,
                24,
                25,
                50,
                51,
                52,
                53,
                54,
                55,
                56,
                57,
                58,
                59,
                60,
                61,
                62,
                63,
                64,
                65,
                66,
                67,
                68,
                69,
                80,
                81,
                82,
                91,
                92,
                121,
                122,
                123,
                125,
                140,
                141,
                142,
                143,
                144,
                147,
                148,
                150,
                151,
                152,
                153,
                154,
                155,
                156,
                157,
                158,
                160,
                161,
                162,
                163,
                164,
                165,
                166,
                167,
                168,
                180,
                181,
                182,
                183,
                184,
            }:
                return "rainy"
            if weather_code in {
                22,
                26,
                70,
                71,
                72,
                73,
                74,
                75,
                76,
                77,
                78,
                79,
                83,
                84,
                85,
                86,
                87,
                88,
                93,
                94,
                124,
                145,
                146,
                167,
                168,
                170,
                171,
                172,
                173,
                174,
                175,
                176,
                177,
                178,
                185,
                186,
                187,
            }:
                return "snowy"

        if precipitation is not None and precipitation > 0.1:
            return "rainy"
        if cloud_cover is not None and cloud_cover >= 80:
            return "cloudy"
        if cloud_cover is not None and cloud_cover >= 20:
            return "partlycloudy"
        return "sunny"

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse an RFC3339 datetime into a timezone-aware object."""
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _safe_int(self, value: float | None) -> int | None:
        """Convert a numeric value to int when available."""
        if value is None:
            return None
        return int(value)
