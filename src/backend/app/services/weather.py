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

_WMO_CODES_DE = {
	0: "Klarer Himmel",
	1: "Überwiegend klar", 2: "Teilweise bewölkt", 3: "Bedeckt",
	45: "Nebel", 48: "Raureifnebel",
	51: "Leichter Nieselregen", 53: "Mäßiger Nieselregen", 55: "Dichter Nieselregen",
	56: "Gefrierender Nieselregen", 57: "Starker gefrierender Nieselregen",
	61: "Leichter Regen", 63: "Mäßiger Regen", 65: "Starker Regen",
	66: "Gefrierender Regen", 67: "Starker gefrierender Regen",
	71: "Leichter Schneefall", 73: "Mäßiger Schneefall", 75: "Starker Schneefall",
	77: "Schneegriesel",
	80: "Leichte Regenschauer", 81: "Mäßige Regenschauer", 82: "Heftige Regenschauer",
	85: "Leichte Schneeschauer", 86: "Starke Schneeschauer",
	95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Schweres Gewitter mit Hagel"
}

def _describe_code(code: int, lang: str = "en") -> str:
	if lang == "de":
		return _WMO_CODES_DE.get(code, "Wechselhaft")
	return _WMO_CODES.get(code, "Variable conditions")

async def get_weather_forecast(location_name: Optional[str] = None, lang: str = "en") -> str:
	"""
	Fetches an hourly weather forecast for today, summarized into
	segments with precipitation and wind.
	If no location is provided, uses settings.USER_LOCATION.
	"""
	from app.services.timezone import get_user_location
	location = location_name or get_user_location()
	if not location:
		return "Wetterstandort nicht konfiguriert." if lang == "de" else "Weather location not configured."

	try:
		# 1. Geocoding: Get lat/lon for the location name
		search_name = location.split(",")[0].strip()
		geocoding_url = f"https://geocoding-api.open-meteo.com/v1/search?name={search_name}&count=1&language=en&format=json"
		async with httpx.AsyncClient(timeout=10.0) as client:
			geo_resp = await client.get(geocoding_url)
			geo_resp.raise_for_status()
			geo_data = geo_resp.json()

			if not geo_data.get("results"):
				return f"Konnte keine Koordinaten finden für: {location}" if lang == "de" else f"Could not find coordinates for: {location}"

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
				return "Keine Wetterdaten verfügbar." if lang == "de" else "No weather data available."

			# Daily overview
			max_temp = daily["temperature_2m_max"][0]
			min_temp = daily["temperature_2m_min"][0]
			daily_code = daily["weather_code"][0]
			precip_sum = daily.get("precipitation_sum", [0])[0]
			wind_max = daily.get("wind_speed_10m_max", [0])[0]
			sunrise = daily.get("sunrise", [""])[0].split("T")[1][:5] if daily.get("sunrise") else ""
			sunset = daily.get("sunset", [""])[0].split("T")[1][:5] if daily.get("sunset") else ""

			if lang == "de":
				lines = [f"🌡️ Wetter in {display_name}: {_describe_code(daily_code, lang)}"]
			else:
				lines = [f"🌡️ Weather in {display_name}: {_describe_code(daily_code, lang)}"]

			# 3. Hourly breakdown by time segment
			h_temps = hourly.get("temperature_2m", [])
			h_codes = hourly.get("weather_code", [])
			h_precip = hourly.get("precipitation_probability", [])
			h_wind = hourly.get("wind_speed_10m", [])

			if len(h_temps) >= 24:
				segments = [
					("00-03", 0, 3),
					("03-07", 3, 7),
					("07-09", 7, 9),
					("09-11", 9, 11),
					("11-13", 11, 13),
					("13-15", 13, 15),
					("15-17", 15, 17),
					("17-18", 17, 18),
					("18-19", 18, 19),
					("19-20", 19, 20),
					("20-22", 20, 22),
					("22-00", 22, 24),
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

					if lang == "de":
						seg_parts = [f"• {label} Uhr: {str(avg_temp).replace('.', ',')}°C ({_describe_code(dominant_code, lang)})"]
					else:
						seg_parts = [f"• {label}: {avg_temp}°C ({_describe_code(dominant_code, lang)})"]

					# Always include wind as requested by user
					if lang == "de":
						wind_str = f"Wind: {avg_wind} km/h"
						rain_str = f"Regen: {max_precip}%" if max_precip > 0 else ""
					else:
						wind_str = f"Wind: {avg_wind} km/h"
						rain_str = f"Rain: {max_precip}%" if max_precip > 0 else ""

					if rain_str:
						seg_parts.append(f"{rain_str} | {wind_str}")
					else:
						seg_parts.append(wind_str)

					lines.append(" | ".join(seg_parts))

			# Append summary stats
			lines.append("")
			if lang == "de":
				lines.append(f"Tageshöchstwert: {str(max_temp).replace('.', ',')}°C | Niederschlag: {str(precip_sum).replace('.', ',')} mm")
				if sunrise and sunset:
					lines.append(f"Sonnenaufgang: {sunrise} | Sonnenuntergang: {sunset}")
			else:
				lines.append(f"Max: {max_temp}°C | Precip: {precip_sum} mm")
				if sunrise and sunset:
					lines.append(f"Sunrise: {sunrise} | Sunset: {sunset}")

			return "\n".join(lines)

	except Exception as e:
		logger.error("Weather fetch error: %s", e)
		if lang == "de":
			return f"Wetterdienst vorübergehend nicht erreichbar für {location}."
		return f"Weather service temporarily unavailable for {location}."
