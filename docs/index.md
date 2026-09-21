[![Tests](https://github.com/DataShades/ckanext-event-audit/actions/workflows/test.yml/badge.svg)](https://github.com/DataShades/ckanext-event-audit/actions/workflows/test.yml)

# ckanext-event-audit

This extension will capture and retain a comprehensive record of all changes within a CKAN app.

* API calls and database changes are recorded out of the box, and you can record your own events.
* Events are kept in Redis, PostgreSQL or AWS CloudWatch, or in a repository of your own.
* A dashboard, reports in several formats and a command line tool let you look at the events.

Start with the [installation](install.md).

## Developer installation

To install ckanext-event-audit for development, activate your CKAN virtualenv and
do:

    git clone https://github.com/DataShades/ckanext-event-audit.git
    cd ckanext-event-audit
    pip install -e '.[dev]'

The extension depends on [ckanext-tables](https://github.com/DataShades/ckanext-tables) for the dashboard.

## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini

The tests need Redis, Solr and PostgreSQL, like any CKAN extension.

## Documentation

To build the documentation, install the docs extras and run mkdocs:

    pip install -e '.[docs]'
    mkdocs serve

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
