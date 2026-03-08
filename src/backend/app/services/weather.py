from typing import Optional
import httpx
import logging

logger = logging.getLogger(__name__)

# WMO Weather Code mapping
_WMO_CODES = {
	0: "Clear sky",
	1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
	45: "Fog", 48: "Depositing rime fog",
	51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
	56: "Freezing drizzle", 57: "Heavy freezing drizzle",
	61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
	66: "Freezing rain", 67: "Heavy freezing rain",
	71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
	77: "Snow grains",
	80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
	85: "Slight snow showers", 86: "Heavy snow showers",
	95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail"
}

def _describe_code(code: int) -> str:
	return _WMO_CODES.get(code, "Variable conditions")

async def get_weather_forecast(location_name: Optional[str] = None) -> str:
	"""
	Fetches an hourly weather forecast for today, summarized into
	morning / afternoon / evening segments with precipitation and wind.
	If no location is provided, uses settings.USER_LOCATION.
	"""
	from app.services.timezone import get_user_location
	location = location_name or get_user_location()
	if not location:
		return "Weather location not configured."

	try:
		# 1. Geocoding: Get lat/lon for the location name
		# Open-Meteo geocoding works best with just the city name (comma-separated format: "City, CC")
		search_name = location.split(",")[0].strip()
		geocoding_url = f"https://geocoding-api.open-meteo.com/v1/search?name={search_name}&count=1&language=en&format=json"
		async with httpx.AsyncClient(timeout=10.0) as client:
			geo_resp = await client.get(geocoding_url)
			geo_resp.raise_for_status()
			geo_data = geo_resp.json()

			if not geo_data.get("results"):
				return f"Could not find coordinates for: {location}"

			city = geo_data["results"][0]
			lat, lon = city["latitude"], city["longitude"]
			display_name = f"{city.get('name')}, {city.get('country')}"

			# 2. Fetch hourly + daily data for a rich forecast
			weather_url = (
				f"https://api.open-meteo.com/v1/forecast?"
				f"latitude={lat}&longitude={lon}"
				f"&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,wind_speed_10m_max,sunrise,sunset"
				f"&hourly=temperature_2m,weather_code,precipitation_probability,wind_speed_10m"
				f"&timezone=auto&forecast_days=1"
			)
			w_resp = await client.get(weather_url)
			w_resp.raise_for_status()
			w_data = w_resp.json()

			daily = w_data.get("daily", {})
			hourly = w_data.get("hourly", {})
			if not daily:
				return "No weather data available."

			# Daily overview
			max_temp = daily["temperature_2m_max"][0]
			min_temp = daily["temperature_2m_min"][0]
			daily_code = daily["weather_code"][0]
			precip_sum = daily.get("precipitation_sum", [0])[0]
			wind_max = daily.get("wind_speed_10m_max", [0])[0]
			sunrise = daily.get("sunrise", [""])[0].split("T")[1][:5] if daily.get("sunrise") else ""
			sunset = daily.get("sunset", [""])[0].split("T")[1][:5] if daily.get("sunset") else ""

			lines = [f"Weather in {display_name}: {_describe_code(daily_code)}"]
			lines.append(f"Temperature: {min_temp}°C to {max_temp}°C")

			if precip_sum > 0:
				lines.append(f"Total precipitation: {precip_sum} mm")
			if wind_max > 0:
				lines.append(f"Max wind: {wind_max} km/h")
			if sunrise and sunset:
				lines.append(f"Sunrise {sunrise} / Sunset {sunset}")

			# 3. Hourly breakdown by time segment
			h_temps = hourly.get("temperature_2m", [])
			h_codes = hourly.get("weather_code", [])
			h_precip = hourly.get("precipitation_probability", [])
			h_wind = hourly.get("wind_speed_10m", [])

			if len(h_temps) >= 23:
				segments = [
					("Morning (6-10)", 6, 10),
					("Midday (10-13)", 10, 13),
					("Afternoon (13-17)", 13, 17),
					("Evening (17-21)", 17, 21),
					("Night (21-24)", 21, 24),
				]
				for label, start, end in segments:
					seg_temps = h_temps[start:end]
					seg_codes = h_codes[start:end]
					seg_precip = h_precip[start:end] if h_precip else []
					seg_wind = h_wind[start:end] if h_wind else []

					avg_temp = round(sum(seg_temps) / len(seg_temps), 1)
					# Pick the most significant weather code in the segment
					dominant_code = max(seg_codes, key=lambda c: c)
					max_precip = max(seg_precip) if seg_precip else 0
					avg_wind = round(sum(seg_wind) / len(seg_wind), 1) if seg_wind else 0

					seg_parts = [f"{label}: {_describe_code(dominant_code)}, {avg_temp}°C"]
					if max_precip > 20:
						seg_parts.append(f"rain chance {max_precip}%")
					if avg_wind > 15:
						seg_parts.append(f"wind {avg_wind} km/h")
					lines.append(" | ".join(seg_parts))

			return "\n".join(lines)

	except Exception as e:
		logger.error("Weather fetch error: %s", e)
		return f"Weather service temporarily unavailable for {location}."
