"""
Authentication and Authorization utilities
JWT token handling, password hashing, RBAC
"""
import secrets
import bcrypt as _bcrypt
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from db.models import UserRole
from api.runtime import load_config

# Configuration — single source of truth for SECRET_KEY
CONFIG = load_config()
SECRET_KEY = CONFIG.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = CONFIG.token_expire_minutes
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

# Password hashing — use bcrypt directly.

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return _bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8") if isinstance(hashed_password, str) else hashed_password
    )


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token with issuer and audience claims."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iss": "sentinelforge",
        "aud": "sentinelforge-api",
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def decode_token(token: str) -> dict:
    """Decode and verify JWT token with issuer/audience validation."""
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            audience="sentinelforge-api", issuer="sentinelforge"
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Get current authenticated user (without DB dependency)"""
    token = credentials.credentials
    payload = decode_token(token)
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    # Return user data from token
    return {
        "id": user_id,
        "username": payload.get("username"),
        "role": payload.get("role", "viewer")
    }


def require_role(required_role: UserRole):
    """Dependency to check user role"""
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role_value = user.get("role", "viewer")
        required_role_value = required_role.value
        
        # Admin > Operator > Viewer
        role_hierarchy = {
            "admin": 3,
            "operator": 2,
            "viewer": 1
        }
        
        if role_hierarchy.get(user_role_value, 0) < role_hierarchy.get(required_role_value, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        return user
    
    return role_checker



async def require_operator_or_ingest(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
) -> dict:
    """Authorize trusted machine ingestion or an operator/admin JWT."""
    config = load_config()
    supplied = request.headers.get("X-Ingest-Key", "")
    if config.is_production and supplied and config.ingest_api_key:
        if secrets.compare_digest(supplied, config.ingest_api_key):
            return {"id": "ingest", "username": "ingest", "role": "operator", "auth_type": "ingest_key"}
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_current_user(credentials)
    if user.get("role") not in {"operator", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user

# Export
__all__ = [
    'verify_password',
    'get_password_hash',
    'create_access_token',
    'decode_token',
    'get_current_user',
    'require_role',
    'require_operator_or_ingest'
]
