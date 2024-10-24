from __future__ import annotations

import os

import yaml

import ckan.plugins.toolkit as tk
from ckan import plugins as p
from ckan.config.declaration import Declaration, Key
from ckan.logic import clear_validators_cache


@tk.blanket.config_declarations
@tk.blanket.validators
class EventAuditPlugin(p.SingletonPlugin):
    p.implements(p.IConfigDeclaration)

    # IConfigDeclaration

    def declare_config_options(self, declaration: Declaration, key: Key):
        # this call allows using custom validators in config declarations
        clear_validators_cache()

        here = os.path.dirname(__file__)
        with open(os.path.join(here, "config_declaration.yaml"), "rb") as src:
            declaration.load_dict(yaml.safe_load(src))
