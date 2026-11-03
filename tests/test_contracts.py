"""The contract fixtures must validate independently of the application code."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_path = Path(__file__).resolve().parents[1] / "scripts" / "validate_contracts.py"
_spec = importlib.util.spec_from_file_location("validate_contracts", _path)
assert _spec is not None and _spec.loader is not None
validate_contracts = importlib.util.module_from_spec(_spec)
sys.modules["validate_contracts"] = validate_contracts
_spec.loader.exec_module(validate_contracts)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def test_all_contract_fixtures_validate(capsys: pytest.CaptureFixture[str]) -> None:
    assert validate_contracts.main() == 0, capsys.readouterr().out


def load(relative: str) -> Any:
    return json.loads((CONTRACTS / relative).read_text("utf-8"))


def test_the_two_status_axes_stay_independent_in_the_fraction_contract() -> None:
    examples = load("grading/v1/fixtures/contract_simplify_fraction.json")["examples"]
    unsimplified = next(example for example in examples if example["answer"] == "2/4")
    assert unsimplified["mathematical_status"] == "CORRECT"
    assert unsimplified["task_compliance"] == "NON_COMPLIANT"


def test_one_root_is_not_the_complete_solution_set() -> None:
    examples = load("grading/v1/fixtures/contract_quadratic_roots.json")["examples"]
    one_root = next(example for example in examples if example["answer"] == "x = 3")
    assert one_root["mathematical_status"] == "INCOMPLETE"


def test_rational_contract_keeps_the_excluded_value() -> None:
    contract = load("grading/v1/fixtures/contract_rational_domain.json")
    assert contract["variable_domains"]["x"]["excluded"] == ["1"]


def test_ambiguous_graph_does_not_invent_certainty() -> None:
    graph = load("page_semantics/v1/fixtures/valid_ambiguous_crossed_out.json")
    group = graph["hypothesis_groups"][0]
    assert group["resolved"] is False
    assert group["unresolved_mass"] > 0
