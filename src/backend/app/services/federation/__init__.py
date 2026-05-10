"""Federation layer — opt-in, gated by FEDERATION_ENABLED."""
from app.config import settings

def federation_enabled() -> bool:
	return settings.FEDERATION_ENABLED
