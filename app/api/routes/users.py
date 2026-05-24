from uuid import UUID

from fastapi import APIRouter, Depends, Query

from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_admin, get_current_user
from db.session import get_db
from schemas.user import UserCreate, UserUpdate, UserOut, Users
from services.user_service import UserService
from exceptions.app_exceptions import Forbidden

router = APIRouter(prefix="/users", tags=["users"])
service = UserService()


@router.post("/", response_model=UserOut, dependencies=[Depends(require_admin)])
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_db)):
    return await service.create_user(session, payload)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role.value != "admin" and current_user.id != user_id:
        raise Forbidden()

    return await service.get_user(session, user_id)


@router.get("/", response_model=Users, dependencies=[Depends(require_admin)])
async def list_users(
    session: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    items, total = await service.list_users(session, offset=offset, limit=limit)
    return Users(items=items, total=total)


@router.patch("/{user_id}", response_model=UserOut, dependencies=[Depends(require_admin)])
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_db),
):
    return await service.update_user(session, user_id, payload)


@router.delete("/{user_id}", response_model=dict, dependencies=[Depends(require_admin)])
async def delete_user(user_id: UUID, session: AsyncSession = Depends(get_db)):
    await service.delete_user(session, user_id)
    return {"ok": True}
