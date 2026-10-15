from fastapi import APIRouter


router = APIRouter(
    prefix="/api",
    tags=["System"]
)


@router.get("/status")
def get_status():
    return {
        "system": "Cyberattack Prediction and Prevention Framework",
        "message": (
            "Intelligent Framework for Prediction and Prevention "
            "of Cyberattack Using Digital Evidence Analysis is online"
        ),
        "status": "online"
    }