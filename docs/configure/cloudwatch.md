Using Cloudwatch repository requires you to configure the following required options in the CKAN configuration file:

```ini
ckanext.event_audit.cloudwatch.access_key = YOUR_ACCESS_KEY
ckanext.event_audit.cloudwatch.secret_key = YOUR_SECRET_KEY
ckanext.event_audit.cloudwatch.region = YOUR_REGION
```

See the [AWS documentation](https://docs.aws.amazon.com/cloudwatch/) for more information on how to obtain these values and configure the AWS Cloudwatch service.

The region is required. The access key and the secret key can be left empty: the standard AWS
credential chain is used then (the `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` environment
variables, a shared credentials file, or the IAM role of the instance/container). This is the
recommended setup, because credentials given through the CKAN configuration end up in the
configuration file. The admin panel doesn't offer them, so they are never stored in the database.

The credentials need permission to create the log group and the log stream, to write, read and
delete log events, and to run a Logs Insights query (`logs:CreateLogGroup`,
`logs:CreateLogStream`, `logs:PutLogEvents`, `logs:FilterLogEvents`, `logs:DeleteLogGroup`,
`logs:DescribeLogGroups`, `logs:StartQuery`, `logs:GetQueryResults`, `logs:StopQuery`).

You can also specify the __log group__ and __log stream__ to use for the Cloudwatch repository. See the configuration options below, with the
default values:

```ini
ckanext.event_audit.cloudwatch.log_group = /ckan/event-audit
ckanext.event_audit.cloudwatch.log_stream = event-audit-stream
```

## How events are read

Two different AWS APIs are used, depending on the caller:

* **`filter_events()`** - used by `get_event()`, the CLI export, and [retention](retention.md) -
  runs a `FilterLogEvents` query: it walks the log group chronologically and can only match by
  equality. It gets slower as the log group grows, so it's meant for a single lookup or a one-off
  export, not for repeated calls over a large log group.
* **The dashboard table** always queries [CloudWatch Logs
  Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html)
  instead, via `query_page()`. Unlike `FilterLogEvents`, Logs Insights can filter by more than
  equality, sort by any column and paginate server-side in a single query, so a dashboard page
  load only pays for the page it actually shows - not for draining the whole log group, however
  large it's grown.

```ini
ckanext.event_audit.cloudwatch.insights_poll_timeout = 30
```

A Logs Insights query is asynchronous: the extension starts it and polls for the result, so a
dashboard page load costs a little real latency (query scheduling overhead, on top of the time
the query itself takes to scan the log group) and is billed by AWS for the data it scans.
`insights_poll_timeout` is how long, in seconds, to poll before giving up - the query is stopped
(`StopQuery`) and the request fails with a `TimeoutError` if it isn't done by then.

The dashboard's filter UI offers `=`, `!=`, `>`, `>=`, `<`, `<=` and `like` on every filterable
column, and every one of them is pushed down to the Logs Insights query - `like` becomes a
case-insensitive regex match. `timestamp` comparisons become the query's time range instead of a
filter condition. There's no combination the dashboard's own UI can produce that isn't pushed
down this way; if a filter ever *can't* be expressed (only reachable by calling the table's data
source directly, not through the UI), it's dropped and logged with a warning rather than silently
fetching everything or returning a partial page.

## Limitations

* The events can't be removed one by one or by a time range. The only way to remove events is to
  remove **all** of them, and that deletes the log group and creates it again empty. Use the
  retention setting of the log group in AWS to expire old events, the extension's own
  [retention command](retention.md) doesn't support this repository.
* An event with a `payload` and a `result` bigger than 256 KB in total is written without them,
  and an error is logged.
* Outside the dashboard (CLI export, `get_event`, retention), reading events still runs a
  `FilterLogEvents` query over the log group, which gets slower as the log grows - see "How
  events are read" above.
