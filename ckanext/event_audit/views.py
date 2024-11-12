from __future__ import annotations

from flask import Blueprint
from flask.views import MethodView

import ckan.plugins as p
import ckan.plugins.toolkit as tk

from ckanext.event_audit import utils

event_audit = Blueprint("event_audit", __name__, url_prefix="/admin-panel/event_audit")

if p.plugin_loaded("admin_panel"):
    from ckan.logic import parse_params

    from ckanext.ap_main.utils import ap_before_request
    from ckanext.ap_main.views.generics import ApConfigurationPageView
    from ckanext.collection.shared import get_collection

    event_audit.before_request(ap_before_request)

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

    class EventAuditListView(MethodView):
        def get(self) -> str:
            return tk.render(
                "event_audit/event_audit_list.html",
                extra_vars={
                    "collection": get_collection(
                        "event-audit-list", parse_params(tk.request.args)
                    )
                },
            )

    event_audit.add_url_rule(
        "/dashboard", view_func=EventAuditListView.as_view("dashboard")
    )
