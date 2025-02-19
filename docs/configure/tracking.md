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

## Custom trackers

You can create and write an event anywhere in your codebase. See the [usage](../usage.md) section for more details.


