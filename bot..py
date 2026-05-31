import os
import time
import json
import re
import threading
import requests
import telebot

# НАСТРОЙКИ ПОДСТАВЛЕНЫ АВТОМАТИЧЕСКИ
BOT_TOKEN = "8500140489:AAHTWa2kEqCrVaMXeyxYT1_kX400x4W-KpI"
CHAT_ID = -1004209927131  # Верный ID вашей группы в Telegram
API_URL = "https://zachotkin.ru/api_telegram.php"
API_TOKEN = "secret_tg_token_9782423001"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
STATE_FILE = "state.json"
RESOLVED_CHAT_ID = None

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка чтения state.json: {e}")
    return {"last_order_id": 0, "last_message_id": 0}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Ошибка сохранения state.json: {e}")

# Функция умной отправки с автоподбором знака для группы
def send_smart_message(text):
    global RESOLVED_CHAT_ID
    if RESOLVED_CHAT_ID is not None:
        try:
            bot.send_message(RESOLVED_CHAT_ID, text)
            return
        except Exception as e:
            print(f"Ошибка отправки в сохраненный чат {RESOLVED_CHAT_ID}: {e}")
            RESOLVED_CHAT_ID = None
            
    chat_ids_to_try = [CHAT_ID]
    if CHAT_ID > 0:
        chat_ids_to_try.append(-CHAT_ID)
        chat_ids_to_try.append(int(f"-100{CHAT_ID}"))
        
    errors = []
    for cid in chat_ids_to_try:
        try:
            bot.send_message(cid, text)
            RESOLVED_CHAT_ID = cid
            print(f"Успешно отправлено в чат ID: {cid}")
            return
        except Exception as e:
            errors.append(f"Чат {cid}: {e}")
            
    print(f"Не удалось отправить сообщение. Ошибки: {'; '.join(errors)}")

# Фоновый опрос сайта
def poll_website():
    state = load_state()
    is_first_run = (state["last_order_id"] == 0 and state["last_message_id"] == 0)
    print("Запущен фоновый опрос сайта...")
    
    while True:
        try:
            params = {
                "token": API_TOKEN,
                "action": "get_updates",
                "last_order_id": state["last_order_id"],
                "last_message_id": state["last_message_id"]
            }
            response = requests.get(API_URL, params=params, timeout=10)
            data = response.json()
            
            if data.get("success"):
                orders = data.get("orders", [])
                messages = data.get("messages", [])
                
                if is_first_run:
                    if orders:
                        state["last_order_id"] = max(o["id"] for o in orders)
                    if messages:
                        state["last_message_id"] = max(m["id"] for m in messages)
                    save_state(state)
                    is_first_run = False
                    print(f"Инициализация завершена. Отслеживание с Заказа #{state['last_order_id']} и Сообщения #{state['last_message_id']}")
                    time.sleep(3)
                    continue
                
                for order in orders:
                    msg_text = f"🔥 <b>Новый заказ #{order['id']}!</b>\n\n"
                    msg_text += f"👤 <b>Имя:</b> {order['name']}\n"
                    msg_text += f"📚 <b>Тема:</b> {order['subject']}\n"
                    msg_text += f"📞 <b>Контакты:</b> {order['contact']}\n"
                    if order.get("comment"):
                        msg_text += f"💬 <b>Комментарий:</b> {order['comment']}\n"
                    if order.get("file_path"):
                        msg_text += f"\n📎 <b>Файл:</b> <a href='https://zachotkin.ru/{order['file_path']}'>Скачать файл задания</a>\n"
                    
                    send_smart_message(msg_text)
                    state["last_order_id"] = max(state["last_order_id"], order["id"])
                    save_state(state)
                    time.sleep(0.5)
                
                for msg in messages:
                    msg_text = f"💬 <b>[Заказ #{msg['order_id']}] Сообщение от клиента:</b>\n\n"
                    msg_text += f"{msg['message']}"
                    if msg.get("file_path"):
                        msg_text += f"\n\n📎 <b>Файл:</b> <a href='https://zachotkin.ru/{msg['file_path']}'>Скачать вложение</a>"
                    
                    send_smart_message(msg_text)
                    state["last_message_id"] = max(state["last_message_id"], msg["id"])
                    save_state(state)
                    time.sleep(0.5)
                    
        except Exception as e:
            print(f"Ошибка в цикле опроса: {e}")
            
        time.sleep(3)

# Обработка Reply-ответов менеджеров в Telegram
@bot.message_handler(func=lambda message: message.reply_to_message is not None)
def handle_reply(message):
    parent_msg = message.reply_to_message
    parent_text = parent_msg.text or parent_msg.caption or ""
    
    match = re.search(r'(?:\[Заказ #|Новый заказ #)(\d+)', parent_text)
    if not match:
        return
        
    order_id = int(match.group(1))
    reply_text = message.text or message.caption or ""
    files = {}
    
    try:
        if message.document:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            files = {"chat_file": (message.document.file_name, downloaded_file)}
        elif message.photo:
            photo = message.photo[-1]
            file_info = bot.get_file(photo.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            files = {"chat_file": ("photo.jpg", downloaded_file)}
            
        data = {
            "token": API_TOKEN,
            "action": "send_message",
            "order_id": order_id,
            "message": reply_text
        }
        
        response = requests.post(API_URL, data=data, files=files, timeout=15)
        res_json = response.json()
        
        if res_json.get("success"):
            bot.reply_to(message, "✅ Доставлено клиенту на сайт")
        else:
            bot.reply_to(message, f"❌ Ошибка отправки на сайт: {res_json.get('error')}")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при передаче сообщения: {e}")

if __name__ == "__main__":
    t = threading.Thread(target=poll_website, daemon=True)
    t.start()
    print("Бот успешно запущен в Telegram. Ожидаем сообщений...")
    bot.infinity_polling()
