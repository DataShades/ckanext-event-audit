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
configuration file, and the admin panel stores them in the database in clear text.

The credentials need permission to create the log group and the log stream and to write, read and
delete log events (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`,
`logs:FilterLogEvents`, `logs:DeleteLogGroup`, `logs:DescribeLogGroups`).

You can also specify the __log group__ and __log stream__ to use for the Cloudwatch repository. See the configuration options below, with the
default values:

```ini
ckanext.event_audit.cloudwatch.log_group = /ckan/event-audit
ckanext.event_audit.cloudwatch.log_stream = event-audit-stream
```

## Limitations

* The events can't be removed one by one or by a time range. The only way to remove events is to
  remove **all** of them, and that deletes the log group and creates it again empty. Use the
  retention setting of the log group in AWS to expire old events, the extension's own
  [retention command](retention.md) doesn't support this repository.
* An event with a `payload` and a `result` bigger than 256 KB in total is written without them,
  and an error is logged.
* Reading events runs a `FilterLogEvents` query over the log group. It gets slower as the log
  grows and is subject to the AWS API rate limits, so it is meant for occasional lookups rather
  than for browsing the dashboard all day.
