[![Tests](https://github.com/DataShades/ckanext-event-audit/actions/workflows/test.yml/badge.svg)](https://github.com/DataShades/ckanext-event-audit/actions/workflows/test.yml)

# ckanext-event-audit

This extension will capture and retain a comprehensive record of all changes within a CKAN app.

Read the [documentation](https://datashades.github.io/ckanext-event-audit/) for a full user guide.

## Quick start

1. Install the extension from `PyPI`.
    `pip install -e .`

2. Enable the plugin in your CKAN configuration file (e.g. `ckan.ini` or `production.ini`). The
   events dashboard is built on [ckanext-tables](https://github.com/DataShades/ckanext-tables),
   so `tables` must be enabled as well, or the dashboard page will fail with a
   `TemplateNotFound` error:

    `ckan.plugins = ... tables event_audit ...`

3. Run DB migrations:

    `ckan db upgrade -p event_audit`

    `ckan db pending-migrations` only lists the pending migrations, unless you add `--apply`.

4. Configure the extension up to your needs and you're ready to go. See the [documentation](https://datashades.github.io/ckanext-event-audit/) for more details about the configuration options, and read the [security notes](https://datashades.github.io/ckanext-event-audit/security/) before storing payloads and results.

## Developer installation

To install ckanext-event-audit for development, activate your CKAN virtualenv and
do:

    pip install -e '.[dev]'

To build the documentation, install the docs extras and run mkdocs:

    pip install -e '.[docs,dev]'
    mkdocs serve

## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
