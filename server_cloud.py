import asyncio
import json
import os
import sqlite3
import psycopg2

# Citim URL-ul bazei de date din cloud (dacă există)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    """Conectează la PostgreSQL în cloud dacă există, altfel la SQLite local."""
    if DATABASE_URL:
        # Folosește baza de date permanentă din cloud
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        # Fallback local SQLite
        conn = sqlite3.connect("deskguard.db")
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Creează tabelul de utilizatori dacă nu există."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            );
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );
        """)
        
    conn.commit()
    conn.close()

# Inițializăm baza de date
init_db()

def register_user(username, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if DATABASE_URL:
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s);", (username, password))
        else:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?);", (username, password))
            
        conn.commit()
        conn.close()
        return True, "Account created successfully!"
    except Exception as e:
        return False, "Username already exists or database error."

def login_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s;", (username, password))
    else:
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?;", (username, password))
        
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return True, "Login successful!"
    return False, "Invalid username or password."

# --- LOGICĂ WEBSOCKET SERVER ---
CONNECTED_CLIENTS = {}
PIN_PAIRINGS = {}

async def handler(websocket):
    current_user = None
    role = None

    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")

            # REGISTRARE
            if msg_type == "REGISTER":
                user = data.get("username", "").strip()
                pwd = data.get("password", "").strip()
                success, msg = register_user(user, pwd)
                await websocket.send(json.dumps({"type": "AUTH_RESPONSE", "success": success, "message": msg}))

            # LOGIN
            elif msg_type == "LOGIN":
                user = data.get("username", "").strip()
                pwd = data.get("password", "").strip()
                success, msg = login_user(user, pwd)
                if success:
                    current_user = user
                    role = data.get("role")
                    CONNECTED_CLIENTS[f"{user}_{role}"] = websocket
                await websocket.send(json.dumps({"type": "AUTH_RESPONSE", "success": success, "message": msg}))

            # PAIRING PIN & STREAMING
            elif msg_type == "PAIR_MOBILE":
                user = data.get("username", "").strip()
                pwd = data.get("password", "").strip()
                success, msg = login_user(user, pwd)
                if success:
                    CONNECTED_CLIENTS[f"{user}_MOBILE"] = websocket
                    # Trimite confirmare conexiune mobil
                    pc_socket = CONNECTED_CLIENTS.get(f"{user}_PC")
                    if pc_socket:
                        await pc_socket.send(json.dumps({"type": "MOBILE_CONNECTED"}))
                    await websocket.send(json.dumps({"type": "PAIR_SUCCESS"}))
                else:
                    await websocket.send(json.dumps({"type": "PAIR_FAILED", "message": msg}))

            elif msg_type == "stream":
                # Redirecționează stream-ul de la PC la Mobile
                mobile_socket = CONNECTED_CLIENTS.get(f"{current_user}_MOBILE")
                if mobile_socket:
                    await mobile_socket.send(json.dumps(data))

            elif msg_type == "command":
                # Trimite comanda de la Mobile la PC
                pc_socket = CONNECTED_CLIENTS.get(f"{current_user}_PC")
                if pc_socket:
                    await pc_socket.send(json.dumps(data))

    except Exception:
        pass
    finally:
        if current_user and role:
            CONNECTED_CLIENTS.pop(f"{current_user}_{role}", None)

async def main():
    port = int(os.environ.get("PORT", 10000))
    async with websockets.serve(handler, "0.0.0.0", port):
        await asyncio.Future()

if __name__ == "__main__":
    import websockets
    asyncio.run(main())
