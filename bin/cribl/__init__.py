"""
Cribl Search API Client Package

This package provides modular components for interacting with the Cribl Search API:
- auth: Authentication handling for Cribl Cloud and on-premises instances
- client: HTTP client with retry logic and error handling
- config: Configuration constants and defaults
- exceptions: Custom exception classes
- job: Search job creation and status polling
- org: Organization/multi-token management
- results: Results retrieval and processing
- logging_utils: Enhanced logging utilities with timing and progress tracking
"""

from cribl.exceptions import (
    CriblSearchError,
    AuthenticationError,
    ConnectionError,
    JobCreationError,
    JobTimeoutError,
    ResultsRetrievalError,
    QueryValidationError,
)
from cribl.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_STATUS_TIMEOUT,
    DEFAULT_HTTP_TIMEOUT,
    MAX_RESULTS_SIZE_MB,
    DEFAULT_SOURCETYPE,
    CRIBL_CLOUD_AUTH_URL,
    CRIBL_CLOUD_AUDIENCE,
)
from cribl.auth import get_auth_token
from cribl.client import CriblHTTPClient
from cribl.job import create_search_job, wait_for_job_completion
from cribl.results import retrieve_results, process_results
from cribl.org import (
    OrganizationConfig,
    OrganizationNotFoundError,
    NoDefaultOrganizationError,
    list_organizations,
    get_organization,
    get_default_organization,
    get_organization_or_default,
    get_organization_secret,
)

__all__ = [
    # Exceptions
    'CriblSearchError',
    'AuthenticationError',
    'ConnectionError',
    'JobCreationError',
    'JobTimeoutError',
    'ResultsRetrievalError',
    'QueryValidationError',
    'OrganizationNotFoundError',
    'NoDefaultOrganizationError',
    # Config
    'DEFAULT_BATCH_SIZE',
    'DEFAULT_STATUS_TIMEOUT',
    'DEFAULT_HTTP_TIMEOUT',
    'MAX_RESULTS_SIZE_MB',
    'DEFAULT_SOURCETYPE',
    'CRIBL_CLOUD_AUTH_URL',
    'CRIBL_CLOUD_AUDIENCE',
    # Auth
    'get_auth_token',
    # Client
    'CriblHTTPClient',
    # Job
    'create_search_job',
    'wait_for_job_completion',
    # Results
    'retrieve_results',
    'process_results',
    # Organization
    'OrganizationConfig',
    'list_organizations',
    'get_organization',
    'get_default_organization',
    'get_organization_or_default',
    'get_organization_secret',
]

__version__ = '1.2.0'
