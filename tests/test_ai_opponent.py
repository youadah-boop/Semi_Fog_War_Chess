import chess

from engine.arbiter import Arbitre
from engine.vision import SuiviCroyances
from ai.ai_opponent import AdversaireIA


def test_secours_arbitre_si_stockfish_indisponible(monkeypatch):
    arbitre = Arbitre()
    arbitre.soumettre_coup("e2e4")  # Blanc joue, Noir au trait

    suivi_noir = SuiviCroyances(chess.BLACK)
    suivi_noir.mettre_a_jour(arbitre.plateau_reel, arbitre.numero_tour)
    belief = suivi_noir.belief_state(arbitre.plateau_reel, arbitre.numero_tour)

    adversaire = AdversaireIA(chemin_stockfish="/chemin/inexistant/stockfish")
    tour_avant = arbitre.numero_tour
    info = adversaire.proposer_coup(belief, arbitre)

    # Le moteur échoue -> filet de sécurité : un coup légal est quand
    # même joué, et l'erreur de connectivité est explicite.
    assert arbitre.numero_tour == tour_avant + 1
    assert info["coup_uci"] is not None
    assert info["source"] == "secours_arbitre"


def test_coup_calcule_sur_hypothese_soumis_a_larbitre(monkeypatch):
    arbitre = Arbitre()
    arbitre.soumettre_coup("e2e4")

    suivi_noir = SuiviCroyances(chess.BLACK)
    suivi_noir.mettre_a_jour(arbitre.plateau_reel, arbitre.numero_tour)
    belief = suivi_noir.belief_state(arbitre.plateau_reel, arbitre.numero_tour)

    adversaire = AdversaireIA()

    def faux_stockfish(self, board):
        # Simule Stockfish : joue le premier coup légal du plateau
        # hypothétique fourni (peu importe lequel pour le test).
        return next(iter(board.legal_moves)).uci()

    monkeypatch.setattr(AdversaireIA, "_meilleur_coup_stockfish", faux_stockfish)

    info = adversaire.proposer_coup(belief, arbitre)
    assert info["coup_uci"] is not None
    assert info["plateau_choisi"] is not None
    # Le plateau hypothétique doit contenir exactement les 16 pièces
    # noires (aucune capture n'a encore eu lieu) — ni plus, ni moins.
    assert len(info["plateau_choisi"]) == 16
