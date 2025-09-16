import os
import asyncpg
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
import logging

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
APP_URL = os.getenv("APP_URL")  # https://your-service.onrender.com
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- база данных ---
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        tg_id BIGINT PRIMARY KEY,
        phone TEXT,
        lat DOUBLE PRECISION,
        lon DOUBLE PRECISION
    )
    """)
    await conn.close()

async def save_user(tg_id, phone, lat, lon):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
    INSERT INTO users (tg_id, phone, lat, lon)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (tg_id) DO UPDATE SET phone=$2, lat=$3, lon=$4
    """, tg_id, phone, lat, lon)
    await conn.close()

# --- роут регистрации ---
@app.post("/register")
async def register(request: Request):
    data = await request.json()
    tg_id = int(data.get("tg_id"))
    phone = data.get("phone")
    lat = data.get("lat")
    lon = data.get("lon")

    await save_user(tg_id, phone, lat, lon)

    await bot.send_message(
        ADMIN_ID,
        f"🔔 Новый пользователь/обновление:\n"
        f"👤 TG_ID: {tg_id}\n📱 Телефон: {phone}\n🌍 Место: {lat}, {lon}"
    )

    await bot.send_message(tg_id, "✅ Вы успешно зарегистрированы!")

    return {"ok": True}

# --- хендлер бота ---
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    web_btn = InlineKeyboardButton(
        "Регистрация",
        url=f"{APP_URL}/static/gateway.html?tg_id={message.from_user.id}"
    )
    keyboard.add(web_btn)
    await message.answer("Привет! Чтобы продолжить, пройди регистрацию:", reply_markup=keyboard)

# --- запуск ---
from aiohttp import web

async def on_startup(app):
    await init_db()
    webhook_url = f"{APP_URL}/webhook"
    await bot.set_webhook(webhook_url)

async def on_shutdown(app):
    await bot.session.close()

app_router = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app_router, path="/webhook")
setup_application(app_router, dp, bot=bot)
app.mount("", app_router)

app.add_event_handler("startup", on_startup)
app.add_event_handler("shutdown", on_shutdown)
