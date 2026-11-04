"""The manual demonstration in a real browser. Input is simulated, and typed steps are synthetic.

These prove the flow and its protections. They say nothing about recognition, because none exists.
"""

from typing import Any

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from apps.grading.models import Verification

from .test_notebook import client_state, draw, open_notebook, wait_synced

pytestmark = pytest.mark.django_db(transaction=True)

VIEW = {"width": 800, "height": 1200}
SIMPLIFY = "ks2.fraction.simplify-2-4"
TIMES = "ks2.multiply.two-digit"
LINE = [(100, 100), (200, 120), (300, 100)]


@pytest.fixture
def context(browser: Browser) -> Any:
    created = browser.new_context(viewport=VIEW, service_workers="block")
    yield created
    created.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    return context.new_page()


def ready(page: Page, live_server: Any, exercise: str = SIMPLIFY) -> None:
    open_notebook(page, live_server)
    expect(page.locator("#verify")).to_be_enabled()
    page.select_option("#verify-exercise", exercise)


def pin_and_type(page: Page, text: str) -> None:
    draw(page, LINE)
    wait_synced(page)
    page.locator("#verify").click()
    expect(page.locator("#verify-status")).to_have_attribute("data-state", "pinned")
    page.locator("#verify-steps").fill(text)


def check(page: Page) -> None:
    page.locator("#verify-confirm").click()
    expect(page.locator("#verify-status")).to_have_attribute("data-state", "done")


def test_the_demo_is_clearly_labelled_as_manual(page: Page, live_server: Any) -> None:
    ready(page, live_server)
    expect(page.locator("#math-demo-label")).to_contain_text(
        "manual transcription, not handwriting recognition"
    )
    expect(page.locator("#verify-statement")).to_have_text("Simplify 2/4.")


def test_simplify_two_quarters_shows_right_value_wrong_form(page: Page, live_server: Any) -> None:
    ready(page, live_server)
    pin_and_type(page, "2/4")
    check(page)

    result = page.locator("#verify-result")
    expect(result).to_have_attribute("data-status", "CORRECT")
    expect(result).to_have_attribute("data-compliance", "NON_COMPLIANT")
    expect(page.locator("#verify-score")).to_have_text("Mark: 1 out of 2.")
    expect(page.locator("#verify-problem")).to_contain_text("not in its simplest form")
    expect(page.locator("#verify-explanation")).to_be_hidden()
    assert "1/2" not in result.inner_text(), "the answer must not be shown"

    page.locator("#verify-explain").click()
    expect(page.locator("#verify-explanation")).to_be_visible()
    expect(page.locator("#verify-explanation")).to_contain_text("simplest form")

    record = Verification.objects.get()
    assert record.revision.visible_hash == client_state(page)["visible_hash"]
    assert record.transcription.provenance == "manual_entry"


def test_verifying_pins_the_revision_with_server_checked_hashes(
    page: Page, live_server: Any
) -> None:
    ready(page, live_server)
    pin_and_type(page, "1/2")
    state = client_state(page)
    expect(page.locator("#verify-status")).to_contain_text("Revision 1")
    check(page)
    record = Verification.objects.get()
    assert record.revision.seq == state["ops"]
    assert record.revision.chain_hash == state["chain_hash"]
    expect(page.locator("#verify-result")).to_have_attribute("data-status", "CORRECT")


def test_two_different_methods_both_pass(page: Page, live_server: Any) -> None:
    ready(page, live_server, TIMES)
    pin_and_type(page, "12 × 10 + 12 × 5\n120 + 60\n180")
    check(page)
    expect(page.locator("#verify-score")).to_have_text("Mark: 3 out of 3.")
    expect(page.locator("#verify-step-list li")).to_have_count(3)

    page.locator("#verify-steps").fill("15 × 12 = 15 × 10 + 15 × 2\n= 150 + 30 = 180")
    check(page)
    expect(page.locator("#verify-score")).to_have_text("Mark: 3 out of 3.")
    assert Verification.objects.count() == 2


def test_a_wrong_step_is_found_at_its_line_without_giving_the_solution(
    page: Page, live_server: Any
) -> None:
    ready(page, live_server, TIMES)
    pin_and_type(page, "12 × 10 + 12 × 5\n120 + 50\n170")
    check(page)
    expect(page.locator("#verify-result")).to_have_attribute("data-status", "INCORRECT")
    expect(page.locator("#verify-problem")).to_contain_text("Line 2")
    expect(page.locator("#verify-step-list li").nth(1)).to_have_attribute(
        "data-status", "INCORRECT"
    )
    assert "180" not in page.locator("#verify-result").inner_text()


@pytest.mark.parametrize(
    ("typed", "status", "hint"),
    [
        ("1/2/3", "UNDETERMINED", "brackets"),
        ("half", "UNSUPPORTED", "word, letter or symbol"),
    ],
)
def test_unclear_input_asks_for_correction_and_gives_no_mark(
    page: Page, live_server: Any, typed: str, status: str, hint: str
) -> None:
    ready(page, live_server)
    pin_and_type(page, typed)
    check(page)
    expect(page.locator("#verify-result")).to_have_attribute("data-status", status)
    expect(page.locator("#verify-score")).to_have_text("No mark given.")
    expect(page.locator("#verify-hint")).to_contain_text(hint)

    page.locator("#verify-steps").fill("1/2")
    check(page)
    expect(page.locator("#verify-result")).to_have_attribute("data-status", "CORRECT")
    first, second = Verification.objects.order_by("pk")
    assert second.corrects_id == first.pk, "a correction keeps the original, and links back to it"
    assert first.transcription.steps == [typed]


def test_double_click_makes_one_record(page: Page, live_server: Any) -> None:
    ready(page, live_server)
    pin_and_type(page, "1/2")
    page.locator("#verify-confirm").dblclick()
    expect(page.locator("#verify-status")).to_have_attribute("data-state", "done")
    page.locator("#verify-confirm").click()
    expect(page.locator("#verify-status")).to_have_attribute("data-state", "done")
    assert Verification.objects.count() == 1


def test_a_lost_response_retries_with_the_same_key_and_one_record(
    page: Page, live_server: Any
) -> None:
    ready(page, live_server)
    pin_and_type(page, "1/2")
    keys: list[str] = []

    def lose_once(route: Route) -> None:
        if route.request.method != "POST":
            route.continue_()
            return
        keys.append(route.request.post_data_json["idempotency_key"])
        if len(keys) == 1:
            # The server does the work, and the answer never arrives.
            route.fetch()
            route.abort()
        else:
            route.continue_()

    page.route("**/api/grading/v1/**/verifications/", lose_once)
    page.locator("#verify-confirm").click()
    expect(page.locator("#verify-retry")).to_be_visible()
    assert Verification.objects.count() == 1

    page.locator("#verify-retry").click()
    expect(page.locator("#verify-status")).to_have_attribute("data-state", "done")
    expect(page.locator("#verify-result")).to_have_attribute("data-status", "CORRECT")
    assert keys[0] == keys[1]
    assert Verification.objects.count() == 1


def test_editing_after_the_result_never_shows_it_as_the_current_verdict(
    page: Page, live_server: Any
) -> None:
    ready(page, live_server)
    pin_and_type(page, "1/2")
    check(page)
    expect(page.locator("#verify-stale")).to_be_hidden()
    expect(page.locator("#verify-result")).to_have_attribute("data-current", "true")

    draw(page, [(100, 300), (200, 300)])
    expect(page.locator("#verify-result")).to_have_attribute("data-current", "false")
    expect(page.locator("#verify-stale")).to_have_text(
        "This result is for revision 1. The page has changed since."
    )

    page.locator("#verify-history-box summary").click()
    expect(page.locator("#verify-history li")).to_have_count(1)
    expect(page.locator("#verify-history li")).to_contain_text("Revision 1")

    wait_synced(page)
    page.locator("#verify").click()
    expect(page.locator("#verify-status")).to_contain_text("Revision 2")
    expect(page.locator("#verify-result")).to_be_hidden()


def test_writing_during_the_check_keeps_the_result_on_the_pinned_revision(
    page: Page, live_server: Any
) -> None:
    ready(page, live_server)
    pin_and_type(page, "1/2")
    pinned_ops = client_state(page)["ops"]
    draw(page, [(100, 300), (200, 300)])
    check(page)
    expect(page.locator("#verify-result")).to_have_attribute("data-current", "false")
    assert Verification.objects.get().revision.seq == pinned_ops


def test_an_empty_page_cannot_be_verified(page: Page, live_server: Any) -> None:
    ready(page, live_server)
    page.locator("#verify").click()
    expect(page.locator("#verify-status")).to_have_attribute("data-state", "error")
    expect(page.locator("#verify-status")).to_contain_text("Write your work")
    expect(page.locator("#verify-work")).to_be_hidden()


def test_offline_keeps_the_writing_and_pins_nothing(
    page: Page, context: BrowserContext, live_server: Any
) -> None:
    ready(page, live_server)
    draw(page, LINE)
    wait_synced(page)
    context.set_offline(True)
    draw(page, [(100, 300), (200, 300)])
    page.locator("#verify").click()
    expect(page.locator("#verify-status")).to_have_attribute("data-state", "error")
    assert len(client_state(page)["strokes"]) == 2
    context.set_offline(False)
    wait_synced(page)
    page.locator("#verify").click()
    expect(page.locator("#verify-status")).to_have_attribute("data-state", "pinned")


def test_typed_markup_stays_text(page: Page, live_server: Any) -> None:
    ready(page, live_server)
    pin_and_type(page, "<img src=x onerror=window.pwned=1>")
    check(page)
    expect(page.locator("#verify-result")).to_have_attribute("data-status", "UNSUPPORTED")
    expect(page.locator("#verify-step-list img")).to_have_count(0)
    assert page.evaluate("window.pwned") is None


def test_changing_page_takes_the_steps_and_result_away(page: Page, live_server: Any) -> None:
    ready(page, live_server)
    pin_and_type(page, "1/2")
    check(page)
    page.locator("#page-new").click()
    expect(page.locator("#page-label")).to_have_text("Page 2 of 2")
    expect(page.locator("#verify-result")).to_be_hidden()
    expect(page.locator("#verify-work")).to_be_hidden()


def test_verify_does_not_disturb_sync_or_saving(page: Page, live_server: Any) -> None:
    ready(page, live_server)
    pin_and_type(page, "1/2")
    check(page)
    draw(page, [(100, 300), (200, 300)])
    wait_synced(page)
    page.locator("#save").click()
    expect(page.locator("#compare-status")).to_have_attribute("data-state", "match")
    expect(page.locator("#revision")).to_have_text("2")
    assert len(client_state(page)["strokes"]) == 2
    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    assert len(client_state(page)["strokes"]) == 2


@pytest.mark.parametrize("size", [(800, 1200), (1024, 600), (1280, 800)])
def test_the_demo_panel_leaves_the_writing_surface_on_screen(
    page: Page, live_server: Any, size: tuple[int, int]
) -> None:
    page.set_viewport_size({"width": size[0], "height": size[1]})
    ready(page, live_server)
    box = page.locator("#page-viewport").bounding_box()
    assert box is not None
    assert box["height"] >= 280
    assert box["y"] + box["height"] <= size[1], "the bottom of the page must stay reachable"
