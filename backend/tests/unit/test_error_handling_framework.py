"""
Tests for Error Handling and Logging Framework
=============================================

Comprehensive tests for the error handling, logging, retry logic,
and middleware components.
"""

import pytest
import json
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.core.exceptions import (
    NewsAssistantError,
    ValidationError,
    NotFoundError,
    ExternalServiceError,
    ErrorSeverity,
    ErrorCategory
)
from src.core.logging import (
    get_logger,
    set_correlation_id,
    get_correlation_id,
    log_exception,
    log_performance,
    StructuredFormatter,
    DevelopmentFormatter
)
from src.core.retry import (
    RetryConfig,
    CircuitBreakerConfig,
    CircuitBreaker,
    retry,
    should_retry,
    calculate_delay
)
from src.core.middleware import ErrorHandlingMiddleware, HealthCheckMiddleware


class TestCustomExceptions:
    """Test custom exception classes."""
    
    def test_news_assistant_error_base(self):
        """Test base NewsAssistantError functionality."""
        error = NewsAssistantError(
            message="Test error",
            error_code="TEST_ERROR",
            details={"key": "value"},
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.SYSTEM
        )
        
        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"
        assert error.details == {"key": "value"}
        assert error.severity == ErrorSeverity.HIGH
        assert error.category == ErrorCategory.SYSTEM
        assert error.user_message == "An error occurred while processing your request."
        assert error.timestamp is not None
        
        # Test to_dict method
        error_dict = error.to_dict()
        assert error_dict["error_code"] == "TEST_ERROR"
        assert error_dict["message"] == "Test error"
        assert error_dict["severity"] == "high"
        assert error_dict["category"] == "system"
    
    def test_validation_error(self):
        """Test ValidationError specific behavior."""
        error = ValidationError(
            message="Invalid input",
            field="email"
        )
        
        assert error.severity == ErrorSeverity.LOW
        assert error.category == ErrorCategory.VALIDATION
        assert error.details["field"] == "email"
        assert "Invalid input" in error.user_message
    
    def test_not_found_error(self):
        """Test NotFoundError specific behavior."""
        error = NotFoundError(
            message="Article not found",
            resource_type="Article"
        )
        
        assert error.severity == ErrorSeverity.LOW
        assert error.category == ErrorCategory.BUSINESS_LOGIC
        assert error.details["resource_type"] == "Article"
        assert "Article not found" in error.user_message
    
    def test_external_service_error(self):
        """Test ExternalServiceError with retry logic."""
        error = ExternalServiceError(
            message="API call failed",
            service="OpenAI",
            status_code=500
        )
        
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.category == ErrorCategory.EXTERNAL_API
        assert error.details["service"] == "OpenAI"
        assert error.details["status_code"] == 500
        assert error.retry_after == 60


class TestLogging:
    """Test logging functionality."""
    
    def test_correlation_id(self):
        """Test correlation ID functionality."""
        # Set correlation ID
        corr_id = set_correlation_id("test-123")
        assert corr_id == "test-123"
        assert get_correlation_id() == "test-123"
        
        # Auto-generate correlation ID
        auto_id = set_correlation_id()
        assert auto_id != "test-123"
        assert len(auto_id) == 36  # UUID format
    
    def test_structured_formatter(self):
        """Test structured JSON formatter."""
        import logging
        
        formatter = StructuredFormatter()
        
        # Create log record
        logger = logging.getLogger("test")
        record = logger.makeRecord(
            name="test",
            level=logging.INFO,
            fn="",
            lno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Add correlation ID
        set_correlation_id("test-corr-id")
        
        # Format record
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"
        assert log_data["correlation_id"] == "test-corr-id"
        assert "timestamp" in log_data
    
    def test_development_formatter(self):
        """Test development formatter with colors."""
        import logging
        
        formatter = DevelopmentFormatter("%(levelname)s | %(correlation_id)s | %(message)s")
        
        # Set correlation ID
        set_correlation_id("dev-123")
        
        # Create log record
        logger = logging.getLogger("test")
        record = logger.makeRecord(
            name="test",
            level=logging.INFO,
            fn="",
            lno=1,
            msg="Development test",
            args=(),
            exc_info=None
        )
        
        # Format record
        formatted = formatter.format(record)
        
        assert "dev-123" in formatted
        assert "Development test" in formatted
    
    def test_log_exception(self):
        """Test exception logging with structured data."""
        logger = get_logger("test")
        
        with patch.object(logger, 'error') as mock_error:
            try:
                raise ValidationError("Test validation error", field="test_field")
            except ValidationError as e:
                log_exception(logger, e, "Validation failed", extra_field="extra_value")
            
            mock_error.assert_called_once()
            call_args = mock_error.call_args
            
            assert "Validation failed" in call_args[0]
            assert call_args[1]["exc_info"] is True
            assert call_args[1]["extra"]["exception_type"] == "ValidationError"
            assert call_args[1]["extra"]["extra_field"] == "extra_value"
    
    def test_log_performance(self):
        """Test performance logging."""
        logger = get_logger("test")
        
        with patch.object(logger, 'log') as mock_log:
            log_performance(logger, "test_operation", 150.5, success=True, user_id="123")
            
            mock_log.assert_called_once()
            call_args = mock_log.call_args
            
            assert call_args[0][0] == 20  # INFO level
            assert "test_operation" in call_args[0][1]
            assert call_args[1]["extra"]["duration_ms"] == 150.5
            assert call_args[1]["extra"]["success"] is True
            assert call_args[1]["extra"]["user_id"] == "123"


class TestRetryLogic:
    """Test retry and circuit breaker functionality."""
    
    def test_retry_config_defaults(self):
        """Test default retry configuration."""
        config = RetryConfig()
        
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
    
    def test_calculate_delay(self):
        """Test delay calculation with exponential backoff."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=10.0, jitter=False)
        
        # Test exponential backoff
        assert calculate_delay(1, config) == 1.0
        assert calculate_delay(2, config) == 2.0
        assert calculate_delay(3, config) == 4.0
        assert calculate_delay(4, config) == 8.0
        assert calculate_delay(5, config) == 10.0  # Capped at max_delay
    
    def test_should_retry_logic(self):
        """Test retry decision logic."""
        config = RetryConfig()
        
        # Should retry external service errors
        assert should_retry(ExternalServiceError("API failed"), config) is True
        
        # Should not retry validation errors
        assert should_retry(ValidationError("Invalid input"), config) is False
        
        # Should handle rate limit errors based on retry_after
        rate_limit_short = ExternalServiceError("Rate limited", retry_after=30)
        rate_limit_long = ExternalServiceError("Rate limited", retry_after=600)
        
        # Note: RateLimitError is in stop_on by default, so these would be False
        # But ExternalServiceError should retry
        assert should_retry(rate_limit_short, config) is True
        assert should_retry(rate_limit_long, config) is True
    
    @pytest.mark.asyncio
    async def test_retry_decorator_success(self):
        """Test retry decorator with successful operation."""
        call_count = 0
        
        @retry(RetryConfig(max_attempts=3))
        async def test_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await test_function()
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_decorator_eventual_success(self):
        """Test retry decorator with eventual success."""
        call_count = 0
        
        @retry(RetryConfig(max_attempts=3, base_delay=0.01))
        async def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ExternalServiceError("Temporary failure")
            return "success"
        
        result = await test_function()
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_decorator_max_attempts(self):
        """Test retry decorator hitting max attempts."""
        call_count = 0
        
        @retry(RetryConfig(max_attempts=2, base_delay=0.01))
        async def test_function():
            nonlocal call_count
            call_count += 1
            raise ExternalServiceError("Persistent failure")
        
        with pytest.raises(ExternalServiceError):
            await test_function()
        
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed state."""
        config = CircuitBreakerConfig(failure_threshold=3)
        circuit_breaker = CircuitBreaker(config)
        
        # Should allow calls when closed
        result = await circuit_breaker.call(lambda: "success")
        assert result == "success"
        assert circuit_breaker.state.value == "closed"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opening after threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=2, expected_exception=ExternalServiceError)
        circuit_breaker = CircuitBreaker(config)
        
        # First failure
        with pytest.raises(ExternalServiceError):
            await circuit_breaker.call(lambda: (_ for _ in ()).throw(ExternalServiceError("Failure 1")))
        
        assert circuit_breaker.state.value == "closed"
        assert circuit_breaker.failure_count == 1
        
        # Second failure - should open circuit
        with pytest.raises(ExternalServiceError):
            await circuit_breaker.call(lambda: (_ for _ in ()).throw(ExternalServiceError("Failure 2")))
        
        assert circuit_breaker.state.value == "open"
        assert circuit_breaker.failure_count == 2
        
        # Next call should be blocked
        with pytest.raises(ExternalServiceError) as exc_info:
            await circuit_breaker.call(lambda: "success")
        
        assert "Circuit breaker is OPEN" in str(exc_info.value)


class TestMiddleware:
    """Test middleware functionality."""
    
    def test_error_handling_middleware_integration(self):
        """Test error handling middleware with FastAPI."""
        from fastapi import FastAPI
        
        app = FastAPI()
        app.add_middleware(ErrorHandlingMiddleware)
        
        @app.get("/test-error")
        async def test_error():
            raise ValidationError("Test validation error", field="test")
        
        @app.get("/test-success")
        async def test_success():
            return {"message": "success"}
        
        client = TestClient(app)
        
        # Test successful request
        response = client.get("/test-success")
        assert response.status_code == 200
        assert "X-Correlation-ID" in response.headers
        
        # Test error handling
        response = client.get("/test-error")
        assert response.status_code == 400
        assert "X-Correlation-ID" in response.headers
        
        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == "ValidationError"
    
    def test_health_check_middleware_metrics(self):
        """Test health check middleware metrics collection."""
        from fastapi import FastAPI
        
        app = FastAPI()
        health_middleware = HealthCheckMiddleware(app)
        app.add_middleware(HealthCheckMiddleware)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        @app.get("/metrics")
        async def get_metrics():
            return health_middleware.get_metrics()
        
        client = TestClient(app)
        
        # Make a metrics request
        response = client.get("/metrics")
        metrics = response.json()
        
        # Check that metrics structure exists with proper fields
        assert "request_count" in metrics
        assert "error_count" in metrics
        assert "error_rate" in metrics
        assert "uptime_seconds" in metrics
        assert isinstance(metrics["request_count"], int)
        assert isinstance(metrics["error_count"], int)


class TestIntegration:
    """Integration tests for the complete error handling system."""
    
    @pytest.mark.asyncio
    async def test_complete_error_flow(self):
        """Test complete error handling flow from exception to response."""
        # This would test the full flow in a real application
        # For now, test individual components work together
        
        # Set correlation ID
        set_correlation_id("integration-test")
        
        # Create a custom error
        error = ExternalServiceError(
            message="Integration test error",
            service="TestService",
            status_code=503
        )
        
        # Verify error properties
        assert error.category == ErrorCategory.EXTERNAL_API
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.retry_after == 60
        
        # Test error serialization
        error_dict = error.to_dict()
        assert error_dict["error_code"] == "ExternalServiceError"
        assert error_dict["details"]["service"] == "TestService"
        
        # Test logging with correlation ID
        logger = get_logger("integration_test")
        
        with patch.object(logger, 'error') as mock_error:
            log_exception(logger, error, "Integration test failed")
            
            # Verify logging call
            mock_error.assert_called_once()
            call_args = mock_error.call_args
            assert "Integration test failed" in call_args[0]
            assert call_args[1]["extra"]["exception_type"] == "ExternalServiceError"
