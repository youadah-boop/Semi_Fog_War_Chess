"""
ai_opponent.py — L'adversaire IA (Stockfish), joue le camp Noir.

Conforme à la description : "il reçoit seulement le plateau
hypothétique le plus plausible (un plateau trouvé par Sampler). Il
joue son meilleur coup (correspondant au plateau hypothétique)."

`echantillonner_plateaux` retourne les plateaux déjà triés du plus au
moins plausible (cf. sampler.py) — on prend donc `plateaux[0]`.

Règle de guerre (identique à un joueur humain, cf. arbiter.py) : le
coup calculé par Stockfish porte sur le plateau HYPOTHÉTIQUE, pas sur
le plateau réel — ils peuvent diverger dans la zone de brouillard. Si
le coup s'avère illégal une fois soumis au vrai plateau, l'arbitre
substitue un coup légal au hasard, exactement comme pour tout autre
camp.
"""

import os
import random
from typing import Optional

import chess
import chess.engine
import subprocess

from engine.arbiter import Arbitre
from engine.sampler import echantillonner_plateaux, plateau_vers_dict


class AdversaireIA:
    def __init__(self, chemin_stockfish: Optional[str] = None,):
        """
        chemin_stockfish : chemin vers le binaire Stockfish (pas un
        paquet pip — à installer séparément). Par défaut, lu depuis la
        variable d'environnement STOCKFISH_PATH, sinon "stockfish" sur
        le PATH système.
        """
        self.chemin_stockfish = chemin_stockfish or os.environ.get("STOCKFISH_PATH", "stockfish")
        self.derniere_erreur_moteur: Optional[str] = None

    def proposer_coup(self, belief_state: dict, arbitre: Arbitre, nb_plateaux_candidats: int = 5) -> dict:
        """
        Choisit le plateau le plus plausible (Sampler) puis lui fait
        jouer un coup par Stockfish, soumis directement à `arbitre`.

        Retourne un dict :
        - coup_uci : le coup RÉELLEMENT joué sur le plateau réel.
        - coup_calcule_uci : le coup choisi par Stockfish sur le
          plateau hypothétique (None si aucun plateau plausible n'a pu
          être généré, ou si le moteur a échoué).
        - source : "stockfish" ou "secours_arbitre".
        - plateau_choisi : le plateau hypothétique retenu, sérialisé
          (case -> type des pièces adverses hypothétiques), ou None.
        - erreur_moteur : diagnostic de connectivité Stockfish (binaire
          introuvable, etc.), None si tout s'est bien passé — ne fuite
          rien du brouillard de guerre.
        """
        camp = chess.WHITE if belief_state["camp"] == "blanc" else chess.BLACK
        plateaux = echantillonner_plateaux(belief_state, n=nb_plateaux_candidats)

        if not plateaux:
            secours = random.choice(arbitre.coups_legaux_uci())
            arbitre.soumettre_coup(secours)
            return {
                "coup_uci": secours,
                "coup_calcule_uci": None,
                "source": "secours_arbitre",
                "plateau_choisi": None,
                "erreur_moteur": None,
            }

        plateau_choisi = plateaux[0]  # le plus plausible (déjà trié par le sampler)
        coup_calcule = self._meilleur_coup_stockfish(plateau_choisi)

        resultat = arbitre.soumettre_coup(coup_calcule if coup_calcule is not None else "0000")
        source = "stockfish" if (coup_calcule is not None and resultat.coup_original_legal) else "secours_arbitre"

        return {
            "coup_uci": resultat.coup_final_uci,
            "coup_calcule_uci": coup_calcule,
            "source": source,
            "plateau_choisi": plateau_vers_dict(plateau_choisi, camp),
            "erreur_moteur": self.derniere_erreur_moteur,
        }

    def _meilleur_coup_stockfish(self, board: chess.Board) -> Optional[str]:
        """Isolé pour être facilement simulé dans les tests. Retourne
          None (jamais d'exception) si le moteur est indisponible — laisse
        ` proposer_coup` retomber sur le filet de sécurité de l'arbitre.
        # Configurer la limite avec le paramètre 'depth'
        # ex. depth=10 signifie que Stockfish analysera jusqu'à 10 demi-coups (5 coups complets)."""
        limite = chess.engine.Limit(depth=5)
        try:
            with chess.engine.SimpleEngine.popen_uci(self.chemin_stockfish, creationflags=subprocess.CREATE_NO_WINDOW) as moteur:
                resultat = moteur.play(board, limite)
                self.derniere_erreur_moteur = None
                return resultat.move.uci() if resultat.move is not None else None
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, FileNotFoundError, OSError) as e:
            self.derniere_erreur_moteur = f"{type(e).__name__}: {e}"
            return None
