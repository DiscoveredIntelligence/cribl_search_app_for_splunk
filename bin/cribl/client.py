"""
HTTP client module for Cribl Search API.

Provides a consistent interface for making HTTP requests to Cribl,
with error handling, logging, and retry logic.
"""

import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import requests
from requests.exceptions import (
    RequestException,
    HTTPError,
    Timeout,
    ConnectionError as RequestsConnectionError,
    SSLError,
    ConnectTimeout,
    ReadTimeout,
    ProxyError,
)

from cribl.exceptions import ConnectionError, AuthenticationError, CriblSearchError
from cribl.config import DEFAULT_HTTP_TIMEOUT
from cribl.logging_utils import sanitize_url_for_logging
from cribl.auth import _create_connection_error


class CriblHTTPClient:
    """
    HTTP client for interacting with the Cribl Search API.
    
    Provides a consistent interface with:
    - Automatic authorization header management
    - Error handling with specific exception types
    - Request/response logging
    - SSL verification configuration
    
    Usage:
        client = CriblHTTPClient(base_url, token, logger)
        response = client.get("/some/endpoint")
        response = client.post("/another/endpoint", data={"key": "value"})
    """
    
    def __init__(
        self,
        base_url: str,
        token: str,
        logger: logging.Logger,
        timeout: int = DEFAULT_HTTP_TIMEOUT,
        verify_ssl: bool = True
    ):
        """
        Initialize the HTTP client.
        
        Args:
            base_url: Base URL for API requests (e.g., "https://cribl.example.com/api/v1/m/")
            token: Bearer token for authentication
            logger: Logger instance for logging
            timeout: Default timeout for requests in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.logger = logger
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        
        # Extract domain for logging
        parsed = urlparse(base_url)
        self.domain = parsed.netloc or base_url.split('/')[0]
        
        # Default headers
        self._headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }
    
    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        """
        Make a GET request.
        
        Args:
            endpoint: API endpoint (will be appended to base_url)
            params: Optional query parameters
            timeout: Optional timeout override
            
        Returns:
            requests.Response object
            
        Raises:
            ConnectionError: If unable to connect
            AuthenticationError: If authentication fails (401/403)
            CriblSearchError: For other HTTP errors
        """
        url = self._build_url(endpoint)
        self.logger.debug(f"GET {sanitize_url_for_logging(url)}")
        
        try:
            response = requests.get(
                url=url,
                headers=self._headers,
                params=params,
                timeout=timeout or self.timeout,
                verify=self.verify_ssl
            )
            self._check_response(response, url)
            return response
            
        except (RequestsConnectionError, Timeout, SSLError, ProxyError) as e:
            raise _create_connection_error(url, e)
    
    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        """
        Make a POST request.
        
        Args:
            endpoint: API endpoint (will be appended to base_url)
            data: JSON data to send in request body
            timeout: Optional timeout override
            
        Returns:
            requests.Response object
            
        Raises:
            ConnectionError: If unable to connect
            AuthenticationError: If authentication fails (401/403)
            CriblSearchError: For other HTTP errors
        """
        url = self._build_url(endpoint)
        self.logger.debug(f"POST {sanitize_url_for_logging(url)}")
        
        try:
            response = requests.post(
                url=url,
                headers=self._headers,
                json=data,
                timeout=timeout or self.timeout,
                verify=self.verify_ssl
            )
            self._check_response(response, url)
            return response
            
        except (RequestsConnectionError, Timeout, SSLError, ProxyError) as e:
            raise _create_connection_error(url, e)
    
    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL from base_url and endpoint.
        
        Args:
            endpoint: API endpoint (may or may not start with /)
            
        Returns:
            Full URL string
        """
        if endpoint.startswith('/'):
            return f"{self.base_url}{endpoint}"
        return f"{self.base_url}/{endpoint}"
    
    def _check_response(self, response: requests.Response, url: str):
        """
        Check response for errors and raise appropriate exceptions.
        
        Args:
            response: Response object to check
            url: URL that was requested (for error messages)
            
        Raises:
            AuthenticationError: For 401/403 responses
            CriblSearchError: For other error responses
        """
        if response.status_code == 401:
            raise AuthenticationError(
                "Unauthorized - token may be invalid or expired",
                details=f"HTTP 401 from {sanitize_url_for_logging(url)}"
            )
        
        if response.status_code == 403:
            raise AuthenticationError(
                "Forbidden - insufficient permissions",
                details=f"HTTP 403 from {sanitize_url_for_logging(url)}"
            )
        
        try:
            response.raise_for_status()
        except HTTPError as e:
            raise CriblSearchError(
                f"HTTP error {response.status_code}",
                details=str(e)
            )


def build_base_url(cribl_url: str, protocol: str = "https://") -> str:
    """
    Build the base API URL from a Cribl URL.
    
    Args:
        cribl_url: Cribl URL (may or may not include protocol)
        protocol: Protocol to use if not included in cribl_url
        
    Returns:
        Base API URL (e.g., "https://cribl.example.com/api/v1/m/")
    """
    if cribl_url.startswith(protocol):
        parsed = urlparse(cribl_url)
        domain = parsed.netloc
    else:
        domain = cribl_url.split('/')[0]
    
    return f"{protocol}{domain}/api/v1/m/"
