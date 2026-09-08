"""
API Response Models
=================

Standard API response models for consistent error handling and responses.
"""

from typing import List, Optional, Dict, Any, Generic, TypeVar, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field

T = TypeVar('T')


class BaseResponse(BaseModel, Generic[T]):
    """Base API response model."""
    success: bool = Field(..., description="Whether the request was successful")
    message: str = Field(..., description="Response message")
    data: Optional[T] = Field(None, description="Response data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorDetail(BaseModel):
    """Detailed error information."""
    error_code: str = Field(..., description="Error code")
    error_type: str = Field(..., description="Type of error")
    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")


class ErrorResponse(BaseModel):
    """API error response model."""
    success: bool = Field(False, description="Always false for error responses")
    error_code: str = Field(..., description="Error code")
    error_type: str = Field(..., description="Type of error")
    message: str = Field(..., description="Error message")
    details: Optional[List[ErrorDetail]] = Field(None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[str] = Field(None, description="Request identifier for tracking")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated API response model."""
    success: bool = Field(True, description="Whether the request was successful")
    data: List[T] = Field(..., description="Response data items")
    pagination: "PaginationInfo" = Field(..., description="Pagination information")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaginationInfo(BaseModel):
    """Pagination information."""
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")
    total_items: int = Field(..., ge=0, description="Total number of items")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_previous: bool = Field(..., description="Whether there is a previous page")
    next_cursor: Optional[str] = Field(
        None,
        description=(
            "Opaque keyset cursor for the next batch (infinite-scroll feed). "
            "Pass back as ?cursor=<value> to continue past this page without "
            "an offset. Null when there are no more results."
        ),
    )


class HealthCheck(BaseModel):
    """API health check response."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    dependencies: Dict[str, str] = Field(default_factory=dict, description="Dependency status")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    uptime: Optional[Union[str, float]] = Field(None, description="Uptime (string or numeric)")
    services: Optional[Dict[str, Any]] = Field(None, description="Service statuses")
    components: Optional[Dict[str, Any]] = Field(None, description="Component health details")


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Overall health status")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    services: Dict[str, str] = Field(default_factory=dict, description="Service status")
    version: str = Field("1.0.0", description="API version")
    uptime: float = Field(0.0, description="Uptime in seconds")
    components: Optional[Dict[str, Dict[str, Any]]] = Field(default_factory=dict, description="Component details")


class ComponentHealth(BaseModel):
    """Individual component health status."""
    name: str = Field(..., description="Component name")
    status: str = Field(..., description="Component status")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AsyncTaskResponse(BaseModel):
    """Response for asynchronous task operations."""
    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Task status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    progress_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)


# Update forward references
PaginatedResponse.model_rebuild()
