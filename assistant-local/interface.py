"""Interface console « Black Jack » : tapis vert sombre, cartes et animations.

Fonctionne dans le cmd de Windows 10/11 (couleurs ANSI 24 bits).
Mets la variable d'environnement BJ_SANS_ANIMATION=1 pour couper les animations.
"""
import colorsys
import functools
import math
import os
import random
import re
import shutil
import sys
import threading
import time

ANIMATIONS = os.environ.get("BJ_SANS_ANIMATION") != "1" and sys.stdout.isatty()

# Réglages modifiables via le mode Paramètres (voir appliquer_params).
PLUIE_DENSITE = 0.8        # fraction de colonnes de pluie actives (0 = aucune, 1 = toutes)
PLUIE_VITESSE = 1.0        # multiplicateur de vitesse de la pluie
TITRE_CYCLE = True         # True = le titre cycle l'arc-en-ciel, False = couleur fixe
SON = True                 # bips de validation
CRT = True                 # effet scanlines / vieil écran
MENU_ANIME = True          # fond animé du menu (pluie Matrix + titre arc-en-ciel) ; coupe-le dans Paramètres [14] si ça scintille


def appliquer_params(animations=None, densite=None, vitesse=None, cycle=None,
                     son=None, crt=None, menu_anime=None):
    """Applique les réglages du mode Paramètres (à chaud)."""
    global ANIMATIONS, PLUIE_DENSITE, PLUIE_VITESSE, TITRE_CYCLE, SON, CRT, MENU_ANIME
    if menu_anime is not None:
        MENU_ANIME = bool(menu_anime)
    if animations is not None:
        ANIMATIONS = (bool(animations) and sys.stdout.isatty()
                      and os.environ.get("BJ_SANS_ANIMATION") != "1")
    if densite is not None:
        PLUIE_DENSITE = max(0.0, min(1.0, densite))
    if vitesse is not None:
        PLUIE_VITESSE = max(0.3, min(3.0, vitesse))
    if cycle is not None:
        TITRE_CYCLE = bool(cycle)
    if son is not None:
        SON = bool(son)
    if crt is not None:
        CRT = bool(crt)


def _bip(sequence=((880, 90), (1245, 130))):
    """Court signal sonore (Windows : winsound ; sinon cloche du terminal)."""
    if not SON:
        return
    try:
        import winsound
        for freq, duree in sequence:
            winsound.Beep(freq, duree)
    except Exception:
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass


# ---------- Couleurs ----------

@functools.lru_cache(maxsize=16384)
def _txt(r, g, b):
    return f"\x1b[38;2;{r};{g};{b}m"


@functools.lru_cache(maxsize=16384)
def _fond(r, g, b):
    return f"\x1b[48;2;{r};{g};{b}m"


RESET = "\x1b[0m"
GRAS = "\x1b[1m"
# ----- Thème « dark / hacker » : fond quasi-noir, néons -----
FOND = _fond(6, 8, 12)             # noir profond légèrement bleuté
TEXTE = _txt(150, 205, 185)        # cyan-vert doux (lisible)
DISCRET = _txt(78, 120, 110)       # gris-vert éteint
VERT = _txt(50, 255, 130)          # vert néon « matrix »
OR = _txt(235, 185, 70)            # ambre
ROUGE = _txt(255, 70, 80)          # rouge néon
BLANC = _txt(235, 245, 240)
NOIR = _txt(10, 12, 16)
CYAN = _txt(60, 230, 230)          # cyan néon
MAGENTA = _txt(230, 90, 205)       # magenta néon
FOND_CARTE = _fond(238, 240, 235)
DOS_CARTE = _fond(120, 20, 40)
BASE = RESET + FOND + TEXTE        # style « normal »

# Mise à jour SYNCHRONISÉE (DEC mode 2026) : le terminal met en tampon tout ce qui
# arrive entre DÉBUT et FIN et affiche l'image d'UN SEUL COUP → aucune déchirure
# (indispensable sur Windows Terminal pour les animations plein écran). Les
# terminaux qui ne la gèrent pas ignorent simplement ces séquences.
_SYNC_DEBUT = "\x1b[?2026h"
_SYNC_FIN = "\x1b[?2026l"

ENSEIGNES = [("♠", NOIR), ("♥", ROUGE), ("♦", ROUGE), ("♣", NOIR)]


def _ecrire(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def _pause(secondes):
    if ANIMATIONS:
        time.sleep(secondes)


def _dim():
    """Taille RÉELLE du terminal (ignore les variables COLUMNS/LINES figées,
    pour voir les agrandissements de fenêtre en direct)."""
    try:
        s = os.get_terminal_size(sys.stdout.fileno())
        return s.columns, s.lines
    except Exception:
        try:
            s = shutil.get_terminal_size((100, 30))
            return s.columns, s.lines
        except Exception:
            return 100, 30


class _Taille:
    """Petit objet .columns/.lines (compatibilité avec le code existant)."""
    def __init__(self):
        self.columns, self.lines = _dim()


def largeur():
    return _dim()[0]


def effacer():
    """Efface l'écran et remet le curseur en haut."""
    _ecrire(BASE + "\x1b[2J\x1b[H")


def _conhost_classique():
    """Vrai ? → console Windows héritée « nue » (conhost), où l'on peut régler la
    taille du buffer sans risque. Faux pour Windows Terminal / VS Code / autres :
    là, toucher au buffer DÉSYNCHRONISE la taille réelle et casse l'affichage."""
    if os.name != "nt":
        return False
    for v in ("WT_SESSION", "WT_PROFILE_ID", "TERM_PROGRAM",
              "VSCODE_INJECTION", "VSCODE_PID", "ConEmuPID"):
        if os.environ.get(v):
            return False
    return True


def _agrandir_conhost():
    """conhost SEULEMENT : buffer ET fenêtre à la taille max de l'écran (sûr ici,
    car on règle les deux ensemble → pas de désynchronisation)."""
    import ctypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32

    class _COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class _RECT(ctypes.Structure):
        _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                    ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

    hout = k32.GetStdHandle(-11)
    k32.GetLargestConsoleWindowSize.restype = _COORD
    maxs = k32.GetLargestConsoleWindowSize(hout)
    if maxs.X < 10 or maxs.Y < 5:                    # valeurs douteuses → on ne touche à rien
        return
    cols = min(maxs.X - 1, 400)
    lines = min(maxs.Y - 1, 160)
    k32.SetConsoleScreenBufferSize(hout, _COORD(cols, lines))
    k32.SetConsoleWindowInfo(hout, True, ctypes.byref(_RECT(0, 0, cols - 1, lines - 1)))
    hwnd = k32.GetConsoleWindow()
    if hwnd:
        u32.ShowWindow(hwnd, 3)                      # SW_MAXIMIZE


def agrandir_fenetre():
    """Agrandit la fenêtre SANS JAMAIS casser l'affichage, puis le programme
    S'ADAPTE à la taille qu'il obtient (il remplit l'espace disponible, sur
    n'importe quel écran). On ne force la taille QUE sur une console conhost nue ;
    sur Windows Terminal / VS Code / autres, on demande juste la maximisation
    (inoffensive) et on s'adapte — pour remplir, il suffit de maximiser la fenêtre."""
    if _conhost_classique():                        # conhost nu → remplissage sûr
        try:
            _agrandir_conhost()
        except Exception:
            pass
    elif os.name == "nt":                           # WT & co : maximisation douce, sans buffer
        try:
            import ctypes
            h = ctypes.windll.kernel32.GetConsoleWindow()
            if h:
                ctypes.windll.user32.ShowWindow(h, 3)
        except Exception:
            pass
    try:
        _ecrire("\x1b[9;1t")                         # maximise (WT / xterm), ignoré ailleurs
        time.sleep(0.12)                            # laisse la fenêtre s'ajuster avant de lire la taille
    except Exception:
        pass


def initialiser():
    """Active les couleurs et bascule sur un ÉCRAN ALTERNATIF (comme vim/htop) :
    pas d'historique de défilement, donc pas de doublons ni d'intro « scrollable »."""
    if os.name == "nt":
        os.system("")  # active le mode ANSI de la console Windows
    agrandir_fenetre()                          # on ouvre la fenêtre en grand
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _ecrire("\x1b[?1049h")            # écran alternatif
    # coupe tout rapport de souris/molette et le collage encadré : en écran
    # alternatif, la molette enverrait sinon des séquences qui polluent la saisie.
    _ecrire("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l\x1b[?2004l")
    _ecrire(BASE + "\x1b[2J\x1b[H")


def restaurer():
    """Revient à l'écran normal du terminal (fin propre, sans logos résiduels)."""
    _ecrire("\x1b[?25h")             # réaffiche le curseur
    _ecrire("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l\x1b[?2004l")
    _ecrire(BASE + "\x1b[2J\x1b[H")
    _ecrire("\x1b[?1049l")           # quitte l'écran alternatif
    _ecrire(RESET)


# ---------- Cartes ----------

def carte(valeur, enseigne, cachee=False):
    """Renvoie les 5 lignes d'une carte (7 colonnes de large)."""
    if cachee:
        motif = DOS_CARTE + OR
        return [motif + l + BASE for l in
                ["┌─────┐", "│░▒░▒░│", "│▒ ♠ ▒│", "│░▒░▒░│", "└─────┘"]]
    couleur = dict(ENSEIGNES)[enseigne]
    v = valeur.ljust(2)
    lignes = ["┌─────┐", f"│{v}   │", f"│  {enseigne}  │", f"│   {valeur.rjust(2)}│", "└─────┘"]
    return [FOND_CARTE + couleur + GRAS + l + BASE for l in lignes]


def _dessiner_main(posees, marge, mobile=None, ecart=1, redessiner=True):
    """Dessine les cartes posées, puis éventuellement une carte en mouvement à `ecart` espaces."""
    if redessiner:
        _ecrire("\x1b[5A")
    for i in range(5):
        ligne = " " * marge + " ".join(c[i] for c in posees)
        if mobile:
            ligne += " " * ecart + mobile[i]
        _ecrire("\r" + BASE + "\x1b[K" + ligne + "\n")


def distribuer(main):
    """Anime la distribution d'une main : chaque carte glisse depuis la droite puis se retourne.

    main : liste de (valeur, enseigne).
    """
    centre = max((largeur() - len(main) * 8) // 2, 0)
    dos = carte("", "", cachee=True)
    posees = []
    _dessiner_main([], centre, redessiner=False)
    for valeur, enseigne in main:
        ecart_min = 1 if posees else 0
        if ANIMATIONS:
            depart = max(largeur() - 9 - centre - len(posees) * 8, ecart_min)
            for ecart in range(depart, ecart_min, -3):
                _dessiner_main(posees, centre, dos, ecart)
                time.sleep(0.012)
        _dessiner_main(posees, centre, dos, ecart_min)
        _pause(0.15)
        posees.append(carte(valeur, enseigne))  # la carte se retourne
        _dessiner_main(posees, centre)
        _pause(0.2)


# ---------- Logo glacé (image rendue en demi-blocs ▀) ----------
# Chaque caractère ▀ = 2 pixels (couleur du haut en avant-plan, couleur du bas
# en fond). On obtient quasiment la finesse d'une image, tout en restant terminal.

BG_RGB = (6, 8, 12)


def _charger_logo():
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_glace.rgb")
    try:
        with open(chemin, "rb") as fp:
            data = fp.read()
    except OSError:
        return 0, 0, [], []
    cols = int.from_bytes(data[0:2], "big")
    hpx = int.from_bytes(data[2:4], "big")
    pix = data[4:]
    grille = [[tuple(pix[(y * cols + x) * 3:(y * cols + x) * 3 + 3]) for x in range(cols)]
              for y in range(hpx)]

    def encre(c):
        return abs(c[0] - BG_RGB[0]) + abs(c[1] - BG_RGB[1]) + abs(c[2] - BG_RGB[2]) > 45
    masque = [[encre(grille[y][x]) for x in range(cols)] for y in range(hpx)]
    return cols, hpx, grille, masque


LOGO_COLS, LOGO_HPX, LOGO, LOGO_MASQUE = _charger_logo()
LOGO_ROWS = LOGO_HPX // 2


def _centrer(texte, visible=None):
    n = len(texte) if visible is None else visible
    return " " * max((largeur() - n) // 2, 0) + texte


def _marge_logo():
    return max((largeur() - LOGO_COLS) // 2, 0)


def _ajuste(c, fac, x=None, reflet=None, rayon=4):
    """Luminosité (fac) + reflet quasi blanc autour de la colonne `reflet`."""
    r, g, b = c
    if reflet is not None and x is not None:
        d = abs(x - reflet)
        if d <= rayon:
            boost = 1.0 + 0.9 * (1 - d / (rayon + 1))
            r, g, b = r * boost + 35, g * boost + 35, b * boost + 35
    return (min(int(r * fac), 255), min(int(g * fac), 255), min(int(b * fac), 255))


def _lignes_logo(fac=1.0, reflet=None, rayon=4):
    """Le logo en lignes de demi-blocs, prêtes à imprimer."""
    lignes = []
    for cr in range(LOGO_ROWS):
        buf, cfg, cbg = [], None, None
        for x in range(LOGO_COLS):
            fg = _txt(*_ajuste(LOGO[2 * cr][x], fac, x, reflet, rayon))
            bg = _fond(*_ajuste(LOGO[2 * cr + 1][x], fac, x, reflet, rayon))
            if fg != cfg:
                buf.append(fg); cfg = fg
            if bg != cbg:
                buf.append(bg); cbg = bg
            buf.append("▀")
        lignes.append("".join(buf) + BASE)
    return lignes


def _teinte(c, deg):
    """Fait tourner la teinte d'une couleur (pour le titre néon arc-en-ciel)."""
    if deg % 360 == 0:
        return c
    h, l, s = colorsys.rgb_to_hls(c[0] / 255, c[1] / 255, c[2] / 255)
    h = (h + (deg % 360) / 360.0) % 1.0
    s = min(1.0, s * 1.25 + 0.15)          # pousse la saturation → néon
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (int(r * 255), int(g * 255), int(b * 255))


def _lignes_logo_teinte(deg):
    """Le logo entier avec la teinte décalée de `deg` degrés."""
    lignes = []
    for cr in range(LOGO_ROWS):
        buf, cfg, cbg = [], None, None
        for x in range(LOGO_COLS):
            fg = _txt(*_teinte(LOGO[2 * cr][x], deg))
            bg = _fond(*_teinte(LOGO[2 * cr + 1][x], deg))
            if fg != cfg:
                buf.append(fg); cfg = fg
            if bg != cbg:
                buf.append(bg); cbg = bg
            buf.append("▀")
        lignes.append("".join(buf) + BASE)
    return lignes


def _cells_logo_teinte(deg):
    """Le logo en CELLULES (char, fg, bg) pour la teinte `deg` — pour le rendu
    différentiel du menu (on compare cellule par cellule)."""
    return [[("▀", _txt(*_teinte(LOGO[2 * cr][x], deg)), _fond(*_teinte(LOGO[2 * cr + 1][x], deg)))
             for x in range(LOGO_COLS)] for cr in range(LOGO_ROWS)]


# On pré-calcule les variantes de teinte (le titre cyclera à travers tout l'arc-en-ciel).
_PAS_TEINTE = 48
_LOGO_TEINTES = ([_lignes_logo_teinte(i * 360 // _PAS_TEINTE) for i in range(_PAS_TEINTE)]
                 if LOGO_COLS else [])
_LOGO_CELLS = ([_cells_logo_teinte(i * 360 // _PAS_TEINTE) for i in range(_PAS_TEINTE)]
               if LOGO_COLS else [])


def banniere():
    marge = " " * _marge_logo()
    for ligne in _lignes_logo():
        _ecrire(BASE + marge + ligne + "\n")
        _pause(0.05)


def clignoter(texte, couleur=OR, fois=3):
    ligne = _centrer(texte)
    for _ in range(fois if ANIMATIONS else 0):
        _ecrire("\r\x1b[K" + couleur + GRAS + ligne + BASE)
        time.sleep(0.18)
        _ecrire("\r\x1b[K")
        time.sleep(0.12)
    _ecrire("\r\x1b[K" + couleur + GRAS + ligne + BASE + "\n")


def machine_a_ecrire(texte, couleur=TEXTE, delai=0.012):
    _ecrire(couleur)
    for c in texte:
        _ecrire(c)
        _pause(delai)
    _ecrire(BASE + "\n")


# ---------- Intro animée (étoiles + logo qui brille et dégouline) ----------

def _cacher_curseur():
    _ecrire("\x1b[?25l")


def _montrer_curseur():
    _ecrire("\x1b[?25h")


def _crt(grille, f):
    """Ajoute un effet CRT léger : scanlines fixes (immobiles). Pas de barre
    roulante : elle réémettait des lignes entières à chaque image (coûteux sur
    la console Windows, d'où les ralentissements)."""
    if not CRT or not grille:
        return grille
    H, W = len(grille), len(grille[0])
    scan = _txt(13, 28, 32)
    for y in range(0, H, 3):                     # scanlines discrètes et STABLES
        row = grille[y]
        for x in range(W):
            if row[x][0] == " " and row[x][1] is None:
                row[x] = ("─", scan, None)
    return grille


_crt_f = 0
_intro_offset = 0          # marge gauche pour centrer l'intro dans la fenêtre
_intro_voffset = 0         # marge haute pour centrer l'intro dans la fenêtre


def _rendu_depuis(g, vo=0, ho=0):
    """Image PLEIN ÉCRAN à partir d'une grille FINALE (CRT déjà posé)."""
    dec = " " * ho
    out = ["\x1b[H"]
    for _ in range(vo):                          # lignes vides au-dessus (centrage vertical)
        out.append(BASE + "\x1b[K\n")
    for rangee in g:
        morceaux = [BASE, dec]
        cfg = cbg = None
        for ch, fg, bg in rangee:
            dfg = fg or TEXTE
            dbg = bg or FOND
            if dfg != cfg:
                morceaux.append(dfg); cfg = dfg
            if dbg != cbg:
                morceaux.append(dbg); cbg = dbg
            morceaux.append(ch)
        out.append("".join(morceaux) + BASE + "\x1b[K\n")
    return "".join(out)


def _rendu_grille(grille):
    """Transforme une grille de (char, fg, bg) en une image terminal plein écran
    (+ CRT), centrée via _intro_offset / _intro_voffset."""
    global _crt_f
    g = _crt(grille, _crt_f)
    _crt_f += 1
    return _rendu_depuis(g, _intro_voffset, _intro_offset)


_fb_prev = None          # dernier cadre émis (cellules finales), pour le rendu différentiel


def _reinit_cadre():
    """À appeler après un effacement d'écran : le prochain cadre sera plein."""
    global _fb_prev
    _fb_prev = None


def _emettre(grille):
    """Rendu DIFFÉRENTIEL : n'émet que les cellules qui ont changé depuis le dernier
    cadre (repositionnement du curseur). INDISPENSABLE sur la console Windows :
    repeindre tout l'écran en 24 bits à chaque image la fait ramer/figer. Le 1er
    cadre (ou après _reinit_cadre) est plein écran."""
    global _fb_prev, _crt_f
    g = _crt(grille, _crt_f)
    _crt_f += 1
    H = len(g)
    W = len(g[0]) if H else 0
    vo, ho = _intro_voffset, _intro_offset
    if _fb_prev is None or len(_fb_prev) != H or (H and len(_fb_prev[0]) != W):
        _fb_prev = [row[:] for row in g]
        return _SYNC_DEBUT + _rendu_depuis(g, vo, ho) + _SYNC_FIN   # plein écran
    prev = _fb_prev
    out = []
    for y in range(H):
        row = g[y]
        prow = prev[y]
        if row == prow:                          # ligne inchangée → rien à émettre
            continue
        x = 0
        while x < W:
            if row[x] != prow[x]:
                xs = x
                seg = ["\x1b[%d;%dH" % (y + 1 + vo, xs + 1 + ho), BASE]
                cfg = cbg = None
                while x < W and row[x] != prow[x]:
                    ch, fg, bg = row[x]
                    dfg = fg or TEXTE
                    dbg = bg or FOND
                    if dfg != cfg:
                        seg.append(dfg); cfg = dfg
                    if dbg != cbg:
                        seg.append(dbg); cbg = dbg
                    seg.append(ch)
                    x += 1
                out.append("".join(seg))
            else:
                x += 1
    _fb_prev = [row[:] for row in g]
    return (_SYNC_DEBUT + "".join(out) + BASE + _SYNC_FIN) if out else ""


CARS_PLUIE = "01010110¦:+*=<>/\\!?#$%&01"


# ---------- Écran d'accueil : un œil détaillé et étiré qui s'ouvre ----------
#
# L'affichage de départ, c'est UNIQUEMENT l'œil (plus détaillé, plus long, plus
# étiré) + un slogan de hacker juste dessous + l'invite « ENTRÉE / ÉCHAP ».
# ENTRÉE → on entre (le menu s'affiche). ÉCHAP → on quitte le programme.

_GARB = "!<>/\\#%&01=?*¦:+"

_SLOGANS = [
    "LA MAISON NE PERD JAMAIS.",
    "JE VOIS DÉJÀ DANS TON JEU.",
    "LA CHANCE EST UNE ILLUSION.",
    "RIEN N'EST LAISSÉ AU HASARD.",
    "LA PARTIE A DÉJÀ COMMENCÉ.",
    "TU AS DÉJÀ PERDU. TU L'IGNORES.",
    "MONTRE-MOI TON JEU.",
]


class _Clavier:
    """Lecture clavier NON bloquante. .get() renvoie 'enter', 'esc' ou None.
    Windows : msvcrt. Linux/Mac : termios en mode cbreak."""
    def __enter__(self):
        self.nt = (os.name == "nt")
        self.ok = False
        self._buf = ""                       # séquence d'échappement en attente (fragment)
        self._esc_hold = 0                   # ESC seul en attente d'une éventuelle suite
        try:
            if self.nt:
                import msvcrt
                self.msvcrt = msvcrt
                self.ok = True
            else:
                import termios, tty
                self.termios = termios
                self.fd = sys.stdin.fileno()
                self.old = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
                self.ok = True
        except Exception:
            self.ok = False
        return self

    def __exit__(self, *a):
        if self.ok and not self.nt:
            try:
                self.termios.tcsetattr(self.fd, self.termios.TCSADRAIN, self.old)
            except Exception:
                pass

    def vider(self):
        """Jette les touches déjà tapées (évite qu'un double appui saute une étape)."""
        if not self.ok:
            return
        try:
            if self.nt:
                while self.msvcrt.kbhit():
                    self.msvcrt.getwch()
            else:
                self.termios.tcflush(self.fd, self.termios.TCIFLUSH)
        except Exception:
            pass

    def _lire_bruts(self):
        """Renvoie les caractères bruts disponibles (non bloquant). Les séquences
        d'échappement (flèches, souris/molette) arrivent en rafale : si les
        données finissent par ESC, on attend ~15 ms la suite pour l'avoir entière
        et pouvoir l'écarter proprement (sinon ses chiffres pollueraient la saisie).
        Côté Windows, les touches spéciales à préfixe \\x00/\\xe0 sont jetées ici."""
        if self.nt:
            def _lot():
                out = []
                while self.msvcrt.kbhit():
                    ch = self.msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):            # flèche/F../Inser… (console héritée)
                        # un préfixe de touche spéciale est TOUJOURS suivi d'un code :
                        # on l'attend (jusqu'à ~40 ms) et on le JETTE, sans se fier à
                        # kbhit() qui peut répondre False juste après le préfixe (sinon
                        # le code — H/P/K/M pour les flèches — polluerait la saisie).
                        for _ in range(40):
                            if self.msvcrt.kbhit():
                                self.msvcrt.getwch()
                                break
                            time.sleep(0.001)
                        continue
                    out.append(ch)
                return "".join(out)
            s = _lot()
            if s.endswith("\x1b"):                        # VT : flèche = ESC [ … ; on attend la fin
                time.sleep(0.015)
                s += _lot()
            return s
        import select
        r, _, _ = select.select([self.fd], [], [], 0)
        if not r:
            return ""
        s = os.read(self.fd, 1024).decode("utf-8", "ignore")
        if s.endswith("\x1b"):
            r2, _, _ = select.select([self.fd], [], [], 0.015)
            if r2:
                s += os.read(self.fd, 1024).decode("utf-8", "ignore")
        return s

    @staticmethod
    def _analyser_echap(s, i):
        """Analyse l'ESC à l'indice i. Renvoie :
        None          -> on ne sait pas encore (séquence incomplète / ESC en fin) ;
        ('esc', j)    -> Échap isolé (le reste du buffer sera lu normalement) ;
        ('seq', j)    -> séquence à JETER (flèche, molette/souris, F.., clavier num.),
                         j = indice juste après. Couvre CSI (ESC [ … octet final
                         0x40-0x7E, rapports souris ESC [ < … M/m inclus) et SS3 (ESC O x)."""
        n = len(s)
        if i + 1 >= n:
            return None                                   # juste ESC pour l'instant
        c = s[i + 1]
        if c == "[":
            if i + 2 < n and s[i + 2] == "M":             # souris X10 : ESC [ M + 3 octets bruts
                return ("seq", i + 6) if i + 5 < n else None
            k = i + 2
            while k < n and "\x20" <= s[k] <= "\x3f":     # paramètres + octets intermédiaires
                k += 1
            if k < n and "\x40" <= s[k] <= "\x7e":        # octet final
                return ("seq", k + 1)
            return None                                   # CSI pas encore complet
        if c == "O":
            return ("seq", i + 3) if i + 2 < n else None
        return ("esc", i + 1)                             # ESC + autre : vrai Échap

    def evenements(self):
        """Lit TOUTES les touches dispo (non bloquant) pour un éditeur de ligne.
        Renvoie une liste d'événements : ('char', c) / ('enter',) / ('back',) /
        ('esc',) / ('ctrl-c',). Flèches et molette sont silencieusement ignorées."""
        evs = []
        if not self.ok:
            return evs
        try:
            nouveau = self._lire_bruts()
        except KeyboardInterrupt:
            raise
        except Exception:
            return evs
        if nouveau:
            self._esc_hold = 0                            # du nouveau est arrivé : on re-décide
        self._buf += nouveau
        s = self._buf
        i, n = 0, len(s)
        while i < n:
            ch = s[i]
            if ch == "\x1b":
                r = self._analyser_echap(s, i)
                if r is None:                             # ESC en fin, ou CSI incomplet
                    if i == n - 1:                        # ESC tout seul au bout
                        if self._esc_hold >= 1:           # resté seul un tour → vrai Échap
                            evs.append(("esc",))
                            i += 1
                            self._esc_hold = 0
                            continue
                        self._esc_hold += 1               # on attend une éventuelle flèche fragmentée
                    break                                 # garde le reste pour le prochain tour
                kind, fin = r
                if kind == "esc":
                    evs.append(("esc",))
                    i += 1                                # le caractère suivant sera lu normalement
                else:
                    i = fin                               # flèche/souris : jetée
                continue
            evs.append(self._classer(ch))
            i += 1
        self._buf = s[i:]
        return evs

    def get(self):
        """Renvoie 'enter', 'esc' ou None (les autres touches et les séquences
        d'échappement sont ignorées)."""
        if not self.ok:
            return None
        res = None
        for ev in self.evenements():
            if ev[0] == "ctrl-c":
                raise KeyboardInterrupt
            if ev[0] in ("enter", "esc"):
                res = ev[0]
        return res

    @staticmethod
    def _classer(ch):
        if ch in ("\r", "\n"):
            return ("enter",)
        if ch in ("\x7f", "\b"):
            return ("back",)
        if ch == "\x1b":
            return ("esc",)
        if ch == "\x03":
            return ("ctrl-c",)
        if ch < " ":
            return ("autre",)
        return ("char", ch)


def _nouvelle_grille(W, H):
    return [[(" ", None, None) for _ in range(W)] for _ in range(H)]


# L'œil est rendu en DEMI-BLOCS « ▀ » : chaque cellule = 2 pixels empilés
# (couleur du haut = avant-plan, couleur du bas = fond). Ça DOUBLE la résolution
# verticale → iris rond, dégradés lisses, bien plus réaliste. Dans cet espace
# « sous-pixel », 1 colonne de large ≈ 1 demi-cellule de haut (quasi carré).
_ASP = 2.05                         # (gardé pour la plongée/zoom)
_FOND_OEIL = (6, 8, 12)             # noir de fond sous l'œil

# --- Palette NOIR & BLANC (argent froid) : l'œil n'est plus rouge mais acier ---
_IRIS_IN = (208, 218, 232)          # cœur de l'iris : argent clair et froid
_IRIS_OUT = (38, 46, 60)            # bord de l'iris (limbe) : ardoise sombre
_PUP = (5, 6, 10)                   # pupille : noir profond
_SCLERE = (224, 230, 239)           # blanc de l'œil (très légèrement bleuté)
_SCLERE_OMBRE = (150, 158, 172)     # blanc à l'ombre de la paupière haute
_PAUP_HAUT = (33, 36, 45)           # paupière haute (peau dans l'ombre)
_PAUP_BAS = (46, 50, 61)            # paupière basse
_CARONCULE = (152, 120, 122)        # coin interne rosé (très discret)


def _oeil_geo(W, H):
    """Géométrie de l'œil GÉANT (il remplit l'écran) + lignes slogan / invite.
    Wx = demi-largeur (colonnes), Hy = demi-hauteur (cellules), Ri = rayon
    vertical de l'iris (cellules). L'amande est couplée ~2.5:1 (largeur:hauteur
    visuelle) pour rester naturelle quelle que soit la taille de la fenêtre."""
    cx = W // 2
    cy = int(H * 0.455)
    hy_vert = max(min(cy - 1, (H - cy) - 5), 3)      # place laissée en bas (slogan)
    wx_horiz = max(cx - 3, 12)
    k = 5.0                                           # Wx ≈ 5·Hy → amande allongée
    Hy = max(min(float(hy_vert), wx_horiz / k), 3.0)
    Wx = max(min(float(wx_horiz), k * Hy), 12.0)
    Ri = Hy * 0.98                                    # iris presque aussi haut que l'œil
    r_slogan = min(int(cy + Hy) + 2, H - 3)
    r_invite = min(int(cy + Hy) + 4, H - 1)
    return cx, cy, Wx, Hy, Ri, r_slogan, r_invite


_oeil_seed = 0                                      # fixe les veines pour tout un lancement


def _dessiner_veines(*a, **k):
    """(Remplacé par des veines procédurales dans _dessiner_oeil.)"""
    return


def _dessiner_oeil(grille, W, H, ouv, gx, gy, dil, f, veines=1.0, ri_scale=1.0):
    """Œil réaliste GÉANT rendu en demi-blocs « ▀ » (2 pixels verticaux/cellule).
    ouv 0→1 ouverture · gx,gy regard · dil pupille · ri_scale taille de l'iris."""
    cx, cy, Wx, Hy, Ri, _, _ = _oeil_geo(W, H)
    P = 0.52                                     # exposant de l'amande (coins pointus)
    cyp = 2.0 * cy                               # centre vertical de l'œil (sous-pixels)
    Hyp = 2.0 * Hy                               # demi-hauteur de l'ouverture (sous-pixels)
    icx = cx + gx                                # centre iris (suit le regard)
    icyp = cyp + 2.0 * gy
    Riy = max(2.0 * Ri * ri_scale, 1.0)          # rayon vertical iris (sous-pixels)
    Rix = max(Riy * 1.02, 1.0)                   # rayon horizontal iris (colonnes) → rond
    pupf = max(min(0.42 * dil, 0.95), 0.03)      # pupille en fraction de l'iris
    lid_ep = Hyp * 0.17 + 1.6                    # épaisseur des paupières (sous-pixels)
    seedph = (_oeil_seed % 628) / 100.0          # phase des fibres (stable/lancement)

    sin = math.sin; hypot = math.hypot; atan2 = math.atan2
    I_IN, I_OUT = _IRIS_IN, _IRIS_OUT
    SCL, SCLO, PH, PB = _SCLERE, _SCLERE_OMBRE, _PAUP_HAUT, _PAUP_BAS
    vein_a = 0.45 * veines

    def pix(xf, yp, L, nx):
        """Couleur (r,g,b) d'un sous-pixel, ou None si hors de l'œil + paupières."""
        dyc = yp - cyp
        ad = dyc if dyc >= 0 else -dyc
        if ad > L:                               # hors ouverture → paupière (peau) ?
            if L > 1.0 and ad <= L + lid_ep:
                e = (ad - L) / lid_ep
                if dyc < 0:                      # paupière haute
                    if e < 0.14:
                        return (95, 99, 114)     # ourlet clair (bord mouillé)
                    base = PH
                else:                            # paupière basse
                    if e < 0.12:
                        return (92, 97, 110)
                    base = PB
                sh = 1.0 - 0.55 * e
                return (int(base[0]*sh), int(base[1]*sh), int(base[2]*sh))
            return None
        # ombrage vertical DOUX : le haut de l'œil est dans l'ombre de la paupière,
        # le bas capte la lumière → dégradé (plus de « bande » horizontale dure).
        vpos = dyc / L                           # -1 (haut) … +1 (bas)
        shade = 0.55 + 0.45 * (vpos * 0.5 + 0.5)
        dxn = (xf - icx) / Rix
        dyn = (yp - icyp) / Riy
        rn = hypot(dxn, dyn)
        if rn <= pupf - 0.05:                    # pupille (noir profond)
            return _PUP
        if rn <= pupf + 0.05:                    # bord adouci de la pupille
            return (17, 18, 24)
        if rn <= 1.0:                            # iris (argent froid, détaillé)
            t = (rn - pupf) / (1.0 - pupf)       # 0 au bord pupille → 1 au limbe
            th = atan2(dyn, dxn)
            fib = 0.5 + 0.5 * sin(th * 52.0 + rn * 5.0 + seedph)   # fibres radiales fines
            cry = 0.5 + 0.5 * sin(th * 7.0 - rn * 3.2 + 0.7)       # cryptes plus larges
            br = (0.62 + 0.48 * fib) * (0.84 + 0.30 * cry) * shade
            if 0.07 < t < 0.20:
                br *= 1.42                        # collerette claire autour de la pupille
            if t > 0.86:
                br *= 0.32                        # anneau limbique (sombre)
            r = (I_IN[0] + (I_OUT[0]-I_IN[0])*t) * br
            g = (I_IN[1] + (I_OUT[1]-I_IN[1])*t) * br
            b = (I_IN[2] + (I_OUT[2]-I_IN[2])*t) * br
            return (int(r) if r < 255 else 255,
                    int(g) if g < 255 else 255,
                    int(b) if b < 255 else 255)
        # --- blanc de l'œil (sclère), ombré en dégradé ---
        anx = nx if nx >= 0 else -nx
        if anx > 0.86:                           # coin interne rosé (caroncule), discret
            m = (anx - 0.86) / 0.14
            r = (SCL[0] + 8*m) * shade; g = (SCL[1] - 46*m) * shade; b = (SCL[2] - 42*m) * shade
            return (int(r) if r < 255 else 255, int(g) if g > 0 else 0, int(b) if b > 0 else 0)
        r = SCL[0] * shade; g = SCL[1] * shade; b = SCL[2] * shade
        if vein_a > 0.0 and anx > 0.42:          # fines veines (œil très légèrement injecté)
            vn = sin(xf * 0.42 + yp * 0.9) + 0.7 * sin(xf * 1.1 - yp * 0.5 + 1.0)
            if vn > 1.52:
                k2 = vein_a * (anx - 0.42)
                r -= 15 * k2; g -= 40 * k2; b -= 38 * k2
        return (int(r) if r < 255 else 255, int(g) if g > 0 else 0, int(b) if b > 0 else 0)

    x0 = max(int(cx - Wx) - 1, 0); x1 = min(int(cx + Wx) + 2, W)
    y0 = max(int(cy - Hy) - 2, 0); y1 = min(int(cy + Hy) + 3, H)
    txt = _txt; fond = _fond; FB = _FOND_OEIL
    Wx_inv = 1.0 / Wx
    Lcol = [0.0] * W                             # demi-ouverture par colonne (1 calcul)
    for x in range(x0, x1):
        nxx = (x - cx) * Wx_inv
        if -1.0 < nxx < 1.0:
            Lcol[x] = ouv * Hyp * (1.0 - nxx*nxx) ** P
    for y in range(y0, y1):
        row = grille[y]
        ypt = 2.0 * y; ypb = ypt + 1.0
        for x in range(x0, x1):
            L = Lcol[x]
            if L <= 0.0:
                continue
            nxx = (x - cx) * Wx_inv
            ct = pix(x, ypt, L, nxx)
            cb = pix(x, ypb, L, nxx)
            if ct is None:
                if cb is None:
                    continue
                row[x] = ("▀", txt(*FB), fond(*cb))
            elif cb is None:
                row[x] = ("▀", txt(*ct), fond(*FB))
            else:
                row[x] = ("▀", txt(*ct), fond(*cb))

    # --- reflet spéculaire (grosse lumière en haut-gauche de l'iris) ---
    gcx = int(round(icx - Rix * 0.40))
    gcy = int((icyp - Riy * 0.46) / 2.0)
    for dx, dy, c in ((0, 0, (255, 255, 255)), (1, 0, (232, 240, 252)),
                      (-1, 0, (226, 235, 250)), (0, 1, (206, 218, 238))):
        xx, yy = gcx + dx, gcy + dy
        if 0 <= xx < W and 0 <= yy < H and abs(2*yy - cyp) <= Lcol[xx]:
            grille[yy][xx] = ("▀", txt(*c), fond(*c))
    # reflet secondaire discret (bas-droite)
    sx = int(round(icx + Rix * 0.52)); sy = int((icyp + Riy * 0.52) / 2.0)
    if 0 <= sx < W and 0 <= sy < H and abs(2*sy - cyp) <= Lcol[sx]:
        grille[sy][sx] = ("▀", txt(150, 160, 176), fond(118, 128, 144))

    # --- cils sur la paupière haute (quelques traits fins) ---
    if ouv > 0.72:
        pas = max(int(Wx // 13), 2)
        for x in range(x0, x1, pas):
            L = Lcol[x]
            if L < Hyp * 0.32:
                continue
            yc = int((cyp - L) / 2.0) - 1
            if 0 <= yc < H and grille[yc][x][0] == " ":
                ex = x - cx
                pt = "╲" if ex < -Wx * 0.3 else ("╱" if ex > Wx * 0.3 else "│")
                grille[yc][x] = (pt, txt(18, 20, 26), None)


def _poser_centre(grille, W, H, row, s, couleur):
    if not (0 <= row < H):
        return
    x0 = max((W - len(s)) // 2, 0)
    for i, ch in enumerate(s):
        if 0 <= x0 + i < W:
            grille[row][x0 + i] = (ch, couleur, None)


def _poser_segments(grille, W, H, row, segments):
    if not (0 <= row < H):
        return
    total = sum(len(t) for t, _ in segments)
    x = max((W - total) // 2, 0)
    for t, couleur in segments:
        for ch in t:
            if 0 <= x < W:
                grille[row][x] = (ch, couleur, None)
            x += 1


def _poser_slogan(grille, W, H, texte):
    _, _, _, _, _, r_slogan, _ = _oeil_geo(W, H)
    _poser_centre(grille, W, H, r_slogan, texte, _txt(212, 224, 238))   # argent clair


def _poser_invite(grille, W, H, allume=True):
    _, _, _, _, _, _, r_invite = _oeil_geo(W, H)
    ent = _txt(228, 234, 244) if allume else _txt(96, 104, 116)         # blanc argenté
    ech = _txt(208, 120, 120) if allume else _txt(112, 70, 72)          # seul accent : rose éteint
    gris = _txt(116, 126, 140)
    _poser_segments(grille, W, H, r_invite, [
        ("[ENTRÉE]", ent), ("  entrer dans la partie        ", gris),
        ("[ÉCHAP]", ech), ("  quitter", gris),
    ])


def _interp(t, ks):
    for i in range(len(ks) - 1):
        (t0, v0), (t1, v1) = ks[i], ks[i + 1]
        if t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            return v0 + (v1 - v0) * k
    return ks[-1][1]


# ---------- Cartes qui tournent (360° sur leur axe vertical) ----------
# Deux as : un CLAIR (white hat) et un SOMBRE (black hat) — l'éthique du hacker.
# La rotation est simulée en comprimant la largeur (× |cos θ|) et en montrant la
# face quand cos θ ≥ 0, le dos quand cos θ < 0 : l'illusion d'un rotateY 3D.

_SPADE_ART = [
    "      █      ",
    "    ▄███▄    ",
    "  ▄███████▄  ",
    "▄███████████▄",
    "█████████████",
    "▀██▀▀███▀▀██▀",
    "     ███     ",
    "   ▄▄███▄▄   ",
]
_CLUB_ART = [
    "    ▄███▄    ",
    "   ███████   ",
    "▄█▄ █████ ▄█▄",
    "███▄█████▄███",
    "█████████████",
    "▀▀▀█▀███▀█▀▀▀",
    "     ███     ",
    "   ▄▄███▄▄   ",
]
_ART_ENSEIGNE = {"♠": _SPADE_ART, "♣": _CLUB_ART}
_LARG_CARTE, _HAUT_CARTE = 15, 14          # colonnes × lignes


def _carte_as(kind, enseigne="♠"):
    """Construit un as (faces avant/arrière) en cellules (char, fg, bg).
    kind 'clair' = carte blanche/encre noire · 'sombre' = l'inverse.
    enseigne : ♠ ou ♣ (dessin central + coins)."""
    if kind == "clair":
        BG, INK, ED = (232, 235, 240), (22, 24, 32), (70, 74, 86)
    else:
        BG, INK, ED = (17, 19, 26), (223, 229, 239), (150, 158, 172)
    bg, ink, ed = _fond(*BG), _txt(*INK), _txt(*ED)
    inner = _LARG_CARTE - 2
    art = _ART_ENSEIGNE.get(enseigne, _SPADE_ART)

    def cell_row(s):
        s = (s + " " * inner)[:inner]
        return [(" ", None, bg) if ch == " " else (ch, ink, bg) for ch in s]

    def bord(g, d):
        return [(g, ed, bg)] + [("─", ed, bg)] * inner + [(d, ed, bg)]

    # --- FACE : coins A + grande enseigne au centre ---
    front = [bord("╭", "╮")]
    front.append([("│", ed, bg)] + cell_row("A") + [("│", ed, bg)])
    front.append([("│", ed, bg)] + cell_row(enseigne) + [("│", ed, bg)])
    for ligne in art:
        front.append([("│", ed, bg)] + cell_row(ligne) + [("│", ed, bg)])
    front.append([("│", ed, bg)] + cell_row("          " + enseigne) + [("│", ed, bg)])
    front.append([("│", ed, bg)] + cell_row("          A") + [("│", ed, bg)])
    front.append(bord("╰", "╯"))

    # --- DOS : treillis + petite enseigne centrale ---
    dos = [bord("╭", "╮")]
    motif = "▞▚" * ((inner // 2) + 1)
    for r in range(_HAUT_CARTE - 2):
        cells = [(motif[(r + i) % len(motif)], ed, bg) for i in range(inner)]
        dos.append([("│", ed, bg)] + cells + [("│", ed, bg)])
    mid = (_HAUT_CARTE - 2) // 2
    dos[mid][1 + inner // 2] = (enseigne, ink, bg)
    dos.append(bord("╰", "╯"))
    return {"front": front, "back": dos, "w": _LARG_CARTE, "h": _HAUT_CARTE}


_AS_CLAIR = None
_AS_SOMBRE = None
_AS_CENTRE = None


def _as_caches():
    """Les deux as de l'accueil : clair (white hat) ♠ + sombre (black hat) ♠."""
    global _AS_CLAIR, _AS_SOMBRE
    if _AS_CLAIR is None:
        _AS_CLAIR = _carte_as("clair", "♠")
        _AS_SOMBRE = _carte_as("sombre", "♠")
    return _AS_CLAIR, _AS_SOMBRE


def _as_centre():
    """Les deux as blancs du MENU, comme la photo : A♣ (devant) + A♠ (derrière)."""
    global _AS_CENTRE
    if _AS_CENTRE is None:
        _AS_CENTRE = (_carte_as("clair", "♣"), _carte_as("clair", "♠"))
    return _AS_CENTRE


def _poser_carte_spin(grille, W, H, ccx, ccy, carte, angle, epais=3):
    """Pose la carte centrée en (ccx, ccy), tournée de `angle` autour de l'axe
    vertical. La carte a une ÉPAISSEUR (tranche claire visible de profil) : elle
    ne se réduit JAMAIS à un simple trait (« pas perpendiculaire »)."""
    c = math.cos(angle)
    s = math.sin(angle)
    face = carte["front"] if c >= 0 else carte["back"]
    Wc, Hc = carte["w"], carte["h"]
    wf = int(round(Wc * abs(c)))                 # largeur de la face (0 de profil)
    we = int(round(epais * abs(s))) if epais else 0   # largeur de la tranche (max de profil)
    total = max(wf + we, 1)
    y0 = ccy - Hc // 2
    x0 = ccx - total // 2
    edge_right = (s >= 0)                        # tranche du côté fuyant
    tr_pl = ("█", _txt(214, 218, 226), _fond(150, 154, 164))   # tranche (corps)
    tr_hb = ("▀", _txt(96, 100, 112), _fond(150, 154, 164))    # tranche (haut/bas)
    for ry in range(Hc):
        gy = y0 + ry
        if not (0 <= gy < H):
            continue
        srow = face[ry]
        rowg = grille[gy]
        bord_hb = (ry == 0 or ry == Hc - 1)
        for k in range(total):
            gx = x0 + k
            if not (0 <= gx < W):
                continue
            in_edge = (k >= wf) if edge_right else (k < we)
            if (in_edge and we > 0) or wf == 0:
                rowg[gx] = tr_hb if bord_hb else tr_pl
            else:
                jf = k if edge_right else (k - we)
                denom = wf if wf > 0 else 1
                sx = (Wc - 1 - int(jf / denom * Wc)) if c < 0 else int(jf / denom * Wc)
                sx = min(max(sx, 0), Wc - 1)
                rowg[gx] = srow[sx]


def _poser_as_coins(grille, W, H, ang_g=0.0, ang_d=0.0):
    """Les deux as (clair = white hat, sombre = black hat) posés en bas, dans les
    coins noirs de l'écran (hors de l'amande de l'œil). Grand écran seulement."""
    if W < 92 or H < 40:
        return
    clair, sombre = _as_caches()
    cyb = H - _HAUT_CARTE // 2 - 2
    xg = _LARG_CARTE // 2 + 3
    xd = W - _LARG_CARTE // 2 - 3
    _poser_carte_spin(grille, W, H, xg, cyb, clair, ang_g)
    _poser_carte_spin(grille, W, H, xd, cyb, sombre, ang_d)


def _intro_cartes(W, H, kb):
    """Lever de rideau : deux as tournent à 360° au centre — un CLAIR (white hat)
    et un SOMBRE (black hat). Ils accélèrent, ralentissent, se présentent de face,
    puis s'effacent pour laisser place à l'œil."""
    if H < 18 or W < 44:
        return None
    cx, cy, _, _, _, _, _ = _oeil_geo(W, H)
    clair, sombre = _as_caches()
    ccy = min(max(cy, _HAUT_CARTE // 2 + 1), H - _HAUT_CARTE // 2 - 4)
    ecart = min(W // 2 - 10, 17)
    xg, xd = cx - ecart, cx + ecart
    rcap = min(ccy + _HAUT_CARTE // 2 + 2, H - 3)
    cap1, cc1 = "WHITE HAT   ◇   BLACK HAT", _txt(212, 220, 234)
    cap2, cc2 = "deux faces · une seule main", _txt(118, 128, 142)

    def img(ang_g, ang_d, p):
        grille = _nouvelle_grille(W, H)
        _poser_carte_spin(grille, W, H, xg, ccy, clair, ang_g)
        _poser_carte_spin(grille, W, H, xd, ccy, sombre, ang_d)
        if p > 0.35:
            _poser_centre(grille, W, H, rcap, cap1, cc1)
        if p > 0.55:
            _poser_centre(grille, W, H, rcap + 1, cap2, cc2)
        _ecrire(_emettre(grille))

    frames = 94
    tours = 3.0
    for f in range(frames):                          # grande rotation qui ralentit
        t = f / (frames - 1)
        e = 1.0 - (1.0 - t) ** 2.4                    # ease-out
        ang = tours * 2 * math.pi * e
        img(ang, -ang, t)
        k = kb.get()
        if k:
            return k
        time.sleep(0.012)
    for _ in range(16):                              # pose : face caméra
        img(0.0, 0.0, 1.0)
        k = kb.get()
        if k:
            return k
        time.sleep(0.03)
    for f in range(12):                              # sortie : les cartes repartent
        t = f / 11.0
        ang = (math.pi / 2) * t
        img(ang, -ang, 1.0)
        if kb.get():
            break
        time.sleep(0.02)
    _ecrire(BASE + "\x1b[2J\x1b[H")
    _reinit_cadre()                                  # l'écran est effacé → prochain cadre plein
    return None


def _oeil_ouverture(W, H, kb):
    """L'œil GÉANT s'ouvre : deux clignements puis grande ouverture, avec un léger
    balayage du regard. Rendu fluide. Renvoie 'enter'/'esc' si on appuie."""
    cx, cy, Wx, Hy, Ri, _, _ = _oeil_geo(W, H)
    cles = [(0.00, 0.0), (0.10, 0.0), (0.16, 0.60), (0.22, 0.05), (0.31, 0.72),
            (0.37, 0.06), (0.50, 1.0), (0.70, 1.0), (0.74, 0.14), (0.80, 1.0), (1.0, 1.0)]
    frames = 66                                      # moins d'images = moins de charge console
    for f in range(frames):
        t = f / (frames - 1)
        ouv = _interp(t, cles)
        look = max(0.0, min((t - 0.50) / 0.45, 1.0))
        gx = (Wx * 0.14) * math.sin(t * 5.0) * look
        gy = (Hy * 0.10) * math.sin(t * 3.1 + 1) * look
        if t > 0.90:                                 # recentre le regard à la fin
            gx *= max((1 - t) / 0.10, 0.0)
            gy *= max((1 - t) / 0.10, 0.0)
        dil = 1.0 + 0.05 * math.sin(f * 0.22)
        grille = _nouvelle_grille(W, H)
        _dessiner_oeil(grille, W, H, ouv, gx, gy, dil, f)
        _ecrire(_emettre(grille))
        k = kb.get()
        if k:
            return k
        time.sleep(0.018)
    return None


def _oeil_revele(W, H, slogan, kb):
    """Le slogan se décode sous l'œil, puis l'invite apparaît (+ les deux as en bas)."""
    frames = 22
    for f in range(frames):
        p = (f + 1) / frames
        grille = _nouvelle_grille(W, H)
        _dessiner_oeil(grille, W, H, 1.0, 0.0, 0.0, 1.0 + 0.05 * math.sin(f * 0.3), 900 + f)
        _poser_as_coins(grille, W, H)
        n = int(len(slogan) * p)
        aff = "".join(slogan[i] if i < n else random.choice(_GARB) for i in range(len(slogan)))
        _poser_slogan(grille, W, H, aff)
        if p > 0.5:
            _poser_invite(grille, W, H, allume=True)
        _ecrire(_emettre(grille))
        k = kb.get()
        if k:
            return k
        time.sleep(0.04)
    return None


def _oeil_frisson(W, H, slogan, kb):
    """Un bref frisson : l'iris se rétracte D'UN COUP (minuscule), l'œil se fige
    et s'écarquille, puis tout revient à la normale. « Ça fait peur, mais pas trop. »"""
    frames = 48
    for f in range(frames):
        t = f / (frames - 1)
        if t < 0.22:                                     # rétraction vive
            u = t / 0.22
            ri = 1.0 - u * 0.72
            dil = 1.0 - u * 0.56
        elif t < 0.50:                                   # maintien : iris minuscule
            ri, dil = 0.28, 0.44
        else:                                            # retour en douceur
            u = (t - 0.50) / 0.50
            ri = 0.28 + u * 0.72
            dil = 0.44 + u * 0.56
        pic = 0.16 < t < 0.58
        veg = 2.6 if pic else 0.7                        # veines gonflées au pic
        ouv = 1.14 if pic else 1.0                       # œil écarquillé
        jit = random.uniform(-0.7, 0.7) if (0.20 < t < 0.50) else 0.0   # tremblement
        grille = _nouvelle_grille(W, H)
        _dessiner_oeil(grille, W, H, ouv, jit, 0.0, dil, 1500 + f, veines=veg, ri_scale=ri)
        _poser_as_coins(grille, W, H)
        _poser_slogan(grille, W, H, slogan)
        _poser_invite(grille, W, H, allume=True)
        _ecrire(_emettre(grille))
        k = kb.get()
        if k:
            return k
        time.sleep(0.03)
    return None


def _oeil_zoom(W, H):
    """Transition : la caméra plonge dans la pupille (le noir envahit l'écran)."""
    _reinit_cadre()                                  # on vient d'une phase quelconque
    cx, cy, Wx, Hy, Ri, _, _ = _oeil_geo(W, H)
    maxr = math.hypot(W / _ASP, H) + 2
    noir = _fond(2, 3, 8)
    frames = 20
    for f in range(frames):
        p = (f + 1) / frames
        grille = _nouvelle_grille(W, H)
        _dessiner_oeil(grille, W, H, 1.0, 0.0, 0.0, 1.0 + p * 7.0, 3000 + f, veines=1.0)
        rad = (p ** 1.7) * maxr                          # disque noir qui grandit
        if rad > 0.5:
            ry = int(rad)
            for y in range(max(cy - ry, 0), min(cy + ry + 1, H)):
                d2 = rad * rad - (y - cy) ** 2
                if d2 <= 0:
                    continue
                demi = _ASP * math.sqrt(d2)
                rowg = grille[y]
                for x in range(max(int(cx - demi), 0), min(int(cx + demi) + 1, W)):
                    rowg[x] = (" ", None, noir)
        _ecrire(_emettre(grille))
        time.sleep(0.03)
    _ecrire(BASE + "\x1b[2J\x1b[H")
    _reinit_cadre()


def _oeil_attente(W, H, slogan, kb):
    """L'œil reste VIVANT mais ÉCONOME : il tient son regard immobile (rendu nul),
    et ne se redessine que lors d'un clignement, d'une saccade ou du pouls de
    l'invite. Indispensable pour ne pas saturer la console pendant l'attente."""
    f = 0
    clin = [0.55, 0.12, 0.0, 0.0, 0.15, 0.55, 1.0]
    prochain_clin = random.randint(90, 180)
    invite_on = True
    besoin = True                                    # redessiner ce tour ?
    while True:
        d = _dim()                                   # la fenêtre a-t-elle changé de taille ?
        Wn = max(min(d[0] - 1, 400), 40)
        Hn = max(min(d[1] - 1, 160), 16)
        if (Wn, Hn) != (W, H):                       # oui → on se ré-adapte (pas de bouillie)
            W, H = Wn, Hn
            _ecrire(BASE + "\x1b[2J\x1b[H")
            _reinit_cadre()
            besoin = True
        ouv = 1.0
        bf = f - prochain_clin
        if 0 <= bf < len(clin):                      # clignement en cours
            ouv = clin[bf]; besoin = True
        elif bf == len(clin):                        # fin du clignement → œil rouvert
            prochain_clin = f + random.randint(110, 240); besoin = True
        on = (f // 11) % 2 == 0                       # pouls de l'invite (~1 s)
        if on != invite_on:
            invite_on = on; besoin = True
        if besoin:                                    # on NE dessine QUE si quelque chose bouge
            grille = _nouvelle_grille(W, H)
            _dessiner_oeil(grille, W, H, ouv, 0.0, 0.0, 1.0, f)   # regard fixe : il te FIXE
            _poser_as_coins(grille, W, H)             # as fixes (sceau white/black hat)
            _poser_slogan(grille, W, H, slogan)
            _poser_invite(grille, W, H, allume=invite_on)
            _ecrire(_emettre(grille))
            besoin = False
        k = kb.get()
        if k in ("enter", "esc"):
            return k
        f += 1
        time.sleep(0.05)


def _accueil_oeil(modele):
    """Lève le rideau : cartes qui tournent → l'œil géant s'ouvre → slogan →
    frisson (iris minuscule) → attente. ENTRÉE plonge dans la pupille (menu),
    ÉCHAP quitte. True = entrer, False = quitter."""
    global _intro_offset, _intro_voffset, _oeil_seed
    _intro_offset = _intro_voffset = 0
    _reinit_cadre()                                  # premier cadre = plein écran
    taille = _Taille()
    W = max(min(taille.columns - 1, 400), 40)
    H = max(min(taille.lines - 1, 160), 16)
    slogan = random.choice(_SLOGANS)
    _oeil_seed = random.randint(1, 10 ** 6)          # veines fixes pour ce lancement
    _cacher_curseur()
    try:
        with _Clavier() as kb:
            phases = (
                lambda: _intro_cartes(W, H, kb),          # les deux as tournent (360°)
                lambda: _oeil_ouverture(W, H, kb),        # l'œil géant s'ouvre
                lambda: _oeil_revele(W, H, slogan, kb),   # slogan + invite
                lambda: _oeil_frisson(W, H, slogan, kb),  # l'iris devient minuscule
                lambda: _oeil_attente(W, H, slogan, kb),  # attend ENTRÉE / ÉCHAP
            )
            for phase in phases:
                r = phase()
                if r == "esc":
                    return False
                if r == "enter":
                    _oeil_zoom(W, H)                      # plongée dans la pupille
                    return True
            return True
    finally:
        _montrer_curseur()


def separateur():
    _ecrire(BASE + DISCRET + "─" * min(largeur() - 1, 90) + BASE + "\n")


# ---------- Menu en sections ----------

BLEU = _txt(90, 150, 240)
LARGEUR_BOITE = 44


def _long_visible(s):
    return len(re.sub(r"\x1b\[[0-9;]*m", "", s))


def _boite(titre, entrees, couleur):
    """Construit les lignes d'une boîte encadrée de largeur fixe."""
    dedans = LARGEUR_BOITE - 2
    t = f" {titre} "
    reste = dedans - len(t)
    g = max(reste // 2, 0)
    d = max(reste - g, 0)
    lignes = [couleur + GRAS + "┌" + "─" * g + t + "─" * d + "┐" + BASE]
    for num, label in entrees:
        corps = f" {OR}[{num:>2}]{TEXTE} {label}"
        pad = dedans - _long_visible(corps)
        lignes.append(couleur + "│" + BASE + corps + " " * max(pad, 0) + couleur + "│" + BASE)
    lignes.append(couleur + "└" + "─" * dedans + "┘" + BASE)
    return lignes


def menu(animer=True):
    """Affiche les fonctions de Black Jack en boîtes, deux par rangée."""
    sections = [
        ("♠ TABLE — L'IA", [
            ("1", "Discuter (tape ton message)"),
            ("2", "Recherche web sourcée"),
            ("3", "CODEX — coder (C++, Python, web…)"),
            ("4", "Nouvelle partie (efface la mémoire)"),
        ], VERT),
        ("♥ STRATÉGIE BLACKJACK", [
            ("5", "Stratégie de base"),
            ("6", "Apprendre à compter (Hi-Lo)"),
            ("7", "Quiz : que faire ?"),
        ], ROUGE),
        ("♦ SYSTÈME — ma machine", [
            ("8", "Infos système"),
            ("9", "Espace disque"),
            ("10", "Lancer un programme"),
        ], OR),
        ("♣ RÉSEAU — ma connexion", [
            ("11", "Mon adresse IP"),
            ("12", "Tester ma connexion (ping)"),
            ("13", "Mes connexions actives"),
        ], CYAN),
    ]
    anim, globals()["ANIMATIONS"] = ANIMATIONS, ANIMATIONS and animer
    marge = max((largeur() - (2 * LARGEUR_BOITE + 3)) // 2, 0)
    for i in range(0, len(sections), 2):
        gauche = _boite(*sections[i])
        droite = _boite(*sections[i + 1]) if i + 1 < len(sections) else None
        vide = " " * LARGEUR_BOITE
        hauteur = max(len(gauche), len(droite) if droite else 0)
        for j in range(hauteur):
            lg = gauche[j] if j < len(gauche) else vide
            ligne = BASE + " " * marge + lg
            if droite:
                ligne += "   " + (droite[j] if j < len(droite) else vide)
            _ecrire(ligne + BASE + "\n")
            _pause(0.012)
        _ecrire("\n")
    globals()["ANIMATIONS"] = anim


# ---------- Fond animé du menu : pluie Matrix + titre arc-en-ciel ----------

LIGNE_TITRE = 2            # le logo commence à cette ligne de l'écran du menu
sur_menu = False           # vrai tant que l'écran du menu est affiché tel quel
_pulse = None
_grille_menu = None        # grille (char, fg, bg) de l'écran du menu
_menu_bas = 0              # nombre de lignes occupées par le menu
_titre_marge = 0           # marge gauche du logo dans le menu
_taille_menu = None        # taille du terminal au moment de composer le menu
_modele_menu = ""          # nom affiché, pour recomposer après un redimensionnement
_menu_offset = 0           # marge gauche pour centrer le menu dans la fenêtre

# --- Les deux as qui tournent au centre du menu (A♣ + A♠, comme la photo) ---
_cartes_actif = False
_cartes_cx = _cartes_cy = 0            # centre du couloir des cartes (grille menu)
_cartes_r0 = _cartes_r1 = 0            # bornes verticales de la zone réservée
_cartes_x0 = _cartes_x1 = 0            # bornes horizontales de la zone réservée
_VIT_CARTES = 0.13                     # vitesse de rotation (rad / image ≈ 1 tour / 3,7 s)


def _dessiner_cartes_centre(grille, W, angle):
    """Pose la paire d'as (A♠ derrière-droite, A♣ devant-gauche) tournés de `angle`."""
    if not _cartes_actif:
        return
    H = len(grille)
    clubs, spades = _as_centre()
    _poser_carte_spin(grille, W, H, _cartes_cx + 3, _cartes_cy, spades, angle)   # derrière
    _poser_carte_spin(grille, W, H, _cartes_cx - 3, _cartes_cy, clubs, angle)    # devant


def _animer_cartes_centre(f):
    """Efface la zone des cartes dans la grille du menu et y redessine la paire
    tournée selon l'image f : appelé à chaque repeint → rotation permanente."""
    if not (_cartes_actif and _grille_menu):
        return
    W = len(_grille_menu[0])
    for ry in range(_cartes_r0, _cartes_r1 + 1):     # efface (fond sombre, pas de pluie)
        if 0 <= ry < len(_grille_menu):
            row = _grille_menu[ry]
            for cx in range(_cartes_x0, _cartes_x1 + 1):
                if 0 <= cx < W:
                    row[cx] = [" ", "", None]
    _dessiner_cartes_centre(_grille_menu, W, f * _VIT_CARTES)

# --- Console vivante (barre du haut + stats en direct) ---
_titre_haut = 2            # ligne où commence le logo (après la barre du haut)
_ligne_horloge = 0         # ligne de l'horloge
_col_horloge = 0           # colonne de l'horloge
_ligne_stats = 2           # ligne des jauges CPU/RAM/disque
_ip_cache = ""             # IP locale (calculée une fois)
_op_cache = ("", "")       # (utilisateur, machine)
_cpu_prev = None           # échantillon CPU précédent
HDR_BG = _fond(14, 18, 28)        # fond de l'entête
BAR_BG = _fond(26, 34, 50)        # fond de la barre de titre (ligne 0)


def _stat_cpu():
    """Charge CPU en % (échantillonnée entre deux appels). None si indispo."""
    global _cpu_prev
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern),
                                                  ctypes.byref(user))
            q = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            idl, tot = q(idle), q(kern) + q(user)
        else:
            with open("/proc/stat") as f:
                v = [int(p) for p in f.readline().split()[1:]]
            idl, tot = v[3] + v[4], sum(v)
        if _cpu_prev is None:
            _cpu_prev = (idl, tot)
            return None
        di, dt = idl - _cpu_prev[0], tot - _cpu_prev[1]
        _cpu_prev = (idl, tot)
        return max(0, min(100, int(100 * (1 - di / dt)))) if dt > 0 else None
    except Exception:
        return None


def _stat_ram():
    """% de RAM utilisée. None si indispo."""
    try:
        if os.name == "nt":
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                            ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong),
                            ("e", ctypes.c_ulonglong), ("f", ctypes.c_ulonglong),
                            ("g", ctypes.c_ulonglong)]
            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return int(ms.dwMemoryLoad)
        with open("/proc/meminfo") as f:
            d = {}
            for line in f:
                parts = line.split()
                d[parts[0].rstrip(":")] = int(parts[1])
        tot = d["MemTotal"]
        dispo = d.get("MemAvailable", d.get("MemFree", 0))
        return int(100 * (tot - dispo) / tot) if tot else None
    except Exception:
        return None


def _stat_disque():
    try:
        return int(100 * shutil.disk_usage("C:\\" if os.name == "nt" else "/").used
                   / shutil.disk_usage("C:\\" if os.name == "nt" else "/").total)
    except Exception:
        return None


def _ip_locale():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "—"


def _operateur():
    import getpass
    import socket
    try:
        return getpass.getuser(), socket.gethostname()
    except Exception:
        return "operateur", "machine"


def _jauge(pct, w=8):
    if pct is None:
        return "·" * w
    n = max(0, min(w, int(round(pct / 100.0 * w))))
    return "▓" * n + "░" * (w - n)


def _coul_niveau(pct):
    if pct is None:
        return DISCRET
    if pct < 60:
        return _txt(90, 220, 140)
    if pct < 85:
        return _txt(240, 190, 90)
    return _txt(240, 90, 90)


_sess_id = ""              # identifiant de session affiché dans l'entête
_ia_turbo = False          # état de l'IA (True = mode TURBO en ligne)
_ia_modele = ""            # nom du modèle IA affiché (local ou turbo)


def definir_etat_ia(turbo, modele):
    """Appelé par ia.py pour que l'entête reflète le mode IA (local / TURBO)."""
    global _ia_turbo, _ia_modele
    _ia_turbo = bool(turbo)
    _ia_modele = modele or ""


def _poser_horloge(grille, W):
    if not (0 <= _ligne_horloge < len(grille)):
        return
    h = time.strftime("%H:%M:%S")
    row = grille[_ligne_horloge]
    for i, ch in enumerate(h):
        c = _col_horloge + i
        if 0 <= c < W:
            row[c] = [ch, _txt(160, 225, 255), BAR_BG]


def _poser_stats(grille, W):
    if not (0 <= _ligne_stats < len(grille)):
        return
    cpu, ram, disque = _stat_cpu(), _stat_ram(), _stat_disque()
    pf = lambda p: (f"{p:>3}%" if p is not None else " --%")
    seg = [("CPU ", DISCRET), (_jauge(cpu), _coul_niveau(cpu)), (" " + pf(cpu), _coul_niveau(cpu)),
           ("   RAM ", DISCRET), (_jauge(ram), _coul_niveau(ram)), (" " + pf(ram), _coul_niveau(ram)),
           ("   DISQUE ", DISCRET), (_jauge(disque), _coul_niveau(disque)), (" " + pf(disque), _coul_niveau(disque)),
           ("   IP " + (_ip_cache or "—"), _txt(120, 200, 230))]
    total = sum(len(t) for t, _ in seg)
    row = grille[_ligne_stats]
    for c in range(W):
        row[c] = [" ", None, HDR_BG]
    x = max((W - total) // 2, 1)
    for t, coul in seg:
        for ch in t:
            if 0 <= x < W:
                row[x] = [ch, coul, HDR_BG]
            x += 1


def _poser_entete(grille, W, modele):
    """Barre du haut, épurée : ♠ BLACK JACK · badge EN LIGNE/HORS-LIGNE · horloge.
    (Plus de CPU/RAM/disque/IP/opérateur : seul l'état en ligne/hors-ligne reste.)"""
    if len(grille) < 1:
        return
    row0 = grille[0]
    for c in range(W):
        row0[c] = [" ", None, BAR_BG]
    for i, ch in enumerate("♠ BLACK JACK"):          # marque à gauche
        if 2 + i < W:
            row0[2 + i] = [ch, _txt(235, 70, 80) if ch == "♠" else _txt(190, 205, 230), BAR_BG]
    if _ia_turbo:                                     # badge état IA (centré)
        badge = f"● EN LIGNE · {_ia_modele}"
        cpt = _txt(90, 235, 140)
    else:
        badge = "○ HORS-LIGNE · IA locale"
        cpt = _txt(150, 160, 178)
    mx = max((W - len(badge)) // 2, 0)
    for i, ch in enumerate(badge):
        if 0 <= mx + i < W:
            row0[mx + i] = [ch, cpt if ch in "●○" else _txt(150, 165, 188), BAR_BG]


def _menu_reinit():
    """(Compat : le menu se repeint entièrement à chaque image — rien à garder.)"""
    return


def _repaint_menu(i_teinte, tetes, f):
    """Repeint TOUT le menu (pluie + titre teinté + les deux as qui tournent) à
    chaque image — donc ça se corrige tout seul (pas d'accumulation d'erreurs),
    MAIS :
      · enveloppé dans une MISE À JOUR SYNCHRONISÉE (mode 2026) → le terminal
        affiche l'image d'un seul coup : AUCUNE déchirure (souci Windows Terminal) ;
      · SANS effacement de ligne (\\x1b[K) → pas de « flash » des cartes blanches."""
    _animer_cartes_centre(f)                      # fait tourner les as (A♣ + A♠)
    W = len(_grille_menu[0])
    dec = _menu_offset
    espaces = " " * dec
    buf = [_SYNC_DEBUT, "\x1b7"]                   # sync + sauve le curseur (ligne de saisie)
    for ry in range(_menu_bas):
        row = _grille_menu[ry]
        bout = ["\x1b[%d;1H" % (ry + 1), BASE, espaces]   # position, PAS de \x1b[K
        cfg = cbg = None
        for x in range(W):
            ch, fg, bg = row[x]
            if ch == " " and fg is None and bg is None and tetes is not None:   # case vide → pluie ?
                k = int(tetes[x][0]) - ry
                if 0 <= k < tetes[x][2]:
                    ch2 = CARS_PLUIE[(x * 7 + ry * 13 + f) % len(CARS_PLUIE)]
                    if k == 0:
                        dfg = _txt(120, 220, 150)
                    else:
                        v = 1 - k / tetes[x][2]
                        dfg = _txt(int(22 + 50 * v), int(60 + 105 * v), int(40 + 65 * v))
                    dbg = FOND
                else:
                    ch2, dfg, dbg = " ", TEXTE, FOND
            else:
                ch2, dfg, dbg = ch, (fg or TEXTE), (bg or FOND)
            if dfg != cfg:
                bout.append(dfg); cfg = dfg
            if dbg != cbg:
                bout.append(dbg); cbg = dbg
            bout.append(ch2)
        buf.append("".join(bout))
        if _titre_haut <= ry < _titre_haut + LOGO_ROWS and _LOGO_TEINTES:   # logo teinté par-dessus
            ligne = _LOGO_TEINTES[i_teinte][ry - _titre_haut]
            buf.append("\x1b[%d;%dH" % (ry + 1, 1 + dec + _titre_marge) + BASE + ligne)
    buf.append("\x1b8")                            # restaure le curseur
    buf.append(_SYNC_FIN)
    return "".join(buf)


class _Pulsation(threading.Thread):
    """Pluie de code dans le fond du menu + titre qui cycle l'arc-en-ciel néon."""
    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()

    def _nouvelles_tetes(self, W, bas, rng):
        tetes = []
        for _ in range(W):
            if rng.random() < PLUIE_DENSITE:
                tetes.append([rng.uniform(-bas, 0.0), rng.uniform(0.6, 1.5) * PLUIE_VITESSE,
                              rng.randint(4, max(5, bas - 2))])
            else:
                tetes.append([0.0, 0.0, 0])
        return tetes

    def run(self):
        if not _LOGO_TEINTES or not _grille_menu:
            return
        rng = random.Random()
        W, bas = len(_grille_menu[0]), _menu_bas
        tetes = self._nouvelles_tetes(W, bas, rng)
        n, i, f = len(_LOGO_TEINTES), 0, 0
        while not self.stop.is_set():
            # redimensionnement de la fenêtre : on recompose le menu à la nouvelle taille
            if _dim() != _taille_menu:
                afficher_menu(_modele_menu)            # recompose + réaffiche à la bonne taille
                _ecrire(_invite())                     # ré-affiche l'invite de saisie
                W, bas = len(_grille_menu[0]), _menu_bas
                tetes = self._nouvelles_tetes(W, bas, rng)
                continue
            for t in tetes:
                if t[2] == 0:
                    continue
                t[0] += t[1]
                if t[0] - t[2] > bas:
                    t[0] = rng.uniform(-bas, 0.0)
                    t[1] = rng.uniform(0.6, 1.5) * PLUIE_VITESSE
                    t[2] = rng.randint(4, max(5, bas - 2))
            _poser_horloge(_grille_menu, W)            # horloge en direct
            if f % 12 == 0:
                _maj_moniteur(_grille_menu, W)
            teinte = (i % n) if TITRE_CYCLE else 0
            _ecrire(_repaint_menu(teinte, tetes, f))
            i += 1
            f += 1
            self.stop.wait(0.09)


def demarrer_pulsation():
    global _pulse
    # Le fond animé (thread qui redessine) n'est lancé QUE si explicitement activé :
    # par défaut le menu est statique (aucun redessin concurrent → affichage stable).
    if MENU_ANIME and ANIMATIONS and _pulse is None and _grille_menu:
        _pulse = _Pulsation()
        _pulse.start()


def arreter_pulsation():
    global _pulse
    if _pulse is not None:
        _pulse.stop.set()
        _pulse.join()
        _pulse = None
        if _grille_menu:
            _menu_reinit()
            _ecrire(_repaint_menu(0, None, 0))   # menu net, sans pluie


def _tetes_pluie(W, bas, rng):
    tetes = []
    for _ in range(W):
        if rng.random() < PLUIE_DENSITE:
            tetes.append([rng.uniform(-bas, 0.0), rng.uniform(0.6, 1.5) * PLUIE_VITESSE,
                          rng.randint(4, max(5, bas - 2))])
        else:
            tetes.append([0.0, 0.0, 0])
    return tetes


def _rendu_ligne_saisie(texte, W):
    """Ligne d'invite dessinée SOUS le menu. Comme on l'affiche nous-mêmes, ce
    qu'on tape reste toujours visible (pas de course avec l'écho du terminal)."""
    y = _menu_bas + 2
    prompt = "♠ black-jack ▸ "
    marge = _menu_offset + 2
    dispo = max(W - marge - len(prompt) - 2, 8)
    vis = texte[-dispo:] if len(texte) > dispo else texte
    return (f"\x1b[{y};1H" + BASE + "\x1b[K" + " " * marge
            + OR + GRAS + prompt + BASE + BLANC + vis
            + _txt(120, 235, 150) + "█" + BASE)


def saisie_menu():
    """Affiche le menu animé ET lit la saisie sur un seul thread : ce qu'on tape
    s'affiche toujours. Renvoie la ligne validée (Entrée)."""
    if not (_grille_menu and MENU_ANIME and ANIMATIONS and _LOGO_TEINTES
            and sys.stdout.isatty()):
        return demander_saisie()                 # repli : saisie classique
    rng = random.Random()
    W, bas = len(_grille_menu[0]), _menu_bas
    tetes = _tetes_pluie(W, bas, rng)
    n = len(_LOGO_TEINTES)
    texte, f = [], 0
    _cacher_curseur()
    try:
        with _Clavier() as kb:
            if not kb.ok:                        # pas de clavier brut → repli
                _montrer_curseur()
                return demander_saisie()
            while True:
                if _dim() != _taille_menu:       # fenêtre redimensionnée
                    afficher_menu(_modele_menu)
                    W, bas = len(_grille_menu[0]), _menu_bas
                    tetes = _tetes_pluie(W, bas, rng)
                for t in tetes:
                    if t[2] == 0:
                        continue
                    t[0] += t[1]
                    if t[0] - t[2] > bas:
                        t[0] = rng.uniform(-bas, 0.0)
                        t[1] = rng.uniform(0.6, 1.5) * PLUIE_VITESSE
                        t[2] = rng.randint(4, max(5, bas - 2))
                _poser_horloge(_grille_menu, W)
                if f % 12 == 0:
                    _maj_moniteur(_grille_menu, W)
                teinte = (f % n) if TITRE_CYCLE else 0
                _ecrire(_repaint_menu(teinte, tetes, f) + _rendu_ligne_saisie("".join(texte), W))
                for ev in kb.evenements():
                    quoi = ev[0]
                    if quoi == "enter":
                        return "".join(texte)
                    if quoi == "ctrl-c":
                        raise KeyboardInterrupt
                    if quoi == "back":
                        if texte:
                            texte.pop()
                    elif quoi == "char":
                        texte.append(ev[1])
                f += 1
                time.sleep(0.09)                      # cadence plus douce (fenêtre agrandie)
    finally:
        _montrer_curseur()


def ligne_entete(gauche, droite=""):
    """La barre du haut (texte brut à gauche et à droite), sans retour à la ligne."""
    W = max(min(largeur(), 400) - 1, 20)          # 1 colonne de moins : pas de retour auto en fin de ligne
    plein = max(W - len(gauche) - len(droite), 1)
    return BAR_BG + _txt(205, 215, 235) + (gauche + " " * plein + droite)[:W] + BASE


def debut_conversation(sous_titre="", droite="« menu » pour revenir  "):
    """Quitte le menu animé pour un écran propre (conversation IA / jeu / sortie)."""
    global sur_menu
    sur_menu = False
    _montrer_curseur()
    _ecrire(BASE + "\x1b[2J\x1b[H")
    W = min(largeur(), 400)
    gauche = "  ◢ BLACK JACK ◣" + (f"   ·   {sous_titre}" if sous_titre else "")
    _ecrire(ligne_entete(gauche, droite) + "\n")
    _ecrire(DISCRET + "  " + "─" * min(W - 4, 100) + BASE + "\n")


def dessiner(lignes):
    """Redessine tout l'écran sur place (sans effacer d'abord : pas de scintillement)."""
    _ecrire("\x1b[H" + "".join(BASE + l + "\x1b[K\n" for l in lignes) + "\x1b[J")


def vider_clavier():
    """Jette les touches en attente (à appeler avant une question au clavier)."""
    with _Clavier() as kb:
        kb.vider()


def lire_touche(valides=None):
    """Attend UNE touche, sans appuyer sur Entrée.

    valides : ensemble de jetons acceptés — des caractères en minuscules ('h') et/ou
    les noms 'enter' / 'esc'. None = n'importe quelle touche. Renvoie le jeton.
    Repli si le terminal n'a pas de lecture brute : on lit une ligne avec input()."""
    attendus = set(valides) if valides else None
    with _Clavier() as kb:
        if kb.ok:
            kb.vider()
            while True:
                for ev in kb.evenements():
                    quoi = ev[0]
                    if quoi == "ctrl-c":
                        raise KeyboardInterrupt
                    if quoi in ("enter", "esc"):
                        jeton = quoi
                    elif quoi == "char":
                        jeton = ev[1].lower()
                    else:
                        continue
                    if attendus is None or jeton in attendus:
                        return jeton
                time.sleep(0.02)
    while True:                                   # repli : pas de clavier brut
        s = input().strip().lower()
        jeton = s[:1] if s else "enter"
        if attendus is None or jeton in attendus:
            return jeton


def attendre_touche(message="Appuie sur une touche pour revenir au menu"):
    _ecrire("\n  " + DISCRET + "╾  " + message + "  ╼" + BASE)
    return lire_touche()

def _ligne_ansi(rangee):
    """Rend une ligne de cellules (char, fg, bg) en une chaîne ANSI."""
    morceaux, cfg, cbg = [BASE], None, None
    for ch, fg, bg in rangee:
        dfg, dbg = fg or TEXTE, bg or FOND
        if dfg != cfg:
            morceaux.append(dfg); cfg = dfg
        if dbg != cbg:
            morceaux.append(dbg); cbg = dbg
        morceaux.append(ch)
    return "".join(morceaux)


# Couleurs d'enseigne (une par panneau), palette casino/hacker épurée
C_PIQUE = _txt(212, 222, 238)    # ♠ argent froid
C_COEUR = _txt(236, 82, 96)      # ♥ rouge
C_CARREAU = _txt(240, 182, 84)   # ♦ ambre / or
C_TREFLE = _txt(84, 212, 150)    # ♣ émeraude


def _boite_cellules(titre, entrees, couleur):
    """Un panneau élégant (coins arrondis, titre à gauche) en cellules (char,fg,bg)."""
    dedans = LARGEUR_BOITE - 2
    t = f"─ {titre} "
    reste = max(dedans - len(t), 0)
    rows = [[(ch, couleur, None) for ch in "╭" + t + "─" * reste + "╮"]]
    for num, label in entrees:
        cells = [(" ", "", None), ("▸", couleur, None), (" ", "", None)]
        cells += [(c, OR, None) for c in f"{num:>2}"]
        cells += [(c, DISCRET, None) for c in " · "]
        cells += [(c, TEXTE, None) for c in label]
        while len(cells) < dedans:
            cells.append((" ", "", None))      # "" = occupé (pas de pluie), rendu vide
        rows.append([("│", couleur, None)] + cells[:dedans] + [("│", couleur, None)])
    rows.append([(ch, couleur, None) for ch in "╰" + "─" * dedans + "╯"])
    return rows


def _poser_signature(grille, W, row_top):
    """Deux mini-cartes A♠ J♠ + « 21 », la signature Black Jack, sous le logo."""
    cartes = [("A", "♠"), ("J", "♠")]
    cw = 5
    bloc = len(cartes) * (cw + 1) - 1
    tag = "  21  ·  table privée"
    x0 = max((W - (bloc + len(tag))) // 2, 0)
    bord = _txt(120, 130, 150)
    argent = _txt(228, 232, 242)
    def put(r, c, ch, col):
        if 0 <= r < len(grille) and 0 <= c < W:
            grille[r][c] = [ch, col, None]
    for ci, (v, s) in enumerate(cartes):
        cx = x0 + ci * (cw + 1)
        for dx, ch in enumerate("┌───┐"):
            put(row_top, cx + dx, ch, bord)
        scol = C_COEUR if s in "♥♦" else argent
        for dx, (ch, col) in enumerate([("│", bord), (v, argent), (" ", None), (s, scol), ("│", bord)]):
            put(row_top + 1, cx + dx, ch, col or bord)
        for dx, ch in enumerate("└───┘"):
            put(row_top + 2, cx + dx, ch, bord)
    tr, tx = row_top + 1, x0 + bloc
    for i, ch in enumerate(tag):
        put(tr, tx + i, ch, OR if ch.isdigit() else DISCRET)


# --- Panneaux « opérateur » (dashboard) ---
NEON_V = _txt(90, 240, 150)        # vert néon
NEON_C = _txt(90, 220, 240)        # cyan néon
_sys_col = -1                      # colonne des jauges (maj en direct)
_sys_row0 = -1                     # 1re ligne de jauge
_sys_inner = 0                     # largeur intérieure du panneau moniteur


def _panneau(titre, contenu, largeur, couleur):
    """Panneau encadré à titre entre crochets : ╭─[ TITRE ]──╮ … ╰──╯."""
    inner = largeur - 2
    etiq = f"[ {titre} ]"
    reste = max(inner - len(etiq) - 1, 0)
    rows = [[(ch, couleur, None) for ch in "╭─" + etiq + "─" * reste + "╮"]]
    for ligne in contenu:
        cells = [(" ", "", None)]
        for seg_txt, seg_col in ligne:
            for ch in seg_txt:
                cells.append((ch, seg_col or "", None))
        while len(cells) < inner:
            cells.append((" ", "", None))
        rows.append([("│", couleur, None)] + cells[:inner] + [("│", couleur, None)])
    rows.append([(ch, couleur, None) for ch in "╰" + "─" * inner + "╯"])
    return rows


def _pf(p):
    return f"{p:>3}%" if p is not None else " --%"


def _contenu_moniteur(inner):
    barw = max(inner - 10, 4)
    cpu, ram, dsk = _stat_cpu(), _stat_ram(), _stat_disque()
    jl = lambda lbl, p: [(f"{lbl} ", DISCRET), (_jauge(p, barw), _coul_niveau(p)),
                         (" " + _pf(p), _coul_niveau(p))]
    return [jl("CPU", cpu), jl("MÉM", ram), jl("DSK", dsk)]


def _maj_moniteur(grille, W):
    """Réécrit les 3 jauges CPU/MÉM/DSK en direct (sans recomposer le menu)."""
    if _sys_col < 0 or _sys_row0 < 0:
        return
    for i, ligne in enumerate(_contenu_moniteur(_sys_inner)):
        r = _sys_row0 + i
        if not (0 <= r < len(grille)):
            continue
        x = _sys_col + 1
        for c in range(_sys_col + 1, _sys_col + 1 + _sys_inner):
            if 0 <= c < W:
                grille[r][c] = [" ", "", None]
        for seg_txt, seg_col in ligne:
            for ch in seg_txt:
                if 0 <= x < W:
                    grille[r][x] = [ch, seg_col or "", None]
                x += 1


def _contenu_reseau(inner):
    etat = ("● EN LIGNE", NEON_V) if _ia_turbo else ("○ HORS-LIGNE", DISCRET)
    return [
        [("IP   ", DISCRET), ((_ip_cache or "—"), _txt(120, 220, 200))],
        [("IA   ", DISCRET), etat],
        [("", "")],
        [("◆ TAPIS   ", DISCRET), ("OK", NEON_V)],
        [("◆ COFFRE  ", DISCRET), ("OK", NEON_V)],
        [("◆ SCAN    ", DISCRET), ("…", _txt(240, 190, 90))],
    ]


# ---------- Table de stratégie Black Jack (option 5) ----------
# Les données (tables S/H/D/P) vivent dans strategie.py, partagées avec le jeu et le quiz.
_STRAT_COUL = {"S": _txt(90, 230, 140), "H": _txt(150, 160, 175),
               "D": _txt(240, 185, 80), "P": _txt(95, 200, 245)}


def montrer_strategie():
    """Table de stratégie de base : les 3 tableaux côte à côte si la fenêtre est large,
    sinon les uns sous les autres."""
    import strategie as st
    debut_conversation("STRATÉGIE DE BASE · 21", droite="")

    def lignes_bloc(titre, lignes, larg):
        out = [OR + GRAS + "▸ " + titre + BASE,
               DISCRET + " " * 7 + "".join(f"{c:>{larg}}" for c in st.COLONNES) + BASE]
        for nom, codes in lignes:
            out.append(_txt(205, 212, 225) + f"{nom:>5}  "
                       + "".join(_STRAT_COUL.get(c, TEXTE) + f"{c:>{larg}}" for c in codes) + BASE)
        return out

    blocs = [("MAINS DURES", st.DUR), ("MAINS SOUPLES (As + carte)", st.SOUPLE),
             ("PAIRES", st.PAIRES)]
    _ecrire("\n  " + _txt(120, 210, 235) + "Colonnes : carte visible du croupier  "
            + "(2 3 4 5 6 7 8 9 10 A)" + BASE + "\n\n")
    larg_bloc = 7 + 10 * 3
    if largeur() >= 3 * larg_bloc + 2 * 4 + 4:                      # côte à côte (cellules de 3)
        cols = [lignes_bloc(t, l, 3) for t, l in blocs]
        haut = max(len(c) for c in cols)
        for i in range(haut):
            morceaux = []
            for c in cols:
                cell = c[i] if i < len(c) else ""
                morceaux.append(cell + " " * max(larg_bloc - _long_visible(cell), 0))
            _ecrire("  " + "    ".join(morceaux) + BASE + "\n")
    else:                                                          # empilé (cellules de 4)
        for t, l in blocs:
            for ligne in lignes_bloc(t, l, 4):
                _ecrire("  " + ligne + "\n")
            _ecrire("\n")
    _ecrire("\n  " + _STRAT_COUL["S"] + "S" + DISCRET + " rester    "
            + _STRAT_COUL["H"] + "H" + DISCRET + " tirer    "
            + _STRAT_COUL["D"] + "D" + DISCRET + " doubler    "
            + _STRAT_COUL["P"] + "P" + DISCRET + " séparer" + BASE + "\n")
    _ecrire("  " + DISCRET + "6 jeux · le croupier reste sur 17 · double après séparation autorisé"
            + BASE + "\n")


def _composer_menu(modele):
    """L'écran principal, épuré et centré : barre, logo, signature A♠ J♠,
    les 4 sections du menu, puis l'invite (plus de panneaux latéraux)."""
    global _ligne_horloge, _col_horloge, _ip_cache, _sys_col, _sys_row0, _sys_inner
    global _cartes_actif, _cartes_cx, _cartes_cy, _cartes_r0, _cartes_r1, _cartes_x0, _cartes_x1
    taille = _Taille()
    # Les 4 encadrés sont écartés pour laisser un COULOIR CENTRAL où les deux as
    # (A♣ + A♠) tournent en permanence — si la fenêtre est assez large.
    _GAP_CARTES = 2 * _LARG_CARTE - 2                  # ~28 colonnes au centre
    cartes_centre = (taille.columns - 1) >= (2 * LARGEUR_BOITE + _GAP_CARTES + 2)
    gap = _GAP_CARTES if cartes_centre else 3
    # la pluie remplit toute la largeur ; jamais plus étroit que le logo (sinon
    # sa pose déborderait de la grille sur une fenêtre très étroite)
    W = max(min(taille.columns - 1, 400), 2 * LARGEUR_BOITE + gap, LOGO_COLS)
    if not _ip_cache:
        _ip_cache = _ip_locale()
    centre_w = 2 * LARGEUR_BOITE + gap
    marge = max((W - centre_w) // 2, 0)                # menu centré (plus de panneaux latéraux)
    _sys_col = _sys_row0 = -1
    ml = max((W - LOGO_COLS) // 2, 0)
    _ligne_horloge = 0
    _col_horloge = max(W - 10, 0)
    sections = [
        ("♠ TABLE · L'IA", [("1", "Discuter (tape ton message)"), ("2", "Recherche web sourcée"),
                            ("3", "CODEX · coder (C++, Python…)"),
                            ("4", "Nouvelle partie (reset mémoire)"),
                            ("16", "Académie (apprendre à coder)")], C_PIQUE),
        ("♥ BLACK JACK · 21", [("15", "JOUER · partie de Black Jack"), ("5", "Table de stratégie"),
                               ("6", "Entraîneur Hi-Lo (compter)"),
                               ("7", "Quiz : que faire ?")], C_COEUR),
        ("♦ SYSTÈME · ma machine", [("8", "Infos système"), ("9", "Espace disque"),
                                    ("10", "Lancer un programme"),
                                    ("14", "Paramètres (IA, Spotify, son…)"),
                                    ("17", "Optimisation (nettoyage)"),
                                    ("18", "Coffre (chiffrer mes fichiers)")], C_CARREAU),
        ("♣ RÉSEAU · ma connexion", [("11", "Mon adresse IP"), ("12", "Tester ma connexion (ping)"),
                                     ("13", "Mes connexions actives")], C_TREFLE),
    ]
    boites = [_boite_cellules(*s) for s in sections]
    lignes = []

    def at(r):
        while len(lignes) <= r:
            lignes.append([[" ", None, None] for _ in range(W)])
        return lignes[r]

    def texte(r, col, s, couleur):
        row = at(r)
        for i, ch in enumerate(s):
            if 0 <= col + i < W:
                row[col + i] = [ch, couleur, None]

    def poser(rtop, col, boite):
        for i, brow in enumerate(boite):
            row = at(rtop + i)
            for j, cell in enumerate(brow):
                row[col + j] = list(cell)

    for r in range(_titre_haut + LOGO_ROWS):          # réserve la barre + la zone logo
        at(r)
    _poser_entete(lignes, W, modele)                  # barre épurée (état en ligne/hors-ligne)
    _poser_horloge(lignes, W)
    for cr in range(LOGO_ROWS):                       # logo (teinte de base, cyclé par le thread)
        row = at(_titre_haut + cr)
        for x in range(LOGO_COLS):
            row[ml + x] = ["▀", _txt(*LOGO[2 * cr][x]), _fond(*LOGO[2 * cr + 1][x])]
    base_sig = _titre_haut + LOGO_ROWS + 1            # signature A♠ J♠ · 21
    for r in range(base_sig, base_sig + 3):
        at(r)
    _poser_signature(lignes, W, base_sig)
    r1 = base_sig + 4                                 # 1ère rangée de panneaux (menu central)
    col_d = marge + LARGEUR_BOITE + gap               # colonne des encadrés de droite
    poser(r1, marge, boites[0]); poser(r1, col_d, boites[1])
    r2 = r1 + max(len(boites[0]), len(boites[1])) + 1
    poser(r2, marge, boites[2]); poser(r2, col_d, boites[3])
    rh = r2 + max(len(boites[2]), len(boites[3])) + 1

    _cartes_actif = cartes_centre
    if cartes_centre:                                 # couloir central : les deux as qui tournent
        bas_boites = r2 + max(len(boites[2]), len(boites[3])) - 1
        _cartes_cx = marge + LARGEUR_BOITE + gap // 2
        _cartes_cy = (r1 + bas_boites) // 2
        _cartes_x0 = marge + LARGEUR_BOITE + 1        # zone large (couvre toute l'étendue
        _cartes_x1 = col_d - 1                        # des cartes, épaisseur comprise)
        _cartes_r0 = max(_cartes_cy - _HAUT_CARTE // 2 - 1, r1)
        _cartes_r1 = min(_cartes_cy + _HAUT_CARTE // 2 + 1, bas_boites)
        for ry in range(_cartes_r0, _cartes_r1 + 1):  # réserve la zone (fond sombre, pas de pluie)
            row = at(ry)
            for cx in range(_cartes_x0, _cartes_x1 + 1):
                if 0 <= cx < W:
                    row[cx] = [" ", "", None]
        _dessiner_cartes_centre(lignes, W, 0.0)       # pose les as au repos (face)

    rh += 1
    aide = "╾  tape un numéro · un message pour l'IA · « menu » · « exit »  ╼"
    texte(rh, max((W - len(aide)) // 2, 0), aide, DISCRET)
    bas = rh + 1
    while len(lignes) < bas:
        at(bas - 1)
    return lignes[:bas], bas, ml


def afficher_menu(modele):
    """Compose et pose l'écran du menu (titre en haut), prêt pour le fond animé."""
    global sur_menu, _grille_menu, _menu_bas, _titre_marge, _taille_menu, _modele_menu, _menu_offset
    taille = _Taille()
    grille, bas, ml = _composer_menu(modele)
    _grille_menu, _menu_bas, _titre_marge = grille, bas, ml
    _modele_menu = modele
    _taille_menu = (taille.columns, taille.lines)
    _menu_offset = max((taille.columns - len(grille[0])) // 2, 0)   # centre le menu
    _menu_reinit()                                 # le prochain repeint sera complet
    dec = " " * _menu_offset
    out = [BASE + "\x1b[2J\x1b[H"]
    for row in grille:
        out.append(BASE + dec + _ligne_ansi(row) + "\x1b[K\n")
    _ecrire("".join(out))
    sur_menu = True


def _distribue_blackjack():
    """Petite signature : Black Jack distribue une main gagnante (A♠ + J♠ = 21)."""
    if not ANIMATIONS:
        return
    effacer()
    _ecrire("\n\n\n")
    distribuer([("A", "♠"), ("J", "♠")])
    _ecrire("\n")
    clignoter("♠  B L A C K J A C K   ·   21  ♠", OR, 3)
    _pause(0.4)


def _boot_console(modele):
    """Boot de la console après le zoom : lignes qui s'écrivent avant le tableau de bord."""
    if not (ANIMATIONS and sys.stdout.isatty()):
        return
    u, _host = _operateur()
    etapes = [("RÉVEIL DU NOYAU", "OK"), ("DÉCHIFFREMENT DU COFFRE", "OK"),
              ("CONNEXION AU TAPIS", "OK"), (f"CHARGEMENT IA · {modele}", "OK"),
              (f"OPÉRATEUR AUTHENTIFIÉ · {u}", "ACCÈS")]
    taille = _Taille()
    W = max(min(taille.columns - 1, 400), 24)
    H = max(min(taille.lines - 1, 120), 10)
    larg = max(len(a) for a, _ in etapes) + 16
    gx = max((W - larg) // 2, 2)
    gy = max(H // 2 - len(etapes), 1)
    _ecrire(BASE + "\x1b[2J")
    for i, (txt, tag) in enumerate(etapes):
        y = gy + i
        _ecrire(f"\x1b[{y};{gx}H" + VERT + "> " + BASE + TEXTE + txt + " ")
        for _ in range(max(larg - len(txt) - 7 - len(tag), 1)):
            _ecrire(DISCRET + ".")
            time.sleep(0.006)
        _ecrire("  " + _txt(120, 255, 160) + GRAS + tag + BASE)
        time.sleep(0.11)
    time.sleep(0.34)
    _ecrire(BASE + "\x1b[2J\x1b[H")


def ecran_accueil(modele):
    """Écran de départ : l'œil + slogan + invite ENTRÉE/ÉCHAP, puis boot de la console.
    Renvoie True si on entre dans le menu, False si l'utilisateur quitte (ÉCHAP)."""
    initialiser()
    if ANIMATIONS and sys.stdout.isatty():
        if not _accueil_oeil(modele):      # ÉCHAP → on quitte proprement
            return False
        _boot_console(modele)              # déverrouillage → la console s'allume
    afficher_menu(modele)
    return True


def ecran_sortie():
    _ecrire("\n")
    machine_a_ecrire(_centrer("♠ ♥ ♦ ♣   À la prochaine partie !   ♣ ♦ ♥ ♠"), OR, 0.015)
    _pause(0.4)
    restaurer()


# ---------- Conversation ----------

def _invite():
    return "\n" + OR + GRAS + "  ♠ toi ▸ " + RESET + FOND + BLANC


def demander_saisie():
    _ecrire(_invite())
    try:
        return input()
    finally:
        _ecrire(BASE)


def demander_texte(invite):
    _ecrire("\n" + OR + "  " + invite + " › " + BLANC)
    try:
        return input().strip()
    finally:
        _ecrire(BASE)


def etiquette_ia():
    _ecrire("\n" + _txt(236, 82, 96) + GRAS + "  ◆ black jack ▸ " + BASE + TEXTE + " ")


def morceau_ia(texte):
    _ecrire(TEXTE + texte)


def fin_reponse():
    _ecrire(BASE + "\n")


def info(texte, couleur=DISCRET):
    _ecrire(BASE + couleur + texte + BASE + "\n")


def erreur(texte):
    info("✖ " + texte, ROUGE)


def demander_confirmation(commande):
    _ecrire("\n" + OR + "♦ Exécuter : " + BLANC + GRAS + commande + BASE + "\n")
    _ecrire(DISCRET + "   o = oui · n = non · t = oui à tout › " + BLANC)
    try:
        return input().strip().lower()
    finally:
        _ecrire(BASE)


class Animation:
    """Indicateur animé (enseignes qui tournent) pendant que Black Jack travaille.

    with Animation("Black Jack réfléchit"):
        ...
    """

    def __init__(self, texte="Black Jack réfléchit"):
        self.texte = texte
        self._stop = threading.Event()
        self._thread = None

    def _boucle(self):
        i = 0
        while not self._stop.is_set():
            symboles = ""
            for k in range(4):
                enseigne, _ = ENSEIGNES[(i + k) % 4]
                couleur = ROUGE if enseigne in "♥♦" else OR
                symboles += (couleur + GRAS if k == 0 else DISCRET) + enseigne + " "
            points = "." * (i % 4)
            _ecrire("\r\x1b[K" + symboles + BASE + DISCRET + self.texte + points + BASE)
            i += 1
            time.sleep(0.15)
        _ecrire("\r\x1b[K")

    def demarrer(self):
        if ANIMATIONS and self._thread is None:
            self._thread = threading.Thread(target=self._boucle, daemon=True)
            self._thread.start()
        elif not ANIMATIONS:
            _ecrire(DISCRET + self.texte + "...\n" + BASE)
        return self

    def arreter(self):
        if self._thread is not None:
            self._stop.set()
            self._thread.join()
            self._thread = None

    def __enter__(self):
        return self.demarrer()

    def __exit__(self, *exc):
        self.arreter()
