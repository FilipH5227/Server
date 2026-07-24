import asyncio
import json
import os
import sqlite3

# Suport opțional pentru PostgreSQL (Neon/Supabase)
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    try:
        import psycopg2
    except ImportError:
        psycopg2 = None

def get_db_connection():
    if DATABASE_URL and psycopg2:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        conn = sqlite3.connect("deskguard.db")
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    if DATABASE_URL and psycopg2:
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

init_db()

def register_user(username, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if DATABASE_URL and psycopg2:
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s);", (username, password))
        else:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?);", (username, password))
        conn.commit()
        conn.close()
        return True, "Account created successfully!"
    except Exception:
        return False, "Username already exists or database error."

def login_user(username, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if DATABASE_URL and psycopg2:
            cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s;", (username, password))
        else:
            cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?;", (username, password))
        user = cursor.fetchone()
        conn.close()
        if user:
            return True, "Login successful!"
        return False, "Invalid username or password."
    except Exception as e:
        return False, str(e)

CONNECTED_CLIENTS = {}
PIN_PAIRINGS = {}

async def handler(websocket):
    current_user = None
    role = None

    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "REGISTER":
                user = data.get("username", "").strip()
                pwd = data.get("password", "").strip()
                success, msg = register_user(user, pwd)
                await websocket.send(json.dumps({"type": "AUTH_RESPONSE", "success": success, "message": msg}))

            elif msg_type == "LOGIN":
                user = data.get("username", "").strip()
                pwd = data.get("password", "").strip()
                success, msg = login_user(user, pwd)
                if success:
                    current_user = user
                    role = data.get("role", "PC")
                    CONNECTED_CLIENTS[f"{user}_{role}"] = websocket
                await websocket.send(json.dumps({"type": "AUTH_RESPONSE", "success": success, "message": msg}))

            elif msg_type == "REGISTER_PIN":
                user = data.get("username", "").strip()
                pin = data.get("pin", "").strip()
                PIN_PAIRINGS[user] = pin

            elif msg_type == "PAIR_MOBILE":
                user = data.get("username", "").strip()
                pwd = data.get("password", "").strip()
                pin_entered = data.get("pin", "").strip()

                success, msg = login_user(user, pwd)
                if success:
                    current_user = user
                    role = "MOBILE"
                    CONNECTED_CLIENTS[f"{user}_MOBILE"] = websocket
                    
                    saved_pin = PIN_PAIRINGS.get(user)
                    if pin_entered == "AUTO" or pin_entered == saved_pin:
                        await websocket.send(json.dumps({"type": "PAIR_SUCCESS"}))
                        
                        pc_socket = CONNECTED_CLIENTS.get(f"{user}_PC")
                        if pc_socket:
                            await pc_socket.send(json.dumps({"type": "MOBILE_CONNECTED"}))
                    else:
                        await websocket.send(json.dumps({"type": "PAIR_FAILED", "message": "Incorrect PIN code."}))
                else:
                    await websocket.send(json.dumps({"type": "PAIR_FAILED", "message": msg}))

            elif msg_type == "stream":
                mobile_socket = CONNECTED_CLIENTS.get(f"{current_user}_MOBILE")
                if mobile_socket:
                    await mobile_socket.send(json.dumps(data))

            elif msg_type == "command":
                pc_socket = CONNECTED_CLIENTS.get(f"{current_user}_PC")
                if pc_socket:
                    await pc_socket.send(json.dumps(data))

            elif msg_type == "FORCE_UPDATE_UI":
                pc_socket = CONNECTED_CLIENTS.get(f"{current_user}_PC")
                if pc_socket:
                    await pc_socket.send(json.dumps({"type": "MOBILE_CONNECTED"}))

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
    asyncio.run(main())
