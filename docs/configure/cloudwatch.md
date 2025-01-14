Using Cloudwatch repository requires you to configure the following required options in the CKAN configuration file:

```ini
ckanext.event_audit.cloudwatch.access_key = YOUR_ACCESS_KEY
ckanext.event_audit.cloudwatch.secret_key = YOUR_SECRET_KEY
ckanext.event_audit.cloudwatch.region = YOUR_REGION
```

See the [AWS documentation](https://docs.aws.amazon.com/cloudwatch/) for more information on how to obtain these values and configure the AWS Cloudwatch service.


You can also specify the __log group__ and __log stream__ to use for the Cloudwatch repository. See the configuration options below, with the
default values:

```ini
ckanext.event_audit.cloudwatch.log_group = /ckan/event-audit
ckanext.event_audit.cloudwatch.log_stream = event-audit-stream
```
