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

# Пробуем разные варианты ID чата
POSSIBLE_CHAT_IDS = [
    1003474109106,  # Оригинальный ID
    -1003474109106, # Возможно с минусом
]

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('NewsAnalyzer')

# ===== ПОИСК ЧАТА =====
async def find_target_chat(client):
    """Находит чат с новостями автоматически"""
    logger.info("🔍 Ищу чат с новостями...")
    
    target_chat = None
    
    async for dialog in client.iter_dialogs():
        # Ищем по ключевым словам в названии
        if any(keyword in dialog.name.lower() for keyword in ['новост', 'парсер', 'канал', 'news']):
            logger.info(f"🎯 НАЙДЕН ЧАТ: {dialog.name} -> {dialog.id}")
            target_chat = dialog
            break
        
        # Или проверяем известные ID
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
            
            # Показываем все доступные чаты
            logger.info("📋 Доступные чаты:")
            async for dialog in user_client.iter_dialogs(limit=10):
                logger.info(f"   💬 {dialog.name} -> {dialog.id}")
            
            await bot_client.send_message(
                1175795428,
                "❌ **НЕ НАЙДЕН ЧАТ!**\n\n"
                "Добавь @Ezzlime в чат с новостями или отправь /chats для списка чатов",
                parse_mode='md'
            )
            return
        
        # Обработчик сообщений
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
                    return
                
                # Анализируем сообщение
                found_keywords = []
                for keyword in KEYWORDS:
                    if keyword.lower() in message_text.lower():
                        found_keywords.append(keyword)
                
                if found_keywords:
                    logger.info(f"🎯 НАЙДЕНО: {len(found_keywords)} ключевых слов")
                    
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
                        f"*Отфильтровано NewsAnalyzer*"
                    )
                    
                    try:
                        await bot_client.send_message(1175795428, formatted_message, parse_mode='md')
                        logger.info("✅ Уведомление отправлено!")
                        mark_message_processed(db_conn, message_hash, message_text, ", ".join(found_keywords))
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки: {e}")
                        
            except Exception as e:
                logger.error(f"💥 Ошибка обработки: {e}")
        
        # Команды
        @bot_client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.reply("✅ NewsAnalyzer активен! Отслеживаю важные новости.")
        
        @bot_client.on(events.NewMessage(pattern='/chats'))
        async def chats_handler(event):
            chats_list = []
            async for dialog in user_client.iter_dialogs(limit=15):
                chats_list.append(f"💬 {dialog.name}: `{dialog.id}`")
            
            await event.reply("\n".join(chats_list) if chats_list else "❌ Нет доступных чатов")
        
        @bot_client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            await event.reply(f"✅ Активен! Мониторю чат: {SOURCE_CHAT_ID}")
        
        logger.info(f"🔄 НАЧИНАЮ МОНИТОРИНГ ЧАТА {SOURCE_CHAT_ID}...")
        
        await bot_client.send_message(
            1175795428,
            f"🟢 **NewsAnalyzer запущен!**\n\n"
            f"✅ Мониторю чат: {SOURCE_CHAT_ID}\n"
            f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
            f"👤 Аккаунт: @Ezzlime",
            parse_mode='md'
        )
        
        await user_client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"💥 Ошибка: {e}")
    finally:
        await user_client.disconnect()
        await bot_client.disconnect()
        db_conn.close()

if __name__ == '__main__':
    asyncio.run(main())
