"""Mon-IA : assistant local (Ollama) avec recherche web sourcée et commandes Windows.

- L'IA peut chercher sur le web (bloc ```recherche```) et cite ses sources [1], [2]...
- L'IA peut proposer des commandes Windows (bloc ```cmd```), exécutées après ta confirmation.
- Commandes : /web <question> force une recherche, reset efface la mémoire, exit quitte.
"""
import html
import re
import subprocess
import sys
import urllib.request

try:
    import ollama
except ImportError:
    print("Le module 'ollama' manque. Lance : pip install ollama")
    sys.exit(1)

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

MODELE = "mon-ia"  # créé à partir du Modelfile
MAX_MESSAGES = 16  # reste dans les 8192 tokens de contexte
NB_RESULTATS = 5
NB_PAGES_LUES = 3

BLOC_CMD = re.compile(r"```(?:cmd|bat|batch|powershell)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
BLOC_RECHERCHE = re.compile(r"```(?:recherche|search|web)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


# ---------- IA ----------

def demander_ia(historique):
    messages = historique[-MAX_MESSAGES:]  # la personnalité est dans le Modelfile
    reponse = ""
    print("IA: ", end="", flush=True)
    for morceau in ollama.chat(model=MODELE, messages=messages, stream=True, keep_alive="30m"):
        texte = morceau["message"]["content"]
        print(texte, end="", flush=True)
        reponse += texte
    print()
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
    print(f"\n🔎 Recherche : {requete}")
    try:
        resultats = list(DDGS().text(requete, max_results=NB_RESULTATS))
    except Exception as e:
        return f"[recherche échouée : {e}]"
    if not resultats:
        return "[aucun résultat]"

    blocs = []
    for i, r in enumerate(resultats, 1):
        url = r.get("href") or r.get("url", "")
        print(f"   [{i}] {r.get('title', '')} - {url}")
        contenu = r.get("body", "")
        if i <= NB_PAGES_LUES:
            page = texte_de_la_page(url)
            if page:
                contenu = page
        blocs.append(f"[{i}] {r.get('title', '')}\nURL : {url}\n{contenu}")
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
        choix = input(f"\n>>> Exécuter : {cmd}\n    (o = oui / n = non / t = oui à tout) : ").strip().lower()
        if choix == "t":
            for reste in commandes[commandes.index(cmd):]:
                print(f"--- {reste}")
                r = executer(reste)
                print(r)
                resultats.append(f"$ {reste}\n{r}")
            break
        if choix == "o":
            r = executer(cmd)
            print(r)
            resultats.append(f"$ {cmd}\n{r}")
        else:
            resultats.append(f"$ {cmd}\n[refusée par l'utilisateur]")
    return "Résultat des commandes :\n" + "\n\n".join(resultats)


# ---------- Boucle principale ----------

def main():
    historique = []
    print(f"Mon-IA activée ({MODELE}).")
    print("  /web <question>  recherche sur internet avec sources")
    print("  reset            efface la mémoire")
    print("  exit             quitte\n")
    while True:
        try:
            saisie = input("Vous: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not saisie:
            continue
        if saisie.lower() == "exit":
            break
        if saisie.lower() == "reset":
            historique.clear()
            print("Mémoire effacée.\n")
            continue

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
                print(f"\nErreur Ollama : {e}\n(Ollama est-il lancé ? 'ollama serve')")
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
        print()


if __name__ == "__main__":
    main()
