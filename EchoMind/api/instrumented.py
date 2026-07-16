"""StandardPilot application with observability and conversation APIs enabled."""
from api.main import app
from api.observability import router as observability_router

app.include_router(observability_router)

__all__ = ["app"]
