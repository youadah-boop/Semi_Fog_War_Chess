# Contributing to Semi Fog War Chess

Thank you for your interest in contributing! Here is everything you need to get started.

## Code conventions

### Language

- **Docstrings and inline comments** are written in **French** (the author's working language).
- **Identifiers** (variable names, function names, class names) may be in French or English; be consistent within a module.
- **Git commit messages** can be in French or English.

### Style

- Follow PEP 8. Line length ≤ 100 characters.
- Type hints on all public functions and method signatures.
- No bare `except:` — always catch a specific exception class.

---

## Architecture rules — non-negotiable

These constraints protect the fog-of-war integrity and must never be broken:

| Rule | Why |
|------|-----|
| `arbiter.py` is the **sole holder of the real board** (`self._board`). It must never expose it directly to any other module. | Any leak would break the fog-of-war discipline. |
| `sampler.py` and `ai/ai_opponent.py` must **never import from `arbiter.py`**. They only consume `belief_state` dicts produced by `vision.py`. | Separates what is known from what is real. |
| An **illegal move is substituted immediately** by a random legal move — no second attempt, no error message that leaks information. | Rule of war. |
| Temporary revelations (check, king-adjacency, pin) are **recomputed from scratch every turn** — nothing persists. | Defined in the variant rules. |
| The **fog zone** is defined solely in `engine/vision.py` (`RANGEES_BROUILLARD`). All other modules import it from there — no hardcoded rank tuples anywhere else. | Single source of truth for future variant changes. |

---

## Adding a new fog variant

The fog zone width is a single constant:

```python
# engine/vision.py
RANGEES_BROUILLARD = (2, 3, 4, 5)   # ranks 3–6 (0-indexed)
```

Change it and all downstream logic (sampler, GUI zone colouring, tests) adapts automatically — provided the tests that assert zone membership use `RANGEES_BROUILLARD` rather than hardcoded tuples (which they do).

---

## Testing

- Maintain **100 % coverage** for `engine/` and `ai/`.
- Every new rule or guard must have at least one dedicated test.
- Tests that assert fog-zone membership must import `RANGEES_BROUILLARD` from `engine.vision`, not hardcode `(2, 3, 4, 5)`.
- Stockfish is mocked in tests — never require a real binary to run the test suite.

```bash
pytest -q          # quick run
pytest -v          # verbose output
pytest tests/test_vision.py   # single file
```

---

## Pull request checklist

- [ ] All 22 existing tests pass.
- [ ] New behaviour is covered by new tests.
- [ ] No real board exposed outside `arbiter.py`.
- [ ] No hardcoded rank tuples outside `engine/vision.py`.
- [ ] `RANGEES_BROUILLARD` imported where needed (not duplicated).
- [ ] Docstrings updated if the public API changed.
- [ ] `CONTRIBUTING.md` updated if a new convention was introduced.

---

## Reporting bugs

Open an issue with:

1. Your OS and Python version (`python --version`).
2. The exact command you ran.
3. The full traceback (copy-paste from the terminal).
4. If the bug is visual (GUI), a screenshot or a description of the board state.
