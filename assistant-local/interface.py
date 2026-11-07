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
MENU_ANIME = False         # fond animé du menu (pluie + titre arc-en-ciel) ; OFF = menu statique stable


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


try:
    from mots_glitch import MOTS as _MOTS_GLITCH, GRANTED as _GRANTED
except Exception:
    _MOTS_GLITCH, _GRANTED = [], []

_GLITCH_GARBAGE = "!<>/\\#%&01=?*¦:+"

# petit « ✓ » en blocs, affiché à droite d'« ACCÈS AUTORISÉ »
_CHECK = ["      ", "     █", "█   █ ", " █ █  ", "  █   "]


def _intro_boot(W, H):
    """Petit journal de démarrage « hacker » qui s'écrit avant l'œil."""
    lignes = [
        "> INITIALISATION DU NOYAU",
        "> CHARGEMENT DU MODELE black-jack",
        "> DECHIFFREMENT AES-256",
        "> CONNEXION AU TAPIS",
        "> ACTIVATION DE L'OEIL",
    ]
    _ecrire(BASE + "\x1b[2J\x1b[H")
    for i, txt in enumerate(lignes):
        _ecrire(f"\x1b[{_intro_voffset + 2 + i};{_intro_offset + 3}H" + VERT)
        for ch in txt:
            _ecrire(ch)
            time.sleep(0.004)
        for _ in range(random.randint(3, 7)):
            _ecrire(".")
            time.sleep(0.028)
        _ecrire("  " + _txt(130, 255, 160) + GRAS + "OK" + BASE)
        time.sleep(0.07)
    time.sleep(0.22)
    _ecrire(BASE + "\x1b[2J\x1b[H")


def _intro_granted(W, H):
    """Panneau encadré « ACCÈS AUTORISÉ ✓ » en vert, avant le logo."""
    if not _GRANTED:
        return
    _bip()                                    # signal de validation
    art = _GRANTED
    h = len(art)
    aw = max(len(l) for l in art)
    bloc = aw + 2 + len(_CHECK[0])
    cw = min(bloc + 10, W - 2)                 # largeur du panneau
    ch_ = h + 4                                 # hauteur du panneau
    top = max(H // 2 - ch_ // 2, 0)
    left = max((W - cw) // 2, 0)
    a_top = top + 2
    a_left = left + max((cw - bloc) // 2, 1)
    gx_check = a_left + aw + 2
    titre = " ◆ ACCÈS AUTORISÉ ◆ "
    sous = "NIVEAU 21 · COFFRE DÉBLOQUÉ"
    for fr in range(24):
        grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]
        vif = _txt(90, 255, 150) if fr % 6 < 4 else _txt(150, 255, 190)
        bord = _txt(55, 200, 120)
        for x in range(left, left + cw):        # bords haut/bas
            if 0 <= x < W:
                grille[top][x] = ("─", bord, None)
                grille[top + ch_ - 1][x] = ("─", bord, None)
        for y in range(top, top + ch_):         # bords gauche/droite
            if 0 <= y < H:
                grille[y][left] = ("│", bord, None)
                if left + cw - 1 < W:
                    grille[y][left + cw - 1] = ("│", bord, None)
        for yy, xx, c in [(top, left, "┌"), (top, left + cw - 1, "┐"),
                          (top + ch_ - 1, left, "└"), (top + ch_ - 1, left + cw - 1, "┘")]:
            if 0 <= yy < H and 0 <= xx < W:
                grille[yy][xx] = (c, bord, None)
        tx = left + max((cw - len(titre)) // 2, 0)     # titre dans la bordure
        for i, c in enumerate(titre):
            if 0 <= tx + i < W:
                grille[top][tx + i] = (c, vif, None)
        for i, ligne in enumerate(art):                 # le mot + la coche
            for j, c in enumerate(ligne):
                if c != " " and 0 <= a_left + j < W and a_top + i < H:
                    grille[a_top + i][a_left + j] = (c, vif, None)
        for i, ligne in enumerate(_CHECK):
            for j, c in enumerate(ligne):
                if c != " " and 0 <= gx_check + j < W and a_top + i < H:
                    grille[a_top + i][gx_check + j] = (c, _txt(180, 255, 200), None)
        sx = left + max((cw - len(sous)) // 2, 0)       # sous-titre
        sy = a_top + h + 1
        if sy < H:
            for i, c in enumerate(sous):
                if 0 <= sx + i < W:
                    grille[sy][sx + i] = (c, _txt(120, 255, 170), None)
        _ecrire(_rendu_grille(grille))
        time.sleep(0.05)


def _cadre_mot(grille, W, H, gauche, top, w, h, couleur, label):
    """Dessine un cadre à coins + un petit label au-dessus d'un mot."""
    coins = [(gauche - 3, top - 1, "┌"), (gauche + w + 2, top - 1, "┐"),
             (gauche - 3, top + h, "└"), (gauche + w + 2, top + h, "┘")]
    for x0, y0, ch in coins:
        if 0 <= x0 < W and 0 <= y0 < H:
            grille[y0][x0] = (ch, couleur, None)
            for d in (1, 2):                      # petits segments aux coins
                if "┌" in ch or "└" in ch:
                    if 0 <= x0 + d < W:
                        grille[y0][x0 + d] = ("─", couleur, None)
                else:
                    if 0 <= x0 - d < W:
                        grille[y0][x0 - d] = ("─", couleur, None)
    for i, ch in enumerate(label):
        x = gauche - 3 + i
        if 0 <= x < W and top - 2 >= 0:
            grille[top - 2][x] = (ch, _txt(75, 135, 100), None)


def _intro_glitch(W, H):
    """Chaque mot se « décode » : un scan balaie de gauche à droite, du bruit
    devant, le mot net derrière, avec cadre, label de module et aberration."""
    if not _MOTS_GLITCH:
        return
    couleurs = [VERT, CYAN, OR, MAGENTA]
    cy0 = H // 2
    n = len(_MOTS_GLITCH)
    for idx, (mot, art) in enumerate(_MOTS_GLITCH):
        h = len(art)
        w = max(len(l) for l in art)
        top = max(cy0 - h // 2, 0)
        gauche = max((W - w) // 2, 0)
        couleur = couleurs[idx % len(couleurs)]
        label = f"> MODULE {idx + 1:02d}/{n:02d}  [{mot}]"

        # --- décodage : le scan révèle le mot ---
        for sx in range(-2, w + 3):
            grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]
            for i, ligne in enumerate(art):
                y = top + i
                if not (0 <= y < H):
                    continue
                for j, ch in enumerate(ligne):
                    x = gauche + j
                    if not (0 <= x < W):
                        continue
                    if ch == " ":
                        if j > sx and random.random() < 0.05:    # bruit léger dans les vides
                            grille[y][x] = (random.choice(_GLITCH_GARBAGE), _txt(28, 66, 50), None)
                        continue
                    if j < sx - 1:                               # déjà révélé : net
                        c = random.choice(_GLITCH_GARBAGE) if random.random() < 0.03 else ch
                        grille[y][x] = (c, couleur, None)
                    elif j <= sx + 1:                            # ligne de scan : éclat + chroma
                        grille[y][x] = (ch, _txt(240, 255, 250), None)
                        if 0 <= x + 1 < W:
                            grille[y][x + 1] = (ch, MAGENTA, None)
                    elif random.random() < 0.55:                # pas encore : bruit
                        grille[y][x] = (random.choice(_GLITCH_GARBAGE), _txt(55, 115, 85), None)
            _cadre_mot(grille, W, H, gauche, top, w, h, _txt(70, 115, 95), label)
            _ecrire(_rendu_grille(grille))
            time.sleep(0.02)

        # --- tenue nette + un bref burst glitch ---
        for fr in range(6):
            grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]
            burst = fr == 3
            dx = random.choice((-2, 2)) if burst else 0
            for i, ligne in enumerate(art):
                y = top + i
                for j, ch in enumerate(ligne):
                    if ch == " ":
                        continue
                    x = gauche + j
                    if burst and 0 <= x + dx < W:
                        grille[y][x + dx] = (ch, CYAN if dx < 0 else MAGENTA, None)
                    if 0 <= x < W:
                        grille[y][x] = (ch, couleur, None)
            _cadre_mot(grille, W, H, gauche, top, w, h, couleur, label)
            _ecrire(_rendu_grille(grille))
            time.sleep(0.04)
        _ecrire(_rendu_grille([[(" ", None, None) for _ in range(W)] for _ in range(H)]))
        time.sleep(0.03)


def _intro_decrypt(W, H):
    """Barre de décryptage qui se remplit, avec hex qui défile — avant l'accès."""
    cy = H // 2
    titre = "DÉCRYPTAGE DU COFFRE · AES-256"
    barw = min(W - 24, 52)
    gx = max((W - barw) // 2, 0)
    octets = max((W - 12) // 3, 8)
    frames = 34
    for fr in range(frames):
        prog = fr / (frames - 1)
        grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]
        tx = max((W - len(titre)) // 2, 0)              # titre
        for i, ch in enumerate(titre):
            grille[cy - 3][tx + i] = (ch, CYAN, None)
        for r in range(1, 4):                            # hex qui défile dessous
            s = " ".join(f"{random.randint(0, 255):02X}" for _ in range(octets))
            hx = max((W - len(s)) // 2, 0)
            for i, ch in enumerate(s):
                if 0 <= hx + i < W:
                    grille[cy + 1 + r][hx + i] = (ch, _txt(40, 115, 72), None)
        rempli = int(prog * barw)                        # barre
        if gx - 2 >= 0:
            grille[cy][gx - 2] = ("[", DISCRET, None)
        if gx + barw + 1 < W:
            grille[cy][gx + barw + 1] = ("]", DISCRET, None)
        for i in range(barw):
            x = gx + i
            if 0 <= x < W:
                if i < rempli:
                    grille[cy][x] = ("█", VERT, None)
                elif i == rempli:
                    grille[cy][x] = ("▓", _txt(180, 255, 200), None)
                else:
                    grille[cy][x] = ("░", _txt(35, 80, 58), None)
        pct = f"{int(prog * 100):3d}%"                   # pourcentage
        for i, ch in enumerate(pct):
            x = gx + barw + 3 + i
            if 0 <= x < W:
                grille[cy][x] = (ch, VERT, None)
        _ecrire(_rendu_grille(grille))
        time.sleep(0.04)
    time.sleep(0.12)


def _intro_oeil(W, H):
    """Un œil réaliste : blanc de l'œil, iris bleu à fibres, pupille noire,
    reflet lumineux. Il cligne, s'ouvre, puis REGARDE autour (vivant)."""
    cx, cy = W // 2, H // 2
    Wx = min(cx - 2, 34)                        # demi-largeur de l'œil (colonnes)
    Hy = min(cy - 1, 9)                         # demi-hauteur (lignes)
    if Wx < 8 or Hy < 3:
        return
    Ri = Hy - 0.5                               # rayon de l'iris (unités y)
    Rp0 = Ri * 0.42                             # rayon de pupille au repos
    amp_x = max(Wx - Ri * 2 - 2, 2)            # amplitude du regard (colonnes)
    amp_y = max(Hy - Ri - 1, 1)

    def paup(ex, ouv):                          # demi-hauteur de l'œil (amande) à la colonne ex
        return ouv * Hy * (max(0.0, 1 - (ex / Wx) ** 2)) ** 0.72

    # ouverture : deux clignements, puis grand ouvert ; + un clignement au milieu
    cles = [(0.0, 0.0), (0.07, 0.5), (0.12, 0.05), (0.19, 0.55), (0.25, 0.05),
            (0.40, 1.0), (0.62, 1.0), (0.66, 0.12), (0.70, 1.0), (1.0, 1.0)]

    def interp(t, ks):
        for i in range(len(ks) - 1):
            (t0, v0), (t1, v1) = ks[i], ks[i + 1]
            if t <= t1:
                k = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
                return v0 + (v1 - v0) * k
        return ks[-1][1]

    frames = 66
    for f in range(frames):
        t = f / (frames - 1)
        ouv = interp(t, cles)
        # le regard balaie (droite, gauche, bas) quand l'œil est ouvert
        look = max(0.0, min((t - 0.30) / 0.55, 1.0))
        gx = amp_x * math.sin(t * 7.0) * look
        gy = amp_y * math.sin(t * 4.3 + 1) * look * 0.7
        if t > 0.9:                              # recentre le regard à la fin
            gx *= (1 - t) / 0.1
            gy *= (1 - t) / 0.1
        Rp = Rp0 * (1 + 0.12 * math.sin(f * 0.4))    # légère dilatation
        grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]
        for y in range(max(cy - Hy - 1, 0), min(cy + Hy + 2, H)):
            dy = y - cy
            for x in range(max(cx - Wx, 0), min(cx + Wx + 1, W)):
                ex = x - cx
                lid = paup(ex, ouv)
                if abs(dy) > lid + 0.001:
                    continue
                dxc = (x - (cx + gx)) / 2.0           # repère centré sur le regard
                dyc = (y - (cy + gy))
                r = math.hypot(dxc, dyc)
                haut = dy < -lid * 0.45              # zone sous la paupière haute (ombre)
                if r <= Rp:                           # pupille (noire)
                    grille[y][x] = (" ", None, _fond(2, 4, 8))
                elif r <= Ri:                         # iris bleu à fibres
                    th = math.atan2(dyc, dxc)
                    fib = 0.5 + 0.5 * math.sin(th * 16 + r * 0.7)
                    bord = r / Ri
                    if bord > 0.9:                    # anneau limbique sombre
                        col = (20, 45, 85)
                    else:
                        base = 1 - 0.35 * bord
                        col = (int((45 + 45 * fib) * base), int((135 + 70 * fib) * base),
                               int((215 + 40 * fib) * base))
                    if haut:
                        col = tuple(int(c * 0.72) for c in col)
                    ch = "▓" if fib > 0.6 else ("▒" if fib > 0.3 else "░")
                    grille[y][x] = (ch, _txt(*col), None)
                else:                                 # blanc de l'œil (sclère)
                    v = 150 if haut else 212          # ombre de la paupière haute
                    coin = abs(ex) > Wx * 0.82
                    col = (200, 150, 150) if coin else (v, v + 8, v + 16)
                    grille[y][x] = ("░" if coin else "▓", _txt(*col), None)
        # reflet spéculaire (lumière fixe, en haut à gauche de l'iris)
        hx = int(cx + gx - Ri * 0.9)
        hy = int(cy + gy - Ri * 0.5)
        for ax, ay in ((0, 0), (1, 0), (0, 1)):
            x, y = hx + ax, hy + ay
            if 0 <= x < W and 0 <= y < H and abs(y - cy) <= paup(x - cx, ouv):
                grille[y][x] = ("█", _txt(250, 252, 255), None)
        # paupières (traits) + cils
        for x in range(max(cx - Wx, 0), min(cx + Wx + 1, W)):
            lid = paup(x - cx, ouv)
            if lid < 0.3:
                continue
            for sgn in (-1, 1):
                yy = cy + int(round(sgn * lid))
                if 0 <= yy < H:
                    grille[yy][x] = ("▄" if sgn < 0 else "▀", _txt(120, 90, 80), None)
        _ecrire(_rendu_grille(grille))
        time.sleep(0.045)
    # éclat d'activation : l'iris s'illumine une fraction de seconde
    for inten in (1.0, 0.5):
        grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]
        for y in range(max(cy - Hy, 0), min(cy + Hy + 1, H)):
            for x in range(max(cx - Wx, 0), min(cx + Wx + 1, W)):
                if math.hypot((x - cx) / 2.0, y - cy) <= Ri:
                    v = int(255 * inten)
                    grille[y][x] = ("▓", _txt(v, v, 255), None)
        _ecrire(_rendu_grille(grille))
        time.sleep(0.05)


def intro_animee():
    """Pluie de code « Matrix » plein écran, d'où émerge le logo glacé qui
    se révèle par balayage avec un reflet. Effet d'ouverture « wow »."""
    if not ANIMATIONS or LOGO_COLS == 0:
        return
    global _intro_offset, _intro_voffset
    taille = _Taille()
    W = max(min(taille.columns - 1, 200), LOGO_COLS + 6)   # remplit la largeur
    H = max(min(taille.lines - 1, 46), LOGO_ROWS + 10)     # remplit la hauteur
    # centre tout le bloc d'intro (W×H) dans la fenêtre réelle, pour qu'il ne
    # reste pas collé en haut à gauche quand le terminal est agrandi
    _intro_offset = max((taille.columns - 1 - W) // 2, 0)
    _intro_voffset = max((taille.lines - 1 - H) // 2, 0)
    gauche = max((W - LOGO_COLS) // 2, 0)
    haut_logo = max((H - LOGO_ROWS) // 2 - 1, 0)

    rng = random.Random(os.environ.get("BJ_SEED"))
    # une goutte de pluie par colonne : [tête (float), vitesse, longueur] ; longueur 0 = inactive
    tetes = []
    for _ in range(W):
        if rng.random() < PLUIE_DENSITE:
            tetes.append([rng.uniform(-H, 0), rng.uniform(0.7, 1.9) * PLUIE_VITESSE,
                          rng.randint(6, max(7, H - 1))])
        else:
            tetes.append([0.0, 0.0, 0])

    R1 = 22                                  # pluie seule
    reveal = LOGO_COLS // 4 + 2              # révélation du logo
    hold = 26                                # logo complet + reflet, la pluie s'efface
    total = R1 + reveal + hold

    _cacher_curseur()
    try:
        _intro_boot(W, H)                    # journal de démarrage « hacker »
        _intro_oeil(W, H)                    # l'« œil » qui s'ouvre + enseignes qui tournent
        _intro_glitch(W, H)                  # mots « hacker » qui se décodent (scan)
        _intro_decrypt(W, H)                 # barre de décryptage + hex
        _intro_granted(W, H)                 # panneau « ACCÈS AUTORISÉ ✓ »
        for f in range(total):
            grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]

            # fondu de la pluie une fois le logo révélé
            if f < R1 + reveal:
                fade = 1.0
            else:
                fade = max(0.18, 1.0 - (f - (R1 + reveal)) / hold)

            # ----- pluie de code -----
            for x in range(W):
                t = tetes[x]
                if t[2] == 0:
                    continue
                t[0] += t[1]
                if t[0] - t[2] > H + 1:
                    t[0] = rng.uniform(-H, 0.0)
                    t[1] = rng.uniform(0.7, 1.9) * PLUIE_VITESSE
                    t[2] = rng.randint(6, max(7, H - 1))
                tete_y = int(t[0])
                for k in range(t[2]):
                    y = tete_y - k
                    if 0 <= y < H:
                        ch = CARS_PLUIE[(x * 7 + y * 13 + f) % len(CARS_PLUIE)]
                        if k == 0:
                            col = _txt(200, 255, 220)               # tête brillante
                        else:
                            v = fade * (1 - k / t[2])
                            col = _txt(int(35 + 110 * v), int(120 + 135 * v), int(70 + 110 * v))
                        grille[y][x] = (ch, col, None)

            # ----- logo qui émerge -----
            if f < R1:
                jusqua, reflet = -1, None
            elif f < R1 + reveal:
                jusqua = (f - R1) * 4
                reflet = jusqua
            else:
                jusqua = LOGO_COLS
                reflet = (f - (R1 + reveal)) * 6 - 6

            if jusqua >= 0:
                for cr in range(LOGO_ROWS):
                    for x in range(min(jusqua + 1, LOGO_COLS)):
                        if not (LOGO_MASQUE[2 * cr][x] or LOGO_MASQUE[2 * cr + 1][x]):
                            continue
                        fg = _txt(*_ajuste(LOGO[2 * cr][x], 1.0, x, reflet, 4))
                        bg = _fond(*_ajuste(LOGO[2 * cr + 1][x], 1.0, x, reflet, 4))
                        grille[haut_logo + cr][gauche + x] = ("▀", fg, bg)

            _ecrire(_rendu_grille(grille))
            time.sleep(0.05)
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


def _repaint_menu(i_teinte, tetes, f):
    """Repeint les lignes du menu : pluie dans les cases vides + titre teinté,
    sans toucher la ligne de saisie ni déplacer le curseur."""
    W = len(_grille_menu[0])
    buf = ["\x1b7"]
    dec = _menu_offset
    for ry in range(_menu_bas):
        if 1 <= ry <= LOGO_ROWS:                         # lignes du titre → teinte
            ligne = _LOGO_TEINTES[i_teinte][ry - 1]
            buf.append(f"\x1b[{ry + 1};1H" + BASE + "\x1b[K" + " " * (dec + _titre_marge) + ligne)
            continue
        row = _grille_menu[ry]
        bout = [f"\x1b[{ry + 1};1H" + BASE + "\x1b[K" + " " * dec]
        cfg = cbg = None
        for x in range(W):
            ch, fg, bg = row[x]
            if ch == " " and fg is None and tetes is not None:   # case vide → pluie ?
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
    """Construit toute la grille de l'écran du menu (title + boîtes + aide)."""
    taille = _Taille()
    W = max(min(taille.columns - 1, 200), 2 * LARGEUR_BOITE + 3)
    marge = max((W - (2 * LARGEUR_BOITE + 3)) // 2, 0)
    ml = max((W - LOGO_COLS) // 2, 0)
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

    for cr in range(LOGO_ROWS):                       # titre (teinte de base)
        row = at(1 + cr)
        for x in range(LOGO_COLS):
            row[ml + x] = ["▀", _txt(*LOGO[2 * cr][x]), _fond(*LOGO[2 * cr + 1][x])]
    sous = f"▓▒░  IA locale · {modele} · hors-ligne · chiffré  ░▒▓"
    texte(LOGO_ROWS + 3, max((W - len(sous)) // 2, 0), sous, DISCRET)
    r1 = LOGO_ROWS + 5
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


def ecran_accueil(modele):
    initialiser()
    if ANIMATIONS:
        intro_animee()           # boot, œil, glitch, ACCÈS AUTORISÉ, pluie, logo
        _distribue_blackjack()   # distribution d'une main gagnante (21)
    afficher_menu(modele)


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
