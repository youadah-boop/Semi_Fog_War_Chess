# ♟ Semi Fog War Chess

> *Chess under the fog — only the centre is hidden.*

**Semi Fog War Chess** is an original chess variant where a **fog-of-war zone covers ranks 3 through 6** (32 squares). Pieces outside that band are always visible; inside it, an enemy piece stays hidden unless directly attacked, giving check, controlling a square next to your king, or pinning one of your pieces.

The game is played **Human (White) vs Stockfish (Black)**, with a Python/Pygame graphical interface, a full referee engine, and a Gibbs-Sampling state estimator that builds a plausible board from what White can legally know.

---

## Table of Contents

- [Rules](#rules)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Installation](#installation)
- [Running the game](#running-the-game)
- [Sampler algorithm](#sampler-algorithm)
- [Running the tests](#running-the-tests)
- [Project structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Rules

Semi Fog War Chess follows standard chess rules (legal moves, check, checkmate, stalemate, 50-move rule, threefold repetition) with the following additions:

### Fog zone

| Ranks | Squares | Status |
|-------|---------|--------|
| 1 – 2 | 16 | **Always visible** (White's starting area) |
| **3 – 6** | **32** | **Fog of war** — enemy pieces hidden unless revealed |
| 7 – 8 | 16 | **Always visible** (Black's starting area) |

### Vision (Dark Chess 1989 rule)

Each side sees:
- All of its own pieces, regardless of location.
- Every square (empty or enemy-occupied) that any of its pieces can move to or capture on — including diagonal pawn captures and a pinned piece's geometric ray.

### Temporary revelation

An enemy piece hidden inside the fog zone is **temporarily revealed** if, on the current turn, it:

1. **Gives check** — attacks your king directly.
2. **Controls a king-adjacent square** — attacks a square next to your king that is either empty (denying your king an escape) or occupied by an enemy piece your king cannot capture.
3. **Pins one of your pieces** — stands on the ray between one of your pieces and your king.

*Temporary* means no memory between turns: every condition is recomputed from scratch each turn. A piece that no longer satisfies any condition vanishes back into the fog.

### Referee

The **Referee** is the sole holder of the real board. It never exposes it to either player, the Sampler, or the display. Every move submitted — human or AI — is validated by the Referee. An **illegal move is immediately replaced by a random legal move** (rule of war — no second attempt, no explanation).

### Promotion

When a White pawn reaches rank 8, a modal menu appears for the human player to choose: **queen, rook, bishop, or knight**.

---

## Screenshots

> *Add your own screenshots here once the GUI is running.*

```
 Plateau visible (Blancs)          Plateau plausible (Sampler)
 ┌──────────────────────┐          ┌───────────────┐
 │  . . . . . . . .     │          │  r . b q . . n r │
 │  p p p p . p p p     │          │  p p . p . p p p │
 │ [x x x x x x x x]   │          │ [x x x x x x x x]│  ← fog (green)
 │ [x . . . x x x x]   │          │ [x . . . p x x x]│
 │ [x x x x P x x x]   │          │ [x x x x P x x x]│
 │ [x x x x x x x x]   │          │ [x x x x x x x x]│
 │  P P P P . P P P     │          │  P P P P . P P P │
 │  R N B Q K B N R     │          │  R N B Q K B N R │
 └──────────────────────┘          └───────────────────┘
   Green cells = fog zone (ranks 3–6). 
```

---

## Architecture

```
semi_fog_chess/
│
├── engine/
│   ├── arbiter.py     ← The sole holder of the real board
│   ├── vision.py      ← Fog rules & belief-state computation
│   ├── sampler.py     ← Gibbs Sampling + history filters
│   ├── partie.py      ← High-level orchestrator
│   └── rendu.py       ← Symbol grids shared by gui.py and cli.py
│
├── ai/
│   └── ai_opponent.py ← Stockfish wrapper (plays on hypothetical board)
│
├── tests/
│   ├── test_vision.py
│   ├── test_sampler.py
│   ├── test_arbiter.py
│   └── test_ai_opponent.py
│
├── gui.py             ← Pygame graphical interface
├── cli.py             ← Text-mode interface (debug / headless)
└── requirements.txt
```

### Data flow (one White turn)

```
Human click / text input
        │
        ▼
   gui.py  ──────────────────────────────────────────┐
        │  uci string                                 │
        ▼                                             │
  arbiter.py  (validates; substitutes random          │
   [REAL BOARD]  legal move if illegal)               │
        │  ResultatCoup (no real board leaked)        │
        ▼                                             │
  vision.py   (recomputes belief-state from           │
   real board; returns only what White may know)      │
        │  belief_state (White's view only)           │
        ▼                                             │
  sampler.py  (Gibbs sampling → N plausible boards)  │
        │  boards[]                                   │
        ▼                                             │
   gui.py  ◄──────────────────────────────────────────┘
   (draws fogged board + most-plausible hypothetical board)
```
(Sampler algorithm, see below)
---
### Black's turn (Stockfish)

```
  vision.py  →  belief_state (Black's view)
       │
       ▼
  sampler.py  →  boards[0]  (most plausible)
       │
       ▼
  ai_opponent.py  →  Stockfish plays on boards[0]
       │  uci string (may be illegal on real board)
       ▼
  arbiter.py  (validates / substitutes)
       │
       ▼
  vision.py  (update — no move leaked to display)
```

---

## Installation

### Prerequisites

- Python 3.10+
- [Stockfish](https://stockfishchess.org/download/) binary (not a pip package)

### 1 — Clone the repository

```bash
git clone https://github.com/youadah-boop/semi-fog-war-chess.git
cd semi-fog-war-chess
```

### 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` contains:

```
chess
pygame
pytest
```

### 3 — Install Stockfish

| OS | Command |
|----|---------|
| Ubuntu / Debian | `sudo apt install stockfish` |
| macOS (Homebrew) | `brew install stockfish` |
| Windows | Download from [stockfishchess.org](https://stockfishchess.org/download/), place the `.exe` anywhere |

If the binary is not named `stockfish` on your `PATH`, set the environment variable:

```bash
export STOCKFISH_PATH=/path/to/stockfish   # Linux / macOS
set STOCKFISH_PATH=C:\path\to\stockfish.exe  # Windows
```

---

## Running the game

### Graphical interface (recommended)

```bash
python gui.py
```

**On Windows** — to prevent the terminal from appearing in front of the game window:

```bash
pythonw gui.py
```

### Text mode (debug / headless)

```bash
python cli.py
```

### Controls

| Action | How |
|--------|-----|
| Move a piece | Click the piece, then click its destination |
| Enter a move manually | Type SAN (`Nf3`, `e4`, `O-O`) or UCI (`e2e4`) in the input bar, press **Enter** |
| Choose promotion | Click one of the four pieces in the pop-up menu |
| Cancel selection / promotion | **Escape** |
| Scroll the log | Mouse wheel over the log panel |

---

## Sampler algorithm

The **State Sampler** generates plausible board hypotheses for White from its `belief_state` (what it is legally allowed to know), following a **Gibbs Sampling + History Filters** approach:

### Step 1 — Initialisation

- Place all own pieces and all enemy pieces already observed (known from direct vision or temporary revelation).
- List the hidden enemy pieces (those not yet seen, using the real inventory reconstructed from one's own captures). Distribute them randomly over the free fog squares (ranks 3–6, not already seen empty and not occupied by a known piece). A captured piece is never placed back.

### Step 2 — Gibbs refinement loop (MCMC)

Repeated **N = 15** times to converge:

```
For each hidden enemy piece P:
  a. Remove P from its current square.
  b. For every currently empty fog square:
       i.  Place P on the candidate square.
       ii. Run history filters (line-of-sight check):
             → if P would reveal itself (giving check, controlling
               a king-adjacent square, or creating a pin) without
               having been seen in reality → score = −∞ (reject).
       iii. If valid, compute a tactical plausibility score
            (centralisation + mobility, inspired by the Kriegspiel
            "state pool" evaluation of Parker, Nau & Subrahmanian 2005).
  c. Convert valid scores to probabilities via Softmax.
  d. Sample the new square for P probabilistically.
  e. Place P there and move to the next hidden piece.
```

### Step 3 — Result

Return the converged board. Multiple independent chains are run (one per requested hypothesis); results are sorted by descending plausibility score. **Stockfish always receives `boards[0]`** — the most plausible estimate.

### Additional safeguards

- **No invented doubled pawns** — a hidden pawn prefers a file free of any other enemy pawn; a file collision is only accepted if no clean file passes the history filter.
- **No resurrected captured pieces** — the inventory is reconstructed from one's own captures (`belief_state["pieces_adverses_restantes_total"]`) and verified explicitly on every accepted board.

---

## Running the tests

```bash
pytest
```

22 tests covering:

| Module | Tests |
|--------|-------|
| `test_vision.py` | Fog zone size, always-visible pieces outside zone, check/pin/king-adjacency revelation, non-persistence, direct vision |
| `test_sampler.py` | Available squares, inventory respect, fog placement only, history-filter coherence, no doubled pawns, no resurrected pieces |
| `test_arbiter.py` | Legal move played unchanged, illegal move substituted, no second attempt, checkmate detection |
| `test_ai_opponent.py` | Stockfish unreachable → fallback, move submitted to referee, no piece count inflation |

---

## Project structure

```
semi_fog_chess/
├── engine/
│   ├── arbiter.py      131 lines — referee, real board, move validation
│   ├── vision.py       313 lines — fog rules, belief-state, reveal conditions
│   ├── sampler.py      370 lines — Gibbs sampling, history filters, plausibility
│   ├── partie.py       115 lines — orchestrator, journal messages
│   └── rendu.py        106 lines — ASCII/Unicode symbol grids
├── ai/
│   └── ai_opponent.py   98 lines — Stockfish wrapper
├── tests/
│   ├── test_vision.py  147 lines
│   ├── test_sampler.py 148 lines
│   ├── test_arbiter.py  40 lines
│   └── test_ai_opponent.py 49 lines
├── gui.py              583 lines — Pygame GUI
├── cli.py               54 lines — text mode
└── requirements.txt
                       ──────────
                  Total  ~2 150 lines
```

---

## Contributing

Pull requests and issues are welcome. A few conventions:

- All docstrings and comments are in **French** (the author's working language).
- Test coverage should stay at 100 % for `engine/` and `ai/`.
- The referee (`arbiter.py`) must **never** expose the real board outside its own module.
- The sampler must **never** import from `arbiter.py` — it only consumes `belief_state` dicts.

---

## License

MIT — see [`LICENSE`](LICENSE).

---

<p align="center">
  Made with ♟ · Python · Pygame · python-chess · Stockfish
</p>
