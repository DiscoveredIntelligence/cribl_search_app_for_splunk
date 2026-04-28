"""
Custom exception classes for the Cribl Search API client.

These exceptions provide specific error types for different failure scenarios,
enabling better error handling and user-friendly error messages.
"""


class CriblSearchError(Exception):
    """
    Base exception for all criblsearch errors.
    
    All other exceptions in this module inherit from this class,
    allowing callers to catch all criblsearch-related errors with
    a single except clause if desired.
    
    Attributes:
        message: Human-readable error description
        details: Optional additional context (e.g., response body, status code)
    """
    
    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(self.message)
    
    def __str__(self):
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class AuthenticationError(CriblSearchError):
    """
    Raised when authentication to Cribl fails.
    
    Common causes:
    - Invalid client_id or client_secret
    - Expired credentials
    - Incorrect Cribl instance URL
    - Network issues reaching the auth endpoint
    """
    
    def __init__(self, message: str = "Authentication failed", details: str = None):
        super().__init__(message, details)


class ConnectionError(CriblSearchError):
    """
    Raised when unable to connect to Cribl.
    
    Common causes:
    - Network connectivity issues
    - Invalid URL
    - Firewall blocking the connection
    - SSL/TLS certificate issues
    - DNS resolution failures
    """
    
    def __init__(self, message: str = "Unable to connect to Cribl", details: str = None):
        super().__init__(message, details)


class JobCreationError(CriblSearchError):
    """
    Raised when search job creation fails.
    
    Common causes:
    - Invalid query syntax
    - Dataset not found
    - Insufficient permissions
    - Server-side error
    """
    
    def __init__(self, message: str = "Failed to create search job", details: str = None):
        super().__init__(message, details)


class JobTimeoutError(CriblSearchError):
    """
    Raised when job status check times out.
    
    This occurs when a search job takes longer than the configured
    timeout (default: 10 minutes / 600 seconds) to complete.
    
    Attributes:
        job_id: The ID of the timed-out job
        elapsed_seconds: How long we waited before timing out
    """
    
    def __init__(self, message: str = "Job timed out", job_id: str = None, 
                 elapsed_seconds: float = None, details: str = None):
        self.job_id = job_id
        self.elapsed_seconds = elapsed_seconds
        if job_id and elapsed_seconds:
            message = f"Job {job_id} timed out after {elapsed_seconds:.1f} seconds"
        super().__init__(message, details)


class ResultsRetrievalError(CriblSearchError):
    """
    Raised when results retrieval fails.
    
    Common causes:
    - Job was cancelled
    - Network error during retrieval
    - Server-side error
    - Results expired
    """
    
    def __init__(self, message: str = "Failed to retrieve results", details: str = None):
        super().__init__(message, details)


class QueryValidationError(CriblSearchError):
    """
    Raised when the search query is invalid.
    
    Common causes:
    - Missing dataset specification
    - Invalid query syntax
    - Empty query
    """
    
    def __init__(self, message: str = "Invalid query", details: str = None):
        super().__init__(message, details)
