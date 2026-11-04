# Milestone 4A support matrix

What the arithmetic engine actually does. **This is not KS2 coverage:** it is a small core chosen from KS2 arithmetic, and no curriculum review has been done. Grammar: `apps/grading/engine/parser.py`.

## Features

| Feature | Accepted syntax | Limits | Not supported, and the result | Tests |
|---|---|---|---|---|
| Integers | `7`, `007` | 18 digits | Thousands comma `1,000`: UNDETERMINED | `test_math_parser` |
| + − × ÷ | `+`, `-`, `−`, `–`, `×`, `*`, `÷` | 64 operations per expression | `:`, `^`, `%`, `√`, `²`: UNSUPPORTED. `3 x 4`: UNDETERMINED, asks | `test_math_parser`, `test_math_properties` |
| Brackets and order of operations | `(3 + 4) × 2` | Depth 24 | Implied multiplication `2(3)`: UNDETERMINED | `test_math_parser`, `test_math_steps` |
| Fractions | `2/4`, `½`, `⁄`, `∕` | 18 digits per part | `1/2/3`, `6÷2/3`, `3/4 ÷ 2/5`: UNDETERMINED; brackets settle them | `test_math_parser`, `test_math_properties` |
| Equivalence and simplification | Value compared exactly; form judged from what was written | As above | Fraction operations in words: UNSUPPORTED | `test_math_contract_fixtures`, `test_math_steps` |
| Fraction operations | `1/2 + 1/3`, `3/4 × 8`, `3/4 ÷ (2/5)` | 2048 bits per numerator or denominator | | `test_math_parser`, `test_math_steps` |
| Finite decimals | `1.25`, `1.50` (places kept) | 18 digits | `.5`, `5.`, `1.2.3`, `1,5`, `1·5`: UNDETERMINED | `test_math_parser` |
| Rounding | `half_up`, ties away from zero; `≈` or `=` in a rounding exercise | Up to 6 places | Other modes refused at load. `≈` elsewhere: UNSUPPORTED | `test_math_parser`, `test_math_properties`, `test_math_steps` |
| Mixed numbers | `1 1/2`, `1½`, `-1 1/2` = −3/2 | Fraction part below 1 | `1 3/2`: UNDETERMINED. `1 2/3/4`: UNDETERMINED | `test_math_parser` |
| Unary signs | One sign per number: `-3`, `3 - -2` | Counts as an operation | `--2`: UNDETERMINED. Parsing need only, not extra curriculum coverage | `test_math_parser` |
| Division by zero | `1/0`, `3 ÷ 0`, `5 ÷ (2 - 2)` | | INCORRECT, `DOMAIN_VIOLATION`, score 0: it is certain, not uncertain | `test_math_steps` |
| Step chains | `a = b = c`, one line per step, leading `= c` | 30 lines, 8 expressions per line, 512 operations per check | Text between steps: UNSUPPORTED | `test_math_steps` |
| Alternative methods | Any chain of equal values (`any_valid_chain`) | As above | `listed_only` refused at load | `test_math_steps`, e2e |
| Partial marks | Four allowlisted rules in `scoring.py`, each declared per exercise | Below the maximum | Any other `when` refused at load | `test_math_steps` |
| Required form | `any`, `integer`, `lowest_terms`, `mixed_number`, `decimal_places` | | `collected`, `expanded`, `complete_solution_set` refused at load | `test_math_parser`, `test_math_steps` |

## Unicode

Normalisation is an explicit table, not NFKC, which would turn `1½` into `11⁄2`. Listed: `−`, `–`, `*`, `⁄`, `∕`, no-break space, tab and the 15 common vulgar fractions. Spaces collapse. Anything else, such as full-width or Arabic-Indic digits and zero-width or control characters, is UNSUPPORTED. `½3` is UNDETERMINED, because it must not become `1/23`.

## Outside this stage

Algebra and variables, equations, proofs, unit conversions and units in answers, word problems, percentages, powers and roots, ratios, recurring decimals, negative-number teaching, spatial anchoring and recognition. Each of these returns UNSUPPORTED or is refused at load. None is marked wrong.

## Existing grading fixtures

The fixtures are unchanged, and all still validate as contracts.

| Fixture | In 4A | Outside 4A |
|---|---|---|
| `contract_simplify_fraction` | All 5 examples pass | |
| `contract_rounding_units` | `2.33`, `2.3` pass, with the unit rule removed in the test only | `2.33 cm`, `2.33 m`, `23.3 mm`: the engine returns UNSUPPORTED, while the fixture expects CORRECT, INCORRECT and UNSUPPORTED. They stay as future acceptance cases. The contract as written is refused because it declares units |
| `contract_quadratic_roots` | | Contract refused at load. Answers are UNSUPPORTED, never wrong |
| `contract_rational_domain` | | Contract refused at load. Answers are UNSUPPORTED, never wrong |
| `result_review_required`, `invalid_results` | Validated, and the same rules are enforced on engine results | |

## Result mapping for operational limits

| Situation | HTTP | Result |
|---|---|---|
| Any engine limit in `limits.py` | 201, stored | UNDETERMINED, `RESOURCE_LIMIT_EXCEEDED`, no score, review required, `limit_exceeded` names the limit |
| Body over 64 KB | 413 `BODY_TOO_LARGE`, not stored | No result |
| Broken request or JSON | 400 | No result |
| U+0000 or lone surrogate in a step | 400 `INVALID_TRANSCRIPTION` | No result |

Latency measured for this budget is in `PROGRESS.md`. See ADR 0005 for why no subprocess is used.
