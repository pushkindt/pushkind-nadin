from datetime import datetime as dt

from flask import current_app, render_template, request
from flask_login import current_user, login_required

from nadin.extensions import db
from nadin.main.routes import bp
from nadin.models.order import EventType, Order, OrderEvent, UserRoles
from nadin.utils import get_filter_timestamps, role_forbidden

################################################################################
# Responibility page
################################################################################


@bp.route("/history/", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor, UserRoles.initiative])
def ShowHistory():
    dates = get_filter_timestamps()
    filter_from = request.args.get("from", default=dates["recently"], type=int)
    dates["сегодня"] = dates.pop("daily")
    dates["неделя"] = dates.pop("weekly")
    dates["месяц"] = dates.pop("monthly")
    dates["квартал"] = dates.pop("quarterly")
    dates["год"] = dates.pop("annually")
    dates["недавно"] = dates.pop("recently")

    search_key = request.args.get("q", type=str)
    page = request.args.get("page", type=int, default=1)

    if search_key:
        events, total = OrderEvent.search(search_key, page, current_app.config["MAX_PER_PAGE"])
    else:
        events = OrderEvent.query

    events = events.filter(OrderEvent.timestamp > dt.fromtimestamp(filter_from))
    events = events.join(Order).filter_by(hub_id=current_user.hub_id)
    events = events.order_by(OrderEvent.timestamp.desc())

    if search_key:
        events = db.paginate(events, page=1, max_per_page=current_app.config["MAX_PER_PAGE"])
        events.total = total
        events.page = page
    else:
        events = events.order_by(OrderEvent.timestamp.desc())
        events = db.paginate(events, page=page, max_per_page=current_app.config["MAX_PER_PAGE"])

    return render_template(
        "main/history/history.html", events=events, EventType=EventType, filter_from=filter_from, dates=dates
    )
