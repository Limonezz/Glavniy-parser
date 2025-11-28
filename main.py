import asyncio
import sqlite3
import os
from datetime import datetime, timedelta
import pytz
from telethon import TelegramClient, events
import logging
import re
import hashlib

# ===== КОНФИГУРАЦИЯ =====
API_ID = os.environ.get('API_ID', '24826804')
API_HASH = os.environ.get('API_HASH', '048e59c243cce6ff788a7da214bf8119')
BOT_TOKEN = '8573638786:AAGVbZBTb914ileFKmGXbWLUsIQzwo5gXi8'

# ID чата, который будем мониторить
SOURCE_CHAT_ID = 1003474109106

KEYWORDS = [
    'обстрел', 'атака', 'прилет', 'диверсант', 'ДРГ', 'ракета', 'Искандер',
    'пленный', 'плен', 'РЭБ', 'наступление', 'штурм', 'артобстрел',
    'танк', 'БМП', 'БТР', 'дрон', 'FPV-дрон', 'Герань',
    'ВСУ', 'ВС РФ', 'ЧВК', 'Вагнер', 'Кадыров',
    'Путин', 'президент', 'губернатор', 'правительство',
    'бюджет', 'финансирование', 'коррупция',
    'авария', 'катастрофа', 'взрыв', 'гибель', 'пострадавший',
    'суд', 'приговор', 'задержание',
    'НАТО', 'США', 'Байден', 'ЕС', 'санкции',
    'Крым', 'Белгород', 'Курск', 'Брянск', 'Херсон'
]

PERMANENT_SUBSCRIBERS = [1175795428, 8019965642]
SUBSCRIBERS_FILE = 'analyzer_subscribers.txt'

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ChatAnalyzer')

# ===== ПРОВЕРКА ДОСТУПА К ЧАТУ =====
async def check_chat_access(client):
    """Проверяет доступ бота к чату"""
    try:
        logger.info(f"🔍 Проверяю доступ к чату {SOURCE_CHAT_ID}...")
        
        # Пробуем получить информацию о чате
        chat = await client.get_entity(SOURCE_CHAT_ID)
        logger.info(f"✅ Чат найден: {chat.title if hasattr(chat, 'title') else 'Unknown'}")
        
        # Пробуем получить последние сообщения
        messages = await client.get_messages(SOURCE_CHAT_ID, limit=1)
        if messages:
            logger.info(f"✅ Могу читать сообщения! Последнее: {messages[0].text[:50] if messages[0].text else 'NO TEXT'}")
        else:
            logger.info("✅ Могу читать сообщения (чат пустой)")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ НЕТ ДОСТУПА К ЧАТУ: {e}")
        logger.info("💡 Решение: Сделайте бота администратором чата с правом 'Читать сообщения'")
        return False

# ===== СИСТЕМА ПОДПИСЧИКОВ =====
def load_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
            return [int(line.strip()) for line in f if line.strip().isdigit()]
    except FileNotFoundError:
        return PERMANENT_SUBSCRIBERS.copy()

def save_subscribers(subscribers):
    try:
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            for user_id in subscribers:
                f.write(f"{user_id}\n")
    except Exception as e:
        logger.error(f"Ошибка сохранения подписчиков: {e}")

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('chat_analyzer.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_messages (
            message_hash TEXT PRIMARY KEY,
            source_chat_id INTEGER,
            original_sender TEXT,
            message_text TEXT,
            keywords_found TEXT,
            processed_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

def generate_message_hash(message_text, sender_id):
    return hashlib.md5(f"{message_text}_{sender_id}".encode()).hexdigest()

def is_message_processed(conn, message_hash):
    cursor = conn.cursor()
    cursor.execute("SELECT message_hash FROM processed_messages WHERE message_hash = ?", (message_hash,))
    return cursor.fetchone() is not None

def mark_message_processed(conn, message_hash, chat_id, sender_name, message_text, keywords):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO processed_messages (message_hash, source_chat_id, original_sender, message_text, keywords_found) VALUES (?, ?, ?, ?, ?)",
        (message_hash, chat_id, sender_name, message_text[:500], keywords)
    )
    conn.commit()

# ===== ФУНКЦИИ АНАЛИЗА =====
def analyze_message(text):
    if not text:
        return []
    
    text_lower = text.lower()
    found_keywords = []
    
    for keyword in KEYWORDS:
        if keyword.lower() in text_lower:
            found_keywords.append(keyword)
    
    return found_keywords

# ===== ОСНОВНОЙ БОТ =====
async def main():
    logger.info("🚀 ЗАПУСК АНАЛИЗАТОРА ЧАТА...")
    
    client = TelegramClient('chat_analyzer_session', API_ID, API_HASH)
    db_conn = init_db()
    
    # ПРОВЕРКА ДОСТУПА ПРИ ЗАПУСКЕ
    try:
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Бот авторизован")
        
        has_access = await check_chat_access(client)
        if not has_access:
            logger.error("❌ БОТ НЕ МОЖЕТ ЧИТАТЬ СООБЩЕНИЯ ИЗ ЧАТА!")
            logger.info("🔧 Решение: Добавьте бота как администратора в чат с правом 'Читать сообщения'")
            return
        
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации: {e}")
        return
    
    @client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
    async def chat_message_handler(event):
        try:
            message = event.message
            logger.debug(f"📥 НОВОЕ СООБЩЕНИЕ: {message.text[:100] if message.text else 'NO TEXT'}")
            
            if not message.text:
                return
            
            message_text = message.text
            sender = await event.get_sender()
            sender_name = sender.username or sender.first_name or f"ID_{sender.id}"
            
            # Проверяем дубликаты
            message_hash = generate_message_hash(message_text, event.sender_id)
            if is_message_processed(db_conn, message_hash):
                logger.debug("⏭️ Уже обработано")
                return
            
            # Анализируем сообщение
            found_keywords = analyze_message(message_text)
            
            if found_keywords:
                logger.info(f"🎯 НАЙДЕНО: {len(found_keywords)} ключевых слов")
                
                # Форматируем сообщение
                moscow_tz = pytz.timezone('Europe/Moscow')
                message_time = message.date.astimezone(moscow_tz).strftime('%H:%M %d.%m.%Y')
                
                formatted_message = (
                    f"🔍 **ВАЖНАЯ НОВОСТЬ**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 **Источник:** {sender_name}\n"
                    f"🕒 **Время:** {message_time}\n"
                    f"🎯 **Ключевые слова:** {', '.join(found_keywords)}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📝 **Сообщение:**\n{message_text}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"*Отфильтровано системой мониторинга*"
                )
                
                # Отправляем подписчикам
                subscribers = load_subscribers()
                for user_id in subscribers:
                    try:
                        await client.send_message(user_id, formatted_message, parse_mode='md')
                        logger.info(f"✅ Отправлено пользователю {user_id}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки {user_id}: {e}")
                
                mark_message_processed(db_conn, message_hash, SOURCE_CHAT_ID, sender_name, message_text, ", ".join(found_keywords))
            
        except Exception as e:
            logger.error(f"💥 Ошибка обработки: {e}")

    # Команды бота
    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        user_id = event.sender_id
        subscribers = load_subscribers()
        if user_id not in subscribers:
            subscribers.append(user_id)
            save_subscribers(subscribers)
        
        await event.reply(
            "🔍 **Анализатор чата АКТИВЕН!**\n\n"
            f"💬 Мониторим чат: {SOURCE_CHAT_ID}\n"
            f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
            f"✅ Вы подписаны!\n\n"
            "✨ **Команды:**\n"
            "/status - статус системы\n"
            "/test - тест анализа"
        )

    @client.on(events.NewMessage(pattern='/status'))
    async def status_handler(event):
        has_access = await check_chat_access(client)
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_messages")
        total = cursor.fetchone()[0]
        
        status_msg = (
            f"📊 **СТАТУС СИСТЕМЫ:**\n\n"
            f"💬 Доступ к чату: {'✅ ЕСТЬ' if has_access else '❌ НЕТ'}\n"
            f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
            f"📈 Обработано: {total}\n"
            f"🔧 Бот активен: ✅ ДА"
        )
        
        if not has_access:
            status_msg += "\n\n⚠️ **РЕШЕНИЕ:** Сделайте бота администратором чата с правом 'Читать сообщения'"
        
        await event.reply(status_msg)

    @client.on(events.NewMessage(pattern='/test'))
    async def test_handler(event):
        test_text = "Обстрел Белгорода: повреждены дома. Путин провел совещание."
        found = analyze_message(test_text)
        
        await event.reply(
            f"🧪 **ТЕСТ:** Найдено {len(found)} ключевых слов: {', '.join(found)}"
        )

    # Запуск мониторинга
    logger.info("✅ Начинаю мониторинг чата...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    if not os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            for user_id in PERMANENT_SUBSCRIBERS:
                f.write(f"{user_id}\n")
    
    asyncio.run(main())
