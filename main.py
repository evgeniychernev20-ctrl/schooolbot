import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, ForceReply
)

from database import Database

load_dotenv()

app = Client(
    "schedule_bot",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("BOT_TOKEN")
)

db = Database()

# ID главного админа (твой Telegram ID)
MAIN_ADMIN_ID = 123456789  # ЗАМЕНИ НА СВОЙ ID

# ===== ПРОВЕРКА ПРАВ =====

async def is_admin(user_id):
    """Проверяет, может ли пользователь управлять ботом"""
    if user_id == MAIN_ADMIN_ID:
        return True
    return db.is_admin(user_id)

# ===== ГЛАВНОЕ МЕНЮ В ЛС =====

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Проверяем, может ли пользователь управлять
    if not await is_admin(user_id):
        await message.reply_text(
            "❌ У вас нет доступа к управлению ботом.\n"
            "Это приватный бот для администраторов."
        )
        return
    
    # Меню для админа
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Добавить ДЗ", callback_data="add_homework")],
        [InlineKeyboardButton("🔄 Добавить замену", callback_data="add_substitution")],
        [InlineKeyboardButton("📅 Добавить экзамен", callback_data="add_exam")],
        [InlineKeyboardButton("📋 Просмотреть всё", callback_data="view_all")],
        [InlineKeyboardButton("⚙️ Настройки группы", callback_data="settings")]
    ])
    
    # Проверяем, настроена ли целевая группа
    group = db.get_target_group()
    group_status = f"✅ Группа: {group['chat_title']}" if group else "❌ Группа не настроена"
    
    await message.reply_text(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"{group_status}\n\n"
        "Я буду отправлять информацию в группу от твоего имени.\n"
        "Выбери действие:",
        reply_markup=keyboard
    )

# ===== НАСТРОЙКА ГРУППЫ =====

@app.on_message(filters.command("setgroup") & filters.private)
async def set_group_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await is_admin(user_id):
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "❌ Использование:\n"
            "`/setgroup @username_группы`\n\n"
            "Или перешли любое сообщение из группы, и я сам пойму ID."
        )
        return
    
    group_identifier = parts[1].strip()
    
    try:
        # Пытаемся получить информацию о группе
        chat = await client.get_chat(group_identifier)
        
        # Сохраняем группу
        db.set_target_group(chat.id, chat.title)
        
        # Отправляем тестовое сообщение в группу
        await client.send_message(
            chat.id,
            f"✅ Бот настроен!\n"
            f"Теперь уведомления будут приходить сюда.\n"
            f"Администратор: {message.from_user.mention}"
        )
        
        await message.reply_text(f"✅ Группа **{chat.title}** успешно настроена!")
        
    except Exception as e:
        await message.reply_text(f"❌ Ошибка: {e}\n\nУбедись, что бот добавлен в группу!")

# ===== ДОБАВЛЕНИЕ ДЗ (через диалог) =====

@app.on_callback_query(filters.regex("^add_homework$"))
async def add_homework_callback(client: Client, callback_query: CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нет доступа")
        return
    
    await callback_query.message.reply_text(
        "📝 **Добавление домашнего задания**\n\n"
        "Отправь сообщение в формате:\n"
        "`Предмет | Задание | ГГГГ-ММ-ДД`\n\n"
        "Пример:\n"
        "`Математика | Решить задачи 1-10 | 2026-03-20`\n\n"
        "Дедлайн можно не указывать.",
        reply_markup=ForceReply(selective=True)
    )
    
    # Сохраняем состояние (ждем ответ)
    # В Pyrogram можно использовать filters.reply
    await callback_query.answer()

@app.on_message(filters.private & filters.reply & filters.text)
async def handle_homework_input(client: Client, message: Message):
    if not await is_admin(message.from_user.id):
        return
    
    # Проверяем, что отвечают на наше сообщение
    if not message.reply_to_message or "Добавление домашнего задания" not in message.reply_to_message.text:
        return
    
    text = message.text.strip()
    parts = [p.strip() for p in text.split("|")]
    
    if len(parts) < 2:
        await message.reply_text("❌ Неверный формат. Используй: `Предмет | Задание | Дата`")
        return
    
    lesson = parts[0]
    task = parts[1]
    deadline = parts[2] if len(parts) > 2 else None
    
    # Сохраняем в БД
    hw_id = db.add_homework(lesson, task, deadline, message.from_user.id)
    
    # Отправляем в группу
    group = db.get_target_group()
    if group:
        deadline_text = f" (до {deadline})" if deadline else ""
        
        await client.send_message(
            group['chat_id'],
            f"📚 **Новое домашнее задание!**\n\n"
            f"**Предмет:** {lesson}\n"
            f"**Задание:** {task}{deadline_text}\n"
            f"👤 Добавил: {message.from_user.first_name}"
        )
        
        await message.reply_text("✅ ДЗ добавлено и отправлено в группу!")
    else:
        await message.reply_text("✅ ДЗ сохранено, но группа не настроена. Используй /setgroup")

# ===== ДОБАВЛЕНИЕ ЗАМЕНЫ =====

@app.on_callback_query(filters.regex("^add_substitution$"))
async def add_substitution_callback(client: Client, callback_query: CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        return
    
    await callback_query.message.reply_text(
        "🔄 **Добавление замены**\n\n"
        "Отправь сообщение в формате:\n"
        "`Дата | Номер пары | Предмет | Преподаватель | Кабинет | Комментарий`\n\n"
        "Пример:\n"
        "`2026-03-10 | 3 | Физкультура | Петров | Спортзал | Вместо математики`\n\n"
        "Преподаватель, кабинет и комментарий можно не указывать.",
        reply_markup=ForceReply(selective=True)
    )
    
    await callback_query.answer()

@app.on_message(filters.private & filters.reply & filters.text)
async def handle_substitution_input(client: Client, message: Message):
    if not await is_admin(message.from_user.id):
        return
    
    if not message.reply_to_message or "Добавление замены" not in message.reply_to_message.text:
        return
    
    text = message.text.strip()
    parts = [p.strip() for p in text.split("|")]
    
    if len(parts) < 3:
        await message.reply_text("❌ Неверный формат. Нужно минимум: Дата | Номер пары | Предмет")
        return
    
    date = parts[0]
    lesson_num = int(parts[1])
    lesson = parts[2]
    teacher = parts[3] if len(parts) > 3 else ""
    room = parts[4] if len(parts) > 4 else ""
    comment = parts[5] if len(parts) > 5 else ""
    
    # Сохраняем в БД
    sub_id = db.add_substitution(date, lesson_num, lesson, teacher, room, comment, message.from_user.id)
    
    # Отправляем в группу
    group = db.get_target_group()
    if group:
        date_formatted = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")
        teacher_text = f", {teacher}" if teacher else ""
        room_text = f", каб. {room}" if room else ""
        comment_text = f"\n💬 {comment}" if comment else ""
        
        await client.send_message(
            group['chat_id'],
            f"🔄 **Замена на {date_formatted}!**\n\n"
            f"**{lesson_num}-я пара:** {lesson}{teacher_text}{room_text}{comment_text}\n"
            f"👤 Добавил: {message.from_user.first_name}"
        )
        
        await message.reply_text("✅ Замена добавлена и отправлена в группу!")
    else:
        await message.reply_text("✅ Замена сохранена")

# ===== ПРОСМОТР ВСЕГО =====

@app.on_callback_query(filters.regex("^view_all$"))
async def view_all_callback(client: Client, callback_query: CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Домашние задания", callback_data="view_homework")],
        [InlineKeyboardButton("🔄 Замены на сегодня", callback_data="view_today_subs")],
        [InlineKeyboardButton("📅 Экзамены", callback_data="view_exams")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ])
    
    await callback_query.message.edit_text(
        "📋 **Просмотр информации**\n\nВыбери, что хочешь посмотреть:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^view_homework$"))
async def view_homework_callback(client: Client, callback_query: CallbackQuery):
    homework = db.get_homework(days=14)
    
    if not homework:
        await callback_query.message.edit_text(
            "📭 Нет домашних заданий на ближайшие дни.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="view_all")
            ]])
        )
        return
    
    text = "📚 **Домашние задания:**\n\n"
    for hw in homework:
        deadline = f" (до {hw['deadline']})" if hw['deadline'] else ""
        text += f"• **{hw['lesson']}**{deadline}:\n  {hw['task']}\n\n"
    
    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="view_all")
        ]])
    )

@app.on_callback_query(filters.regex("^view_today_subs$"))
async def view_today_subs_callback(client: Client, callback_query: CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    subs = db.get_substitutions(today)
    
    if not subs:
        await callback_query.message.edit_text(
            "✅ На сегодня замен нет.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="view_all")
            ]])
        )
        return
    
    text = f"🔄 **Замены на {datetime.now().strftime('%d.%m.%Y')}:**\n\n"
    for sub in subs:
        teacher = f", {sub['teacher']}" if sub['teacher'] else ""
        room = f", каб. {sub['room']}" if sub['room'] else ""
        comment = f"\n  💬 {sub['comment']}" if sub['comment'] else ""
        text += f"**{sub['lesson_number']}-я пара:** {sub['lesson']}{teacher}{room}{comment}\n\n"
    
    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="view_all")
        ]])
    )

# ===== ДОБАВЛЕНИЕ АДМИНОВ =====

@app.on_message(filters.command("addadmin") & filters.private)
async def add_admin_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Только главный админ может добавлять других
    if user_id != MAIN_ADMIN_ID:
        await message.reply_text("❌ Только главный администратор может добавлять админов.")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(
            "❌ Использование: `/addadmin USER_ID`\n\n"
            "Чтобы узнать ID пользователя, используй @userinfobot"
        )
        return
    
    try:
        new_admin_id = int(parts[1])
        
        # Пробуем получить информацию о пользователе
        try:
            user = await client.get_users(new_admin_id)
            username = user.username or ""
            first_name = user.first_name or ""
        except:
            username = "unknown"
            first_name = "unknown"
        
        db.add_admin(new_admin_id, username, first_name, user_id)
        
        await message.reply_text(f"✅ Пользователь {new_admin_id} добавлен как администратор!")
        
        # Уведомляем нового админа
        try:
            await client.send_message(
                new_admin_id,
                "🎉 Вас назначили администратором бота-расписания!\n"
                "Напишите /start для начала работы."
            )
        except:
            pass
            
    except ValueError:
        await message.reply_text("❌ Неверный ID. ID должен быть числом.")

@app.on_message(filters.command("admins") & filters.private)
async def list_admins_command(client: Client, message: Message):
    if not await is_admin(message.from_user.id):
        return
    
    admins = db.get_admins()
    
    if not admins:
        await message.reply_text("📭 Нет других администраторов.")
        return
    
    text = "👑 **Администраторы:**\n\n"
    for admin in admins:
        text += f"• {admin['first_name']} (@{admin['username']}) - `{admin['user_id']}`\n"
    
    await message.reply_text(text)

# ===== КНОПКА НАЗАД =====

@app.on_callback_query(filters.regex("^back_to_main$"))
async def back_to_main_callback(client: Client, callback_query: CallbackQuery):
    await start_command(client, callback_query.message)

# ===== ЗАПУСК =====

if __name__ == "__main__":
    print("=" * 50)
    print("📚 ЗАПУСК БОТА-РАСПИСАНИЯ (УПРАВЛЕНИЕ ИЗ ЛС)")
    print("=" * 50)
    print("\n✅ Бот готов к работе!")
    print("📱 Админы управляют в личном чате с ботом")
    print("👥 Участники получают уведомления в группе")
    
    app.run()
