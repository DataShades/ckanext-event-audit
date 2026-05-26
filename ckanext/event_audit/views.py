from __future__ import annotations

from flask import Blueprint

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan.views.admin import before_request

import ckanext.tables.shared as t

from ckanext.event_audit import config, utils
from ckanext.event_audit.table import EventAuditTable

event_audit = Blueprint("event_audit", __name__, url_prefix="/admin-panel/event_audit")
event_audit.before_request(before_request)

event_audit.add_url_rule(
    "/dashboard",
    view_func=t.GenericTableView.as_view(
        "dashboard",
        table=EventAuditTable,
        breadcrumb_label=tk._("Event Audit list"),
    ),
)


if p.plugin_loaded("admin_panel") and config.is_admin_panel_enabled():
    from ckanext.ap_main.views.generics import ApConfigurationPageView

    event_audit.add_url_rule(
        "/config",
        view_func=ApConfigurationPageView.as_view(
            "config",
            "event_audit_config",
            render_template="event_audit/config.html",
            page_title=tk._("Event audit config"),
        ),
    )

    @event_audit.route("/clear_repo", methods=["POST"])
    def clear_repo():
        try:
            result = utils.get_active_repo().remove_all_events()
        except NotImplementedError:
            return tk.h.flash_error(tk._("Repository does not support this operation"))

        tk.h.flash_success(result.message)

        return tk.h.redirect_to("event_audit.config")
