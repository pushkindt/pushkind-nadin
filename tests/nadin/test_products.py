import pandas as pd

from nadin import products


def test_clean_column_name():
    assert products.clean_column_name("  Test  ") == "test"
    assert products.clean_column_name("tesT") == "test"
    assert products.clean_column_name("  test   test  ") == "test_test"
    assert products.clean_column_name("  test.test  ") == "test_test"


def test_option_columns_to_json():
    assert (
        products.option_columns_to_json(pd.Series(["test", "test2"], index=["col1", "col2"]))
        == '{"col1": ["test"], "col2": ["test2"]}'
    )
    assert products.option_columns_to_json(pd.Series(["test"], index=["col1"])) == '{"col1": ["test"]}'
    assert products.option_columns_to_json(pd.Series([])) == ""


def test_price_columns_to_json():
    assert (
        products.price_columns_to_json(pd.Series([10.0, 20.0], index=["prices_online_store", "prices_marketplace"]))
        == '{"online_store": 10.0, "marketplace": 20.0}'
    )
    assert products.price_columns_to_json(pd.Series([10.0], index=["prices_online_store"])) == '{"online_store": 10.0}'
    assert products.price_columns_to_json(pd.Series([])) == "{}"


def test_process_product_tags():
    product_ids = {
        "a": 1,
        "b": 2,
    }
    df_tags = pd.DataFrame(
        {
            "sku": ["a", "b", "c"],
            "tags": ["tag1", "tag2,tag3", None],
        }
    )
    expected = pd.DataFrame(
        {
            "product_id": [1, 2, 2],
            "tag": ["tag1", "tag2", "tag3"],
        },
    )
    expected["product_id"] = expected["product_id"].astype("int64")
    result = products.process_product_tags(product_ids, df_tags)
    pd.testing.assert_frame_equal(result, expected)


def test_process_string_columns():
    df = pd.DataFrame(
        {
            "sku": [1, 2, 3],
            "name": ["name1", "name2", "name3"],
            "description": ["desc1", "desc2", "desc3"],
        }
    )
    expected = pd.DataFrame(
        {
            "sku": ["1", "2", "3"],
            "name": ["name1", "name2", "name3"],
            "description": ["desc1", "desc2", "desc3"],
        }
    )
    result = products.process_string_columns(df, ["sku", "name", "description"])
    pd.testing.assert_frame_equal(result, expected)


def test_process_images_column():
    df1 = pd.DataFrame(
        {
            "a": ["1", "2", "3"],
            "images": ["image1", "image1,image2", "image1, image2"],
        }
    )
    df2 = pd.DataFrame(
        {
            "a": ["1", "2", "3"],
        }
    )
    expected = pd.DataFrame(
        {
            "a": ["1", "2", "3"],
            "images": ['["image1"]', '["image1", "image2"]', '["image1", "image2"]'],
        }
    )
    result1 = products.process_images_column(df1)
    result2 = products.process_images_column(df2)
    pd.testing.assert_frame_equal(result1, expected)
    pd.testing.assert_frame_equal(result2, df2)


def test_process_category_column():
    df = pd.DataFrame(
        {
            "sku": ["1", "2", "3"],
            "category": ["category1", "category2", "category3"],
        }
    )
    categories = {
        "category1": 1,
        "category2": 2,
        "category3": 3,
    }
    expected = pd.DataFrame(
        {
            "sku": ["1", "2", "3"],
            "cat_id": [1, 2, 3],
        }
    )
    result = products.process_category_column(df, categories)
    pd.testing.assert_frame_equal(result, expected)


def test_process_price_columns():
    df = pd.DataFrame(
        {
            "price": ["1.0", "2.0", "3.0"],
            "prices_online_store": ["1", "2", "3"],
            "prices_marketplace": ["4", "5", "6"],
        }
    )
    expected = pd.DataFrame(
        {
            "price": [1.0, 2.0, 3.0],
            "prices": [
                '{"online_store": 1.0, "marketplace": 4.0}',
                '{"online_store": 2.0, "marketplace": 5.0}',
                '{"online_store": 3.0, "marketplace": 6.0}',
            ],
        }
    )
    result = products.process_price_columns(df)
    pd.testing.assert_frame_equal(result, expected)


def test_extra_columns_to_options():
    df = pd.DataFrame(
        {
            "sku": ["1", "2", "3"],
            "color": ["red", "blue", "green"],
            "size": ["S", "M", "L"],
        }
    )
    expected = pd.DataFrame(
        {
            "sku": ["1", "2", "3"],
            "options": [
                '{"color": ["red"], "size": ["S"]}',
                '{"color": ["blue"], "size": ["M"]}',
                '{"color": ["green"], "size": ["L"]}',
            ],
        }
    )
    result = products.extra_columns_to_options(df, ["sku"])
    pd.testing.assert_frame_equal(result, expected)


def test_process_products():
    existing_products = pd.DataFrame(
        {
            "sku": ["1", "2", "3"],
            "name": ["name1", "name2", "name3"],
            "description": ["desc1", "desc2", "desc3"],
            "cat_id": [1, 2, 3],
            "price": [1.0, 2.0, 3.0],
            "prices": [
                '{"online_store": 1.0, "marketplace": 4.0}',
                '{"online_store": 2.0, "marketplace": 5.0}',
                '{"online_store": 3.0, "marketplace": 6.0}',
            ],
            "image": [None, None, None],
            "images": ['["image1"]', '["image1", "image2"]', '["image1", "image2"]'],
            "options": [
                '{"color": ["red"], "size": ["S"]}',
                '{"color": ["blue"], "size": ["M"]}',
                '{"color": ["green"], "size": ["L"]}',
            ],
        }
    )
    new_products = pd.DataFrame(
        {
            "sku": ["1", "4", "5", "6"],
            "name": ["n1", "n4", "n5", "n6"],
            "category": ["category1", "category4", "category5", "category1"],
            "price": ["1.0", "4.0", "5.0", "6"],
            "prices.online_store": ["1", "4", "5", "6"],
            "prices.marketplace": ["4", "7", "8", "9"],
            "image": ["image1", "image4", "image5", "image6"],
            "images": ["image1", "image4", "image5", "image1, image6"],
            "color": ["red", "blue", None, None],
            "size": ["S", "M", None, None],
        }
    )
    categories = {
        "category1": 1,
        "category4": 4,
        "category5": 5,
    }
    result = products.process_products(new_products, existing_products, categories)
    expected = pd.DataFrame(
        {
            "sku": ["1", "2", "3", "4", "5", "6"],
            "description": ["desc1", "desc2", "desc3", None, None, None],
            "cat_id": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0],
            "image": ["image1", None, None, "image4", "image5", "image6"],
            "images": [
                '["image1"]',
                '["image1", "image2"]',
                '["image1", "image2"]',
                '["image4"]',
                '["image5"]',
                '["image1", "image6"]',
            ],
            "name": ["n1", "name2", "name3", "n4", "n5", "n6"],
            "options": [
                '{"color": ["red"], "size": ["S"]}',
                '{"color": ["blue"], "size": ["M"]}',
                '{"color": ["green"], "size": ["L"]}',
                '{"color": ["blue"], "size": ["M"]}',
                None,
                None,
            ],
            "price": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "prices": [
                '{"online_store": 1.0, "marketplace": 4.0}',
                '{"online_store": 2.0, "marketplace": 5.0}',
                '{"online_store": 3.0, "marketplace": 6.0}',
                '{"online_store": 4.0, "marketplace": 7.0}',
                '{"online_store": 5.0, "marketplace": 8.0}',
                '{"online_store": 6.0, "marketplace": 9.0}',
            ],
        }
    )

    pd.testing.assert_frame_equal(result, expected)
