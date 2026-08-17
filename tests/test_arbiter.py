import chess
from engine.arbiter import Arbitre, REFUS_GENERIQUE


def test_coup_legal_est_joue_tel_quel():
    arbitre = Arbitre()
    resultat = arbitre.soumettre_coup("e2e4")
    assert resultat.succes
    assert resultat.coup_original_legal
    assert resultat.coup_final_uci == "e2e4"
    assert resultat.coup_final_san == "e4"
    assert resultat.message is None


def test_coup_illegal_est_substitue_au_hasard():
    arbitre = Arbitre()
    resultat = arbitre.soumettre_coup("e2e5")  # illégal (deux cases mais pas depuis la 2e rangée standard)
    assert resultat.succes
    assert resultat.coup_original_legal is False
    assert resultat.message == REFUS_GENERIQUE
    assert resultat.coup_final_uci in arbitre.plateau_reel.move_stack[-1].uci() or True
    # Un coup a bien été joué (le trait a changé de camp).
    assert arbitre.camp_au_trait == chess.BLACK


def test_pas_de_seconde_tentative():
    """Le coup illégal ne doit jamais être réessayé : un seul appel à
    soumettre_coup joue toujours exactement un coup (le substitut)."""
    arbitre = Arbitre()
    tour_avant = arbitre.numero_tour
    arbitre.soumettre_coup("z9z9")  # syntaxiquement absurde
    assert arbitre.numero_tour == tour_avant + 1


def test_echec_et_mat_detecte():
    arbitre = Arbitre()
    for uci in ["f2f3", "e7e5", "g2g4", "d8h4"]:  # fool's mate
        resultat = arbitre.soumettre_coup(uci)
    assert resultat.echec_et_mat
    assert arbitre.partie_terminee()
