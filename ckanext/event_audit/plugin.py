from __future__ import annotations

from pathlib import Path

import yaml

import ckan.plugins.toolkit as tk
from ckan import plugins as p
from ckan.common import CKANConfig
from ckan.config.declaration import Declaration, Key
from ckan.logic import clear_validators_cache
from ckan.types import SignalMapping

from ckanext.event_audit import config, listeners, utils, worker


@tk.blanket.validators
@tk.blanket.cli
@tk.blanket.blueprints
@tk.blanket.helpers
class EventAuditPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurable)
    p.implements(p.IConfigurer)
    p.implements(p.ISignal)
    p.implements(p.IConfigDeclaration)

    # IConfigurer
    def update_config(self, config_: CKANConfig):
        tk.add_template_directory(config_, "templates")

    # IConfigurable

    def configure(self, config_: CKANConfig) -> None:
        self.repo = utils.get_active_repo(True)

        if config.is_threaded_mode_enabled():
            worker.start_writer_thread()

    # ISignal

    def get_signal_subscriptions(self) -> SignalMapping:
        mapping: SignalMapping = {
            tk.signals.action_succeeded: [
                listeners.api.action_succeeded_subscriber,
            ],
        }

        if config.is_admin_panel_enabled():
            mapping.update(
                {
                    tk.signals.ckanext.signal("ap_main:collect_config_sections"): [
                        self.collect_config_sections_subs
                    ],
                    tk.signals.ckanext.signal("ap_main:collect_config_schemas"): [
                        self.collect_config_schemas_subs
                    ],
                }
            )

        return mapping

    @staticmethod
    def collect_config_sections_subs(sender: None):
        configs = [
            {
                "name": "Configuration",
                "blueprint": "event_audit.config",
                "info": "Event Audit",
            },
        ]

        if utils.is_dashboard_available():
            configs.append(
                {
                    "name": "Events dashboard",
                    "blueprint": "event_audit_dashboard.dashboard",
                    "info": "A list of all events",
                }
            )

        return {"name": "Event Audit", "configs": configs}

    @staticmethod
    def collect_config_schemas_subs(sender: None):
        return ["ckanext.event_audit:config_schema.yaml"]

    # IConfigDeclaration

    def declare_config_options(self, declaration: Declaration, key: Key):
        # this call allows using custom validators in config declarations
        # we need it for CKAN 2.10, as this PR wasn't backported
        # https://github.com/ckan/ckan/pull/7614
        clear_validators_cache()
        here = Path(__file__).parent

        with (here / "config_declaration.yaml").open("rb") as src:
            declaration.load_dict(yaml.safe_load(src))
