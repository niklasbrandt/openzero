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
		import re
		text = re.sub(r'</?(en|de)>', '', text)
		voice = "alloy"  # XTTS is multilingual and auto-detects language
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
	else:
		# Piper (tts-1) is monolingual. We split by <en> and <de> tags to support multi-language text.
		import re
		chunks = re.split(r'(</?en>|</?de>)', text)
		combined_audio = b""
		
		current_lang = language
		current_voice = VOICE_MAP.get(current_lang, "alloy")
		
		# Merge split parts
		async with httpx.AsyncClient(timeout=120.0) as client:
			buffer = ""
			for token in chunks:
				if token in ("<en>", "<de>"):
					# Generate anything in buffer before switching
					if buffer.strip():
						data = {"model": model, "input": buffer.strip(), "voice": current_voice, "speed": 0.85}
						response = await client.post(url, json=data)
						if response.status_code == 200:
							combined_audio += response.content
					buffer = ""
					current_lang = token[1:-1]
					current_voice = VOICE_MAP.get(current_lang, "alloy")
				elif token in ("</en>", "</de>"):
					if buffer.strip():
						data = {"model": model, "input": buffer.strip(), "voice": current_voice, "speed": 0.85}
						response = await client.post(url, json=data)
						if response.status_code == 200:
							combined_audio += response.content
					buffer = ""
					current_lang = language # Revert to default
					current_voice = VOICE_MAP.get(current_lang, "alloy")
				else:
					buffer += token
			
			if buffer.strip():
				data = {"model": model, "input": buffer.strip(), "voice": current_voice, "speed": 0.85}
				response = await client.post(url, json=data)
				if response.status_code == 200:
					combined_audio += response.content
		
		if not combined_audio:
			raise Exception("TTS generation failed: No audio generated")
		return combined_audio

