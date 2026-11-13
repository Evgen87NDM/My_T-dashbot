import sqlite3
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_file="bot_database.db"):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                user_name TEXT,
                tinkoff_token TEXT,
                selected_account TEXT,
                selected_brokers TEXT DEFAULT 'tinkoff',
                timezone TEXT DEFAULT 'Europe/Moscow',
                digest_time TEXT DEFAULT '09:00',
                digest_enabled INTEGER DEFAULT 1
            )
        """)
        self.conn.commit()
        logger.info("✅ База данных инициализирована")

    def get_user(self, telegram_id: int):
        self.cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'telegram_id': row[0],
                'user_name': row[1],
                'tinkoff_token': row[2],
                'selected_account': row[3],
                'selected_brokers': row[4],
                'timezone': row[5],
                'digest_time': row[6],
                'digest_enabled': row[7]
            }
        return None

    def save_user_data(self, telegram_id: int, **kwargs):
        user = self.get_user(telegram_id)
        if not user:
            self.cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,))

        allowed_fields = ['user_name', 'tinkoff_token', 'selected_account', 'selected_brokers', 'timezone', 'digest_time', 'digest_enabled']
        for key, value in kwargs.items():
            if key in allowed_fields:
                self.cursor.execute(f"UPDATE users SET {key} = ? WHERE telegram_id = ?", (value, telegram_id))
        self.conn.commit()

db = Database()
