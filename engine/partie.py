"""
partie.py — Orchestrateur de haut niveau : relie l'arbitre, le suivi
de croyances (vision.py) et le Sampler (sampler.py) pour offrir une
API simple à cli.py et gui.py, sans qu'ils aient à connaître les
détails internes des trois modules.

Ne fuite jamais le plateau réel ni le coup joué par l'IA : seules les
informations qu'un camp a le droit de connaître transitent vers
l'affichage.
"""

from dataclasses import asdict
from typing import Optional

import chess

from engine.arbiter import Arbitre, ResultatCoup
from engine.vision import SuiviCroyances
from engine.sampler import echantillonner_plateaux, plateau_vers_dict
from ai.ai_opponent import AdversaireIA


def _lire_etat(arbitre: Arbitre) -> dict:
    """Indicateurs de fin/état de partie lus directement sur le
    plateau réel APRÈS un coup — utilisé identiquement que le coup
    vienne d'un humain ou de l'IA."""
    b = arbitre.plateau_reel
    return {
        "echec": b.is_check(),
        "echec_et_mat": b.is_checkmate(),
        "pat": b.is_stalemate(),
        "nulle_50_coups": b.can_claim_fifty_moves(),
        "nulle_repetition": b.can_claim_threefold_repetition(),
        "nulle_materiel_insuffisant": b.is_insufficient_material(),
    }


def _messages_etat(etat: dict) -> list[str]:
    lignes = []
    if etat["echec_et_mat"]:
        lignes.append("Echec et mat")
    elif etat["pat"]:
        lignes.append("Pat")
    elif etat["echec"]:
        lignes.append("Echec")
    if etat["nulle_50_coups"]:
        lignes.append("Nulle par 50-coups")
    if etat["nulle_repetition"]:
        lignes.append("Nulle par répétition")
    if etat["nulle_materiel_insuffisant"]:
        lignes.append("Nulle par manque de force")
    return lignes


class Partie:
    def __init__(self, adversaire_ia: Optional[AdversaireIA] = None):
        self.arbitre = Arbitre()
        self.camp_humain = chess.WHITE
        self.camp_ia = chess.BLACK
        self.suivis = {
            chess.WHITE: SuiviCroyances(chess.WHITE),
            chess.BLACK: SuiviCroyances(chess.BLACK),
        }
        self.adversaire_ia = adversaire_ia or AdversaireIA()
        self._maj_croyances()

    def _maj_croyances(self) -> None:
        for camp in (chess.WHITE, chess.BLACK):
            self.suivis[camp].mettre_a_jour(self.arbitre.plateau_reel, self.arbitre.numero_tour)

    def belief_state(self, camp: chess.Color) -> dict:
        return self.suivis[camp].belief_state(self.arbitre.plateau_reel, self.arbitre.numero_tour)

    def plateaux_plausibles(self, camp: chess.Color, n: int = 5) -> list[chess.Board]:
        """Sert à l'affichage (plateau plausible des Blancs) — jamais à
        l'IA adverse, qui échantillonne elle-même en interne."""
        return echantillonner_plateaux(self.belief_state(camp), n=n)

    def hypothese_dict(self, camp: chess.Color, n: int = 5) -> Optional[dict]:
        plateaux = self.plateaux_plausibles(camp, n=n)
        if not plateaux:
            return None
        return plateau_vers_dict(plateaux[0], camp)

    def partie_terminee(self) -> bool:
        return self.arbitre.partie_terminee()

    def jouer_coup_humain(self, uci: str) -> dict:
        """Soumet le coup du camp humain (toujours Blanc). Retourne un
        dict avec les lignes de journal à afficher."""
        resultat = self.arbitre.soumettre_coup(uci)
        self._maj_croyances()

        lignes: list[str] = []
        if not resultat.coup_original_legal:
            lignes.append("Coup illégal. Arbitre joue un coup au hasard")
        lignes.append(f"Coup des Blancs : {resultat.coup_final_san}")
        lignes += _messages_etat(_lire_etat(self.arbitre))

        return {"resultat": resultat, "lignes": lignes}

    def jouer_coup_ia(self) -> dict:
        """Fait jouer l'IA (toujours Noir). Le coup réellement joué
        n'est JAMAIS révélé dans le journal (il porterait sur une case
        potentiellement encore dans le brouillard pour les Blancs)."""
        belief = self.belief_state(self.camp_ia)
        info = self.adversaire_ia.proposer_coup(belief, self.arbitre)
        self._maj_croyances()

        lignes: list[str] = []
        if info["source"] == "secours_arbitre":
            lignes.append("Coup illégal. Arbitre joue un coup au hasard")
        lignes += _messages_etat(_lire_etat(self.arbitre))

        return {"info": info, "lignes": lignes}
