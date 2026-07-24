import asyncio
import json
import os
import random
import string
import logging
import websockets

# Configurare Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# Structuri de date în memorie
# USERS: { username: password }
USERS = {}

# PC_SESSIONS: { username: { "ws": websocket, "pin": "6CHAR_PIN" } }
PC_SESSIONS = {}

# MOBILE_SESSIONS: { username: set(websocket) }
MOBILE_SESSIONS = {}

def generate_pin():
    """Generează un cod PIN unic din 6 caractere alfanumerice (litere mari și cifre)."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def authenticate_user(username, password):
    """
    Verifică datele de autentificare.
    Dacă utilizatorul nu există, îl înregistrează automat la prima conectare.
    """
    if not username or not password:
        return False, "Numele de utilizator și parola nu pot fi goale."

    if username not in USERS:
        USERS[username] = password
        logging.info(f"Cont nou creat automat pentru utilizatorul: {username}")
        return True, "Cont creat cu succes."
    
    if USERS[username] == password:
        return True, "Autentificare reușită."
    else:
        return False, "Parolă incorectă."

async def handle_pc_pairing(ws, data):
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    auth_ok, msg = await authenticate_user(username, password)
    if not auth_ok:
        await ws.send(json.dumps({"type": "ERROR", "message": msg}))
        return None

    # Generează PIN pentru sesiunea PC
    pin = generate_pin()
    PC_SESSIONS[username] = {
        "ws": ws,
        "pin": pin
    }

    logging.info(f"[PC CONNECTED] User: '{username}' | PIN alocat: {pin}")

    # Trimite PIN-ul generat către PC
    await ws.send(json.dumps({
        "type": "PAIR_PIN",
        "pin": pin,
        "status": "ONLINE"
    }))

    return username

async def handle_mobile_pairing(ws, data):
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    provided_pin = data.get("pin", "").strip().upper()

    auth_ok, msg = await authenticate_user(username, password)
    if not auth_ok:
        await ws.send(json.dumps({"type": "ERROR", "message": msg}))
        return None

    # Verifica daca exista o sesiune PC activa pentru acest user
    pc_session = PC_SESSIONS.get(username)
    if not pc_session:
        await ws.send(json.dumps({
            "type": "ERROR",
            "message": "PC-ul tău nu este conectat! Pornește aplicația PC Agent mai întâi."
        }))
        return None

    # Verificare PIN (sau reconectare AUTO)
    if provided_pin != "AUTO" and provided_pin != pc_session["pin"]:
        await ws.send(json.dumps({
            "type": "ERROR",
            "message": "Codul PIN este incorect!"
        }))
        return None

    # Adaugă mobilul în sesiunile active
    if username not in MOBILE_SESSIONS:
        MOBILE_SESSIONS[username] = set()
    MOBILE_SESSIONS[username].add(ws)

    logging.info(f"[MOBILE CONNECTED] User: '{username}' s-a conectat cu succes!")

    # Confirmare conectare către mobil
    await ws.send(json.dumps({
        "type": "PAIR_SUCCESS",
        "message": "Conectat cu succes la PC!"
    }))

    return username

async def router(ws, path=None):
    current_user = None
    client_type = None  # "PC" sau "MOBILE"

    try:
        async for message in ws:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            # 1. AUTENTIFICARE & CONECTARE INITIALĂ
            if msg_type == "PAIR_PC":
                client_type = "PC"
                current_user = await handle_pc_pairing(ws, data)
                if not current_user:
                    break

            elif msg_type == "PAIR_MOBILE":
                client_type = "MOBILE"
                current_user = await handle_mobile_pairing(ws, data)
                if not current_user:
                    break

            # 2. RELAY FLUX VIDEO (De la PC către Mobil)
            elif msg_type == "stream" and client_type == "PC" and current_user:
                mobiles = MOBILE_SESSIONS.get(current_user, set())
                if mobiles:
                    payload = json.dumps({
                        "type": "stream",
                        "image": data.get("image")
                    })
                    # Trimite cadrul la toate dispozitivele mobile conectate ale utilizatorului
                    disconnected = set()
                    for mobile_ws in mobiles:
                        try:
                            await mobile_ws.send(payload)
                        except websockets.ConnectionClosed:
                            disconnected.add(mobile_ws)
                    
                    # Curățare conexiuni închise
                    MOBILE_SESSIONS[current_user] -= disconnected

            # 3. RELAY COMENZI (De la Mobil către PC)
            elif msg_type == "command" and client_type == "MOBILE" and current_user:
                pc_session = PC_SESSIONS.get(current_user)
                if pc_session and pc_session["ws"]:
                    try:
                        await pc_session["ws"].send(json.dumps({
                            "type": "command",
                            "action": data.get("action")
                        }))
                    except websockets.ConnectionClosed:
                        logging.warning(f"Sesiunea PC pentru {current_user} s-a închis la trimiterea comenzii.")

    except websockets.ConnectionClosed:
        pass
    finally:
        # Curățare conexiuni la deconectare
        if current_user:
            if client_type == "PC":
                if current_user in PC_SESSIONS and PC_SESSIONS[current_user]["ws"] == ws:
                    del PC_SESSIONS[current_user]
                    logging.info(f"[PC DISCONNECTED] User: '{current_user}'")
                    
                    # Anunță mobilele că PC-ul a trecut offline
                    mobiles = MOBILE_SESSIONS.get(current_user, set())
                    for mobile_ws in list(mobiles):
                        try:
                            await mobile_ws.send(json.dumps({"type": "STATUS", "status": "OFFLINE"}))
                        except Exception:
                            pass

            elif client_type == "MOBILE":
                if current_user in MOBILE_SESSIONS:
                    MOBILE_SESSIONS[current_user].discard(ws)
                    logging.info(f"[MOBILE DISCONNECTED] User: '{current_user}'")

async def main():
    # Render sau alte servicii de hosting furnizează portul prin variabila PORT
    port = int(os.environ.get("PORT", 8765))
    logging.info(f"Pornire Server DeskGuard Cloud pe portul {port}...")

    async with websockets.serve(
        router,
        "0.0.0.0",
        port,
        ping_interval=20,  # Trimite ping la fiecare 20 secunde pentru menținere conexiune
        ping_timeout=20
    ):
        await asyncio.Future()  # Menține serverul pornit nedefinit

if __name__ == "__main__":
    asyncio.run(main())