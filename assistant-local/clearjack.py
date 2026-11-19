"""ClearJack : nettoyer et optimiser son PC Windows, sans IA.

Lancement : double-clic sur lancer_clearjack.bat (ou « python clearjack.py »).

Principes :
  · rien n'est supprimé ni modifié sans confirmation explicite (o/n) ;
  · tout ce qui touche au système passe par les outils officiels de Windows
    (Nettoyage de disque, Assistant stockage, powercfg, PowerShell) ;
  · aucune action dangereuse : pas de « débridage » de carte graphique, pas de
    priorité « temps réel », pas de nettoyage du Registre.
"""
import csv
import io
import os
import shutil
import subprocess
import sys

import interface as ui
import optimisation as opt
import coffre

WINDOWS = os.name == "nt"

# ---------- Palette « pro » : bleu nuit + cyan glacé ----------
C_TITRE = ui._txt(120, 220, 255)
C_TEXTE = ui._txt(205, 215, 230)
C_DISCRET = ui._txt(110, 125, 150)
C_OK = ui._txt(90, 230, 150)
C_ALERTE = ui._txt(255, 190, 90)
C_DANGER = ui._txt(255, 100, 100)
C_CADRE = ui._txt(70, 110, 160)
C_NUM = ui._txt(130, 200, 255)

# ---------- Titre en relief (lettres pleines + ombre portée) ----------
_LETTRES = {
    "C": [" ██████╗", "██╔════╝", "██║     ", "██║     ", "╚██████╗", " ╚═════╝"],
    "L": ["██╗     ", "██║     ", "██║     ", "██║     ", "███████╗", "╚══════╝"],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "J": ["     ██╗", "     ██║", "     ██║", "██   ██║", "╚█████╔╝", " ╚════╝ "],
    "K": ["██╗  ██╗", "██║ ██╔╝", "█████╔╝ ", "██╔═██╗ ", "██║  ██╗", "╚═╝  ╚═╝"],
}
# dégradé vertical de la face avant (haut clair → bas profond) : effet de volume
_DEGRADE = [(170, 240, 255), (120, 215, 255), (80, 180, 250),
            (60, 145, 235), (50, 110, 210), (40, 80, 170)]
_OMBRE = ui._txt(40, 55, 85)                      # la tranche / l'ombre portée


def _titre(mot="CLEARJACK"):
    """Le titre en relief. Chaque █ prend la couleur de sa ligne (dégradé), les
    traits ╔═╗ forment l'ombre portée en bleu ardoise : un vrai effet 3D net."""
    lignes = []
    for r in range(6):
        morceaux = []
        for lettre in mot:
            for ch in _LETTRES[lettre][r]:
                if ch == "█":
                    morceaux.append(ui._txt(*_DEGRADE[r]) + ch)
                elif ch == " ":
                    morceaux.append(" ")
                else:
                    morceaux.append(_OMBRE + ch)
        lignes.append("".join(morceaux) + ui.BASE)
    return lignes


def _largeur():
    return max(min(ui.largeur() - 1, 200), 40)


def _centrer(texte, visible=None):
    n = ui._long_visible(texte) if visible is None else visible
    return " " * max((_largeur() - n) // 2, 0) + texte


def _ecrire(texte=""):
    ui._ecrire(ui.BASE + texte + ui.BASE + "\n")


def _entete(sous_titre):
    """Haut de chaque écran : titre en relief (si la fenêtre est assez large) +
    sous-titre centré."""
    ui.ecran_defilant()
    W = _largeur()
    if W >= 76 and ui._dim()[1] >= 26:
        _ecrire()
        for l in _titre():
            _ecrire(_centrer(l, 72))
        _ecrire(_centrer(C_DISCRET + "nettoyer · optimiser · protéger", 31))
    else:
        _ecrire()
        _ecrire(_centrer(C_TITRE + ui.GRAS + "C L E A R J A C K", 17))
    _ecrire()
    if sous_titre:
        trait = "─" * min(W - 8, 74)
        _ecrire(_centrer(C_CADRE + trait, len(trait)))
        _ecrire(_centrer(C_TITRE + ui.GRAS + sous_titre, len(sous_titre)))
        _ecrire(_centrer(C_CADRE + trait, len(trait)))
        _ecrire()


def _demander(invite):
    try:
        return ui.demander_texte(invite).strip()
    except (EOFError, KeyboardInterrupt):
        return "0"


def _confirmer(question):
    rep = _demander(f"{question} (o/n)").lower()
    return rep in ("o", "oui", "y", "yes")


def _pause():
    _demander("Entrée pour revenir")


def _windows_seulement():
    if WINDOWS:
        return False
    _ecrire("  " + C_ALERTE + "Cette fonction utilise des outils de Windows : elle ne marche que sous Windows.")
    _pause()
    return True


def _cmd(args, timeout=30):
    """Lance une commande et renvoie sa sortie texte ('' si elle échoue)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.stdout or ""
    except Exception:
        return ""


def _powershell(script, timeout=30):
    return _cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout)


def _jauge(pct, larg=30):
    if pct is None:
        return C_DISCRET + "  —"
    pct = max(0, min(100, pct))
    plein = int(round(larg * pct / 100))
    coul = C_OK if pct < 70 else (C_ALERTE if pct < 90 else C_DANGER)
    return coul + "█" * plein + C_DISCRET + "░" * (larg - plein) + ui.BASE + C_TEXTE + f" {pct:3.0f} %"


# =====================================================================
#  1. DIAGNOSTIC (lecture seule)
# =====================================================================

def _lecteurs():
    if WINDOWS:
        return [f"{l}:\\" for l in "CDEFGHIJ" if os.path.exists(f"{l}:\\")]
    return ["/"]


def diagnostic():
    _entete("DIAGNOSTIC · ce qui prend de la place (rien n'est supprimé)")
    _ecrire("  " + C_TITRE + ui.GRAS + "Disques")
    for lect in _lecteurs():
        try:
            u = shutil.disk_usage(lect)
        except OSError:
            continue
        pct = 100 * u.used / u.total if u.total else 0
        _ecrire(f"  {C_TEXTE}{lect:<4} {_jauge(pct)}   {C_DISCRET}libre {opt._fmt_octets(u.free)}"
                f" sur {opt._fmt_octets(u.total)}")
    _ecrire()
    _ecrire("  " + C_TITRE + ui.GRAS + "Tes dossiers les plus lourds " + C_DISCRET + "(calcul en cours…)")
    maison = os.path.expanduser("~")
    candidats = ["Downloads", "Téléchargements", "Desktop", "Bureau", "Documents",
                 "Videos", "Vidéos", "Pictures", "Images", "Music", "Musique"]
    vus, mesures = set(), []
    for nom in candidats:
        chemin = os.path.join(maison, nom)
        reel = os.path.realpath(chemin)
        if os.path.isdir(chemin) and reel not in vus:
            vus.add(reel)
            taille, n, tronque = opt._taille_dossier(chemin)
            mesures.append((taille, chemin, n, tronque))
    for chemin in opt._dossiers_temp():
        if os.path.isdir(chemin) and os.path.realpath(chemin) not in vus:
            vus.add(os.path.realpath(chemin))
            taille, n, tronque = opt._taille_dossier(chemin)
            mesures.append((taille, chemin + "   (temporaires : nettoyables)", n, tronque))
    for taille, chemin, n, tronque in sorted(mesures, reverse=True):
        plus = "+" if tronque else ""
        _ecrire(f"  {C_NUM}{opt._fmt_octets(taille):>10}{plus:<1}  {C_TEXTE}{chemin}  "
                f"{C_DISCRET}({n}{plus} fichiers)")
    if not mesures:
        _ecrire("  " + C_DISCRET + "Aucun dossier personnel trouvé.")
    _ecrire()
    _ecrire("  " + C_DISCRET + "Astuce : le plus gros gain vient souvent de Téléchargements et des jeux")
    _ecrire("  " + C_DISCRET + "que tu n'utilises plus. Pour les fichiers de Windows, va dans [2] Nettoyage.")
    _pause()


# =====================================================================
#  2. NETTOYAGE
# =====================================================================

def _ouvrir_cleanmgr():
    if _windows_seulement():
        return
    _entete("NETTOYAGE DE DISQUE DE WINDOWS")
    _ecrire("  " + C_TEXTE + "L'outil officiel de Windows va s'ouvrir. Choisis le disque C:, puis clique sur")
    _ecrire("  " + C_TEXTE + "« Nettoyer les fichiers système » pour inclure les anciennes mises à jour.")
    _ecrire("  " + C_DISCRET + "C'est lui qui décide de ce qui peut être supprimé sans risque.")
    try:
        subprocess.Popen(["cleanmgr"])
        _ecrire("\n  " + C_OK + "Ouvert ✓")
    except Exception as e:
        _ecrire("\n  " + C_DANGER + f"Impossible de l'ouvrir : {e}")
    _pause()


def _ouvrir_assistant_stockage():
    if _windows_seulement():
        return
    _entete("ASSISTANT STOCKAGE (nettoyage automatique)")
    _ecrire("  " + C_TEXTE + "La page des Paramètres va s'ouvrir. Active l'Assistant stockage : Windows videra")
    _ecrire("  " + C_TEXTE + "lui-même les fichiers temporaires et la corbeille, régulièrement.")
    try:
        os.startfile("ms-settings:storagesense")
        _ecrire("\n  " + C_OK + "Ouvert ✓")
    except Exception as e:
        _ecrire("\n  " + C_DANGER + f"Impossible de l'ouvrir : {e}")
    _pause()


def _analyser_winsxs():
    if _windows_seulement():
        return
    _entete("ANALYSE DU DOSSIER WINSXS (lecture seule)")
    _ecrire("  " + C_TEXTE + "WinSxS garde les composants et anciennes mises à jour de Windows.")
    _ecrire("  " + C_TEXTE + "Pour savoir ce qui est récupérable, ouvre un terminal EN ADMINISTRATEUR et tape :")
    _ecrire()
    _ecrire("     " + C_NUM + "Dism.exe /Online /Cleanup-Image /AnalyzeComponentStore")
    _ecrire()
    _ecrire("  " + C_TEXTE + "S'il recommande un nettoyage, cette commande-ci est sans danger :")
    _ecrire()
    _ecrire("     " + C_NUM + "Dism.exe /Online /Cleanup-Image /StartComponentCleanup")
    _ecrire()
    _ecrire("  " + C_DANGER + "À éviter : l'option /ResetBase. Elle empêche définitivement de désinstaller")
    _ecrire("  " + C_DANGER + "les mises à jour déjà installées.")
    _pause()


def menu_nettoyage():
    while True:
        _entete("NETTOYAGE")
        items = [("1", "Vider les fichiers temporaires", "avec confirmation"),
                 ("2", "Vider la corbeille", "avec confirmation"),
                 ("3", "Nettoyage de disque de Windows", "anciennes mises à jour, caches"),
                 ("4", "Activer l'Assistant stockage", "nettoyage automatique"),
                 ("5", "WinSxS : comment l'analyser", "explications"),
                 ("0", "Retour", "")]
        _menu_items(items)
        c = _demander("Ton choix")
        if c in ("0", "", "q"):
            return
        if c == "1":
            opt.nettoyer_temp()
        elif c == "2":
            opt.vider_corbeille()
        elif c == "3":
            _ouvrir_cleanmgr()
        elif c == "4":
            _ouvrir_assistant_stockage()
        elif c == "5":
            _analyser_winsxs()


# =====================================================================
#  3. BOOSTER UNE APPLICATION (priorité processeur)
# =====================================================================

def _processus():
    """Liste (nom, pid, mémoire Mo, temps CPU s) triée par mémoire. Windows."""
    sortie = _powershell(
        "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 "
        "Name,Id,@{n='Mo';e={[int]($_.WorkingSet64/1MB)}},@{n='CPU';e={[int]$_.CPU}},PriorityClass "
        "| ConvertTo-Csv -NoTypeInformation")
    res = []
    for ligne in csv.DictReader(io.StringIO(sortie)):
        try:
            res.append((ligne["Name"], int(ligne["Id"]), int(ligne["Mo"] or 0),
                        int(ligne["CPU"] or 0), ligne.get("PriorityClass") or "?"))
        except (KeyError, ValueError):
            continue
    return res


def booster():
    if WINDOWS is False:
        _entete("BOOSTER UNE APPLICATION")
        _windows_seulement()
        return
    while True:
        _entete("BOOSTER UNE APPLICATION · priorité processeur")
        _ecrire("  " + C_TEXTE + "Lance ton jeu d'abord, puis choisis-le ici : Windows lui donnera la priorité")
        _ecrire("  " + C_TEXTE + "sur les programmes en arrière-plan. " + C_DISCRET
                + "(ça ne crée pas de puissance : ça la répartit mieux)")
        _ecrire()
        liste = _processus()
        if not liste:
            _ecrire("  " + C_DANGER + "Impossible de lire la liste des programmes (PowerShell indisponible ?).")
            _pause()
            return
        _ecrire("  " + C_DISCRET + f"{'#':>3}  {'Programme':<28}{'Mémoire':>10}{'CPU (s)':>10}   Priorité")
        for i, (nom, pid, mo, cpu, prio) in enumerate(liste, 1):
            _ecrire(f"  {C_NUM}{i:>3}  {C_TEXTE}{nom[:27]:<28}{mo:>7} Mo{cpu:>10}   {C_DISCRET}{prio}")
        _ecrire()
        c = _demander("Numéro à booster · N + numéro pour remettre en normal · 0 retour")
        if c in ("0", "", "q"):
            return
        normal = c.lower().startswith("n")
        num = c[1:].strip() if normal else c
        if not num.isdigit() or not 1 <= int(num) <= len(liste):
            continue
        nom, pid = liste[int(num) - 1][:2]
        classe = "Normal" if normal else "High"
        if not normal and not _confirmer(f"Donner la priorité HAUTE à « {nom} » (jusqu'à sa fermeture) ?"):
            continue
        _powershell(f"(Get-Process -Id {pid}).PriorityClass = '{classe}'")
        apres = _powershell(f"(Get-Process -Id {pid}).PriorityClass").strip()
        if apres == classe:
            _ecrire("  " + C_OK + f"« {nom} » est maintenant en priorité {'normale' if normal else 'haute'} ✓")
        else:
            _ecrire("  " + C_ALERTE + "Windows a refusé (il faut parfois lancer ClearJack en administrateur).")
        _pause()


# =====================================================================
#  4. ÉTAT DU MATÉRIEL (lecture seule)
# =====================================================================

def materiel():
    _entete("ÉTAT DU MATÉRIEL (lecture seule)")
    _ecrire("  " + C_TITRE + ui.GRAS + "Processeur et mémoire")
    _ecrire(f"  {C_TEXTE}Processeur  {_jauge(ui._stat_cpu())}")
    _ecrire(f"  {C_TEXTE}Mémoire     {_jauge(ui._stat_ram())}")
    _ecrire()
    _ecrire("  " + C_TITRE + ui.GRAS + "Carte graphique")
    sortie = _cmd(["nvidia-smi", "--query-gpu=name,driver_version,temperature.gpu,utilization.gpu,"
                   "memory.used,memory.total,clocks.gr,power.draw",
                   "--format=csv,noheader,nounits"], timeout=10).strip()
    if sortie:
        for ligne in sortie.splitlines():
            v = [x.strip() for x in ligne.split(",")]
            if len(v) < 8:
                continue
            nom, pilote, temp, util, mu, mt, horloge, watts = v[:8]
            try:
                pct_mem = 100 * float(mu) / float(mt)
            except ValueError:
                pct_mem = None
            try:
                t = float(temp)
                ct = C_OK if t < 70 else (C_ALERTE if t < 83 else C_DANGER)
            except ValueError:
                ct = C_TEXTE
            _ecrire(f"  {C_TEXTE}{nom}   {C_DISCRET}pilote {pilote}")
            _ecrire(f"  {C_TEXTE}Charge      {_jauge(float(util) if util.replace('.', '').isdigit() else None)}")
            _ecrire(f"  {C_TEXTE}Mémoire vid.{_jauge(pct_mem)}  {C_DISCRET}{mu} / {mt} Mo")
            _ecrire(f"  {C_TEXTE}Température {ct}{temp} °C   {C_DISCRET}fréquence {horloge} MHz · {watts} W")
    elif WINDOWS:
        noms = _powershell("Get-CimInstance Win32_VideoController | "
                           "ForEach-Object { $_.Name + ' — pilote ' + $_.DriverVersion }").strip()
        _ecrire("  " + C_TEXTE + (noms or "Carte graphique non détectée."))
        _ecrire("  " + C_DISCRET + "(détails en direct disponibles avec une carte NVIDIA et son pilote)")
    else:
        _ecrire("  " + C_DISCRET + "Non détectée sur ce système.")
    _ecrire()
    _ecrire("  " + C_TITRE + ui.GRAS + "Conseils pour gagner en fluidité, sans risque")
    for t in ("Mets à jour le pilote graphique depuis le site officiel (NVIDIA ou AMD).",
              "Dans les jeux, baisse d'abord l'ombre, les reflets et l'anticrénelage.",
              "Passe en mode « Performances élevées » ([5]) quand tu joues sur secteur.",
              "Ferme les programmes lourds en arrière-plan (navigateur avec 40 onglets…).",
              "Surveille la température : au-delà de ~85 °C, nettoie la poussière du PC."):
        _ecrire("  " + C_OK + "› " + C_TEXTE + t)
    _ecrire()
    _ecrire("  " + C_ALERTE + "Débrider la carte (BIOS modifié, tension forcée) : déconseillé — risque de")
    _ecrire("  " + C_ALERTE + "la griller, perte de garantie, gain faible. ClearJack ne le fera pas.")
    _pause()


# =====================================================================
#  5. MODE PERFORMANCES (plan d'alimentation Windows)
# =====================================================================

_PLANS = {"1": ("SCHEME_MIN", "Performances élevées"),
          "2": ("SCHEME_BALANCED", "Utilisation normale recommandée"),
          "3": ("SCHEME_MAX", "Économie d'énergie")}


def performances():
    if WINDOWS is False:
        _entete("MODE PERFORMANCES")
        _windows_seulement()
        return
    while True:
        _entete("MODE PERFORMANCES · plan d'alimentation")
        actuel = _cmd(["powercfg", "/getactivescheme"]).strip()
        _ecrire("  " + C_DISCRET + "Plan actuel : " + C_TEXTE + (actuel.split("(")[-1].rstrip(")") if "(" in actuel
                                                                else actuel or "inconnu"))
        _ecrire()
        _menu_items([("1", "Performances élevées", "pour jouer, sur secteur"),
                     ("2", "Normal (recommandé)", "le réglage par défaut"),
                     ("3", "Économie d'énergie", "sur batterie"),
                     ("0", "Retour", "")])
        c = _demander("Ton choix")
        if c in ("0", "", "q"):
            return
        if c in _PLANS:
            alias, nom = _PLANS[c]
            if _confirmer(f"Passer en « {nom} » ?"):
                _cmd(["powercfg", "/setactive", alias])
                _ecrire("  " + C_OK + "Fait ✓ " + C_DISCRET + "(réversible à tout moment ici)")
                _pause()


# =====================================================================
#  MENU PRINCIPAL
# =====================================================================

# =====================================================================
#  8. OUTILS RECOMMANDÉS (logiciels gratuits et légaux, à installer soi-même)
# =====================================================================
# Chaque outil : nom, catégorie, description, site, identifiant winget (ou None),
# chemins possibles de l'exécutable (sous Program Files / AppData / WinGet).
# L'installation passe par winget, l'installeur officiel de Windows, et seulement
# après confirmation. Si l'identifiant winget est inconnu, on ouvre le site.

def _recherche(nom):
    import urllib.parse
    return "https://duckduckgo.com/?q=" + urllib.parse.quote(nom + " site officiel")


OUTILS = [
    # --- Nettoyage ---
    ("BleachBit", "Nettoyage", "nettoyeur libre, montre ce qu'il va supprimer avant",
     "https://www.bleachbit.org/", "BleachBit.BleachBit", [r"BleachBit\bleachbit.exe"]),
    ("Wise Disk Cleaner", "Nettoyage", "nettoyeur simple avec planification (non libre)",
     "https://www.wisecleaner.com/wise-disk-cleaner.html", None,
     [r"Wise\Wise Disk Cleaner\WiseDiskCleaner.exe"]),
    ("Glary Utilities", "Nettoyage", "boîte à outils complète ; refuse les options en plus à l'installation",
     "https://www.glarysoft.com/", None, [r"Glary Utilities 5\Integrator.exe"]),
    ("CleanSweep", "Nettoyage", "nettoyeur présenté comme open source", _recherche("CleanSweep nettoyage Windows"),
     None, []),
    ("FluentCleaner", "Nettoyage", "nettoyeur léger, axé vie privée", _recherche("FluentCleaner"), None, []),
    # --- Analyse de l'espace disque ---
    ("WinDirStat", "Espace disque", "carte colorée de ce qui prend la place (libre)",
     "https://windirstat.net/", "WinDirStat.WinDirStat", [r"WinDirStat\WinDirStat.exe"]),
    ("WizTree", "Espace disque", "le plus rapide sur les gros disques",
     "https://diskanalyzer.com/", "AntibodySoftware.WizTree", [r"WizTree\WizTree64.exe", r"WizTree\WizTree.exe"]),
    ("TreeSize Free", "Espace disque", "dossiers triés par taille, clic droit dans l'Explorateur",
     "https://www.jam-software.com/treesize_free", "JAMSoftware.TreeSize.Free",
     [r"JAM Software\TreeSize Free\TreeSizeFree.exe"]),
    ("SpaceSniffer", "Espace disque", "visualisation graphique, portable",
     "http://www.uderzo.it/main_products/space_sniffer/", None, []),
    ("JDiskReport", "Espace disque", "graphiques de l'occupation (nécessite Java)",
     "https://www.jgoodies.com/freeware/jdiskreport/", None, []),
    # --- Surveillance des composants ---
    ("HWiNFO", "Composants", "TOUTES les températures, fréquences, tensions (lecture seule)",
     "https://www.hwinfo.com/", "REALiX.HWiNFO", [r"HWiNFO64\HWiNFO64.exe", r"HWiNFO\HWiNFO64.exe"]),
    ("MSI Afterburner", "Composants", "suivi en jeu ; ses réglages d'overclocking = prudence",
     "https://www.msi.com/Landing/afterburner/graphics-cards", "Guru3D.Afterburner",
     [r"MSI Afterburner\MSIAfterburner.exe"]),
    ("AMD Ryzen Master", "Composants", "outil officiel AMD (processeurs Ryzen uniquement)",
     "https://www.amd.com/en/products/software/ryzen-master.html", None,
     [r"AMD\RyzenMaster\bin\AMD Ryzen Master.exe"]),
    ("Intel XTU", "Composants", "outil officiel Intel (processeurs Intel uniquement)",
     "https://www.intel.com/content/www/us/en/download/17881/intel-extreme-tuning-utility-intel-xtu.html",
     None, [r"Intel\Intel(R) Extreme Tuning Utility\Client\XtuUiLauncher.exe"]),
    # --- Santé du disque et de la mémoire ---
    ("CrystalDiskInfo", "Santé matériel", "état de santé du disque/SSD (bleu = OK, rouge = danger)",
     "https://crystalmark.info/en/software/crystaldiskinfo/", "CrystalDewWorld.CrystalDiskInfo",
     [r"CrystalDiskInfo\DiskInfo64.exe", r"CrystalDiskInfo\DiskInfo32.exe"]),
    ("Diagnostic mémoire Windows", "Santé matériel", "test de la RAM intégré à Windows (redémarre le PC)",
     "builtin:mdsched", None, []),
    ("MemTest86", "Santé matériel", "test de RAM approfondi sur clé USB",
     "https://www.memtest86.com/", None, []),
    ("MemTest64", "Santé matériel", "test de RAM sous Windows (TechPowerUp)",
     "https://www.techpowerup.com/download/memtest64/", None, []),
    # --- Système (Microsoft Sysinternals) ---
    ("Autoruns", "Système", "TOUT ce qui démarre avec Windows (Microsoft)",
     "https://learn.microsoft.com/sysinternals/downloads/autoruns", "Microsoft.Sysinternals.Autoruns",
     ["@autoruns64", "@autoruns"]),
    ("Process Explorer", "Système", "gestionnaire des tâches avancé (Microsoft)",
     "https://learn.microsoft.com/sysinternals/downloads/process-explorer",
     "Microsoft.Sysinternals.ProcessExplorer", ["@procexp64", "@procexp"]),
    ("Suite Sysinternals", "Système", "tous les outils Sysinternals d'un coup (Microsoft)",
     "https://learn.microsoft.com/sysinternals/downloads/sysinternals-suite", None, []),
    ("HiBit Startup Manager", "Système", "gestionnaire de démarrage simple", _recherche("HiBit Startup Manager"),
     None, []),
    ("Autorun Organizer", "Système", "gestionnaire de démarrage simple",
     "https://www.chemtable.com/autorun-organizer.htm", None, []),
    # --- Sécurité ---
    ("AdwCleaner", "Sécurité", "retire les logiciels indésirables (Malwarebytes)",
     "https://www.malwarebytes.com/adwcleaner", None, []),
]

A_EVITER = [
    ("CCleaner", "En 2017, une version piratée a infecté ~2,27 millions de PC. Les versions officielles "
                 "suivantes sont saines, mais Windows fait déjà l'essentiel. Si tu l'utilises : site officiel."),
    ("Nettoyeurs de registre", "Gain quasi nul, risque de casser Windows."),
    ("Optimiseurs « tout-en-un » miracles", "Promettent beaucoup, installent souvent des logiciels en plus."),
    ("Débridage de carte graphique", "Risque de griller la carte et perte de garantie."),
]


def _trouver_exe(chemins):
    """Chemin de l'exécutable s'il est installé, sinon None."""
    for c in chemins:
        if c.startswith("@"):
            p = shutil.which(c[1:])
            if p:
                return p
            continue
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
            if base and os.path.isfile(os.path.join(base, c)):
                return os.path.join(base, c)
    return None


def _winget_ok():
    return bool(WINDOWS and shutil.which("winget"))


def _ouvrir_site(url):
    import webbrowser
    try:
        webbrowser.open(url)
        _ecrire("  " + C_OK + "Site ouvert dans ton navigateur ✓")
    except Exception as e:
        _ecrire("  " + C_DANGER + f"Impossible d'ouvrir le navigateur : {e}")
        _ecrire("  " + C_TEXTE + url)


def _fiche_outil(outil):
    nom, cat, desc, url, wid, chemins = outil
    while True:
        _entete(f"OUTIL · {nom}")
        _ecrire(f"  {C_DISCRET}Catégorie : {C_TEXTE}{cat}")
        _ecrire(f"  {C_DISCRET}À quoi ça sert : {C_TEXTE}{desc}")
        integre = url.startswith("builtin:")
        exe = None if integre else _trouver_exe(chemins)
        if integre:
            _ecrire(f"  {C_DISCRET}État : {C_OK}intégré à Windows")
        elif exe:
            _ecrire(f"  {C_DISCRET}État : {C_OK}installé ✓  {C_DISCRET}({exe})")
        else:
            _ecrire(f"  {C_DISCRET}État : {C_TEXTE}pas installé (ou installé ailleurs)")
        if not integre:
            _ecrire(f"  {C_DISCRET}Site : {C_TEXTE}{url}")
        _ecrire()
        choix = []
        if integre or exe:
            choix.append(("L", "Lancer"))
        if wid and not exe:
            choix.append(("I", "Installer avec winget (installeur officiel de Windows)"))
        if not integre:
            choix.append(("S", "Ouvrir le site officiel"))
        choix.append(("0", "Retour"))
        for k, lib in choix:
            _ecrire(f"   {C_NUM}{ui.GRAS}[{k}]{ui.BASE} {C_TEXTE}{lib}")
        c = _demander("Ton choix").lower()
        if c in ("0", "", "q"):
            return
        if c == "s" and not integre:
            _ouvrir_site(url)
            _pause()
        elif c == "l" and integre:
            if _windows_seulement():
                continue
            _ecrire("  " + C_ALERTE + "Windows va proposer de REDÉMARRER pour tester la mémoire.")
            if _confirmer("Ouvrir le diagnostic de mémoire Windows ?"):
                try:
                    subprocess.Popen(["mdsched.exe"])
                    _ecrire("  " + C_OK + "Ouvert ✓")
                except Exception as e:
                    _ecrire("  " + C_DANGER + f"Impossible : {e}")
                _pause()
        elif c == "l" and exe:
            try:
                os.startfile(exe)
                _ecrire("  " + C_OK + f"{nom} lancé ✓")
            except Exception as e:
                _ecrire("  " + C_DANGER + f"Impossible de le lancer : {e}")
            _pause()
        elif c == "i" and wid and not exe:
            if not _winget_ok():
                _ecrire("  " + C_ALERTE + "winget n'est pas disponible ici. Installe-le depuis le site officiel ([S]).")
                _pause()
                continue
            _ecrire("  " + C_TEXTE + f"Commande : {C_NUM}winget install --id {wid} --exact")
            if _confirmer(f"Installer {nom} ?"):
                _ecrire("  " + C_DISCRET + "Installation… (Windows peut demander une autorisation)")
                try:
                    r = subprocess.run(["winget", "install", "--id", wid, "--exact",
                                        "--accept-package-agreements", "--accept-source-agreements"])
                    _ecrire("  " + (C_OK + "Installé ✓" if r.returncode == 0
                                    else C_ALERTE + f"winget a renvoyé le code {r.returncode}."))
                except Exception as e:
                    _ecrire("  " + C_DANGER + f"Échec : {e}")
                _pause()


_CATEGORIES = [("Nettoyage", "fichiers inutiles"),
               ("Espace disque", "voir ce qui prend la place"),
               ("Composants", "températures, fréquences"),
               ("Santé matériel", "état du disque et de la mémoire"),
               ("Système", "démarrage, processus"),
               ("Sécurité", "logiciels indésirables")]


def _etat_outil(outil):
    url, chemins = outil[3], outil[5]
    if url.startswith("builtin:"):
        return C_OK + "intégré"
    if WINDOWS and _trouver_exe(chemins):
        return C_OK + "installé ✓"
    return ""


def _liste_categorie(cat):
    while True:
        _entete(f"OUTILS · {cat.upper()}")
        dans = [o for o in OUTILS if o[1] == cat]
        larg_desc = max(_largeur() - 46, 20)
        for i, o in enumerate(dans, 1):
            _ecrire(f"   {C_NUM}{ui.GRAS}{i:>2}{ui.BASE}  {C_TEXTE}{o[0]:<26}{C_DISCRET}{o[2][:larg_desc]}")
            etat = _etat_outil(o)
            if etat:
                _ecrire(f"       {etat}")
        _ecrire()
        c = _demander("Numéro de l'outil · 0 retour")
        if c in ("0", "", "q"):
            return
        if c.isdigit() and 1 <= int(c) <= len(dans):
            _fiche_outil(dans[int(c) - 1])


def _ecran_a_eviter():
    import textwrap
    _entete("À ÉVITER · et pourquoi")
    larg = max(_largeur() - 8, 30)
    for nom, pourquoi in A_EVITER:
        _ecrire(f"  {C_DANGER}{ui.GRAS}✗ {nom}")
        for l in textwrap.wrap(pourquoi, larg):
            _ecrire(f"    {C_TEXTE}{l}")
        _ecrire()
    _pause()


def outils_recommandes():
    while True:
        _entete("OUTILS RECOMMANDÉS · gratuits et légaux")
        items = []
        for i, (cat, desc) in enumerate(_CATEGORIES, 1):
            n = sum(1 for o in OUTILS if o[1] == cat)
            items.append((str(i), f"{cat} ({n})", desc))
        items.append(("7", "À éviter", "et pourquoi"))
        items.append(("0", "Retour", ""))
        _menu_items(items)
        _ecrire(_centrer(C_DISCRET + "Rien n'est installé sans ta confirmation.", 40))
        c = _demander("Ton choix")
        if c in ("0", "", "q"):
            return
        if c.isdigit() and 1 <= int(c) <= len(_CATEGORIES):
            _liste_categorie(_CATEGORIES[int(c) - 1][0])
        elif c == "7":
            _ecran_a_eviter()


def _menu_items(items):
    """Un cadre arrondi centré : numéro · titre · description (coupée si trop longue)."""
    larg = min(70, _largeur() - 4)
    dedans = larg - 2
    _ecrire(_centrer(C_CADRE + "╭" + "─" * dedans + "╮", larg))
    for num, titre, desc in items:
        tete = f"  {num:>2}  "
        titre = titre[:30].ljust(31)
        reste = max(dedans - len(tete) - len(titre), 0)
        desc = desc[:reste].ljust(reste)
        ligne = (C_CADRE + "│" + C_NUM + ui.GRAS + tete + ui.BASE + C_TEXTE + titre
                 + C_DISCRET + desc + C_CADRE + "│")
        _ecrire(_centrer(ligne, larg))
    _ecrire(_centrer(C_CADRE + "╰" + "─" * dedans + "╯", larg))


def menu_principal():
    while True:
        _entete("")
        _menu_items([("1", "Diagnostic", "ce qui prend de la place"),
                     ("2", "Nettoyage", "temporaires, corbeille, Windows"),
                     ("3", "Booster une application", "priorité pour un jeu"),
                     ("4", "État du matériel", "processeur, mémoire, GPU"),
                     ("5", "Mode performances", "plan d'alimentation"),
                     ("6", "Programmes au démarrage", "démarrer Windows plus vite"),
                     ("7", "Coffre", "chiffrer tes fichiers"),
                     ("8", "Outils recommandés", "les meilleurs logiciels gratuits"),
                     ("0", "Quitter", "")])
        c = _demander("Ton choix")
        if c in ("0", "q", "exit", "quitter"):
            return
        actions = {"1": diagnostic, "2": menu_nettoyage, "3": booster, "4": materiel,
                   "5": performances, "6": opt.ecran_demarrage, "8": outils_recommandes, "7": lambda: coffre.menu({})}
        if c in actions:
            try:
                actions[c]()
            except KeyboardInterrupt:
                pass
            except Exception as e:
                _ecrire("  " + C_DANGER + f"Erreur : {e}")
                _pause()


_SLOGANS_CJ = [
    "JE VOIS TOUT CE QUI ENCOMBRE TON PC.",
    "RIEN NE M'ÉCHAPPE. PAS MÊME TES FICHIERS TEMPORAIRES.",
    "TON DISQUE N'A PLUS DE SECRETS.",
    "JE SURVEILLE CHAQUE OCTET.",
]


def _accueil():
    """L'œil au lancement (comme dans Black Jack). ENTRÉE → menu, ÉCHAP → quitter."""
    t = ui._Taille()
    if not (ui.ANIMATIONS and sys.stdout.isatty() and t.columns >= 60 and t.lines >= 20):
        return True                                  # pas d'animation possible : direct au menu
    ui.TEXTE_ENTREE = "ouvrir ClearJack"
    return ui._accueil_oeil("ClearJack", slogans=_SLOGANS_CJ)


def main():
    ui.initialiser()
    try:
        if not _accueil():                           # ÉCHAP sur l'œil → on quitte
            return
        menu_principal()
    finally:
        ui.restaurer()


if __name__ == "__main__":
    main()
