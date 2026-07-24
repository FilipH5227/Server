import sqlite3
import hashlib
import os
import logging

DB_FILE = "deskguard.db"

def init_db():
    """Creates the users table if it does not already exist."""
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
    logging.info("SQLite database initialized successfully.")

def _hash_password(password: str, salt: str) -> str:
    """Generates a secure PBKDF2 hash for a password."""
    return hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt.encode('utf-8'), 
        100000
    ).hex()

def verify_or_register_user(username: str, password: str) -> tuple[bool, str]:
    """
    Verifies user credentials. Automatically registers the user if they don't exist.
    Returns (Success: bool, Message: str)
    """
    username = username.strip()
    password = password.strip()

    if not username or not password:
        return False, "Username and password are required."

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user is None:
            # Register new user
            salt = os.urandom(16).hex()
            p_hash = _hash_password(password, salt)
            cursor.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, p_hash, salt)
            )
            conn.commit()
            logging.info(f"[DB] New account created: '{username}'")
            return True, "New account created successfully!"
        else:
            # Verify password for existing user
            db_hash, salt = user
            input_hash = _hash_password(password, salt)
            if input_hash == db_hash:
                return True, "Authentication successful!"
            else:
                return False, "Incorrect password!"
    except Exception as e:
        logging.error(f"[DB ERROR] {e}")
        return False, "An error occurred while accessing the database."
    finally:
        conn.close()