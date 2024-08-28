from io import StringIO

import pandas as pd
from flask import render_template
from flask_login import current_user, login_required
from sqlalchemy import text

from nadin.extensions import db
from nadin.main.routes import bp
from nadin.models.hub import UserCategory, UserProject, UserRoles
from nadin.models.order import OrderStatus, Project, User
from nadin.models.product import Category
from nadin.utils import role_forbidden

################################################################################
# Responibility page
################################################################################


@bp.route("/help/", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def ShowHelp():
    with db.get_engine().connect() as conn:
        stats = pd.read_sql(
            text(
                f"""select
                '' as status,
                '' as `project_name`,
                '' as category_name,
                sum(total) as price,
                count(*) as `cnt`
                from `order`
                union all
                select
                o.status,
                p.name as project_name,
                c.name as category_name,
                sum(o.total) as price,
                count(*) as `cnt`
                from `order` o
                inner join project p on o.project_id = p.id
                inner join order_category oc on o.id = oc.order_id
                inner join category c on oc.category_id = c.id
                where o.hub_id = {current_user.hub_id}
                group by o.status, s.name, c.name
                order by o.status, s.name, c.name"""
            ),
            con=conn,
        )
    buf = StringIO()
    stats["status"] = stats["status"].apply(lambda x: OrderStatus[x] if x != "" else "")
    stats.rename(
        {
            "status": "Статус",
            "project_name": "Клиент",
            "category_name": "Категория",
            "price": "Сумма",
            "cnt": "Кол-во",
        },
        inplace=True,
        axis=1,
    )
    stats.to_html(
        buf=buf,
        classes=["table", "table-striped", "table-sm"],
        float_format=lambda x: f"{x:.2f}",
        table_id="statsTable",
    )
    buf.seek(0)
    project_responsibility = {}
    projects = Project.query.filter_by(hub_id=current_user.hub_id).join(UserProject)
    projects = projects.join(User).filter_by(role=UserRoles.validator).order_by(Project.name).all()

    for project in projects:
        project_responsibility[project.name] = {
            "users": project.users,
            "positions": set(),
        }
        for user in project.users:
            position = user.position.name if user.position else "не указана"
            project_responsibility[project.name]["positions"].add(position)

    category_responsibility = {}
    categories = Category.query.filter_by(hub_id=current_user.hub_id).join(UserCategory)
    categories = categories.join(User).filter_by(role=UserRoles.validator).order_by(Category.name)
    categories = categories.all()

    for category in categories:
        category_responsibility[category.name] = {
            "users": category.users,
            "positions": set(),
        }
        for user in category.users:
            position = user.position.name if user.position else "не указана"
            category_responsibility[category.name]["positions"].add(position)

    return render_template(
        "help.html",
        projects=project_responsibility,
        categories=category_responsibility,
        stats=buf,
    )
