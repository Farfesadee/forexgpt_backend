import logging
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.database import get_db

logger = logging.getLogger(__name__)
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        client = get_db()
        user_response = client.auth.get_user(token)
        if user_response.user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token.")
        logger.info(f"Token verified for user: {user_response.user.id}")
        return {
            "user_id": str(user_response.user.id),
            "email": user_response.user.email,
            "token": token,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token.")