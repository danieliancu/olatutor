import time
from collections.abc import Iterator
from typing import Any

import pytest
from django.db import connection
from playwright.sync_api import Browser


@pytest.fixture(autouse=True)
def quiet_database_at_teardown(transactional_db: Any, browser: Browser) -> Iterator[None]:
    """Stop every client and let in-flight requests finish before the test database is flushed.

    Otherwise a request still running in the live server can deadlock against the flush.
    """
    yield
    for context in browser.contexts:
        context.close()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> pg_backend_pid() AND state <> 'idle'"
            )
            if cursor.fetchone()[0] == 0:
                return
        time.sleep(0.05)
