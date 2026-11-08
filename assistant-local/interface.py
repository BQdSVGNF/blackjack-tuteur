"""Interface console « Black Jack » : tapis vert sombre, cartes et animations.

Fonctionne dans le cmd de Windows 10/11 (couleurs ANSI 24 bits).
Mets la variable d'environnement BJ_SANS_ANIMATION=1 pour couper les animations.
"""
import colorsys
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

def _txt(r, g, b):
    return f"\x1b[38;2;{r};{g};{b}m"


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


def initialiser():
    """Active les couleurs et bascule sur un ÉCRAN ALTERNATIF (comme vim/htop) :
    pas d'historique de défilement, donc pas de doublons ni d'intro « scrollable »."""
    if os.name == "nt":
        os.system("")  # active le mode ANSI de la console Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _ecrire("\x1b[?1049h")            # écran alternatif
    _ecrire(BASE + "\x1b[2J\x1b[H")


def restaurer():
    """Revient à l'écran normal du terminal (fin propre, sans logos résiduels)."""
    _ecrire("\x1b[?25h")             # réaffiche le curseur
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


# On pré-calcule les variantes de teinte (le titre cyclera à travers tout l'arc-en-ciel).
_PAS_TEINTE = 48
_LOGO_TEINTES = ([_lignes_logo_teinte(i * 360 // _PAS_TEINTE) for i in range(_PAS_TEINTE)]
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
    """Ajoute un effet CRT : scanlines fixes + barre de balayage qui roule."""
    if not CRT or not grille:
        return grille
    H, W = len(grille), len(grille[0])
    for y in range(0, H, 3):                     # scanlines discrètes
        row = grille[y]
        for x in range(W):
            if row[x][0] == " " and row[x][1] is None:
                row[x] = ("─", _txt(13, 28, 32), None)
    bar = (f * 2) % (H + 6) - 3                   # barre lumineuse qui descend
    for yy in (bar, bar + 1):
        if 0 <= yy < H:
            row = grille[yy]
            for x in range(W):
                if row[x][0] in (" ", "─") and (row[x][1] is None or row[x][1] == _txt(13, 28, 32)):
                    row[x] = ("─", _txt(28, 58, 64), None)
    return grille


_crt_f = 0
_intro_offset = 0          # marge gauche pour centrer l'intro dans la fenêtre
_intro_voffset = 0         # marge haute pour centrer l'intro dans la fenêtre


def _rendu_grille(grille):
    """Transforme une grille de (char, fg, bg) en une image terminal (+ CRT).
    L'image (de taille W×H) est centrée dans le terminal réel via les marges
    _intro_offset (gauche) et _intro_voffset (haut), pour qu'elle ne se colle
    pas en haut à gauche quand la fenêtre est agrandie."""
    global _crt_f
    grille = _crt(grille, _crt_f)
    _crt_f += 1
    dec = " " * _intro_offset
    out = ["\x1b[H"]
    for _ in range(_intro_voffset):              # lignes vides au-dessus (centrage vertical)
        out.append(BASE + "\x1b[K\n")
    for rangee in grille:
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

    def get(self):
        if not self.ok:
            return None
        try:
            if self.nt:
                res = None
                while self.msvcrt.kbhit():
                    ch = self.msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):           # touche spéciale (flèche…)
                        if self.msvcrt.kbhit():
                            self.msvcrt.getwch()
                        continue
                    if ch in ("\r", "\n"):
                        res = "enter"
                    elif ch == "\x1b":
                        res = "esc"
                    elif ch == "\x03":
                        raise KeyboardInterrupt
                return res
            import select
            r, _, _ = select.select([self.fd], [], [], 0)
            if not r:
                return None
            ch = os.read(self.fd, 1)
            if ch in (b"\r", b"\n"):
                return "enter"
            if ch == b"\x03":
                raise KeyboardInterrupt
            if ch == b"\x1b":
                r2, _, _ = select.select([self.fd], [], [], 0.02)
                if r2:
                    os.read(self.fd, 2)                   # avale une séquence de flèche
                    return None
                return "esc"
            return None
        except KeyboardInterrupt:
            raise
        except Exception:
            return None


def _nouvelle_grille(W, H):
    return [[(" ", None, None) for _ in range(W)] for _ in range(H)]


# compression horizontale : une cellule du terminal est ~2× plus haute que large
_ASP = 2.05


def _oeil_geo(W, H):
    """Géométrie de l'œil (étiré) + les lignes où poser le slogan et l'invite."""
    cx = W // 2
    cy = int(H * 0.44)
    Wx = max(min(cx - 4, 100), 12)                # DEMI-largeur (œil tout en longueur)
    Hy = max(min(cy - 3, (H - cy) - 6, 10), 3)    # demi-hauteur (plus plat → très étiré)
    Ri = Hy - 0.3                                  # rayon vertical de l'iris
    r_slogan = min(cy + Hy + 3, H - 4)
    r_invite = min(cy + Hy + 5, H - 2)
    return cx, cy, Wx, Hy, Ri, r_slogan, r_invite


_oeil_seed = 0                                      # fixe les veines pour tout un lancement


def _dessiner_veines(grille, W, H, cx, cy, Wx, Hy, Ri, icx, icy, ouv, intensite=1.0):
    """Veines rouges (œil injecté de sang) sur le blanc de l'œil : des coins vers
    l'iris, avec ramifications. Stables d'une frame à l'autre grâce à _oeil_seed."""
    if intensite <= 0 or ouv < 0.45:
        return
    rng = random.Random(_oeil_seed)

    def lid(ex):
        nx = ex / Wx
        return 0.0 if abs(nx) >= 1.0 else ouv * Hy * (1.0 - nx * nx) ** 0.52

    def sur_sclere(x, y):
        l = lid(x - cx)
        if l < 0.6 or abs(y - cy) > l - 0.5:
            return False
        return math.hypot((x - icx) / _ASP, y - icy) > Ri + 0.4

    def trace(x, y, ang, pas, prof):
        for i in range(pas):
            ang += rng.uniform(-0.45, 0.45)
            x += math.cos(ang) * 1.25
            y += math.sin(ang) * 0.62
            xi, yi = int(round(x)), int(round(y))
            if not (0 <= xi < W and 0 <= yi < H) or not sur_sclere(xi, yi):
                return
            fade = 1.0 - i / max(pas, 1) * 0.65
            rr = min(255, int((150 + 95 * intensite) * fade))
            grille[yi][xi] = ("█", _txt(rr, int(34 * fade), int(32 * fade)), None)
            if prof == 0 and rng.random() < 0.12 and i > 1:      # une ramification
                trace(x, y, ang + rng.uniform(-1.1, 1.1), rng.randint(3, 7), 1)

    for _ in range(rng.randint(4, 6)):
        cote = rng.choice((-1, 1))
        sx = cx + cote * rng.uniform(Wx * 0.62, Wx * 0.96)
        sy = cy + rng.uniform(-0.55, 0.55) * Hy
        ang = math.atan2(cy - sy, (cx - sx)) + rng.uniform(-0.6, 0.6)
        trace(sx, sy, ang, rng.randint(max(int(Wx * 0.30), 4), max(int(Wx * 0.60), 6)), 0)


def _dessiner_oeil(grille, W, H, ouv, gx, gy, dil, f, veines=1.0):
    """Dessine un œil réaliste et détaillé dans la grille.
    ouv 0→1 = ouverture des paupières ; gx,gy = décalage du regard ; dil = pupille."""
    cx, cy, Wx, Hy, Ri, _, _ = _oeil_geo(W, H)
    Rp = Ri * 0.40 * dil                           # rayon de la pupille
    icx, icy = cx + gx, cy + gy                     # centre de l'iris (suit le regard)

    def lid(ex):                                    # demi-hauteur de l'amande à la colonne ex
        nx = ex / Wx
        if abs(nx) >= 1.0:
            return 0.0
        return ouv * Hy * (1.0 - nx * nx) ** 0.52   # exposant bas = coins plus pointus (étiré)

    y0, y1 = max(cy - Hy - 2, 0), min(cy + Hy + 3, H)
    x0, x1 = max(cx - Wx - 1, 0), min(cx + Wx + 2, W)
    for y in range(y0, y1):
        dy = y - cy
        row = grille[y]
        for x in range(x0, x1):
            ex = x - cx
            l = lid(ex)
            if l <= 0.0:
                continue
            ady = abs(dy)
            if ady > l + 0.6:
                continue
            bord_paup = ady > l - 0.6                # tout près du bord de la paupière
            sous_haut = dy < -l * 0.30               # sous la paupière haute → ombre
            vx = (x - icx) / _ASP
            vy = (y - icy)
            r = math.hypot(vx, vy)
            th = math.atan2(vy, vx)

            if r <= Rp - 0.5:                        # --- pupille (noir profond) ---
                ch, col = "█", (3, 5, 11)
            elif r <= Rp + 0.4:                      # bord adouci de la pupille
                ch, col = "▓", (18, 6, 8)
            elif r <= Ri:                            # --- iris bleu, très détaillé ---
                rn = (r - Rp) / max(Ri - Rp, 0.01)   # 0 au bord pupille → 1 au limbe
                fib = 0.5 + 0.5 * math.sin(th * 46 + r * 0.9)      # fibres radiales fines
                cry = 0.5 + 0.5 * math.sin(th * 6 - r * 1.8 + 0.7)  # cryptes plus larges
                cc = (255, 95, 68)                   # centre incandescent (rouge-orangé)
                ec = (82, 10, 14)                    # bord profond (rouge sombre)
                base = [cc[i] + (ec[i] - cc[i]) * rn for i in range(3)]
                br = (0.70 + 0.42 * fib) * (0.85 + 0.30 * cry)
                if 0.10 < rn < 0.24:                 # collerette claire autour de la pupille
                    br *= 1.4
                if rn > 0.88:                        # anneau limbique sombre
                    br *= 0.30
                if sous_haut:
                    br *= 0.60
                col = tuple(min(255, max(0, int(c * br))) for c in base)
                s = fib * 0.6 + cry * 0.4
                ch = "█" if s > 0.56 else ("▓" if s > 0.34 else "▒")
            else:                                    # --- blanc de l'œil (sclère) ---
                nx = ex / Wx
                coin = abs(nx) > 0.88
                if coin:                             # petite caroncule rosée au coin
                    ch, col = "▓", (198, 162, 162)
                else:
                    v = 150 if sous_haut else 224
                    col = [v, min(255, v + 6), min(255, v + 14)]
                    vn = math.sin(ex * 0.5 + dy * 1.7) + 0.6 * math.sin(ex * 1.3 - dy * 0.5 + 1.0)
                    if vn > 1.5 and abs(nx) > 0.45:   # veines rares, plutôt vers les côtés
                        col = [min(255, col[0] + 6), int(col[1] * 0.80), int(col[2] * 0.80)]
                    ch, col = "█", tuple(col)
            if bord_paup:                            # anti-aliasing du contour
                ch = "▒" if r <= Ri else "░"
            row[x] = (ch, _txt(*col), None)

    # --- veines rouges (œil injecté de sang) sur la sclère ---
    _dessiner_veines(grille, W, H, cx, cy, Wx, Hy, Ri, icx, icy, ouv, veines)

    # --- reflet spéculaire (lumière en haut-gauche de l'iris) + reflet secondaire ---
    for ax, ay, c in ((0, 0, (255, 255, 255)), (1, 0, (236, 246, 255)),
                      (0, 1, (224, 238, 252)), (1, 1, (205, 225, 245))):
        hx = int(icx - Ri * 0.8) + ax
        hy = int(icy - Ri * 0.5) + ay
        if 0 <= hx < W and 0 <= hy < H and abs(hy - cy) <= lid(hx - cx):
            grille[hy][hx] = ("█", _txt(*c), None)
    sx, sy = int(icx + Ri * 0.6), int(icy + Ri * 0.5)
    if 0 <= sx < W and 0 <= sy < H and abs(sy - cy) <= lid(sx - cx):
        grille[sy][sx] = ("▓", _txt(170, 110, 105), None)

    # --- paupières + cils ---
    for x in range(max(cx - Wx, 0), min(cx + Wx + 1, W)):
        ex = x - cx
        l = lid(ex)
        if l < 0.5:
            continue
        yt = cy - int(round(l))                      # paupière haute
        yb = cy + int(round(l))                      # paupière basse
        if 0 <= yt < H:
            grille[yt][x] = ("▀", _txt(70, 46, 40), None)
        if 0 <= yb < H:
            grille[yb][x] = ("▄", _txt(55, 34, 30), None)
        if ouv > 0.75 and ex % 3 == 0:               # cils (œil ouvert)
            cl = yt - 1
            if 0 <= cl < H and abs((cl) - cy) > l:
                pointe = "╲" if ex < -Wx * 0.3 else ("╱" if ex > Wx * 0.3 else "│")
                grille[cl][x] = (pointe, _txt(35, 24, 22), None)
    # --- pli de la paupière (trait sombre discret au-dessus) ---
    if ouv > 0.6:
        for x in range(max(cx - Wx, 0), min(cx + Wx + 1, W)):
            l = lid(x - cx)
            yc = cy - int(round(l)) - 2
            if 0 <= yc < H and grille[yc][x][0] == " ":
                grille[yc][x] = ("─", _txt(26, 30, 40), None)


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
    _poser_centre(grille, W, H, r_slogan, texte, _txt(130, 245, 185))


def _poser_invite(grille, W, H, allume=True):
    _, _, _, _, _, _, r_invite = _oeil_geo(W, H)
    ent = _txt(120, 240, 150) if allume else _txt(60, 120, 80)
    ech = _txt(240, 110, 110) if allume else _txt(120, 60, 60)
    gris = _txt(120, 130, 140)
    _poser_segments(grille, W, H, r_invite, [
        ("[ENTRÉE]", ent), (" entrer dans la partie      ", gris),
        ("[ÉCHAP]", ech), (" quitter", gris),
    ])


def _interp(t, ks):
    for i in range(len(ks) - 1):
        (t0, v0), (t1, v1) = ks[i], ks[i + 1]
        if t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            return v0 + (v1 - v0) * k
    return ks[-1][1]


def _oeil_ouverture(W, H, kb):
    """Ouverture LONGUE et détaillée : deux clignements puis grande ouverture,
    avec un léger balayage du regard. Renvoie 'enter'/'esc' si on appuie, sinon None."""
    cx, cy, Wx, Hy, Ri, _, _ = _oeil_geo(W, H)
    cles = [(0.00, 0.0), (0.12, 0.0), (0.18, 0.55), (0.24, 0.05), (0.33, 0.65),
            (0.39, 0.06), (0.52, 1.0), (0.72, 1.0), (0.76, 0.12), (0.82, 1.0), (1.0, 1.0)]
    frames = 120                                     # long
    for f in range(frames):
        t = f / (frames - 1)
        ouv = _interp(t, cles)
        look = max(0.0, min((t - 0.50) / 0.45, 1.0))
        gx = (Wx * 0.16) * math.sin(t * 5.0) * look
        gy = (Hy * 0.12) * math.sin(t * 3.1 + 1) * look
        if t > 0.92:                                 # recentre le regard à la fin
            gx *= (1 - t) / 0.08
            gy *= (1 - t) / 0.08
        dil = 1.0 + 0.06 * math.sin(f * 0.22)
        grille = _nouvelle_grille(W, H)
        _dessiner_oeil(grille, W, H, ouv, gx, gy, dil, f)
        _ecrire(_rendu_grille(grille))
        k = kb.get()
        if k:
            return k
        time.sleep(0.045)
    return None


def _oeil_revele(W, H, slogan, kb):
    """Le slogan se décode sous l'œil, puis l'invite apparaît."""
    frames = 18
    for f in range(frames):
        p = (f + 1) / frames
        grille = _nouvelle_grille(W, H)
        _dessiner_oeil(grille, W, H, 1.0, 0.0, 0.0, 1.0 + 0.05 * math.sin(f * 0.3), 900 + f)
        n = int(len(slogan) * p)
        aff = "".join(slogan[i] if i < n else random.choice(_GARB) for i in range(len(slogan)))
        _poser_slogan(grille, W, H, aff)
        if p > 0.55:
            _poser_invite(grille, W, H, allume=True)
        _ecrire(_rendu_grille(grille))
        k = kb.get()
        if k:
            return k
        time.sleep(0.05)
    return None


_SCAN_HUD = ["> ANALYSE RÉTINIENNE", "> IDENTITÉ : INCONNUE", "> MENACE   : ÉLEVÉE"]


def _poser_gauche(grille, W, H, row, colg, s, couleur):
    if not (0 <= row < H):
        return
    for i, ch in enumerate(s):
        if 0 <= colg + i < W:
            grille[row][colg + i] = (ch, couleur, None)


def _oeil_reticule(grille, W, H, cx, cy, Wx, Hy, serre, couleur):
    """Crochets de visée aux quatre coins de l'œil (serre 0 = large … 1 = collé)."""
    mx = int(Wx + 5 - serre * 4)
    my = int(Hy + 2 - serre * 1)
    coins = {(-1, -1): "┌", (1, -1): "┐", (-1, 1): "└", (1, 1): "┘"}
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, y0 = cx + sx * mx, cy + sy * my
            if not (0 <= y0 < H and 0 <= x0 < W):
                continue
            grille[y0][x0] = (coins[(sx, sy)], couleur, None)
            for d in range(1, 5):                        # bras horizontal
                x = x0 - sx * d
                if 0 <= x < W:
                    grille[y0][x] = ("─", couleur, None)
            for d in range(1, 3):                        # bras vertical
                y = y0 + sy * d
                if 0 <= y < H:
                    grille[y][x0] = ("│", couleur, None)


def _oeil_scan(W, H, kb):
    """Scan de l'iris + lecture HUD, puis la pupille se contracte (VERROUILLÉ)."""
    cx, cy, Wx, Hy, Ri, r_slogan, _ = _oeil_geo(W, H)
    cyan, rouge, vif = _txt(90, 210, 230), _txt(240, 70, 70), _txt(170, 255, 245)
    frames = 60
    for f in range(frames):
        p = f / (frames - 1)
        verrou = p > 0.72
        if not verrou:
            dil = 1.08 + 0.05 * math.sin(f * 0.4)
        else:
            dil = 1.08 - 0.62 * min((p - 0.72) / 0.28, 1.0)     # contraction nette
        gx = (Wx * 0.05) * math.sin(f * 0.2)
        grille = _nouvelle_grille(W, H)
        _dessiner_oeil(grille, W, H, 1.0, gx, 0.0, dil, 700 + f,
                       veines=1.0 + (1.8 if verrou else 0.0))
        serre = 1.0 if verrou else min(p / 0.72, 1.0)
        _oeil_reticule(grille, W, H, cx, cy, Wx, Hy, serre, rouge if verrou else cyan)
        if not verrou:                                   # ligne de scan qui balaie
            sy = int(cy - Hy + (f % 18) / 18.0 * 2 * Hy)
            for x in range(max(cx - Wx, 0), min(cx + Wx + 1, W)):
                if 0 <= sy < H and grille[sy][x][0] != " ":
                    grille[sy][x] = (grille[sy][x][0], vif, None)
        nb = min(len(_SCAN_HUD), int(p / 0.65 * len(_SCAN_HUD)) + 1)
        for i in range(nb):                              # HUD en haut à gauche
            _poser_gauche(grille, W, H, 1 + i, 2, _SCAN_HUD[i], cyan)
        if verrou:
            _poser_centre(grille, W, H, r_slogan, "●  CIBLE VERROUILLÉE  ●", rouge)
        _ecrire(_rendu_grille(grille))
        k = kb.get()
        if k:
            return k
        time.sleep(0.05)
    time.sleep(0.18)
    return None


def _oeil_zoom(W, H):
    """Transition : la caméra plonge dans la pupille (le noir envahit l'écran)."""
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
        _ecrire(_rendu_grille(grille))
        time.sleep(0.03)
    _ecrire(BASE + "\x1b[2J\x1b[H")


def _oeil_attente(W, H, slogan, kb):
    """L'œil reste vivant (clignements, micro-regard) et attend ENTRÉE / ÉCHAP."""
    cx, cy, Wx, Hy, Ri, _, _ = _oeil_geo(W, H)
    f = 0
    prochain_clin = random.randint(55, 110)
    clin = [0.55, 0.12, 0.0, 0.0, 0.15, 0.55, 1.0]
    while True:
        ouv = 1.0
        bf = f - prochain_clin
        if 0 <= bf < len(clin):
            ouv = clin[bf]
        elif bf >= len(clin):
            prochain_clin = f + random.randint(55, 130)
        gx = (Wx * 0.09) * math.sin(f * 0.040)
        gy = (Hy * 0.06) * math.sin(f * 0.029 + 0.5)
        dil = 1.0 + 0.07 * math.sin(f * 0.11)
        grille = _nouvelle_grille(W, H)
        _dessiner_oeil(grille, W, H, ouv, gx, gy, dil, f)
        _poser_slogan(grille, W, H, slogan)
        _poser_invite(grille, W, H, allume=(f // 7) % 2 == 0)   # l'invite pulse doucement
        _ecrire(_rendu_grille(grille))
        k = kb.get()
        if k in ("enter", "esc"):
            return k
        f += 1
        time.sleep(0.06)


def _accueil_oeil(modele):
    """Anime l'œil (ouverture → scan/verrouillage → slogan), attend la touche,
    puis plonge dans la pupille vers le menu. True = entrer, False = quitter."""
    global _intro_offset, _intro_voffset, _oeil_seed
    _intro_offset = _intro_voffset = 0
    taille = _Taille()
    W = max(min(taille.columns - 1, 400), 24)
    H = max(min(taille.lines - 1, 120), 14)
    slogan = random.choice(_SLOGANS)
    _oeil_seed = random.randint(1, 10 ** 6)          # veines fixes pour ce lancement
    _cacher_curseur()
    try:
        with _Clavier() as kb:
            phases = (
                lambda: _oeil_ouverture(W, H, kb),   # l'œil s'ouvre (long)
                lambda: _oeil_scan(W, H, kb),        # scan + verrouillage
                lambda: _oeil_revele(W, H, slogan, kb),   # slogan + invite
                lambda: _oeil_attente(W, H, slogan, kb),  # attend ENTRÉE / ÉCHAP
            )
            for phase in phases:
                r = phase()
                if r == "esc":
                    return False
                if r == "enter":
                    _oeil_zoom(W, H)                 # plongée dans la pupille
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

# --- Console vivante (barre du haut + stats en direct) ---
_titre_haut = 4            # ligne où commence le logo (après l'entête console)
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
    """Barre de titre (ligne 0) + statut opérateur (ligne 1)."""
    if len(grille) < 2:
        return
    row0 = grille[0]
    for c in range(W):
        row0[c] = [" ", None, BAR_BG]
    for i, ch in enumerate("◤ BLACK JACK ◢"):
        if 2 + i < W:
            row0[2 + i] = [ch, _txt(155, 215, 255), BAR_BG]
    enl = "● EN LIGNE"
    mx = max((W - len(enl)) // 2, 0)
    for i, ch in enumerate(enl):
        if 0 <= mx + i < W:
            row0[mx + i] = [ch, _txt(90, 235, 140) if ch == "●" else _txt(150, 210, 180), BAR_BG]
    u, host = _op_cache
    mode_ia = f"IA TURBO · {_ia_modele}" if _ia_turbo else (f"IA locale · {_ia_modele}" if _ia_modele else "IA locale")
    etat = "● EN LIGNE" if _ia_turbo else "○ HORS-LIGNE"
    stat = f"OPÉRATEUR {u}@{host}  ·  SESSION #{_sess_id}  ·  {mode_ia}  ·  {etat}"
    row1 = grille[1]
    for c in range(W):
        row1[c] = [" ", None, HDR_BG]
    for i, ch in enumerate(stat):
        if 2 + i < W:
            row1[2 + i] = [ch, _txt(110, 150, 185), HDR_BG]


def _repaint_menu(i_teinte, tetes, f):
    """Repeint les lignes du menu : pluie dans les cases vides + titre teinté,
    sans toucher la ligne de saisie ni déplacer le curseur."""
    W = len(_grille_menu[0])
    buf = ["\x1b7"]
    dec = _menu_offset
    for ry in range(_menu_bas):
        if _titre_haut <= ry < _titre_haut + LOGO_ROWS:  # lignes du titre → teinte
            ligne = _LOGO_TEINTES[i_teinte][ry - _titre_haut]
            buf.append(f"\x1b[{ry + 1};1H" + BASE + "\x1b[K" + " " * (dec + _titre_marge) + ligne)
            continue
        row = _grille_menu[ry]
        bout = [f"\x1b[{ry + 1};1H" + BASE + "\x1b[K" + " " * dec]
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
    buf.append("\x1b8")
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
            if f % 11 == 0:                            # stats ~1×/s
                _poser_stats(_grille_menu, W)
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
            _ecrire(_repaint_menu(0, None, 0))   # menu net, sans pluie


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


def _boite_cellules(titre, entrees, couleur):
    """Une boîte encadrée sous forme de cellules (char, fg, bg)."""
    dedans = LARGEUR_BOITE - 2
    t = f" {titre} "
    reste = dedans - len(t)
    g, d = max(reste // 2, 0), max(reste - reste // 2, 0)
    rows = [[(ch, couleur, None) for ch in "┌" + "─" * g + t + "─" * d + "┐"]]
    for num, label in entrees:
        cells = [(c, OR, None) for c in f" [{num:>2}] "] + [(c, TEXTE, None) for c in label]
        while len(cells) < dedans:
            cells.append((" ", "", None))      # "" = occupé (pas de pluie), mais rendu vide
        rows.append([("│", couleur, None)] + cells[:dedans] + [("│", couleur, None)])
    rows.append([(ch, couleur, None) for ch in "└" + "─" * dedans + "┘"])
    return rows


def _composer_menu(modele):
    """Console : entête (barre + stats en direct) puis logo, modules, invite."""
    global _ligne_horloge, _col_horloge, _ligne_stats, _ip_cache, _op_cache, _sess_id
    taille = _Taille()
    W = max(min(taille.columns - 1, 400), 2 * LARGEUR_BOITE + 3)   # la pluie remplit toute la largeur
    marge = max((W - (2 * LARGEUR_BOITE + 3)) // 2, 0)
    ml = max((W - LOGO_COLS) // 2, 0)
    if not _ip_cache:
        _ip_cache = _ip_locale()
    _op_cache = _operateur()
    if not _sess_id:
        _sess_id = f"{os.getpid() & 0xFFFF:04X}"
    _ligne_horloge, _ligne_stats = 0, 2
    _col_horloge = max(W - 10, 0)
    sections = [
        ("♠ TABLE — L'IA", [("1", "Discuter (tape ton message)"), ("2", "Recherche web sourcée"),
                            ("3", "CODEX — coder (C++, Python, web…)"),
                            ("4", "Nouvelle partie (efface la mémoire)")], VERT),
        ("♥ STRATÉGIE BLACKJACK", [("5", "Stratégie de base"), ("6", "Apprendre à compter (Hi-Lo)"),
                                   ("7", "Quiz : que faire ?")], ROUGE),
        ("♦ SYSTÈME — ma machine", [("8", "Infos système"), ("9", "Espace disque"),
                                    ("10", "Lancer un programme"),
                                    ("14", "Paramètres (Spotify, couleurs…)")], OR),
        ("♣ RÉSEAU — ma connexion", [("11", "Mon adresse IP"), ("12", "Tester ma connexion (ping)"),
                                     ("13", "Mes connexions actives")], CYAN),
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

    for r in range(_titre_haut + LOGO_ROWS):          # réserve entête + zone logo
        at(r)
    _poser_entete(lignes, W, modele)                  # barre + statut opérateur
    _poser_horloge(lignes, W)
    _poser_stats(lignes, W)
    for cr in range(LOGO_ROWS):                       # titre (teinte de base)
        row = at(_titre_haut + cr)
        for x in range(LOGO_COLS):
            row[ml + x] = ["▀", _txt(*LOGO[2 * cr][x]), _fond(*LOGO[2 * cr + 1][x])]
    if _ia_turbo:
        sous = f"▓▒░  IA TURBO · {_ia_modele} · en ligne  ░▒▓"
    else:
        sous = f"▓▒░  IA locale · {_ia_modele or modele} · hors-ligne · chiffré  ░▒▓"
    base_sous = _titre_haut + LOGO_ROWS + 1
    texte(base_sous, max((W - len(sous)) // 2, 0), sous, DISCRET)
    r1 = base_sous + 2
    poser(r1, marge, boites[0]); poser(r1, marge + LARGEUR_BOITE + 3, boites[1])
    r2 = r1 + max(len(boites[0]), len(boites[1])) + 1
    poser(r2, marge, boites[2]); poser(r2, marge + LARGEUR_BOITE + 3, boites[3])
    rh = r2 + max(len(boites[2]), len(boites[3])) + 1
    texte(rh, 3, "Tape un numéro, un message, menu pour revoir ceci, ou exit pour quitter.", DISCRET)
    texte(rh + 1, 0, "─" * min(W - 1, 90), DISCRET)
    bas = rh + 2
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
    return "\n" + OR + GRAS + "♣ Toi ›" + RESET + FOND + BLANC + " "


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
    _ecrire("\n" + VERT + GRAS + "♠ Black Jack ›" + BASE + " ")


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
