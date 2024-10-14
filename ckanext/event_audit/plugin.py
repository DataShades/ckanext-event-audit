import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit


class EventAuditPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)


    # IConfigurer

    def update_config(self, config_):
        toolkit.add_resource("assets", "event_audit")
