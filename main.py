import asyncio
import sqlite3
import os
from datetime import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import logging
import hashlib

# ===== ТВОИ ДАННЫЕ =====
API_ID = 30519385
API_HASH = 'fa0fc5cd3b68e94c7ce1d9c4c984df9d'
SESSION_STRING = '1ApWapzMBuyYciqhblZyGuoTsE_AaOPzwhc1OwGU5LLFhSuUes1Haofveo_gpSCiWyq_ey4VligWxXfjbh6DEO2sqAB95zSmty6baD_f6AN-NxRDy390hyeMsSZ_A0JTLNjQ3Emp0jUcvFwgOT0UINw_3_qzNRxM-VdjJ89W8yxw9DEqMFaJ-xaOuPai9QXzQmLxisTo8UrTiS98vvIsPVBi8EXQt8r2BLBEZM_fzuZP56U1tiYjnRTsaVPK5gjEL_Z8Gg4RNfKK5axCewarHDS2GSAHTnUoSeB1tF0w_BbinN-8tcZK0zMGGKgAaeHX13MRdB9JOFOakOL57Y4WMf1eebUxGlEs='

BOT_TOKEN = '8573638786:AAGVbZBTb914ileFKmGXbWLUsIQzwo5gXi8'
SOURCE_CHAT_ID = 1003474109106

# Ключевые слова для фильтрации
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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('news_analyzer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('NewsAnalyzer')

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('news_analyzer.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_messages (
            message_hash TEXT PRIMARY KEY,
            message_text TEXT,
            keywords_found TEXT,
            processed_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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

# ===== ОСНОВНОЙ КОД =====
async def main():
    logger.info("🚀 ЗАПУСК NEWS ANALYZER...")
    
    # Инициализация базы данных
    db_conn = init_db()
    
    # User client для чтения сообщений из чата
    user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    
    # Bot client для отправки уведомлений
    bot_client = TelegramClient('bot_notifier', API_ID, API_HASH)
    
    try:
        # Запускаем user client
        await user_client.start()
        logger.info("✅ User client запущен")
        
        # Запускаем bot client
        await bot_client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Bot client запущен")
        
        # Получаем информацию об аккаунте
        me = await user_client.get_me()
        logger.info(f"👤 Аккаунт: {me.first_name} (@{me.username or 'no username'})")
        
        # Проверяем доступ к чату
        try:
            chat = await user_client.get_entity(SOURCE_CHAT_ID)
            logger.info(f"✅ Доступ к чату: {chat.title if hasattr(chat, 'title') else 'Unknown'}")
        except Exception as e:
            logger.error(f"❌ Нет доступа к чату {SOURCE_CHAT_ID}: {e}")
            logger.info("💡 Добавь этот аккаунт в чат как участника!")
            return
        
        # Обработчик новых сообщений в чате
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
                
                # Проверяем дубликаты
                message_hash = generate_message_hash(message_text)
                if is_message_processed(db_conn, message_hash):
                    logger.debug("⏭️ Сообщение уже обработано")
                    return
                
                # Анализируем сообщение на ключевые слова
                found_keywords = []
                for keyword in KEYWORDS:
                    if keyword.lower() in message_text.lower():
                        found_keywords.append(keyword)
                
                if found_keywords:
                    logger.info(f"🎯 НАЙДЕНО КЛЮЧЕВЫХ СЛОВ: {len(found_keywords)} - {found_keywords}")
                    
                    # Форматируем время
                    moscow_tz = pytz.timezone('Europe/Moscow')
                    message_time = message.date.astimezone(moscow_tz).strftime('%H:%M %d.%m.%Y')
                    
                    # Создаем красивое сообщение
                    formatted_message = (
                        f"🔍 **ВАЖНАЯ НОВОСТЬ**\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🤖 **Источник:** {sender_name}\n"
                        f"🕒 **Время:** {message_time}\n"
                        f"🎯 **Ключевые слова:** {', '.join(found_keywords)}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📝 **Сообщение:**\n{message_text}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"*Отфильтровано NewsAnalyzer*"
                    )
                    
                    # Отправляем уведомление
                    try:
                        await bot_client.send_message(
                            1175795428,  # Твой ID
                            formatted_message, 
                            parse_mode='md',
                            link_preview=False
                        )
                        logger.info(f"✅ Уведомление отправлено!")
                        
                        # Помечаем как обработанное
                        mark_message_processed(db_conn, message_hash, message_text, ", ".join(found_keywords))
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки уведомления: {e}")
                
                else:
                    logger.debug("⏭️ Ключевые слова не найдены")
                    
            except Exception as e:
                logger.error(f"💥 Ошибка обработки сообщения: {e}")
        
        # Команды для бота
        @bot_client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.reply(
                "🔍 **NewsAnalyzer активен!**\n\n"
                f"💬 Мониторим чат: {SOURCE_CHAT_ID}\n"
                f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
                f"✅ Получаешь важные новости\n\n"
                "✨ Команды:\n"
                "/status - статус системы\n"
                "/stats - статистика"
            )
        
        @bot_client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            await event.reply(
                f"📊 **СТАТУС СИСТЕМЫ:**\n\n"
                f"✅ User client: работает\n"
                f"✅ Bot client: работает\n"
                f"💬 Чат: {SOURCE_CHAT_ID}\n"
                f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
                f"🔧 Все системы в норме"
            )
        
        @bot_client.on(events.NewMessage(pattern='/stats'))
        async def stats_handler(event):
            cursor = db_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM processed_messages")
            total = cursor.fetchone()[0]
            
            await event.reply(
                f"📈 **СТАТИСТИКА:**\n\n"
                f"📊 Обработано сообщений: {total}\n"
                f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
                f"💬 Мониторим чат: {SOURCE_CHAT_ID}"
            )
        
        logger.info("🔄 НАЧИНАЮ МОНИТОРИНГ ЧАТА...")
        logger.info(f"🎯 Отслеживаю {len(KEYWORDS)} ключевых слов")
        
        # Отправляем тестовое уведомление
        try:
            await bot_client.send_message(
                1175795428,
                "🟢 **NewsAnalyzer запущен!**\n\n"
                f"✅ Начинаю мониторинг чата: {SOURCE_CHAT_ID}\n"
                f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
                f"⏰ {datetime.now().strftime('%H:%M %d.%m.%Y')}",
                parse_mode='md'
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить тестовое уведомление: {e}")
        
        # Запускаем мониторинг
        await user_client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
    finally:
        await user_client.disconnect()
        await bot_client.disconnect()
        db_conn.close()

if __name__ == '__main__':
    asyncio.run(main())
