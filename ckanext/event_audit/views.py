from __future__ import annotations

from flask import Blueprint

import ckan.plugins as p
import ckan.plugins.toolkit as tk

from ckanext.event_audit import utils

event_audit = Blueprint("event_audit", __name__)

if p.plugin_loaded("admin_panel"):
    from ckanext.ap_main.utils import ap_before_request
    from ckanext.ap_main.views.generics import ApConfigurationPageView

    event_audit.before_request(ap_before_request)

    event_audit.add_url_rule(
        "/admin-panel/event_audit/config",
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

