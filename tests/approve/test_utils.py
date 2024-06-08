from nadin.utils import first


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
