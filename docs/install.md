# Installation

## Requirements

Compatibility with core CKAN versions:

| CKAN version | Compatible? |
|--------------|-------------|
| 2.9          | no          |
| 2.10         | yes         |
| 2.11         | yes         |
| 2.12         | yes         |
| master       | yes         |

The extension needs Python 3.10 or newer, and
[ckanext-tables](https://github.com/DataShades/ckanext-tables) 2.0.1 or newer, which renders the
events dashboard.

## Installation

1. Install [ckanext-tables](https://github.com/DataShades/ckanext-tables). If your package index
   doesn't offer version 2 yet, install it from GitHub:
    ```sh
    pip install https://github.com/DataShades/ckanext-tables/archive/refs/tags/v2.0.1.tar.gz
    ```

2. Install the extension from `PyPI`:
    ```sh
    pip install -e .
    ```

3. Enable the plugins in your CKAN configuration file (e.g. `ckan.ini` or `production.ini`). The
   events dashboard is built on ckanext-tables, so `tables` must be enabled as well:
    ```ini
    ckan.plugins = ... tables event_audit ...
    ```

4. Run DB migrations. They create the table used by the `postgres` repository:
    ```sh
    ckan db upgrade -p event_audit
    ```
    Running `ckan db upgrade` without `-p` applies the pending migrations of core CKAN and of all
    the plugins. `ckan db pending-migrations` only *lists* them, unless you add `--apply`.

5. Configure the extension up to your needs and you're ready to go. See the [documentation](https://datashades.github.io/ckanext-event-audit/) for more details about the configuration options.
   Read the [Security](security.md) page before you enable `store_payload_and_result`.
