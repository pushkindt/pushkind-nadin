from html import escape

from nadin.utils import first, get_escaped_url_parameter


def test_first():
    # Test 1: When the iterable is not empty
    iterable = [1, 2, 3, 4]
    expected = 1
    result = first(iterable)
    assert result == expected

    # Test 2: When the iterable is empty
    iterable = []
    expected = None
    result = first(iterable)
    assert result == expected


def test_get_url_parameter():
    assert get_escaped_url_parameter(escape("https://example.com/?param=value"), "param") == "value"
    assert get_escaped_url_parameter(escape("https://example.com/?param1=value1&param2=value2"), "param2") == "value2"
    assert (
        get_escaped_url_parameter(escape("https://example.com/?param=%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82"), "param")
        == "привет"
    )
    assert (
        get_escaped_url_parameter(
            escape("https://example.com/?param1=value1&param2=%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82"), "param2"
        )
        == "привет"
    )
    assert get_escaped_url_parameter(escape("https://example.com/?param1=value1&param2=value2"), "param3") is None
    assert (
        get_escaped_url_parameter(
            escape("https://example.com/?param1=value1&param2=value2"), "param3", default="default"
        )
        == "default"
    )
