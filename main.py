import os
import random
import sys
import traceback
from contextlib import contextmanager
from typing import Optional, Dict, List, Tuple

from dotenv import load_dotenv
import telebot
from telebot import types
import psycopg2

# Загрузка переменных окружения
load_dotenv()

# Создание бота
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

# Глобальное хранилище данных пользователей
user_data = {}


# Контекстный менеджер для работы с БД
@contextmanager
def db_connection():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        yield conn
    except psycopg2.Error as e:
        print(f"Ошибка подключения к БД: {e}")
        raise
    finally:
        if conn:
            conn.close()


# Добавление пользователя или получение его ID
def get_or_create_user(user: types.User) -> Optional[int]:
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (telegram_id, username, first_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (telegram_id) 
                    DO UPDATE SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
                    RETURNING id
                """, (user.id, user.username, user.first_name))
                user_id = cur.fetchone()[0]
                conn.commit()
                return user_id
    except Exception as e:
        print(f"Ошибка в get_or_create_user: {e}")
        return None


# Получение количества слов пользователя
def get_user_words_count(user_id: int) -> int:
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM user_words 
                    WHERE user_id = %s
                """, (user_id,))
                return cur.fetchone()[0]
    except Exception as e:
        print(f"Ошибка в get_user_words_count: {e}")
        return 0


# Получение случайного слова и вариантов (с проверкой на повторение)
def get_random_word_with_options(user_id: int, previous_word: str = None) -> Optional[Dict]:
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                word_data = None
                word_type = None
                attempts = 0
                max_attempts = 10  # Максимальное количество попыток найти уникальное слово

                while attempts < max_attempts:
                    attempts += 1

                    # Сначала пробуем получить пользовательское слово (50% chance)
                    if random.random() > 0.5:
                        if previous_word:
                            cur.execute("""
                                SELECT word, translation FROM user_words 
                                WHERE user_id = %s AND word != %s
                                ORDER BY RANDOM() 
                                LIMIT 1
                            """, (user_id, previous_word))
                        else:
                            cur.execute("""
                                SELECT word, translation FROM user_words 
                                WHERE user_id = %s 
                                ORDER BY RANDOM() 
                                LIMIT 1
                            """, (user_id,))
                        word_data = cur.fetchone()
                        word_type = 'user'

                    # Если не нашли пользовательское слово, берем из базы
                    if not word_data:
                        if previous_word:
                            cur.execute("""
                                SELECT word, translation FROM base_words 
                                WHERE word != %s
                                ORDER BY RANDOM() 
                                LIMIT 1
                            """, (previous_word,))
                        else:
                            cur.execute("""
                                SELECT word, translation FROM base_words 
                                ORDER BY RANDOM() 
                                LIMIT 1
                            """)
                        word_data = cur.fetchone()
                        word_type = 'base'

                    if not word_data:
                        continue  # Если слова нет, пробуем еще раз

                    word, translation = word_data

                    # Получаем 3 случайных неправильных варианта перевода
                    cur.execute("""
                        SELECT translation FROM base_words 
                        WHERE translation != %s 
                        ORDER BY RANDOM() 
                        LIMIT 3
                    """, (translation,))
                    other_words = [row[0] for row in cur.fetchall()]

                    return {
                        'word': word,
                        'translation': translation,
                        'other_words': other_words,
                        'type': word_type
                    }

                # Если не нашли уникальное слово после всех попыток
                return None

    except Exception as e:
        print(f"Ошибка в get_random_word_with_options: {e}")
        return None


# Добавление пользовательского слова
def add_user_word(user_id: int, word: str, translation: str) -> bool:
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_words (user_id, word, translation)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, word) 
                    DO UPDATE SET translation = EXCLUDED.translation
                """, (user_id, word.strip(), translation.strip()))
                conn.commit()
                return True
    except Exception as e:
        print(f"Ошибка в add_user_word: {e}")
        return False


# Удаление пользовательского слова
def delete_user_word(user_id: int, word: str) -> bool:
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM user_words 
                    WHERE user_id = %s AND word = %s
                    RETURNING id
                """, (user_id, word.strip()))
                deleted = cur.fetchone() is not None
                conn.commit()
                return deleted
    except Exception as e:
        print(f"Ошибка в delete_user_word: {e}")
        return False


# Получение списка пользовательских слов
def get_user_words(user_id: int) -> List[Tuple[str, str]]:
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT word, translation FROM user_words 
                    WHERE user_id = %s
                    ORDER BY word
                """, (user_id,))
                return cur.fetchall()
    except Exception as e:
        print(f"Ошибка в get_user_words: {e}")
        return []


# Приветственное сообщение
WELCOME_MESSAGE = """
👋 Привет! 
Давай займемся изучением английского языка.
Занятия проходят в удобном для тебя темпе.
У тебя есть возможность использовать тренажёр, как конструктор, и собирать свою собственную базу для обучения.
Для этого необходимо добавить сначала слово на русском языке, а потом его перевод.

📌 Что ты можешь:
- 🔤 Начать тренировку — получить карточку и выбрать перевод.
- 📚 Посмотреть свои слова — проверить, что уже добавил.
- ➕ Добавить слово — самостоятельно пополнять базу.
- ➖ Удалить слово — управлять своей коллекцией.

Ну что, начнём? 😉
"""


# Главное меню с inline-кнопками
def main_menu() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton('🔤 Начать тренировку', callback_data='start_quiz'),
        types.InlineKeyboardButton('📚 Мои слова', callback_data='my_words'),
        types.InlineKeyboardButton('➕ Добавить слово', callback_data='add_word'),
        types.InlineKeyboardButton('➖ Удалить слово', callback_data='delete_word')

    )
    return markup


# Клавиатура с вариантами ответов
def create_card_markup(target_word: str, other_words: List[str]) -> types.InlineKeyboardMarkup:
    buttons = [types.InlineKeyboardButton(word, callback_data=f"answer_{word}")
               for word in [target_word] + other_words]
    random.shuffle(buttons)
    return types.InlineKeyboardMarkup(row_width=2).add(*buttons)


# Клавиатура подтверждения удаления
def confirm_delete_markup(word: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del_{word}"),
        types.InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_delete")
    )
    return markup


# Отправка карточки с вопросом
def send_card(chat_id: int, word_data: dict, edit_message_id: int = None):
    question = word_data['word']
    translation = word_data['translation']
    other_words = word_data['other_words']

    markup = create_card_markup(translation, other_words)

    # Сохраняем данные перед отправкой
    user_data[chat_id] = {
        'correct_answer': translation,
        'question': question,
        'other_words': other_words,
        'message_id': None,
        'previous_word': question  # Сохраняем текущее слово для проверки на повторение
    }

    # Отправляем или редактируем сообщение с вопросом
    if edit_message_id:
        try:
            sent_msg = bot.edit_message_text(
                chat_id=chat_id,
                message_id=edit_message_id,
                text=f"Как переводится слово:\n🇷🇺 *{question}*",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            user_data[chat_id]['message_id'] = edit_message_id
        except Exception as e:
            print(f"Ошибка при редактировании сообщения: {e}")
            sent_msg = bot.send_message(
                chat_id,
                f"Как переводится слово:\n🇷🇺 *{question}*",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            user_data[chat_id]['message_id'] = sent_msg.message_id
    else:
        sent_msg = bot.send_message(
            chat_id,
            f"Как переводится слово:\n🇷🇺 *{question}*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        user_data[chat_id]['message_id'] = sent_msg.message_id


# Обработчик команды /start
@bot.message_handler(commands=["start", "help"])
def send_welcome(message: types.Message):
    try:
        user_id = get_or_create_user(message.from_user)
        if not user_id:
            raise Exception("Не удалось создать/получить пользователя")
        bot.send_message(message.chat.id, WELCOME_MESSAGE, reply_markup=main_menu())
    except Exception as e:
        print(f"Ошибка в send_welcome: {e}")
        bot.send_message(message.chat.id, "⚠️ Произошла ошибка. Попробуйте позже.")


# Обработчик запроса русского слова для добавления
def ask_for_russian_word(chat_id: int):
    msg = bot.send_message(
        chat_id,
        "📝 Введите слово, которое хотите добавить, на русском языке:",
        reply_markup=types.ForceReply()
    )
    bot.register_next_step_handler(msg, process_russian_word)


# Обработчик русского слова
def process_russian_word(message: types.Message):
    chat_id = message.chat.id
    russian_word = message.text.strip()

    if not russian_word:
        bot.send_message(chat_id, "❌ Слово не может быть пустым. Попробуйте снова.", reply_markup=main_menu())
        return

    # Сохраняем русское слово во временных данных
    if chat_id not in user_data:
        user_data[chat_id] = {}
    user_data[chat_id]['adding_word'] = russian_word

    # Запрашиваем перевод
    msg = bot.send_message(
        chat_id,
        f"Теперь введите перевод для слова '{russian_word}':",
        reply_markup=types.ForceReply()
    )
    bot.register_next_step_handler(msg, process_translation)


# Обработчик перевода слова
def process_translation(message: types.Message):
    chat_id = message.chat.id
    translation = message.text.strip()

    if not translation:
        bot.send_message(chat_id, "❌ Перевод не может быть пустым. Попробуйте снова.", reply_markup=main_menu())
        return

    # Получаем сохраненное русское слово
    russian_word = user_data.get(chat_id, {}).get('adding_word')
    if not russian_word:
        bot.send_message(chat_id, "❌ Не удалось найти исходное слово. Попробуйте снова.", reply_markup=main_menu())
        return

    user_id = get_or_create_user(message.from_user)
    if not user_id:
        bot.send_message(chat_id, "❌ Ошибка пользователя", reply_markup=main_menu())
        return

    if add_user_word(user_id, russian_word, translation):
        # Получаем количество слов пользователя
        words_count = get_user_words_count(user_id)
        bot.send_message(
            chat_id,
            f"✅ Слово '{russian_word}' с переводом '{translation}' успешно добавлено!\n"
            f"📊 Теперь вы изучаете слов: {words_count}",
            reply_markup=main_menu()
        )
    else:
        bot.send_message(chat_id, f"❌ Не удалось добавить слово '{russian_word}'", reply_markup=main_menu())

    # Очищаем временные данные
    if chat_id in user_data and 'adding_word' in user_data[chat_id]:
        del user_data[chat_id]['adding_word']


# Обработчик inline-кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    user = call.from_user
    user_id = get_or_create_user(user)

    if not user_id:
        bot.answer_callback_query(call.id, "Ошибка пользователя. Попробуйте снова.")
        return

    try:
        if call.data == 'start_quiz':
            # Начало новой тренировки
            previous_word = user_data.get(chat_id, {}).get('previous_word')
            word_data = get_random_word_with_options(user_id, previous_word)

            if not word_data:
                bot.send_message(chat_id, "Не удалось получить слова для тренировки.", reply_markup=main_menu())
                return

            send_card(chat_id, word_data)
            bot.answer_callback_query(call.id)
            return

        elif call.data.startswith('answer_'):
            # Обработка ответа пользователя
            data = user_data.get(chat_id)
            if not data:
                bot.answer_callback_query(call.id, "Ошибка: данные вопроса не найдены")
                bot.send_message(chat_id, "⚠️ Сессия устарела. Начните новую тренировку.", reply_markup=main_menu())
                return

            correct_answer = data.get('correct_answer')
            question = data.get('question')
            message_id = data.get('message_id')
            other_words = data.get('other_words', [])
            user_answer = call.data[len('answer_'):]

            if not correct_answer or not question:
                bot.answer_callback_query(call.id, "Ошибка: данные вопроса не найдены")
                bot.send_message(chat_id, "⚠️ Не удалось найти данные вопроса. Попробуйте начать заново.",
                                 reply_markup=main_menu())
                return

            # Проверяем ответ
            if user_answer == correct_answer:
                response = f"✅ Отлично!\n{question} -> {correct_answer}"
                bot.answer_callback_query(call.id, "✅ Верно!")

                # Очищаем данные после правильного ответа, кроме previous_word
                if chat_id in user_data:
                    prev_word = user_data[chat_id].get('previous_word')
                    user_data[chat_id] = {'previous_word': prev_word}

                # Предлагаем продолжить
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("➡️ Следующее слово", callback_data="start_quiz"),
                    types.InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")
                )

                # Пытаемся отредактировать сообщение или отправить новое
                try:
                    if message_id:
                        bot.edit_message_text(
                            response,
                            chat_id=chat_id,
                            message_id=message_id,
                            reply_markup=markup
                        )
                    else:
                        bot.send_message(chat_id, response, reply_markup=markup)
                except Exception as e:
                    print(f"Ошибка при редактировании сообщения: {e}")
                    bot.send_message(chat_id, response, reply_markup=markup)
            else:
                # Неправильный ответ - показываем тот же вопрос снова
                bot.answer_callback_query(call.id, "❌ Неверно! Попробуйте еще раз")

                # Создаем новые данные для вопроса (можно оставить те же варианты)
                word_data = {
                    'word': question,
                    'translation': correct_answer,
                    'other_words': other_words
                }

                # Редактируем сообщение с тем же вопросом
                send_card(chat_id, word_data, message_id)
            return

        elif call.data == 'add_word':
            # Начало процесса добавления слова - запрашиваем русское слово
            ask_for_russian_word(chat_id)
            return

        elif call.data == 'delete_word':
            # Удаление слова - показ списка
            user_words = get_user_words(user_id)
            if not user_words:
                bot.send_message(chat_id, "У вас пока нет добавленных слов.", reply_markup=main_menu())
                return

            markup = types.InlineKeyboardMarkup(row_width=1)
            for word, _ in user_words:
                markup.add(types.InlineKeyboardButton(word, callback_data=f"ask_del_{word}"))
            markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))
            bot.send_message(chat_id, "Выберите слово для удаления:", reply_markup=markup)
            return

        elif call.data.startswith('ask_del_'):
            # Подтверждение удаления
            word = call.data[len('ask_del_'):]
            bot.send_message(
                chat_id,
                f"Вы уверены, что хотите удалить слово '{word}'?",
                reply_markup=confirm_delete_markup(word)
            )
            return

        elif call.data.startswith('confirm_del_'):
            # Подтвержденное удаление
            word = call.data[len('confirm_del_'):]
            if delete_user_word(user_id, word):
                bot.answer_callback_query(call.id, f"✅ Слово '{word}' удалено")
                bot.send_message(chat_id, f"✅ Слово '{word}' успешно удалено!", reply_markup=main_menu())
            else:
                bot.answer_callback_query(call.id, f"❌ Не удалось удалить слово '{word}'")
                bot.send_message(chat_id, f"❌ Не удалось удалить слово '{word}'", reply_markup=main_menu())
            return

        elif call.data == 'cancel_delete':
            # Отмена удаления - возвращаемся в главное меню
            bot.answer_callback_query(call.id, "❌ Удаление отменено")
            bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu())
            return

        elif call.data == 'my_words':
            # Показ списка слов пользователя
            user_words = get_user_words(user_id)

            if not user_words:
                bot.send_message(chat_id, "У вас пока нет добавленных слов.", reply_markup=main_menu())
                return

            words_count = len(user_words)
            words_list = "\n".join([f"{rus} - {eng}" for rus, eng in user_words])
            bot.send_message(
                chat_id,
                f"📚 Ваши слова ({words_count}):\n{words_list}",
                reply_markup=main_menu()
            )
            return

        elif call.data == 'main_menu':
            # Возврат в главное меню
            bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu())
            return

    except Exception as e:
        print(f"Ошибка в обработке callback: {e}\nТрассировка: {traceback.format_exc()}")
        bot.answer_callback_query(call.id, "⚠️ Произошла ошибка. Попробуйте снова.")


# Проверка подключения к БД и запуск бота
if __name__ == '__main__':
    print("🚀 Бот запускается...")

    try:
        # Проверка подключения к БД
        with db_connection() as conn:
            with conn.cursor() as cur:
                # Проверка существования необходимых таблиц
                for table in ['users', 'base_words', 'user_words']:
                    cur.execute(f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = '{table}'
                        )
                    """)
                    if not cur.fetchone()[0]:
                        raise Exception(f"Таблица '{table}' не существует")

        print("✅ Подключение к БД выполнено успешно!")

        # Запуск бота
        print("🙏 Бот готов к работе!")
        bot.infinity_polling()

    except Exception as e:
        print(f"Ошибка при запуске бота: {e}\nТрассировка: {traceback.format_exc()}")
        sys.exit(1)