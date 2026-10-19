# ♠ Blackjack Mouse ♥

Utilise ton téléphone Android comme **souris** et **clavier** pour ton PC, sur le même Wi-Fi, dans un thème table de Blackjack.

```
blackjack-mouse/
├── server/    → serveur Python à lancer sur le PC
└── android/   → projet Android Studio (l'appli du téléphone)
```

## 1. Sur le PC (Windows) : lancer le serveur

1. Installe [Python](https://www.python.org/downloads/) si besoin (coche **« Add python.exe to PATH »**).
2. Ouvre PowerShell dans le dossier `blackjack-mouse\server` et lance :

```powershell
pip install -r requirements.txt
python blackjack_mouse_server.py
```

Il affiche **l'IP du PC**, le **port** (5555) et un **PIN** à 4 chiffres (change à chaque lancement ; `--pin 1234` pour en fixer un).

- À la première exécution, Windows demande l'autorisation du pare-feu : coche **Réseaux privés** puis *Autoriser*.
- Le PC et le téléphone doivent être sur le **même Wi-Fi**. Si ton IP n'est pas la bonne, vérifie avec `ipconfig` (« Adresse IPv4 »).
- La touche **Win** de l'appli ouvre le menu Démarrer ; les fenêtres lancées en administrateur ne reçoivent pas les clics/touches sauf si tu lances aussi le serveur en administrateur.
- (macOS : autorise le Terminal dans Accessibilité. Linux : X11 uniquement.)

## 2. Sur le téléphone : installer l'appli avec Android Studio

1. Android Studio → **Open** → choisis le dossier `blackjack-mouse/android` et laisse la synchronisation Gradle finir.
2. Active le **débogage USB** sur le téléphone (Options développeur), branche-le en USB.
3. Sélectionne ton téléphone en haut et clique sur ▶ **Run**. L'appli « Blackjack Mouse » est installée.
4. Dans l'appli, entre l'IP, le port et le PIN du PC → **Jouer ♠**.

Pour avoir un APK à installer sans câble : *Build → Build Bundle(s) / APK(s) → Build APK(s)*.

## Utilisation

**♠ Souris**
- Glisser 1 doigt : déplacer le curseur
- Tap : clic gauche · tap 2 doigts : clic droit
- Glisser 2 doigts : défiler
- Cartes **A♠** (clic gauche), **K♥** (clic droit), **J♦** (maintenir pour glisser-déposer)
- Curseur « Vitesse » pour régler la sensibilité

**♥ Clavier**
- Tape dans le champ : les caractères sont envoyés en direct au PC (retour arrière compris, ✔ accents)
- Touches spéciales (Entrée, flèches, Échap, Win…) et raccourcis (Ctrl+C/V/Z…)

## Sécurité

Le trafic n'est pas chiffré : à n'utiliser que sur un Wi-Fi de confiance. Le PIN empêche les autres appareils du réseau de prendre le contrôle du PC.
