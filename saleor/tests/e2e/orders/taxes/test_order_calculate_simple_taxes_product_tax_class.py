import pytest

from ... import DEFAULT_ADDRESS
from ...product.utils import update_product
from ...product.utils.preparing_product import prepare_product
from ...shop.utils.preparing_shop import prepare_shop
from ...taxes.utils import update_country_tax_rates
from ...utils import assign_permissions
from ..utils import (
    draft_order_complete,
    draft_order_create,
    draft_order_update,
    order_lines_create,
)


@pytest.mark.e2e
def test_order_calculate_simple_tax_based_on_product_tax_class_CORE_2006(
    e2e_staff_api_client,
    shop_permissions,
    permission_manage_product_types_and_attributes,
    permission_manage_orders,
):
    # Before
    permissions = [
        *shop_permissions,
        permission_manage_product_types_and_attributes,
        permission_manage_orders,
    ]
    assign_permissions(e2e_staff_api_client, permissions)

    shop_data = prepare_shop(
        e2e_staff_api_client,
        country_code="US",
        country_tax_rate=20,
        product_tax_rate=13,
        prices_entered_with_tax=False,
    )
    channel_id = shop_data["channel_id"]
    warehouse_id = shop_data["warehouse_id"]
    shipping_method_id = shop_data["shipping_method_id"]
    product_tax_rate = shop_data["product_tax_rate"]
    country_tax_rate = shop_data["country_tax_rate"]
    product_tax_class_id = shop_data["product_tax_class_id"]
    country = shop_data["country"]
    update_country_tax_rates(
        e2e_staff_api_client,
        country,
        [{"rate": country_tax_rate}],
    )
    variant_price = "1234"
    (product_id, product_variant_id, product_variant_price) = prepare_product(
        e2e_staff_api_client,
        warehouse_id,
        channel_id,
        variant_price,
    )
    product_tax_class = {"taxClass": product_tax_class_id}
    update_product(e2e_staff_api_client, product_id, input=product_tax_class)

    # Step 1 - Create a draft order
    input = {
        "channelId": channel_id,
        "billingAddress": DEFAULT_ADDRESS,
        "shippingAddress": DEFAULT_ADDRESS,
    }
    data = draft_order_create(
        e2e_staff_api_client,
        input,
    )
    order_id = data["order"]["id"]
    assert data["order"]["billingAddress"] is not None
    assert data["order"]["shippingAddress"] is not None
    product_variant_price = float(product_variant_price)

    # Step 2 - Add product to draft order and check prices
    lines = [{"variantId": product_variant_id, "quantity": 1}]
    order_data = order_lines_create(
        e2e_staff_api_client,
        order_id,
        lines,
    )
    order_data = order_data["order"]
    calculated_tax = round(
        (product_variant_price * (product_tax_rate / 100)),
        2,
    )
    assert order_data["total"]["net"]["amount"] == product_variant_price
    assert order_data["total"]["tax"]["amount"] == calculated_tax
    assert order_data["total"]["gross"]["amount"] == round(
        product_variant_price + calculated_tax, 2
    )
    shipping_method_id = order_data["shippingMethods"][0]["id"]
    shipping_price = order_data["shippingMethods"][0]["price"]["amount"]

    # Step 3 - Add a shipping method to the order and check prices
    input = {"shippingMethod": shipping_method_id}
    order_data = draft_order_update(
        e2e_staff_api_client,
        order_id,
        input,
    )
    order_data = order_data["order"]
    shipping_tax = round((shipping_price * (country_tax_rate / 100)), 2)
    total_tax = calculated_tax + shipping_tax
    calculated_net = round(product_variant_price + shipping_price, 2)

    assert order_data["shippingPrice"]["net"]["amount"] == shipping_price
    assert order_data["shippingPrice"]["tax"]["amount"] == shipping_tax
    assert order_data["shippingPrice"]["gross"]["amount"] == round(
        shipping_price + shipping_tax, 2
    )

    # Step 4 - Complete the draft order
    order = draft_order_complete(
        e2e_staff_api_client,
        order_id,
    )
    assert order["order"]["status"] == "UNFULFILLED"
    assert order["order"]["paymentStatus"] == "NOT_CHARGED"
    assert order_data["total"]["tax"]["amount"] == total_tax
    assert order_data["total"]["net"]["amount"] == calculated_net
    assert order_data["total"]["gross"]["amount"] == round(
        calculated_net + total_tax, 2
    )
