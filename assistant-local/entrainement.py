"""Entraîneurs hors-ligne (aucune IA, réponses instantanées) :

  • hilo() : comptage Hi-Lo — cartes flash, compte courant, compte vrai ;
  • quiz() : « que faire ? » d'après la stratégie de base.

Les touches sont des LETTRES (indépendantes du clavier AZERTY / QWERTY).
"""
import random
import time

import interface as ui
import strategie as st
from jeu import _bloc, _txt_total, _touche

# +1 / 0 / −1  (« & » et « à » sont les touches 1 et 0 non décalées d'un clavier AZERTY)
PLUS, ZERO, MOINS = set("p+=1&"), set("z0à"), set("m-")
TOUCHES_HILO = PLUS | ZERO | MOINS | {"q", "esc"}

NIVEAUX = {"d": ("Débutant", 10, 1.2), "m": ("Moyen", 20, 0.8), "e": ("Casino", 30, 0.5)}


def _cartes_aleatoire(rng):
    return rng.choice(st.RANGS), rng.choice(st.ENSEIGNES)


def _entete(titre, droite="« Q » pour quitter  "):
    return [ui.ligne_entete(f"  ◢ BLACK JACK ◣   ·   {titre}", droite),
            ui.DISCRET + "  " + "─" * min(max(ui.largeur() - 4, 20), 100) + ui.BASE]


def _carte_centree(rang, ens):
    marge = max((ui.largeur() - 7) // 2, 2)
    return [" " * marge + l for l in ui.carte(rang, ens)]


def _centre(texte, visible=None):
    n = visible if visible is not None else ui._long_visible(texte)
    return " " * max((ui.largeur() - n) // 2, 2) + texte


def _fmt(n):
    return f"{n:+d}" if n else "0"


def _lire_entier(texte, defaut=None):
    t = texte.strip().replace("−", "-").replace("—", "-").replace(",", ".").replace(" ", "")
    if not t:
        return defaut
    try:
        return float(t)
    except ValueError:
        return None


# =====================================================================
#  HI-LO
# =====================================================================

def _legende():
    return ("  " + _touche("P", "+1 (2 à 6)") + "    " + _touche("Z", "0 (7 à 9)") + "    "
            + _touche("M", "−1 (10, J, Q, K, A)") + ui.DISCRET + "     (ou + / 0 / −)" + ui.BASE)


def _flash(rng, n=20):
    ok, temps, erreurs = 0, [], []
    for i in range(n):
        rang, ens = _cartes_aleatoire(rng)
        vrai = st.hilo(rang)
        L = _entete("HI-LO · CARTES FLASH")
        L += ["", "  " + ui.TEXTE + f"Carte {i + 1}/{n}" + ui.DISCRET + f"   ·   justes : {ok}" + ui.BASE, ""]
        L += _carte_centree(rang, ens) + ["", _legende()]
        ui.dessiner(L)
        t0 = time.time()
        k = ui.lire_touche(TOUCHES_HILO)
        dt = time.time() - t0
        if k in ("q", "esc"):
            return
        rep = 1 if k in PLUS else (0 if k in ZERO else -1)
        temps.append(dt)
        if rep == vrai:
            ok += 1
            L.append("  " + ui.VERT + ui.GRAS + f"✓ {_fmt(vrai)}" + ui.DISCRET + f"   ({dt:.1f} s)" + ui.BASE)
            ui.dessiner(L)
            time.sleep(0.35)
        else:
            erreurs.append((rang, ens, vrai))
            L.append("  " + ui.ROUGE + ui.GRAS + f"✗ c'était {_fmt(vrai)}" + ui.BASE)
            ui.dessiner(L)
            time.sleep(1.2)
    moy = sum(temps) / len(temps)
    L = _entete("HI-LO · CARTES FLASH · RÉSULTAT", droite="")
    L += ["", "  " + ui.TEXTE + f"Score : {ui.OR}{ui.GRAS}{ok}/{n}{ui.BASE}{ui.TEXTE}   ·   temps moyen : "
          f"{ui.OR}{moy:.2f} s{ui.BASE}{ui.TEXTE} par carte" + ui.BASE, ""]
    if ok == n and moy <= 1.5:
        L.append("  " + ui.VERT + "Niveau casino : parfait et assez rapide. Passe au compte courant." + ui.BASE)
    elif ok == n:
        L.append("  " + ui.VERT + "Sans faute ! Vise maintenant moins de 1,5 s par carte." + ui.BASE)
    else:
        L.append("  " + ui.OR + "Rappel : 2-6 = +1 · 7-9 = 0 · 10, J, Q, K, A = −1. Refais une série." + ui.BASE)
        for rang, ens, vrai in erreurs[:5]:
            L.append("    " + ui.DISCRET + f"{rang}{ens}  →  {_fmt(vrai)}" + ui.BASE)
    ui.dessiner(L)
    ui.attendre_touche("Appuie sur une touche pour continuer")


def _compte_courant(rng):
    L = _entete("HI-LO · COMPTE COURANT")
    L += ["", "  " + ui.TEXTE + "Les cartes défilent une à une : tiens le compte de tête." + ui.BASE,
          "  " + ui.TEXTE + "À la fin, donne le total (2-6 = +1 · 7-9 = 0 · 10-A = −1)." + ui.BASE, ""]
    for cle, (nom, n, delai) in NIVEAUX.items():
        L.append("  " + _touche(cle.upper(), f"{nom:<9} {n} cartes, {delai:.1f} s par carte"))
    ui.dessiner(L)
    k = ui.lire_touche(set(NIVEAUX) | {"q", "esc"})
    if k in ("q", "esc"):
        return
    nom, n, delai = NIVEAUX[k]
    cartes = [_cartes_aleatoire(rng) for _ in range(n)]
    for i, (rang, ens) in enumerate(cartes):
        L = _entete(f"HI-LO · COMPTE COURANT · {nom.upper()}", droite="")
        L += ["", "  " + ui.DISCRET + f"Carte {i + 1}/{n}" + ui.BASE, ""] + _carte_centree(rang, ens)
        ui.dessiner(L)
        time.sleep(delai)
        ui.dessiner(_entete(f"HI-LO · COMPTE COURANT · {nom.upper()}", droite=""))   # écran vide : sépare 2 cartes identiques
        time.sleep(0.1)
    vrai = sum(st.hilo(r) for r, _ in cartes)
    ui.dessiner(_entete("HI-LO · COMPTE COURANT", droite="") + ["", "  " + ui.OR + ui.GRAS
                                                                    + "Quel est le compte ?" + ui.BASE])
    ui.vider_clavier()
    rep = _lire_entier(ui.demander_texte("Compte courant (ex. +4, -2, 0)"))
    L = _entete("HI-LO · COMPTE COURANT · RÉSULTAT", droite="")
    if rep is not None and int(round(rep)) == vrai:
        L += ["", "  " + ui.VERT + ui.GRAS + f"✓ Exact : le compte était {_fmt(vrai)}." + ui.BASE]
    else:
        L += ["", "  " + ui.ROUGE + ui.GRAS + f"✗ Le compte était {_fmt(vrai)}." + ui.BASE]
    L += ["", "  " + ui.DISCRET + "Les cartes, dans l'ordre :" + ui.BASE]
    seq, run = [], 0
    for rang, ens in cartes:
        run += st.hilo(rang)
        seq.append(f"{rang}{ens} ({_fmt(run)})")
    ligne = "    "
    for morceau in seq:
        if len(ligne) + len(morceau) + 2 > min(ui.largeur() - 2, 100):
            L.append(ui.TEXTE + ligne + ui.BASE)
            ligne = "    "
        ligne += morceau + "  "
    L.append(ui.TEXTE + ligne + ui.BASE)
    ui.dessiner(L)
    ui.attendre_touche("Appuie sur une touche pour continuer")


def _compte_vrai(rng, n=8):
    ok = 0
    notes = []
    for i in range(n):
        courant = rng.randint(-8, 16)
        jeux = rng.choice([1, 1.5, 2, 2.5, 3, 3.5, 4, 5])
        L = _entete("HI-LO · COMPTE VRAI")
        L += ["", "  " + ui.TEXTE + f"Question {i + 1}/{n}" + ui.DISCRET + f"   ·   justes : {ok}" + ui.BASE, "",
              "  " + ui.TEXTE + "Compte courant : " + ui.OR + ui.GRAS + _fmt(courant) + ui.BASE,
              "  " + ui.TEXTE + "Jeux restants   : " + ui.OR + ui.GRAS + f"{jeux:g}" + ui.BASE, "",
              "  " + ui.DISCRET + "Compte vrai = compte courant ÷ jeux restants (arrondi à l'entier)." + ui.BASE]
        ui.dessiner(L)
        ui.vider_clavier()
        rep = _lire_entier(ui.demander_texte("Compte vrai"))
        exact = courant / jeux
        if rep is not None and abs(rep - exact) <= 0.75:
            ok += 1
            notes.append(ui.VERT + f"✓ {_fmt(courant)} ÷ {jeux:g} = {exact:.1f}" + ui.BASE)
        else:
            notes.append(ui.ROUGE + f"✗ {_fmt(courant)} ÷ {jeux:g} = {exact:.1f}" + ui.BASE)
        L.append("")
        L.append("  " + notes[-1])
        ui.dessiner(L)
        time.sleep(0.9)
    L = _entete("HI-LO · COMPTE VRAI · RÉSULTAT", droite="")
    L += ["", "  " + ui.TEXTE + f"Score : {ui.OR}{ui.GRAS}{ok}/{n}{ui.BASE}", ""]
    L += ["  " + x for x in notes]
    L += ["", "  " + ui.DISCRET + "À partir d'un compte vrai de +2 à +3, la mise peut monter ; "
          "l'assurance devient rentable à +3." + ui.BASE]
    ui.dessiner(L)
    ui.attendre_touche("Appuie sur une touche pour continuer")


def hilo(rng=None):
    """Menu de l'entraîneur Hi-Lo."""
    rng = rng or random.Random()
    ui._cacher_curseur()
    try:
        ui.debut_conversation("ENTRAÎNEUR HI-LO", droite="« Q » pour revenir  ")
        while True:
            L = _entete("ENTRAÎNEUR HI-LO", droite="« Q » pour revenir  ")
            L += ["", "  " + ui.OR + ui.GRAS + "Le système Hi-Lo" + ui.BASE,
                  "  " + ui.TEXTE + "2 à 6 → " + ui.VERT + "+1" + ui.TEXTE + "     7 à 9 → 0     10, J, Q, K, A → "
                  + ui.ROUGE + "−1" + ui.BASE,
                  "  " + ui.DISCRET + "Compte courant = somme des valeurs des cartes vues. Plus il est haut, "
                  "plus il reste de grosses cartes." + ui.BASE, "",
                  "  " + _touche("F", "Cartes flash     : donne la valeur de chaque carte, vite"),
                  "  " + _touche("C", "Compte courant   : suis une série de cartes, donne le total"),
                  "  " + _touche("V", "Compte vrai      : convertis avec les jeux restants"),
                  "  " + _touche("Q", "Retour au menu")]
            ui.dessiner(L)
            k = ui.lire_touche({"f", "c", "v", "q", "esc"})
            if k in ("q", "esc"):
                return
            {"f": lambda: _flash(rng), "c": lambda: _compte_courant(rng),
             "v": lambda: _compte_vrai(rng)}[k]()
    finally:
        ui._montrer_curseur()


# =====================================================================
#  QUIZ « QUE FAIRE ? »
# =====================================================================

def situation(rng):
    """Une situation réaliste : (cartes du joueur, carte visible du croupier)."""
    cat = rng.choices(("dur", "souple", "paire"), weights=(5, 3, 2))[0]
    up = (rng.choice(["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]),
          rng.choice(st.ENSEIGNES))
    ens = lambda: rng.choice(st.ENSEIGNES)
    if cat == "paire":
        r = rng.choice(["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"])
        r2 = rng.choice(["10", "J", "Q", "K"]) if r == "10" else r
        main = [(r, ens()), (r2, ens())]
    elif cat == "souple":
        main = [("A", ens()), (rng.choice(["2", "3", "4", "5", "6", "7", "8", "9"]), ens())]
    else:
        while True:
            a, b = rng.choice(["2", "3", "4", "5", "6", "7", "8", "9", "10"]), \
                   rng.choice(["2", "3", "4", "5", "6", "7", "8", "9", "10"])
            if a != b and 8 <= st.valeur_carte(a) + st.valeur_carte(b) <= 17:
                break
        main = [(a, ens()), (b, ens())]
    rng.shuffle(main)
    return main, up


def quiz(rng=None, n=10):
    """Quiz « que faire ? » : n situations, correction instantanée."""
    rng = rng or random.Random()
    ui._cacher_curseur()
    ok, ratees = 0, []
    try:
        ui.debut_conversation("QUIZ · QUE FAIRE ?", droite="« Q » pour quitter  ")
        for i in range(n):
            main, up = situation(rng)
            code, phrase = st.conseil(main, up[0])
            L = _entete("QUIZ · QUE FAIRE ?")
            L += ["", "  " + ui.TEXTE + f"Question {i + 1}/{n}" + ui.DISCRET + f"   ·   justes : {ok}" + ui.BASE, ""]
            bloc_c, _ = _bloc(ui.TEXTE + ui.GRAS + "CROUPIER" + ui.BASE + ui.DISCRET + "   carte visible" + ui.BASE,
                              [up, ("?", "♠")], cacher_derniere=True)
            bloc_j, _ = _bloc(ui.TEXTE + ui.GRAS + "TOI" + ui.BASE + "   " + _txt_total(main), main)
            L += ["  " + l for l in bloc_c] + [""] + ["  " + l for l in bloc_j] + [""]
            L.append("  " + "   ".join(_touche(k, lib) for k, lib in
                                       (("S", "rester"), ("H", "tirer"), ("D", "doubler"), ("P", "séparer"))))
            ui.dessiner(L)
            k = ui.lire_touche({"s", "h", "d", "p", "q", "esc"})
            if k in ("q", "esc"):
                break
            if k.upper() == code:
                ok += 1
                L.append("")
                L.append("  " + ui.VERT + ui.GRAS + "✓ Bonne réponse. " + ui.BASE + ui.DISCRET + phrase + ui.BASE)
                ui.dessiner(L)
                time.sleep(0.9)
            else:
                ratees.append((main, up, k.upper(), code, phrase))
                L.append("")
                L.append("  " + ui.ROUGE + ui.GRAS + "✗ Raté. " + ui.BASE + ui.TEXTE + phrase + ui.BASE)
                ui.dessiner(L)
                ui.attendre_touche("Appuie sur une touche pour continuer")
        else:
            L = _entete("QUIZ · RÉSULTAT", droite="")
            L += ["", "  " + ui.TEXTE + f"Score : {ui.OR}{ui.GRAS}{ok}/{n}{ui.BASE}", ""]
            if ok == n:
                L.append("  " + ui.VERT + "Sans faute. Tu connais la stratégie de base." + ui.BASE)
            elif ok >= n * 0.8:
                L.append("  " + ui.VERT + "Très bien. Encore un peu de pratique." + ui.BASE)
            else:
                L.append("  " + ui.OR + "Relis la table de stratégie (option 5) puis réessaie." + ui.BASE)
            if ratees:
                L += ["", "  " + ui.DISCRET + "À revoir :" + ui.BASE]
                for main, up, rep, code, phrase in ratees:
                    L.append("    " + ui.TEXTE + phrase + ui.DISCRET + f"   (tu as répondu {rep})" + ui.BASE)
            ui.dessiner(L)
            ui.attendre_touche("Appuie sur une touche pour revenir au menu")
    finally:
        ui._montrer_curseur()
