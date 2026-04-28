"""
Configuration constants and defaults for the Cribl Search API client.

These values can be overridden via the criblsearch.conf configuration file
or command-line parameters where applicable.
"""

# =============================================================================
# Batch and Timeout Settings
# =============================================================================

# Number of results to fetch per API call
# Larger values reduce API calls but increase memory usage per request
DEFAULT_BATCH_SIZE = 10000

# Maximum time (in seconds) to wait for a job to complete
# 600 seconds = 10 minutes
DEFAULT_STATUS_TIMEOUT = 600

# HTTP request timeout in seconds
DEFAULT_HTTP_TIMEOUT = 60

# Interval between job status checks in seconds
STATUS_CHECK_INTERVAL = 5

# Maximum results size in bytes (500MB)
# This prevents memory exhaustion on very large result sets
MAX_RESULTS_SIZE_MB = 500
MAX_RESULTS_SIZE_BYTES = MAX_RESULTS_SIZE_MB * 1000000

# =============================================================================
# Default Values
# =============================================================================

# Default sourcetype for returned events
DEFAULT_SOURCETYPE = "criblsearch:cmd:events"

# Default search group if not specified
DEFAULT_GROUP = "default"

# =============================================================================
# Cribl Cloud Authentication
# =============================================================================

# OAuth2 token endpoint for Cribl Cloud
CRIBL_CLOUD_AUTH_URL = "https://login.cribl.cloud/oauth/token"

# API audience for Cribl Cloud OAuth2
CRIBL_CLOUD_AUDIENCE = "https://api.cribl.cloud"

# Identifier for Cribl Cloud instances
CRIBL_CLOUD_INSTANCE = "cribl.cloud"

# =============================================================================
# API Endpoints (relative paths)
# =============================================================================

# Authentication endpoint for on-premises instances
ONPREM_AUTH_ENDPOINT = "/auth/login"

# Search jobs endpoint (format with group name)
SEARCH_JOBS_ENDPOINT = "/{group}/search/jobs"

# Job status endpoint (format with group and job_id)
JOB_STATUS_ENDPOINT = "/{group}/search/jobs/{job_id}/status"

# Job results endpoint (format with group and job_id)
JOB_RESULTS_ENDPOINT = "/{group}/search/jobs/{job_id}/results"

# =============================================================================
# Configuration File Settings
# =============================================================================

# Configuration file name (without .conf extension)
TOKEN_CONF = 'criblsearch'

# Configuration stanza name
TOKEN_STANZA = 'criblsearch_api'

# Secret storage realm and name
SECRET_REALM = 'criblsearch_realm'
SECRET_NAME = 'cribl_client_secret'

# =============================================================================
# Logging Settings
# =============================================================================

# Log file name (without .log extension)
LOG_NAME = "criblsearch"

# Maximum log file size in bytes (25MB)
LOG_MAX_BYTES = 25000000

# Number of backup log files to keep
LOG_BACKUP_COUNT = 5


def validate_batch_size(batch_size: int) -> int:
    """
    Validate and normalize batch size.
    
    Args:
        batch_size: Requested batch size
        
    Returns:
        Valid batch size (clamped to reasonable bounds)
    """
    min_batch = 100
    max_batch = 50000
    
    if batch_size < min_batch:
        return min_batch
    if batch_size > max_batch:
        return max_batch
    return batch_size


def validate_timeout(timeout: int) -> int:
    """
    Validate and normalize timeout value.
    
    Args:
        timeout: Requested timeout in seconds
        
    Returns:
        Valid timeout (clamped to reasonable bounds)
    """
    min_timeout = 30
    max_timeout = 3600  # 1 hour
    
    if timeout < min_timeout:
        return min_timeout
    if timeout > max_timeout:
        return max_timeout
    return timeout
