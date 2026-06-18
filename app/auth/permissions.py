from fastapi import HTTPException, status, Depends
from app.models import User, RoleEnum
from app.auth.jwt_handler import get_current_user

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

async def require_participant(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != RoleEnum.PARTICIPANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Participant access required"
        )
    return current_user
