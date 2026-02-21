import httpx
from app.config import settings

async def generate_speech(text: str) -> bytes:
    """
    Generate speech from text using the local TTS service.
    Returns audio bytes (mp3).
    """
    url = f"{settings.TTS_BASE_URL}/v1/audio/speech"
    data = {
        "model": "tts-1",
        "input": text,
        "voice": "alloy"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=data)
        if response.status_code == 200:
            return response.content
            
    raise Exception(f"TTS generation failed: {response.status_code} - {response.text}")
