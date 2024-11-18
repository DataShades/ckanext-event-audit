# Ignore events

The extension provides a various set of configuration options to adjust the behavior of the audit logs.

???+ warning "Warning"

    These config options are applicable only for built-in tracking methods (API, Database) and not related to client's usage of the extension.

## Ignoring categories

The extension allows to ignore specific categories of events. To do this, we have to set the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.ignore.categories = test
```

By default, we're not ignoring any categories. The `categories` option is a comma-separated list of categories that should be ignored.

Categories are arbitrary strings that can be used to group events.

## Ignoring actions

The extension allows to ignore specific actions. To do this, we have to set the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.ignore.actions = test
```

Some actions might be called more frequently than others, and we might not be interested in storing them. The `actions` option is a comma-separated list of actions that should be ignored.

By default, we're excluding next actions from being stored:

* `editable_config_list`
* `editable_config_change`
* `get_site_user`
* `ckanext_pages_list`
* `user_show`

## Ignoring models

The extension allows to ignore specific models. To do this, we have to set the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.ignore.models = User Package Resource
```

By default, we're excluding next models from being stored:

* `Option`
