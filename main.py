import asyncio
import sqlite3
import os
from datetime import datetime
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import logging
import hashlib
import re

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

# ===== БЕЗОПАСНОЕ ФОРМАТИРОВАНИЕ =====
def safe_format_message(sender_name, message_time, found_keywords, message_text):
    """Безопасное форматирование без Markdown"""
    
    # Очищаем текст от проблемных символов
    def clean_text(text):
        if not text:
            return ""
        # Удаляем Markdown символы
        text = re.sub(r'[*_`\[\]()]', '', text)
        # Обрезаем длинные тексты
        if len(text) > 1200:
            text = text[:1200] + "..."
        return text
    
    sender_name = clean_text(sender_name)
    keywords_str = clean_text(', '.join(found_keywords))
    message_text = clean_text(message_text)
    
    # Форматируем без Markdown
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
                "❌ НЕ НАЙДЕН ЧАТ!\n\n"
                "Добавь @Ezzlime в чат с новостями или отправь /chats для списка чатов"
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
                    logger.debug("⏭️ Сообщение уже обработано")
                    return
                
                # Анализируем сообщение
                found_keywords = []
                for keyword in KEYWORDS:
                    if keyword.lower() in message_text.lower():
                        found_keywords.append(keyword)
                
                if found_keywords:
                    logger.info(f"🎯 НАЙДЕНО: {len(found_keywords)} ключевых слов - {found_keywords}")
                    
                    moscow_tz = pytz.timezone('Europe/Moscow')
                    message_time = message.date.astimezone(moscow_tz).strftime('%H:%M %d.%m.%Y')
                    
                    # Используем безопасное форматирование
                    formatted_message = safe_format_message(
                        sender_name, 
                        message_time, 
                        found_keywords, 
                        message_text
                    )
                    
                    try:
                        # Отправляем без parse_mode
                        await bot_client.send_message(1175795428, formatted_message)
                        logger.info("✅ Уведомление отправлено!")
                        mark_message_processed(db_conn, message_hash, message_text, ", ".join(found_keywords))
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки: {e}")
                        
            except Exception as e:
                logger.error(f"💥 Ошибка обработки: {e}")
        
        # Команды
        @bot_client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.reply(
                "✅ NewsAnalyzer активен! Отслеживаю важные новости.\n\n"
                f"💬 Чат: {SOURCE_CHAT_ID}\n"
                f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
                f"👤 Аккаунт: @Ezzlime"
            )
        
        @bot_client.on(events.NewMessage(pattern='/chats'))
        async def chats_handler(event):
            chats_list = ["📋 ДОСТУПНЫЕ ЧАТЫ:\n"]
            async for dialog in user_client.iter_dialogs(limit=15):
                chats_list.append(f"💬 {dialog.name}: {dialog.id}")
            
            message = "\n".join(chats_list) if chats_list else "❌ Нет доступных чатов"
            await event.reply(message)
        
        @bot_client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            cursor = db_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM processed_messages")
            total = cursor.fetchone()[0]
            
            await event.reply(
                f"📊 СТАТУС:\n\n"
                f"✅ Активен\n"
                f"💬 Чат: {SOURCE_CHAT_ID}\n"
                f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
                f"📈 Обработано: {total}\n"
                f"👤 Аккаунт: @Ezzlime"
            )
        
        logger.info(f"🔄 НАЧИНАЮ МОНИТОРИНГ ЧАТА {SOURCE_CHAT_ID}...")
        
        # Тестовое уведомление
        await bot_client.send_message(
            1175795428,
            f"🟢 NewsAnalyzer запущен!\n\n"
            f"✅ Мониторю чат: {SOURCE_CHAT_ID}\n"
            f"🎯 Ключевых слов: {len(KEYWORDS)}\n"
            f"👤 Аккаунт: @Ezzlime\n\n"
            f"🔄 Начинаю мониторинг..."
        )
        
        await user_client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
    finally:
        await user_client.disconnect()
        await bot_client.disconnect()
        db_conn.close()

if __name__ == '__main__':
    asyncio.run(main())
