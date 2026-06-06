from fastapi import APIRouter

from .voices import list_voices

router = APIRouter()


@router.get("/voices")
async def voices():
    return list_voices()
