"""
gui.py — Interface graphique Pygame de Semi Fog War Chess.

Disposition demandée (variante_battlechess.txt, section Affichage) :
- Fenêtre relativement large : plateau visible sous brouillard du
  joueur humain (Blancs).
- Fenêtre relativement moins large, à côté : plateau hypothétique des
  Blancs (le plus plausible, donné par le Sampler).
- Zone journal défilante, SITUÉE AU-DESSUS de la fenêtre du plateau
  hypothétique.

Le plateau réel n'est jamais dessiné. Le coup joué par Stockfish n'est
jamais annoncé en clair dans le journal (il porterait potentiellement
sur une case encore dans le brouillard pour les Blancs) — seul
"Tour à Stockfish ..." l'indique, comme demandé.
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
from typing import Optional

import chess
from engine.partie import Partie
from engine.rendu import GLYPHES, SYMBOLES, cellule_connue, nom_camp
from engine.vision import zone_brouillard
import pygame

sys.path.insert(0, os.path.dirname(__file__))

ZONE_BROUILLARD_CASES = zone_brouillard()


# ---------------------------------------------------------------------------
# Couleurs
# ---------------------------------------------------------------------------
FOND = (14, 16, 20)
CASE_CLAIRE = (86, 92, 104)
CASE_SOMBRE = (58, 62, 72)
CASE_VUE_VIDE = (
    46,
    58,
    52,
)  # légère teinte verte : case confirmée vide (hors zone)
CASE_ZONE_BROUILLARD = (
    40,
    110,
    62,
)  # vert fixe : toute case de la zone de brouillard,
# quel que soit son statut (occupée, vue, inconnue...)
ZONE_X_COULEUR = (
    24,
    64,
    38,
)  # "x" discret au centre des cases de la zone, couleur non vive
CASE_SELECTION = (198, 178, 84)
BLANC_PIECE = (245, 245, 245)
NOIR_PIECE_CONNU = (
    225,
    90,
    90,
)  # rouge : pièce adverse localisée (danger visible)
NOIR_PIECE_HYPO = (90, 150, 235)  # bleu : pièce hypothétique du Sampler
TEXTE = (225, 228, 232)
TEXTE_ATTENUE = (150, 155, 165)
PANNEAU_FOND = (20, 22, 27)
BORDURE = (70, 74, 84)

PROMOTION_LETTRES = ["q", "r", "b", "n"]
PROMOTION_NOMS = {"q": "dame", "r": "tour", "b": "fou", "n": "cavalier"}


def parser_coup(board: chess.Board, texte: str) -> Optional[str]:
  texte = texte.strip()
  if not texte:
    return None
  try:
    return board.parse_san(texte).uci()
  except ValueError:
    pass
  try:
    chess.Move.from_uci(texte)
    return texte
  except ValueError:
    return None


class SemiFogGUI:

  def __init__(self):
    pygame.init()
    pygame.display.set_caption("Semi Fog War Chess")
    self.screen = pygame.display.set_mode((1000, 740), pygame.RESIZABLE)

    # Force la fenêtre au premier plan au démarrage (certains OS/gestionnaires
    # de fenêtres ne donnent pas le focus automatiquement à une fenêtre SDL).
    pygame.display.set_caption("Semi Fog War Chess")

    wm_info = pygame.display.get_wm_info()["window"]
    ctypes.windll.user32.SetWindowPos(wm_info, -1, 0, 0, 0, 0, 0x0001 | 0x0002)

    self.clock = pygame.time.Clock()

    self.partie = Partie()

    self.log_lines: list[str] = []
    self.log_scroll = 0

    self.input_text = ""
    self.input_active = True
    self.selected_square: Optional[int] = None
    self.pending_promotion: Optional[dict] = None  # {"uci_base": "e7e8"}

    self.ai_busy = False
    self.ai_queue: queue.Queue[dict] = queue.Queue()

    self.font = pygame.font.Font(None, 24)
    self.small_font = pygame.font.Font(None, 20)
    self.title_font = pygame.font.Font(None, 30)
    self.coord_font = pygame.font.Font(None, 16)
    self._font_cache: dict[int, pygame.font.Font] = {}

    self.running = True

    self._log("=== Semi Fog War Chess ===")
    self._log("Blanc humain contre Noir (Stockfish).")
    self._log("Zone de brouillard en vert")
    self._log("Cliquez une pièce blanche puis sa destination,")
    self._log("ou saisissez un coup SAN/UCI puis Entrée.")
    self._log("")

    self._commencer_tour()

  # ------------------------------------------------------------------
  # Journal
  # ------------------------------------------------------------------
  def _log(self, ligne: str) -> None:
    self.log_lines.append(ligne)
    self.log_scroll = 0  # revient en bas à chaque nouvelle ligne

  # ------------------------------------------------------------------
  # Enchaînement des tours
  # ------------------------------------------------------------------
  def _commencer_tour(self) -> None:
    if self.partie.partie_terminee():
      return

    if self.partie.arbitre.camp_au_trait == chess.WHITE:
      self._log("Tour aux Blancs")
    else:
      self._log("Tour à Stockfish ...")
      self._lancer_ia_async()

  @staticmethod
  def _message_fin(etat: str) -> str:
    return {
        "echec_et_mat_blanc_gagne": "Echec et mat — les Blancs gagnent",
        "echec_et_mat_noir_gagne": "Echec et mat — les Noirs gagnent",
        "pat": "Pat",
        "nulle_materiel_insuffisant": "Nulle par manque de force",
        "nulle_repetition": "Nulle par répétition",
        "nulle_50_coups": "Nulle par 50-coups",
    }.get(etat, "Partie terminée")

  def _lancer_ia_async(self) -> None:
    self.ai_busy = True
    threading.Thread(target=self._travail_ia, daemon=True).start()

  def _travail_ia(self) -> None:
    resultat = self.partie.jouer_coup_ia()
    self.ai_queue.put(resultat)

  def _poll_ia(self) -> None:
    try:
      resultat = self.ai_queue.get_nowait()
    except queue.Empty:
      return
    self.ai_busy = False
    for ligne in resultat["lignes"]:
      self._log(ligne)
    self._commencer_tour()

  def _soumettre_coup_humain(self, uci: str) -> None:
    if self.ai_busy or self.partie.partie_terminee():
      return
    if self.partie.arbitre.camp_au_trait != chess.WHITE:
      return
    resultat = self.partie.jouer_coup_humain(uci)
    for ligne in resultat["lignes"]:
      self._log(ligne)
    self.selected_square = None
    self.input_text = ""
    self._commencer_tour()

  def _est_coup_promotion(self, uci_base: str) -> bool:
    if len(uci_base) != 4:
      return False
    try:
      depart = chess.parse_square(uci_base[:2])
      arrivee = chess.parse_square(uci_base[2:4])
    except ValueError:
      return False
    piece = self.partie.arbitre.plateau_reel.piece_at(depart)
    return (
        piece is not None
        and piece.piece_type == chess.PAWN
        and piece.color == chess.WHITE
        and chess.square_rank(arrivee) == 7
    )

  # ------------------------------------------------------------------
  # Disposition & Bouton Fermer
  # ------------------------------------------------------------------
  def _close_button_rect(self) -> pygame.Rect:
    """Retourne le rectangle du bouton X dans le coin supérieur droit."""
    return pygame.Rect(self.screen.get_width() - 34, 10, 24, 24)

  def _layout(self) -> dict:
    w, h = self.screen.get_size()
    marge = 16
    header_h = 46
    input_h = 44

    board_area_w = int(w * 0.60)
    board_size = min(
        board_area_w - 2 * marge, h - header_h - input_h - 2 * marge
    )
    board_rect = pygame.Rect(marge, header_h + marge, board_size, board_size)

    right_x = board_rect.right + marge
    right_w = w - right_x - marge
    right_top = header_h + marge
    right_bottom = h - input_h - marge

    hypo_size = min(right_w, int((right_bottom - right_top) * 0.42))
    hypo_rect = pygame.Rect(
        right_x, right_bottom - hypo_size, hypo_size, hypo_size
    )

    log_rect = pygame.Rect(
        right_x, right_top, right_w, hypo_rect.top - right_top - marge
    )

    input_rect = pygame.Rect(marge, h - input_h, w - 2 * marge, input_h - 8)

    return {
        "board": board_rect,
        "log": log_rect,
        "hypo": hypo_rect,
        "input": input_rect,
    }

  def _police_case(self, taille: int) -> pygame.font.Font:
    if taille not in self._font_cache:
      try:
        self._font_cache[taille] = pygame.font.SysFont("dejavusans", taille)
      except Exception:
        self._font_cache[taille] = pygame.font.Font(None, taille)
    return self._font_cache[taille]

  # ------------------------------------------------------------------
  # Dessin : en-tête & Bouton de fermeture
  # ------------------------------------------------------------------
  def _draw_header(self) -> None:
    titre = self.title_font.render("SEMI FOG WAR CHESS", True, TEXTE)
    self.screen.blit(titre, (18, 10))

    # --- Bouton de fermeture 'X' ---
    btn_rect = self._close_button_rect()
    pos_souris = pygame.mouse.get_pos()
    couleur_btn = (
        (220, 50, 50) if btn_rect.collidepoint(pos_souris) else (160, 40, 40)
    )
    pygame.draw.rect(self.screen, couleur_btn, btn_rect, border_radius=4)

    # Croix
    pad = 6
    epaisseur = 2
    pygame.draw.line(
        self.screen,
        (255, 255, 255),
        (btn_rect.left + pad, btn_rect.top + pad),
        (btn_rect.right - pad, btn_rect.bottom - pad),
        epaisseur,
    )
    pygame.draw.line(
        self.screen,
        (255, 255, 255),
        (btn_rect.left + pad, btn_rect.bottom - pad),
        (btn_rect.right - pad, btn_rect.top - pad),
        epaisseur,
    )

    # --- Statut de la partie ---
    if self.ai_busy:
      statut = "NOIR : Stockfish réfléchit..."
    elif self.partie.partie_terminee():
      statut = "PARTIE TERMINÉE"
    elif self.partie.arbitre.camp_au_trait == chess.WHITE:
      statut = "BLANC : à vous de jouer"
    else:
      statut = "NOIR"
    surf = self.small_font.render(statut, True, TEXTE_ATTENUE)
    # Positionné juste à gauche du bouton 'X'
    self.screen.blit(surf, (btn_rect.left - surf.get_width() - 16, 18))

  # ------------------------------------------------------------------
  # Dessin : plateau brouillé (visible du joueur)
  # ------------------------------------------------------------------
  def _square_from_mouse(self, pos, rect) -> Optional[int]:
    if not rect.collidepoint(pos):
      return None
    taille_case = rect.width / 8
    col = int((pos[0] - rect.x) / taille_case)
    rang_ecran = int((pos[1] - rect.y) / taille_case)
    if not (0 <= col < 8 and 0 <= rang_ecran < 8):
      return None
    rang = 7 - rang_ecran
    return chess.square(col, rang)

  def _draw_board_large(self, rect: pygame.Rect) -> None:
    pygame.draw.rect(self.screen, PANNEAU_FOND, rect, border_radius=6)
    taille_case = rect.width / 8
    belief = self.partie.belief_state(chess.WHITE)
    piece_font = self._police_case(int(taille_case * 0.62))
    x_font = self._police_case(int(taille_case * 0.4))

    for rang_ecran in range(8):
      rang = 7 - rang_ecran
      for fichier in range(8):
        square = chess.square(fichier, rang)
        nom_case = chess.square_name(square)
        cell_rect = pygame.Rect(
            rect.x + fichier * taille_case,
            rect.y + rang_ecran * taille_case,
            taille_case,
            taille_case,
        )

        cellule = cellule_connue(belief, nom_case)
        en_zone = square in ZONE_BROUILLARD_CASES
        claire = (fichier + rang) % 2 == 1

        if en_zone:
          couleur = CASE_ZONE_BROUILLARD
        elif cellule == "vide_vue":
          couleur = CASE_VUE_VIDE
        else:
          couleur = CASE_CLAIRE if claire else CASE_SOMBRE
        pygame.draw.rect(self.screen, couleur, cell_rect)

        if square == self.selected_square:
          pygame.draw.rect(self.screen, CASE_SELECTION, cell_rect, 3)

        if en_zone:
          x_surf = x_font.render("x", True, ZONE_X_COULEUR)
          self.screen.blit(x_surf, x_surf.get_rect(center=cell_rect.center))

        if isinstance(cellule, tuple):
          camp_piece, type_piece, source = cellule
          glyph = GLYPHES[(camp_piece, type_piece)]
          couleur_piece = (
              BLANC_PIECE if camp_piece == "blanc" else NOIR_PIECE_CONNU
          )
          surf = piece_font.render(glyph, True, couleur_piece)
          self.screen.blit(surf, surf.get_rect(center=cell_rect.center))
          if camp_piece == "noir":
            pygame.draw.circle(
                self.screen,
                NOIR_PIECE_CONNU,
                (cell_rect.right - 6, cell_rect.top + 6),
                4,
            )

        if fichier == 0:
          lbl = self.coord_font.render(str(rang + 1), True, TEXTE_ATTENUE)
          self.screen.blit(lbl, (cell_rect.x + 2, cell_rect.y + 2))
        if rang_ecran == 7:
          lbl = self.coord_font.render(
              "abcdefgh"[fichier], True, TEXTE_ATTENUE
          )
          self.screen.blit(lbl, (cell_rect.right - 12, cell_rect.bottom - 14))

    pygame.draw.rect(self.screen, BORDURE, rect, 2, border_radius=6)

  # ------------------------------------------------------------------
  # Dessin : plateau hypothétique (petite fenêtre)
  # ------------------------------------------------------------------
  def _draw_hypo_board(self, rect: pygame.Rect) -> None:
    pygame.draw.rect(self.screen, PANNEAU_FOND, rect, border_radius=6)
    titre = self.small_font.render(
        "Plateau plausible (Blancs)", True, TEXTE_ATTENUE
    )
    self.screen.blit(titre, (rect.x, rect.y - 20))

    belief = self.partie.belief_state(chess.WHITE)
    hypothese = self.partie.hypothese_dict(chess.WHITE) or {}
    taille_case = rect.width / 8
    piece_font = self._police_case(int(taille_case * 0.6))
    x_font = self._police_case(int(taille_case * 0.4))

    connues = belief["pieces_adverses_connues"]
    propres = belief["pieces_propres"]

    for rang_ecran in range(8):
      rang = 7 - rang_ecran
      for fichier in range(8):
        square = chess.square(fichier, rang)
        nom_case = chess.square_name(square)
        cell_rect = pygame.Rect(
            rect.x + fichier * taille_case,
            rect.y + rang_ecran * taille_case,
            taille_case,
            taille_case,
        )
        en_zone = square in ZONE_BROUILLARD_CASES
        claire = (fichier + rang) % 2 == 1
        couleur = (
            CASE_ZONE_BROUILLARD
            if en_zone
            else (CASE_CLAIRE if claire else CASE_SOMBRE)
        )
        pygame.draw.rect(self.screen, couleur, cell_rect)
        if en_zone:
          x_surf = x_font.render("x", True, ZONE_X_COULEUR)
          self.screen.blit(x_surf, x_surf.get_rect(center=cell_rect.center))

        camp_piece = None
        type_piece = None
        hypo = False
        if nom_case in propres:
          camp_piece, type_piece = "blanc", propres[nom_case]
        elif nom_case in connues:
          camp_piece, type_piece = "noir", connues[nom_case]["type"]
        elif nom_case in hypothese:
          camp_piece, type_piece, hypo = "noir", hypothese[nom_case], True

        if camp_piece is not None:
          glyph = GLYPHES[(camp_piece, type_piece)]
          if camp_piece == "blanc":
            couleur = BLANC_PIECE
          elif hypo:
            couleur = NOIR_PIECE_HYPO
          else:
            couleur = NOIR_PIECE_CONNU
          surf = piece_font.render(glyph, True, couleur)
          self.screen.blit(surf, surf.get_rect(center=cell_rect.center))
          if hypo:
            q = self.coord_font.render("?", True, NOIR_PIECE_HYPO)
            self.screen.blit(
                q, (cell_rect.right - q.get_width() - 1, cell_rect.top + 1)
            )

    pygame.draw.rect(self.screen, BORDURE, rect, 2, border_radius=6)

  # ------------------------------------------------------------------
  # Dessin : journal défilant
  # ------------------------------------------------------------------
  def _draw_log(self, rect: pygame.Rect) -> None:
    pygame.draw.rect(self.screen, PANNEAU_FOND, rect, border_radius=6)
    pygame.draw.rect(self.screen, BORDURE, rect, 2, border_radius=6)

    titre = self.small_font.render("Journal", True, TEXTE_ATTENUE)
    self.screen.blit(titre, (rect.x + 10, rect.y + 6))

    clip = self.screen.get_clip()
    interieur = rect.inflate(-16, -34)
    interieur.y = rect.y + 28
    interieur.height = rect.height - 34
    self.screen.set_clip(interieur)

    ligne_h = 22
    lignes_visibles = interieur.height // ligne_h
    total = len(self.log_lines)
    self.log_scroll = max(
        0, min(self.log_scroll, max(0, total - lignes_visibles))
    )
    depart = max(0, total - lignes_visibles - self.log_scroll)
    fin = total - self.log_scroll

    y = interieur.y
    for ligne in self.log_lines[depart:fin]:
      surf = self.font.render(ligne, True, TEXTE)
      self.screen.blit(surf, (interieur.x, y))
      y += ligne_h

    self.screen.set_clip(clip)

  # ------------------------------------------------------------------
  # Dessin : champ de saisie
  # ------------------------------------------------------------------
  def _draw_input(self, rect: pygame.Rect) -> None:
    bordure = (100, 130, 160) if self.input_active else BORDURE
    pygame.draw.rect(self.screen, (18, 20, 24), rect, border_radius=6)
    pygame.draw.rect(self.screen, bordure, rect, 2, border_radius=6)

    prefixe = "Coup Blanc > "
    p_surf = self.font.render(prefixe, True, TEXTE_ATTENUE)
    self.screen.blit(p_surf, (rect.x + 10, rect.y + 8))
    t_surf = self.font.render(self.input_text, True, TEXTE)
    self.screen.blit(t_surf, (rect.x + 10 + p_surf.get_width(), rect.y + 8))

  def _promotion_menu_rects(
      self, board_rect: pygame.Rect
  ) -> dict[str, pygame.Rect]:
    taille = min(90, board_rect.width // 5)
    total_w = taille * 4 + 30
    x0 = board_rect.centerx - total_w // 2
    y0 = board_rect.centery - taille // 2
    rects = {}
    for i, lettre in enumerate(PROMOTION_LETTRES):
      rects[lettre] = pygame.Rect(x0 + i * (taille + 10), y0, taille, taille)
    return rects

  def _draw_promotion_menu(self, board_rect: pygame.Rect) -> None:
    overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 165))
    self.screen.blit(overlay, (0, 0))

    label = self.font.render("Promotion — choisissez une pièce", True, TEXTE)
    self.screen.blit(
        label,
        label.get_rect(center=(board_rect.centerx, board_rect.centery - 70)),
    )

    rects = self._promotion_menu_rects(board_rect)
    piece_font = self._police_case(int(min(90, board_rect.width // 5) * 0.7))
    for lettre, rect in rects.items():
      pygame.draw.rect(self.screen, PANNEAU_FOND, rect, border_radius=8)
      pygame.draw.rect(self.screen, CASE_SELECTION, rect, 2, border_radius=8)
      glyph = GLYPHES[("blanc", PROMOTION_NOMS[lettre])]
      surf = piece_font.render(glyph, True, BLANC_PIECE)
      self.screen.blit(surf, surf.get_rect(center=rect.center))
      nom_surf = self.coord_font.render(
          PROMOTION_NOMS[lettre], True, TEXTE_ATTENUE
      )
      self.screen.blit(
          nom_surf, nom_surf.get_rect(midtop=(rect.centerx, rect.bottom + 4))
      )

  def draw(self) -> None:
    self.screen.fill(FOND)
    layout = self._layout()
    self._draw_header()
    self._draw_board_large(layout["board"])
    self._draw_log(layout["log"])
    self._draw_hypo_board(layout["hypo"])
    self._draw_input(layout["input"])
    if self.pending_promotion is not None:
      self._draw_promotion_menu(layout["board"])
    pygame.display.flip()

  # ------------------------------------------------------------------
  # Événements
  # ------------------------------------------------------------------
  def _handle_board_click(self, pos, rect) -> None:
    if self.ai_busy or self.partie.partie_terminee():
      return
    if self.partie.arbitre.camp_au_trait != chess.WHITE:
      return
    square = self._square_from_mouse(pos, rect)
    if square is None:
      return
    piece = self.partie.arbitre.plateau_reel.piece_at(square)

    if self.selected_square is None:
      if piece is not None and piece.color == chess.WHITE:
        self.selected_square = square
      return

    if square == self.selected_square:
      self.selected_square = None
      return

    depart, arrivee = self.selected_square, square
    self.selected_square = None
    uci_base = chess.square_name(depart) + chess.square_name(arrivee)
    if self._est_coup_promotion(uci_base):
      self.pending_promotion = {"uci_base": uci_base}
      return
    self._soumettre_coup_humain(uci_base)

  def _handle_event(self, event) -> None:
    if event.type == pygame.QUIT:
      self.running = False
      return
    if event.type == pygame.VIDEORESIZE:
      self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
      return
    if event.type == pygame.MOUSEWHEEL:
      layout = self._layout()
      if layout["log"].collidepoint(pygame.mouse.get_pos()):
        self.log_scroll += event.y * 3
      return
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
      # Verification du clic sur le bouton 'X' personnalisé
      if self._close_button_rect().collidepoint(event.pos):
        self.running = False
        return

      layout = self._layout()
      if self.pending_promotion is not None:
        rects = self._promotion_menu_rects(layout["board"])
        for lettre, rect in rects.items():
          if rect.collidepoint(event.pos):
            uci = self.pending_promotion["uci_base"] + lettre
            self.pending_promotion = None
            self._soumettre_coup_humain(uci)
            break
        return
      if layout["board"].collidepoint(event.pos):
        self._handle_board_click(event.pos, layout["board"])
        return
      self.input_active = layout["input"].collidepoint(event.pos)
      return
    if event.type == pygame.KEYDOWN:
      if self.pending_promotion is not None:
        if event.key == pygame.K_ESCAPE:
          self.pending_promotion = None
        return
      if not self.input_active or self.ai_busy:
        return
      if event.key == pygame.K_RETURN:
        board = self.partie.arbitre.plateau_reel
        uci = parser_coup(board, self.input_text)
        if uci is not None and self._est_coup_promotion(uci):
          self.pending_promotion = {"uci_base": uci}
          self.input_text = ""
          return
        self._soumettre_coup_humain(uci if uci else "0000")
        return
      if event.key == pygame.K_BACKSPACE:
        self.input_text = self.input_text[:-1]
        return
      if event.key == pygame.K_ESCAPE:
        self.input_text = ""
        self.selected_square = None
        return
      if len(self.input_text) < 24 and event.unicode.isprintable():
        self.input_text += event.unicode

  def run(self) -> None:
    while self.running:
      for event in pygame.event.get():
        self._handle_event(event)
      self._poll_ia()
      self.draw()
      self.clock.tick(60)
    pygame.quit()


def main():
  SemiFogGUI().run()


if __name__ == "__main__":
  main()
