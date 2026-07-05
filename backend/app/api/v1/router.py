"""Central API v1 router — registers all route modules."""

from fastapi import APIRouter

from app.api.v1.routes.analytics import router as analytics_router
from app.api.v1.routes.chat import router as chat_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.measurements import router as measurements_router
from app.api.v1.routes.nutrition import router as nutrition_router
from app.api.v1.routes.reviews import router as reviews_router
from app.api.v1.routes.swimming import router as swimming_router
from app.api.v1.routes.users import router as users_router
from app.api.v1.routes.workouts import router as workouts_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(users_router)
api_router.include_router(chat_router)
api_router.include_router(dashboard_router)
api_router.include_router(workouts_router)
api_router.include_router(measurements_router)
api_router.include_router(reviews_router)
api_router.include_router(swimming_router)
api_router.include_router(nutrition_router)
api_router.include_router(analytics_router)
