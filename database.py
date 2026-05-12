import sqlite3
import threading

class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.lock = threading.Lock()
        self.create_tables()

    def create_tables(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    balance REAL DEFAULT 0.0,
                    referred_by INTEGER,
                    referral_count INTEGER DEFAULT 0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY,
                    channel_username TEXT UNIQUE
                )
            ''')
            self.conn.commit()
        
        # Initialize default referral reward to $1.0 if not exists
        if not self.get_setting('referral_reward'):
            self.set_setting('referral_reward', '1.0')

    def user_exists(self, user_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
            return bool(cursor.fetchone())

    def add_user(self, user_id, first_name, referred_by=None):
        if not self.user_exists(user_id):
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO users (id, first_name, referred_by) VALUES (?, ?, ?)", 
                                    (user_id, first_name, referred_by))
                self.conn.commit()
            return True
        return False

    def get_user(self, user_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'first_name': row[1],
                    'balance': row[2],
                    'referred_by': row[3],
                    'referral_count': row[4]
                }
            return None

    def add_balance(self, user_id, amount):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
            self.conn.commit()

    def increment_referral_count(self, user_id):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE id = ?", (user_id,))
            self.conn.commit()

    def get_setting(self, key):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

    def set_setting(self, key, value):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            self.conn.commit()

    def get_total_users(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]

    def get_total_balance(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT SUM(balance) FROM users")
            return cursor.fetchone()[0] or 0.0

    def add_channel(self, channel_username):
        with self.lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute("INSERT INTO channels (channel_username) VALUES (?)", (channel_username,))
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_channel(self, channel_username):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM channels WHERE channel_username = ?", (channel_username,))
            self.conn.commit()
            return cursor.rowcount > 0

    def get_all_channels(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT channel_username FROM channels")
            return [row[0] for row in cursor.fetchall()]

