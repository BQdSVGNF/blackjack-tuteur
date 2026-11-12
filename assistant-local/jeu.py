"""Black Jack jouable : moteur (sans affichage) + table dans le terminal.

Règles : 6 jeux (sabot remélangé quand il en reste un quart), blackjack payé 3:2,
le croupier reste sur tous les 17, double sur toute main de 2 cartes (aussi après
séparation), une seule séparation (les As séparés ne reçoivent qu'une carte),
assurance proposée contre un As. Le croupier regarde sa carte cachée quand il
montre un As ou un 10.

Les jetons sont débités au moment de la mise, du double, de la séparation et de
l'assurance, puis recrédités au règlement.
"""
import random

import interface as ui
import strategie as st

MISE_MIN = 10            # multiples de 10 : le blackjack à 3:2 tombe toujours juste
BANQUE_DEPART = 1000
JEUX = 6


# =====================================================================
#  MOTEUR (aucun affichage)
# =====================================================================

class Sabot:
    def __init__(self, jeux=JEUX, rng=None, cartes=None):
        self.rng = rng or random.Random()
        if cartes is not None:                       # sabot truqué (tests) : cartes[0] sort en 1er
            self.cartes = list(reversed(cartes))
        else:
            self.cartes = [(r, s) for _ in range(jeux) for r in st.RANGS for s in st.ENSEIGNES]
            self.rng.shuffle(self.cartes)
        self.initial = len(self.cartes)
        self.compte = 0                              # compte Hi-Lo des cartes VUES

    def tirer(self, visible=True):
        c = self.cartes.pop()
        if visible:
            self.compte += st.hilo(c[0])
        return c

    def reveler(self, carte):
        self.compte += st.hilo(carte[0])

    def restant(self):
        return len(self.cartes)

    def jeux_restants(self):
        return len(self.cartes) / 52.0

    def vrai_compte(self):
        return self.compte / max(self.jeux_restants(), 0.5)

    def a_melanger(self):
        return len(self.cartes) < self.initial * 0.25


class Main:
    def __init__(self, mise, cartes=None):
        self.cartes = list(cartes or [])
        self.mise = mise
        self.fini = False
        self.doublee = False
        self.apres_split = False
        self.issue = None            # 'bj' | 'gagne' | 'perd' | 'egal' | 'saute'


class Manche:
    """Une donne complète. Les méthodes sont appelées dans cet ordre :
    donner → (assurance) → controle_blackjack → [avancer/actions/agir]* →
    reveler → [croupier_doit_tirer/croupier_tire]* → regler."""

    def __init__(self, sabot, jetons, mise):
        self.sabot = sabot
        self.jetons_depart = jetons
        self.jetons = jetons - mise
        self.mains = [Main(mise)]
        self.croupier = []
        self.cachee = True                # la 2e carte du croupier est face cachée
        self.assurance = 0
        self.indice = 0
        self.termine = False

    # --- donne -------------------------------------------------------
    def donner(self):
        s, p = self.sabot, self.mains[0]
        p.cartes.append(s.tirer())
        self.croupier.append(s.tirer())
        p.cartes.append(s.tirer())
        self.croupier.append(s.tirer(visible=False))

    @property
    def visible(self):
        return self.croupier[0]

    @property
    def net(self):
        return self.jetons - self.jetons_depart

    # --- assurance / blackjacks -------------------------------------
    def assurance_possible(self):
        demi = self.mains[0].mise // 2
        return (self.croupier[0][0] == "A" and self.assurance == 0
                and demi > 0 and self.jetons >= demi)

    def prendre_assurance(self):
        demi = self.mains[0].mise // 2
        self.jetons -= demi
        self.assurance = demi

    def reveler(self):
        if self.cachee:
            self.cachee = False
            self.sabot.reveler(self.croupier[1])

    def controle_blackjack(self):
        """À appeler après la donne (et l'assurance). True si la manche est déjà réglée."""
        p = self.mains[0]
        regarde = st.valeur_carte(self.croupier[0][0]) >= 10      # As ou 10 : il regarde
        d_bj = regarde and st.est_blackjack(self.croupier)
        j_bj = st.est_blackjack(p.cartes)
        if d_bj:
            self.reveler()
            if self.assurance:
                self.jetons += self.assurance * 3                  # mise + gain 2:1
            if j_bj:
                p.issue = "egal"
                self.jetons += p.mise
            else:
                p.issue = "perd"
        elif j_bj:                                                 # le croupier ne peut pas avoir BJ
            self.reveler()
            p.issue = "bj"
            self.jetons += p.mise + p.mise * 3 // 2
        else:
            return False
        p.fini = True
        self.termine = True
        return True

    # --- tour du joueur ---------------------------------------------
    @property
    def main(self):
        return self.mains[self.indice]

    def avancer(self):
        """Passe à la prochaine main à jouer. False quand toutes sont terminées."""
        while self.indice < len(self.mains) and self.mains[self.indice].fini:
            self.indice += 1
        return self.indice < len(self.mains)

    def actions(self):
        m = self.main
        if m.fini:
            return set()
        a = {"h", "s"}
        if len(m.cartes) == 2 and self.jetons >= m.mise:
            a.add("d")
            if (len(self.mains) == 1
                    and st.valeur_carte(m.cartes[0][0]) == st.valeur_carte(m.cartes[1][0])):
                a.add("p")
        return a

    def agir(self, a):
        if a not in self.actions():
            raise ValueError(f"action impossible : {a}")
        m = self.main
        if a == "h":
            m.cartes.append(self.sabot.tirer())
            t = st.total(m.cartes)[0]
            if t > 21:
                m.fini, m.issue = True, "saute"
            elif t == 21:
                m.fini = True
        elif a == "s":
            m.fini = True
        elif a == "d":
            self.jetons -= m.mise
            m.mise *= 2
            m.doublee = True
            m.cartes.append(self.sabot.tirer())
            m.fini = True
            if st.total(m.cartes)[0] > 21:
                m.issue = "saute"
        elif a == "p":
            self.jetons -= m.mise
            c1, c2 = m.cartes
            seconde = Main(m.mise, [c2])
            m.cartes = [c1]
            m.apres_split = seconde.apres_split = True
            self.mains.append(seconde)
            for h in self.mains:
                h.cartes.append(self.sabot.tirer())
                if c1[0] == "A" or st.total(h.cartes)[0] == 21:    # As séparés : une seule carte
                    h.fini = True

    # --- tour du croupier et règlement ------------------------------
    def croupier_doit_tirer(self):
        """À appeler après reveler()."""
        if all(h.issue == "saute" for h in self.mains):
            return False
        return st.total(self.croupier)[0] < 17

    def croupier_tire(self):
        c = self.sabot.tirer()
        self.croupier.append(c)
        return c

    def regler(self):
        self.reveler()
        d = st.total(self.croupier)[0]
        for h in self.mains:
            if h.issue == "saute":
                continue
            t = st.total(h.cartes)[0]
            if d > 21 or t > d:
                h.issue = "gagne"
                self.jetons += h.mise * 2
            elif t == d:
                h.issue = "egal"
                self.jetons += h.mise
            else:
                h.issue = "perd"
        self.termine = True
        return self.net


# =====================================================================
#  AFFICHAGE
# =====================================================================

def _pad(s, w):
    return s + " " * max(w - ui._long_visible(s), 0)


def _lignes_cartes(cartes, cacher_derniere=False, grand=False):
    """Les cartes côte à côte : grandes (9×7) ou petites (7×5)."""
    haut = 7 if grand else 5
    if not cartes:
        return [""] * haut
    fab = ui.grande_carte if grand else ui.carte
    arts = [fab(r, s, cachee=(cacher_derniere and i == len(cartes) - 1))
            for i, (r, s) in enumerate(cartes)]
    return [" ".join(a[i] for a in arts) for i in range(haut)]


def _txt_total(cartes, cache=False):
    if not cartes:
        return ""
    if cache:
        return ui.DISCRET + "total ?"
    t, souple = st.total(cartes)
    if t > 21:
        return ui.ROUGE + ui.GRAS + f"{t} · SAUTÉ"
    if t == 21:
        return ui.VERT + ui.GRAS + "21"
    return ui.BLANC + f"{t}" + (ui.DISCRET + " souple" if souple else "")


def _bloc(etiquette, cartes, cacher_derniere=False, actif=False, grand=False):
    """Une main : ses cartes puis, dessous, son étiquette — centrées l'une sur l'autre."""
    cartes_l = _lignes_cartes(cartes, cacher_derniere, grand)
    marque = ui.OR + ui.GRAS + "▶ " if actif else ""
    etiq = marque + etiquette + ui.BASE
    larg = max([ui._long_visible(l) for l in cartes_l] + [ui._long_visible(etiq), 1])
    centre = lambda l: " " * ((larg - ui._long_visible(l)) // 2) + l
    return [_pad(centre(l), larg) for l in cartes_l] + [_pad(centre(etiq), larg)], larg


def _touche(lettre, libelle):
    return ui.OR + ui.GRAS + f"[{lettre}]" + ui.BASE + ui.TEXTE + f" {libelle}" + ui.BASE


def _jetons(mise):
    """Petite pile de jetons misés : ◉◉◉ 150."""
    n = min(max(mise // 50, 1), 8)
    return ui.accent_theme(True) + ui.GRAS + "◉" * n + ui.BASE + ui.BLANC + f" {mise}" + ui.BASE


def _ecran(v, croupier, cachee, mains, actif=None, message="", boutons=(), avis="",
           montrer_compte=True, afficher_mise=True):
    """Dessine toute la table, CENTRÉE, avec de grandes cartes si la fenêtre le permet
    (sinon les petites). mains : liste de (cartes, mise)."""
    W, Hf = ui._dim()
    W = max(min(W - 1, 200), 40)
    jetons = v["jetons"]
    engage = sum(mise for _, mise in mains)
    droite = f"JETONS {jetons}" + (f"   MISE {engage}" if engage and afficher_mise else "") + "  "
    entete = [ui.ligne_entete("  ◢ BLACK JACK ◣   ·   TABLE", droite),
              ui.DISCRET + "  " + "─" * min(W - 4, 100) + ui.BASE]

    def centrer(l):
        return " " * max((W - ui._long_visible(l)) // 2, 0) + l

    def composer(grand, air):
        """Lignes de la table pour une taille de cartes et un espacement donnés."""
        L = []
        vide = [""] * air
        cache = cachee and len(croupier) >= 2
        etiq = ui.TEXTE + ui.GRAS + "CROUPIER" + ui.BASE + "  " + _txt_total(croupier, cache=cache)
        bloc_c, _ = _bloc(etiq, croupier, cacher_derniere=cache, grand=grand)
        L += [centrer(l) for l in bloc_c] + vide
        # le bord du tapis, aux couleurs du thème
        regle = " ♠  BLACKJACK PAIE 3:2  ·  LE CROUPIER RESTE SUR 17  ♠ "
        lg = min(W - 6, 90)
        if lg >= len(regle) + 6:
            cote = (lg - len(regle)) // 2
            L.append(centrer(ui.accent_theme() + "╶" + "─" * (cote - 1) + ui.accent_theme(True)
                             + regle + ui.accent_theme() + "─" * (lg - cote - len(regle) - 1)
                             + "╴" + ui.BASE))
        else:
            L.append(centrer(ui.accent_theme() + "─" * lg + ui.BASE))
        L.append(centrer(message) if message else "")
        L += vide
        # les mains du joueur (côte à côte, empilées si trop large)
        blocs = []
        for i, (cartes, mise) in enumerate(mains):
            nom = "TOI" if len(mains) == 1 else f"MAIN {i + 1}"
            etiq = ui.TEXTE + ui.GRAS + nom + ui.BASE + "  " + _txt_total(cartes)
            lignes, larg = _bloc(etiq, cartes, actif=(actif == i), grand=grand)
            pile = _jetons(mise)
            lignes = [_pad(" " * max((larg - ui._long_visible(pile)) // 2, 0) + pile, larg)] + lignes
            blocs.append((lignes, larg))
        if not blocs:
            blocs = [_bloc(ui.DISCRET + "TOI" + ui.BASE, [], grand=grand)]
        total = sum(w for _, w in blocs) + 6 * (len(blocs) - 1)
        if len(blocs) > 1 and total + 2 > W:
            for lignes, _ in blocs:
                L += [centrer(l) for l in lignes]
        else:
            haut = max(len(b[0]) for b in blocs)
            for i in range(haut):
                L.append(centrer("      ".join(b[0][i] if i < len(b[0]) else " " * b[1]
                                               for b in blocs)))
        return L

    # pied : boutons, conseil, compte, stats
    pied = ["", centrer("   ".join(_touche(k, lib) for k, lib in boutons)) if boutons else "",
            centrer(avis) if avis else ""]
    s_ = v["sabot"]
    if v["compte_on"] and montrer_compte:
        pied.append(centrer(ui.CYAN + f"Hi-Lo  compte {s_.compte:+d}  ·  vrai {s_.vrai_compte():+.1f}"
                            + ui.DISCRET + f"   ({s_.restant()} cartes, {s_.jeux_restants():.1f} jeux)"
                            + ui.BASE))
    else:
        pied.append(centrer(ui.DISCRET + "[K] compte Hi-Lo" + ui.BASE))
    ok, n = v["ok"], v["n"]
    pct = f"{100 * ok // n} %" if n else "—"
    pied.append(centrer(ui.DISCRET + f"Stratégie de base : {ok}/{n} ({pct})   ·   manches : {v['manches']}"
                        + ui.BASE))

    dispo = Hf - 1 - len(entete) - len(pied) - 2     # -2 : ligne de saisie de la mise
    corps = None
    for grand, air in ((True, 1), (True, 0), (False, 1), (False, 0)):   # du plus beau au plus serré
        essai = composer(grand, air)
        if len(essai) <= dispo and max((ui._long_visible(l) for l in essai), default=0) <= W:
            corps = essai
            break
    if corps is None:
        corps = composer(False, 0)
    marge_haut = max((dispo - len(corps)) // 2, 0)   # la table est centrée verticalement
    ui.dessiner(entete + [""] * marge_haut + corps + pied)


def _boutons(actions):
    libelles = {"h": "tirer", "s": "rester", "d": "doubler", "p": "séparer"}
    b = [(k.upper(), libelles[k]) for k in "hsdp" if k in actions]
    return b + [("C", "conseil"), ("K", "compte")]


def _bandeau(m):
    morceaux = []
    for i, h in enumerate(m.mains):
        pref = f"Main {i + 1} : " if len(m.mains) > 1 else ""
        if h.issue == "bj":
            s = ui.OR + ui.GRAS + f"BLACKJACK !  +{h.mise * 3 // 2}"
        elif h.issue == "gagne":
            s = ui.VERT + ui.GRAS + f"GAGNÉ  +{h.mise}"
        elif h.issue == "perd":
            s = ui.ROUGE + ui.GRAS + f"PERDU  −{h.mise}"
        elif h.issue == "saute":
            s = ui.ROUGE + ui.GRAS + f"SAUTÉ  −{h.mise}"
        else:
            s = ui.TEXTE + ui.GRAS + "ÉGALITÉ  (mise rendue)"
        morceaux.append(pref + s + ui.BASE)
    txt = "   ·   ".join(morceaux)
    if m.assurance:
        if st.est_blackjack(m.croupier):
            txt += ui.CYAN + f"   ·   assurance +{m.assurance * 2}" + ui.BASE
        else:
            txt += ui.DISCRET + f"   ·   assurance −{m.assurance}" + ui.BASE
    if len(m.mains) > 1 or m.assurance:
        couleur = ui.VERT if m.net > 0 else (ui.ROUGE if m.net < 0 else ui.TEXTE)
        txt += ui.BASE + "   ·   " + couleur + ui.GRAS + f"net {m.net:+d}" + ui.BASE
    return txt


# =====================================================================
#  PARTIE
# =====================================================================

def _demander_mise(v, jetons, derniere):
    """Renvoie la mise choisie, ou None si on quitte la table."""
    maxi = jetons // MISE_MIN * MISE_MIN
    derniere = max(min(derniere, maxi), MISE_MIN)
    err = v.pop("info", "")                       # info ponctuelle (nouveau sabot, prêt de la banque…)
    while True:
        fin = v.get("vue_finale")
        if fin:
            _ecran(v, fin["croupier"], False, fin["mains"], message=fin["message"],
                   avis=err or fin.get("avis", ""), afficher_mise=False)
        else:
            _ecran(v, [], False, [], message=v.get("message", ""), avis=err)
        err = ""
        rep = ui.demander_texte(
            f"Mise ({MISE_MIN}–{maxi}) · Entrée = {derniere} · T = tapis · K = compte · Q = quitter"
        ).strip().lower()
        if rep in ("q", "quit", "quitter", "exit", "menu"):
            return None
        if rep == "k":
            v["compte_on"] = not v["compte_on"]
            continue
        if rep == "":
            mise = derniere
        elif rep in ("t", "tapis", "max", "all"):
            mise = maxi
        else:
            try:
                mise = int(rep.replace(" ", ""))
            except ValueError:
                err = ui.ROUGE + "Entre un nombre, par exemple 50." + ui.BASE
                continue
        mise = mise // MISE_MIN * MISE_MIN
        if mise < MISE_MIN:
            err = ui.ROUGE + f"Mise minimum : {MISE_MIN}." + ui.BASE
            continue
        if mise > maxi:
            err = ui.ROUGE + f"Tu n'as que {jetons} jetons." + ui.BASE
            continue
        return mise


def _jouer_manche(v, sabot, jetons, mise):
    """Joue une manche. Renvoie les jetons à la fin."""
    m = Manche(sabot, jetons, mise)
    m.donner()
    p = m.mains[0]
    v["sabot"] = sabot
    v["jetons"] = m.jetons

    # --- donne animée (le compte est masqué le temps de la distribution) ---
    for np_, nd in ((1, 0), (1, 1), (2, 1), (2, 2)):
        _ecran(v, m.croupier[:nd], nd == 2, [(p.cartes[:np_], mise)],
               message=ui.DISCRET + "Distribution…" + ui.BASE, montrer_compte=False)
        ui._pause(0.28)

    def vue(message="", avis="", boutons=(), cachee=None, actif=None, mise=True):
        _ecran(v, m.croupier, m.cachee if cachee is None else cachee,
               [(h.cartes, h.mise) for h in m.mains], actif=actif, message=message,
               boutons=boutons, avis=avis, afficher_mise=mise)

    retour = ""                                    # « ✓ conforme / ✗ conseillé » sur le dernier coup

    def fin(message):
        v["vue_finale"] = {"croupier": list(m.croupier), "message": message, "avis": retour,
                           "mains": [(list(h.cartes), h.mise) for h in m.mains]}
        v["jetons"] = m.jetons
        v["manches"] += 1
        vue(message=message, cachee=False, mise=False)
        ui._pause(0.5)

    # --- assurance (As du croupier) ---
    if m.assurance_possible():
        demi = mise // 2
        astuce = ""
        if v["compte_on"]:
            astuce = ui.CYAN + f"Hi-Lo : vrai compte {sabot.vrai_compte():+.1f} (rentable à partir de +3)"
        vue(message=ui.OR + ui.GRAS + f"Le croupier montre un As. Assurance ({demi}) ?" + ui.BASE,
            boutons=[("O", f"assurance (−{demi})"), ("N", "non merci")], avis=astuce)
        if ui.lire_touche({"o", "n"}) == "o":
            m.prendre_assurance()
            v["jetons"] = m.jetons

    # --- blackjacks ---
    if m.controle_blackjack():
        if m.mains[0].issue == "bj":
            ui._bip(((988, 70), (1319, 120)))
        fin(_bandeau(m))
        return m.jetons

    # --- tour du joueur ---
    avis = ""
    while m.avancer():
        h = m.main
        actions = m.actions()
        nom = "" if len(m.mains) == 1 else f"Main {m.indice + 1} — "
        vue(message=ui.TEXTE + nom + "À toi de jouer." + ui.BASE, avis=avis or retour,
            boutons=_boutons(actions), actif=m.indice)
        touche = ui.lire_touche(set(actions) | {"c", "k"})
        if touche == "k":
            v["compte_on"] = not v["compte_on"]
            continue
        code, phrase = st.conseil(h.cartes, m.visible[0], "d" in actions, "p" in actions)
        if touche == "c":
            avis = ui.CYAN + "Conseil — " + phrase + ui.BASE
            continue
        v["n"] += 1
        juste = touche.upper() == code
        v["ok"] += int(juste)
        retour = (ui.VERT + "✓ Conforme à la stratégie de base." if juste
                  else ui.ROUGE + "✗ La stratégie de base conseillait : " + phrase) + ui.BASE
        avis = ""
        m.agir(touche)
        if touche == "p":
            vue(message=ui.OR + "Séparation !" + ui.BASE, actif=0)
            ui._pause(0.5)

    # --- tour du croupier ---
    m.reveler()
    vue(message=ui.TEXTE + "Le croupier retourne sa carte…" + ui.BASE, cachee=False, avis=retour)
    ui._pause(0.7)
    while m.croupier_doit_tirer():
        m.croupier_tire()
        vue(message=ui.TEXTE + "Le croupier tire…" + ui.BASE, cachee=False, avis=retour)
        ui._pause(0.65)

    m.regler()
    if any(h.issue == "bj" for h in m.mains):
        ui._bip(((988, 70), (1319, 120)))
    fin(_bandeau(m))
    return m.jetons


def jouer(conf, sabot=None):
    """Lance la table de Black Jack. Les jetons et statistiques sont gardés dans conf."""
    jetons = int(conf.get("bankroll", BANQUE_DEPART))
    sabot = sabot or Sabot()
    v = {"jetons": jetons, "sabot": sabot, "compte_on": bool(conf.get("hilo_visible", False)),
         "ok": 0, "n": 0, "manches": 0, "vue_finale": None,
         "message": ui.DISCRET + f"Table {JEUX} jeux · blackjack paie 3:2 · le croupier reste sur 17 · "
                    f"mise minimum {MISE_MIN}" + ui.BASE}
    depart = jetons
    derniere = int(conf.get("derniere_mise", 50))
    ui.debut_conversation("TABLE", droite="")
    try:
        while True:
            if jetons < MISE_MIN:                              # plus de jetons : la banque prête
                jetons = BANQUE_DEPART
                v["info"] = ui.OR + f"Plus de jetons : la banque te prête {BANQUE_DEPART}." + ui.BASE
            if sabot.a_melanger():
                sabot = Sabot()
                v["sabot"] = sabot
                v["info"] = ui.CYAN + "Nouveau sabot mélangé — le compte repart à 0." + ui.BASE
            v["jetons"] = jetons
            mise = _demander_mise(v, jetons, derniere)
            if mise is None:
                break
            derniere = mise
            v["message"] = ""
            v["vue_finale"] = None
            jetons = _jouer_manche(v, sabot, jetons, mise)
    finally:
        conf["bankroll"] = jetons
        conf["derniere_mise"] = derniere
        conf["hilo_visible"] = v["compte_on"]
        conf["strat_ok"] = int(conf.get("strat_ok", 0)) + v["ok"]
        conf["strat_total"] = int(conf.get("strat_total", 0)) + v["n"]

    # --- résumé ---
    ui.debut_conversation("TABLE · RÉSUMÉ", droite="")
    diff = jetons - depart
    couleur = ui.VERT if diff > 0 else (ui.ROUGE if diff < 0 else ui.TEXTE)
    ui._ecrire(f"\n  {ui.TEXTE}Tu quittes la table avec {ui.OR}{ui.GRAS}{jetons} jetons{ui.BASE}"
               f"  {couleur}({diff:+d}){ui.BASE}\n")
    ui._ecrire(f"  {ui.TEXTE}Manches jouées : {v['manches']}\n")
    if v["n"]:
        ui._ecrire(f"  {ui.TEXTE}Stratégie de base : {v['ok']}/{v['n']} décisions justes "
                   f"({100 * v['ok'] // v['n']} %)\n")
    tot = int(conf.get("strat_total", 0))
    if tot:
        ui._ecrire(f"  {ui.DISCRET}Depuis le début : {conf['strat_ok']}/{tot} "
                   f"({100 * conf['strat_ok'] // tot} %){ui.BASE}\n")
    ui.attendre_touche()
