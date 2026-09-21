# Security

The audit log is only as trustworthy and as safe as what you put in it. This page lists what the
extension stores, who can see it, and what you should do about it.

## What is stored

By default, an event contains only *metadata*: the category, the action, the ID of the user, the
type and the ID of the object, and the time. `payload` and `result` are empty.

If you enable [`store_payload_and_result`](configure/tracking.md#storing-payload-and-result-data),
the input and the output of every API action, and the state of every changed database row, are
stored **verbatim**. That includes:

* the `password`, `password1` and `password2` fields in the payload of `user_create`,
  `user_update` and `user_password_reset`;
* the API token in the result of `api_token_create`;
* for the `User` model, the password hash, `reset_key`, `apikey`, `email` and `plugin_extras`;
* anything else a user submits: personal data in datasets, private dataset contents, and the
  results of `package_show`-like actions, which can be large.

There is **no built-in redaction**. Only the keys starting with an underscore are dropped. Until
that changes, either keep the option disabled, or remove what you don't want to keep in a
`modify_event` hook, as shown below.

With the [CloudWatch repository](repositories/cloudwatch.md) the events leave your server, and
your AWS permissions and retention rules decide who reads them and for how long.

### Redacting keys

The [`modify_event`](interfaces.md) hook runs for every event produced by the built-in trackers,
before it is queued or written, so it is the place to remove sensitive values:

```python
from __future__ import annotations

from typing import Any

import ckan.plugins as p

from ckanext.event_audit import types
from ckanext.event_audit.interfaces import IEventAudit

REDACTED = "***"
SENSITIVE_KEYS = {"apikey", "reset_key", "token", "authorization", "secret_key"}


def _is_sensitive(key: Any) -> bool:
    key = str(key).lower()

    return key.startswith("password") or key in SENSITIVE_KEYS


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive(key) else redact(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [redact(item) for item in value]

    return value


class RedactionPlugin(p.SingletonPlugin):
    p.implements(IEventAudit, inherit=True)

    def modify_event(self, event: types.Event) -> types.Event:
        event.payload = redact(event.payload)
        event.result = redact(event.result)

        return event
```

Extend `SENSITIVE_KEYS` to fit your data, and remember that values like the email address are
personal data too. Check the result: have a look at what the dashboard shows after creating a user
and a token in a test environment.

## Who has access

* The dashboard and the configuration page are available to `sysadmin` users only.
* Sysadmins can delete events: individually and in bulk from the dashboard, all at once with the
  "Clear repo" button, and with `ckan event-audit remove-events` on the command line, which
  deletes **everything** if you give it no time range. The log isn't tamper-proof against a
  sysadmin. If you need that, use a store that CKAN's own credentials can't delete from, for
  example a CloudWatch log group with IAM permissions that leave out `logs:DeleteLogGroup`, and
  restrict the available repositories to it.
* [`restrict_available_repos`](configure/repository.md#list-of-available-repositories) limits
  which repositories can be selected, and is not changeable from the admin panel.

## Credentials

The CloudWatch access key and secret key are not available in the admin panel, so they are never stored in the database. They can only be set in the CKAN configuration file, where they are in clear text. Leave them empty and give the CKAN process an IAM role or environment credentials instead, see [CloudWatch](configure/cloudwatch.md). Grant only the permissions the repository needs.

## Log volume

Every recorded event is a write. With `track_api` enabled, any request that calls an action
records an event, and anonymous visitors and crawlers can trigger read actions like
`package_show` and `package_search`. The default [ignore list](configure/ignore.md) leaves those
out, but **setting `ignore.actions` replaces the list**, so keep the defaults you still want.

In [threaded mode](configure/async.md) the write queue is bounded, so a flood can't exhaust memory:
the surplus events are dropped and an error is logged. Set a [retention](configure/retention.md)
period so that the log doesn't grow forever.
