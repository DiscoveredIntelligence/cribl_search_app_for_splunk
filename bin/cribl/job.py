"""
Job management module for Cribl Search API.

Handles search job creation, status polling, and completion waiting.
"""

import logging
import time
from typing import Tuple, Optional

from cribl.client import CriblHTTPClient
from cribl.exceptions import JobCreationError, JobTimeoutError, QueryValidationError
from cribl.config import DEFAULT_STATUS_TIMEOUT, STATUS_CHECK_INTERVAL

# Retry configuration for job creation
JOB_CREATION_MAX_RETRIES = 3
JOB_CREATION_RETRY_DELAY = 2.0  # seconds, doubles each retry


def validate_query(query: str) -> str:
    """
    Validate and normalize a Cribl search query.
    
    Ensures the query:
    - Starts with "cribl "
    - Contains a dataset specification
    
    Args:
        query: The search query to validate
        
    Returns:
        Normalized query string
        
    Raises:
        QueryValidationError: If query is invalid
    """
    if not query or not query.strip():
        raise QueryValidationError("Query cannot be empty")
    
    query = query.strip()
    
    # Ensure query starts with "cribl "
    if not query.startswith("cribl "):
        query = "cribl " + query
    
    # Ensure query has a dataset specification
    if "dataset=" not in query:
        raise QueryValidationError(
            "No dataset specified in query",
            details="Query must include 'dataset=<dataset_name>'"
        )
    
    return query


def create_search_job(
    client: CriblHTTPClient,
    group: str,
    query: str,
    earliest: float,
    latest: float,
    logger: logging.Logger
) -> str:
    """
    Create a new search job on Cribl.
    
    Args:
        client: CriblHTTPClient instance
        group: Search group (e.g., "default_search")
        query: Cribl search query
        earliest: Start time as Unix timestamp
        latest: End time as Unix timestamp
        logger: Logger instance
        
    Returns:
        Job ID string
        
    Raises:
        JobCreationError: If job creation fails
        QueryValidationError: If query is invalid
    """
    # Validate and normalize query
    query = validate_query(query)
    
    # Build endpoint URL
    endpoint = f"/{group}/search/jobs"
    
    # Construct POST data
    data = {
        "earliest": earliest,
        "latest": latest,
        "group": group,
        "query": query
    }
    
    logger.debug(f"Creating search job: group={group}, query={query[:100]}...")
    
    last_error = None
    for attempt in range(JOB_CREATION_MAX_RETRIES):
        try:
            response = client.post(endpoint, data=data)
            response_data = response.json()
            
            # Extract job details from response
            items = response_data.get('items', [])
            if not items:
                raise JobCreationError(
                    "No job returned in response",
                    details=f"Response: {response_data}"
                )
            
            job_id = items[0].get('id')
            if not job_id:
                raise JobCreationError(
                    "Job response missing ID",
                    details=f"Response: {response_data}"
                )
            
            logger.info(f"Created search job: {job_id}")
            return job_id
            
        except JobCreationError:
            raise
        except Exception as e:
            last_error = e
            if attempt < JOB_CREATION_MAX_RETRIES - 1:
                delay = JOB_CREATION_RETRY_DELAY * (2 ** attempt)
                logger.warning(f"Job creation attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"Job creation failed after {JOB_CREATION_MAX_RETRIES} attempts")
    
    raise JobCreationError(
        "Failed to create search job",
        details=str(last_error) if last_error else "Unknown error"
    )


def get_job_status(
    client: CriblHTTPClient,
    group: str,
    job_id: str,
    logger: logging.Logger
) -> str:
    """
    Get the current status of a search job.
    
    Args:
        client: CriblHTTPClient instance
        group: Search group
        job_id: Job ID to check
        logger: Logger instance
        
    Returns:
        Job status string (e.g., "running", "completed", "failed")
        
    Raises:
        CriblSearchError: If status check fails
    """
    endpoint = f"/{group}/search/jobs/{job_id}/status"
    
    response = client.get(endpoint)
    response_data = response.json()
    
    items = response_data.get('items', [])
    if not items:
        logger.warning(f"No status returned for job {job_id}")
        return "unknown"
    
    status = items[0].get('status', 'unknown')
    return status


def wait_for_job_completion(
    client: CriblHTTPClient,
    group: str,
    job_id: str,
    logger: logging.Logger,
    timeout_seconds: int = DEFAULT_STATUS_TIMEOUT,
    check_interval: int = STATUS_CHECK_INTERVAL
) -> Tuple[str, float]:
    """
    Wait for a search job to complete, polling status periodically.
    
    Args:
        client: CriblHTTPClient instance
        group: Search group
        job_id: Job ID to wait for
        logger: Logger instance
        timeout_seconds: Maximum time to wait in seconds
        check_interval: Time between status checks in seconds
        
    Returns:
        Tuple of (final_status, elapsed_seconds)
        
    Raises:
        JobTimeoutError: If job does not complete within timeout
    """
    start_time = time.time()
    check_count = 0
    max_checks = timeout_seconds // check_interval
    
    logger.info(f"Waiting for job {job_id} to complete (timeout: {timeout_seconds}s)")
    
    while True:
        status = get_job_status(client, group, job_id, logger)
        elapsed = time.time() - start_time
        
        logger.debug(f"Job {job_id} status: {status} ({elapsed:.1f}s elapsed)")
        
        if status == "completed":
            logger.info(f"Job {job_id} completed in {elapsed:.1f}s")
            return status, elapsed
        
        if status in ("failed", "cancelled", "error"):
            logger.warning(f"Job {job_id} ended with status: {status}")
            return status, elapsed
        
        check_count += 1
        if check_count >= max_checks:
            raise JobTimeoutError(
                job_id=job_id,
                elapsed_seconds=elapsed,
                details=f"Job still in '{status}' state after {elapsed:.1f}s"
            )
        
        time.sleep(check_interval)


def build_job_urls(base_url: str, group: str, job_id: str) -> Tuple[str, str, str]:
    """
    Build the URLs for job operations.
    
    Args:
        base_url: Base API URL
        group: Search group
        job_id: Job ID
        
    Returns:
        Tuple of (job_url, status_url, results_url)
    """
    job_url = f"{base_url.rstrip('/')}/{group}/search/jobs/{job_id}"
    status_url = f"{job_url}/status"
    results_url = f"{job_url}/results"
    
    return job_url, status_url, results_url
