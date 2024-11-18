# Installation

## Requirements

Compatibility with core CKAN versions:

| CKAN version | Compatible? |
|--------------|-------------|
| 2.9          | no          |
| 2.10         | yes         |
| 2.11         | yes         |
| master       | yes         |

## Installation

1. Install the extension from `PyPI`:
    ```sh
    pip install ckanext-event-audit
    ```

2. Enable the plugin in your CKAN configuration file (e.g. `ckan.ini` or `production.ini`):
    ```sh
    ckan.plugins = ... event_audit ...
    ```

3. Run DB migrations:
    ```sh
    ckan db upgrade -p event_audit
    ```

4. Configure the extension up to your needs and you're ready to go. See the [documentation](https://datashades.github.io/ckanext-event-audit/) for more details about the configuration options.

