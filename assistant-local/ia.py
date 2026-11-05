"""Assistant IA local (Ollama) qui peut exécuter des commandes Windows.

L'IA propose des commandes dans un bloc ```cmd ... ```.
Chaque commande est affichée et exécutée après ta confirmation (o/n),
puis le résultat est renvoyé à l'IA pour qu'elle continue.
"""
import re
import subprocess
import sys

try:
    import ollama
except ImportError:
    print("Le module 'ollama' manque. Lance : pip install ollama")
    sys.exit(1)

MODELE = "llama3"
MAX_MESSAGES = 30

SYSTEME = {
    "role": "system",
    "content": (
        "Tu es un assistant direct et efficace qui tourne sur un PC Windows. "
        "Tu réponds en français, sans détour. Quand l'utilisateur demande une action "
        "sur son ordinateur (fichiers, dossiers, programmes, infos système), tu fournis "
        "la ou les commandes Windows cmd nécessaires dans UN bloc :\n"
        "```cmd\n<commandes>\n```\n"
        "Une commande par ligne. Après exécution, tu recevras la sortie et tu pourras "
        "continuer ou corriger. Si aucune commande n'est utile, réponds simplement."
    ),
}

BLOC_CMD = re.compile(r"```(?:cmd|bat|batch|powershell)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def demander_ia(historique):
    messages = [SYSTEME] + historique[-MAX_MESSAGES:]
    reponse = ""
    print("IA: ", end="", flush=True)
    for morceau in ollama.chat(model=MODELE, messages=messages, stream=True):
        texte = morceau["message"]["content"]
        print(texte, end="", flush=True)
        reponse += texte
    print()
    return reponse


def executer(commande):
    try:
        res = subprocess.run(commande, shell=True, capture_output=True, text=True,
                             timeout=120, encoding="cp850", errors="replace")
        sortie = (res.stdout or "") + (res.stderr or "")
        return f"[code {res.returncode}]\n{sortie.strip()[:4000]}"
    except subprocess.TimeoutExpired:
        return "[erreur] commande trop longue (plus de 120 s), arrêtée."


def main():
    historique = []
    print(f"IA activée ({MODELE}). Tape 'exit' pour quitter, 'reset' pour effacer la mémoire.\n")
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

        historique.append({"role": "user", "content": saisie})

        # Boucle : l'IA peut enchaîner plusieurs commandes à la suite
        for _ in range(5):
            try:
                reponse = demander_ia(historique)
            except Exception as e:
                print(f"\nErreur Ollama : {e}\n(Ollama est-il lancé ? 'ollama serve')")
                historique.pop()
                break
            historique.append({"role": "assistant", "content": reponse})

            blocs = BLOC_CMD.findall(reponse)
            commandes = [l.strip() for b in blocs for l in b.splitlines() if l.strip()]
            if not commandes:
                break

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

            historique.append({"role": "user",
                               "content": "Résultat des commandes :\n" + "\n\n".join(resultats)})
        print()


if __name__ == "__main__":
    main()
