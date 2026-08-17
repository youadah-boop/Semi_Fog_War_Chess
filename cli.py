"""cli.py — Mode texte (utile pour tester sans Pygame). Blanc humain
contre Noir Stockfish, comme le décrit variante_battlechess.txt."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from engine.partie import Partie
from engine.rendu import rendu_ascii_plateau_connu, rendu_ascii_plateau_hypothese


def parser_coup(board, texte):
    import chess
    try:
        return board.parse_san(texte).uci()
    except ValueError:
        pass
    try:
        chess.Move.from_uci(texte)
        return texte
    except ValueError:
        return None


def main():
    partie = Partie()
    print("=== Semi Fog War Chess ===")
    print("Blanc humain contre Noir (Stockfish). Brouillard : rangées 3 à 6.\n")

    while not partie.partie_terminee():
        import chess
        if partie.arbitre.camp_au_trait == chess.WHITE:
            print("Tour aux Blancs")
            belief = partie.belief_state(chess.WHITE)
            print(rendu_ascii_plateau_connu(belief))
            hyp = partie.hypothese_dict(chess.WHITE)
            print("\nPlateau plausible :")
            print(rendu_ascii_plateau_hypothese(belief, hyp))
            texte = input("\nCoup (SAN/UCI) > ").strip()
            uci = parser_coup(partie.arbitre.plateau_reel, texte)
            resultat = partie.jouer_coup_humain(uci if uci else "0000")
            for ligne in resultat["lignes"]:
                print(ligne)
        else:
            print("Tour à Stockfish ...")
            resultat = partie.jouer_coup_ia()
            for ligne in resultat["lignes"]:
                print(ligne)
        print()


if __name__ == "__main__":
    main()
