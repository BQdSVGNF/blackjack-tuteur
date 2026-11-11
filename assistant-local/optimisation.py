"""Optimisation Windows : nettoyage des fichiers temporaires et liste des
programmes au démarrage. Rien n'est supprimé sans confirmation explicite
(touche o/n). Les entrées du Registre (démarrage automatique HKCU/HKLM) sont
seulement LISTÉES, jamais modifiées : les couper se fait depuis le
Gestionnaire des tâches (onglet Démarrage) — on ne touche pas au Registre
sans pouvoir le tester sur un vrai Windows. Seuls les raccourcis du dossier
Démarrage peuvent être coupés ici, et de façon réversible (un simple
renommage, rien n'est supprimé).
"""
import ctypes
import os
import shutil

import interface as ui


# ---------- Utilitaires (indépendants du système) ----------

def _fmt_octets(n):
    unites = ["o", "Ko", "Mo", "Go", "To"]
    n = float(abs(n))
    for u in unites:
        if n < 1024 or u == unites[-1]:
            return (f"{n:.0f} {u}" if u == "o" else f"{n:.1f} {u}")
        n /= 1024


def _taille_dossier(chemin, limite=200_000):
    """(taille totale, nb fichiers, tronqué ?) — lecture seule, erreurs ignorées."""
    total = 0
    fichiers = 0
    for racine, _dirs, noms in os.walk(chemin, onerror=lambda e: None):
        for nom in noms:
            try:
                total += os.path.getsize(os.path.join(racine, nom))
            except OSError:
                continue
            fichiers += 1
            if fichiers >= limite:
                return total, fichiers, True
    return total, fichiers, False


def _dossiers_temp():
    """Les dossiers de fichiers temporaires à analyser/nettoyer, sans doublons."""
    chemins = []
    for var in ("TEMP", "TMP"):
        p = os.environ.get(var)
        if p and os.path.isdir(p):
            chemins.append(p)
    win_temp = r"C:\Windows\Temp"
    if os.name == "nt" and os.path.isdir(win_temp):
        chemins.append(win_temp)
    vus, uniques = set(), []
    for c in chemins:
        cle = os.path.normcase(os.path.normpath(c))
        if cle not in vus:
            vus.add(cle)
            uniques.append(c)
    return uniques


def _nettoyer_dossiers(dossiers):
    """Supprime le CONTENU de chaque dossier (pas le dossier lui-même).
    Renvoie (octets_liberes, elements_supprimes, elements_ignores)."""
    liberes = supprimes = ignores = 0
    for d in dossiers:
        try:
            noms = os.listdir(d)
        except OSError:
            continue
        for nom in noms:
            chemin = os.path.join(d, nom)
            try:
                if os.path.isdir(chemin) and not os.path.islink(chemin):
                    taille, _n, _t = _taille_dossier(chemin)
                    shutil.rmtree(chemin)
                else:
                    taille = os.path.getsize(chemin)
                    os.remove(chemin)
            except OSError:
                ignores += 1
                continue
            liberes += taille
            supprimes += 1
    return liberes, supprimes, ignores


# ---------- Démarrage : liste (Registre) + bascule (dossier Démarrage) ----------

def _cle_demarrage(hive, chemin_cle, nom_hive):
    try:
        import winreg
    except ImportError:
        return []
    out = []
    try:
        with winreg.OpenKey(hive, chemin_cle) as cle:
            i = 0
            while True:
                try:
                    nom, valeur, _type = winreg.EnumValue(cle, i)
                except OSError:
                    break
                out.append({"type": "registre", "nom": nom, "ou": nom_hive,
                            "detail": valeur, "actif": True, "modifiable": False,
                            "chemin": None})
                i += 1
    except OSError:
        pass
    return out


def _dossier_demarrage():
    """Raccourcis des dossiers Démarrage (utilisateur + tous les utilisateurs).
    Un fichier coupé porte juste un « .disabled » en plus — rien n'est supprimé."""
    out = []
    emplacements = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        emplacements.append(("Utilisateur",
                              os.path.join(appdata, "Microsoft", "Windows",
                                           "Start Menu", "Programs", "Startup")))
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        emplacements.append(("Tous les utilisateurs",
                              os.path.join(programdata, "Microsoft", "Windows",
                                           "Start Menu", "Programs", "Startup")))
    for ou, d in emplacements:
        if not os.path.isdir(d):
            continue
        try:
            noms = os.listdir(d)
        except OSError:
            continue
        for nom in noms:
            chemin = os.path.join(d, nom)
            if not os.path.isfile(chemin):
                continue
            actif = not nom.endswith(".disabled")
            affiche = nom[:-len(".disabled")] if not actif else nom
            out.append({"type": "dossier", "nom": affiche, "ou": ou,
                        "detail": d, "actif": actif, "modifiable": True,
                        "chemin": chemin})
    return out


def demarrage_liste():
    """Toutes les entrées de démarrage connues. [] si pas sous Windows."""
    if os.name != "nt":
        return []
    import winreg
    entrees = []
    entrees += _cle_demarrage(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Run",
                               "Registre (utilisateur)")
    entrees += _cle_demarrage(winreg.HKEY_LOCAL_MACHINE,
                               r"Software\Microsoft\Windows\CurrentVersion\Run",
                               "Registre (machine)")
    entrees += _dossier_demarrage()
    return entrees


def _basculer(entree):
    """Coupe/réactive un raccourci du dossier Démarrage en ajoutant/enlevant
    « .disabled ». Réversible, aucune suppression."""
    chemin = entree["chemin"]
    nouveau = (chemin + ".disabled") if entree["actif"] else chemin[:-len(".disabled")]
    os.rename(chemin, nouveau)
    return nouveau


# ---------- Écrans ----------

def ecran_disque():
    ui.effacer()
    ui.info("\n  ♦ ANALYSE DU DISQUE — fichiers temporaires\n", ui.CYAN)
    dossiers = _dossiers_temp()
    if not dossiers:
        ui.info("  Aucun dossier temporaire trouvé (variables TEMP/TMP absentes).", ui.OR)
    total = 0
    for d in dossiers:
        taille, n, tronque = _taille_dossier(d)
        total += taille
        suffixe = ui.DISCRET + " (partiel, dossier énorme)" if tronque else ""
        ui.info(f"   {d}", ui.TEXTE)
        ui.info(f"     {_fmt_octets(taille)} dans {n} fichier(s){suffixe}", ui.DISCRET)
    if dossiers:
        ui.info(f"\n  Total estimé : {_fmt_octets(total)}", ui.OR)
    ui.info("\n  Ces fichiers sont temporaires : les supprimer est normalement sans risque,", ui.DISCRET)
    ui.info("  mais un fichier utilisé par un programme ouvert sera simplement ignoré.", ui.DISCRET)
    ui.attendre_touche()


def nettoyer_temp():
    dossiers = _dossiers_temp()
    ui.effacer()
    ui.info("\n  ♦ NETTOYAGE DES FICHIERS TEMPORAIRES\n", ui.CYAN)
    if not dossiers:
        ui.info("  Rien à nettoyer : aucun dossier temporaire trouvé.", ui.OR)
        ui.attendre_touche()
        return
    for d in dossiers:
        taille, n, _t = _taille_dossier(d)
        ui.info(f"   • {d}  ({_fmt_octets(taille)}, {n} fichier(s))", ui.TEXTE)
    ui.info("\n  Supprime tout le CONTENU de ces dossiers (le dossier lui-même reste).", ui.DISCRET)
    ui.info("  Un fichier encore utilisé par un programme ouvert sera simplement ignoré.", ui.DISCRET)
    ui._ecrire("\n  " + ui.OR + "Confirmer le nettoyage ? [o/n] " + ui.BLANC)
    rep = ui.lire_touche({"o", "n"})
    ui._ecrire(rep + "\n")
    if rep != "o":
        ui.info("  Annulé.", ui.DISCRET)
        ui.attendre_touche()
        return
    liberes, supprimes, ignores = _nettoyer_dossiers(dossiers)
    ui.info(f"\n  ✓ {supprimes} élément(s) supprimé(s), {_fmt_octets(liberes)} libéré(s).", ui.VERT)
    if ignores:
        ui.info(f"  {ignores} élément(s) ignoré(s) (probablement en cours d'utilisation).", ui.DISCRET)
    ui.attendre_touche()


def vider_corbeille():
    ui.effacer()
    ui.info("\n  ♦ VIDER LA CORBEILLE\n", ui.CYAN)
    if os.name != "nt":
        ui.info("  Disponible uniquement sous Windows.", ui.OR)
        ui.attendre_touche()
        return
    ui._ecrire("\n  " + ui.OR + "Confirmer : vider définitivement la corbeille ? [o/n] " + ui.BLANC)
    rep = ui.lire_touche({"o", "n"})
    ui._ecrire(rep + "\n")
    if rep != "o":
        ui.info("  Annulé.", ui.DISCRET)
        ui.attendre_touche()
        return
    # SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND : on a déjà
    # demandé nous-mêmes, pas besoin de la boîte de dialogue de Windows en plus.
    DRAPEAUX = 0x00000001 | 0x00000002 | 0x00000004
    try:
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, DRAPEAUX)
        if res in (0, -2147418113):   # 0 = succès ; l'autre code veut souvent dire « déjà vide »
            ui.info("  ✓ Corbeille vidée (ou déjà vide).", ui.VERT)
        else:
            ui.info(f"  La corbeille n'a peut-être pas pu être vidée (code {res}).", ui.OR)
    except Exception as e:
        ui.erreur(f"Impossible de vider la corbeille : {e}")
    ui.attendre_touche()


def ecran_demarrage():
    if os.name != "nt":
        ui.effacer()
        ui.info("\n  ♦ PROGRAMMES AU DÉMARRAGE\n", ui.CYAN)
        ui.info("  Disponible uniquement sous Windows.", ui.OR)
        ui.attendre_touche()
        return
    while True:
        entrees = demarrage_liste()
        ui.effacer()
        ui.info("\n  ♦ PROGRAMMES AU DÉMARRAGE\n", ui.CYAN)
        if not entrees:
            ui.info("  Aucune entrée trouvée.", ui.DISCRET)
        for i, e in enumerate(entrees, 1):
            etat = (ui.VERT + "actif") if e["actif"] else (ui.DISCRET + "coupé")
            ui.info(f"   {ui.OR}[{i:>2}]{ui.TEXTE} {e['nom']}   {ui.DISCRET}· {e['ou']}   {etat}{ui.BASE}")
        ui.info(f"\n   {ui.OR}[ 0]{ui.TEXTE} Revenir")
        ui.info("\n  Seuls les raccourcis du dossier Démarrage peuvent être coupés ici (réversible).", ui.DISCRET)
        ui.info("  Pour les entrées du Registre : Gestionnaire des tâches → onglet Démarrage.", ui.DISCRET)
        choix = ui.demander_texte("Numéro à couper/réactiver, ou 0").strip()
        if choix in ("0", ""):
            return
        try:
            entree = entrees[int(choix) - 1]
        except (ValueError, IndexError):
            continue
        if not entree["modifiable"]:
            ui.info("\n  Cette entrée vient du Registre : elle ne peut pas être changée ici.", ui.OR)
            ui.attendre_touche()
            continue
        verbe = "couper" if entree["actif"] else "réactiver"
        ui._ecrire(f"\n  {ui.OR}{verbe.capitalize()} « {entree['nom']} » au démarrage ? [o/n] {ui.BLANC}")
        rep = ui.lire_touche({"o", "n"})
        ui._ecrire(rep + "\n")
        if rep == "o":
            try:
                _basculer(entree)
                ui.info(f"  ✓ {entree['nom']} {'coupé' if entree['actif'] else 'réactivé'}.", ui.VERT)
            except OSError as e:
                ui.erreur(f"Impossible de modifier ce raccourci : {e}")
            ui.attendre_touche()


def menu(conf):
    """Menu de l'optimisation. conf n'est pas modifié (rien ici n'a de réglage
    à mémoriser) mais est reçu pour rester cohérent avec les autres écrans."""
    while True:
        ui.effacer()
        ui.info("\n  ⚙  OPTIMISATION — nettoyage, démarrage\n", ui.CYAN)
        ui.info(f"   {ui.OR}[1]{ui.TEXTE} Analyser le disque (fichiers temporaires)")
        ui.info(f"   {ui.OR}[2]{ui.TEXTE} Nettoyer les fichiers temporaires")
        ui.info(f"   {ui.OR}[3]{ui.TEXTE} Vider la corbeille")
        ui.info(f"   {ui.OR}[4]{ui.TEXTE} Programmes au démarrage")
        ui.info(f"   {ui.OR}[0]{ui.TEXTE} Revenir au menu")
        choix = ui.demander_texte("Ton choix").strip()
        if choix in ("0", "", "retour", "exit"):
            return
        elif choix == "1":
            ecran_disque()
        elif choix == "2":
            nettoyer_temp()
        elif choix == "3":
            vider_corbeille()
        elif choix == "4":
            ecran_demarrage()
