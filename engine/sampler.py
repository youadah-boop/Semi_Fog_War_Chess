"""
sampler.py — State Sampler : génère, pour UN camp, des plateaux
plausibles compatibles avec ce qu'il sait (son `belief_state`),
suivant l'algorithme fourni ("Sampler_algorithme.txt") :

    Gibbs Sampling + Filtres d'Historique

1. INITIALISATION
   - Les pièces propres et les pièces adverses déjà observées
     (belief_state["pieces_adverses_connues"]) sont placées telles
     quelles.
   - Les pièces adverses manquantes (cachées) sont distribuées au
     hasard sur les cases libres du brouillard — dans cette variante,
     "case du brouillard" = case de la zone de brouillard (rangées 3
     à 6, cf. engine/vision.zone_brouillard) qui n'est ni occupée par
     une pièce déjà connue, ni vue vide par le champ de vision actuel
     du camp (une pièce cachée ne peut matériellement se trouver
     ailleurs : toute case hors de cette zone est toujours visible —
     cf. règle "hors_zone" de vision.py).
   - Aucune pièce déjà capturée n'est replacée : l'inventaire vient de
     `belief_state["pieces_adverses_restantes_total"]` (compte réel,
     reconstituable par le camp lui-même à partir de ses propres
     captures, cf. vision.py).

2. RAFFINEMENT PAS À PAS (boucle de Gibbs)
   Répété `iterations` fois pour faire converger le plateau : pour
   chaque pièce cachée P, on la retire, on note un score de
   plausibilité pour chaque case candidate valide (softmax), et on la
   replace au hasard pondéré par ces scores.

   Filtres d'historique ("vérification des lignes de vue") : faute
   d'un historique coup-par-coup détaillé (l'arbitre ne renvoie qu'un
   message générique en cas de coup illégal, cf. arbiter.py — aucune
   déduction fine à la Kriegspiel de type "mon fou bloqué en f5" n'est
   donc possible ici), le filtre disponible est la cohérence
   structurelle immédiate avec le plateau réel : un placement candidat
   est rejeté (score = -infini) s'il ferait apparaître une nouvelle
   pièce cachée en position d'échec, de voisinage du roi ou de
   clouage — elle aurait alors nécessairement déjà dû être révélée
   dans la réalité (contradiction avec ce que le camp sait vraiment).

3. RÉSULTAT
   `echantillonner_plateaux` fait tourner plusieurs chaînes
   indépendantes (autant que de plateaux demandés, avec un budget
   d'essais en cas d'échec de convergence) et retourne les plateaux
   obtenus, triés du plus au moins plausible.

GARDE-FOUS SUPPLÉMENTAIRES (demandés en plus de l'algorithme de base) :
   - Aucun plateau candidat ne peut faire apparaître deux pions cachés
     adverses sur la même colonne : un pion candidat qui doublerait une
     colonne déjà occupée par un autre pion adverse est écarté au
     profit d'une colonne libre, tant qu'il en reste une (repli sur le
     doublon uniquement si aucune colonne libre ne passe déjà le filtre
     des lignes de vue — cf. `_fichier_a_autre_pion`).
   - Aucune pièce déjà capturée ne peut réapparaître : garanti par
     construction (le nombre de pièces cachées générées = total réel
     moins pièces déjà connues, cf. `_pieces_adverses_restantes`), et
     revérifié explicitement à l'acceptation de chaque plateau par
     `_respecte_inventaire`, en garde-fou supplémentaire.

GARANTIE DE FUITE ZÉRO : ce module ne prend et ne lit JAMAIS le
plateau réel, uniquement le `belief_state` d'un camp.
"""

import math
import random
from typing import Optional
import chess

from engine.vision import (
    zone_brouillard,
    RANGEES_BROUILLARD,
    pieces_attaquant_roi,
    pieces_revelees_voisinage_roi,
    pieces_clouantes,
)


NOM_VERS_TYPE = {
    "pion": chess.PAWN,
    "cavalier": chess.KNIGHT,
    "fou": chess.BISHOP,
    "tour": chess.ROOK,
    "dame": chess.QUEEN,
    "roi": chess.KING,
}
TYPE_VERS_NOM = {v: k for k, v in NOM_VERS_TYPE.items()}

EFFECTIF_INITIAL = {
    chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2,
    chess.ROOK: 2, chess.QUEEN: 1, chess.KING: 1,
}

# Nombre de tours de raffinement Gibbs par chaîne. La zone de
# brouillard reste modeste (32 cases max) donc la convergence est
# rapide ; cette valeur est volontairement généreuse.
ITERATIONS_GIBBS_PAR_DEFAUT = 15


def _pieces_adverses_restantes(belief_state: dict) -> dict[int, int]:
    """Combien de pièces adverses de chaque type restent à placer dans
    l'ombre, une fois retirées celles déjà connues."""
    pieces_adverses_connues = belief_state["pieces_adverses_connues"]
    deja_localisees: dict[int, int] = {pt: 0 for pt in EFFECTIF_INITIAL}
    for info in pieces_adverses_connues.values():
        pt = NOM_VERS_TYPE[info["type"]]
        deja_localisees[pt] += 1

    total_reel = belief_state.get("pieces_adverses_restantes_total")
    if total_reel is not None:
        totaux = {pt: total_reel.get(TYPE_VERS_NOM[pt], 0) for pt in EFFECTIF_INITIAL}
    else:
        totaux = dict(EFFECTIF_INITIAL)

    return {pt: max(0, totaux[pt] - deja_localisees[pt]) for pt in EFFECTIF_INITIAL}


def _cases_disponibles_brouillard(belief_state: dict) -> list[int]:
    """Cases de la zone de brouillard ni occupées par une pièce connue,
    ni vues vides par le champ de vision actuel du camp."""
    occupees = {chess.parse_square(n) for n in belief_state["pieces_propres"]}
    occupees |= {chess.parse_square(n) for n in belief_state["pieces_adverses_connues"]}
    vues = {chess.parse_square(n) for n in belief_state["champ_de_vision_actuel"]}
    return [c for c in zone_brouillard() if c not in occupees and c not in vues]


def _construire_plateau_connu(belief_state: dict, camp: chess.Color) -> chess.Board:
    board = chess.Board(None)
    board.turn = camp  # le trait est une information publique, pas cachée
    for nom_case, type_piece in belief_state["pieces_propres"].items():
        board.set_piece_at(chess.parse_square(nom_case), chess.Piece(NOM_VERS_TYPE[type_piece], camp))
    for nom_case, info in belief_state["pieces_adverses_connues"].items():
        board.set_piece_at(chess.parse_square(nom_case), chess.Piece(NOM_VERS_TYPE[info["type"]], not camp))
    return board


def _respecte_lignes_de_vue(board: chess.Board, camp: chess.Color, cases_deja_revelees: set[int]) -> bool:
    """Filtre d'historique : rejette un plateau candidat si une pièce
    cachée s'y trouve en position d'échec / voisinage du roi / clouage
    sans être déjà parmi les cases connues — elle aurait dû être
    révélée dans la réalité."""
    reveles = (
        pieces_attaquant_roi(board, camp)
        | pieces_revelees_voisinage_roi(board, camp)
        | set(pieces_clouantes(board, camp).values())
    )
    return reveles <= cases_deja_revelees


def _plateau_valide(board: chess.Board) -> bool:
    if board.king(chess.WHITE) is None or board.king(chess.BLACK) is None:
        return False
    roi_inactif = board.king(not board.turn)
    if roi_inactif is not None and board.is_attacked_by(board.turn, roi_inactif):
        return False  # le camp qui n'a pas le trait ne peut pas être en échec
    return True


def _fichier_a_autre_pion(board: chess.Board, camp_adverse: chess.Color, fichier: int, case_a_exclure: Optional[int] = None) -> bool:
    """True si un pion de `camp_adverse` occupe déjà la colonne
    `fichier` ailleurs que sur `case_a_exclure` — sert à empêcher le
    Sampler d'inventer des pions doublés sans justification (capture)."""
    for sq in board.pieces(chess.PAWN, camp_adverse):
        if sq == case_a_exclure:
            continue
        if chess.square_file(sq) == fichier:
            return True
    return False


def _respecte_inventaire(board: chess.Board, camp: chess.Color, belief_state: dict) -> bool:
    """Garde-fou supplémentaire : aucune pièce déjà capturée ne doit
    réapparaître. Vérifie que le compte de chaque type de pièce
    adverse sur le plateau candidat correspond exactement au total
    réel restant (belief_state["pieces_adverses_restantes_total"])."""
    total_reel = belief_state.get("pieces_adverses_restantes_total")
    if total_reel is None:
        return True
    camp_adverse = not camp
    for nom_type, type_piece in NOM_VERS_TYPE.items():
        if len(board.pieces(type_piece, camp_adverse)) != total_reel.get(nom_type, 0):
            return False
    return True


def _score_case(board: chess.Board, case: int) -> float:
    """Score de plausibilité tactique d'UNE pièce déjà placée sur
    `case` du plateau `board` : centralisation + mobilité, dans
    l'esprit du "state pool" évalué par une fonction d'échecs de la
    littérature Kriegspiel (Parker, Nau & Subrahmanian 2005)."""
    fichier = chess.square_file(case)
    rang = chess.square_rank(case)
    centralisation = 3.5 - (abs(3.5 - fichier) + abs(3.5 - rang)) / 2.0
    mobilite = len(board.attacks(case))
    return centralisation + 0.3 * mobilite


def _initialiser_plateau(
    belief_state: dict,
    camp: chess.Color,
    cases_disponibles: list[int],
    restantes: dict[int, int],
    rng: random.Random,
) -> Optional[chess.Board]:
    """Étape 1 : place les pièces connues, distribue les pièces cachées
    au hasard sur les cases libres du brouillard. Retourne None si
    l'inventaire ne tient pas dans les cases disponibles (contraintes
    incohérentes, ne devrait pas arriver avec un belief_state normal).

    Les pions cachés sont distribués en préférant des colonnes encore
    libres de tout autre pion adverse (pas de doublon inventé sans
    justification), avec repli sur un doublon uniquement si aucune
    colonne libre ne reste disponible."""
    a_placer = [pt for pt, n in restantes.items() for _ in range(n)]
    if len(a_placer) > len(cases_disponibles):
        return None

    board = _construire_plateau_connu(belief_state, camp)
    camp_adverse = not camp
    cases_libres = list(cases_disponibles)
    rng.shuffle(cases_libres)

    pions = [pt for pt in a_placer if pt == chess.PAWN]
    autres = [pt for pt in a_placer if pt != chess.PAWN]

    for type_piece in autres:
        if not cases_libres:
            return None
        case = cases_libres.pop()
        board.set_piece_at(case, chess.Piece(type_piece, camp_adverse))

    for _ in pions:
        if not cases_libres:
            return None
        sans_doublon = [c for c in cases_libres if not _fichier_a_autre_pion(board, camp_adverse, chess.square_file(c))]
        pool = sans_doublon if sans_doublon else cases_libres
        case = rng.choice(pool)
        cases_libres.remove(case)
        board.set_piece_at(case, chess.Piece(chess.PAWN, camp_adverse))

    return board


def _affiner_gibbs(
    board: chess.Board,
    camp: chess.Color,
    cases_disponibles: list[int],
    cases_deja_revelees: set[int],
    iterations: int,
    rng: random.Random,
) -> chess.Board:
    """Étape 2 : boucle de raffinement Gibbs. Pour chaque pièce cachée,
    on la retire, on évalue chaque case candidate encore libre (rejet
    -infini si elle contredit les lignes de vue, sinon score tactique),
    on convertit en probabilités par softmax, et on retire une nouvelle
    case au hasard pondéré."""
    cases_cachees = [c for c in cases_disponibles if board.piece_at(c) is not None]
    if not cases_cachees:
        return board

    camp_adverse = not camp

    for _ in range(iterations):
        rng.shuffle(cases_cachees)
        for i, case_actuelle in enumerate(cases_cachees):
            piece = board.piece_at(case_actuelle)
            if piece is None:
                continue
            est_pion = piece.piece_type == chess.PAWN
            board.remove_piece_at(case_actuelle)

            candidats: list[int] = []
            scores: list[float] = []
            candidats_sans_doublon: list[int] = []
            scores_sans_doublon: list[float] = []
            for case_candidate in cases_disponibles:
                if board.piece_at(case_candidate) is not None:
                    continue  # déjà occupée par une autre pièce cachée
                board.set_piece_at(case_candidate, piece)
                if _respecte_lignes_de_vue(board, camp, cases_deja_revelees):
                    s = _score_case(board, case_candidate)
                    candidats.append(case_candidate)
                    scores.append(s)
                    if est_pion and not _fichier_a_autre_pion(board, camp_adverse, chess.square_file(case_candidate), case_a_exclure=case_candidate):
                        candidats_sans_doublon.append(case_candidate)
                        scores_sans_doublon.append(s)
                # sinon : score = -infini -> candidat simplement ignoré
                board.remove_piece_at(case_candidate)

            if est_pion and candidats_sans_doublon:
                # Préfère une colonne encore libre de tout autre pion
                # adverse (pas de doublon inventé sans justification).
                candidats, scores = candidats_sans_doublon, scores_sans_doublon

            if not candidats:
                # Aucun candidat ne passe le filtre (rare) : on remet la
                # pièce où elle était plutôt que de la perdre.
                board.set_piece_at(case_actuelle, piece)
                continue

            plafond = max(scores)
            poids = [math.exp(s - plafond) for s in scores]
            total = sum(poids)
            probabilites = [w / total for w in poids]
            case_choisie = rng.choices(candidats, weights=probabilites, k=1)[0]
            board.set_piece_at(case_choisie, piece)
            cases_cachees[i] = case_choisie

    return board


def _score_plateau(board: chess.Board, camp: chess.Color) -> float:
    camp_adverse = not camp
    return sum(
        _score_case(board, sq)
        for sq in chess.SquareSet(board.occupied_co[camp_adverse])
        if chess.square_rank(sq) in RANGEES_BROUILLARD
    )


def echantillonner_plateaux(
    belief_state: dict,
    n: int = 5,
    iterations: int = ITERATIONS_GIBBS_PAR_DEFAUT,
    generateur_aleatoire: Optional[random.Random] = None,
    essais_max: Optional[int] = None,
) -> list[chess.Board]:
    """
    Fait tourner jusqu'à `n` chaînes Gibbs indépendantes (initialisation
    + raffinement) et retourne les plateaux valides obtenus, triés du
    plus au moins plausible (`_score_plateau`). Peut retourner moins de
    `n` plateaux si les contraintes sont trop serrées (rare).
    """
    rng = generateur_aleatoire or random
    camp = chess.WHITE if belief_state["camp"] == "blanc" else chess.BLACK

    restantes = _pieces_adverses_restantes(belief_state)
    cases_disponibles = _cases_disponibles_brouillard(belief_state)
    cases_deja_revelees = {chess.parse_square(nc) for nc in belief_state["pieces_adverses_connues"]}
    essais_max = essais_max if essais_max is not None else max(4 * n, 20)

    resultats: list[chess.Board] = []
    essais = 0
    while len(resultats) < n and essais < essais_max:
        essais += 1
        board = _initialiser_plateau(belief_state, camp, cases_disponibles, restantes, rng)
        if board is None:
            break  # contraintes impossibles : inutile de réessayer
        board = _affiner_gibbs(board, camp, cases_disponibles, cases_deja_revelees, iterations, rng)
        if (
            _plateau_valide(board)
            and _respecte_lignes_de_vue(board, camp, cases_deja_revelees)
            and _respecte_inventaire(board, camp, belief_state)
        ):
            resultats.append(board)

    resultats.sort(key=lambda b: _score_plateau(b, camp), reverse=True)
    return resultats


def plateau_vers_dict(board: chess.Board, camp: chess.Color) -> dict[str, str]:
    """Sérialise un plateau candidat {case: type} pour les pièces
    ADVERSES uniquement (les pièces propres sont déjà connues via
    belief_state["pieces_propres"])."""
    camp_adverse = not camp
    return {
        chess.square_name(sq): TYPE_VERS_NOM[piece.piece_type]
        for sq, piece in board.piece_map().items()
        if piece.color == camp_adverse
    }
