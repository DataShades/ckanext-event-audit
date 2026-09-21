# Ignore events

The extension provides a various set of configuration options to adjust the behavior of the audit logs.

???+ warning "Warning"

    These config options are applicable only for built-in tracking methods (API, Database) and not related to client's usage of the extension.

All the options below are space-separated lists. Setting an option **replaces** its default
value: it doesn't add to it.

## Ignoring categories

The extension allows to ignore specific categories of events. To do this, we have to set the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.ignore.categories = view
```

By default, we're not ignoring any categories. The built-in trackers use the `api` and `model` categories.

Categories are arbitrary strings that can be used to group events.

## Ignoring actions

The extension allows to ignore specific actions. To do this, we have to set the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.ignore.actions = package_show package_search
```

Some actions might be called more frequently than others, and we might not be interested in storing them.

By default, we're excluding next actions from being stored:

* `resource_view_list`
* `editable_config_list`
* `editable_config_change`
* `get_site_user`
* `ckanext_pages_list`
* `user_show`
* `package_search`
* `package_show`
* `task_status_update`
* `task_status_show`

???+ warning
    Because setting the option replaces the default list, the example above records
    `user_show`, `resource_view_list` and the rest again. Repeat the defaults that you want to
    keep ignoring.

Read-only actions like `package_show` are the most frequent ones. Recording them increases the
number of events quickly, and anyone, including anonymous visitors and crawlers, can trigger
them. Think twice before removing them from the list.

## Ignoring models

The extension allows to ignore specific models. To do this, we have to set the following configuration option in the CKAN configuration file:

```ini
ckanext.event_audit.ignore.models = User Package Resource
```

By default, we're excluding next models from being stored:

* `Option`

The model names are case-sensitive. To record only some models, see [track only specific
models](tracking.md#track-only-specific-models): the list of tracked models has priority over
this one.
