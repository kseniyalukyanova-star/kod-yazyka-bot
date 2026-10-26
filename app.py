"""
«Код Языка» — Telegram-бот (MVP-прототип)
Автор и разработчик: Ксения Лукьянова, Белорусско-Российский университет (БРУ)
Стек: Python 3.10+, aiogram 3.x, asyncio. Состояние — в памяти (без БД).

Запуск локально:   BOT_TOKEN=8762493511:AAFdCvra6-exUZVH8i_WOzs0wPu2jcRDmwg python app.py
Render/Railway:    Start command `python app.py` (переменная BOT_TOKEN обязательна).
                   Если задан PORT, поднимается мини-HTTP-сервер для health-check.
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

# ----------------------------- Данные (in-memory) -----------------------------

EXAMS = {"ege": "🇷🇺 ЕГЭ", "ct": "🇧🇾 ЦТ / ЦЭ", "ent": "🇰🇿 ЕНТ"}

# Демо-значения для презентации (совпадают со слайдами проекта)
START_XP, XP_REWARD, XP_LEVEL_CAP = 400, 50, 1000
STREAK_DAYS, LEVEL_TITLE, ACCURACY = 14, "Подмастерье", 90

TOPICS = {
    "spell": {
        "title": "✍️ Орфография (Приставки ПРЕ/ПРИ)",
        "lesson": (
            "📘 <b>УРОК: ОРФОГРАФИЯ</b>\n<i>Правописание приставок ПРЕ- и ПРИ-</i>\n\n"
            "<b>Правило</b>\n"
            "• <b>ПРИ-</b> — приближение, присоединение, неполнота действия "
            "(<i>приплыть, приклеить, приоткрыть</i>).\n"
            "• <b>ПРЕ-</b> — высшая степень качества (<i>превосходный, прекрасный</i>) "
            "или близко к «пере-» (<i>преобразовать</i>).\n\n"
            "🔑 <b>Лайфхак для запоминания</b>\n"
            "• <b>ПРЕ-</b> = «очень» → ПРЕмудрый — очень мудрый.\n"
            "• <b>ПРИ-</b> = «рядом» → ПРИбрежный — рядом с берегом."
        ),
        "task": "Лодка <b>пр…</b>плыла к берегу.\n\nКакую приставку нужно написать?",
        "options": ["ПРЕ-", "ПРИ-"],
        "correct": 1,
        "algo": (
            "1. Определи значение приставки: приближение к берегу.\n"
            "2. Приближение → <b>ПРИ-</b> («рядом»). Верно: «приплыла»."
        ),
        "task_title": "ЗАДАНИЕ: ПРЕ / ПРИ",
    },
    "punct": {
        "title": "🪧 Пунктуация (Задание №12)",
        "lesson": (
            "📘 <b>УРОК: ПУНКТУАЦИЯ</b>\n<i>Однородные сказуемые и общий второстепенный член</i>\n\n"
            "<b>Правило</b>\n"
            "Если в предложении есть <b>общий второстепенный член</b> "
            "(относится сразу к обеим частям), то он связывает части в единое целое — "
            "запятая перед «и» <b>не ставится</b>.\n\n"
            "🔑 <b>Лайфхак</b>\n"
            "Нашёл слово, которое «обслуживает» обе части сразу, — запятую не ставь. "
            "Например: «<u>Утром</u> светило солнце и пели птицы»."
        ),
        "task": "Утром светило солнце &lt;?&gt; и пели птицы.\n\nСтавить ли запятую?",
        "options": ["🔴 Поставить запятую", "🔵 Не ставить запятую"],
        "correct": 1,
        "algo": (
            "1. Найди грамматические основы: «светило солнце» и «пели птицы».\n"
            "2. Проверь на общий второстепенный член: «Утром» относится к обеим частям.\n"
            "   ✅ ЕСТЬ общий член → запятая НЕ нужна."
        ),
        "task_title": "ЗАДАНИЕ №12",
    },
}

# Профили пользователей: {user_id: {"exam": str|None, "xp": int}}
USERS: dict[int, dict] = {}


def user(uid: int) -> dict:
    return USERS.setdefault(uid, {"exam": None, "xp": START_XP})


# ------------------------------- Клавиатуры -----------------------------------

def kb_exams() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, name in EXAMS.items():
        b.button(text=name, callback_data=f"exam:{key}")
    b.button(text="🎓 О проекте и методике", callback_data="about")
    b.adjust(3, 1)
    return b.as_markup()


def kb_topics() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, t in TOPICS.items():
        b.button(text=t["title"], callback_data=f"lesson:{key}")
    b.button(text="🎓 О проекте и методике", callback_data="about")
    b.button(text="🔁 Сменить экзамен", callback_data="start")
    b.adjust(1)
    return b.as_markup()


def kb_single(text: str, data: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=text, callback_data=data)
    return b.as_markup()


def kb_task(topic: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, label in enumerate(TOPICS[topic]["options"]):
        b.button(text=label, callback_data=f"ans:{topic}:{i}")
    b.adjust(2)
    return b.as_markup()


def kb_fail(topic: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Повторить попытку", callback_data=f"task:{topic}")
    b.button(text="📚 К выбору тем", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


# ------------------------------- Тексты ---------------------------------------

WELCOME = (
    "👋 Привет! Я — <b>«Код Языка»</b>, твой персональный алгоритм сдачи экзаменов "
    "по русскому языку: ЕГЭ, ЦТ/ЦЭ и ЕНТ.\n\n"
    "Проект создала <b>Ксения Лукьянова</b> (Белорусско-Российский университет, БРУ) "
    "для международного кейс-чемпионата «Русский язык. Территория инноваций».\n\n"
    "Мы не зубрим правила, а учимся находить закономерности: мнемоника, "
    "алгоритмы решения, мгновенный разбор ошибок и игровая мотивация.\n\n"
    "👇 <b>Выбери свой экзамен:</b>"
)

ABOUT = (
    "🎓 <b>О проекте и методике</b>\n\n"
    "«Код Языка» разработан на базе <b>Белорусско-Российского университета (БРУ, г. Могилёв)</b> "
    "в рамках международного кейс-чемпионата. Автор: Ксения Лукьянова, "
    "специальность «Программная инженерия».\n\n"
    "<b>Методические основы:</b>\n"
    "• <b>Адаптивное обучение</b> — стартовая диагностика и фокус на слабых зонах;\n"
    "• <b>Когнитивные стратегии</b> — мнемоника и ассоциации вместо зубрёжки;\n"
    "• <b>Микрообучение</b> — теория короткими «конспектами-шпаргалками»;\n"
    "• <b>Интервальное повторение</b> — кривая забывания Эббингауза;\n"
    "• <b>Компетентностный подход</b> — алгоритмы и поиск паттернов в заданиях.\n\n"
    "<i>Это прототип: в полном продукте — мобильное приложение на Flutter (iOS/Android) "
    "с офлайн-режимом и админ-панелью для методистов.</i>"
)


# ------------------------------- Хелперы --------------------------------------

async def show(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    """Редактируем текущее сообщение (чат остаётся чистым); при ошибке — шлём новое."""
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


def topics_text(uid: int) -> str:
    exam = EXAMS.get(user(uid)["exam"] or "", "—")
    return f"Экзамен: <b>{exam}</b>\n\n📚 <b>Каталог тем</b>\nВыбери раздел для тренировки:"


# ------------------------------- Хендлеры -------------------------------------

@router.message(CommandStart())
async def cmd_start(m: Message) -> None:
    user(m.from_user.id)
    await m.answer(WELCOME, reply_markup=kb_exams())


@router.message(Command("menu"))
async def cmd_menu(m: Message) -> None:
    await m.answer(topics_text(m.from_user.id), reply_markup=kb_topics())


@router.callback_query(F.data == "start")
async def cb_start(cb: CallbackQuery) -> None:
    await show(cb, WELCOME, kb_exams())


@router.callback_query(F.data == "about")
async def cb_about(cb: CallbackQuery) -> None:
    await show(cb, ABOUT, kb_single("⬅️ Назад", "menu" if user(cb.from_user.id)["exam"] else "start"))


@router.callback_query(F.data.startswith("exam:"))
async def cb_exam(cb: CallbackQuery) -> None:
    user(cb.from_user.id)["exam"] = cb.data.split(":")[1]
    await show(cb, topics_text(cb.from_user.id), kb_topics())


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery) -> None:
    await show(cb, topics_text(cb.from_user.id), kb_topics())


@router.callback_query(F.data.startswith("lesson:"))
async def cb_lesson(cb: CallbackQuery) -> None:
    topic = cb.data.split(":")[1]
    await show(cb, TOPICS[topic]["lesson"], kb_single("🚀 Начать тренировку", f"task:{topic}"))


@router.callback_query(F.data.startswith("task:"))
async def cb_task(cb: CallbackQuery) -> None:
    topic = cb.data.split(":")[1]
    t = TOPICS[topic]
    await show(cb, f"📝 <b>{t['task_title']}</b>\n\n{t['task']}", kb_task(topic))


@router.callback_query(F.data.startswith("ans:"))
async def cb_answer(cb: CallbackQuery) -> None:
    _, topic, idx = cb.data.split(":")
    t, u = TOPICS[topic], user(cb.from_user.id)

    if int(idx) != t["correct"]:
        # Неверный ответ: разбор ошибки по алгоритму + повтор
        text = (
            "❌ <b>РАЗБОР ОШИБКИ</b>\n\n"
            f"Ты выбрал: <i>{t['options'][int(idx)]}</i> — это неверно.\n\n"
            f"🧩 <b>Алгоритм решения:</b>\n{t['algo']}\n\n"
            "Вспомни алгоритм и попробуй ещё раз!"
        )
        await show(cb, text, kb_fail(topic))
        return

    # Верный ответ: награда и геймификация
    u["xp"] += XP_REWARD
    text = (
        "🌟 <b>УРОК ОКОНЧЕН — УРОВЕНЬ ЗАВЕРШЁН!</b>\n\n"
        f"✅ Верно! Правильный ответ: <b>{t['options'][t['correct']]}</b>\n\n"
        f"🧩 <b>Алгоритм:</b>\n{t['algo']}\n\n"
        "🏆 <b>Твоя награда</b>\n"
        f"• +{XP_REWARD} очков опыта (всего: {u['xp']}/{XP_LEVEL_CAP})\n"
        f"• 🔥 Ударный режим: {STREAK_DAYS} дней подряд\n"
        f"• 🎖 Уровень: {LEVEL_TITLE}\n"
        f"• 🎯 Точность: {ACCURACY}%\n\n"
        "Продолжай в том же духе, Мастер!"
    )
    await show(cb, text, kb_single("📚 К выбору тем", "menu"))


# ------------------------------- Запуск ---------------------------------------

async def health_server() -> None:
    """Мини-HTTP-сервер: Render/Railway требуют открытый порт у web-сервиса."""
    port = os.getenv("PORT")
    if not port:
        return
    from aiohttp import web  # aiohttp ставится вместе с aiogram

    async def ok(_):
        return web.Response(text="Код Языка: OK")

    app = web.Application()
    app.router.add_get("/", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(port)).start()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Задайте переменную окружения BOT_TOKEN (токен от @BotFather).")

    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    await health_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
