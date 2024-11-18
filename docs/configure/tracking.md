There are two built-in trackers in the extension that are enabled by default and work out of the box - API and Database trackers.

## API tracker

Captures all events that are triggered by the CKAN API. Everything that is called via `tk.get_action` will be tracked by this tracker, unless it's explicitly ignored by the configuration. See the [ignore](ignore.md) section for more details.

To disable the API tracker, specify this in the configuration file:

```ini
ckanext.event_audit.track.api = false
```

We can ignore specific actions from being tracked by setting the `ckanext.event_audit.ignore.actions` configuration option. See the [ignore](ignore.md) section for more details.

## Database tracker

We're utilising the SQLAlchemy’s event system for tracking database interactions. The audit event creation will be triggered when the model is created, updated, or deleted.

To disable the Database tracker, specify this in the configuration file:

```ini
ckanext.event_audit.track.model = false
```

We can ignore specific models from being tracked by setting the `ckanext.event_audit.ignore.models` configuration option. See the [ignore](ignore.md) section for more details.

## Custom trackers

You can create and write an event anywhere in your codebase. 

TODO: add link to usage docs
