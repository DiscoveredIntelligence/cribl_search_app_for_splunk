"""
Authentication module for Cribl Search API.

Handles authentication for both Cribl Cloud and on-premises instances.
"""

import logging
import socket
from typing import Tuple
from urllib.parse import urlparse

import requests
from requests.exceptions import (
    RequestException,
    HTTPError,
    SSLError,
    ConnectTimeout,
    ReadTimeout,
    ConnectionError as RequestsConnectionError,
    ProxyError,
    InvalidURL,
)

from cribl.exceptions import AuthenticationError, ConnectionError
from cribl.config import (
    CRIBL_CLOUD_AUTH_URL,
    CRIBL_CLOUD_AUDIENCE,
    CRIBL_CLOUD_INSTANCE,
    DEFAULT_HTTP_TIMEOUT,
)
from cribl.logging_utils import mask_sensitive


def _create_connection_error(url: str, exception: Exception) -> ConnectionError:
    """
    Create a user-friendly ConnectionError based on the type of connection failure.
    
    Args:
        url: The URL that failed to connect
        exception: The original exception
        
    Returns:
        ConnectionError with user-friendly message
    """
    # Extract hostname for error messages
    try:
        parsed = urlparse(url)
        hostname = parsed.netloc or url
    except Exception:
        hostname = url
    
    error_str = str(exception).lower()
    
    # SSL/TLS certificate errors
    if isinstance(exception, SSLError):
        return ConnectionError(
            f"SSL certificate verification failed for {hostname}. "
            "Verify the SSL certificate is valid or check SSL settings.",
            details=str(exception)
        )
    
    # Connection timeout (couldn't establish connection)
    if isinstance(exception, ConnectTimeout):
        return ConnectionError(
            f"Connection to {hostname} timed out. "
            "Verify the URL is correct and the server is reachable.",
            details=str(exception)
        )
    
    # Read timeout (connected but response took too long)
    if isinstance(exception, ReadTimeout):
        return ConnectionError(
            f"Request to {hostname} timed out waiting for response. "
            "The server may be overloaded. Try again later or increase timeout.",
            details=str(exception)
        )
    
    # Proxy errors
    if isinstance(exception, ProxyError):
        return ConnectionError(
            f"Proxy error connecting to {hostname}. "
            "Verify proxy settings are correct.",
            details=str(exception)
        )
    
    # Invalid URL
    if isinstance(exception, InvalidURL):
        return ConnectionError(
            f"Invalid URL: {url}. "
            "Verify the Cribl URL is formatted correctly.",
            details=str(exception)
        )
    
    # DNS resolution failure (check the error string)
    if 'nodename nor servname provided' in error_str or \
       'name or service not known' in error_str or \
       'getaddrinfo failed' in error_str or \
       'failed to resolve' in error_str:
        return ConnectionError(
            f"Cannot resolve hostname '{hostname}'. "
            "Verify the URL is correct and DNS is working.",
            details=str(exception)
        )
    
    # Connection refused
    if 'connection refused' in error_str or \
       'actively refused' in error_str or \
       'errno 111' in error_str:
        return ConnectionError(
            f"Connection refused by {hostname}. "
            "Verify the URL and port are correct and the service is running.",
            details=str(exception)
        )
    
    # Network unreachable
    if 'network unreachable' in error_str or \
       'no route to host' in error_str:
        return ConnectionError(
            f"Network unreachable for {hostname}. "
            "Check network connectivity and firewall settings.",
            details=str(exception)
        )
    
    # Generic connection error with original message
    return ConnectionError(
        f"Unable to connect to {hostname}. "
        "Verify the URL and network connectivity.",
        details=str(exception)
    )


def get_auth_token(
    cribl_instance: str,
    base_url: str,
    client_id: str,
    client_secret: str,
    logger: logging.Logger,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
    verify_ssl: bool = True
) -> str:
    """
    Authenticate with Cribl and obtain an access token.
    
    Handles both Cribl Cloud (OAuth2 client credentials flow) and
    on-premises instances (username/password authentication).
    
    Args:
        cribl_instance: Instance type ("cribl.cloud" for cloud, anything else for on-prem)
        base_url: Base API URL for on-premises instances
        client_id: Client ID (cloud) or username (on-prem)
        client_secret: Client secret (cloud) or password (on-prem)
        logger: Logger instance for logging
        timeout: HTTP request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
        
    Returns:
        Bearer token string (e.g., "Bearer eyJ...")
        
    Raises:
        AuthenticationError: If authentication fails
        ConnectionError: If unable to connect to the auth endpoint
    """
    is_cloud = cribl_instance == CRIBL_CLOUD_INSTANCE
    
    if is_cloud:
        return _authenticate_cloud(client_id, client_secret, logger, timeout, verify_ssl)
    else:
        return _authenticate_onprem(base_url, client_id, client_secret, logger, timeout, verify_ssl)


def _authenticate_cloud(
    client_id: str,
    client_secret: str,
    logger: logging.Logger,
    timeout: int,
    verify_ssl: bool
) -> str:
    """
    Authenticate with Cribl Cloud using OAuth2 client credentials flow.
    
    Args:
        client_id: OAuth2 client ID
        client_secret: OAuth2 client secret
        logger: Logger instance
        timeout: HTTP request timeout
        verify_ssl: Whether to verify SSL certificates
        
    Returns:
        Bearer token string
        
    Raises:
        AuthenticationError: If authentication fails
        ConnectionError: If unable to connect
    """
    logger.debug(f"Authenticating with Cribl Cloud (client_id: {mask_sensitive(client_id)})")
    
    headers = {"content-type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "audience": CRIBL_CLOUD_AUDIENCE
    }
    
    try:
        response = requests.post(
            url=CRIBL_CLOUD_AUTH_URL,
            headers=headers,
            json=data,
            timeout=timeout,
            verify=verify_ssl
        )
        response.raise_for_status()
        
    except HTTPError as e:
        status_code = e.response.status_code if e.response is not None else "unknown"
        if status_code == 401:
            raise AuthenticationError(
                "Invalid client credentials",
                details=f"HTTP 401 from {CRIBL_CLOUD_AUTH_URL}"
            )
        elif status_code == 403:
            raise AuthenticationError(
                "Access forbidden - check client permissions",
                details=f"HTTP 403 from {CRIBL_CLOUD_AUTH_URL}"
            )
        else:
            raise AuthenticationError(
                f"Authentication request failed with HTTP {status_code}",
                details=str(e)
            )
            
    except RequestException as e:
        raise _create_connection_error(CRIBL_CLOUD_AUTH_URL, e)
    
    return _extract_token(response.json(), logger)


def _authenticate_onprem(
    base_url: str,
    username: str,
    password: str,
    logger: logging.Logger,
    timeout: int,
    verify_ssl: bool
) -> str:
    """
    Authenticate with an on-premises Cribl instance.
    
    Args:
        base_url: Base API URL (e.g., "https://cribl.example.com/api/v1/m/")
        username: Cribl username
        password: Cribl password
        logger: Logger instance
        timeout: HTTP request timeout
        verify_ssl: Whether to verify SSL certificates
        
    Returns:
        Bearer token string
        
    Raises:
        AuthenticationError: If authentication fails
        ConnectionError: If unable to connect
    """
    auth_url = f"{base_url.rstrip('/')}/auth/login"
    logger.debug(f"Authenticating with on-premises Cribl (username: {mask_sensitive(username)})")
    
    headers = {"content-type": "application/json"}
    data = {
        "username": username,
        "password": password
    }
    
    try:
        response = requests.post(
            url=auth_url,
            headers=headers,
            json=data,
            timeout=timeout,
            verify=verify_ssl
        )
        response.raise_for_status()
        
    except HTTPError as e:
        status_code = e.response.status_code if e.response is not None else "unknown"
        if status_code == 401:
            raise AuthenticationError(
                "Invalid username or password",
                details=f"HTTP 401 from {auth_url}"
            )
        elif status_code == 403:
            raise AuthenticationError(
                "Access forbidden - check user permissions",
                details=f"HTTP 403 from {auth_url}"
            )
        else:
            raise AuthenticationError(
                f"Authentication request failed with HTTP {status_code}",
                details=str(e)
            )
            
    except RequestException as e:
        raise _create_connection_error(auth_url, e)
    
    return _extract_token(response.json(), logger)


def _extract_token(token_response: dict, logger: logging.Logger) -> str:
    """
    Extract the bearer token from the authentication response.
    
    Handles both response formats:
    - Cribl Cloud: {"access_token": "..."}
    - On-premises: {"token": "..."}
    
    Args:
        token_response: JSON response from auth endpoint
        logger: Logger instance
        
    Returns:
        Bearer token string (prefixed with "Bearer ")
        
    Raises:
        AuthenticationError: If token cannot be extracted
    """
    token = None
    
    if 'access_token' in token_response:
        token = token_response['access_token']
    elif 'token' in token_response:
        token = token_response['token']
    
    if not token:
        raise AuthenticationError(
            "Authentication response did not contain a token",
            details=f"Response keys: {list(token_response.keys())}"
        )
    
    logger.info("Authentication successful")
    return f"Bearer {token}"
