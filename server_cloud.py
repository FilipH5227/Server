import asyncio
import json
import os
import random
import string
import logging
import websockets
from database import init_db, verify_or_register_user

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# In-memory active sessions
PC_SESSIONS = {}        # { username: { "ws": websocket, "pin": "6CHAR_PIN" } }
MOBILE_SESSIONS = {}    # { username: set(websocket) }

def generate_pin():
    """Generates a unique 6-character alphanumeric PIN code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def handle_pc_pairing(ws, data):
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    # Non-blocking DB verification
    auth_ok, msg = await asyncio.to_thread(verify_or_register_user, username, password)
    if not auth_ok:
        await ws.send(json.dumps({"type": "ERROR", "message": msg}))
        return None

    pin = generate_pin()
    PC_SESSIONS[username] = {
        "ws": ws,
        "pin": pin
    }

    logging.info(f"[PC CONNECTED] User: '{username}' | Assigned PIN: {pin}")

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

    auth_ok, msg = await asyncio.to_thread(verify_or_register_user, username, password)
    if not auth_ok:
        await ws.send(json.dumps({"type": "ERROR", "message": msg}))
        return None

    pc_session = PC_SESSIONS.get(username)
    if not pc_session:
        await ws.send(json.dumps({
            "type": "ERROR",
            "message": "PC Agent is not connected! Please start the PC Agent application first."
        }))
        return None

    if provided_pin != "AUTO" and provided_pin != pc_session["pin"]:
        await ws.send(json.dumps({
            "type": "ERROR",
            "message": "Incorrect PIN code!"
        }))
        return None

    if username not in MOBILE_SESSIONS:
        MOBILE_SESSIONS[username] = set()
    MOBILE_SESSIONS[username].add(ws)

    logging.info(f"[MOBILE CONNECTED] User: '{username}' connected successfully.")

    await ws.send(json.dumps({
        "type": "PAIR_SUCCESS",
        "message": "Successfully connected to PC Agent!"
    }))

    return username

async def router(ws, path=None):
    current_user = None
    client_type = None  # "PC" or "MOBILE"

    try:
        async for message in ws:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

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

            elif msg_type == "stream" and client_type == "PC" and current_user:
                mobiles = MOBILE_SESSIONS.get(current_user, set())
                if mobiles:
                    payload = json.dumps({
                        "type": "stream",
                        "image": data.get("image")
                    })
                    disconnected = set()
                    for mobile_ws in mobiles:
                        try:
                            await mobile_ws.send(payload)
                        except websockets.ConnectionClosed:
                            disconnected.add(mobile_ws)
                    MOBILE_SESSIONS[current_user] -= disconnected

            elif msg_type == "command" and client_type == "MOBILE" and current_user:
                pc_session = PC_SESSIONS.get(current_user)
                if pc_session and pc_session["ws"]:
                    try:
                        await pc_session["ws"].send(json.dumps({
                            "type": "command",
                            "action": data.get("action")
                        }))
                    except websockets.ConnectionClosed:
                        logging.warning(f"PC Session for '{current_user}' closed while sending command.")

    except websockets.ConnectionClosed:
        pass
    finally:
        if current_user:
            if client_type == "PC":
                if current_user in PC_SESSIONS and PC_SESSIONS[current_user]["ws"] == ws:
                    del PC_SESSIONS[current_user]
                    logging.info(f"[PC DISCONNECTED] User: '{current_user}'")
                    
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
    init_db()

    port = int(os.environ.get("PORT", 8765))
    logging.info(f"Starting DeskGuard Cloud Server on port {port}...")

    async with websockets.serve(
        router,
        "0.0.0.0",
        port,
        ping_interval=20,
        ping_timeout=20
    ):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())