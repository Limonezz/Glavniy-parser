import asyncio
import sqlite3
import os
from datetime import datetime
import pytz
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
import logging
import hashlib
import re

# ===== ТВОИ ДАННЫЕ =====
API_ID = 30519385
API_HASH = 'fa0fc5cd3b68e94c7ce1d9c4c984df9d'
SESSION_STRING = '1ApWapzMBuyYciqhblZyGuoTsE_AaOPzwhc1OwGU5LLFhSuUes1Haofveo_gpSCiWyq_ey4VligWxXfjbh6DEO2sqAB95zSmty6baD_f6AN-NxRDy390hyeMsSZ_A0JTLNjQ3Emp0jUcvFwgOT0UINw_3_qzNRxM-VdjJ89W8yxw9DEqMFaJ-xaOuPai9QXzQmLxisTo8UrTiS98vvIsPVBi8EXQt8r2BLBEZM_fzuZP56U1tiYjnRTsaVPK5gjEL_Z8Gg4RNfKK5axCewarHDS2GSAHTnUoSeB1tF0w_BbinN-8tcZK0zMGGKgAaeHX13MRdB9JOFOakOL57Y4WMf1eebUxGlEs='
BOT_TOKEN = '8573638786:AAGVbZBTb914ileFKmGXbWLUsIQzwo5gXi8'

# ID администратора (ты)
ADMIN_ID = 1175795428

# Пробуем разные варианты ID чата
POSSIBLE_CHAT_IDS = [
    1003474109106,  # Оригинальный ID
    -1003474109106, # Возможно с минусом
]

KEYWORDS = [
    'FPV-дрон', 'обстрел', 'фортификации', 'укрепления', 'взрывчатка', 'РЭБ', 'радиоэлектронная борьба', 'приграничье',
    
    # Политика и власть
    'Путин', 'президент', 'губернатор', 'врио губернатора', 'правительство', 'администрация',
    'Госдума', 'Совет Федерации', 'законопроект', 'законодательство', 'выборы', 'мэр',
    'санкции', 'переговоры', 'дипломатия', 'международные отношения', 'саммит', 'встречи',
    'партия', 'Единая Россия', 'оппозиция', 'иноагент', 'патриотизм', 'суверенитет',
    'интеграция', 'сотрудничество', 'внешняя политика', 'федеральный бюджет', 'указы', 
    'распоряжения', 'политическое давление', 'кадровые перестановки', 'лоббирование',
    'государственные интересы',

    # Экономика и коррупция
    'бюджет', 'финансирование', 'контракт', 'госконтракт', 'тендер', 'аукцион',
    'корпорация развития', 'инвестиции', 'субсидия', 'дотация', 'налог', 'НДС',
    'уклонение от налогов', 'штраф', 'пеня', 'банкротство', 'ликвидация', 'имущество', 
    'арест имущества', 'конфискация', 'отмывание денег', 'схема', 'махинация', 'хищение', 
    'растрата', 'взятка', 'откат', 'коррупция', 'злоупотребление полномочиями',
    'служебный подлог', 'мошенничество', 'фальсификация', 'подделка документов',
    'банковские операции', 'криптовалюта', 'экономический кризис', 'инфляция',
    'недвижимость', 'фондовый рынок',

    # Строительство и инфраструктура
    'строительство', 'реконструкция', 'благоустройство', 'инфраструктура', 'транспорт', 
    'дороги', 'энергетика', 'капремонт', 'объект', 'сооружение', 'подрядчик', 'заказчик',
    'смета', 'стоимость', 'сроки строительства', 'нарушение сроков', 'приемка объектов',
    'социальные объекты', 'больницы', 'школы', 'очистные сооружения', 'мемoриальный комплекс',
    'жилье', 'квартиры',

    # Происшествия и ЧП
    'обрушение', 'разрушение', 'взрыв', 'детонация',
    'несчастный случай', 'травма', 'гибель', 'больница', 'госпиталь',
    'полиция', 'правоохранители', 'уголовное дело', 'задержание', 'арест', 'суд', 
    'судебное заседание', 'приговор', 'колония', 'СИЗО', 'следствие', 'дознание',
    'прокурор', 'следователь', 'обвиняемый', 'подозреваемый', 'доказательства', 'улики',

    # Общество и социальная сфера
    'образование', 'школы', 'здравоохранение', 'больницы', 'общественные организации',
    'СМИ', 'журналисты', 'телеграм-каналы', 'блогеры', 'информационная безопасность',
    
    # Дополнительные важные слова
    'гуманитарная помощь', 'военные учения', 'нейтрализация',
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('NewsAnalyzer')

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('news_analyzer.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Таблица для обработанных сообщений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_messages (
            message_hash TEXT PRIMARY KEY,
            message_text TEXT,
            keywords_found TEXT,
            processed_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица для подписчиков
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            subscribed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # Таблица настроек
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Добавляем администратора по умолчанию
    cursor.execute('''
        INSERT OR IGNORE INTO subscribers (user_id, username, first_name, last_name, is_active) 
        VALUES (?, ?, ?, ?, ?)
    ''', (ADMIN_ID, 'ezzlime', 'Admin', 'Admin', 1))
    
    conn.commit()
    return conn

def generate_message_hash(text):
    return hashlib.md5(text.encode()).hexdigest()

def is_message_processed(conn, message_hash):
    cursor = conn.cursor()
    cursor.execute("SELECT message_hash FROM processed_messages WHERE message_hash = ?", (message_hash,))
    return cursor.fetchone() is not None

def mark_message_processed(conn, message_hash, text, keywords):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO processed_messages (message_hash, message_text, keywords_found) VALUES (?, ?, ?)",
        (message_hash, text[:500], keywords)
    )
    conn.commit()

# ===== ФУНКЦИИ ДЛЯ ПОДПИСЧИКОВ =====
def add_subscriber(conn, user_id, username, first_name, last_name):
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO subscribers (user_id, username, first_name, last_name, is_active, subscribed_at) 
        VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
    ''', (user_id, username, first_name, last_name))
    conn.commit()
    return cursor.rowcount

def remove_subscriber(conn, user_id):
    cursor = conn.cursor()
    cursor.execute("UPDATE subscribers SET is_active = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    return cursor.rowcount

def get_subscribers(conn, active_only=True):
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT user_id, username, first_name FROM subscribers WHERE is_active = 1")
    else:
        cursor.execute("SELECT user_id, username, first_name FROM subscribers")
    return cursor.fetchall()

def get_subscriber_count(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM subscribers WHERE is_active = 1")
    return cursor.fetchone()[0]

def is_subscribed(conn, user_id):
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM subscribers WHERE user_id = ? AND is_active = 1", (user_id,))
    return cursor.fetchone() is not None

# ===== БЕЗОПАСНОЕ ФОРМАТИРОВАНИЕ =====
def safe_format_message(sender_name, message_time, found_keywords, message_text):
    """Безопасное форматирование без Markdown"""
    
    def clean_text(text):
        if not text:
            return ""
        text = re.sub(r'[*_`\[\]()]', '', text)
        if len(text) > 1200:
            text = text[:1200] + "..."
        return text
    
    sender_name = clean_text(sender_name)
    keywords_str = clean_text(', '.join(found_keywords))
    message_text = clean_text(message_text)
    
    formatted_message = (
        f"🔍 ВАЖНАЯ НОВОСТЬ\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Источник: {sender_name}\n"
        f"🕒 Время: {message_time}\n"
        f"🎯 Ключевые слова: {keywords_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 Сообщение:\n{message_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Отфильтровано NewsAnalyzer"
    )
    
    return formatted_message

# ===== РАССЫЛКА СООБЩЕНИЙ =====
async def broadcast_message(bot_client, conn, message_text, exclude_user_id=None):
    """Рассылка сообщения всем подписчикам"""
    subscribers = get_subscribers(conn)
    success_count = 0
    fail_count = 0
    
    for user_id, username, first_name in subscribers:
        if exclude_user_id and user_id == exclude_user_id:
            continue
            
        try:
            await bot_client.send_message(user_id, message_text)
            success_count += 1
            logger.info(f"✅ Отправлено пользователю: {username or first_name or user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")
            fail_count += 1
            # Если пользователь заблокировал бота, отписываем его
            if "bot was blocked" in str(e).lower():
                remove_subscriber(conn, user_id)
    
    return success_count, fail_count

# ===== ОСНОВНОЙ КОД =====
async def main():
    logger.info("🚀 ЗАПУСК NEWS ANALYZER...")
    
    db_conn = init_db()
    user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    bot_client = TelegramClient('bot_notifier', API_ID, API_HASH)
    
    try:
        await user_client.start()
        logger.info("✅ User client запущен")
        
        await bot_client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Bot client запущен")
        
        me = await user_client.get_me()
        logger.info(f"👤 Аккаунт: {me.first_name} (@{me.username})")
        
        # Ищем чат автоматически
        SOURCE_CHAT_ID = await find_target_chat(user_client)
        
        if not SOURCE_CHAT_ID:
            logger.error("❌ Не найден чат для мониторинга!")
            logger.info("📋 Доступные чаты:")
            async for dialog in user_client.iter_dialogs(limit=10):
                logger.info(f"   💬 {dialog.name} -> {dialog.id}")
            
            await bot_client.send_message(
                ADMIN_ID,
                "❌ НЕ НАЙДЕН ЧАТ!\n\n"
                "Добавь @Ezzlime в чат с новостями или отправь /chats для списка чатов"
            )
            return
        
        # Обработчик сообщений из чата
        @user_client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
        async def chat_message_handler(event):
            try:
                message = event.message
                if not message.text:
                    return
                
                logger.info(f"📥 Новое сообщение: {message.text[:100]}...")
                
                message_text = message.text
                sender = await event.get_sender()
                sender_name = sender.username or sender.first_name or f"ID_{sender.id}"
                
                message_hash = generate_message_hash(message_text)
                if is_message_processed(db_conn, message_hash):
                    logger.debug("⏭️ Сообщение уже обработано")
                    return
                
                found_keywords = []
                for keyword in KEYWORDS:
                    if keyword.lower() in message_text.lower():
                        found_keywords.append(keyword)
                
                if found_keywords:
                    logger.info(f"🎯 НАЙДЕНО: {len(found_keywords)} ключевых слов - {found_keywords}")
                    
                    moscow_tz = pytz.timezone('Europe/Moscow')
                    message_time = message.date.astimezone(moscow_tz).strftime('%H:%M %d.%m.%Y')
                    
                    formatted_message = safe_format_message(
                        sender_name, 
                        message_time, 
                        found_keywords, 
                        message_text
                    )
                    
                    try:
                        # Рассылка всем подписчикам (включая админа)
                        success, fail = await broadcast_message(bot_client, db_conn, formatted_message)
                        
                        # Логируем статистику
                        logger.info(f"📊 Рассылка: успешно {success}, неудачно {fail}")
                        
                        # Отправляем статистику админу
                        if success > 0 or fail > 0:
                            await bot_client.send_message(
                                ADMIN_ID,
                                f"📊 Рассылка новости:\n"
                                f"✅ Получили: {success} пользователей\n"
                                f"❌ Не получили: {fail} пользователей\n"
                                f"🎯 Ключевых слов: {len(found_keywords)}"
                            )
                        
                        mark_message_processed(db_conn, message_hash, message_text, ", ".join(found_keywords))
                    except Exception as e:
                        logger.error(f"❌ Ошибка рассылки: {e}")
                        
            except Exception as e:
                logger.error(f"💥 Ошибка обработки: {e}")
        
        # ===== КОМАНДЫ БОТА =====
        @bot_client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            user_id = event.sender_id
            username = event.sender.username
            first_name = event.sender.first_name
            last_name = event.sender.last_name
            
            # Добавляем пользователя при старте
            add_subscriber(db_conn, user_id, username, first_name, last_name)
            
            welcome_text = (
                "📰 *Добро пожаловать в NewsAnalyzer!*\n\n"
                "Я отслеживаю важные новости по ключевым словам и отправляю их подписчикам.\n\n"
                "🔸 Вы автоматически подписаны на рассылку\n"
                "🔸 Используйте /unsubscribe чтобы отписаться\n"
                "🔸 /status - статус системы\n"
                "🔸 /help - помощь\n\n"
                f"👥 Подписчиков: {get_subscriber_count(db_conn)}\n"
                f"🎯 Отслеживается слов: {len(KEYWORDS)}"
            )
            
            buttons = [
                [Button.inline("✅ Подписаться", b"subscribe"),
                 Button.inline("❌ Отписаться", b"unsubscribe")],
                [Button.inline("📊 Статистика", b"stats")]
            ]
            
            await event.reply(welcome_text, buttons=buttons)
        
        @bot_client.on(events.NewMessage(pattern='/subscribe'))
        async def subscribe_handler(event):
            user_id = event.sender_id
            username = event.sender.username
            first_name = event.sender.first_name
            last_name = event.sender.last_name
            
            if is_subscribed(db_conn, user_id):
                await event.reply("✅ Вы уже подписаны на рассылку!")
            else:
                add_subscriber(db_conn, user_id, username, first_name, last_name)
                await event.reply(
                    f"✅ Вы успешно подписались на рассылку!\n\n"
                    f"Теперь вы будете получать важные новости.\n"
                    f"👥 Всего подписчиков: {get_subscriber_count(db_conn)}"
                )
        
        @bot_client.on(events.NewMessage(pattern='/unsubscribe'))
        async def unsubscribe_handler(event):
            user_id = event.sender_id
            
            if not is_subscribed(db_conn, user_id):
                await event.reply("❌ Вы не подписаны на рассылку.")
            else:
                remove_subscriber(db_conn, user_id)
                await event.reply(
                    "❌ Вы отписались от рассылки.\n"
                    "Используйте /subscribe чтобы снова подписаться."
                )
        
        @bot_client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            cursor = db_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM processed_messages")
            total_processed = cursor.fetchone()[0]
            
            subscriber_count = get_subscriber_count(db_conn)
            
            status_text = (
                f"📊 *СТАТУС СИСТЕМЫ*\n\n"
                f"✅ Система активна\n"
                f"💬 Мониторинг чата: {SOURCE_CHAT_ID}\n"
                f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
                f"📈 Обработано новостей: {total_processed}\n"
                f"👥 Подписчиков: {subscriber_count}\n"
                f"🤖 Бот: @{(await bot_client.get_me()).username}"
            )
            
            await event.reply(status_text)
        
        @bot_client.on(events.NewMessage(pattern='/subscribers'))
        async def subscribers_handler(event):
            if event.sender_id != ADMIN_ID:
                await event.reply("❌ Эта команда только для администратора.")
                return
            
            subscribers = get_subscribers(db_conn)
            if not subscribers:
                await event.reply("📭 Нет активных подписчиков.")
                return
            
            text = "📋 *АКТИВНЫЕ ПОДПИСЧИКИ:*\n\n"
            for i, (user_id, username, first_name) in enumerate(subscribers, 1):
                name = f"@{username}" if username else f"{first_name or ''}"
                text += f"{i}. {name} (ID: {user_id})\n"
            
            await event.reply(text)
        
        @bot_client.on(events.NewMessage(pattern='/broadcast'))
        async def broadcast_handler(event):
            if event.sender_id != ADMIN_ID:
                await event.reply("❌ Эта команда только для администратора.")
                return
            
            # Берем текст после команды
            message_text = event.text.replace('/broadcast', '').strip()
            if not message_text:
                await event.reply("❌ Укажите текст для рассылки.\nПример: /broadcast Привет всем!")
                return
            
            subscriber_count = get_subscriber_count(db_conn)
            if subscriber_count == 0:
                await event.reply("❌ Нет подписчиков для рассылки.")
                return
            
            # Подтверждение
            buttons = [
                [Button.inline("✅ Да, отправить", b"confirm_broadcast")],
                [Button.inline("❌ Отмена", b"cancel_broadcast")]
            ]
            
            await event.reply(
                f"📢 *Подтвердите рассылку:*\n\n"
                f"Текст: {message_text[:200]}...\n"
                f"Кому: {subscriber_count} подписчиков\n\n"
                f"Отправить?",
                buttons=buttons
            )
            
            # Сохраняем текст для рассылки
            db_conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                          ('pending_broadcast', message_text))
            db_conn.commit()
        
        @bot_client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            help_text = (
                "📖 *ПОМОЩЬ*\n\n"
                "🔸 /start - Запустить бота и подписаться\n"
                "🔸 /subscribe - Подписаться на рассылку\n"
                "🔸 /unsubscribe - Отписаться от рассылки\n"
                "🔸 /status - Статус системы\n"
                "🔸 /help - Эта справка\n\n"
                "*Для администратора:*\n"
                "🔸 /subscribers - Список подписчиков\n"
                "🔸 /broadcast - Рассылка сообщения\n\n"
                "Бот отслеживает новости по ключевым словам и присылает их подписчикам."
            )
            await event.reply(help_text)
        
        # ===== ОБРАБОТКА INLINE-КНОПОК =====
        @bot_client.on(events.CallbackQuery())
        async def callback_handler(event):
            user_id = event.sender_id
            data = event.data.decode('utf-8')
            
            if data == "subscribe":
                username = event.sender.username
                first_name = event.sender.first_name
                last_name = event.sender.last_name
                
                if is_subscribed(db_conn, user_id):
                    await event.answer("Вы уже подписаны!")
                else:
                    add_subscriber(db_conn, user_id, username, first_name, last_name)
                    await event.answer("✅ Вы подписались!")
                    await event.edit(
                        f"✅ Вы успешно подписаны!\n\n"
                        f"Теперь вы будете получать важные новости.\n"
                        f"👥 Всего подписчиков: {get_subscriber_count(db_conn)}"
                    )
            
            elif data == "unsubscribe":
                if not is_subscribed(db_conn, user_id):
                    await event.answer("Вы не подписаны!")
                else:
                    remove_subscriber(db_conn, user_id)
                    await event.answer("❌ Вы отписались!")
                    await event.edit(
                        "❌ Вы отписались от рассылки.\n"
                        "Используйте /subscribe чтобы снова подписаться."
                    )
            
            elif data == "stats":
                cursor = db_conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM processed_messages")
                total_processed = cursor.fetchone()[0]
                
                stats_text = (
                    f"📊 *СТАТИСТИКА*\n\n"
                    f"👥 Подписчиков: {get_subscriber_count(db_conn)}\n"
                    f"📈 Обработано новостей: {total_processed}\n"
                    f"🎯 Ключевых слов: {len(KEYWORDS)}"
                )
                await event.answer()
                await event.edit(stats_text)
            
            elif data == "confirm_broadcast":
                if user_id != ADMIN_ID:
                    await event.answer("❌ Только для администратора!")
                    return
                
                cursor = db_conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = 'pending_broadcast'")
                result = cursor.fetchone()
                
                if not result:
                    await event.answer("❌ Нет сообщения для рассылки")
                    return
                
                message_text = result[0]
                subscriber_count = get_subscriber_count(db_conn)
                
                await event.answer(f"🔄 Рассылаю {subscriber_count} подписчикам...")
                
                success, fail = await broadcast_message(bot_client, db_conn, message_text, ADMIN_ID)
                
                # Очищаем сохраненное сообщение
                db_conn.execute("DELETE FROM settings WHERE key = 'pending_broadcast'")
                db_conn.commit()
                
                await event.edit(
                    f"📢 *Рассылка завершена*\n\n"
                    f"✅ Успешно: {success}\n"
                    f"❌ Неудачно: {fail}\n"
                    f"📝 Текст: {message_text[:100]}..."
                )
            
            elif data == "cancel_broadcast":
                if user_id != ADMIN_ID:
                    await event.answer("❌ Только для администратора!")
                    return
                
                db_conn.execute("DELETE FROM settings WHERE key = 'pending_broadcast'")
                db_conn.commit()
                
                await event.answer("❌ Рассылка отменена")
                await event.delete()
        
        logger.info(f"🔄 НАЧИНАЮ МОНИТОРИНГ ЧАТА {SOURCE_CHAT_ID}...")
        
        # Тестовое уведомление админу
        await bot_client.send_message(
            ADMIN_ID,
            f"🟢 NewsAnalyzer запущен!\n\n"
            f"✅ Мониторю чат: {SOURCE_CHAT_ID}\n"
            f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
            f"👥 Подписчиков: {get_subscriber_count(db_conn)}\n"
            f"🤖 Бот: @{(await bot_client.get_me()).username}\n\n"
            f"🔄 Начинаю мониторинг..."
        )
        
        # Рассылка запуска подписчикам
        launch_message = (
            "🟢 *NewsAnalyzer перезапущен!*\n\n"
            "Система мониторинга новостей снова активна.\n"
            "Вы продолжите получать важные новости по ключевым словам."
        )
        
        success, fail = await broadcast_message(bot_client, db_conn, launch_message, ADMIN_ID)
        logger.info(f"📢 Уведомление о запуске: успешно {success}, неудачно {fail}")
        
        await user_client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await user_client.disconnect()
        await bot_client.disconnect()
        db_conn.close()

# ===== ПОИСК ЧАТА =====
async def find_target_chat(client):
    """Находит чат с новостями автоматически"""
    logger.info("🔍 Ищу чат с новостями...")
    
    target_chat = None
    
    async for dialog in client.iter_dialogs():
        if any(keyword in dialog.name.lower() for keyword in ['новост', 'парсер', 'канал', 'news']):
            logger.info(f"🎯 НАЙДЕН ЧАТ: {dialog.name} -> {dialog.id}")
            target_chat = dialog
            break
        
        if dialog.id in POSSIBLE_CHAT_IDS or abs(dialog.id) in [abs(pid) for pid in POSSIBLE_CHAT_IDS]:
            logger.info(f"🎯 НАЙДЕН ЧАТ ПО ID: {dialog.name} -> {dialog.id}")
            target_chat = dialog
            break
    
    if target_chat:
        logger.info(f"✅ Использую чат: {target_chat.name} (ID: {target_chat.id})")
        return target_chat.id
    else:
        logger.error("❌ Не удалось найти подходящий чат")
        return None

if __name__ == '__main__':
    asyncio.run(main())
