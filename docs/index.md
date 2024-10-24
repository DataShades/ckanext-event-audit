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


## Register new repositories

There are few repositories available by default, but you can register new repositories to store the events. Think of it as a way to store the events in different databases or services. We don't want to limit the extension to a specific storage. The main idea is to provide a way to store, retrieve, and filter the events.

To register a new repository, you need to define a repository class and register it.

### Defining the repository class

To register a new repository, you need to define a repository class that inherits from `AbstractRepository` and implements the following methods: `write_event`, `get_event`, and `filter_events`.

For example:

```python
from ckanext.event_audit.repositories import AbstractRepository
from ckanext.event_audit import types


class MyRepository(AbstractRepository):
    name = "my_repository"

    @classmethod
    def get_name(cls) -> str:
        return "my_repository"

    def write_event(self, event: types.Event) -> types.WriteStatus:
        pass

    def get_event(self, event_id: str) -> types.Event | None:
        pass

    def filter_events(self, filters: types.Filters) -> list[types.Event]:
        pass
```

See the existing repositories as examples (`ckanext/event_audit/repositories/`).

### Registering the repository

To register the new repository, you need to use a IEventAudit interface and the `register_repository` method.

For example:

```python
from ckanext.event_audit.interfaces import IEventAudit
from ckanext.your_extension.repositories import MyRepository

class MyRepositoryPlugin(plugins.SingletonPlugin):
    ...
    plugins.implements(IEventAudit, inherit=True)

    # IEventAudit

    def register_repository(self) -> dict[str, type[AbstractRepository]]:
        return {
            MyRepository.get_name(): MyRepository,
        }
```


## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
