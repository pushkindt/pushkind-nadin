import sqlalchemy as sa

from nadin import search
from nadin.extensions import db


class SearchableMixin:
    __searchable__: list = []

    @classmethod
    def search(cls, expr: str, page: int, per_page: int, fields: list = None):
        ids, total = search.query_index(cls.__tablename__, expr, page, per_page, fields=fields)
        query = sa.select(cls).where(cls.id.in_(ids))
        if total > 0:
            when = []
            for i, val in enumerate(ids):
                when.append((val, i))
            query = query.order_by(db.case(*when, value=cls.id))
        return query, total

    @classmethod
    def before_commit(cls, session):
        session._changes = {"add": list(session.new), "update": list(session.dirty), "delete": list(session.deleted)}

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes["add"]:
            if isinstance(obj, SearchableMixin):
                search.add_to_index(obj.__tablename__, obj)
        for obj in session._changes["update"]:
            if isinstance(obj, SearchableMixin):
                search.add_to_index(obj.__tablename__, obj)
        for obj in session._changes["delete"]:
            if isinstance(obj, SearchableMixin):
                search.remove_from_index(obj.__tablename__, obj)
        session._changes = None

    @classmethod
    def reindex(cls):
        for obj in db.session.scalars(sa.select(cls)):
            search.add_to_index(cls.__tablename__, obj)


db.event.listen(db.session, "before_commit", SearchableMixin.before_commit)
db.event.listen(db.session, "after_commit", SearchableMixin.after_commit)
