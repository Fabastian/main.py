import re
import sqlite3
import datetime
import requests
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import BufferedInputFile

# --- НАСТРОЙКИ ---
TOKEN = "8279771926:AAGkONdhOx8scqOIhtZLRezNKoGoQ5kFIgQ"
bot = Bot(token=TOKEN)
dp = Dispatcher()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
}

def get_schedule_for_date(group_num, target_date):
    url = "https://chernihivoblenergo.com.ua/blackouts"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        html = response.text
        # Берем дату в формате ДД.ММ
        short_date = target_date[:5] 
        if short_date not in html:
            return None
        pattern = rf"{group_num}.*?(\d{{2}}:\d{{2}}[-—]\d{{2}}:\d{{2}}(?:,\s*\d{{2}}:\d{{2}}[-—]\d{{2}}:\d{{2}})*)"
        match = re.search(pattern, html)
        if match:
            return match.group(1).strip()
        return "нет ограничений"
    except Exception:
        return "ошибка"

def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, group_num TEXT)")
    conn.commit()
    conn.close()

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Выбрать очередь", callback_data="set_group")
    kb.button(text="📅 График на сегодня", callback_data="view_today")
    kb.button(text="🕒 График на завтра", callback_data="view_tomorrow")
    kb.button(text="🖼 Картинка с сайта", callback_data="send_photo")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    await message.answer("💡 **Бот Світло Чернігів** запущен!\nВыбери свою очередь:", reply_markup=main_menu(), parse_mode="Markdown")

@dp.callback_query(F.data == "set_group")
async def set_group(call: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    for m in range(1, 7):
        for s in [1, 2]:
            g = f"{m}.{s}"
            kb.button(text=g, callback_data=f"save_{g}")
    kb.adjust(4)
    await call.message.edit_text("Выбери подгруппу:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("save_"))
async def save_group(call: types.CallbackQuery):
    group = call.data.split("_")[1]
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, group_num) VALUES (?, ?)", (call.from_user.id, group))
    conn.commit()
    conn.close()
    await call.message.edit_text(f"✅ Очередь {group} сохранена!", reply_markup=main_menu())

async def get_and_send_schedule(call, days_delta):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT group_num FROM users WHERE user_id = ?", (call.from_user.id,))
    res = cursor.fetchone()
    conn.close()
    if not res:
        await call.message.answer("⚠️ Сначала выбери очередь!")
        return
    group = res[0]
    target_dt = datetime.datetime.now() + datetime.timedelta(days=days_delta)
    date_str = target_dt.strftime("%d.%m.%Y")
    await call.answer(f"Загружаю {date_str}...")
    times = get_schedule_for_date(group, date_str)
    if times == "ошибка":
        msg = "❌ Ошибка связи с Облэнерго."
    elif times is None:
        msg = f"📭 На **{date_str}** графика еще нет на сайте."
    elif times == "нет ограничений":
        msg = f"✅ На **{date_str}** для группы {group} отключений не планируется."
    else:
        msg = f"📅 **График на {date_str}**\n👥 Группа: {group}\n\n"
        for t in times.split(','):
            msg += f"🛑 **Отключение: {t.strip()}**\n"
    await call.message.answer(msg, parse_mode="Markdown")

@dp.callback_query(F.data == "view_today")
async def view_today(call: types.CallbackQuery):
    await get_and_send_schedule(call, 0)

@dp.callback_query(F.data == "view_tomorrow")
async def view_tomorrow(call: types.CallbackQuery):
    await get_and_send_schedule(call, 1)

@dp.callback_query(F.data == "send_photo")
async def send_photo(call: types.CallbackQuery):
    img_url = "https://chernihivoblenergo.com.ua/files/other/schedule_groups.jpg"
    try:
        await call.answer("Загружаю фото...")
        resp = requests.get(img_url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            photo = BufferedInputFile(resp.content, filename="grafik.jpg")
            await call.message.answer_photo(photo, caption="📸 Актуальная картинка ГПВ")
    except Exception:
        await call.message.answer("⚠️ Не удалось загрузить картинку.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
