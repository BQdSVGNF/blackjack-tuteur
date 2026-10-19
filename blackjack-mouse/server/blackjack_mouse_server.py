#!/usr/bin/env python3
"""Serveur Blackjack Mouse : reçoit les commandes du téléphone et pilote la souris/clavier du PC.

Protocole (une commande par ligne, TCP) :
    AUTH <pin>            -> "OK" ou "NO"
    MOVE <dx> <dy>        déplacement relatif de la souris
    CLICK left|right|middle
    DOWN left | UP left   maintenir / relâcher (glisser-déposer)
    SCROLL <n>            molette (positif = haut)
    TYPE <texte>          texte encodé en URL (quote_plus)
    KEY <combo>           ex: enter, backspace, ctrl+c
"""
import argparse
import hmac
import random
import socket
import sys
import threading
from urllib.parse import unquote_plus

if sys.platform == "win32":
    # Sans ça, la souris dérive quand l'échelle d'affichage Windows est > 100 %
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

from pynput.keyboard import Controller as Keyboard
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as Mouse

mouse = Mouse()
keyboard = Keyboard()

BUTTONS = {"left": Button.left, "right": Button.right, "middle": Button.middle}
KEY_ALIASES = {
    "win": "cmd", "super": "cmd", "pageup": "page_up", "pagedown": "page_down",
    "return": "enter", "escape": "esc", "del": "delete",
}


def resolve_key(name):
    name = KEY_ALIASES.get(name.lower(), name.lower())
    key = getattr(Key, name, None)
    if key is not None:
        return key
    if len(name) == 1:
        return name
    raise ValueError(f"touche inconnue: {name}")


def press_combo(combo):
    keys = [resolve_key(part) for part in combo.split("+") if part]
    for k in keys:
        keyboard.press(k)
    for k in reversed(keys):
        keyboard.release(k)


def handle(line):
    cmd, _, arg = line.partition(" ")
    cmd = cmd.upper()
    if cmd == "MOVE":
        dx, dy = arg.split()
        mouse.move(int(dx), int(dy))
    elif cmd == "CLICK":
        mouse.click(BUTTONS[arg.strip()])
    elif cmd == "DOWN":
        mouse.press(BUTTONS[arg.strip()])
    elif cmd == "UP":
        mouse.release(BUTTONS[arg.strip()])
    elif cmd == "SCROLL":
        mouse.scroll(0, int(arg))
    elif cmd == "TYPE":
        keyboard.type(unquote_plus(arg))
    elif cmd == "KEY":
        press_combo(arg.strip())


def serve_client(conn, addr, pin):
    print(f"[+] Connexion de {addr[0]}")
    try:
        conn.settimeout(5)
        f = conn.makefile("r", encoding="utf-8", newline="\n")
        first = f.readline().strip()
        given = first[5:] if first.startswith("AUTH ") else ""
        if not hmac.compare_digest(given.encode(), pin.encode()):
            conn.sendall(b"NO\n")
            print(f"[!] PIN incorrect depuis {addr[0]}")
            return
        conn.sendall(b"OK\n")
        conn.settimeout(None)
        for line in f:
            line = line.rstrip("\r\n")
            if not line:
                continue
            try:
                handle(line)
            except Exception as e:  # une commande invalide ne coupe pas la session
                print(f"[!] Commande ignorée {line!r}: {e}")
    except OSError:
        pass
    finally:
        mouse.release(Button.left)  # évite un bouton resté bloqué
        conn.close()
        print(f"[-] Déconnexion de {addr[0]}")


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    p = argparse.ArgumentParser(description="Serveur Blackjack Mouse")
    p.add_argument("--port", type=int, default=5555)
    p.add_argument("--pin", default=None, help="PIN fixe (sinon un PIN aléatoire est généré)")
    args = p.parse_args()
    pin = args.pin or f"{random.randint(0, 9999):04d}"

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(2)

    print("♠ ♥  BLACKJACK MOUSE  ♦ ♣")
    print(f"  IP du PC : {local_ip()}")
    print(f"  Port     : {args.port}")
    print(f"  PIN      : {pin}")
    print("  (Ctrl+C pour arrêter)\n")

    try:
        while True:
            conn, addr = srv.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=serve_client, args=(conn, addr, pin), daemon=True).start()
    except KeyboardInterrupt:
        print("\nAu revoir !")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
