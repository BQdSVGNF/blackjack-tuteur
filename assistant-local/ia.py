"""Black Jack : assistant local (Ollama) avec recherche web sourcée et commandes Windows.

- L'IA peut chercher sur le web (bloc ```recherche```) et cite ses sources [1], [2]...
- L'IA peut proposer des commandes Windows (bloc ```cmd```), exécutées après ta confirmation.
- Commandes : /web <question> force une recherche, reset efface la mémoire, exit quitte.
"""
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

import interface as ui

# On parle à Ollama par son API HTTP locale (pas de module à installer, donc
# rien que le « Contrôle intelligent des applications » de Windows puisse bloquer).
OLLAMA_URL = "http://localhost:11434/api/chat"


# ---------- Paramètres (sauvegardés dans parametres.json) ----------

CHEMIN_CONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parametres.json")
DEFAUTS = {
    "spotify": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
    "musique_auto": True,
    "animations": True,
    "pluie_densite": "moyenne",     # faible / moyenne / forte
    "pluie_vitesse": "normale",     # lente / normale / rapide
    "titre_cycle": True,            # titre arc-en-ciel animé
    "son": True,                    # bips de validation
    "crt": True,                    # effet scanlines / vieil écran
}
DENSITES = {"faible": 0.4, "moyenne": 0.8, "forte": 1.0}
VITESSES = {"lente": 0.6, "normale": 1.0, "rapide": 1.7}


def charger_conf():
    conf = dict(DEFAUTS)
    try:
        with open(CHEMIN_CONF, encoding="utf-8") as fp:
            conf.update(json.load(fp))
    except Exception:
        pass
    return conf


def sauver_conf(conf):
    try:
        with open(CHEMIN_CONF, "w", encoding="utf-8") as fp:
            json.dump(conf, fp, indent=2, ensure_ascii=False)
    except Exception as e:
        ui.erreur(f"Impossible d'enregistrer les paramètres : {e}")


def appliquer_conf(conf):
    ui.appliquer_params(
        animations=conf.get("animations", True),
        densite=DENSITES.get(conf.get("pluie_densite"), 0.8),
        vitesse=VITESSES.get(conf.get("pluie_vitesse"), 1.0),
        cycle=conf.get("titre_cycle", True),
        son=conf.get("son", True),
        crt=conf.get("crt", True),
    )


def lancer_musique(conf):
    """Ouvre Spotify sur la playlist choisie (Windows uniquement)."""
    if conf.get("musique_auto") and conf.get("spotify") and hasattr(os, "startfile"):
        try:
            os.startfile(conf["spotify"])          # ouvre l'URI spotify: via l'appli
        except Exception:
            pass


def _suivant(valeur, choix):
    """Renvoie l'élément suivant dans une liste (pour faire défiler une option)."""
    try:
        return choix[(choix.index(valeur) + 1) % len(choix)]
    except ValueError:
        return choix[0]


def ecran_parametres(conf):
    """Mode Paramètres : règle Spotify, les couleurs/LED et la pluie."""
    while True:
        oui = lambda b: "oui" if b else "non"
        ui.effacer()
        ui.info("\n  ⚙  PARAMÈTRES  —  tape un numéro pour modifier, 0 pour revenir\n", ui.CYAN)
        lignes = [
            ("1", "Playlist / lien Spotify", conf["spotify"]),
            ("2", "Musique au lancement", oui(conf["musique_auto"])),
            ("3", "Animations (intro + pluie)", oui(conf["animations"])),
            ("4", "Densité de la pluie", conf["pluie_densite"]),
            ("5", "Vitesse de la pluie", conf["pluie_vitesse"]),
            ("6", "Titre arc-en-ciel (sinon fixe)", oui(conf["titre_cycle"])),
            ("7", "Son (bips de validation)", oui(conf["son"])),
            ("8", "Effet CRT (scanlines)", oui(conf["crt"])),
            ("0", "Revenir au menu", ""),
        ]
        for num, nom, val in lignes:
            ligne = f"   {ui.OR}[{num:>2}]{ui.TEXTE} {nom:<32}"
            if val:
                ligne += f"{ui.VERT}{val}"
            ui.info(ligne + ui.BASE)
        choix = ui.demander_texte("Ton choix").strip().lower()

        if choix in ("0", "", "retour", "exit"):
            break
        elif choix == "1":
            nv = ui.demander_texte("Colle ton lien Spotify (spotify:playlist:… ou https://open.spotify.com/…)")
            if nv:
                conf["spotify"] = nv.strip()
        elif choix == "2":
            conf["musique_auto"] = not conf["musique_auto"]
        elif choix == "3":
            conf["animations"] = not conf["animations"]
        elif choix == "4":
            conf["pluie_densite"] = _suivant(conf["pluie_densite"], ["faible", "moyenne", "forte"])
        elif choix == "5":
            conf["pluie_vitesse"] = _suivant(conf["pluie_vitesse"], ["lente", "normale", "rapide"])
        elif choix == "6":
            conf["titre_cycle"] = not conf["titre_cycle"]
        elif choix == "7":
            conf["son"] = not conf["son"]
        elif choix == "8":
            conf["crt"] = not conf["crt"]
        else:
            continue
        sauver_conf(conf)
        appliquer_conf(conf)
    ui.afficher_menu(MODELE)

try:
    from ddgs import DDGS
except Exception:
    try:
        from duckduckgo_search import DDGS
    except Exception:
        DDGS = None

MODELE = "black-jack"  # créé à partir du Modelfile
MAX_MESSAGES = 16  # reste dans les 8192 tokens de contexte
NB_RESULTATS = 5
NB_PAGES_LUES = 3

BLOC_CMD = re.compile(r"```(?:cmd|bat|batch|powershell)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
BLOC_RECHERCHE = re.compile(r"```(?:recherche|search|web)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


# ---------- IA ----------

def demander_ia(historique):
    corps = json.dumps({
        "model": MODELE,
        "messages": historique[-MAX_MESSAGES:],   # la personnalité est dans le Modelfile
        "stream": True,
        "keep_alive": "30m",
    }).encode("utf-8")
    requete = urllib.request.Request(OLLAMA_URL, data=corps,
                                     headers={"Content-Type": "application/json"})
    reponse = ""
    animation = ui.Animation("Black Jack réfléchit").demarrer()
    try:
        with urllib.request.urlopen(requete, timeout=120) as flux:
            for ligne in flux:                     # Ollama renvoie un JSON par ligne
                ligne = ligne.strip()
                if not ligne:
                    continue
                bloc = json.loads(ligne)
                texte = bloc.get("message", {}).get("content", "")
                if texte:
                    if animation:                  # 1er morceau : on arrête l'animation
                        animation.arreter()
                        animation = None
                        ui.etiquette_ia()
                    ui.morceau_ia(texte)
                    reponse += texte
                if bloc.get("done"):
                    break
    except urllib.error.URLError as e:
        if animation:
            animation.arreter()
        raise RuntimeError(f"Ollama injoignable ({getattr(e, 'reason', e)}). "
                           "Lance Ollama (ou c'est normal s'il n'est pas installé sur cet appareil).")
    finally:
        if animation:
            animation.arreter()
    ui.fin_reponse()
    return reponse


# ---------- Recherche web ----------

def texte_de_la_page(url, limite=1500):
    """Télécharge une page et renvoie son texte brut (sans HTML), tronqué."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            brut = r.read(400_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except Exception:
        return ""
    brut = re.sub(r"(?is)<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>", " ", brut)
    texte = html.unescape(re.sub(r"(?s)<[^>]+>", " ", brut))
    return re.sub(r"\s+", " ", texte).strip()[:limite]


def recherche_web(requete):
    """Renvoie un bloc de texte avec les résultats numérotés et leurs URLs."""
    if DDGS is None:
        return "[recherche impossible : module 'ddgs' manquant, lance : pip install ddgs]"
    try:
        with ui.Animation(f"Black Jack fouille le web : {requete}"):
            resultats = list(DDGS().text(requete, max_results=NB_RESULTATS))
    except Exception as e:
        ui.erreur(f"Recherche échouée : {e}")
        return f"[recherche échouée : {e}]"
    ui.info(f"\n♦ Recherche : {requete}", ui.OR)
    if not resultats:
        return "[aucun résultat]"

    blocs = []
    with ui.Animation("Black Jack lit les pages"):
        for i, r in enumerate(resultats, 1):
            url = r.get("href") or r.get("url", "")
            contenu = r.get("body", "")
            if i <= NB_PAGES_LUES:
                page = texte_de_la_page(url)
                if page:
                    contenu = page
            blocs.append(f"[{i}] {r.get('title', '')}\nURL : {url}\n{contenu}")
    for i, r in enumerate(resultats, 1):
        ui.info(f"   [{i}] {r.get('title', '')} - {r.get('href') or r.get('url', '')}")
    return "\n\n".join(blocs)


def message_resultats(requete, resultats):
    return (f"Résultats de la recherche web pour « {requete} » :\n\n{resultats}\n\n"
            "Réponds maintenant à ma question avec ces informations. Cite tes sources avec "
            "[1], [2]... dans le texte et termine par la liste « Sources : » avec les URLs.")


# ---------- Commandes Windows ----------

def executer(commande):
    try:
        res = subprocess.run(commande, shell=True, capture_output=True, text=True,
                             timeout=120, encoding="cp850", errors="replace")
        sortie = (res.stdout or "") + (res.stderr or "")
        return f"[code {res.returncode}]\n{sortie.strip()[:4000]}"
    except subprocess.TimeoutExpired:
        return "[erreur] commande trop longue (plus de 120 s), arrêtée."


def gerer_commandes(commandes):
    resultats = []
    for cmd in commandes:
        choix = ui.demander_confirmation(cmd)
        if choix == "t":
            for reste in commandes[commandes.index(cmd):]:
                ui.info(f"♦ {reste}", ui.OR)
                r = executer(reste)
                ui.info(r)
                resultats.append(f"$ {reste}\n{r}")
            break
        if choix == "o":
            r = executer(cmd)
            ui.info(r)
            resultats.append(f"$ {cmd}\n{r}")
        else:
            resultats.append(f"$ {cmd}\n[refusée par l'utilisateur]")
    return "Résultat des commandes :\n" + "\n\n".join(resultats)


# ---------- Menu (raccourcis numérotés) ----------

# Chaque entrée : ("prompt", texte)  -> envoyé à l'IA
#                 ("cmd", commande)  -> commande Windows lancée directement
#                 ("info", texte)    -> simple message
#                 ("lancer",)        -> demande un programme et l'ouvre
#                 ("reset",)         -> nouvelle partie
RACCOURCIS = {
    "1": ("info", "Pose ta question ou écris ton message, tout simplement."),
    "2": ("info", "Tape : /web suivi de ta question (ex. : /web prix RTX 4060)."),
    "3": ("prompt", "Active le mode CODEX : tu es un assistant de code expert "
                    "(C++, Python, web, scripts…). Demande-moi le langage et ce que je veux "
                    "faire, puis donne le code complet, prêt à compiler/exécuter, avec une "
                    "courte explication et comment le lancer."),
    "4": ("reset",),
    "5": ("prompt", "Explique-moi la stratégie de base au blackjack sous forme de tableau "
                    "clair (ma main en lignes, la carte du croupier en colonnes)."),
    "6": ("prompt", "Apprends-moi à compter les cartes au blackjack avec le système Hi-Lo, "
                    "étape par étape, avec un exemple."),
    "7": ("prompt", "Fais-moi un quiz de blackjack : donne-moi une situation (ma main + la "
                    "carte du croupier) et demande-moi ce que je ferais, puis corrige."),
    "8": ("cmd", "systeminfo"),
    "9": ("cmd", 'powershell -NoProfile -Command "Get-CimInstance Win32_LogicalDisk | '
                 "Select-Object DeviceID,"
                 "@{n='LibreGo';e={[math]::Round($_.FreeSpace/1GB,1)}},"
                 "@{n='TotalGo';e={[math]::Round($_.Size/1GB,1)}} | Format-Table -AutoSize\""),
    "10": ("lancer",),
    "11": ("cmd", 'ipconfig | findstr /i "IPv4"'),
    "12": ("cmd", "ping -n 4 8.8.8.8"),
    "13": ("cmd", "netstat -n"),
}


def gerer_raccourci(saisie, historique):
    """Traite un numéro du menu.

    Retourne "ia" si un prompt a été injecté (l'IA doit répondre),
    "ok" si l'action est terminée, ou None si ce n'est pas un raccourci connu.
    """
    r = RACCOURCIS.get(saisie)
    if r is None:
        return None
    genre = r[0]
    if genre == "prompt":
        historique.append({"role": "user", "content": r[1]})
        return "ia"
    if genre == "info":
        ui.info("\n" + r[1], ui.OR)
    elif genre == "cmd":
        ui.info("\n♦ " + r[1], ui.OR)
        ui.info(executer(r[1]))
    elif genre == "lancer":
        nom = ui.demander_texte("Nom ou chemin du programme (ex. notepad)")
        if nom:
            ui.info(executer(f'start "" {nom}'))
    elif genre == "reset":
        historique.clear()
        ui.info("\n♠ Nouvelle partie : mémoire effacée.", ui.OR)
        ui.distribuer([("10", "♦"), ("A", "♣")])
    return "ok"


# ---------- Boucle principale ----------

def main():
    historique = []
    conf = charger_conf()
    appliquer_conf(conf)                 # applique les réglages avant l'intro
    lancer_musique(conf)                 # ouvre Spotify si activé
    ui.ecran_accueil(MODELE)
    while True:
        if ui.sur_menu:
            ui.demarrer_pulsation()      # fond animé pendant l'attente de saisie
        try:
            saisie = ui.demander_saisie().strip()
        except (EOFError, KeyboardInterrupt):
            break
        finally:
            ui.arreter_pulsation()
        if not saisie:
            continue                     # Entrée seule : on reste sur le menu (il repulse)
        if saisie.lower() == "exit":
            break
        if saisie.lower() == "menu":
            ui.afficher_menu(MODELE)
            continue
        if saisie == "14" or saisie.lower() in ("params", "paramètres", "parametres"):
            ecran_parametres(conf)       # redessine le menu en sortant
            continue
        ui.sur_menu = False              # à partir d'ici l'écran défile, plus de pulsation
        if saisie.lower() == "reset":
            historique.clear()
            ui.info("\n♠ Nouvelle partie : mémoire effacée.", ui.OR)
            ui.distribuer([("10", "♦"), ("A", "♣")])
            ui.separateur()
            continue

        raccourci = gerer_raccourci(saisie, historique)
        if raccourci == "ok":
            ui.separateur()
            continue
        elif raccourci is None:
            if saisie.lower().startswith("/web "):
                question = saisie[5:].strip()
                historique.append({"role": "user", "content": question})
                historique.append({"role": "user",
                                   "content": message_resultats(question, recherche_web(question))})
            else:
                historique.append({"role": "user", "content": saisie})

        # L'IA peut enchaîner recherches et commandes (5 étapes max)
        for _ in range(5):
            try:
                reponse = demander_ia(historique)
            except Exception as e:
                ui.erreur(f"Erreur Ollama : {e} (Ollama est-il lancé ? 'ollama serve')")
                break
            historique.append({"role": "assistant", "content": reponse})

            recherches = [r.strip() for r in BLOC_RECHERCHE.findall(reponse) if r.strip()]
            if recherches:
                requete = recherches[0].splitlines()[0]
                historique.append({"role": "user",
                                   "content": message_resultats(requete, recherche_web(requete))})
                continue

            commandes = [l.strip() for b in BLOC_CMD.findall(reponse)
                         for l in b.splitlines() if l.strip()]
            if commandes:
                historique.append({"role": "user", "content": gerer_commandes(commandes)})
                continue
            break
        ui.separateur()
    ui.ecran_sortie()


if __name__ == "__main__":
    main()
