# In-built tracking

There are two built-in trackers in the extension that are enabled by default and work out of the box - API and Database trackers.

## API tracker

Captures all events that are triggered by the CKAN API. Everything that is called via `tk.get_action` will be tracked by this tracker, unless it's explicitly ignored by the configuration. See the [ignore](ignore.md) section for more details.

To disable the API tracker, specify this in the configuration file:

```ini
ckanext.event_audit.track_api = false
```

We can ignore specific actions from being tracked by setting the `ckanext.event_audit.ignore.actions` configuration option. See the [ignore](ignore.md) section for more details.

## Database tracker

We're utilising the SQLAlchemy’s event system for tracking database interactions. The audit event creation will be triggered when the model is created, updated, or deleted.

Changes are tracked in the sessions CKAN hands out: the regular `model.Session` and the ones from `ckan.model.meta.create_local_session`, which is what code running outside of a request, including other extensions, usually writes with. A session you build yourself, e.g. with `sqlalchemy.orm.Session(bind=engine)`, isn't tracked, and neither are changes made with plain SQL.

To disable the Database tracker, specify this in the configuration file:

```ini
ckanext.event_audit.track_model = false
```

We can ignore specific models from being tracked by setting the `ckanext.event_audit.ignore.models` configuration option. See the [ignore](ignore.md) section for more details.

### Track only specific models

If you want to track only specific models, you can set the `ckanext.event_audit.track.models` configuration option. This will ignore all the models that are not specified in the list.

```ini
ckanext.event_audit.track.models = Package Resource User
```

???+ Warning
    1. The model names are case-sensitive.
    2. Tracking specific models have a priority over ignoring specific models. If you specify the models to track, the ignore list will be ignored.

### Track previous model state

By default, the extension doesn't track the previous state of the model. If you want to track the previous state of the model, you can enable it by setting the following configuration option:

```ini
ckanext.event_audit.track.store_previous_model_state = true
```

???+ Warning
    The previous state is stored in the `result` of the event, so this option only has an effect
    together with [`store_payload_and_result`](#storing-payload-and-result-data). On its own, it
    does nothing.

The `event` result field contains two keys: `old` and `new`. If this option is enabled, the `old` key will contain the previous state of the model:

```json
{
  "old": {
    ...
  },
  "new": {
    ...
  }
}
```

## Storing payload and result data

Storing `payload` and `result` data for in-built trackers is disabled by default, as it might be too expensive to store all the data. You can enable it by setting the following configuration options:

```ini
ckanext.event_audit.store_payload_and_result = true
```

???+ Warning
    Enabling this option might have a significant impact on the storage size. Use it with caution.

???+ Danger
    The data is stored **as it is**. Payloads of actions like `user_create` contain passwords,
    the result of `api_token_create` contains the token, and the rows of the `User` model contain
    the password hash, the reset key and the email address. Nothing is redacted by default, and with the CloudWatch
    repository the data leaves your server. Read [Security](../security.md) before enabling this option.

## Limiting anonymous events

Every recorded event is a write, and anyone can send requests. To keep a flood of anonymous requests
from filling up the repository, or from crowding the events of signed-in users out of the
[write queue](async.md#queue-size), the events that anonymous users cause are limited:

```ini
ckanext.event_audit.anonymous.rate_limit = 1000
```

This is the number of events per minute that are recorded for anonymous users. The surplus is
**dropped**, and a warning is logged, once a minute at most. By default, it is 1000.
Set it to `0` to remove the limit.

A few things to keep in mind:

* Only events caused by requests of anonymous users count. Signed-in users, the command line and
  background jobs are never limited.
* The limit is per process: with 4 workers, up to 4 times the number is recorded.
* Events that are [ignored](ignore.md) don't count, so ignoring the actions that anonymous
  visitors call most often is still the best way to keep the volume down.
* The dropped events are gone. On a busy public site that must record every anonymous call,
  raise the limit rather than remove it, and size the repository for it.

## Custom trackers

You can create and write an event anywhere in your codebase. See the [usage](../usage.md) section for more details.
