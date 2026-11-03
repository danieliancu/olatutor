"""Property tests over randomly generated journals (spec section 12)."""

import importlib.util
import sys
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.notebooks.ink.encoding import encode
from apps.notebooks.ink.replay import PageState, replay_page

_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_ink_fixtures.py"
_spec = importlib.util.spec_from_file_location("generate_ink_fixtures", _path)
assert _spec is not None and _spec.loader is not None
generator = importlib.util.module_from_spec(_spec)
sys.modules["generate_ink_fixtures"] = generator
_spec.loader.exec_module(generator)

Ops = generator.Ops
random_sequence = generator.random_sequence

SEEDS = st.integers(min_value=0, max_value=2**31)
FAST = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def replay(ops: list[dict[str, Any]]) -> PageState:
    return replay_page("page-1", 2100, 2970, ops)


def fingerprint(state: PageState) -> tuple[str, str, str]:
    return state.visible_hash(), state.full_hash(), state.chain_hash


@FAST
@given(seed=SEEDS, length=st.integers(1, 60), fraction=st.floats(0, 1))
def test_snapshot_at_any_point_equals_replay_from_zero(
    seed: int, length: int, fraction: float
) -> None:
    ops = random_sequence(seed, length)
    cut = int(fraction * length)
    resumed = replay(ops[:cut]).to_snapshot()
    state = PageState.from_snapshot(resumed)
    for op in ops[cut:]:
        state.apply(op)
    assert fingerprint(state) == fingerprint(replay(ops))


@FAST
@given(seed=SEEDS, length=st.integers(1, 60))
def test_undo_n_redo_n_is_identity_for_visible_ink(seed: int, length: int) -> None:
    ops = random_sequence(seed, length)
    state = replay(ops)
    before = state.visible_hash(), list(state.undo)
    builder = Ops()
    builder.seq = 100_000

    undone = 0
    while state.undo:
        state.apply(builder.undo(state.undo[-1]))
        undone += 1
    assert state.visible() == []
    for _ in range(undone):
        state.apply(builder.redo(state.redo[-1]))
    assert (state.visible_hash(), state.undo) == before


@FAST
@given(seed=SEEDS, length=st.integers(1, 60))
def test_snapshot_survives_json_round_trip(seed: int, length: int) -> None:
    import json

    state = replay(random_sequence(seed, length))
    restored = PageState.from_snapshot(json.loads(json.dumps(state.to_snapshot())))
    assert fingerprint(restored) == fingerprint(state)


@FAST
@given(seed=SEEDS, length=st.integers(1, 40))
def test_visible_ranges_stay_inside_their_root(seed: int, length: int) -> None:
    state = replay(random_sequence(seed, length))
    for node in state.nodes.values():
        assert 0 <= node.start <= node.end < len(state.roots[node.root_id]["points"])


@given(
    st.recursive(
        st.none() | st.booleans() | st.integers(-(2**53) + 1, 2**53 - 1) | st.text(max_size=8),
        lambda children: (
            st.lists(children, max_size=4)
            | st.dictionaries(st.text("abcXYZ_", max_size=4), children, max_size=4)
        ),
        max_leaves=20,
    )
)
def test_encoding_does_not_depend_on_map_insertion_order(value: Any) -> None:
    def shuffled(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: shuffled(item[key]) for key in reversed(list(item))}
        if isinstance(item, list):
            return [shuffled(entry) for entry in item]
        return item

    assert encode(shuffled(value)) == encode(value)
