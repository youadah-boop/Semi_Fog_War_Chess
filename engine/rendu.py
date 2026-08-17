"""
rendu.py — Construit des grilles 8x8 de cellules à partir d'un
belief_state (et, optionnellement, d'une hypothèse du Sampler), sans
jamais toucher au plateau réel. Réutilisé par cli.py (texte) et
gui.py (Pygame).

Chaque cellule de la grille "connue" (plateau brouillé du joueur) est
un tuple (camp, type_piece, statut_ou_None) ou None si la case est
vide/inconnue :
    - une pièce propre  -> ("blanc"/"noir", type, None)
    - une pièce adverse connue -> (camp_adverse, type, source)
    - case vue vide (confirmée vide) -> "vide_vue"
    - case dans le brouillard, pas d'info -> "brouillard"
    - case hors zone de brouillard, vide -> "vide" (toujours visible)
"""

from typing import Optional
import chess

SYMBOLES = {
    ("blanc", "roi"): "R", ("blanc", "dame"): "D", ("blanc", "tour"): "T",
    ("blanc", "fou"): "F", ("blanc", "cavalier"): "C", ("blanc", "pion"): "P",
    ("noir", "roi"): "r", ("noir", "dame"): "d", ("noir", "tour"): "t",
    ("noir", "fou"): "f", ("noir", "cavalier"): "c", ("noir", "pion"): "p",
}

GLYPHES = {
    ("blanc", "roi"): "♔", ("blanc", "dame"): "♕", ("blanc", "tour"): "♖",
    ("blanc", "fou"): "♗", ("blanc", "cavalier"): "♘", ("blanc", "pion"): "♙",
    ("noir", "roi"): "♚", ("noir", "dame"): "♛", ("noir", "tour"): "♜",
    ("noir", "fou"): "♝", ("noir", "cavalier"): "♞", ("noir", "pion"): "♟",
}


def nom_camp(camp: chess.Color) -> str:
    return "blanc" if camp == chess.WHITE else "noir"


def cellule_connue(belief_state: dict, nom_case: str):
    """Retourne la cellule à afficher pour `nom_case` sur le plateau
    brouillé du joueur : pièce propre, pièce adverse connue, case vue
    vide, ou None (brouillard, aucune info)."""
    camp = belief_state["camp"]
    camp_adverse = "noir" if camp == "blanc" else "blanc"

    if nom_case in belief_state["pieces_propres"]:
        return (camp, belief_state["pieces_propres"][nom_case], None)

    connues = belief_state["pieces_adverses_connues"]
    if nom_case in connues:
        info = connues[nom_case]
        return (camp_adverse, info["type"], info["source"])

    if nom_case in belief_state["champ_de_vision_actuel"]:
        return "vide_vue"

    if nom_case not in belief_state["zone_brouillard"]:
        return "vide"

    return None  # brouillard : aucune information


def rendu_ascii_plateau_connu(belief_state: dict) -> str:
    camp = belief_state["camp"]
    lignes = []
    for rang in range(7, -1, -1):
        cases_rang = []
        for fichier in range(8):
            nom_case = chess.square_name(chess.square(fichier, rang))
            cellule = cellule_connue(belief_state, nom_case)
            if cellule is None:
                texte = "?"
            elif cellule in ("vide_vue", "vide"):
                texte = "."
            else:
                c_camp, type_p, _source = cellule
                texte = SYMBOLES[(c_camp, type_p)]
            cases_rang.append(texte.rjust(3))
        lignes.append(f"{rang + 1} " + " ".join(cases_rang))
    lignes.append("    " + "   ".join("abcdefgh"))
    return "\n".join(lignes)


def rendu_ascii_plateau_hypothese(belief_state: dict, hypothese: Optional[dict]) -> str:
    camp = belief_state["camp"]
    camp_adverse = "noir" if camp == "blanc" else "blanc"
    connues = belief_state["pieces_adverses_connues"]
    hypothese = hypothese or {}

    lignes = []
    for rang in range(7, -1, -1):
        cases_rang = []
        for fichier in range(8):
            nom_case = chess.square_name(chess.square(fichier, rang))
            if nom_case in belief_state["pieces_propres"]:
                texte = SYMBOLES[(camp, belief_state["pieces_propres"][nom_case])]
            elif nom_case in connues:
                texte = SYMBOLES[(camp_adverse, connues[nom_case]["type"])]
            elif nom_case in hypothese:
                texte = SYMBOLES[(camp_adverse, hypothese[nom_case])] + "?"
            else:
                texte = "."
            cases_rang.append(texte.rjust(3))
        lignes.append(f"{rang + 1} " + " ".join(cases_rang))
    lignes.append("    " + "   ".join("abcdefgh"))
    return "\n".join(lignes)
