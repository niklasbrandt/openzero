import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

async def get_weather_forecast(location_name: str = None) -> str:
    """
    Fetches weather forecast for a given location using Open-Meteo.
    If no location is provided, uses settings.USER_LOCATION.
    """
    location = location_name or settings.USER_LOCATION
    if not location:
        return "Weather location not configured."

    try:
        # 1. Geocoding: Get lat/lon for the location name
        geocoding_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=en&format=json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            geo_resp = await client.get(geocoding_url)
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            
            if not geo_data.get("results"):
                return f"Could not find coordinates for: {location}"
            
            city = geo_data["results"][0]
            lat, lon = city["latitude"], city["longitude"]
            display_name = f"{city.get('name')}, {city.get('country')}"

            # 2. Weather: Get forecast
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto"
            )
            w_resp = await client.get(weather_url)
            w_resp.raise_for_status()
            w_data = w_resp.json()
            
            daily = w_data.get("daily", {})
            if not daily:
                return "No weather data available."

            max_temp = daily["temperature_2m_max"][0]
            min_temp = daily["temperature_2m_min"][0]
            code = daily["weathercode"][0]
            
            # Simple weather code mapping (WMO codes)
            weather_desc = {
                0: "Clear sky",
                1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Fog", 48: "Depositing rime fog",
                51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
                61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
                95: "Thunderstorm"
            }.get(code, "Variable conditions")

            return f"Weather in {display_name}: {weather_desc}, {min_temp}°C to {max_temp}°C."

    except Exception as e:
        logger.error(f"Weather fetch error: {e}")
        return f"Weather service temporarily unavailable for {location}."
