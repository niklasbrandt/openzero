import os
import httpx
from app.config import settings
from pydub import AudioSegment
import io

async def transcribe_voice(audio_bytes: bytes) -> str:
    """
    Transcribe voice using Whisper. 
    Can be configured for Local Whisper (via separate container) or Cloud (Groq/OpenAI).
    """
    
    # Convert Ogg/Opus to Wav for compatibility
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="ogg")
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        wav_bytes = buffer.getvalue()
    except Exception as e:
        print(f"Error converting audio: {e}")
        return ""

    # Prefer local Whisper if configured
    if settings.WHISPER_BASE_URL:
        try:
            return await _transcribe_local(wav_bytes)
        except Exception as e:
            print(f"Local transcription failed, falling back: {e}")

    if settings.LLM_PROVIDER == "ollama":
        # If we had a local whisper container, we'd call it here
        # For now, default to Groq if API key is present for transcribed chat
        if settings.GROQ_API_KEY:
            return await _transcribe_groq(wav_bytes)
        elif settings.OPENAI_API_KEY:
            return await _transcribe_openai(wav_bytes)
        else:
            return "[Voice support requires GROQ_API_KEY or OPENAI_API_KEY for transcription]"
    
    return "[Transcription failed: No provider configured]"

async def _transcribe_groq(audio_data: bytes):
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    files = {"file": ("voice.wav", audio_data, "audio/wav")}
    data = {"model": "whisper-large-v3"}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, files=files, data=data)
        if response.status_code == 200:
            return response.json().get("text", "")
    return "[Groq transcription failed]"

async def _transcribe_openai(audio_data: bytes):
    # Standard OpenAI Whisper implementation
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    buffer = io.BytesIO(audio_data)
    buffer.name = "voice.wav"
    
    response = await client.audio.transcriptions.create(
        model="whisper-1", 
        file=buffer
    )
    return response.text

async def _transcribe_local(audio_data: bytes):
    """Call the local whisper-asr-webservice."""
    # This service follows the OpenAI Whisper API format
    url = f"{settings.WHISPER_BASE_URL}/asr?task=transcribe&language=en&output=json"
    files = {"audio_file": ("voice.wav", audio_data, "audio/wav")}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, files=files)
        if response.status_code == 200:
            return response.json().get("text", "").strip()
    
    raise Exception(f"Local whisper ASR failed with status {response.status_code}")
