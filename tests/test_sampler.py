import random

import chess

from engine.vision import SuiviCroyances, RANGEES_BROUILLARD
from engine.sampler import (
    echantillonner_plateaux, plateau_vers_dict,
    _cases_disponibles_brouillard, _pieces_adverses_restantes,
)


def _belief_apres_ouverture():
    """Position après 1.e4 Nf6 2.Nc3 : quelques pièces noires dans la
    zone de brouillard, certaines cachées, une vue directement."""
    board = chess.Board()
    for coup in ["e4", "Nf6", "Nc3"]:
        board.push_san(coup)
    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 3)
    return suivi.belief_state(board, 3), board


def test_cases_disponibles_excluent_connues_et_vues():
    belief, board = _belief_apres_ouverture()
    cases = _cases_disponibles_brouillard(belief)
    occupees_ou_vues = (
        set(chess.parse_square(n) for n in belief["pieces_propres"])
        | set(chess.parse_square(n) for n in belief["pieces_adverses_connues"])
        | set(chess.parse_square(n) for n in belief["champ_de_vision_actuel"])
    )
    assert not (set(cases) & occupees_ou_vues)


def test_plateaux_echantillonnes_respectent_inventaire():
    belief, board = _belief_apres_ouverture()
    rng = random.Random(42)
    plateaux = echantillonner_plateaux(belief, n=4, generateur_aleatoire=rng)
    assert len(plateaux) > 0

    restantes = _pieces_adverses_restantes(belief)
    for candidat in plateaux:
        camp_adverse = chess.BLACK
        # Chaque type de pièce adverse doit correspondre exactement au
        # total réel restant (connu + caché), jamais plus.
        for type_piece, total_attendu in belief["pieces_adverses_restantes_total"].items():
            from engine.sampler import NOM_VERS_TYPE
            pt = NOM_VERS_TYPE[type_piece]
            assert len(candidat.pieces(pt, camp_adverse)) == total_attendu


def test_pieces_cachees_placees_uniquement_en_zone_brouillard():
    belief, board = _belief_apres_ouverture()
    rng = random.Random(7)
    plateaux = echantillonner_plateaux(belief, n=3, generateur_aleatoire=rng)
    assert plateaux

    cases_connues = {chess.parse_square(n) for n in belief["pieces_adverses_connues"]}
    for candidat in plateaux:
        for sq, piece in candidat.piece_map().items():
            if piece.color == chess.BLACK and sq not in cases_connues:
                assert chess.square_rank(sq) in RANGEES_BROUILLARD, (
                    "une pièce cachée générée hors de la zone de brouillard"
                )


def test_plateau_echantillonne_ne_revele_pas_de_piece_cachee():
    from engine.sampler import _respecte_lignes_de_vue
    belief, board = _belief_apres_ouverture()
    rng = random.Random(123)
    camp = chess.WHITE
    plateaux = echantillonner_plateaux(belief, n=5, generateur_aleatoire=rng)
    cases_deja_revelees = {chess.parse_square(n) for n in belief["pieces_adverses_connues"]}
    for candidat in plateaux:
        assert _respecte_lignes_de_vue(candidat, camp, cases_deja_revelees)


def test_plateau_vers_dict_ne_contient_que_pieces_adverses():
    belief, board = _belief_apres_ouverture()
    rng = random.Random(1)
    plateaux = echantillonner_plateaux(belief, n=1, generateur_aleatoire=rng)
    assert plateaux
    d = plateau_vers_dict(plateaux[0], chess.WHITE)
    for nom_case in d:
        piece = plateaux[0].piece_at(chess.parse_square(nom_case))
        assert piece.color == chess.BLACK


def test_position_de_depart_aucune_piece_en_zone_donc_aucun_cache():
    """Au tout premier coup (avant tout mouvement), aucune pièce noire
    n'est dans la zone de brouillard : le sampler ne doit rien avoir à
    cacher."""
    board = chess.Board()
    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 1)
    belief = suivi.belief_state(board, 1)

    rng = random.Random(0)
    plateaux = echantillonner_plateaux(belief, n=3, generateur_aleatoire=rng)
    assert plateaux
    connues = set(belief["pieces_adverses_connues"])
    for candidat in plateaux:
        # Toutes les pièces adverses du plateau candidat doivent
        # correspondre exactement à celles déjà connues (hors zone,
        # donc toujours visibles) : rien n'est réellement caché ici.
        assert set(plateau_vers_dict(candidat, chess.WHITE)) == connues


def test_pas_de_pions_doubles_inventes_sans_capture():
    """Position où plusieurs pions noirs cachés doivent être placés
    dans la zone de brouillard : le sampler ne doit pas les entasser
    sur la même colonne alors que d'autres colonnes libres existent."""
    board = chess.Board()
    for coup in ["e4", "a5", "d4", "b5", "c4", "c5", "b4", "d5"]:
        board.push_san(coup)
    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 9)
    belief = suivi.belief_state(board, 9)

    rng = random.Random(99)
    plateaux = echantillonner_plateaux(belief, n=5, generateur_aleatoire=rng)
    assert plateaux

    for candidat in plateaux:
        fichiers = [chess.square_file(sq) for sq in candidat.pieces(chess.PAWN, chess.BLACK)]
        # Il y a largement assez de colonnes libres dans cette position
        # pour éviter tout doublon : aucun fichier ne doit être répété.
        assert len(fichiers) == len(set(fichiers)), f"pions doublés générés : {fichiers}"


def test_aucune_piece_capturee_ne_reapparait():
    """Après une capture réelle, le sampler ne doit jamais faire
    apparaître plus de pièces adverses d'un type que ce qu'il en
    reste réellement."""
    board = chess.Board()
    board.push_san("e4")
    board.push_san("d5")
    board.push(chess.Move.from_uci("e4d5"))  # Blanc capture un pion noir
    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 3)
    belief = suivi.belief_state(board, 3)

    assert belief["pieces_adverses_restantes_total"]["pion"] == 7

    rng = random.Random(5)
    plateaux = echantillonner_plateaux(belief, n=5, generateur_aleatoire=rng)
    assert plateaux
    for candidat in plateaux:
        assert len(candidat.pieces(chess.PAWN, chess.BLACK)) == 7
