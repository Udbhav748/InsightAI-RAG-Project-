import re
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.app.core.config import settings
import time
from collections import defaultdict
import asyncio

class InputValidator:
    """Input validation utilities for security"""
    
    # Maximum lengths for various inputs
    MAX_QUERY_LENGTH = 1000
    MAX_DOCUMENT_ID_LENGTH = 100
    MAX_SESSION_ID_LENGTH = 100
    
    # Allowed characters for document IDs
    DOCUMENT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_]+$')
    
    @classmethod
    def validate_query(cls, query: str) -> str:
        """Validate and sanitize user query"""
        if not query or not query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query cannot be empty"
            )
        
        if len(query) > cls.MAX_QUERY_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Query exceeds maximum length of {cls.MAX_QUERY_LENGTH} characters"
            )
        
        # Remove potentially dangerous characters
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', query)
        return sanitized.strip()
    
    @classmethod
    def validate_document_id(cls, doc_id: str) -> str:
        """Validate document ID format"""
        if not doc_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document ID cannot be empty"
            )
        
        if len(doc_id) > cls.MAX_DOCUMENT_ID_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document ID exceeds maximum length of {cls.MAX_DOCUMENT_ID_LENGTH} characters"
            )
        
        if not cls.DOCUMENT_ID_PATTERN.match(doc_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document ID contains invalid characters"
            )
        
        return doc_id
    
    @classmethod
    def validate_session_id(cls, session_id: str) -> str:
        """Validate session ID format"""
        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session ID cannot be empty"
            )
        
        if len(session_id) > cls.MAX_SESSION_ID_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session ID exceeds maximum length of {cls.MAX_SESSION_ID_LENGTH} characters"
            )
        
        return session_id

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.lock = asyncio.Lock()
    
    async def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed under rate limit"""
        async with self.lock:
            now = time.time()
            # Clean old requests
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id]
                if now - req_time < self.window_seconds
            ]
            
            if len(self.requests[client_id]) >= self.max_requests:
                return False
            
            self.requests[client_id].append(now)
            return True

# Global rate limiter instance
rate_limiter = RateLimiter(
    max_requests=getattr(settings, 'RATE_LIMIT_PER_MINUTE', 60),
    window_seconds=60
)

async def rate_limit_middleware(request: Request, call_next):
    """Middleware to enforce rate limiting"""
    client_id = request.client.host
    
    if not await rate_limiter.is_allowed(client_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": "60"}
        )
    
    response = await call_next(request)
    return response

# Security headers middleware
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    
    return response
