"""
Results retrieval and processing module for Cribl Search API.

Handles fetching search results in batches and processing them for output.
"""

import json
import logging
import sys
from typing import List, Dict, Any, Tuple, Optional, Union
from operator import itemgetter
from datetime import datetime

from cribl.client import CriblHTTPClient
from cribl.exceptions import ResultsRetrievalError
from cribl.config import DEFAULT_BATCH_SIZE, MAX_RESULTS_SIZE_BYTES, DEFAULT_SOURCETYPE
from cribl.logging_utils import ProgressLogger, format_bytes


def retrieve_results(
    client: CriblHTTPClient,
    group: str,
    job_id: str,
    logger: logging.Logger,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_size_bytes: int = MAX_RESULTS_SIZE_BYTES
) -> Tuple[List[Dict[str, Any]], int, bool]:
    """
    Retrieve all results from a completed search job.
    
    Fetches results in batches to handle large result sets efficiently.
    Stops if results exceed max_size_bytes to prevent memory exhaustion.
    
    Args:
        client: CriblHTTPClient instance
        group: Search group
        job_id: Job ID to retrieve results for
        logger: Logger instance
        batch_size: Number of results to fetch per API call
        max_size_bytes: Maximum total size of results in bytes
        
    Returns:
        Tuple of (results_list, total_count, is_complete)
        - results_list: List of result dictionaries
        - total_count: Total number of events (may be more than returned)
        - is_complete: True if all results were retrieved
        
    Raises:
        ResultsRetrievalError: If results retrieval fails
    """
    results: List[Dict[str, Any]] = []
    results_fetched = 0
    total_events_count = 0
    is_complete = True
    
    endpoint_base = f"/{group}/search/jobs/{job_id}/results"
    
    # Initialize progress logger (total will be set once we know it)
    progress = ProgressLogger(logger, "Results retrieval", total=0, log_interval_pct=20.0)
    
    logger.info(f"Starting results retrieval for job {job_id}")
    
    while True:
        # Build endpoint with pagination
        endpoint = f"{endpoint_base}?offset={results_fetched}&limit={batch_size}"
        
        try:
            response = client.get(endpoint)
        except Exception as e:
            logger.error(f"Error fetching results: {e}")
            logger.warning("Returning any results retrieved so far")
            is_complete = False
            break
        
        # Parse response - format is newline-delimited JSON
        # First line is metadata, subsequent lines are results
        result_lines = list(filter(None, response.text.split('\n')))
        
        if not result_lines:
            logger.warning("Empty response from results endpoint")
            break
        
        # Parse metadata (first line)
        try:
            metadata = json.loads(result_lines[0])
            total_events_count = metadata.get("totalEventCount", 0)
            
            # Update progress tracker with total
            if progress.total == 0 and total_events_count > 0:
                progress.set_total(total_events_count)
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse results metadata: {e}")
            total_events_count = 0
        
        # Remove metadata, leaving only result rows
        result_lines.pop(0)
        
        # Parse each result line
        batch_results = []
        for line in result_lines:
            try:
                batch_results.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.debug(f"Skipping unparseable result line: {e}")
                continue
        
        # Add to overall results
        results.extend(batch_results)
        batch_count = len(batch_results)
        results_fetched += batch_count
        
        # Update progress
        progress.update(batch_count)
        
        # Check if we've retrieved all results
        if results_fetched >= total_events_count:
            logger.info(f"Retrieved all {results_fetched:,} events")
            break
        
        # Check size limit
        current_size = sys.getsizeof(results)
        if current_size > max_size_bytes:
            logger.warning(
                f"Results size ({format_bytes(current_size)}) exceeded limit "
                f"({format_bytes(max_size_bytes)}). Returning partial results."
            )
            is_complete = False
            break
        
        # Safety check - if batch returned no results but we expect more, break
        if batch_count == 0:
            logger.warning("Empty batch received, stopping retrieval")
            break
    
    progress.complete(results_fetched)
    
    return results, total_events_count, is_complete


def parse_iso8601_to_epoch(timestamp_str: str) -> Optional[float]:
    """
    Convert ISO-8601 timestamp string to Unix epoch float.
    
    Handles various ISO-8601 formats with timezone info.
    Examples:
    - "2026-02-24T16:40:16.367Z" → 1771952416.367
    - "2026-02-24T16:40:16.367+00:00" → 1771952416.367
    - "2026-02-24T16:40:16Z" → 1771952416.0
    
    Args:
        timestamp_str: ISO-8601 formatted timestamp string
        
    Returns:
        Unix epoch timestamp as float, or None if parsing fails
    """
    if not timestamp_str or not isinstance(timestamp_str, str):
        return None
    
    try:
        # Replace Z suffix with +00:00 for consistent parsing
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        
        # Try parsing with timezone info first
        # Format: "2026-02-24T16:40:16.367+00:00"
        try:
            dt = datetime.fromisoformat(timestamp_str)
        except ValueError:
            # Try without microseconds if that fails
            # Format: "2026-02-24T16:40:16+00:00"
            dt = datetime.fromisoformat(timestamp_str.split('.')[0] + ('+00:00' if '+' not in timestamp_str else timestamp_str.split('+')[1]))
        
        # Convert to Unix epoch timestamp
        return dt.timestamp()
    except (ValueError, AttributeError, IndexError):
        return None


def convert_timestamp_field(event: Dict[str, Any], logger: Optional[logging.Logger] = None) -> None:
    """
    Convert _time field in an event to Unix epoch format if it's a string.
    
    Modifies the event in-place. Handles:
    - ISO-8601 strings (e.g., from Cribl Search API)
    - Numeric values (already in epoch format - no change)
    - Invalid/missing timestamps (logs warning, no change)
    
    Issue #24: Timeline visualization requires numeric _time (epoch timestamp),
    not ISO-8601 strings.
    
    Args:
        event: Dictionary containing event data with optional _time field
        logger: Optional logger for diagnostics
    """
    if '_time' not in event:
        return
    
    time_val = event['_time']
    
    # Already numeric - Splunk compatible, no conversion needed
    if isinstance(time_val, (int, float)):
        return
    
    # String - attempt conversion
    if isinstance(time_val, str):
        epoch_val = parse_iso8601_to_epoch(time_val)
        if epoch_val is not None:
            event['_time'] = epoch_val
            if logger:
                logger.debug(f"Converted ISO-8601 timestamp '{time_val}' to epoch {epoch_val}")
        else:
            # Conversion failed - log warning but don't fail
            if logger:
                logger.warning(f"Could not parse _time value as ISO-8601 or epoch: '{time_val}'")
    else:
        # Unknown type
        if logger:
            logger.warning(f"Unexpected _time type {type(time_val).__name__}: {time_val}")


def process_results(
    results: List[Dict[str, Any]],
    command_sourcetype: Optional[str] = None,
    default_sourcetype: str = DEFAULT_SOURCETYPE,
    sort_field: str = "_time",
    sort_reverse: bool = True,
    logger: Optional[logging.Logger] = None
) -> List[Dict[str, Any]]:
    """
    Process results for output to Splunk.
    
    Applies:
    - Sourcetype assignment (with priority: command > event > default)
    - Sorting by specified field
    
    Sourcetype Decision Tree (Issue #7):
    1. If command_sourcetype is provided, use it for ALL events
    2. Otherwise, for each event:
       - If event has 'sourcetype' field, use that
       - Otherwise, use default_sourcetype
    
    Args:
        results: List of result dictionaries
        command_sourcetype: Sourcetype specified in SPL command (overrides all)
        default_sourcetype: Default sourcetype when no other source available
        sort_field: Field to sort by
        sort_reverse: Whether to sort in descending order (newest first)
        logger: Optional logger instance
        
    Returns:
        Processed and sorted list of results
    """
    if not results:
        return []
    
    if logger:
        logger.debug(f"Processing {len(results):,} results (sort by {sort_field})")
    
    # Convert _time field from ISO-8601 strings to epoch timestamps (Issue #24)
    # This ensures Splunk timeline visualization works properly
    timestamps_converted = 0
    for event in results:
        if '_time' in event and isinstance(event['_time'], str):
            old_time = event['_time']
            convert_timestamp_field(event, logger)
            if isinstance(event.get('_time'), (int, float)):
                timestamps_converted += 1
    
    if timestamps_converted > 0 and logger:
        logger.info(f"Converted {timestamps_converted:,} ISO-8601 timestamps to epoch format")
    
    # Sort results
    try:
        sorted_results = sorted(results, key=itemgetter(sort_field), reverse=sort_reverse)
    except KeyError:
        # If sort field doesn't exist, return unsorted
        if logger:
            logger.warning(f"Sort field '{sort_field}' not found, returning unsorted")
        sorted_results = results
    
    # Assign sourcetype to each event based on decision tree
    if command_sourcetype:
        # Command-specified sourcetype overrides ALL events
        for event in sorted_results:
            event['sourcetype'] = command_sourcetype
        if logger:
            logger.info(f"Processed {len(sorted_results):,} events with command sourcetype '{command_sourcetype}'")
    else:
        # Use per-event sourcetype or default
        events_with_sourcetype = 0
        events_defaulted = 0
        for event in sorted_results:
            event_st = event.get('sourcetype')
            if event_st and str(event_st).strip():
                # Event has its own sourcetype - keep it
                events_with_sourcetype += 1
            else:
                # No sourcetype in event - use default
                event['sourcetype'] = default_sourcetype
                events_defaulted += 1
        if logger:
            logger.info(
                f"Processed {len(sorted_results):,} events: "
                f"{events_with_sourcetype} with event sourcetype, "
                f"{events_defaulted} defaulted to '{default_sourcetype}'"
            )
    
    return sorted_results


def determine_sourcetype(
    command_sourcetype: Optional[str],
    event_sourcetype: Optional[str] = None,
    default_sourcetype: str = DEFAULT_SOURCETYPE
) -> str:
    """
    Determine the sourcetype to use for events.
    
    Priority order:
    1. Command-specified sourcetype (--sourcetype parameter)
    2. Event's existing sourcetype (if present and valid)
    3. Default sourcetype
    
    Args:
        command_sourcetype: Sourcetype from command parameter
        event_sourcetype: Sourcetype from the event itself
        default_sourcetype: Default sourcetype to use as fallback
        
    Returns:
        Sourcetype string to use
    """
    if command_sourcetype:
        return command_sourcetype
    
    if event_sourcetype and event_sourcetype.strip():
        return event_sourcetype
    
    return default_sourcetype


def estimate_results_size(results: List[Dict[str, Any]]) -> int:
    """
    Estimate the memory size of results in bytes.
    
    Args:
        results: List of result dictionaries
        
    Returns:
        Estimated size in bytes
    """
    return sys.getsizeof(results)


def prepare_statistics_output(
    results: List[Dict[str, Any]],
    logger: Optional[logging.Logger] = None
) -> List[Dict[str, Any]]:
    """
    Prepare results for Statistics tab display (Issue #19).
    
    Removes the _raw field from results so Splunk displays them
    in the Statistics tab instead of the Events tab.
    All other fields are passed through as-is.
    
    Args:
        results: List of result dictionaries
        logger: Optional logger instance
        
    Returns:
        List of results with _raw field removed
    """
    if not results:
        return []
    
    stats_results = []
    raw_count = 0
    
    for event in results:
        # Create new dict without _raw
        if '_raw' in event:
            stat_event = {k: v for k, v in event.items() if k != '_raw'}
            raw_count += 1
        else:
            stat_event = event.copy()
        stats_results.append(stat_event)
    
    if logger:
        logger.debug(
            f"Statistics mode: processed {len(results):,} events, "
            f"removed _raw from {raw_count:,}"
        )
    
    return stats_results
