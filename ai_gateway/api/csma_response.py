"""
CSMA Response Utilities for AI Gateway Service
Implements the CSMAResponse<T> pattern for consistent API responses
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TypeVar, Generic
from fastapi import HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

T = TypeVar('T')

class CSMAMeta(BaseModel):
    """CSMA response metadata"""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    version: str = Field(default="1.0.0")
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    service: str = Field(default="ai-gateway")
    gitlab: Optional[Dict[str, Any]] = Field(default=None)

class CSMAError(BaseModel):
    """CSMA error details"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = Field(default=None)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

class CSMAResponse(BaseModel, Generic[T]):
    """CSMA Response class for consistent API responses"""
    success: bool
    data: Optional[T] = None
    message: str
    errors: List[str] = Field(default_factory=list)
    meta: CSMAMeta = Field(default_factory=CSMAMeta)

    @classmethod
    def success_response(
        cls, 
        data: T, 
        message: str = "Operation completed successfully", 
        **kwargs
    ) -> "CSMAResponse[T]":
        """Create a successful response"""
        return cls(
            success=True,
            data=data,
            message=message,
            meta=CSMAMeta(**kwargs)
        )

    @classmethod
    def error_response(
        cls, 
        message: str, 
        errors: List[str] = None, 
        **kwargs
    ) -> "CSMAResponse[None]":
        """Create an error response"""
        if errors is None:
            errors = []
        return cls(
            success=False,
            data=None,
            message=message,
            errors=errors,
            meta=CSMAMeta(**kwargs)
        )

    def with_gitlab_context(self, gitlab_context: Dict[str, Any]) -> "CSMAResponse[T]":
        """Add GitLab context to the response"""
        self.meta.gitlab = gitlab_context
        return self

    def with_errors(self, errors: List[str]) -> "CSMAResponse[T]":
        """Add errors to the response"""
        self.errors.extend(errors)
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "errors": self.errors,
            "meta": self.meta.dict()
        }

    def to_json_response(self, status_code: int = 200) -> JSONResponse:
        """Convert to FastAPI JSONResponse"""
        return JSONResponse(
            content=self.to_dict(),
            status_code=status_code
        )

class CSMAException(HTTPException):
    """CSMA exception for standardized error handling"""
    
    def __init__(
        self, 
        code: str, 
        message: str, 
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.details = details or {}
        self.timestamp = datetime.utcnow().isoformat()
        self.request_id = str(uuid.uuid4())

    def to_response(self, **kwargs) -> CSMAResponse[None]:
        """Convert to CSMA response"""
        return CSMAResponse.error_response(
            message=self.detail,
            errors=[self.code],
            request_id=self.request_id,
            **kwargs
        )

    def to_json_response(self, **kwargs) -> JSONResponse:
        """Convert to FastAPI JSONResponse"""
        return self.to_response(**kwargs).to_json_response(self.status_code)

# Common error codes
class CSMAErrorCodes:
    """Common CSMA error codes"""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INVALID_REQUEST = "INVALID_REQUEST"
    CONFLICT = "CONFLICT"
    TIMEOUT = "TIMEOUT"
    MODEL_ERROR = "MODEL_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"

# Common error responses
class CSMAErrorResponses:
    """Factory for common CSMA error responses"""
    
    @staticmethod
    def validation_error(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create validation error"""
        return CSMAException(
            code=CSMAErrorCodes.VALIDATION_ERROR,
            message=message,
            status_code=400,
            details=details
        )
    
    @staticmethod
    def authentication_error(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create authentication error"""
        return CSMAException(
            code=CSMAErrorCodes.AUTHENTICATION_ERROR,
            message=message,
            status_code=401,
            details=details
        )
    
    @staticmethod
    def authorization_error(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create authorization error"""
        return CSMAException(
            code=CSMAErrorCodes.AUTHORIZATION_ERROR,
            message=message,
            status_code=403,
            details=details
        )
    
    @staticmethod
    def not_found(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create not found error"""
        return CSMAException(
            code=CSMAErrorCodes.NOT_FOUND,
            message=message,
            status_code=404,
            details=details
        )
    
    @staticmethod
    def internal_error(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create internal error"""
        return CSMAException(
            code=CSMAErrorCodes.INTERNAL_ERROR,
            message=message,
            status_code=500,
            details=details
        )
    
    @staticmethod
    def rate_limit_exceeded(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create rate limit error"""
        return CSMAException(
            code=CSMAErrorCodes.RATE_LIMIT_EXCEEDED,
            message=message,
            status_code=429,
            details=details
        )
    
    @staticmethod
    def service_unavailable(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create service unavailable error"""
        return CSMAException(
            code=CSMAErrorCodes.SERVICE_UNAVAILABLE,
            message=message,
            status_code=503,
            details=details
        )
    
    @staticmethod
    def invalid_request(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create invalid request error"""
        return CSMAException(
            code=CSMAErrorCodes.INVALID_REQUEST,
            message=message,
            status_code=400,
            details=details
        )
    
    @staticmethod
    def conflict(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create conflict error"""
        return CSMAException(
            code=CSMAErrorCodes.CONFLICT,
            message=message,
            status_code=409,
            details=details
        )
    
    @staticmethod
    def timeout(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create timeout error"""
        return CSMAException(
            code=CSMAErrorCodes.TIMEOUT,
            message=message,
            status_code=408,
            details=details
        )
    
    @staticmethod
    def model_error(message: str, details: Optional[Dict[str, Any]] = None) -> CSMAException:
        """Create model error"""
        return CSMAException(
            code=CSMAErrorCodes.MODEL_ERROR,
            message=message,
            status_code=422,
            details=details
        )

# FastAPI exception handler for CSMA errors
async def csma_exception_handler(request, exc: CSMAException) -> JSONResponse:
    """Handle CSMA exceptions in FastAPI"""
    return exc.to_json_response(service="ai-gateway")

# Response helper functions
def csma_success(
    data: Any, 
    message: str = "Operation completed successfully", 
    status_code: int = 200,
    **kwargs
) -> CSMAResponse:
    """Create a successful CSMA response"""
    return CSMAResponse.success_response(
        data=data,
        message=message,
        **kwargs
    ).to_json_response(status_code)

def csma_error(
    message: str, 
    errors: List[str] = None, 
    status_code: int = 400,
    **kwargs
) -> CSMAResponse:
    """Create an error CSMA response"""
    if errors is None:
        errors = []
    return CSMAResponse.error_response(
        message=message,
        errors=errors,
        **kwargs
    ).to_json_response(status_code)
