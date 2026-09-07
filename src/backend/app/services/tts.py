import httpx
from app.config import settings

VOICE_MAP = {
	"en": "alloy",
	"de": "de_DE-thorsten-medium",
}

async def generate_speech(text: str, language: str = "en") -> bytes:
	"""
	Generate speech from text using the local TTS service.
	Returns audio bytes (mp3).
	"""
	if not settings.TTS_BASE_URL:
		raise Exception("TTS service not configured (voice profile disabled)")
	url = f"{settings.TTS_BASE_URL}/v1/audio/speech"
	
	model = settings.TTS_MODEL
	if model == "tts-1-hd":
		voice = "alloy"  # XTTS is multilingual and auto-detects language
	else:
		voice = VOICE_MAP.get(language, "alloy")
	
	data = {
		"model": model,
		"input": text,
		"voice": voice,
		"speed": 0.85
	}
	
	async with httpx.AsyncClient(timeout=120.0) as client:
		response = await client.post(url, json=data)
		if response.status_code == 200:
			return response.content
			
	raise Exception(f"TTS generation failed: {response.status_code} - {response.text}")

