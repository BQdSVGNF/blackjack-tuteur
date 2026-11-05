"""Interface console « Black Jack » : tapis vert sombre, cartes et animations.

Fonctionne dans le cmd de Windows 10/11 (couleurs ANSI 24 bits).
Mets la variable d'environnement BJ_SANS_ANIMATION=1 pour couper les animations.
"""
import os
import shutil
import sys
import threading
import time

ANIMATIONS = os.environ.get("BJ_SANS_ANIMATION") != "1" and sys.stdout.isatty()


# ---------- Couleurs ----------

def _txt(r, g, b):
    return f"\x1b[38;2;{r};{g};{b}m"


def _fond(r, g, b):
    return f"\x1b[48;2;{r};{g};{b}m"


RESET = "\x1b[0m"
GRAS = "\x1b[1m"
FOND = _fond(7, 38, 23)            # tapis vert sombre
TEXTE = _txt(196, 226, 200)        # vert très clair
DISCRET = _txt(95, 140, 110)       # vert grisé
VERT = _txt(80, 205, 120)          # vert vif
OR = _txt(226, 186, 70)            # or des jetons
ROUGE = _txt(225, 70, 70)
BLANC = _txt(245, 244, 238)
NOIR = _txt(20, 20, 20)
FOND_CARTE = _fond(244, 241, 230)
DOS_CARTE = _fond(120, 20, 30)
BASE = RESET + FOND + TEXTE        # style « normal » sur le tapis

ENSEIGNES = [("♠", NOIR), ("♥", ROUGE), ("♦", ROUGE), ("♣", NOIR)]


def _ecrire(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def _pause(secondes):
    if ANIMATIONS:
        time.sleep(secondes)


def largeur():
    return shutil.get_terminal_size((100, 30)).columns


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


# ---------- Bannière ----------

BANNIERE = [
    r" ____  _            _           _            _    ",
    r"| __ )| | __ _  ___| | __      | | __ _  ___| | __",
    r"|  _ \| |/ _` |/ __| |/ /   _  | |/ _` |/ __| |/ /",
    r"| |_) | | (_| | (__|   <   | |_| | (_| | (__|   < ",
    r"|____/|_|\__,_|\___|_|\_\   \___/ \__,_|\___|_|\_\ ",
]


def _centrer(texte, visible=None):
    n = len(texte) if visible is None else visible
    return " " * max((largeur() - n) // 2, 0) + texte


def banniere():
    degrade = [(80, 205, 120), (120, 205, 105), (165, 200, 90), (200, 192, 78), (226, 186, 70)]
    n = max(len(l) for l in BANNIERE)
    for ligne, (r, g, b) in zip(BANNIERE, degrade):
        _ecrire(BASE + _txt(r, g, b) + GRAS + _centrer(ligne.ljust(n)) + BASE + "\n")
        _pause(0.07)


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


def separateur():
    _ecrire(BASE + DISCRET + "─" * min(largeur() - 1, 90) + BASE + "\n")


def ecran_accueil(modele):
    initialiser()
    _ecrire("\n")
    distribuer([("A", "♠"), ("K", "♥")])
    _ecrire("\n")
    clignoter("★  B L A C K J A C K  ★")
    _ecrire("\n")
    banniere()
    _ecrire("\n")
    sous_titre = f"♠ ♥ ♦ ♣   ton IA locale · modèle {modele}   ♣ ♦ ♥ ♠"
    _ecrire(_centrer("", len(sous_titre)))
    machine_a_ecrire(sous_titre, DISCRET, 0.006)
    _ecrire("\n")
    aide = [
        ("/web <question>", "recherche sur internet avec sources"),
        ("reset", "nouvelle partie (efface la mémoire)"),
        ("exit", "quitter la table"),
    ]
    for cmd, desc in aide:
        _ecrire(f"   {OR}{cmd:<17}{DISCRET}{desc}{BASE}\n")
        _pause(0.05)
    _ecrire("\n")
    separateur()


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
