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

# Ключевые слова для фильтрации (упрощенный список для теста)
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

# Подписчики
PERMANENT_SUBSCRIBERS = [1175795428, 8019965642]
SUBSCRIBERS_FILE = 'analyzer_subscribers.txt'

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,  # ИЗМЕНИЛ НА DEBUG ДЛЯ ПОДРОБНОГО ЛОГИРОВАНИЯ
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chat_analyzer_debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ChatAnalyzer')

# ===== СИСТЕМА ПОДПИСЧИКОВ =====
def load_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
            file_subs = [int(line.strip()) for line in f if line.strip().isdigit()]
    except FileNotFoundError:
        file_subs = []
    all_subs = list(set(PERMANENT_SUBSCRIBERS + file_subs))
    logger.info(f"Загружено подписчиков: {len(all_subs)}")
    return all_subs

def save_subscribers(subscribers):
    regular_subs = [sub for sub in subscribers if sub not in PERMANENT_SUBSCRIBERS]
    try:
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            for user_id in regular_subs:
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
    logger.info("База данных инициализирована")
    return conn

def generate_message_hash(chat_id, message_text, sender_id):
    text_to_hash = f"{chat_id}_{sender_id}_{clean_text(message_text)}"
    return hashlib.md5(text_to_hash.encode()).hexdigest()

def is_message_processed(conn, message_hash):
    cursor = conn.cursor()
    cursor.execute("SELECT message_hash FROM processed_messages WHERE message_hash = ?", (message_hash,))
    return cursor.fetchone() is not None

def mark_message_processed(conn, message_hash, chat_id, sender_name, message_text, keywords):
    cursor = conn.cursor()
    cursor.execute(
        """INSERT OR IGNORE INTO processed_messages 
        (message_hash, source_chat_id, original_sender, message_text, keywords_found) 
        VALUES (?, ?, ?, ?, ?)""",
        (message_hash, chat_id, sender_name, message_text[:1000], keywords)
    )
    conn.commit()

# ===== ФУНКЦИИ АНАЛИЗА =====
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'http\S+|@\w+|#\w+', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower()

def analyze_message(text):
    if not text:
        return []
    
    text_lower = text.lower()
    found_keywords = []
    
    logger.debug(f"🔍 Анализируем текст: {text_lower[:100]}...")
    
    for keyword in KEYWORDS:
        if keyword.lower() in text_lower:
            found_keywords.append(keyword)
            logger.debug(f"🎯 Найдено ключевое слово: {keyword}")
    
    logger.debug(f"📊 Всего найдено ключевых слов: {len(found_keywords)}")
    return found_keywords

def is_recent_message(message_date):
    utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
    message_age = utc_now - message_date
    is_recent = message_age <= timedelta(hours=24)
    logger.debug(f"🕒 Сообщение свежее: {is_recent} (возраст: {message_age})")
    return is_recent

# ===== ОСНОВНОЙ БОТ =====
async def main():
    logger.info("🚀 ЗАПУСК АНАЛИЗАТОРА ЧАТА С ДЕБАГОМ...")
    
    client = TelegramClient('chat_analyzer_session', API_ID, API_HASH)
    db_conn = init_db()
    
    @client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
    async def chat_message_handler(event):
        try:
            message = event.message
            logger.debug(f"📥 ПОЛУЧЕНО СООБЩЕНИЕ: {message.text[:100] if message.text else 'NO TEXT'}")
            
            if not message.text:
                logger.debug("⏭️ Пропущено: нет текста")
                return
            
            # Проверяем свежесть сообщения
            if not is_recent_message(message.date):
                logger.debug("⏭️ Пропущено: сообщение устарело")
                return
            
            message_text = message.text
            sender = await event.get_sender()
            sender_name = sender.username or sender.first_name or f"ID_{sender.id}"
            
            logger.debug(f"👤 Отправитель: {sender_name}")
            
            # Проверяем дубликаты
            message_hash = generate_message_hash(SOURCE_CHAT_ID, message_text, event.sender_id)
            if is_message_processed(db_conn, message_hash):
                logger.debug("⏭️ Пропущено: уже обработано")
                return
            
            # Анализируем сообщение
            found_keywords = analyze_message(message_text)
            
            if found_keywords:
                logger.info(f"🎯 НАЙДЕНЫ КЛЮЧЕВЫЕ СЛОВА: {len(found_keywords)} - {found_keywords}")
                
                # Форматируем сообщение для отправки
                moscow_tz = pytz.timezone('Europe/Moscow')
                message_time = message.date.astimezone(moscow_tz).strftime('%H:%M %d.%m.%Y')
                
                formatted_message = (
                    f"🔍 **ВАЖНАЯ НОВОСТЬ**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 **Источник:** {sender_name}\n"
                    f"🕒 **Время:** {message_time}\n"
                    f"🎯 **Ключевые слова:** {', '.join(found_keywords[:8])}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📝 **Сообщение:**\n{message_text[:600]}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"*Отфильтровано системой мониторинга*"
                )
                
                # Отправляем подписчикам
                subscribers = load_subscribers()
                success_count = 0
                
                logger.debug(f"👥 Попытка отправки {len(subscribers)} подписчикам")
                
                for user_id in subscribers:
                    try:
                        await client.send_message(
                            user_id, 
                            formatted_message, 
                            parse_mode='md',
                            link_preview=False
                        )
                        success_count += 1
                        logger.info(f"✅ Отправлено подписчику {user_id}")
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки {user_id}: {e}")
                
                if success_count > 0:
                    mark_message_processed(
                        db_conn, 
                        message_hash, 
                        SOURCE_CHAT_ID, 
                        sender_name, 
                        message_text,
                        ", ".join(found_keywords)
                    )
                    logger.info(f"📊 УСПЕХ: Обработано сообщение. Ключевых слов: {len(found_keywords)}. Отправлено: {success_count}")
                else:
                    logger.error("💥 НИ ОДНОМУ ПОДПИСЧИКУ НЕ ОТПРАВЛЕНО!")
            
            else:
                logger.debug("⏭️ Пропущено: ключевые слова не найдены")
            
        except Exception as e:
            logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА ОБРАБОТКИ: {e}")

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
            f"✅ Вы подписаны на уведомления!\n\n"
            "✨ **Команды:**\n"
            "/test - тест анализа\n"
            "/debug - статус системы\n"
            "/stats - статистика"
        )
        logger.info(f"👤 Новый подписчик: {user_id}")

    @client.on(events.NewMessage(pattern='/test'))
    async def test_handler(event):
        """Тестовая команда"""
        test_text = "Обстрел Белгорода: повреждены дома, пострадавших нет. Путин провел совещание."
        
        found_keywords = analyze_message(test_text)
        
        await event.reply(
            f"🧪 **ТЕСТ АНАЛИЗАТОРА:**\n\n"
            f"Текст: {test_text}\n\n"
            f"🎯 Найдено ключевых слов: {len(found_keywords)}\n"
            f"📝 Слова: {', '.join(found_keywords) if found_keywords else 'НЕТ'}\n\n"
            f"✅ Система работает: ДА"
        )

    @client.on(events.NewMessage(pattern='/debug'))
    async def debug_handler(event):
        """Команда отладки"""
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_messages")
        total_processed = cursor.fetchone()[0]
        
        cursor.execute("SELECT message_text FROM processed_messages ORDER BY processed_time DESC LIMIT 1")
        last_message = cursor.fetchone()
        
        await event.reply(
            f"🐛 **ДЕБАГ ИНФО:**\n\n"
            f"💬 ID чата: {SOURCE_CHAT_ID}\n"
            f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
            f"📊 Обработано сообщений: {total_processed}\n"
            f"⏰ Последнее: {last_message[0][:50] if last_message else 'НЕТ'}\n"
            f"🔧 Логирование: DEBUG\n"
            f"✅ Бот активен: ДА"
        )

    @client.on(events.NewMessage(pattern='/stats'))
    async def stats_handler(event):
        subscribers = load_subscribers()
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_messages")
        total_processed = cursor.fetchone()[0]
        
        await event.reply(
            f"📊 **СТАТИСТИКА:**\n\n"
            f"👥 Подписчиков: {len(subscribers)}\n"
            f"💬 Чат: {SOURCE_CHAT_ID}\n"
            f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
            f"📈 Обработано: {total_processed}"
        )

    # Запуск
    try:
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ БОТ УСПЕШНО ЗАПУЩЕН!")
        logger.info(f"🔍 Мониторим чат: {SOURCE_CHAT_ID}")
        logger.info(f"🎯 Ключевых слов: {len(KEYWORDS)}")
        
        # Тестовое сообщение
        try:
            await client.send_message(
                'me',
                f"🟢 **АНАЛИЗАТОР ЧАТА ЗАПУЩЕН**\n\n"
                f"💬 Чат: {SOURCE_CHAT_ID}\n"
                f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}\n\n"
                f"✅ Начинаю мониторинг...",
                parse_mode='md'
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить тестовое сообщение: {e}")
        
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА ЗАПУСКА: {e}")
    finally:
        await client.disconnect()
        db_conn.close()

if __name__ == '__main__':
    # Создаем необходимые файлы
    if not os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            f.write("1175795428\n8019965642\n")
    
    asyncio.run(main())
