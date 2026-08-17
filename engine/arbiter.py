"""
arbiter.py — Le moteur-arbitre : seul détenteur du plateau réel.

Règles de la variante "Semi Fog War Chess" (cf. variante_battlechess.txt) :
- Mêmes règles de mouvement et d'échecs que les échecs classiques
  (coups légaux, échec, échec et mat, pat, règle des 50 coups, etc.).
- L'arbitre est le seul à connaître le plateau réel. Il ne le donne
  jamais, ni aux joueurs, ni au Sampler, ni à l'affichage.
- Aucun coup ne passe sans sa validation. En cas de coup illégal,
  l'arbitre fait lui-même une substitution par un coup légal choisi au
  hasard — pas de seconde tentative pour l'auteur du coup.
"""

import random
from dataclasses import dataclass
from typing import Optional
import chess


REFUS_GENERIQUE = "mouvement illégal"


@dataclass
class ResultatCoup:
    succes: bool
    coup_final_uci: Optional[str] = None   # le coup RÉELLEMENT joué (peut différer du coup soumis)
    coup_final_san: Optional[str] = None   # sa notation algébrique (lisible pour le journal)
    coup_original_legal: bool = True       # False si le coup soumis était illégal -> substitution aléatoire
    message: Optional[str] = None          # REFUS_GENERIQUE si coup_original_legal est False
    echec: bool = False
    echec_et_mat: bool = False
    pat: bool = False
    nulle_50_coups: bool = False
    nulle_repetition: bool = False
    nulle_materiel_insuffisant: bool = False
    camp_au_trait: Optional[chess.Color] = None


class Arbitre:
    """Le moteur-arbitre. Détient le plateau réel (`self._board`)."""

    def __init__(self, fen: Optional[str] = None):
        self._board = chess.Board(fen) if fen else chess.Board()
        self._numero_tour = 1

    @property
    def plateau_reel(self) -> chess.Board:
        return self._board

    @property
    def camp_au_trait(self) -> chess.Color:
        return self._board.turn

    @property
    def numero_tour(self) -> int:
        return self._numero_tour

    def soumettre_coup(self, uci: str) -> ResultatCoup:
        """
        Tente de jouer un coup en notation UCI. Si `uci` est illégal ou
        syntaxiquement invalide, l'arbitre substitue immédiatement un
        coup légal tiré au hasard parmi tous les coups légaux du camp
        au trait (règle de guerre — pas de seconde tentative). Le
        message de refus est volontairement générique, quelle que soit
        la vraie raison (case masquée par le brouillard, coup mettant
        son propre roi en échec, syntaxe invalide...) pour ne jamais
        fuiter d'information à l'auteur du coup.
        """
        try:
            coup = chess.Move.from_uci(uci)
            coup_legal = coup in self._board.legal_moves
        except ValueError:
            coup = None
            coup_legal = False

        if not coup_legal:
            coups_possibles = list(self._board.legal_moves)
            if not coups_possibles:
                return ResultatCoup(succes=False, coup_original_legal=False, message=REFUS_GENERIQUE)
            coup = random.choice(coups_possibles)

        san = self._board.san(coup)
        self._board.push(coup)
        self._numero_tour += 1

        return ResultatCoup(
            succes=True,
            coup_final_uci=coup.uci(),
            coup_final_san=san,
            coup_original_legal=coup_legal,
            message=None if coup_legal else REFUS_GENERIQUE,
            echec=self._board.is_check(),
            echec_et_mat=self._board.is_checkmate(),
            pat=self._board.is_stalemate(),
            nulle_50_coups=self._board.can_claim_fifty_moves(),
            nulle_repetition=self._board.can_claim_threefold_repetition(),
            nulle_materiel_insuffisant=self._board.is_insufficient_material(),
            camp_au_trait=self._board.turn,
        )

    def coups_legaux_uci(self) -> list[str]:
        return [m.uci() for m in self._board.legal_moves]

    def coup_est_legal(self, uci: str) -> bool:
        try:
            coup = chess.Move.from_uci(uci)
        except ValueError:
            return False
        return coup in self._board.legal_moves

    def partie_terminee(self) -> bool:
        return self._board.is_game_over()

    def etat_partie(self) -> str:
        if self._board.is_checkmate():
            gagnant = "noir" if self._board.turn == chess.WHITE else "blanc"
            return f"echec_et_mat_{gagnant}_gagne"
        if self._board.is_stalemate():
            return "pat"
        if self._board.is_insufficient_material():
            return "nulle_materiel_insuffisant"
        if self._board.can_claim_threefold_repetition():
            return "nulle_repetition"
        if self._board.can_claim_fifty_moves():
            return "nulle_50_coups"
        return "en_cours"

    def __str__(self) -> str:
        """Représentation ASCII du plateau RÉEL — debug uniquement, jamais
        envoyée à un client."""
        return str(self._board)
