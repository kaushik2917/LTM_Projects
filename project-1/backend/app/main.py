from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.status import router as status_router
from app.api.incidents import router as incidents_router
from app.api.evidence import router as evidence_router
from app.api.research import router as research_router
from app.api.workflow import router as workflow_router
from app.api.defense import router as defense_router


app = FastAPI(
    title="Intelligent Cyberattack Prediction and Prevention API",
    description=(
        "Backend for the Intelligent Framework for Prediction and "
        "Prevention of Cyberattack Using Digital Evidence Analysis"
    ),
    version="0.1.0",
)


# ---------------------------------------------------------
# CORS CONFIGURATION
# Allows the Next.js frontend to communicate with FastAPI
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# API ROUTERS
# ---------------------------------------------------------

app.include_router(status_router)
app.include_router(incidents_router)
app.include_router(evidence_router)
app.include_router(research_router)
app.include_router(workflow_router)
app.include_router(defense_router)


# ---------------------------------------------------------
# ROOT ENDPOINT
# ---------------------------------------------------------

@app.get("/")
def root():
    return {
        "system": "Cyberattack Prediction and Prevention Framework",
        "message": (
            "Intelligent Cyberattack Prediction and Prevention "
            "Backend is online"
        ),
        "status": "online",
    }
