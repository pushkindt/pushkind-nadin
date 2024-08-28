from nadin.models.order import Order
from nadin.models.shopping_cart import ApiShoppingCartModel


def test_can_load_from_json(shopping_cart):
    ApiShoppingCartModel.model_validate_json(shopping_cart)


def test_can_create_order(app, shopping_cart):
    cart = ApiShoppingCartModel.model_validate_json(shopping_cart)
    order = Order.from_api_request("admin@example.com", cart)
    assert order.initiative_id == 1
    assert len(order.products) == len(cart.items)
