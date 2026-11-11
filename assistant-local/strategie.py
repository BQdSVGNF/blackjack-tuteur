"""Logique pure du Black Jack (aucun affichage) : valeur des mains, stratégie de
base et compte Hi-Lo. Partagée par le jeu, l'entraîneur, le quiz et la table de
stratégie.

Règles de référence : 6 jeux, le croupier reste sur tous les 17 (même souples),
double sur toute main de 2 cartes, double après séparation autorisé, une seule
séparation, pas d'abandon.
"""

RANGS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
ENSEIGNES = ["♠", "♥", "♦", "♣"]

# Colonnes des tables = carte visible du croupier : 2 3 4 5 6 7 8 9 10 A
COLONNES = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]

# S = rester · H = tirer · D = doubler · P = séparer
DUR = [("8", "HHHHHHHHHH"), ("9", "HDDDDHHHHH"), ("10", "DDDDDDDDHH"),
       ("11", "DDDDDDDDDH"), ("12", "HHSSSHHHHH"), ("13", "SSSSSHHHHH"),
       ("14", "SSSSSHHHHH"), ("15", "SSSSSHHHHH"), ("16", "SSSSSHHHHH"),
       ("17+", "SSSSSSSSSS")]
SOUPLE = [("A,2", "HHHDDHHHHH"), ("A,3", "HHHDDHHHHH"), ("A,4", "HHDDDHHHHH"),
          ("A,5", "HHDDDHHHHH"), ("A,6", "HDDDDHHHHH"), ("A,7", "SDDDDSSHHH"),
          ("A,8", "SSSSSSSSSS"), ("A,9", "SSSSSSSSSS")]
PAIRES = [("2-2", "PPPPPPHHHH"), ("3-3", "PPPPPPHHHH"), ("4-4", "HHHPPHHHHH"),
          ("5-5", "DDDDDDDDHH"), ("6-6", "PPPPPHHHHH"), ("7-7", "PPPPPPHHHH"),
          ("8-8", "PPPPPPPPPP"), ("9-9", "PPPPPSPPSS"), ("T-T", "SSSSSSSSSS"),
          ("A-A", "PPPPPPPPPP")]

NOM_CODE = {"S": "rester", "H": "tirer", "D": "doubler", "P": "séparer"}


def valeur_carte(rang):
    """Valeur au Black Jack : As = 11 (réduit à 1 au besoin), figures et 10 = 10."""
    if rang == "A":
        return 11
    if rang in ("10", "J", "Q", "K"):
        return 10
    return int(rang)


def total(cartes):
    """(total, souple) d'une main. souple = un As compte encore pour 11."""
    t = sum(valeur_carte(c[0]) for c in cartes)
    as_a_11 = sum(1 for c in cartes if c[0] == "A")
    while t > 21 and as_a_11:
        t -= 10
        as_a_11 -= 1
    return t, as_a_11 > 0


def est_blackjack(cartes):
    return len(cartes) == 2 and total(cartes)[0] == 21


def hilo(rang):
    """Valeur Hi-Lo : 2-6 = +1 · 7-9 = 0 · 10, J, Q, K, A = −1."""
    if rang in ("2", "3", "4", "5", "6"):
        return 1
    if rang in ("7", "8", "9"):
        return 0
    return -1


def indice_croupier(rang):
    """Colonne (0..9) de la carte visible du croupier dans les tables."""
    v = valeur_carte(rang)
    return 9 if v == 11 else v - 2


def _nom_croupier(rang):
    if rang == "A":
        return "l'As"
    return "10" if valeur_carte(rang) == 10 else rang


def _cle_paire(rang):
    if rang == "A":
        return "A-A"
    return "T-T" if valeur_carte(rang) == 10 else f"{rang}-{rang}"


def _nom_paire(cle):
    return {"A-A": "Paire d'As", "T-T": "Paire de 10"}.get(cle, f"Paire de {cle[0]}")


def conseil(cartes, up, peut_doubler=True, peut_separer=True):
    """Conseil de la stratégie de base pour `cartes` contre la carte visible `up`.

    Renvoie (code, phrase) avec code ∈ 'S', 'H', 'D', 'P' (action réellement
    possible : si doubler/séparer est impossible, on replie sur la bonne autre
    action)."""
    j = indice_croupier(up)
    t, souple = total(cartes)
    deux = len(cartes) == 2
    suffixe = ""
    if (deux and peut_separer
            and valeur_carte(cartes[0][0]) == valeur_carte(cartes[1][0])):
        cle = _cle_paire(cartes[0][0])
        code = dict(PAIRES)[cle][j]
        desc = _nom_paire(cle)
    elif souple and 13 <= t <= 20:
        code = dict(SOUPLE)[f"A,{t - 11}"][j]
        desc = f"Main souple {t}"
    elif souple and t == 21:
        code, desc = "S", "21"
    elif souple and t == 12:                    # deux As qu'on ne peut pas séparer
        code, desc = "H", "Main souple 12"
    else:                                        # main dure
        if t >= 17:
            code = "S"
        elif t <= 8:
            code = "H"
        else:
            code = dict(DUR)[str(t)][j]
        desc = f"{t}"
    if code == "D" and not (deux and peut_doubler):
        code = "S" if (souple and t == 18) else "H"   # « Ds » : A,7 reste si on ne peut pas doubler
        suffixe = " (doubler impossible)"
    return code, f"{desc} contre {_nom_croupier(up)} : {NOM_CODE[code]}{suffixe}."
