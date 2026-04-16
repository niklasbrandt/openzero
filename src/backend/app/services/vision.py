import base64
import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

_CAPTION_PROMPT = (
	"Describe what you see. "
	"If it is a whiteboard, sticky notes, or handwritten list, extract every item verbatim. "
	"If it is a receipt, food, or meal, list all items and quantities. "
	"If it is a document, contract, or form, summarise the subject and key obligations in 2-3 sentences. "
	"Be concise. Output only the description, no preamble."
)

async def caption_image(image_bytes: bytes, user_hint: str = "") -> str:
	"""Describe an image using the configured cloud LLM (multimodal).

	Returns a plain-text description suitable for crew routing.
	Returns an error string prefixed with '[' if vision is unavailable.
	"""
	if not settings.cloud_configured:
		return "[Vision requires a cloud LLM — set LLM_CLOUD_BASE_URL, LLM_CLOUD_API_KEY, and LLM_MODEL_CLOUD]"

	prompt = _CAPTION_PROMPT
	if user_hint.strip():
		prompt += f"\n\nUser context: {user_hint.strip()}"

	b64 = base64.b64encode(image_bytes).decode("utf-8")
	payload = {
		"model": settings.LLM_MODEL_CLOUD,
		"messages": [
			{
				"role": "user",
				"content": [
					{
						"type": "image_url",
						"image_url": {"url": f"data:image/jpeg;base64,{b64}"},
					},
					{"type": "text", "text": prompt},
				],
			}
		],
		"max_tokens": 512,
		"stream": False,
	}
	headers = {
		"Authorization": f"Bearer {settings.LLM_CLOUD_API_KEY}",
		"Content-Type": "application/json",
	}
	url = f"{settings.LLM_CLOUD_BASE_URL.rstrip('/')}/v1/chat/completions"

	try:
		async with httpx.AsyncClient(timeout=60.0) as client:
			response = await client.post(url, json=payload, headers=headers)
			response.raise_for_status()
			data = response.json()
			return data["choices"][0]["message"]["content"].strip()
	except Exception as exc:
		logger.warning("caption_image failed: %s", exc)
		return "[Vision processing failed — check cloud LLM connectivity]"
