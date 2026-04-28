# CriblSearch App for Splunk by Discovered Intelligence

## Overview

The CriblSearch App for Splunk provides a custom generating search command `criblsearch` that dispatches a Cribl-compatible search query to remotely execute in Cribl Search and return the results against the dataset(s) specified in the query.

Once results are fetched using this command, you can use any streaming or transforming commands for further processing followed by writing results to an index or lookup file using `collect` or `outputlookup` commands.

---

## Key Features

- **Multi-Endpoint Support**: Configure and manage multiple Cribl Cloud endpoints with a single app installation
- **OAuth Authentication**: Client ID/Secret authentication for Cribl Cloud deployments
- **Default Endpoint**: Set a default endpoint or specify which endpoint to query at search time
- **Custom Sourcetype**: Assign custom sourcetypes to returned results
- **Debug Logging**: Override log levels at runtime for troubleshooting
- **Execution Dashboard**: Built-in dashboard for monitoring job executions, status, and logs
- **SSL Verification**: Enabled by default for secure connections
- **Splunk Cloud Compatible**: Passes Splunk AppInspect validation

---

## Installation

1. Download the app from Github releases page
2. Install the app on a Search Head
3. Navigate to the app's Setup page (Manage Apps → criblsearch → Set up)
4. Configure your Cribl Cloud endpoint:
   - **Endpoint Name**: A unique identifier for this connection
   - **Cribl URL**: Hostname only (e.g., `main-yourorg.cribl.cloud`)
   - **Client ID**: Your Cribl Cloud Client ID
   - **Client Secret**: Your Cribl Cloud Client Secret
   - **Set as Default**: Check to make this the default endpoint
5. Click Save

**Note**: Client ID and Client Secret can be created or retrieved from the Cribl Cloud console: Account → Organization → API Management Tab

---

## Usage

### Basic Syntax

```
| criblsearch query="<cribl-search-query>" [cribl_endpoint=<name>] [sourcetype=<type>] [log_level=<level>]
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | Yes | Cribl-compatible search query with dataset specified |
| `cribl_endpoint` | No | Name of configured endpoint (uses default if not specified) |
| `sourcetype` | No | Custom sourcetype for results (default: `criblsearch:cmd:events`) |
| `log_level` | No | Override logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Examples

**Basic search:**
```
| criblsearch query="dataset=example-cribl-edge-nodes '1.1.1.1'"
```

**Search with specific endpoint and custom sourcetype:**
```
| criblsearch query="dataset=web-logs status>=400" cribl_endpoint="prod_cribl" sourcetype="web:errors"
```

**Debug a query:**
```
| criblsearch query="dataset=firewall-logs src_ip=192.0.2.1" log_level="DEBUG"
```

**Aggregation query with Statistics tab output:**
```
| criblsearch query="dataset=web-logs | summarize count() as count by status | project status, count" statistics_mode=true
```

For Cribl search syntax, see: https://docs.cribl.io/search/build-a-search

---

## Logging

The command generates execution logs to `SPLUNK_HOME/var/log/splunk/criblsearch.log`.

Query logs with:
```
index=_internal sourcetype=criblsearch:cmd:log
```

---

## Troubleshooting

1. **Use the Dashboard**: Navigate to the `Criblsearch Executions` dashboard for job status, parameters, and error details
2. **Enable Debug Logging**: Add `log_level="DEBUG"` to your search for detailed execution logs
3. **Verify Endpoint URL**: Ensure you're using the Leader URL, not the Cribl Cloud home page URL
4. **Check Credentials**: Verify Client ID/Secret or Username/Password are correct in Setup

---

## Known Limitations

- Timeline bar doesn't display in Search page despite chronological event ordering
- Search time configurations (field extractions, calculated fields) defined for the assigned sourcetype won't apply to retrieved events
- If Cribl search takes more than 10 minutes, the command retrieves available (possibly partial) results
- Total results are capped at 500 MB to prevent memory issues

---

## Support

For support, bug reports, or feature requests:

**Email**: support@discoveredintelligence.ca

---

## License

Copyright © Discovered Intelligence Inc. All rights reserved.
