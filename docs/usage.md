To use an event audit in your extension, you should get an instance of the repository class. There are two ways to do this:

1. **Using the `get_repo` function**:

    ```python
    import ckanext.event_audit.utils as utils

    repo = utils.get_active_repo()

    event = repo.build_event({"category": "xxx", "action": "xxx"})

    repo.write_event(event)
    ```

    The `get_active_repo` function will return an instance of the active repository class that is configured in the CKAN configuration file.

2. **Using the `get_repo` function with a specific repository**:

    ```python
    import ckanext.event_audit.utils as utils

    repo = utils.get_repo("file")

    event = repo.build_event({"category": "xxx", "action": "xxx"})

    repo.write_event(event)
    ```

    The `get_repo` function will return an instance of the repository class that is specified in the argument. You can use this method to get a specific repository instance.
