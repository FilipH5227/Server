import sqlite3
import hashlib
import os
import logging

DB_FILE = "deskguard.db"

def init_db():
    """Creează tabela de utilizatori dacă nu există deja."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Baza de date SQLite a fost inițializată cu succes.")

def _hash_password(password: str, salt: str) -> str:
    """Generează hash securizat PBKDF2 pentru parolă."""
    return hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt.encode('utf-8'), 
        100000
    ).hex()

def verify_or_register_user(username: str, password: str) -> tuple[bool, str]:
    """
    Verifică utilizatorul. Dacă nu există, îl înregistrează automat.
    Returnează (Success: bool, Message: str)
    """
    username = username.strip()
    password = password.strip()

    if not username or not password:
        return False, "Numele de utilizator și parola sunt obligatorii."

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user is None:
            # Înregistrare utilizator nou
            salt = os.urandom(16).hex()
            p_hash = _hash_password(password, salt)
            cursor.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, p_hash, salt)
            )
            conn.commit()
            logging.info(f"[DB] Cont nou înregistrat: '{username}'")
            return True, "Cont nou creat cu succes!"
        else:
            # Verificare parolă pentru utilizator existent
            db_hash, salt = user
            input_hash = _hash_password(password, salt)
            if input_hash == db_hash:
                return True, "Autentificare reușită!"
            else:
                return False, "Parolă incorectă!"
    except Exception as e:
        logging.error(f"[DB ERROR] {e}")
        return False, "A apărut o eroare la accesarea bazei de date."
    finally:
        conn.close()
