from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.cases import router as cases_router
from app.api.routes.health import router as health_router
from app.api.routes.profiles import router as profiles_router


app = FastAPI(title="PAB Operator Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(profiles_router)
app.include_router(cases_router)
