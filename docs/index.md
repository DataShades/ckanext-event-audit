[![Tests](https://github.com/DataShades/ckanext-event-audit/actions/workflows/test.yml/badge.svg)](https://github.com/DataShades/ckanext-event-audit/actions/workflows/test.yml)

# ckanext-event-audit

This extension will capture and retain a comprehensive record of all changes within a CKAN app.

## Developer installation

To install ckanext-event-audit for development, activate your CKAN virtualenv and
do:

    git clone https://github.com/DataShades/ckanext-event-audit.git
    cd ckanext-event-audit
    pip install -e .
    pip install -r dev-requirements.txt


## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
