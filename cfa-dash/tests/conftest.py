import pytest


@pytest.fixture
def app_ctx():
    import app as zapp

    with zapp.server.test_request_context("/"):
        yield
