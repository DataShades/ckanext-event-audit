[![Tests](https://github.com/DataShades/ckanext-event-audit/actions/workflows/test.yml/badge.svg)](https://github.com/DataShades/ckanext-event-audit/actions/workflows/test.yml)

# ckanext-event-audit

This extension will capture and retain a comprehensive record of all changes within a CKAN app. 

Read the [documentation](https://datashades.github.io/ckanext-event-audit/) for a full user guide.

TODO:
- [ ] add config option to exclude result and payload fields from being stored
- [ ] allow to restrict a list of available repos (security concern)
- [ ] disable the admin interface by default (security concern)
- [ ] update `remove_events` method to allow removing events by date range
- [ ] add a cli command to remove events by date range

## Quick start

1. Install the extension from `PyPI`:

    `pip install ckanext-event-audit`

2. Enable the plugin in your CKAN configuration file (e.g. `ckan.ini` or `production.ini`):

    `ckan.plugins = ... event_audit ...`

3. Run DB migrations. For CKAN 2.10+ we can run this command:

    `ckan db pending-migrations`

    CKAN 2.11+ allows us to run the following command to create the tables:

    `ckan db upgrade`

4. Configure the extension up to your needs and you're ready to go. See the [documentation](https://datashades.github.io/ckanext-event-audit/) for more details about the configuration options.

## Developer installation

To install ckanext-event-audit for development, activate your CKAN virtualenv and
do:

    pip install -e '.[dev, xlsx]'

## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)

