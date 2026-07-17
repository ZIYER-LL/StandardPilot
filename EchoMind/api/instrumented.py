"""StandardPilot application with observability and adaptive execution APIs enabled."""
from api.main import app
from api.observability import router as observability_router
from api.adaptive import router as adaptive_router

app.include_router(observability_router)
app.include_router(adaptive_router)

__all__ = ["app"]
