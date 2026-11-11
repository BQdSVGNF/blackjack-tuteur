# ♞ Échecs

Jeu d'échecs complet dans le navigateur : contre un bot (Stockfish 17.1, jusqu'à 3200+ Elo) ou à deux sur le même écran.

## Lancer

```bash
cd echecs
python3 -m http.server 8000
```

Puis ouvrir <http://localhost:8000>. Un serveur web est nécessaire (le moteur ne se charge pas depuis `file://`).
Le dossier est 100 % statique : il peut aussi être publié tel quel sur GitHub Pages.

## Fonctions

- 9 bots : de 1350 à 3190 Elo (Stockfish bridé via `UCI_Elo`), puis 3 bots à pleine puissance (1 s, 3 s, 8 s par coup).
- Mode deux joueurs, avec retournement automatique de l'échiquier en option.
- Toutes les règles : roque, prise en passant, promotion, pat, triple répétition, 50 coups, matériel insuffisant.
- Glisser-déposer ou clic, coups légaux affichés, pendule avec incrément, annulation, indice, relecture des coups (← →), export PGN, sons.

Les Elo au-delà de 3190 sont des estimations : ils dépendent de la puissance de l'appareil.

## Crédits

- Moteur : [Stockfish 17.1](https://github.com/nmrugg/stockfish.js) (GPLv3, voir `vendor/stockfish/Copying.txt`)
- Règles : [chess.js](https://github.com/jhlywa/chess.js) (BSD-2-Clause)
- Pièces : Colin M.L. Burnett (GPLv2+ / BSD / GFDL)
