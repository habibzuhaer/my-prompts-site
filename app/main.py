from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.endpoints import auth, strategies, alerts
from app.database import engine, Base
import os

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AlertBot Manager API",
    description="API for managing trading alerts",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(strategies.router)
app.include_router(alerts.router)

@app.get("/")
def read_root():
    return {"message": "AlertBot Manager API is running"}
