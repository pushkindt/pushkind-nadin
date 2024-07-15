from typing import Protocol

from flask import current_app


class SearchableModel(Protocol):
    id: int
    __searchable__: list


def add_to_index(index: str, model: SearchableModel):
    if not current_app.elasticsearch:
        return
    payload = {}
    for field in model.__searchable__:
        payload[field] = getattr(model, field)
    current_app.elasticsearch.index(index=index, id=model.id, document=payload)


def remove_from_index(index: str, model: SearchableModel):
    if not current_app.elasticsearch:
        return
    current_app.elasticsearch.delete(index=index, id=model.id)


def query_index(index: str, query: str, page: int, per_page: int) -> tuple[list, int]:
    if not current_app.elasticsearch:
        return [], 0
    search = current_app.elasticsearch.search(
        index=index,
        query={"multi_match": {"query": query, "fields": ["*"]}},
        from_=(page - 1) * per_page,
        size=per_page,
    )
    ids = [int(hit["_id"]) for hit in search["hits"]["hits"]]
    return ids, search["hits"]["total"]["value"]
