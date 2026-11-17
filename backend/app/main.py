from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings
from backend.app.core.database import engine, Base, AsyncSessionLocal
from backend.app.services.catalog_seed import seed_initial_catalog
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.products import router as products_router
from backend.app.api.v1.cart import router as cart_router
from backend.app.api.v1.groups import router as groups_router
from backend.app.api.v1.webhooks import router as webhooks_router
from backend.app.api.v1.ai import router as ai_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist on startup (for SQLite/local dev)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Seed initial catalog if needed
    async with AsyncSessionLocal() as session:
        await seed_initial_catalog(session)

    yield
    await engine.dispose()

app = FastAPI(
    title="ShopCart API",
    description="AI-Powered Collaborative E-Commerce Platform with Dynamic Payment Redistribution",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    settings.FRONTEND_URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(cart_router, prefix="/api/v1")
app.include_router(groups_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "service": "shopcart-backend",
        "version": "1.0.0",
        "env": settings.APP_ENV
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
