"""
vision.py — Calcule, à partir du plateau réel, ce que CHAQUE camp a le
droit de savoir dans la variante "Semi Fog War Chess". C'est ici, et
uniquement ici, que se joue la discipline du brouillard de guerre :
engine/sampler.py et ai/ai_opponent.py ne doivent jamais recevoir
autre chose que la sortie de ce module (le `belief_state`).

Règles de la variante (cf. variante_battlechess.txt, zone étendue à 4
rangées) :

- ZONE DE BROUILLARD : rangées 3 à 6 (32 cases). Toute pièce adverse
  HORS de cette zone est TOUJOURS visible, sans condition.
- VISION (façon Dark Chess 1989) : chaque camp voit ses propres pièces
  et les cases (vides ou occupées par l'ennemi) où ses propres pièces
  peuvent aller occuper/capturer — y compris le long d'une ligne
  bloquée par un clouage, la pièce clouée "voit" quand même à travers
  sa propre ligne d'attaque géométrique.
- Une pièce sous brouillard (donc située en rangée 3, 4, 5 ou 6)
  redevient visible TEMPORAIREMENT si :
    * elle attaque le roi adverse (échec) ; ou
    * elle attaque une case voisine du roi adverse — case vide, ou
      occupée par une pièce ennemie protégée que le roi ne peut pas
      capturer ; ou
    * elle cloue une pièce ennemie contre son roi.
  "Temporairement" veut dire que RIEN de tout cela ne persiste : à
  chaque tour, ces conditions sont recalculées à neuf à partir du
  plateau réel. Une pièce qui n'est plus vue et ne remplit plus aucune
  de ces conditions retourne dans l'ombre.

Statuts :
    confirmee  -> vue directement CE tour-ci (vision directe, ou toute
                  pièce adverse hors de la zone de brouillard).
    localisee  -> révélée par échec, voisinage du roi ou clouage CE
                  tour-ci uniquement (ne persiste pas).
"""

from dataclasses import dataclass
from typing import Optional
import chess


STATUT_CONFIRMEE = "confirmee"
STATUT_LOCALISEE = "localisee"

SOURCE_VISION_DIRECTE = "vision_directe"
SOURCE_HORS_ZONE = "hors_zone"
SOURCE_ECHEC = "echec"
SOURCE_VOISINAGE_ROI = "voisinage_roi"
SOURCE_CLOUAGE = "clouage"

NOM_PIECE = {
    chess.PAWN: "pion",
    chess.KNIGHT: "cavalier",
    chess.BISHOP: "fou",
    chess.ROOK: "tour",
    chess.QUEEN: "dame",
    chess.KING: "roi",
}

# Rangées 3 à 6 (indices python-chess 2 à 5, base 0).
RANGEES_BROUILLARD = (2, 3, 4, 5)


def zone_brouillard() -> frozenset[int]:
    """Les 32 cases de la zone de brouillard (rangées 3 à 6)."""
    return frozenset(
        sq for sq in chess.SQUARES if chess.square_rank(sq) in RANGEES_BROUILLARD
    )


def hors_zone(square: int) -> bool:
    return chess.square_rank(square) not in RANGEES_BROUILLARD


def _nom_case(square: int) -> str:
    return chess.square_name(square)


@dataclass
class EntreeConnue:
    type: str
    statut: str
    confiance: float
    source: str
    tour_maj: int

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "statut": self.statut,
            "confiance": self.confiance,
            "source": self.source,
            "tour_maj": self.tour_maj,
        }


def _cases_avancee_pion(board: chess.Board, square: int, camp: chess.Color) -> set[int]:
    """
    `board.attacks()` ne donne, pour un pion, que ses cases de capture
    en diagonale — jamais la case droit devant lui, alors qu'il peut
    "aller l'occuper" (coup normal, pas de capture). La règle de
    vision de la variante ("cases où leurs propres pièces peuvent
    aller occuper/capturer") inclut donc explicitement l'avance d'un
    pas (toujours visible, pour savoir si elle est bloquée) et de deux
    pas depuis la case de départ (si la première est libre).
    """
    resultat: set[int] = set()
    direction = 8 if camp == chess.WHITE else -8
    rang_depart = 1 if camp == chess.WHITE else 6
    une_case = square + direction
    if 0 <= une_case < 64:
        resultat.add(une_case)
        if board.piece_at(une_case) is None and chess.square_rank(square) == rang_depart:
            deux_cases = square + 2 * direction
            if 0 <= deux_cases < 64:
                resultat.add(deux_cases)
    return resultat


def champ_de_vision(board: chess.Board, camp: chess.Color) -> set[int]:
    """
    Cases actuellement visibles par `camp` : les cases occupées par ses
    propres pièces, plus toutes les cases (vides ou sous l'ennemi) où
    ces pièces peuvent aller occuper/capturer — qu'un coup y soit
    légal ou non pour l'instant (une pièce clouée voit toujours le
    long de sa ligne, même si elle ne peut pas légalement s'y
    déplacer) — exactement la règle de vision de la variante Dark
    Chess (1989) citée dans la description.
    """
    vues: set[int] = set()
    for square in chess.SquareSet(board.occupied_co[camp]):
        vues.add(square)
        vues |= set(board.attacks(square))
        piece = board.piece_at(square)
        if piece is not None and piece.piece_type == chess.PAWN:
            vues |= _cases_avancee_pion(board, square, camp)
    return vues


def pieces_clouantes(board: chess.Board, camp: chess.Color) -> dict[int, int]:
    """{case_piece_clouee: case_piece_clouante} pour toutes les pièces
    de `camp` actuellement clouées contre leur roi."""
    resultat: dict[int, int] = {}
    roi_case = board.king(camp)
    if roi_case is None:
        return resultat

    for square in chess.SquareSet(board.occupied_co[camp]):
        if not board.is_pinned(camp, square):
            continue
        rayon = board.pin(camp, square)
        for case_rayon in rayon:
            if case_rayon in (square, roi_case):
                continue
            piece = board.piece_at(case_rayon)
            if piece is not None and piece.color != camp:
                resultat[square] = case_rayon
                break
    return resultat


def pieces_attaquant_roi(board: chess.Board, camp: chess.Color) -> set[int]:
    """Cases des pièces adverses qui attaquent (mettent en échec) le
    roi de `camp`, sur le plateau donné. Calculé structurellement (pas
    conditionné par le trait), pour rester valable quel que soit le
    moment où le belief_state est reconstruit."""
    roi_case = board.king(camp)
    if roi_case is None:
        return set()
    return set(board.attackers(not camp, roi_case))


def pieces_revelees_voisinage_roi(board: chess.Board, camp: chess.Color) -> set[int]:
    """
    Cases des pièces adverses qui attaquent une case voisine du roi de
    `camp` — case vide (elle en contrôle l'accès), ou occupée par une
    pièce ennemie qu'elles protègent (le roi ne peut alors pas la
    capturer). Une case voisine occupée par une pièce PROPRE est
    ignorée : rien de nouveau à en tirer.
    """
    roi_case = board.king(camp)
    if roi_case is None:
        return set()

    camp_adverse = not camp
    resultat: set[int] = set()
    for voisine in chess.SquareSet(chess.BB_KING_ATTACKS[roi_case]):
        piece = board.piece_at(voisine)
        if piece is not None and piece.color == camp:
            continue
        resultat |= set(board.attackers(camp_adverse, voisine))
    return resultat


class SuiviCroyances:
    """Maintient, pour UN camp, ce qu'il sait du plateau réel. Aucune
    mémoire d'un tour à l'autre : `mettre_a_jour` recalcule tout à neuf
    à chaque appel, conformément à la règle "temporairement visible"."""

    def __init__(self, camp: chess.Color):
        self.camp = camp
        self._connues: dict[int, EntreeConnue] = {}
        self._dernier_refus: Optional[str] = None

    def mettre_a_jour(self, board: chess.Board, tour: int) -> None:
        camp_adverse = not self.camp
        nouvelles: dict[int, EntreeConnue] = {}

        # 1. Hors zone de brouillard : toujours visible, sans condition.
        for square in chess.SquareSet(board.occupied_co[camp_adverse]):
            if hors_zone(square):
                piece = board.piece_at(square)
                nouvelles[square] = EntreeConnue(
                    type=NOM_PIECE[piece.piece_type],
                    statut=STATUT_CONFIRMEE,
                    confiance=1.0,
                    source=SOURCE_HORS_ZONE,
                    tour_maj=tour,
                )

        # 2. Révélations structurelles dans la zone de brouillard :
        #    échec > voisinage du roi > clouage, aucune ne persiste.
        echecs = pieces_attaquant_roi(board, self.camp)
        voisinage = pieces_revelees_voisinage_roi(board, self.camp)
        clouages = pieces_clouantes(board, self.camp)
        cases_clouantes = set(clouages.values())
        cases_structurelles = echecs | voisinage | cases_clouantes

        for square in cases_structurelles:
            if square in nouvelles:
                continue  # déjà connue (hors zone) — rien à changer
            piece = board.piece_at(square)
            if piece is None or piece.color != camp_adverse:
                continue
            if square in echecs:
                source = SOURCE_ECHEC
            elif square in voisinage:
                source = SOURCE_VOISINAGE_ROI
            else:
                source = SOURCE_CLOUAGE
            nouvelles[square] = EntreeConnue(
                type=NOM_PIECE[piece.piece_type],
                statut=STATUT_LOCALISEE,
                confiance=0.95,
                source=source,
                tour_maj=tour,
            )

        # 3. Vision directe (champ de vision façon Dark Chess) : écrase/
        #    upgrade en confiance maximale, en conservant l'étiquette de
        #    source la plus informative si elle existe déjà.
        vues = champ_de_vision(board, self.camp)
        for square in vues:
            piece = board.piece_at(square)
            if piece is None or piece.color != camp_adverse:
                continue
            source = nouvelles[square].source if square in nouvelles else SOURCE_VISION_DIRECTE
            nouvelles[square] = EntreeConnue(
                type=NOM_PIECE[piece.piece_type],
                statut=STATUT_CONFIRMEE,
                confiance=1.0,
                source=source,
                tour_maj=tour,
            )

        self._connues = nouvelles

    def enregistrer_refus(self, message: str) -> None:
        self._dernier_refus = message

    def effacer_refus(self) -> None:
        self._dernier_refus = None

    def belief_state(self, board: chess.Board, tour: int) -> dict:
        roi_case = board.king(self.camp)
        en_echec = board.is_check() and board.turn == self.camp

        cases_legales_roi: list[str] = []
        if en_echec and roi_case is not None:
            cases_legales_roi = [
                _nom_case(coup.to_square)
                for coup in board.legal_moves
                if coup.from_square == roi_case
            ]

        pieces_dict = {
            _nom_case(sq): entree.to_dict() for sq, entree in self._connues.items()
        }

        pieces_propres = {
            _nom_case(sq): NOM_PIECE[board.piece_at(sq).piece_type]
            for sq in chess.SquareSet(board.occupied_co[self.camp])
        }

        pieces_adverses_restantes_total = {
            NOM_PIECE[pt]: len(board.pieces(pt, not self.camp)) for pt in NOM_PIECE
        }

        return {
            "camp": "blanc" if self.camp == chess.WHITE else "noir",
            "tour": tour,
            "roi": {
                "case": _nom_case(roi_case) if roi_case is not None else None,
                "en_echec": en_echec,
                "cases_legales": cases_legales_roi,
            },
            "pieces_adverses_connues": pieces_dict,
            "pieces_propres": pieces_propres,
            "champ_de_vision_actuel": [_nom_case(sq) for sq in champ_de_vision(board, self.camp)],
            "zone_brouillard": [_nom_case(sq) for sq in zone_brouillard()],
            "pieces_adverses_restantes_total": pieces_adverses_restantes_total,
            "dernier_refus": self._dernier_refus,
        }
