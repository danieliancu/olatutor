import pytest
from django.test import Client, override_settings
from django.urls import reverse


@pytest.fixture
def client() -> Client:
    return Client()


def test_home_is_public_when_the_prototype_is_off(client: Client) -> None:
    with override_settings(INK_PROTOTYPE_ENABLED=False):
        response = client.get("/")
    assert response.status_code == 200
    assert "Try the notebook" not in response.content.decode()


def test_home_links_to_the_notebook_when_the_prototype_is_on(client: Client) -> None:
    with override_settings(INK_PROTOTYPE_ENABLED=True):
        response = client.get("/")
    assert f'href="{reverse("new_notebook")}"' in response.content.decode()


def test_home_says_planned_features_are_not_built(client: Client) -> None:
    html = client.get("/").content.decode()
    assert "Not yet open to families" in html
    assert "Reading and checking aren't built yet" in html
    assert "We don't collect children's data" in html


def test_home_refuses_writes(client: Client) -> None:
    assert client.post("/").status_code == 405


def test_home_names_the_company_and_contact(client: Client) -> None:
    html = client.get("/").content.decode()
    assert "Ola Technologies London Ltd" in html
    assert 'href="mailto:ola@olacompanion.com"' in html
