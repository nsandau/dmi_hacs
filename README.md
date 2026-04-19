# DMI Weather Hybrid for Home Assistant

This integration is a separate Home Assistant integration with its own domain, `dmi_weather_hybrid`, so it can be installed alongside the original `dmi_weather` repository.

It uses two DMI data sources:

- **Current weather** from DMI station observations (`metObs`)
- **Forecasts** from DMI forecast model data (`forecastedr`)

## Installation

### HACS

1. Open **HACS** in Home Assistant.
2. Click the three-dot menu in the top right and choose **Custom repositories**.
3. Add this repository URL:

```text
https://github.com/vondk/dmi_hacs
```

4. Select category **Integration**.
5. Search for **DMI Weather Hybrid**.
6. Install it.

Because this integration uses the domain `dmi_weather_hybrid`, it does not collide with the original `dmi_weather` integration.

### Manual installation

Copy `custom_components/dmi_weather_hybrid` into your Home Assistant `config/custom_components/` directory.

## Configuration

Add the integration from **Settings -> Devices & Services -> Add Integration** and select **DMI Weather Hybrid**.

The setup requires:

- `name`
- `latitude`
- `longitude`
- `station_id`
- `update_interval`

`station_id` is required because current values are read from a specific DMI observation station.

Find valid station IDs here:

- https://www.dmi.dk/friedata/dokumentation/data/meteorological-observation-data-stations

## Data behavior

### Current values

Current values come from the configured DMI station when that station provides them:

- temperature
- humidity
- dew point
- pressure
- wind speed
- wind gust
- wind direction
- visibility
- cloud coverage
- weather condition

If the selected station does not publish a specific value, that field is left unavailable instead of being guessed.

### Forecast

Forecast data comes from DMI's HARMONIE EDR model and is exposed as:

- hourly forecast
- daily forecast

The forecast continues to use location coordinates, not the station position.

## Notes

- No API key is required.
- The integration is intended for Denmark, Greenland, and Faroe Islands where DMI station and forecast coverage exists.
- The observation feed is raw station data from DMI and may occasionally have missing parameters.

## Credits

Based on the original DMI Home Assistant work by [@crusell](https://github.com/crusell) and further adapted here into a separate hybrid integration.
