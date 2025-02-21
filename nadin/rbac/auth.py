from functools import wraps

from flask import abort
from flask_login import current_user
from sqlalchemy.orm import aliased

from nadin.extensions import cache, db
from nadin.models.hub import Action, ActionRole, Role, UserRole


@cache.memoize(timeout=30)  # Cache for 30 seconds
def get_user_permissions(user_id, action_name):
    role_alias = aliased(Role)
    action_alias = aliased(Action)
    return db.session.query(
        db.exists().where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_alias.id,
            ActionRole.role_id == role_alias.id,
            ActionRole.action_id == action_alias.id,
            action_alias.name == action_name,
        )
    ).scalar()


def rbac_required(action_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)

            has_permission = get_user_permissions(current_user.id, action_name)

            if not has_permission:
                abort(403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator
