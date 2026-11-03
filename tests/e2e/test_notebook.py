"""The Milestone 0 demonstration in a real browser. Input is SIMULATED with a mouse pointer.

These tests prove the data path and the contract. They say nothing about writing comfort, palm
behaviour or real stylus latency, which need a physical device and real people.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

pytestmark = pytest.mark.django_db(transaction=True)

VIEW = {"width": 800, "height": 1200}


@pytest.fixture
def context(browser: Browser) -> Any:
    created = browser.new_context(viewport=VIEW, service_workers="block")
    yield created
    created.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    return context.new_page()


def open_notebook(page: Page, live_server: Any, notebook_id: str = "") -> str:
    path = f"/notebook/{notebook_id}/" if notebook_id else "/notebook/"
    page.goto(f"{live_server.url}{path}")
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    return page.url


def draw(page: Page, points: list[tuple[int, int]]) -> None:
    box = page.locator("#page").bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + points[0][0], box["y"] + points[0][1])
    page.mouse.down()
    for x, y in points[1:]:
        page.mouse.move(box["x"] + x, box["y"] + y)
    page.mouse.up()


def client_state(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const s = window.tutorInk.state;
            return {
                strokes: s.visible(),
                visible_hash: s.visibleHash(),
                full_hash: s.fullHash(),
                chain_hash: s.chainHash,
                undo: s.undo.length,
                redo: s.redo.length,
                ops: s.opIndex.size,
                page_id: s.pageId,
                width: s.width,
                height: s.height,
            };
        }"""
    )


def wait_synced(page: Page) -> None:
    expect(page.locator("#sync-status")).to_have_attribute("data-state", "synced")


def server_state(page: Page, live_server: Any, seq: int | None = None) -> dict[str, Any]:
    state = client_state(page)
    notebook = page.url.rstrip("/").rsplit("/", 1)[1]
    url = (
        f"{live_server.url}/api/ink/v1/notebooks/{notebook}/pages/{state['page_id']}"
        f"/reconstruction/"
    )
    if seq is not None:
        url += f"?seq={seq}"
    return page.request.get(url).json()


def test_write_erase_undo_redo_save_and_server_rebuilds_the_same_page(
    page: Page, live_server: Any
) -> None:
    open_notebook(page, live_server)

    draw(page, [(100, 100), (200, 120), (300, 100), (400, 130), (500, 100)])
    draw(page, [(100, 300), (200, 300), (300, 300)])
    draw(page, [(100, 500), (140, 540)])
    assert len(client_state(page)["strokes"]) == 3

    page.locator("#tool-eraser").click()
    draw(page, [(300, 60), (300, 160)])
    page.locator("#tool-pen").click()
    after_erase = client_state(page)
    assert len(after_erase["strokes"]) == 4, "the eraser must split the first stroke in two"

    page.locator("#undo").click()
    assert len(client_state(page)["strokes"]) == 3
    page.locator("#redo").click()
    assert client_state(page)["visible_hash"] == after_erase["visible_hash"]

    page.locator("#save").click()
    expect(page.locator("#compare-status")).to_have_attribute("data-state", "match")
    expect(page.locator("#revision")).to_have_text("1")

    client = client_state(page)
    server = server_state(page, live_server)
    assert server["strokes"] == client["strokes"]
    assert server["visible_hash"] == client["visible_hash"]
    assert server["full_hash"] == client["full_hash"]
    assert server["chain_hash"] == client["chain_hash"]

    image = page.locator("#server-render")
    expect(image).to_be_visible()
    loaded = image.evaluate("img => img.decode().then(() => img.naturalWidth)")
    assert loaded == 840


def test_reload_reproduces_the_page_from_persisted_data(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 200), (300, 100)])
    draw(page, [(100, 400), (300, 420)])
    wait_synced(page)
    before = client_state(page)

    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    after = client_state(page)
    assert after["strokes"] == before["strokes"]
    assert after["chain_hash"] == before["chain_hash"]
    assert after["undo"] == before["undo"]


def test_fresh_browser_restores_the_page_from_the_server(
    browser: Browser, page: Page, live_server: Any
) -> None:
    url = open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 200), (300, 100)])
    wait_synced(page)
    before = client_state(page)

    other = browser.new_context(viewport={"width": 500, "height": 800}, service_workers="block")
    other_page = other.new_page()
    other_page.goto(url)
    expect(other_page.locator("#page")).to_have_attribute("data-ready", "true")
    restored = client_state(other_page)
    other.close()
    assert restored["strokes"] == before["strokes"]
    assert restored["chain_hash"] == before["chain_hash"]


def test_writing_offline_then_reconnecting_syncs_without_duplicates(
    context: BrowserContext, page: Page, live_server: Any
) -> None:
    open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    wait_synced(page)

    context.set_offline(True)
    draw(page, [(100, 200), (200, 200)])
    draw(page, [(100, 300), (200, 300)])
    expect(page.locator("#sync-status")).to_have_attribute(
        "data-state", re.compile("offline|retrying")
    )
    assert len(client_state(page)["strokes"]) == 3

    context.set_offline(False)
    wait_synced(page)
    server = server_state(page, live_server)
    client = client_state(page)
    assert len(server["strokes"]) == 3
    assert server["chain_hash"] == client["chain_hash"]


def test_pending_work_survives_a_reload_and_syncs_once(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    wait_synced(page)

    page.route("**/pages/*/ops/", lambda route: route.abort())
    draw(page, [(100, 200), (200, 200)])
    expect(page.locator("#sync-status")).not_to_have_attribute("data-state", "synced")
    written = client_state(page)
    # Let the IndexedDB write finish; the op is committed before the first send is attempted.
    page.wait_for_function("window.tutorInk.sync.attempts > 0")

    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    assert client_state(page)["strokes"] == written["strokes"], "pending ink was lost on reload"

    page.unroute("**/pages/*/ops/")
    page.locator("#sync-retry").wait_for(state="attached")
    page.evaluate("window.tutorInk.sync.retryNow()")
    wait_synced(page)
    server = server_state(page, live_server)
    assert server["strokes"] == written["strokes"]
    assert server["chain_hash"] == client_state(page)["chain_hash"]


def test_lost_response_does_not_duplicate_ink(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    wait_synced(page)
    seen = {"dropped": False}

    def drop_first_response(route: Any) -> None:
        if seen["dropped"]:
            route.continue_()
            return
        seen["dropped"] = True
        route.fetch()  # The server receives and stores it...
        route.abort()  # ...but the browser never hears back.

    page.route("**/pages/*/ops/", drop_first_response)
    draw(page, [(100, 100), (200, 100)])
    expect(page.locator("#sync-status")).to_have_attribute("data-state", "synced", timeout=15000)
    assert seen["dropped"]
    assert len(server_state(page, live_server)["strokes"]) == 1
    assert server_state(page, live_server)["chain_hash"] == client_state(page)["chain_hash"]


def test_the_undo_button_stops_at_a_saved_revision(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    page.locator("#save").click()
    expect(page.locator("#compare-status")).to_have_attribute("data-state", "match")
    expect(page.locator("#undo")).to_be_disabled()

    draw(page, [(100, 300), (200, 300)])
    expect(page.locator("#undo")).to_be_enabled()
    page.locator("#undo").click()
    expect(page.locator("#undo")).to_be_disabled()
    wait_synced(page)
    assert len(client_state(page)["strokes"]) == 1


def test_a_cancelled_gesture_is_not_journaled(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    wait_synced(page)
    before = client_state(page)["ops"]
    page.evaluate(
        """() => {
            const canvas = document.getElementById("page");
            const rect = canvas.getBoundingClientRect();
            const init = {
                pointerId: 7, pointerType: "touch", isPrimary: true, bubbles: true,
                clientX: rect.left + 50, clientY: rect.top + 50, button: 0,
            };
            canvas.setPointerCapture = () => {};
            canvas.dispatchEvent(new PointerEvent("pointerdown", init));
            canvas.dispatchEvent(new PointerEvent("pointermove",
                {...init, clientX: rect.left + 90}));
            canvas.dispatchEvent(new PointerEvent("pointercancel", init));
        }"""
    )
    assert client_state(page)["ops"] == before
    assert client_state(page)["strokes"] == []


def test_touch_is_ignored_while_the_pen_is_in_use(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    page.evaluate(
        """() => {
            const canvas = document.getElementById("page");
            canvas.setPointerCapture = () => {};
            const rect = canvas.getBoundingClientRect();
            const at = (x, y, type, id) => ({
                pointerId: id, pointerType: type, isPrimary: true, bubbles: true, button: 0,
                clientX: rect.left + x, clientY: rect.top + y, pressure: 0.5,
            });
            canvas.dispatchEvent(new PointerEvent("pointerdown", at(50, 50, "pen", 1)));
            canvas.dispatchEvent(new PointerEvent("pointerdown", at(300, 300, "touch", 2)));
            canvas.dispatchEvent(new PointerEvent("pointermove", at(300, 320, "touch", 2)));
            canvas.dispatchEvent(new PointerEvent("pointerup", at(300, 320, "touch", 2)));
            canvas.dispatchEvent(new PointerEvent("pointermove", at(90, 60, "pen", 1)));
            canvas.dispatchEvent(new PointerEvent("pointerup", at(90, 60, "pen", 1)));
        }"""
    )
    strokes = client_state(page)["strokes"]
    assert len(strokes) == 1
    assert all(point[3] == 512 for point in strokes[0]["points"]), "a pen's pressure is stored"


def test_mouse_pressure_is_stored_as_null(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    assert all(point[3] is None for point in client_state(page)["strokes"][0]["points"])


@pytest.mark.parametrize("scale", [1, 2, 3])
def test_logical_coordinates_do_not_depend_on_device_pixel_ratio(
    browser: Browser, live_server: Any, scale: int
) -> None:
    context = browser.new_context(
        viewport={"width": 700, "height": 1000},
        device_scale_factor=scale,
        service_workers="block",
    )
    page = context.new_page()
    open_notebook(page, live_server)
    box = page.locator("#page").bounding_box()
    assert box is not None
    draw(page, [(int(box["width"]) // 2, 100), (int(box["width"]) // 2, 200)])
    points = client_state(page)["strokes"][0]["points"]
    context.close()
    assert abs(points[0][0] - 1050) <= 4, "the page's horizontal centre is logical x=1050"


def test_two_writers_conflict_is_shown_and_nothing_is_merged(
    browser: Browser, page: Page, live_server: Any
) -> None:
    url = open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    wait_synced(page)

    other = browser.new_context(viewport=VIEW, service_workers="block")
    other_page = other.new_page()
    other_page.goto(url)
    expect(other_page.locator("#page")).to_have_attribute("data-ready", "true")
    draw(other_page, [(100, 300), (200, 300)])
    wait_synced(other_page)
    winner = server_state(other_page, live_server)
    other.close()

    draw(page, [(100, 500), (200, 500)])
    expect(page.locator("#sync-status")).to_have_attribute("data-state", "conflict")
    assert len(client_state(page)["strokes"]) == 2, "the local writing stays on screen"
    assert server_state(page, live_server)["chain_hash"] == winner["chain_hash"]

    # After a reload the page shows the server's version; the local stroke is kept, not replayed.
    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    expect(page.locator("#sync-status")).to_have_attribute("data-state", "conflict")
    assert client_state(page)["chain_hash"] == winner["chain_hash"]
    kept = page.evaluate(
        """async () => {
            const app = window.tutorInk;
            const records = await app.store.load(app.notebookId);
            return records.filter((r) => !r.acked).length;
        }"""
    )
    assert kept == 1, "the conflicting stroke must survive in local storage"


def test_a_pin_survives_an_offline_reload(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    page.locator("#save").click()
    expect(page.locator("#compare-status")).to_have_attribute("data-state", "match")

    page.route("**/api/ink/**", lambda route: route.abort())
    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    assert len(client_state(page)["strokes"]) == 1
    expect(page.locator("#undo")).to_be_disabled()


def open_with_pages(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    page.locator("#page-orientation").select_option("portrait")


def test_several_pages_keep_separate_ink_and_survive_a_reload(page: Page, live_server: Any) -> None:
    open_with_pages(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    first = client_state(page)

    page.locator("#page-new").click()
    expect(page.locator("#page-label")).to_have_text("Page 2 of 2")
    assert client_state(page)["strokes"] == []
    draw(page, [(100, 300), (300, 300)])
    draw(page, [(100, 400), (300, 400)])
    second = client_state(page)
    assert len(second["strokes"]) == 2

    page.locator("#page-prev").click()
    assert client_state(page)["strokes"] == first["strokes"]
    page.locator("#undo").click()
    assert client_state(page)["strokes"] == []
    page.locator("#redo").click()
    wait_synced(page)

    page.locator("#page-next").click()
    assert client_state(page)["strokes"] == second["strokes"]
    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    expect(page.locator("#page-label")).to_have_text("Page 2 of 2")
    assert client_state(page)["chain_hash"] == second["chain_hash"]
    server = server_state(page, live_server)
    assert server["strokes"] == second["strokes"]
    assert server["chain_hash"] == second["chain_hash"]


def test_a_landscape_page_keeps_its_own_coordinates(page: Page, live_server: Any) -> None:
    open_with_pages(page, live_server)
    page.locator("#page-orientation").select_option("landscape")
    page.locator("#page-new").click()
    expect(page.locator("#page-label")).to_have_text("Page 2 of 2")
    box = page.locator("#page").bounding_box()
    assert box is not None
    assert box["width"] > box["height"]
    draw(page, [(int(box["width"]) // 2, 100), (int(box["width"]) // 2, 200)])
    state = client_state(page)
    assert (state["width"], state["height"]) == (2970, 2100)
    assert abs(state["strokes"][0]["points"][0][0] - 1485) <= 6
    wait_synced(page)
    assert server_state(page, live_server)["width"] == 2970


def test_deleting_a_page_needs_confirmation_and_keeps_evidence(
    page: Page, live_server: Any
) -> None:
    open_with_pages(page, live_server)
    expect(page.locator("#page-delete")).to_be_disabled()
    page.locator("#page-new").click()
    draw(page, [(100, 100), (200, 100)])
    deleted = client_state(page)

    page.locator("#page-delete").click()
    expect(page.locator("#delete-confirm")).to_be_visible()
    page.locator("#delete-no").click()
    expect(page.locator("#page-label")).to_have_text("Page 2 of 2")

    page.locator("#page-delete").click()
    page.locator("#delete-yes").click()
    expect(page.locator("#page-label")).to_have_text("Page 1 of 1")
    wait_synced(page)

    notebook = page.url.rstrip("/").rsplit("/", 1)[1]
    api = f"{live_server.url}/api/ink/v1/notebooks/{notebook}"
    state = page.request.get(f"{api}/").json()
    entry = next(p for p in state["pages"] if p["page_id"] == deleted["page_id"])
    assert entry["deleted"] is True
    kept = page.request.get(f"{api}/pages/{deleted['page_id']}/reconstruction/").json()
    assert kept["strokes"] == deleted["strokes"]

    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    expect(page.locator("#page-label")).to_have_text("Page 1 of 1")


def test_deleting_a_page_written_offline_saves_its_ink_first(
    context: BrowserContext, page: Page, live_server: Any
) -> None:
    open_with_pages(page, live_server)
    wait_synced(page)
    page.locator("#page-new").click()
    wait_synced(page)
    target = client_state(page)["page_id"]
    context.set_offline(True)
    draw(page, [(100, 100), (200, 100)])
    page.locator("#page-delete").click()
    page.locator("#delete-yes").click()
    context.set_offline(False)
    wait_synced(page)
    notebook = page.url.rstrip("/").rsplit("/", 1)[1]
    state = page.request.get(f"{live_server.url}/api/ink/v1/notebooks/{notebook}/").json()
    entry = next(p for p in state["pages"] if p["page_id"] == target)
    assert entry["deleted"] is True
    assert entry["head_seq"] == 1


def test_zoom_keeps_logical_coordinates_correct(page: Page, live_server: Any) -> None:
    open_with_pages(page, live_server)
    state = client_state(page)
    box = page.locator("#page").bounding_box()
    assert box is not None
    units_per_px = state["width"] / box["width"]
    draw(page, [(100, 100), (150, 100)])
    at_fit = client_state(page)["strokes"][0]["points"][0][0]
    assert abs(at_fit - 100 * units_per_px) <= 3

    page.locator("#zoom-in").click()
    page.locator("#zoom-in").click()
    expect(page.locator("#zoom-label")).to_have_text("200%")
    expect(page.locator("#zoom-in")).to_be_disabled()
    draw(page, [(100, 300), (150, 300)])
    zoomed = client_state(page)["strokes"][1]["points"][0][0]
    assert abs(zoomed - 100 * units_per_px / 2) <= 3, "same screen spot, half the logical distance"
    wait_synced(page)
    assert server_state(page, live_server)["chain_hash"] == client_state(page)["chain_hash"]


def test_writing_after_scrolling_lands_on_the_right_part_of_the_page(
    browser: Browser, live_server: Any
) -> None:
    context = browser.new_context(viewport={"width": 1024, "height": 600}, service_workers="block")
    page = context.new_page()
    open_notebook(page, live_server)
    page.locator("#page-orientation").select_option("portrait")
    page.locator("#page-new").click()
    page.locator("#tool-hand").click()
    box = page.locator("#page-viewport").bounding_box()
    assert box is not None
    start_y = box["y"] + box["height"] - 20
    page.mouse.move(box["x"] + 100, start_y)
    page.mouse.down()
    page.mouse.move(box["x"] + 100, box["y"] + 20, steps=5)
    page.mouse.up()
    scrolled = page.evaluate("document.getElementById('page-viewport').scrollTop")
    assert scrolled > 50, "the Move page tool must scroll"
    assert client_state(page)["strokes"] == [], "moving the page must not leave ink"

    page.locator("#tool-pen").click()
    canvas = page.locator("#page").bounding_box()
    assert canvas is not None
    y_on_screen = box["y"] + 40
    page.mouse.move(box["x"] + 100, y_on_screen)
    page.mouse.down()
    page.mouse.move(box["x"] + 160, y_on_screen)
    page.mouse.up()
    state = client_state(page)
    expected = (y_on_screen - canvas["y"]) * state["width"] / canvas["width"]
    context.close()
    assert abs(state["strokes"][0]["points"][0][1] - expected) <= 3


def make_conflict(browser: Browser, page: Page, live_server: Any) -> dict[str, Any]:
    url = open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    wait_synced(page)
    other = browser.new_context(viewport=VIEW, service_workers="block")
    other_page = other.new_page()
    other_page.goto(url)
    expect(other_page.locator("#page")).to_have_attribute("data-ready", "true")
    draw(other_page, [(100, 300), (200, 300)])
    wait_synced(other_page)
    winner = server_state(other_page, live_server)
    other.close()
    draw(page, [(100, 500), (200, 500)])
    expect(page.locator("#conflict")).to_be_visible()
    return winner


def test_keep_my_version_as_a_new_page_loses_nothing(
    browser: Browser, page: Page, live_server: Any
) -> None:
    winner = make_conflict(browser, page, live_server)
    mine = client_state(page)["strokes"]
    assert len(mine) == 2

    with page.expect_navigation():
        page.locator("#conflict-copy").click()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    wait_synced(page)
    expect(page.locator("#conflict")).to_be_hidden()
    expect(page.locator("#page-label")).to_have_text("Page 1 of 2")
    assert client_state(page)["chain_hash"] == winner["chain_hash"]

    page.locator("#page-next").click()
    copied = client_state(page)["strokes"]
    assert [[p[:2] for p in s["points"]] for s in copied] == [
        [p[:2] for p in s["points"]] for s in mine
    ]
    assert server_state(page, live_server)["strokes"] == copied


def test_use_the_other_version_clears_the_conflict(
    browser: Browser, page: Page, live_server: Any
) -> None:
    winner = make_conflict(browser, page, live_server)
    with page.expect_navigation():
        page.locator("#conflict-discard").click()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    wait_synced(page)
    expect(page.locator("#conflict")).to_be_hidden()
    assert client_state(page)["chain_hash"] == winner["chain_hash"]
    kept = page.evaluate(
        """async () => {
            const app = window.tutorInk;
            const records = await app.store.load(app.notebookId);
            return records.filter((r) => r.sidelined).length;
        }"""
    )
    assert kept == 1, "set-aside work stays on the device"
    draw(page, [(100, 700), (200, 700)])
    wait_synced(page)
    assert client_state(page)["chain_hash"] == server_state(page, live_server)["chain_hash"]


def test_a_visited_notebook_reopens_with_no_network(browser: Browser, live_server: Any) -> None:
    context = browser.new_context(viewport=VIEW)
    page = context.new_page()
    open_notebook(page, live_server)
    draw(page, [(100, 100), (200, 100)])
    wait_synced(page)
    page.evaluate("navigator.serviceWorker.ready")
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    page.wait_for_timeout(300)
    before = client_state(page)

    context.set_offline(True)
    page.reload()
    expect(page.locator("#page")).to_have_attribute("data-ready", "true")
    assert client_state(page)["strokes"] == before["strokes"]
    draw(page, [(100, 300), (200, 300)])
    expect(page.locator("#sync-status")).to_have_attribute(
        "data-state", re.compile("offline|retrying")
    )

    context.set_offline(False)
    page.evaluate("window.tutorInk.sync.retryNow()")
    wait_synced(page)
    assert server_state(page, live_server)["chain_hash"] == client_state(page)["chain_hash"]
    context.close()


def test_the_first_page_and_the_new_page_default_suit_the_screen(
    browser: Browser, live_server: Any
) -> None:
    context = browser.new_context(viewport={"width": 1024, "height": 600}, service_workers="block")
    page = context.new_page()
    open_notebook(page, live_server)
    assert client_state(page)["width"] == 2970
    expect(page.locator("#page-orientation")).to_have_value("landscape")
    context.close()


def test_saving_immediately_after_a_stroke_includes_that_stroke(
    page: Page, live_server: Any
) -> None:
    open_notebook(page, live_server)
    wait_synced(page)
    draw(page, [(100, 100), (200, 100)])
    page.locator("#save").click()
    expect(page.locator("#compare-status")).to_have_attribute("data-state", "match")
    assert len(server_state(page, live_server)["strokes"]) == 1


def test_all_saved_is_never_shown_while_a_stroke_is_unsaved(page: Page, live_server: Any) -> None:
    open_notebook(page, live_server)
    wait_synced(page)
    state = page.evaluate(
        """() => {
            const app = window.tutorInk;
            const journal = app.activePage.journal;
            app.sync.beginCommit(journal);
            const shown = document.getElementById("sync-status").dataset.state;
            journal.committing -= 1;
            return shown;
        }"""
    )
    assert state != "synced"
