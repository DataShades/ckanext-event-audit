from __future__ import annotations

import ckan.plugins.toolkit as tk
from ckan import plugins as p


@tk.blanket.config_declarations
@tk.blanket.validators
@tk.blanket.cli
class EventAuditPlugin(p.SingletonPlugin):
    pass
