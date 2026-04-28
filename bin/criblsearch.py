#!/usr/bin/env python

###############################################################################
###############################################################################
##
##  Dispatches a search to remotely execute in Cribl and return results
##  containing the searched string for the given dataset
##
##  Discovered Intelligence - https://discoveredintelligence.ca
##
##  Copyright (C) 2023 - Discovered Intelligence
##  All Rights Reserved
##
##  For support contact:
##  support@discoveredintelligence.ca
##
###############################################################################
###############################################################################

import os
import sys
import logging
import logging.handlers
import time

# Add lib directory to path for splunklib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

# Add bin directory to path for cribl package
sys.path.insert(0, os.path.dirname(__file__))

from splunklib.searchcommands import dispatch, GeneratingCommand, Configuration, Option

# Import cribl package modules
from cribl import (
    CriblSearchError,
    AuthenticationError,
    ConnectionError as CriblConnectionError,
    JobCreationError,
    JobTimeoutError,
    ResultsRetrievalError,
    OrganizationNotFoundError,
    NoDefaultOrganizationError,
    DEFAULT_BATCH_SIZE,
    DEFAULT_SOURCETYPE,
    DEFAULT_STATUS_TIMEOUT,
)
from cribl.auth import get_auth_token
from cribl.client import CriblHTTPClient, build_base_url
from cribl.job import create_search_job, wait_for_job_completion, validate_query
from cribl.results import retrieve_results, process_results, prepare_statistics_output
from cribl.org import get_organization_or_default, get_organization_secret
from cribl.logging_utils import (
    TimingContext,
    CriblLogFilter,
    CriblLogFormatter,
    generate_invocation_id,
)
from cribl.config import (
    LOG_NAME,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
)

# Library-loading boilerplate
APP_NAME = 'criblsearch'
splunkhome = os.environ.get('SPLUNK_HOME', '/opt/splunk')
apphome = os.path.join(splunkhome, 'etc', 'apps', APP_NAME)

# Module-level log filter instance (so we can update job_id later)
_log_filter = None


def setup_logger(log_name: str, invocation_id: str) -> logging.Logger:
    """
    Setup the logger with file handler and custom formatting.
    
    Args:
        log_name: Name for the log file
        invocation_id: Unique ID for this invocation
        
    Returns:
        Configured logger instance
    """
    global _log_filter
    
    loginst = logging.getLogger(log_name)
    loginst.propagate = False
    
    _log_filter = CriblLogFilter(invocation_id)
    loginst.addFilter(_log_filter)
    loginst.setLevel(logging.INFO)

    log_path = os.path.join(
        os.environ.get('SPLUNK_HOME', '/opt/splunk'),
        'var', 'log', 'splunk', f'{log_name}.log'
    )
    
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT
        )
        CriblLogFormatter.converter = time.gmtime
        # Include job_id in log format for better correlation
        formatter = CriblLogFormatter(
            '%(asctime)s %(levelname)s invocation_id=%(invocation_id)s job_id=%(job_id)s %(message)s'
        )
        file_handler.setFormatter(formatter)
        loginst.addHandler(file_handler)
    except (PermissionError, OSError):
        # If we can't create the log file, use a NullHandler to avoid failures
        # This can happen during import when running outside Splunk context
        loginst.addHandler(logging.NullHandler())

    return loginst


# Create a unique identifier for this invocation
INVOCATION_ID = generate_invocation_id()

# Setup the logging for the command runs
logger = setup_logger(LOG_NAME, INVOCATION_ID)


@Configuration()
class CriblSearch(GeneratingCommand):
    """
    The criblsearch command executes a search remotely on a Cribl instance 
    for specific strings against specific dataset and fetches the result.
    
    Example:
    ```| criblsearch query="cribl dataset=example-cribl-edge-nodes '1.1.1.1'" sourcetype="example:logs" log_level="DEBUG"```
    
    Returns events matching the search string '1.1.1.1' from the Cribl dataset,
    assign sourcetype 'example:logs', and generate DEBUG logs.
    """
    
    # Generating command parameters
    query = Option(
        doc='''
        **Syntax:** **query=***<querystring>*
        **Description: Cribl-compatible query to run against Cribl** ''',
        require=True
    )
    sourcetype = Option(
        doc='''
        **Syntax:** **sourcetype=***<sourcetype-name>*
        **Description: Override sourcetype for ALL returned results.
        If specified, overrides any sourcetype in the events.
        If not specified, events keep their existing sourcetype field,
        or default to 'criblsearch:cmd:events' if no sourcetype present.** ''',
        require=False
    )
    log_level = Option(
        doc='''
        **Syntax:** **log_level=***<ERROR|WARN|INFO|DEBUG>*
        **Description: Logging level. Defaults to 'INFO'** ''',
        require=False
    )
    cribl_endpoint = Option(
        doc='''
        **Syntax:** **cribl_endpoint=***<endpoint-name>*
        **Description: Name of Cribl endpoint/connection to use for credentials. 
        If not specified, uses the default endpoint.** ''',
        require=False
    )
    statistics_mode = Option(
        doc='''
        **Syntax:** **statistics_mode=***<true|false>*
        **Description: When true, returns results in tabular format for the Statistics tab.
        Removes _raw field from results. Useful for aggregation queries like summarize/project.
        Defaults to false.** ''',
        require=False
    )

    def generate(self):
        """
        Main entry point - orchestrates the search workflow.
        
        Workflow:
        1. Configure logging level
        2. Get search parameters and configuration
        3. Authenticate with Cribl
        4. Create search job
        5. Wait for job completion
        6. Retrieve results
        7. Process and yield results
        """
        total_start_time = time.time()
        
        # Configure logging level
        self._configure_log_level()
        
        # Get search metadata
        sid = self._metadata.searchinfo.sid
        username = self._metadata.searchinfo.username
        args = self._metadata.searchinfo.args
        earliest = self._metadata.searchinfo.earliest_time
        latest = self._metadata.searchinfo.latest_time
        
        logger.info(
            f"Starting criblsearch: sid={sid}, user={username}, "
            f"query={self.query[:100]}..., earliest={earliest}, latest={latest}"
        )
        
        try:
            # Get endpoint configuration
            endpoint_config = get_organization_or_default(
                self.service.confs, 
                self.cribl_endpoint, 
                logger
            )
            
            # Use hardcoded Cribl Cloud default search group
            group = "default_search"
            
            # Build base URL - use HTTP for local endpoints, HTTPS for cloud
            # Local endpoints use "local" as the name and are typically self-hosted on localhost
            protocol = "http://" if endpoint_config.name.lower() == "local" else "https://"
            base_url = build_base_url(endpoint_config.cribl_url, protocol=protocol)
            logger.info(
                f"Configuration: endpoint={endpoint_config.name}, "
                f"instance={endpoint_config.cribl_instance}, group={group}, protocol={protocol}"
            )
            
            # Get credentials using session key
            cribl_secret = get_organization_secret(
                self.service.token, 
                endpoint_config.name
            )
            
            # Authenticate
            with TimingContext(logger, "Authentication") as auth_timer:
                token = get_auth_token(
                    cribl_instance=endpoint_config.cribl_instance,
                    base_url=base_url,
                    client_id=endpoint_config.cribl_client_id,
                    client_secret=cribl_secret,
                    logger=logger,
                    verify_ssl=True
                )
            
            # Create HTTP client
            client = CriblHTTPClient(
                base_url=base_url,
                token=token,
                logger=logger,
                verify_ssl=True
            )
            
            # Create search job
            with TimingContext(logger, "Job creation") as job_timer:
                job_id = create_search_job(
                    client=client,
                    group=group,
                    query=self.query,
                    earliest=earliest,
                    latest=latest,
                    logger=logger
                )
            
            # Set job_id in log filter for correlation in all subsequent logs
            if _log_filter:
                _log_filter.set_job_id(job_id)
            
            logger.info(f"Created job: {job_id}")
            
            # Wait for job completion
            with TimingContext(logger, "Job execution") as exec_timer:
                job_status, job_elapsed = wait_for_job_completion(
                    client=client,
                    group=group,
                    job_id=job_id,
                    logger=logger,
                    timeout_seconds=DEFAULT_STATUS_TIMEOUT
                )
            
            # Retrieve results
            with TimingContext(logger, "Results retrieval") as retrieval_timer:
                results, total_count, is_complete = retrieve_results(
                    client=client,
                    group=group,
                    job_id=job_id,
                    logger=logger,
                    batch_size=DEFAULT_BATCH_SIZE
                )
            
            if not is_complete:
                job_status = "partially_executed"
            
            logger.info(f"Job status: {job_status}")
            
            # Process results
            # Issue #7: Sourcetype decision tree
            # - If self.sourcetype is provided, use it for ALL events
            # - Otherwise, use event's sourcetype if present, else default
            with TimingContext(logger, "Results processing") as process_timer:
                processed_results = process_results(
                    results=results,
                    command_sourcetype=self.sourcetype,  # None if not specified
                    default_sourcetype=DEFAULT_SOURCETYPE,
                    sort_field="_time",
                    sort_reverse=True,
                    logger=logger
                )
            
            # Calculate results memory size
            import sys
            results_size = sys.getsizeof(processed_results)
            for event in processed_results:
                results_size += sys.getsizeof(event)
            
            # Log detailed summary with timing breakdown
            total_elapsed = time.time() - total_start_time
            logger.info(
                f"Search completed: {len(processed_results):,} events "
                f"in {total_elapsed:.2f}s total"
            )
            logger.info(
                f"Timing breakdown: auth={auth_timer.elapsed:.2f}s, "
                f"job_create={job_timer.elapsed:.2f}s, job_exec={exec_timer.elapsed:.2f}s, "
                f"retrieval={retrieval_timer.elapsed:.2f}s, process={process_timer.elapsed:.2f}s"
            )
            logger.debug(
                f"Results memory: ~{results_size / (1024*1024):.2f}MB for {len(processed_results):,} events"
            )
            
            # Apply statistics mode if requested (Issue #19)
            # Strip _raw field so results appear in Statistics tab instead of Events tab
            if self.statistics_mode and self.statistics_mode.lower() == 'true':
                processed_results = prepare_statistics_output(processed_results, logger)
                logger.info(f"Statistics mode enabled: stripped _raw from {len(processed_results):,} results")
            
            # Yield results
            logger.info(f"Dispatching {len(processed_results):,} events to Splunk")
            for event in processed_results:
                yield event
                
        except OrganizationNotFoundError as e:
            logger.error(f"Organization not found: {e}")
            yield self._error_event(f"Organization not found: {e.message}")
            
        except NoDefaultOrganizationError as e:
            logger.error(f"No default organization: {e}")
            yield self._error_event(f"No default organization configured: {e.message}")
            
        except AuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            yield self._error_event(f"Authentication failed: {e.message}")
            
        except CriblConnectionError as e:
            logger.error(f"Connection error: {e}")
            yield self._error_event(f"Connection error: {e.message}")
            
        except JobCreationError as e:
            logger.error(f"Job creation failed: {e}")
            yield self._error_event(f"Failed to create search job: {e.message}")
            
        except JobTimeoutError as e:
            logger.error(f"Job timeout: {e}")
            yield self._error_event(f"Search job timed out: {e.message}")
            
        except ResultsRetrievalError as e:
            logger.error(f"Results retrieval failed: {e}")
            yield self._error_event(f"Failed to retrieve results: {e.message}")
            
        except CriblSearchError as e:
            logger.error(f"Cribl search error: {e}")
            yield self._error_event(f"Search error: {e.message}")
            
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            yield self._error_event(f"Unexpected error: {str(e)}")
    
    def _configure_log_level(self):
        """Configure the logging level based on command parameter."""
        level_map = {
            'DEBUG': logging.DEBUG,
            'ERROR': logging.ERROR,
            'WARN': logging.WARN,
            'WARNING': logging.WARNING,
            'INFO': logging.INFO,
        }
        if self.log_level and self.log_level.upper() in level_map:
            logger.setLevel(level_map[self.log_level.upper()])
    
    def _error_event(self, message: str) -> dict:
        """Create an error event to return to Splunk."""
        return {
            '_raw': message,
            '_time': time.time(),
            'sourcetype': 'criblsearch:error',
            'error': True,
        }


dispatch(CriblSearch, sys.argv, sys.stdin, sys.stdout, __name__)

