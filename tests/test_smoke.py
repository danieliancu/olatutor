import pytest
from django.contrib.auth import get_user_model
from django.test import Client


@pytest.mark.django_db
def test_healthz_reports_database_ok() -> None:
    response = Client().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_custom_user_model_is_active() -> None:
    assert get_user_model()._meta.label == "accounts.User"
