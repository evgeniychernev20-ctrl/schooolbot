import sqlite3
import threading
import json
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_name='schedule.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.lock = threading.Lock()
        self.create_tables()
    
    def create_tables(self):
        with self.lock:
            # Группа, куда бот отправляет уведомления
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS target_group (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE NOT NULL,
                    chat_title TEXT,
                    invite_link TEXT,
                    is_active INTEGER DEFAULT 1
                )
            ''')
            
            # Администраторы (кто может управлять из ЛС)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    can_manage INTEGER DEFAULT 1,
                    added_by INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Домашние задания
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS homework (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson TEXT NOT NULL,
                    task TEXT NOT NULL,
                    deadline DATE,
                    added_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Замены
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS substitutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    lesson_number INTEGER,
                    lesson TEXT NOT NULL,
                    teacher TEXT,
                    room TEXT,
                    comment TEXT,
                    added_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Экзамены
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS exams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson TEXT NOT NULL,
                    date DATE NOT NULL,
                    time TEXT,
                    room TEXT,
                    description TEXT,
                    added_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Предложения от участников (если добавишь позже)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    type TEXT,
                    data TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.conn.commit()
    
    # ===== НАСТРОЙКА ГРУППЫ =====
    
    def set_target_group(self, chat_id, chat_title):
        """Устанавливает группу для отправки уведомлений"""
        with self.lock:
            self.cursor.execute('''
                INSERT OR REPLACE INTO target_group (chat_id, chat_title)
                VALUES (?, ?)
            ''', (chat_id, chat_title))
            self.conn.commit()
    
    def get_target_group(self):
        """Получает целевую группу"""
        with self.lock:
            self.cursor.execute('SELECT chat_id, chat_title FROM target_group WHERE is_active = 1')
            row = self.cursor.fetchone()
            return dict(row) if row else None
    
    # ===== АДМИНИСТРАТОРЫ =====
    
    def add_admin(self, user_id, username, first_name, added_by):
        """Добавляет администратора"""
        with self.lock:
            self.cursor.execute('''
                INSERT OR REPLACE INTO admins (user_id, username, first_name, added_by)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, added_by))
            self.conn.commit()
    
    def is_admin(self, user_id):
        """Проверяет, является ли пользователь админом"""
        with self.lock:
            self.cursor.execute('SELECT 1 FROM admins WHERE user_id = ? AND can_manage = 1', (user_id,))
            return self.cursor.fetchone() is not None
    
    def get_admins(self):
        """Список всех админов"""
        with self.lock:
            self.cursor.execute('SELECT user_id, username, first_name FROM admins WHERE can_manage = 1')
            return [dict(row) for row in self.cursor.fetchall()]
    
    def remove_admin(self, user_id):
        """Удаляет администратора"""
        with self.lock:
            self.cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            self.conn.commit()
    
    # ===== ДОМАШНИЕ ЗАДАНИЯ =====
    
    def add_homework(self, lesson, task, deadline, added_by):
        with self.lock:
            self.cursor.execute('''
                INSERT INTO homework (lesson, task, deadline, added_by)
                VALUES (?, ?, ?, ?)
            ''', (lesson, task, deadline, added_by))
            self.conn.commit()
            return self.cursor.lastrowid
    
    def get_homework(self, days=14):
        with self.lock:
            today = datetime.now().date()
            future = today + timedelta(days=days)
            self.cursor.execute('''
                SELECT id, lesson, task, deadline, created_at
                FROM homework
                WHERE deadline IS NULL OR deadline <= ?
                ORDER BY deadline, lesson
            ''', (future.isoformat(),))
            return [dict(row) for row in self.cursor.fetchall()]
    
    def delete_homework(self, hw_id):
        with self.lock:
            self.cursor.execute('DELETE FROM homework WHERE id = ?', (hw_id,))
            self.conn.commit()
    
    # ===== ЗАМЕНЫ =====
    
    def add_substitution(self, date, lesson_number, lesson, teacher, room, comment, added_by):
        with self.lock:
            self.cursor.execute('''
                INSERT INTO substitutions (date, lesson_number, lesson, teacher, room, comment, added_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (date, lesson_number, lesson, teacher, room, comment, added_by))
            self.conn.commit()
            return self.cursor.lastrowid
    
    def get_substitutions(self, date=None):
        with self.lock:
            if date:
                self.cursor.execute('''
                    SELECT lesson_number, lesson, teacher, room, comment
                    FROM substitutions
                    WHERE date = ?
                    ORDER BY lesson_number
                ''', (date,))
            else:
                today = datetime.now().strftime("%Y-%m-%d")
                self.cursor.execute('''
                    SELECT date, lesson_number, lesson, teacher, room, comment
                    FROM substitutions
                    WHERE date >= ?
                    ORDER BY date, lesson_number
                ''', (today,))
            return [dict(row) for row in self.cursor.fetchall()]
    
    # ===== ЭКЗАМЕНЫ =====
    
    def add_exam(self, lesson, date, time, room, description, added_by):
        with self.lock:
            self.cursor.execute('''
                INSERT INTO exams (lesson, date, time, room, description, added_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (lesson, date, time, room, description, added_by))
            self.conn.commit()
            return self.cursor.lastrowid
    
    def get_exams(self):
        with self.lock:
            today = datetime.now().strftime("%Y-%m-%d")
            self.cursor.execute('''
                SELECT lesson, date, time, room, description
                FROM exams
                WHERE date >= ?
                ORDER BY date
            ''', (today,))
            return [dict(row) for row in self.cursor.fetchall()]
