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


def appliquer_params(animations=None, densite=None, vitesse=None, cycle=None):
    """Applique les réglages du mode Paramètres (à chaud)."""
    global ANIMATIONS, PLUIE_DENSITE, PLUIE_VITESSE, TITRE_CYCLE
    if animations is not None:
        ANIMATIONS = (bool(animations) and sys.stdout.isatty()
                      and os.environ.get("BJ_SANS_ANIMATION") != "1")
    if densite is not None:
        PLUIE_DENSITE = max(0.0, min(1.0, densite))
    if vitesse is not None:
        PLUIE_VITESSE = max(0.3, min(3.0, vitesse))
    if cycle is not None:
        TITRE_CYCLE = bool(cycle)


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


def largeur():
    return shutil.get_terminal_size((100, 30)).columns


def effacer():
    """Efface l'écran et remet le curseur en haut."""
    _ecrire(BASE + "\x1b[2J\x1b[H")


def initialiser():
    """Active les couleurs dans le cmd et peint le tapis vert."""
    if os.name == "nt":
        os.system("")  # active le mode ANSI de la console Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _ecrire(BASE + "\x1b[2J\x1b[H")


def restaurer():
    _ecrire(RESET + "\n")


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


def _rendu_grille(grille):
    """Transforme une grille de (char, fg, bg) en une image terminal."""
    out = ["\x1b[H"]
    for rangee in grille:
        morceaux = [BASE]
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


def _intro_oeil(W, H):
    """Un « œil » qui s'ouvre avec les 4 enseignes qui tournent autour d'une
    pupille (clin d'œil au Sharingan, version Black Jack)."""
    cx, cy = W // 2, H // 2
    enseignes = [("♠", _txt(130, 225, 255)), ("♥", _txt(255, 120, 170)),
                 ("♦", _txt(255, 175, 110)), ("♣", _txt(140, 255, 185))]
    frames = 30
    for f in range(frames):
        grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]
        ouv = (f + 1) / frames
        demi = max(int(ouv * (H // 2)), 0)
        larg = int(ouv * cx)
        # bords des paupières (haut et bas de l'œil)
        for x in range(max(cx - larg, 0), min(cx + larg, W)):
            for yy in (cy - demi, cy + demi):
                if 0 <= yy < H:
                    grille[yy][x] = ("─", _txt(55, 135, 160), None)
        # emblème : les 4 enseignes tournent sur un cercle qui grandit
        R = 1.5 + ouv * 5.0
        ang = f * 0.45
        for k, (ens, col) in enumerate(enseignes):
            th = ang + k * math.pi / 2
            x = cx + int(round(R * math.cos(th) * 2.1))
            y = cy + int(round(R * math.sin(th)))
            if cy - demi <= y <= cy + demi and 0 <= x < W and 0 <= y < H:
                grille[y][x] = (ens, col, None)
        if demi > 0:                                   # pupille centrale
            grille[cy][cx] = ("●", _txt(205, 245, 255), None)
        _ecrire(_rendu_grille(grille))
        time.sleep(0.04)
    # clignement : un éclat bref puis noir, avant la pluie
    grille = [[(" ", None, None) for _ in range(W)] for _ in range(H)]
    for x in range(W):
        grille[cy][x] = ("─", _txt(150, 210, 240), None)
    _ecrire(_rendu_grille(grille))
    time.sleep(0.05)


def intro_animee():
    """Pluie de code « Matrix » plein écran, d'où émerge le logo glacé qui
    se révèle par balayage avec un reflet. Effet d'ouverture « wow »."""
    if not ANIMATIONS or LOGO_COLS == 0:
        return
    taille = shutil.get_terminal_size((100, 30))
    W = min(taille.columns - 1, max(LOGO_COLS + 6, 80))
    H = min(max(taille.lines - 1, LOGO_ROWS + 10), 28)
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
        _intro_oeil(W, H)                    # l'« œil » qui s'ouvre + enseignes qui tournent
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


def _repaint_menu(i_teinte, tetes, f):
    """Repeint les lignes du menu : pluie dans les cases vides + titre teinté,
    sans toucher la ligne de saisie ni déplacer le curseur."""
    W = len(_grille_menu[0])
    buf = ["\x1b7"]
    for ry in range(_menu_bas):
        if 1 <= ry <= LOGO_ROWS:                         # lignes du titre → teinte
            ligne = _LOGO_TEINTES[i_teinte][ry - 1]
            buf.append(f"\x1b[{ry + 1};1H" + BASE + "\x1b[K" + " " * _titre_marge + ligne)
            continue
        row = _grille_menu[ry]
        bout = [f"\x1b[{ry + 1};1H" + BASE + "\x1b[K"]
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

    def run(self):
        if not _LOGO_TEINTES or not _grille_menu:
            return
        W, bas = len(_grille_menu[0]), _menu_bas
        rng = random.Random()
        tetes = []
        for _ in range(W):
            if rng.random() < PLUIE_DENSITE:
                tetes.append([rng.uniform(-bas, 0.0), rng.uniform(0.6, 1.5) * PLUIE_VITESSE,
                              rng.randint(4, max(5, bas - 2))])
            else:
                tetes.append([0.0, 0.0, 0])
        n, i, f = len(_LOGO_TEINTES), 0, 0
        while not self.stop.is_set():
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
    if ANIMATIONS and _pulse is None and _grille_menu:
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
    taille = shutil.get_terminal_size((100, 30))
    W = max(min(taille.columns - 1, 118), 2 * LARGEUR_BOITE + 3)
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
    global sur_menu, _grille_menu, _menu_bas, _titre_marge
    grille, bas, ml = _composer_menu(modele)
    _grille_menu, _menu_bas, _titre_marge = grille, bas, ml
    out = [BASE + "\x1b[2J\x1b[H"]
    for row in grille:
        out.append(_ligne_ansi(row) + "\x1b[K\n")
    _ecrire("".join(out))
    sur_menu = True


def ecran_accueil(modele):
    initialiser()
    if ANIMATIONS:
        intro_animee()           # cinématique : étoiles + logo qui brille et dégouline
    afficher_menu(modele)


def ecran_sortie():
    _ecrire("\n")
    machine_a_ecrire(_centrer("♠ ♥ ♦ ♣   À la prochaine partie !   ♣ ♦ ♥ ♠"), OR, 0.015)
    _pause(0.4)
    restaurer()


# ---------- Conversation ----------

def demander_saisie():
    _ecrire("\n" + OR + GRAS + "♣ Toi ›" + RESET + FOND + BLANC + " ")
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
