import pytest

import plum
from plum.promotion import _convert, _promotion_rule


@pytest.fixture
def convert():
    # Save methods.
    all_methods = _convert._methods_registry._all_methods

    yield plum.convert

    # Clear methods after use.
    _convert._methods_registry._all_methods = all_methods
    _convert.clear_cache()


@pytest.fixture
def promote():
    # Save methods.
    all_methods = _promotion_rule._methods_registry._all_methods

    yield plum.promote

    # Clear methods after use.
    _promotion_rule._methods_registry._all_methods = all_methods
    _promotion_rule.clear_cache()
