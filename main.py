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

# Ключевые слова для фильтрации (расширенный список)
KEYWORDS = [
    # Военные действия
    'обстрел', 'атака', 'прилет', 'диверсант', 'ДРГ', 'ракета', 'Искандер',
    'пленный', 'плен', 'РЭБ', 'наступление', 'контрнаступление',
    'окружение', 'штурм', 'артобстрел', 'миномет', 'артиллерия', 'танк', 'БМП', 'БТР',
    'беспилотник', 'дрон', 'FPV-дрон', 'Герань', 'Шахед', 'Ланцет',
    'С-300', 'С-400', 'Искандер', 'Калибр', 'Кинжал',
    'фортификация', 'укрепление', 'траншея', 'бункер',
    'ВСУ', 'ВС РФ', 'ЧВК', 'Вагнер', 'Ахмат', 'Кадыров', 'ССО', 'разведка',
    
    # Политика и власть
    'Путин', 'президент', 'губернатор', 'правительство', 'Госдума',
    'законопроект', 'выборы', 'санкции', 'переговоры', 'дипломатия',
    'Медведев', 'Песков', 'Лавров', 'Шойгу', 'Герасимов',
    
    # Экономика и коррупция
    'бюджет', 'финансирование', 'госконтракт', 'оборонный заказ',
    'военно-промышленный комплекс', 'Ростех', 'коррупция', 'взятка',
    'хищение', 'растрата', 'мошенничество',
    
    # Происшествия
    'авария', 'катастрофа', 'обрушение', 'разрушение', 'взрыв', 'гибель', 'пострадавший',
    'уголовное дело', 'задержание', 'арест', 'суд', 'приговор',
    
    # Инфраструктура
    'АЭС', 'атомная станция', 'Курская АЭС-2', 'электроэнергия',
    'строительство', 'реконструкция', 'благоустройство',
    
    # Международные отношения
    'НАТО', 'США', 'Пентагон', 'Байден', 'ЕС', 'санкция', 'эмбарго',
    'военная помощь', 'вооружение', 'оружие', 'F-16', 'Абрамс', 'Леопард',
    
    # География
    'Донбасс', 'ДНР', 'ЛНР', 'Крым', 'Севастополь', 'Херсон', 'Запорожье', 
    'Мариуполь', 'Бахмут', 'Авдеевка', 'Лиман', 'Изюм', 'Купянск', 'Харьков',
    'Белгород', 'Курск', 'Брянск',
    
    # Социальные аспекты
    'эвакуация', 'беженец', 'переселенец', 'гуманитарная помощь', 'военное положение'
]

# Категории для лучшей организации
CATEGORIES = {
    '⚔️ Военные действия': ['обстрел', 'атака', 'прилет', 'наступление', 'штурм', 'артобстрел'],
    '🛡️ Техника и вооружение': ['танк', 'БМП', 'БТР', 'дрон', 'ракета', 'С-300', 'С-400'],
    '🏛️ Политика и власть': ['Путин', 'президент', 'губернатор', 'правительство', 'Госдума'],
    '💰 Экономика и коррупция': ['бюджет', 'финансирование', 'госконтракт', 'коррупция'],
    '🚨 Происшествия и ЧП': ['авария', 'катастрофа', 'взрыв', 'гибель', 'пострадавший'],
    '🌍 Международные отношения': ['НАТО', 'США', 'ЕС', 'санкции'],
    '📍 География': ['Белгород', 'Курск', 'Брянск', 'Крым', 'Донбасс']
}

# Подписчики (пользователи, которым будем отправлять отфильтрованные новости)
PERMANENT_SUBSCRIBERS = [
    1175795428,
    8019965642,
]

SUBSCRIBERS_FILE = 'analyzer_subscribers.txt'
MAX_MESSAGE_AGE_HOURS = 24

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chat_analyzer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ChatAnalyzer')

# ===== СИСТЕМА ПОДПИСЧИКОВ =====
def load_subscribers():
    """Загружает список подписчиков"""
    try:
        with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
            file_subs = [int(line.strip()) for line in f if line.strip().isdigit()]
    except FileNotFoundError:
        file_subs = []
    
    all_subs = list(set(PERMANENT_SUBSCRIBERS + file_subs))
    logger.info(f"📋 Загружено подписчиков: {len(all_subs)}")
    return all_subs

def save_subscribers(subscribers):
    """Сохраняет список подписчиков"""
    regular_subs = [sub for sub in subscribers if sub not in PERMANENT_SUBSCRIBERS]
    try:
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            for user_id in regular_subs:
                f.write(f"{user_id}\n")
    except Exception as e:
        logger.error(f"Ошибка сохранения подписчиков: {e}")

def add_subscriber(user_id):
    """Добавляет подписчика"""
    subscribers = load_subscribers()
    if user_id not in subscribers:
        subscribers.append(user_id)
        save_subscribers(subscribers)
        logger.info(f"✅ Новый подписчик: {user_id}")
    return load_subscribers()

def remove_subscriber(user_id):
    """Удаляет подписчика"""
    if user_id in PERMANENT_SUBSCRIBERS:
        logger.info(f"⏩ Пропуск удаления вечного подписчика: {user_id}")
        return load_subscribers()
    
    subscribers = load_subscribers()
    if user_id in subscribers:
        subscribers.remove(user_id)
        save_subscribers(subscribers)
        logger.info(f"❌ Отписался: {user_id}")
    return load_subscribers()

# ===== БАЗА ДАННЫХ =====
def init_db():
    """Инициализирует базу данных"""
    conn = sqlite3.connect('chat_analyzer.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_messages (
            message_hash TEXT PRIMARY KEY,
            source_chat_id INTEGER,
            original_sender TEXT,
            message_text TEXT,
            keywords_found TEXT,
            category TEXT,
            processed_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    logger.info("✅ База данных инициализирована")
    return conn

def generate_message_hash(chat_id, message_text, sender_id):
    """Генерирует хеш для идентификации сообщения"""
    text_to_hash = f"{chat_id}_{sender_id}_{clean_text(message_text)}"
    return hashlib.md5(text_to_hash.encode()).hexdigest()

def is_message_processed(conn, message_hash):
    """Проверяет, было ли сообщение уже обработано"""
    cursor = conn.cursor()
    cursor.execute("SELECT message_hash FROM processed_messages WHERE message_hash = ?", (message_hash,))
    return cursor.fetchone() is not None

def mark_message_processed(conn, message_hash, chat_id, sender_name, message_text, keywords, category):
    """Помечает сообщение как обработанное"""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT OR IGNORE INTO processed_messages 
        (message_hash, source_chat_id, original_sender, message_text, keywords_found, category) 
        VALUES (?, ?, ?, ?, ?, ?)""",
        (message_hash, chat_id, sender_name, message_text[:1000], keywords, category)
    )
    conn.commit()

# ===== ФУНКЦИИ АНАЛИЗА =====
def clean_text(text):
    """Очищает текст от лишних символов"""
    if not text:
        return ""
    text = re.sub(r'http\S+|@\w+|#\w+', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower()

def analyze_message(text):
    """Анализирует сообщение и возвращает найденные ключевые слова и категорию"""
    if not text:
        return [], "не определено"
    
    text_lower = text.lower()
    found_keywords = []
    found_categories = set()
    
    # Поиск ключевых слов
    for keyword in KEYWORDS:
        if keyword.lower() in text_lower:
            found_keywords.append(keyword)
            
            # Определяем категорию
            for category, words in CATEGORIES.items():
                if keyword in words:
                    found_categories.add(category)
    
    # Определяем основную категорию
    if found_categories:
        main_category = list(found_categories)[0]
    else:
        main_category = "не определено"
    
    return found_keywords, main_category

def is_recent_message(message_date):
    """Проверяет, является ли сообщение свежим"""
    utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
    message_age = utc_now - message_date
    return message_age <= timedelta(hours=MAX_MESSAGE_AGE_HOURS)

def format_analyzed_message(original_message, sender_name, found_keywords, category, message_date, message_link=None):
    """Форматирует проанализированное сообщение для отправки"""
    
    # Форматируем время
    moscow_tz = pytz.timezone('Europe/Moscow')
    message_time = message_date.astimezone(moscow_tz).strftime('%H:%M %d.%m.%Y')
    
    # Обрезаем текст если слишком длинный
    if len(original_message) > 600:
        display_text = original_message[:600] + "..."
    else:
        display_text = original_message
    
    # Форматируем ключевые слова
    if found_keywords:
        keywords_str = ", ".join(found_keywords[:8])
        if len(found_keywords) > 8:
            keywords_str += f" ... (всего: {len(found_keywords)})"
    else:
        keywords_str = "не найдены"
    
    # Создаем сообщение
    formatted_message = (
        f"🔍 **ВАЖНАЯ НОВОСТЬ**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 **Источник:** {sender_name}\n"
        f"🕒 **Время:** {message_time}\n"
        f"🏷️ **Категория:** {category}\n"
        f"🎯 **Ключевые слова:** {keywords_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 **Сообщение:**\n{display_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    # Добавляем ссылку если есть
    if message_link:
        formatted_message += f"🔗 [Ссылка на сообщение]({message_link})\n"
    
    formatted_message += "*Отфильтровано системой мониторинга*"
    
    return formatted_message

# ===== ОСНОВНОЙ БОТ =====
async def main():
    logger.info("🚀 Запуск Chat Analyzer Bot...")
    
    # Инициализация клиента
    client = TelegramClient('chat_analyzer_session', API_ID, API_HASH)
    db_conn = init_db()
    
    @client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
    async def chat_message_handler(event):
        """Обработчик новых сообщений в чате"""
        try:
            message = event.message
            if not message.text:
                return
            
            logger.info(f"📥 Получено сообщение от {event.sender_id} в чате {SOURCE_CHAT_ID}")
            
            # Проверяем свежесть сообщения
            if not is_recent_message(message.date):
                logger.info("⏭️ Сообщение слишком старое, пропускаем")
                return
            
            message_text = message.text
            sender = await event.get_sender()
            sender_name = sender.username or sender.first_name or f"ID_{sender.id}"
            
            # Проверяем дубликаты
            message_hash = generate_message_hash(SOURCE_CHAT_ID, message_text, event.sender_id)
            if is_message_processed(db_conn, message_hash):
                logger.info("⏭️ Сообщение уже обработано, пропускаем")
                return
            
            # Анализируем сообщение
            found_keywords, category = analyze_message(message_text)
            
            # Если нашли ключевые слова - обрабатываем
            if found_keywords:
                logger.info(f"🎯 Найдены ключевые слова: {len(found_keywords)} шт. Категория: {category}")
                
                # Создаем ссылку на сообщение
                message_link = f"https://t.me/c/{str(SOURCE_CHAT_ID).replace('-100', '')}/{message.id}"
                
                # Форматируем сообщение для отправки
                formatted_message = format_analyzed_message(
                    message_text, 
                    sender_name, 
                    found_keywords, 
                    category, 
                    message.date,
                    message_link
                )
                
                # Отправляем подписчикам
                subscribers = load_subscribers()
                success_count = 0
                
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
                        await asyncio.sleep(0.3)  # Пауза между отправками
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки {user_id}: {e}")
                
                if success_count > 0:
                    mark_message_processed(
                        db_conn, 
                        message_hash, 
                        SOURCE_CHAT_ID, 
                        sender_name, 
                        message_text,
                        ", ".join(found_keywords),
                        category
                    )
                    logger.info(f"📊 Обработано сообщение. Найдено ключевых слов: {len(found_keywords)}. Отправлено {success_count} подписчикам")
                else:
                    logger.warning("⚠️ Не удалось отправить ни одному подписчику")
            else:
                logger.info("⏭️ Ключевые слова не найдены, пропускаем")
            
        except Exception as e:
            logger.error(f"💥 Ошибка обработки сообщения: {e}")

    # ===== КОМАНДЫ БОТА =====
    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        """Команда /start"""
        user_id = event.sender_id
        subscribers = add_subscriber(user_id)
        
        await event.reply(
            "🔍 **Добро пожаловать в систему анализа чата!**\n\n"
            "✅ Вы подписались на получение отфильтрованных новостей\n"
            f"💬 Мониторим чат: {SOURCE_CHAT_ID}\n"
            f"🎯 Ключевых слов для анализа: {len(KEYWORDS)}\n"
            f"🏷️ Категорий: {len(CATEGORIES)}\n"
            "⚡ Получаете только самые важные сообщения\n\n"
            "✨ **Команды:**\n"
            "/stats - статистика\n"
            "/stop - отписаться\n"
            "/keywords - ключевые слова\n"
            "/categories - категории\n"
            "/test - тест анализа"
        )
        logger.info(f"👤 Пользователь {user_id} подписался")

    @client.on(events.NewMessage(pattern='/stop'))
    async def stop_handler(event):
        """Команда /stop"""
        user_id = event.sender_id
        subscribers = remove_subscriber(user_id)
        await event.reply("❌ Вы отписались от аналитики чата")
        logger.info(f"👤 Пользователь {user_id} отписался")

    @client.on(events.NewMessage(pattern='/stats'))
    async def stats_handler(event):
        """Команда /stats"""
        subscribers = load_subscribers()
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_messages")
        total_processed = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT category) FROM processed_messages WHERE category != 'не определено'")
        active_categories = cursor.fetchone()[0]
        
        await event.reply(
            f"📊 **Статистика анализатора:**\n\n"
            f"👥 Подписчиков: {len(subscribers)}\n"
            f"💬 Мониторим чат: {SOURCE_CHAT_ID}\n"
            f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
            f"🏷️ Категорий: {len(CATEGORIES)}\n"
            f"📈 Обработано сообщений: {total_processed}\n"
            f"🔍 Активных категорий: {active_categories}\n"
            f"⏱ Глубина анализа: {MAX_MESSAGE_AGE_HOURS} часов"
        )

    @client.on(events.NewMessage(pattern='/keywords'))
    async def keywords_handler(event):
        """Команда /keywords"""
        categories_text = "\n".join([f"• {cat}: {len(words)} слов" for cat, words in CATEGORIES.items()])
        
        await event.reply(
            f"🎯 **Система анализа ключевых слов:**\n\n"
            f"{categories_text}\n\n"
            f"📝 Всего ключевых слов: {len(KEYWORDS)}\n"
            f"🔍 Бот анализирует сообщения на наличие этих слов"
        )

    @client.on(events.NewMessage(pattern='/categories'))
    async def categories_handler(event):
        """Команда /categories"""
        categories_detail = []
        for category, words in CATEGORIES.items():
            sample_words = ", ".join(words[:3])
            if len(words) > 3:
                sample_words += f"... (еще {len(words)-3})"
            categories_detail.append(f"• **{category}**: {sample_words}")
        
        await event.reply(
            "🏷️ **Категории для анализа:**\n\n" + "\n\n".join(categories_detail)
        )

    @client.on(events.NewMessage(pattern='/test'))
    async def test_handler(event):
        """Команда /test - тест анализа"""
        test_text = (
            "В результате обстрела Белгорода повреждены несколько жилых домов. "
            "По предварительной информации, пострадавших нет. Спецслужбы работают на месте. "
            "Путин провел совещание по ситуации в регионе."
        )
        
        found_keywords, category = analyze_message(test_text)
        formatted_test = format_analyzed_message(
            test_text,
            "test_bot",
            found_keywords,
            category,
            datetime.now(pytz.utc)
        )
        
        await event.reply(
            "🧪 **Тест анализатора:**\n\n" + formatted_test,
            parse_mode='md',
            link_preview=False
        )
        logger.info("✅ Тест анализа выполнен")

    # ===== ЗАПУСК БОТА =====
    try:
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Chat Analyzer Bot успешно запущен!")
        
        subscribers = load_subscribers()
        logger.info(f"👥 Подписчиков: {len(subscribers)}")
        logger.info(f"💬 Мониторим чат: {SOURCE_CHAT_ID}")
        logger.info(f"🎯 Ключевых слов: {len(KEYWORDS)}")
        logger.info(f"🏷️ Категорий: {len(CATEGORIES)}")
        
        # Уведомляем вечных подписчиков
        for user_id in PERMANENT_SUBSCRIBERS:
            try:
                await client.send_message(
                    user_id, 
                    "🟢 **Система анализа чата запущена!**\n\n"
                    f"✅ Начинаю мониторинг чата: {SOURCE_CHAT_ID}\n"
                    f"🎯 Анализирую по {len(KEYWORDS)} ключевым словам\n"
                    f"🏷️ Категорий анализа: {len(CATEGORIES)}\n"
                    "⚡ Ожидайте важные отфильтрованные сообщения",
                    parse_mode='md'
                )
                logger.info(f"✅ Уведомлен вечный подписчик: {user_id}")
            except Exception as e:
                logger.error(f"❌ Не удалось уведомить {user_id}: {e}")
        
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
    finally:
        await client.disconnect()
        db_conn.close()
        logger.info("🔴 Бот остановлен")

if __name__ == '__main__':
    # Создаем необходимые файлы
    if not os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            pass
        logger.info("📁 Создан файл подписчиков")
    
    asyncio.run(main())
