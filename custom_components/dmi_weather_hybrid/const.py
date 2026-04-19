"""Constants for the DMI Weather Hybrid integration."""

DOMAIN = "dmi_weather_hybrid"

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_NAME = "name"
CONF_STATION_ID = "station_id"
DEFAULT_NAME = "DMI Weather Hybrid"

# DMI API configuration
DMI_EDR_BASE_URL = "https://opendataapi.dmi.dk/v1/forecastedr"
DMI_METOBS_BASE_URL = "https://opendataapi.dmi.dk/v2/metObs"

# API endpoints
EDR_COLLECTIONS_ENDPOINT = "/collections"
EDR_POSITION_QUERY = "/position"
METOBS_STATION_ENDPOINT = "/collections/station/items"
METOBS_OBSERVATION_ENDPOINT = "/collections/observation/items"

# API request parameters
DEFAULT_TIMEOUT = 30
MAX_FORECAST_DAYS = 5

CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 30  # minutes

STATION_LOOKUP_URL = "https://www.dmi.dk/friedata/dokumentation/data/meteorological-observation-data-stations"

# EDR parameter mappings for HARMONIE collection
EDR_PARAMETERS = {
    "temperature": "temperature-2m",
    "pressure": "pressure-sealevel",
    "humidity": "relative-humidity-2m",
    "wind_speed": "wind-speed-10m",
    "wind_gust": "gust-wind-speed-10m",
    "precipitation": "total-precipitation",
    "cloud_cover": "fraction-of-cloud-cover",
    "dew_point": "dew-point-temperature-2m",
}

OBSERVATION_PARAMETERS = {
    "temperature": "temp_dry",
    "dew_point": "temp_dew",
    "humidity": "humidity",
    "pressure": "pressure_at_sea",
    "pressure_station": "pressure",
    "wind_speed": "wind_speed",
    "wind_gust": "wind_max",
    "wind_direction": "wind_dir",
    "visibility": "visibility",
    "visibility_mean": "visib_mean_last10min",
    "cloud_cover": "cloud_cover",
    "weather": "weather",
    "precipitation": "precip_past10min",
}
