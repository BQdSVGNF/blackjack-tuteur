"""Coffre-fort : chiffre/déchiffre TES fichiers avec un mot de passe que TU
choisis. Rien d'autre : ce n'est pas un outil pour ouvrir des fichiers dont tu
n'as pas le mot de passe (ça, c'est du cassage de chiffrement, hors de
question ici).

Construction, en toute transparence :
- dérivation de clé : PBKDF2-HMAC-SHA256, 300 000 itérations, sel aléatoire ;
- chiffrement : flux de clé SHA256 en mode compteur (XOR), nonce aléatoire ;
- intégrité : HMAC-SHA256 sur l'en-tête + le chiffré (chiffrer-puis-authentifier,
  vérifié AVANT tout déchiffrement) ;
- rien que la bibliothèque standard de Python (hashlib, hmac, os) : pas de
  dépendance externe, donc rien que le Contrôle intelligent des applications de
  Windows puisse bloquer (ça nous est déjà arrivé avec d'autres bibliothèques).

Honnêteté : c'est une construction maison à partir de briques standard,
pas un algorithme audité comme AES-GCM. Ça protège bien contre un vol
d'ordinateur ou un curieux qui fouille tes fichiers. Ce n'est pas un coffre de
niveau professionnel/gouvernemental.
"""
import hashlib
import hmac
import os

import interface as ui

MAGIC = b"BJVLT1\x00\x00"          # 8 octets
EXT = ".bjv"
ITERATIONS_DEFAUT = 300_000
TAILLE_ENTETE = 8 + 4 + 16 + 16 + 8  # magic + iterations + sel + nonce + taille_originale = 52


# =====================================================================
#  Logique pure (aucun affichage, testable directement)
# =====================================================================

def _derive_cles(mot_de_passe, sel, iterations):
    dk = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel, iterations, dklen=64)
    return dk[:32], dk[32:64]          # clé de chiffrement, clé d'authentification


def _flux_cle(cle, nonce, longueur):
    morceaux = []
    produit = 0
    i = 0
    while produit < longueur:
        bloc = hashlib.sha256(cle + nonce + i.to_bytes(8, "big")).digest()
        morceaux.append(bloc)
        produit += len(bloc)
        i += 1
    return b"".join(morceaux)[:longueur]


def _xor(donnees, cle_flux):
    n = len(donnees)
    if n == 0:
        return b""
    a = int.from_bytes(donnees, "big")
    b = int.from_bytes(cle_flux[:n], "big")
    return (a ^ b).to_bytes(n, "big")


def chiffrer_octets(donnees, mot_de_passe, iterations=ITERATIONS_DEFAUT):
    sel = os.urandom(16)
    nonce = os.urandom(16)
    cle_chiffrement, cle_mac = _derive_cles(mot_de_passe, sel, iterations)
    chiffre = _xor(donnees, _flux_cle(cle_chiffrement, nonce, len(donnees)))
    entete = MAGIC + iterations.to_bytes(4, "big") + sel + nonce + len(donnees).to_bytes(8, "big")
    mac = hmac.new(cle_mac, entete + chiffre, hashlib.sha256).digest()
    return entete + chiffre + mac


def dechiffrer_octets(conteneur, mot_de_passe):
    """Lève ValueError (format invalide) ou PermissionError (mot de passe
    incorrect ou fichier modifié — volontairement indiscernable : dire lequel
    des deux donnerait une info à qui essaierait de deviner)."""
    if len(conteneur) < TAILLE_ENTETE + 32:
        raise ValueError("Fichier trop court : ce n'est pas un coffre valide.")
    if conteneur[:8] != MAGIC:
        raise ValueError("Ce n'est pas un fichier du coffre Black Jack (.bjv).")
    iterations = int.from_bytes(conteneur[8:12], "big")
    sel = conteneur[12:28]
    nonce = conteneur[28:44]
    taille_orig = int.from_bytes(conteneur[44:52], "big")
    chiffre = conteneur[52:52 + taille_orig]
    mac_lu = conteneur[52 + taille_orig:52 + taille_orig + 32]
    if len(chiffre) != taille_orig or len(mac_lu) != 32:
        raise ValueError("Fichier corrompu ou tronqué.")
    cle_chiffrement, cle_mac = _derive_cles(mot_de_passe, sel, iterations)
    entete = conteneur[:52]
    mac_attendu = hmac.new(cle_mac, entete + chiffre, hashlib.sha256).digest()
    if not hmac.compare_digest(mac_lu, mac_attendu):
        raise PermissionError("Mot de passe incorrect, ou fichier modifié/corrompu.")
    return _xor(chiffre, _flux_cle(cle_chiffrement, nonce, taille_orig))


def _nom_libre(chemin):
    """Un nom de fichier qui n'existe pas encore : ajoute « (1) », « (2) »… au
    besoin. On n'écrase JAMAIS un fichier existant."""
    if not os.path.exists(chemin):
        return chemin
    base, ext = os.path.splitext(chemin)
    i = 1
    while True:
        candidat = f"{base} ({i}){ext}"
        if not os.path.exists(candidat):
            return candidat
        i += 1


def chiffrer_fichier(chemin_src, mot_de_passe, iterations=ITERATIONS_DEFAUT):
    """Écrit <chemin_src>.bjv (jamais d'écrasement) et le renvoie. L'original
    n'est JAMAIS touché."""
    with open(chemin_src, "rb") as f:
        donnees = f.read()
    conteneur = chiffrer_octets(donnees, mot_de_passe, iterations)
    dst = _nom_libre(chemin_src + EXT)
    with open(dst, "wb") as f:
        f.write(conteneur)
    return dst


def dechiffrer_fichier(chemin_src, mot_de_passe):
    """Déchiffre vers le nom d'origine (sans .bjv), jamais d'écrasement.
    Peut lever ValueError/PermissionError (voir dechiffrer_octets)."""
    with open(chemin_src, "rb") as f:
        conteneur = f.read()
    donnees = dechiffrer_octets(conteneur, mot_de_passe)   # peut lever
    base = chemin_src[:-len(EXT)] if chemin_src.lower().endswith(EXT) else chemin_src + ".dechiffre"
    dst = _nom_libre(base)
    with open(dst, "wb") as f:
        f.write(donnees)
    return dst


def lister_fichiers(dossier, suffixe=None, exclure_suffixe=None):
    out = []
    for racine, _dirs, noms in os.walk(dossier):
        for nom in noms:
            if suffixe and not nom.lower().endswith(suffixe):
                continue
            if exclure_suffixe and nom.lower().endswith(exclure_suffixe):
                continue
            out.append(os.path.join(racine, nom))
    return out


# =====================================================================
#  Écrans
# =====================================================================

def _lire_mot_de_passe(confirmer=False):
    """Saisie masquée (getpass) ; repli sur une saisie normale si le terminal
    ne le permet pas (invisible échoue rarement, mais on ne bloque jamais)."""
    import getpass

    def demander(invite):
        try:
            return getpass.getpass("  " + invite + " (invisible) › ")
        except Exception:
            return ui.demander_texte(invite + " (sera affiché : terminal non compatible)")

    p1 = demander("Mot de passe")
    if not p1:
        ui.info("  Mot de passe vide : annulé.", ui.DISCRET)
        return None
    if confirmer:
        p2 = demander("Confirme le mot de passe")
        if p1 != p2:
            ui.erreur("Les deux mots de passe ne correspondent pas.")
            return None
    return p1


def _fmt_octets(n):
    unites = ["o", "Ko", "Mo", "Go", "To"]
    n = float(abs(n))
    for u in unites:
        if n < 1024 or u == unites[-1]:
            return (f"{n:.0f} {u}" if u == "o" else f"{n:.1f} {u}")
        n /= 1024


def ecran_chiffrer_fichier():
    ui.effacer()
    ui.info("\n  ♦ COFFRE — chiffrer UN fichier\n", ui.CYAN)
    ui.info("  L'original n'est jamais touché : un fichier .bjv est créé à côté.", ui.DISCRET)
    chemin = ui.demander_texte("Chemin du fichier à chiffrer").strip().strip('"').strip("'")
    if not chemin:
        return
    if not os.path.isfile(chemin):
        ui.erreur("Fichier introuvable.")
        ui.attendre_touche()
        return
    mdp = _lire_mot_de_passe(confirmer=True)
    if not mdp:
        ui.attendre_touche()
        return
    ui.info("\n  Chiffrement…", ui.DISCRET)
    try:
        dst = chiffrer_fichier(chemin, mdp)
    except OSError as e:
        ui.erreur(f"Échec : {e}")
        ui.attendre_touche()
        return
    ui.info(f"\n  ✓ Créé : {dst}", ui.VERT)
    ui.info("  Retiens bien ce mot de passe : sans lui, ce fichier est illisible pour toujours.", ui.OR)
    ui.attendre_touche()


def ecran_dechiffrer_fichier():
    ui.effacer()
    ui.info("\n  ♦ COFFRE — déchiffrer UN fichier\n", ui.CYAN)
    chemin = ui.demander_texte("Chemin du fichier .bjv à déchiffrer").strip().strip('"').strip("'")
    if not chemin:
        return
    if not os.path.isfile(chemin):
        ui.erreur("Fichier introuvable.")
        ui.attendre_touche()
        return
    mdp = _lire_mot_de_passe(confirmer=False)
    if not mdp:
        ui.attendre_touche()
        return
    ui.info("\n  Déchiffrement…", ui.DISCRET)
    try:
        dst = dechiffrer_fichier(chemin, mdp)
    except PermissionError:
        ui.erreur("Mot de passe incorrect (ou fichier modifié/corrompu).")
        ui.attendre_touche()
        return
    except ValueError as e:
        ui.erreur(str(e))
        ui.attendre_touche()
        return
    except OSError as e:
        ui.erreur(f"Échec : {e}")
        ui.attendre_touche()
        return
    ui.info(f"\n  ✓ Créé : {dst}", ui.VERT)
    ui.attendre_touche()


def ecran_chiffrer_dossier():
    ui.effacer()
    ui.info("\n  ♦ COFFRE — chiffrer UN DOSSIER\n", ui.CYAN)
    ui.info("  Chaque fichier donne un .bjv à côté de lui. Les originaux ne sont", ui.DISCRET)
    ui.info("  jamais touchés automatiquement (proposé à part, à la fin).", ui.DISCRET)
    dossier = ui.demander_texte("Chemin du dossier à chiffrer").strip().strip('"').strip("'")
    if not dossier:
        return
    if not os.path.isdir(dossier):
        ui.erreur("Dossier introuvable.")
        ui.attendre_touche()
        return
    fichiers = lister_fichiers(dossier, exclure_suffixe=EXT)
    if not fichiers:
        ui.info("\n  Rien à chiffrer : aucun fichier (hors .bjv déjà présents).", ui.OR)
        ui.attendre_touche()
        return
    taille = sum(os.path.getsize(f) for f in fichiers if os.path.isfile(f))
    ui.info(f"\n  {len(fichiers)} fichier(s), {_fmt_octets(taille)} au total.", ui.TEXTE)
    ui._ecrire("\n  " + ui.OR + "Confirmer le chiffrement ? [o/n] " + ui.BLANC)
    rep = ui.lire_touche({"o", "n"})
    ui._ecrire(rep + "\n")
    if rep != "o":
        ui.info("  Annulé.", ui.DISCRET)
        ui.attendre_touche()
        return
    mdp = _lire_mot_de_passe(confirmer=True)
    if not mdp:
        ui.attendre_touche()
        return
    ok, erreurs = [], []
    for f in fichiers:
        try:
            chiffrer_fichier(f, mdp)
            ok.append(f)
        except OSError as e:
            erreurs.append((f, str(e)))
    ui.info(f"\n  ✓ {len(ok)}/{len(fichiers)} fichier(s) chiffré(s).", ui.VERT)
    for f, err in erreurs[:5]:
        ui.info(f"    ✖ {f} : {err}", ui.ROUGE)
    ui.info("\n  Retiens bien ce mot de passe : sans lui, ces fichiers sont illisibles pour toujours.", ui.OR)
    if ok and not erreurs:
        ui._ecrire("\n  " + ui.OR + f"Supprimer les {len(ok)} fichier(s) d'origine (non chiffrés) "
                   "maintenant ? [o/n] " + ui.BLANC)
        rep = ui.lire_touche({"o", "n"})
        ui._ecrire(rep + "\n")
        if rep == "o":
            supprimes, echecs = 0, 0
            for f in ok:
                try:
                    os.remove(f)
                    supprimes += 1
                except OSError:
                    echecs += 1
            ui.info(f"  ✓ {supprimes} original(aux) supprimé(s)."
                     + (f" {echecs} n'ont pas pu être supprimés." if echecs else ""), ui.VERT)
        else:
            ui.info("  Les originaux restent en place.", ui.DISCRET)
    ui.attendre_touche()


def ecran_dechiffrer_dossier():
    ui.effacer()
    ui.info("\n  ♦ COFFRE — déchiffrer UN DOSSIER\n", ui.CYAN)
    ui.info("  Le même mot de passe est utilisé pour tous les fichiers .bjv du dossier.", ui.DISCRET)
    dossier = ui.demander_texte("Chemin du dossier à déchiffrer").strip().strip('"').strip("'")
    if not dossier:
        return
    if not os.path.isdir(dossier):
        ui.erreur("Dossier introuvable.")
        ui.attendre_touche()
        return
    fichiers = lister_fichiers(dossier, suffixe=EXT)
    if not fichiers:
        ui.info("\n  Aucun fichier .bjv trouvé dans ce dossier.", ui.OR)
        ui.attendre_touche()
        return
    ui.info(f"\n  {len(fichiers)} fichier(s) .bjv trouvé(s).", ui.TEXTE)
    mdp = _lire_mot_de_passe(confirmer=False)
    if not mdp:
        ui.attendre_touche()
        return
    # on valide le mot de passe sur le premier fichier avant de foncer sur tous
    # les autres : si c'est le mauvais, un seul message au lieu d'un déluge
    try:
        dechiffrer_octets(open(fichiers[0], "rb").read(), mdp)
    except PermissionError:
        ui.erreur("Mot de passe incorrect pour ce dossier (testé sur le premier fichier).")
        ui.attendre_touche()
        return
    except (ValueError, OSError) as e:
        ui.erreur(f"Premier fichier illisible : {e}")
        ui.attendre_touche()
        return
    ok, erreurs = 0, []
    for f in fichiers:
        try:
            dechiffrer_fichier(f, mdp)
            ok += 1
        except (ValueError, PermissionError, OSError) as e:
            erreurs.append((f, str(e)))
    ui.info(f"\n  ✓ {ok}/{len(fichiers)} fichier(s) déchiffré(s).", ui.VERT)
    for f, err in erreurs[:5]:
        ui.info(f"    ✖ {f} : {err}", ui.ROUGE)
    ui.attendre_touche()


def ecran_a_propos():
    ui.effacer()
    ui.info("\n  ♦ COFFRE — comment ça marche\n", ui.CYAN)
    ui.info("  • Dérivation de clé : PBKDF2-HMAC-SHA256, 300 000 itérations, sel aléatoire.", ui.TEXTE)
    ui.info("  • Chiffrement : flux de clé SHA256 en mode compteur (XOR), nonce aléatoire.", ui.TEXTE)
    ui.info("  • Intégrité : HMAC-SHA256, vérifié AVANT tout déchiffrement.", ui.TEXTE)
    ui.info("  • Rien que la bibliothèque standard de Python : aucune dépendance externe.", ui.TEXTE)
    ui.info("\n  Honnêtement : c'est une construction maison à partir de briques standard,", ui.DISCRET)
    ui.info("  pas un algorithme audité comme AES-GCM. Bon contre un vol d'ordinateur ou un", ui.DISCRET)
    ui.info("  curieux qui fouille tes fichiers. Pas un coffre de niveau professionnel.", ui.DISCRET)
    ui.info("\n  Jamais d'écrasement : un fichier qui existe déjà reçoit un « (1) », « (2) »…", ui.DISCRET)
    ui.info("  Le mot de passe n'est stocké NULLE PART : si tu le perds, le fichier est perdu.", ui.OR)
    ui.attendre_touche()


def menu(conf):
    ui.ecran_defilant()          # texte long : écran qui défile (molette utilisable)
    while True:
        ui.effacer()
        ui.info("\n  ⚙  COFFRE — chiffrer / déchiffrer tes fichiers\n", ui.CYAN)
        ui.info(f"   {ui.OR}[1]{ui.TEXTE} Chiffrer un fichier")
        ui.info(f"   {ui.OR}[2]{ui.TEXTE} Chiffrer un dossier")
        ui.info(f"   {ui.OR}[3]{ui.TEXTE} Déchiffrer un fichier (.bjv)")
        ui.info(f"   {ui.OR}[4]{ui.TEXTE} Déchiffrer un dossier")
        ui.info(f"   {ui.OR}[5]{ui.TEXTE} Comment ça marche, les limites")
        ui.info(f"   {ui.OR}[0]{ui.TEXTE} Revenir au menu")
        choix = ui.demander_texte("Ton choix").strip()
        if choix in ("0", "", "retour", "exit"):
            return
        elif choix == "1":
            ecran_chiffrer_fichier()
        elif choix == "2":
            ecran_chiffrer_dossier()
        elif choix == "3":
            ecran_dechiffrer_fichier()
        elif choix == "4":
            ecran_dechiffrer_dossier()
        elif choix == "5":
            ecran_a_propos()
