import ckan.plugins as plugins
import ckan.plugins.toolkit as tk


@tk.blanket.config_declarations
class EventAuditPlugin(plugins.SingletonPlugin):
    pass
