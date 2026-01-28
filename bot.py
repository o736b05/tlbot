import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ========== НАСТРОЙКА СРЕДЫ ==========
IS_PRODUCTION = os.getenv('PYTHONANYWHERE_SITE') is not None or os.getenv('RAILWAY_ENVIRONMENT') == 'production'

log_level = logging.INFO if IS_PRODUCTION else logging.DEBUG
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level
)
logger = logging.getLogger(__name__)

# ========== ПОЛУЧЕНИЕ ТОКЕНА ==========
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TOKEN:
    if IS_PRODUCTION:
        logger.error("❌ Токен не найден!")
        logger.error("📝 Добавьте TELEGRAM_BOT_TOKEN в настройках хостинга")
        exit(1)
    else:
        TOKEN = ""

logger.info(f"✅ Режим: {'ПРОДАКШЕН' if IS_PRODUCTION else 'ЛОКАЛЬНЫЙ'} ")

# ========== КОНСТАНТЫ БОТА ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Обновленные данные для видео с вашим текстом
VIDEOS = {
    1: {
        'file_path': os.path.join(BASE_DIR, 'video1.mp4'),
        'url': 'https://disk.yandex.ru/d/eO0ffJFFLev1YA',  # Замените на реальную ссылку
        'text_before': """если у тебя не загружается урок — его можно 
открыть по ссылке: https://disk.yandex.ru/d/eO0ffJFFLev1YA

урок 1. Основы Photoshop

скачать фотошоп (https://t.me/+v_vSoBd1p6o4NjUy)

Обещанный подарок
⠀
Пак шрифтов, которым я делюсь на своем полноценном обучении.
⠀
1. подпишись на меня в инсте instagram.com/brezdenuk_/

2/ выложи свой список желаний <b>с отметкой меня</b> и любым отзывом в сторис

3/ напиши мне в личку тг 

вот ссылка на инсту ↓
instagram.com/brezdenuk_/
<a>https://t.me/brezdenuk</a>""",
        'conclusions': '📌 Отлично! Первый урок пройден!'
    },
    2: {
        'file_path': os.path.join(BASE_DIR, 'video2.mp4'),
        'url': 'https://disk.yandex.ru/d/eO0ffJFFLev1YA',  # Замените на реальную ссылку
        'text_before': """если у тебя не загружается урок — его можно 
открыть по ссылке: https://disk.yandex.ru/d/eO0ffJFFLev1YA

урок 2. Создаем карточку для WB

Все материалы к уроку (https://t.me/+v_vSoBd1p6o4NjUy)

(повторяйте карточку за мной)""",
        'conclusions': '📌 Отлично! Второй урок пройден!'
    },
    3: {
        'file_path': os.path.join(BASE_DIR, 'video3.mp4'),
        'url': 'https://disk.yandex.ru/d/eO0ffJFFLev1YA',  # Замените на реальную ссылку
        'text_before': """если у тебя не загружается урок — его можно 
открыть по ссылке: https://disk.yandex.ru/d/eO0ffJFFLev1YA

урок 3. Как найти клиентов и начать зарабатывать.

В конце видео отдам подарок""",
        'conclusions': '📌 Все уроки пройдены!'
    }
}

FINAL_VIDEO = {
    'file_path': os.path.join(BASE_DIR, 'final_video.mp4'),
    'url': 'https://disk.yandex.ru/d/eO0ffJFFLev1YA',  # Замените на реальную ссылку
    'caption': '🎯 Видео-сообщение от автора курса'
}

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_states = {}
active_timers = {}
shutting_down = False


# ========== НОВАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ СООБЩЕНИЯ ПОСЛЕ 21 ЧАСА ==========
async def send_discount_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Отправляет сообщение о скидке через 21 час"""
    message_text = (
        "<b><u>У тебя осталось 3 часа до конца скидки</u></b>\n\n"
        "<a href='https://t.me/Alexander_brez'>Занять место по выгодной цене:</a>\n"
        "<a href='https://t.me/Alexander_brez'>Занять место</a>\n"
        "t.me/brezdenuk"
    )

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        logger.info(f"Сообщение о скидке отправлено пользователю {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения о скидке: {e}")


async def cleanup_user(user_id):
    """Очистка данных пользователя, но только если нет активных таймеров"""
    # Проверяем, есть ли активные таймеры
    has_active_timers = False
    if user_id in active_timers:
        for timer in active_timers[user_id]:
            if not timer.done():
                has_active_timers = True
                break

    # Если есть активные таймеры, не удаляем пользователя полностью
    if has_active_timers:
        # Просто отмечаем как завершенного, но оставляем данные
        if user_id in user_states:
            user_states[user_id]['cleanup_pending'] = True
        logger.info(f"Пользователь {user_id} имеет активные таймеры, откладываем очистку")
    else:
        # Если таймеров нет, удаляем полностью
        if user_id in active_timers:
            active_timers.pop(user_id, None)
        if user_id in user_states:
            user_states.pop(user_id, None)
        logger.info(f"Данные пользователя {user_id} полностью очищены")


# Добавляем новую функцию для проверки и удаления старых пользователей
async def cleanup_completed_users():
    """Периодически очищает данные завершенных пользователей"""
    while not shutting_down:
        await asyncio.sleep(300)  # Проверяем каждые 5 минут

        current_time = datetime.now()
        users_to_remove = []

        for user_id, user_data in user_states.items():
            if user_data.get('completed', False):
                # Проверяем, был ли отправлен discount_reminder
                reminder_time = user_data.get('discount_reminder_time')

                if reminder_time:
                    # Если таймер скидки прошел (21 час + 1 час на всякий случай)
                    if current_time > reminder_time + timedelta(hours=1):
                        # Проверяем активные таймеры
                        has_active_timers = False
                        if user_id in active_timers:
                            for timer in active_timers[user_id]:
                                if not timer.done():
                                    has_active_timers = True
                                    break

                        if not has_active_timers:
                            users_to_remove.append(user_id)

        # Удаляем старых пользователей
        for user_id in users_to_remove:
            if user_id in active_timers:
                active_timers.pop(user_id, None)
            if user_id in user_states:
                user_states.pop(user_id, None)
            logger.info(f"Автоматически очищены данные пользователя {user_id}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    if shutting_down:
        return

    user = update.effective_user
    user_id = user.id

    await cleanup_user(user_id)

    user_states[user_id] = {
        'current_video': 1,
        'chat_id': update.message.chat_id,
        'start_time': datetime.now()
    }
    active_timers[user_id] = []

    # Ваше первое сообщение без изменений
    await update.message.reply_text(
        """<b>привет!</b> искренне рад тебя видеть на моем мини-курсе

За 3 видео, ты узнаешь:

1. Основы дизайна, как скачать и работать в Photoshop

2. Сделаешь дизайн своего списка желаний

3. Создашь карточку товара для WB

4. Разберешься как искать клиентов и зарабатывать

<b>Я разработал лучший способ поиска заказов, мои ученики уже применили его и зарабатывают.</b>

Для тебя это точно будет полезный навык""",
        parse_mode="HTML"
    )

    # Небольшая пауза перед отправкой первого видео
    await asyncio.sleep(1)
    await send_video(user_id, 1, context)


async def send_video(user_id, video_num, context):
    """Отправляет видео и кнопку"""
    if user_id not in user_states or shutting_down:
        return

    chat_id = user_states[user_id]['chat_id']
    video_data = VIDEOS[video_num]

    # 2. Отправляем само видео (ссылка или файл)
    try:
        if os.path.exists(video_data['file_path']):
            # Пытаемся отправить файлом
            with open(video_data['file_path'], 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    supports_streaming=False,
                    disable_notification=True
                )
                logger.info(f"Видео {video_num} отправлено файлом")
        else:
            # Если файла нет - отправляем ссылку
            raise FileNotFoundError
            # 1. Отправляем текстовое сообщение перед видео
        await context.bot.send_message(
            chat_id=chat_id,
            text=video_data['text_before'],
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except (FileNotFoundError, Exception) as e:
        # Отправляем ссылку на YouTube
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📺 Смотрите видео по ссылке:\n{video_data['url']}",
            parse_mode='HTML',
            disable_web_page_preview=False
        )
        logger.info(f"Отправлена ссылка на видео {video_num}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=video_data['text_before'],
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    # 3. Отправляем кнопку подтверждения
    if video_num < 3:
        keyboard = [[
            InlineKeyboardButton(
                f"✅ Я посмотрел видео {video_num}",
                callback_data=f'watched_{video_num}'
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        button_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="После просмотра видео нажмите кнопку ниже:",
            reply_markup=reply_markup
        )
        user_states[user_id][f'button_msg_{video_num}'] = button_msg.message_id

        # 4. Запускаем таймер авто-продолжения (только для видео 1 и 2)
        if not shutting_down:
            # Отменяем предыдущий таймер, если есть
            timer_key = f'timer_{video_num}'
            if timer_key in user_states[user_id]:
                old_timer = user_states[user_id][timer_key]
                if old_timer and not old_timer.done():
                    old_timer.cancel()

            # Создаем новый таймер
            timer = asyncio.create_task(
                auto_next_video(user_id, video_num, context)
            )
            active_timers[user_id].append(timer)
            user_states[user_id][timer_key] = timer
    else:
        # Для третьего видео - сразу запускаем таймер для финального сообщения
        await asyncio.sleep(3)  # Пауза 3 секунды после отправки 3го видео
        await send_final_video(user_id, context)


async def auto_next_video(user_id, current_video_num, context):
    """Автоматически переходит к следующему видео через 10 минут"""
    try:
        # На продакшене: 600 секунд (10 минут), на локальном: 30 секунд для теста
        wait_time = 600 if IS_PRODUCTION else 30
        await asyncio.sleep(wait_time)

        if (shutting_down or
                user_id not in user_states or
                user_states[user_id].get('current_video') != current_video_num):
            return

        # Обновляем состояние
        user_states[user_id]['current_video'] = current_video_num + 1

        # Редактируем сообщение с кнопкой
        if f'button_msg_{current_video_num}' in user_states[user_id]:
            try:
                await context.bot.edit_message_text(
                    chat_id=user_states[user_id]['chat_id'],
                    message_id=user_states[user_id][f'button_msg_{current_video_num}'],
                    text="⏰ Уже посмотрел урок? Отправляю следующий..."
                )
            except Exception as e:
                logger.error(f"Ошибка при редактировании сообщения: {e}")

        # Удаляем таймер
        user_states[user_id].pop(f'timer_{current_video_num}', None)

        # Отправляем выводы по уроку
        await context.bot.send_message(
            chat_id=user_states[user_id]['chat_id'],
            text=VIDEOS[current_video_num]['conclusions'],
            parse_mode='HTML'
        )

        # Пауза и отправка следующего видео
        await asyncio.sleep(2)
        if current_video_num < 3:
            await send_video(user_id, current_video_num + 1, context)

    except asyncio.CancelledError:
        logger.info(f"Таймер отменен")
    except Exception as e:
        logger.error(f"Ошибка в auto_next_video: {e}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    if shutting_down:
        return

    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data.startswith('watched_'):
        video_num = int(data.split('_')[1])

        if user_id not in user_states:
            await query.message.reply_text("Пожалуйста, начните с команды /start")
            return

        # Отменяем таймер для этого видео (только для видео 1 и 2)
        if video_num < 3:
            timer_key = f'timer_{video_num}'
            if timer_key in user_states[user_id]:
                timer = user_states[user_id][timer_key]
                if not timer.done():
                    timer.cancel()
                user_states[user_id].pop(timer_key, None)

        # Обновляем состояние
        user_states[user_id]['current_video'] = video_num + 1

        # Редактируем сообщение с кнопкой
        try:
            await query.edit_message_text(
                text="✅ Вы подтвердили просмотр видео!"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании кнопки: {e}")

        # Отправляем выводы по уроку
        await query.message.reply_text(
            VIDEOS[video_num]['conclusions'],
            parse_mode='HTML'
        )

        # Пауза и отправка следующего видео
        await asyncio.sleep(1)

        if video_num < 2:
            await send_video(user_id, video_num + 1, context)
        elif video_num == 2:
            # Для второго видео сразу отправляем третье видео
            await send_video(user_id, 3, context)


async def send_final_video(user_id, context):
    """Отправляет финальное видео (без изменений)"""
    if user_id not in user_states:
        return

    chat_id = user_states[user_id]['chat_id']

    await context.bot.send_message(
        chat_id=chat_id,
        text="🎉 **Поздравляю! Вы завершили все видео-уроки!**\n\n"
             "Теперь вас ждёт специальное видео-сообщение от автора.",
        parse_mode='Markdown'
    )

    video_sent = False

    if os.path.exists(FINAL_VIDEO['file_path']):
        try:
            # Пробуем отправить как Video Note (кружок)
            try:
                with open(FINAL_VIDEO['file_path'], 'rb') as video_file:
                    await context.bot.send_video_note(
                        chat_id=chat_id,
                        video_note=video_file,
                        duration=38,
                        length=640
                    )
                    video_sent = True

            except Exception as note_error:
                logger.warning(f"Не удалось отправить как Video Note: {note_error}")

                with open(FINAL_VIDEO['file_path'], 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        supports_streaming=False
                    )
                    video_sent = True

        except Exception as e:
            logger.error(f"Ошибка при отправке финального видео: {e}")
            video_sent = False

    if not video_sent:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{FINAL_VIDEO['url']}\n\n",
            disable_web_page_preview=False
        )
    await asyncio.sleep(2)
    await context.bot.send_message(
        chat_id=chat_id,
        text="<b>Поздравляю</b> тебя <b>с прохождением</b> Миникурса!\n\n"
"Ты проделал(а) классную работу!\n"
"Надеюсь теперь, ты полюбил(а) дизайн также сильно, как и я\n\n"
"Буду искренне рад видеть тебя на своем предобучение -\n\n"
"предобучение - это часть моего <b>основного курса</b>,\n" 
"где в течении 5 дней ты сможешь побыть на нем в роли студента\n\n"
"Что ты получишь:\n\n"
"<b>+ 20 актульных способов поиска клиентов</b>\n"
"- Освоешь первостепенные навыки дизайна\n"
"- Научишься работать в Photoshop\n"
"- Cделашь первые качественные карточки\n"
"- Получишь от меня обратную связь на все вопросы\n\n\n"
"<b><u>Те кто прошел миникурс могут занять место на предобучении со\n"
"СКИДКОЙ 50% на 24 ЧАСА</u></b>\n\n"
"↓ ↓ ↓ ↓\n"
"https://t.me/Alexander_brez\n"
"https://t.me/Alexander_brez\n"
"https://t.me/Alexander_brez\n\n"
"напиши мне: 'дизайн' - и я покажу всю программу предобучения\n"
"Telegram (https://t.me/Alexander_brez)\n"
"Брезденюк | Дизайнер\n"
"Канал про дизайн: https://t.me/brezdenuk", parse_mode="HTML",
        disable_web_page_preview=True
    )

    user_states[user_id]['completed'] = True

    # Устанавливаем таймер для отправки напоминания о скидке через 21 час
    if not user_states[user_id].get('discount_timer_set', False):
        # Рассчитываем время отправки (21 час с момента финального сообщения)
        reminder_time = datetime.now() + timedelta(hours=21)

        # Создаем отложенную задачу
        reminder_timer = asyncio.create_task(
            delayed_discount_reminder(user_id, context)
        )

        # ВАЖНО: добавляем таймер в active_timers
        if user_id not in active_timers:
            active_timers[user_id] = []
        active_timers[user_id].append(reminder_timer)

        user_states[user_id]['discount_timer_set'] = True
        user_states[user_id]['discount_reminder_time'] = reminder_time

        logger.info(f"Таймер скидки установлен для пользователя {user_id} на {reminder_time}")


async def delayed_discount_reminder(user_id, context):
    """Отправляет напоминание о скидке через 21 час"""
    try:
        # Ждем 3 секунды для теста (или 21 час для продакшена)
        await asyncio.sleep(21 * 3600)

        # Проверяем, не завершается ли бот
        if not shutting_down:
            # ЗДЕСЬ ВАЖНО: проверяем chat_id без использования user_states
            chat_id = None

            # Если пользователь все еще в user_states, берем оттуда
            if user_id in user_states:
                chat_id = user_states[user_id]['chat_id']
            else:
                # Пользователь уже удален, нужно сохранить chat_id заранее
                # Но мы это сделаем по-другому
                return

            if chat_id:
                await send_discount_reminder(context, chat_id)

    except asyncio.CancelledError:
        logger.info(f"Таймер скидки отменен для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка в delayed_discount_reminder: {e}")


async def debug_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для отладки"""
    user_id = update.effective_user.id

    info = f"""
📊 Отладочная информация:
user_id: {user_id}
user_id in user_states: {user_id in user_states}
shutting_down: {shutting_down}

Все user_states: {list(user_states.keys())}
Все active_timers: {list(active_timers.keys())}
"""

    if user_id in user_states:
        info += f"\nДанные пользователя {user_id}:"
        for key, value in user_states[user_id].items():
            info += f"\n  {key}: {value}"

    await update.message.reply_text(info)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        "ℹ️ <b>Помощь:</b>\n\n"
        "/start - Начать обучение\n"
        "/help - Эта справка\n\n"
        "📥 Бот отправляет видео для обучения\n"
        "⏳ На каждое видео даётся 10 минут\n"
        "✅ Нажмите кнопку после просмотра",
        parse_mode='HTML'
    )


def main():
    """Запуск бота"""
    logger.info("🚀 Запуск Telegram бота...")

    if IS_PRODUCTION:
        print("=" * 50)
        print("🌐 БОТ ЗАПУЩЕН НА УДАЛЁННОМ СЕРВЕРЕ")
        print("⏰ Доступен 24/7")
        print("📱 Ищите в Telegram")
        print("=" * 50)
    else:
        print("=" * 50)
        print("🔧 ЛОКАЛЬНЫЙ РЕЖИМ")
        print("⏰ Таймер: 30 секунд (для теста)")
        print("🛑 Ctrl+C для остановки")
        print("=" * 50)

    try:
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("debug", debug_state))
        application.add_handler(CallbackQueryHandler(button_handler))

        application.run_polling()

    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка: {e}")


if __name__ == '__main__':
    main()