"""
Endpoint management module for multi-token support.

Handles multiple Cribl endpoints/connections with:
- UCC Framework account storage (criblsearch_account.conf)
- UCC-managed encrypted secret storage
- Default endpoint handling
- Backward compatibility with legacy criblsearch.conf format
"""

import logging
from typing import Optional, List, Dict, Any, Tuple, NamedTuple

from cribl.exceptions import CriblSearchError


class OrganizationConfig(NamedTuple):
    """Configuration for a single Cribl endpoint."""
    name: str
    label: str
    cribl_url: str
    cribl_instance: str
    cribl_client_id: str
    group: str
    is_default: bool


class OrganizationNotFoundError(CriblSearchError):
    """Raised when a specified endpoint is not found."""
    def __init__(self, org_name: str, available_orgs: Optional[List[str]] = None):
        self.org_name = org_name
        self.available_orgs = available_orgs or []
        message = f"Endpoint '{org_name}' not found"
        if self.available_orgs:
            message += f". Available: {', '.join(self.available_orgs)}"
        super().__init__(message)


class NoDefaultOrganizationError(CriblSearchError):
    """Raised when no default endpoint is configured."""
    def __init__(self):
        super().__init__(
            "No default endpoint configured",
            details="Set is_default=true on one endpoint or specify cribl_endpoint= in the command"
        )


# UCC account configuration file
UCC_ACCOUNT_CONF = "criblsearch_account"

# Legacy config stanza prefixes (for backward compatibility)
LEGACY_ORG_STANZA_PREFIX = "endpoint:"
LEGACY_STANZA = "criblsearch_api"

# Secret storage formats
SECRET_REALM_BASE = "criblsearch_realm"
UCC_CREDENTIAL_REALM = "__REST_CREDENTIAL__#criblsearch#configs/conf-criblsearch_account"


def get_secret_realm(org_name: Optional[str] = None) -> str:
    """
    Get the legacy secret realm for an endpoint.
    
    Args:
        org_name: Endpoint name, or None for legacy single-endpoint
        
    Returns:
        Secret realm string
    """
    if org_name:
        return f"{SECRET_REALM_BASE}:{org_name}"
    return SECRET_REALM_BASE


def get_secret_username(org_name: Optional[str] = None) -> str:
    """
    Get the legacy secret username for an endpoint.
    
    For new multi-endpoint setup, the username is the endpoint name.
    For legacy single-endpoint, it's 'cribl_client_secret'.
    
    Args:
        org_name: Endpoint name, or None for legacy
        
    Returns:
        Secret username string
    """
    if org_name:
        return org_name
    return "cribl_client_secret"


def list_organizations(confs) -> List[OrganizationConfig]:
    """
    List all configured endpoints.
    
    Checks for UCC account format first (criblsearch_account.conf),
    then falls back to legacy formats for backward compatibility.
    
    Args:
        confs: Splunk configuration service (search_command.service.confs)
        
    Returns:
        List of OrganizationConfig objects
    """
    organizations = []
    found_ucc = False
    
    # Try UCC account format first
    try:
        account_conf = confs[UCC_ACCOUNT_CONF]
        for stanza in account_conf:
            org = _parse_ucc_account_stanza(stanza)
            if org:
                organizations.append(org)
                found_ucc = True
    except KeyError:
        # UCC account conf doesn't exist yet
        pass
    
    # If we found UCC accounts, return them
    if found_ucc:
        return organizations
    
    # Fall back to legacy criblsearch.conf format
    try:
        conf = confs['criblsearch']
    except KeyError:
        return organizations
    
    for stanza in conf:
        stanza_name = stanza.name
        
        if stanza_name.startswith(LEGACY_ORG_STANZA_PREFIX):
            # Legacy endpoint stanza
            org_name = stanza_name[len(LEGACY_ORG_STANZA_PREFIX):]
            org = _parse_legacy_org_stanza(stanza, org_name, is_legacy=False)
            if org:
                organizations.append(org)
                
        elif stanza_name == LEGACY_STANZA:
            # Legacy single-endpoint stanza - treat as endpoint named "default"
            org = _parse_legacy_org_stanza(stanza, "default", is_legacy=True)
            if org:
                organizations.append(org)
    
    return organizations


def _parse_ucc_account_stanza(stanza) -> Optional[OrganizationConfig]:
    """
    Parse a UCC account stanza into an OrganizationConfig.
    
    UCC account stanzas have the account name as the stanza name,
    with fields matching globalConfig.json entity definitions.
    
    Args:
        stanza: Splunk configuration stanza from criblsearch_account.conf
        
    Returns:
        OrganizationConfig or None if invalid
    """
    org_name = stanza.name
    
    # Skip disabled accounts
    disabled = getattr(stanza, 'disabled', '0') or '0'
    if disabled.lower() in ('true', '1', 'yes'):
        return None
    
    cribl_url = getattr(stanza, 'cribl_url', None) or ''
    cribl_instance = getattr(stanza, 'cribl_instance', None) or 'cribl.cloud'
    client_id = getattr(stanza, 'cribl_client_id', None) or ''
    group = getattr(stanza, 'group', None) or 'default'
    
    # Skip if no URL configured (incomplete setup)
    if not cribl_url:
        return None
    
    is_default_str = getattr(stanza, 'is_default', '0') or '0'
    is_default = is_default_str.lower() in ('true', '1', 'yes')
    
    return OrganizationConfig(
        name=org_name,
        label=org_name,  # UCC uses the account name as the label
        cribl_url=cribl_url,
        cribl_instance=cribl_instance,
        cribl_client_id=client_id,
        group=group,
        is_default=is_default
    )


def _parse_legacy_org_stanza(stanza, org_name: str, is_legacy: bool) -> Optional[OrganizationConfig]:
    """
    Parse a configuration stanza into an OrganizationConfig.
    
    Args:
        stanza: Splunk configuration stanza
        org_name: Name for this endpoint
        is_legacy: Whether this is a legacy single-endpoint stanza
        
    Returns:
        OrganizationConfig or None if invalid
    """
    cribl_url = getattr(stanza, 'cribl_url', None) or ''
    cribl_instance = getattr(stanza, 'cribl_instance', None) or ''
    client_id = getattr(stanza, 'cribl_client_id', None) or ''
    group = getattr(stanza, 'group', None) or 'default'
    
    # Skip if no URL configured (incomplete setup)
    if not cribl_url:
        return None
    
    # For new-style, read is_default; for legacy, it's always default if it's the only one
    if is_legacy:
        is_default = True
        label = "Default (Legacy)"
    else:
        is_default_str = getattr(stanza, 'is_default', 'false') or 'false'
        is_default = is_default_str.lower() in ('true', '1', 'yes')
        label = getattr(stanza, 'label', None) or org_name
    
    return OrganizationConfig(
        name=org_name,
        label=label,
        cribl_url=cribl_url,
        cribl_instance=cribl_instance,
        cribl_client_id=client_id,
        group=group,
        is_default=is_default
    )


def get_organization(confs, org_name: str) -> OrganizationConfig:
    """
    Get a specific endpoint by name.
    
    Args:
        confs: Splunk configuration service
        org_name: Endpoint name to retrieve
        
    Returns:
        OrganizationConfig for the specified endpoint
        
    Raises:
        OrganizationNotFoundError: If endpoint not found
    """
    organizations = list_organizations(confs)
    org_names = [o.name for o in organizations]
    
    for org in organizations:
        if org.name == org_name:
            return org
    
    raise OrganizationNotFoundError(org_name, org_names)


def get_default_organization(confs) -> OrganizationConfig:
    """
    Get the default endpoint.
    
    Returns the endpoint with is_default=true, or if only one
    endpoint is configured, returns that one.
    
    Args:
        confs: Splunk configuration service
        
    Returns:
        OrganizationConfig for the default endpoint
        
    Raises:
        NoDefaultOrganizationError: If no default endpoint
    """
    organizations = list_organizations(confs)
    
    if not organizations:
        raise NoDefaultOrganizationError()
    
    # If only one endpoint, it's the default
    if len(organizations) == 1:
        return organizations[0]
    
    # Find explicit default
    for org in organizations:
        if org.is_default:
            return org
    
    raise NoDefaultOrganizationError()


def get_organization_or_default(
    confs,
    org_name: Optional[str] = None,
    logger: Optional[logging.Logger] = None
) -> OrganizationConfig:
    """
    Get an endpoint by name, or the default if not specified.
    
    Args:
        confs: Splunk configuration service
        org_name: Optional endpoint name
        logger: Optional logger for debug output
        
    Returns:
        OrganizationConfig
        
    Raises:
        OrganizationNotFoundError: If specified endpoint not found
        NoDefaultOrganizationError: If no default when endpoint not specified
    """
    if org_name:
        org = get_organization(confs, org_name)
        if logger:
            logger.debug(f"Using specified endpoint: {org_name}")
        return org
    else:
        org = get_default_organization(confs)
        if logger:
            logger.debug(f"Using default endpoint: {org.name}")
        return org


def get_organization_secret(session_key: str, org_name: str) -> str:
    """
    Get the client secret for an endpoint using UCC credential storage.
    
    Uses solnlib.conf_manager.ConfManager to access encrypted credentials
    stored by the UCC framework.
    
    Args:
        session_key: Splunk session key for API access
        org_name: Endpoint/account name
        
    Returns:
        Decrypted client secret
        
    Raises:
        CriblSearchError: If secret not found
    """
    try:
        from solnlib.conf_manager import ConfManager
        
        # Use ConfManager to access encrypted credentials
        # UCC stores credentials with realm pattern:
        # __REST_CREDENTIAL__#criblsearch#configs/conf-criblsearch_account
        cfm = ConfManager(
            session_key,
            'criblsearch',
            realm=UCC_CREDENTIAL_REALM
        )
        conf = cfm.get_conf(UCC_ACCOUNT_CONF)
        account_details = conf.get(org_name)
        
        if not account_details:
            raise CriblSearchError(
                f"Account '{org_name}' not found in encrypted storage",
                details="Configure credentials in the app setup page"
            )
        
        client_secret = account_details.get('cribl_client_secret')
        if not client_secret:
            raise CriblSearchError(
                f"Client secret not found for account '{org_name}'",
                details="Ensure cribl_client_secret is configured for this account"
            )
        
        return client_secret
        
    except ImportError:
        raise CriblSearchError(
            "solnlib module not available",
            details="The UCC framework libraries are required for credential access"
        )
    except Exception as e:
        if isinstance(e, CriblSearchError):
            raise
        raise CriblSearchError(
            f"Failed to get credential for account '{org_name}'",
            details=str(e)
        )


def format_org_list(organizations: List[OrganizationConfig]) -> str:
    """
    Format endpoint list for display.
    
    Args:
        organizations: List of OrganizationConfig
        
    Returns:
        Formatted string listing endpoints
    """
    if not organizations:
        return "No endpoints configured"
    
    lines = ["Configured endpoints:"]
    for org in organizations:
        default_marker = " (default)" if org.is_default else ""
        lines.append(f"  - {org.name}: {org.label}{default_marker}")
    
    return "\n".join(lines)
