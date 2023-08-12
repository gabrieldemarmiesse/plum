import beartype.claw
import pytest

beartype.claw.beartype_package("plum")


import plum  # noqa: E402
from plum.promotion import _convert, _promotion_rule  # noqa: E402


@pytest.fixture
def convert():
    # Save methods.
    _convert._resolve_pending_registrations()
    resolved = list(_convert._resolved)

    yield plum.convert

    # Clear methods after use.
    _convert._resolve_pending_registrations()
    _convert._pending = []
    _convert._resolved = resolved
    _convert.clear_cache(reregister=True)


@pytest.fixture
def promote():
    # Save methods.
    _promotion_rule._resolve_pending_registrations()
    resolved = list(_promotion_rule._resolved)

    yield plum.promote

    # Clear methods after use.
    _promotion_rule._pending = []
    _promotion_rule._resolved = resolved
    _promotion_rule.clear_cache(reregister=True)
