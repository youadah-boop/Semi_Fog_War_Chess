import chess
import pytest

from engine.vision import (
    SuiviCroyances, zone_brouillard, hors_zone,
    SOURCE_HORS_ZONE, SOURCE_ECHEC, SOURCE_VOISINAGE_ROI, SOURCE_CLOUAGE, SOURCE_VISION_DIRECTE,
)


def test_zone_brouillard_est_rangees_3_a_6():
    zone = zone_brouillard()
    assert len(zone) == 32
    for sq in zone:
        assert chess.square_rank(sq) in (2, 3, 4, 5)
    assert chess.parse_square("e3") in zone
    assert chess.parse_square("e4") in zone
    assert chess.parse_square("e5") in zone
    assert chess.parse_square("e6") in zone
    assert chess.parse_square("e2") not in zone
    assert chess.parse_square("e7") not in zone


def test_piece_hors_zone_toujours_visible():
    # Une tour noire en h8 (hors zone) doit être visible même sans
    # aucune ligne de vue blanche dessus.
    board = chess.Board(None)
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
    board.set_piece_at(chess.H8, chess.Piece(chess.ROOK, chess.BLACK))
    board.turn = chess.WHITE

    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 1)
    belief = suivi.belief_state(board, 1)

    assert "h8" in belief["pieces_adverses_connues"]
    assert belief["pieces_adverses_connues"]["h8"]["source"] == SOURCE_HORS_ZONE


def test_piece_cachee_dans_zone_non_vue_reste_invisible():
    board = chess.Board(None)
    board.set_piece_at(chess.A1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.H8, chess.Piece(chess.KING, chess.BLACK))
    # cavalier noir en e5 (zone de brouillard), loin de tout, pas vu.
    board.set_piece_at(chess.E5, chess.Piece(chess.KNIGHT, chess.BLACK))
    board.turn = chess.WHITE

    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 1)
    belief = suivi.belief_state(board, 1)

    assert "e5" not in belief["pieces_adverses_connues"]


def test_piece_dans_zone_donnant_echec_est_revelee():
    board = chess.Board(None)
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.H8, chess.Piece(chess.KING, chess.BLACK))
    # Dame noire en e5 (zone brouillard) donnant échec au roi blanc en e1.
    board.set_piece_at(chess.E5, chess.Piece(chess.QUEEN, chess.BLACK))
    board.turn = chess.WHITE

    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 1)
    belief = suivi.belief_state(board, 1)

    assert "e5" in belief["pieces_adverses_connues"]
    assert belief["pieces_adverses_connues"]["e5"]["source"] == SOURCE_ECHEC
    assert belief["roi"]["en_echec"] is True


def test_revelation_ne_persiste_pas():
    board = chess.Board(None)
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.H8, chess.Piece(chess.KING, chess.BLACK))
    # Tour noire en e5 : donne échec au roi blanc (même colonne).
    board.set_piece_at(chess.E5, chess.Piece(chess.ROOK, chess.BLACK))
    board.turn = chess.WHITE

    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 1)
    belief = suivi.belief_state(board, 1)
    assert "e5" in belief["pieces_adverses_connues"]

    # La tour s'éloigne vers a5 : ni la même colonne ni la même rangée
    # que le roi (a5 ne touche ni le roi ni son voisinage) -> doit
    # redisparaître du brouillard.
    board.remove_piece_at(chess.E5)
    board.set_piece_at(chess.A5, chess.Piece(chess.ROOK, chess.BLACK))
    suivi.mettre_a_jour(board, 2)
    belief2 = suivi.belief_state(board, 2)
    assert "a5" not in belief2["pieces_adverses_connues"]


def test_piece_controlant_voisinage_du_roi_est_revelee():
    board = chess.Board(None)
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.H8, chess.Piece(chess.KING, chess.BLACK))
    # Tour noire en e5 contrôle e2 (case voisine du roi blanc e1), vide.
    board.set_piece_at(chess.E5, chess.Piece(chess.ROOK, chess.BLACK))
    board.turn = chess.WHITE

    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 1)
    belief = suivi.belief_state(board, 1)

    assert "e5" in belief["pieces_adverses_connues"]
    assert belief["pieces_adverses_connues"]["e5"]["source"] in (SOURCE_ECHEC, SOURCE_VOISINAGE_ROI)


def test_piece_clouante_est_revelee():
    board = chess.Board(None)
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.H8, chess.Piece(chess.KING, chess.BLACK))
    board.set_piece_at(chess.E3, chess.Piece(chess.ROOK, chess.WHITE))
    # Tour noire en e5 (zone brouillard) cloue la tour blanche en e3
    # contre le roi blanc en e1.
    board.set_piece_at(chess.E5, chess.Piece(chess.ROOK, chess.BLACK))
    board.turn = chess.WHITE

    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 1)
    belief = suivi.belief_state(board, 1)

    assert "e5" in belief["pieces_adverses_connues"]
    assert belief["pieces_adverses_connues"]["e5"]["source"] == SOURCE_CLOUAGE


def test_vision_directe_dans_zone():
    board = chess.Board()  # position de départ standard
    suivi = SuiviCroyances(chess.WHITE)
    suivi.mettre_a_jour(board, 1)
    belief = suivi.belief_state(board, 1)
    # Aucune pièce noire dans la zone de brouillard n'est encore
    # connue au coup 1 (les pièces hors zone, ex. la rangée 7, sont
    # toujours visibles et donc légitimement présentes).
    connues_en_zone = set(belief["pieces_adverses_connues"]) & set(belief["zone_brouillard"])
    assert connues_en_zone == set()

    board.push_san("e4")
    board.push_san("e5")
    suivi.mettre_a_jour(board, 2)
    belief2 = suivi.belief_state(board, 2)
    # Le pion noir e5 est dans la zone de brouillard, mais vu directement
    # par le pion blanc e4 (champ de vision façon Dark Chess).
    assert "e5" in belief2["pieces_adverses_connues"]
    assert belief2["pieces_adverses_connues"]["e5"]["source"] == SOURCE_VISION_DIRECTE
