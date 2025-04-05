import logging
import asyncio
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Update
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timedelta

# Инициализация логгирования
logging.basicConfig(level=logging.INFO)

bot_token = os.getenv("BOT_TOKEN")
channel_id = os.getenv("CHANNEL_ID")

# Настройки базы данных
DATABASE_URL = 'sqlite:///posts.db'  # Файл базы данных в папке с ботом

# Создание базы данных
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель для хранения постов
class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    message_id = Column(Integer)
    type = Column(String(10))  # 'photo', 'video'
    file_id = Column(String(255))
    caption = Column(Text)
    created_at = Column(DateTime)
    is_published = Column(Boolean, default=False)  # Флаг, опубликован ли пост

    user = relationship("User", back_populates="posts")

# Модель для хранения пользователей
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, unique=True)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    posts = relationship("Post", back_populates="user")
    is_admin = Column(Boolean, default=False)  # Флаг, является ли пользователь админом

# Модель для хранения настроек
class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True, index=True)
    interval = Column(Integer)  # Интервал между постами в минутах

# Создание таблиц в базе данных
Base.metadata.create_all(bind=engine)

# Создание бота и диспетчера
bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)

# Состояния для FSMContext
class Form(StatesGroup):
    interval = State()

# Список админских ID
admin_ids = [6472135701, 871322442]  # Замените вторым админским ID

# Обработчик команды /start
@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    db_session = SessionLocal()
    try:
        user = db_session.query(User).filter_by(chat_id=user_id).first()
        if not user:
            user = User(chat_id=user_id, username=message.from_user.username,
                          first_name=message.from_user.first_name, last_name=message.from_user.last_name)
            db_session.add(user)
            db_session.commit()

        if user_id in admin_ids:
            user.is_admin = True
            db_session.commit()

            # Отправляем сообщение админу с кнопками
            keyboard = [
                [InlineKeyboardButton(text="Админское меню", callback_data="admin_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await message.answer("Привет! Чтобы получить доступ к админскому меню, нажмите на кнопку ниже:", reply_markup=reply_markup)  
        else:
            await message.answer("Привет! Черт")
            await asyncio.sleep(2)
            await message.answer("Отправь че-нибудь черт")
    except Exception as e:
        logging.exception(f"Ошибка при старте: {e}")
        await message.answer(f"Произошла ошибка: {e}")
    finally:
        db_session.close()

# Обработчик фото и видео сообщений
@dp.message(lambda message: message.photo or message.video)
async def handle_image_message(message: types.Message):
    if message.from_user.id == bot.id:
        return

    user_id = message.from_user.id
    db_session = SessionLocal()

    try:
        # Сохраняем информацию о пользователе
        user = db_session.query(User).filter_by(chat_id=user_id).first()
        if not user:
            user = User(chat_id=user_id, username=message.from_user.username,
                          first_name=message.from_user.first_name, last_name=message.from_user.last_name)
            db_session.add(user)
            db_session.commit()

        if message.photo:
            # Если сообщение содержит фото, сохраняем его в базе данных
            photo_file = message.photo[-1].file_id
            caption = "[ZLP™](https://t.me/zalupepe)"
            post = Post(user_id=user.id, type='photo', file_id=photo_file, caption=caption, created_at=datetime.now())
            db_session.add(post)
            db_session.commit()
        elif message.video:
            # Если сообщение содержит видео, сохраняем его в базе данных
            video_file = message.video.file_id
            caption = "[ZLP™](https://t.me/zalupepe)"
            post = Post(user_id=user.id, type='video', file_id=video_file, caption=caption, created_at=datetime.now())
            db_session.add(post)
            db_session.commit()
    except Exception as e:
        logging.exception(f"Ошибка при сохранении поста: {e}")
        await message.answer(f"Произошла ошибка: {e}")
    finally:
        db_session.close()

# Обработчик команды /show_posts
@dp.callback_query(lambda c: c.data == 'show_posts')
async def show_posts(call: CallbackQuery):
    user_id = call.from_user.id
    db_session = SessionLocal()
    try:
        user = db_session.query(User).filter_by(chat_id=user_id).first()
        if user and user.is_admin:
            posts = db_session.query(Post).filter_by(is_published=False).order_by(Post.created_at.asc()).limit(40).all()
            if posts:
                for post in posts:
                    keyboard = [
                        [InlineKeyboardButton(text="Удалить", callback_data=f"delete_{post.id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
                    if post.type == 'photo':
                        await bot.send_photo(chat_id=call.from_user.id, photo=post.file_id, caption=post.caption, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
                    elif post.type == 'video':
                        await bot.send_video(chat_id=call.from_user.id, video=post.file_id, caption=post.caption, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            else:
                await call.message.answer("Постов нет.")
        else:
            await call.message.answer("У вас нет доступа к этой команде.")
    except Exception as e:
        logging.exception(f"Ошибка при получении постов: {e}")
        await call.message.answer(f"Произошла ошибка: {e}")
    finally:
        db_session.close()

# Обработчик команды /set_interval
@dp.callback_query(lambda c: c.data == 'set_interval')
async def set_interval(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    db_session = SessionLocal()
    try:
        user = db_session.query(User).filter_by(chat_id=user_id).first()
        if user and user.is_admin:
            await call.message.answer("Введите желаемый интервал между постами (в минутах). Например, 5")
            await state.set_state(Form.interval)
        else:
            await call.message.answer("У вас нет доступа к этой команде.")
    except Exception as e:
        logging.exception(f"Ошибка при установке интервала: {e}")
        await call.message.answer(f"Произошла ошибка: {e}")
    finally:
        db_session.close()

# Обработчик ввода интервала
@dp.message(Form.interval)
async def handle_interval(message: types.Message, state: FSMContext):
    try:
        interval = int(message.text)
        db_session = SessionLocal()
        settings = db_session.query(Settings).first()
        if not settings:
            settings = Settings(interval=interval)
            db_session.add(settings)
        else:
            settings.interval = interval
        db_session.commit()
        await message.answer("Интервал успешно установлен!")
        
        # Отправляем следующий пост сразу после установки интервала
        post = db_session.query(Post).filter_by(is_published=False).order_by(Post.created_at.asc()).first()
        if post:
            try:
                if post.type == 'photo':
                    await bot.send_photo(chat_id=channel_id, photo=post.file_id, caption=post.caption, parse_mode=ParseMode.MARKDOWN)
                elif post.type == 'video':
                    await bot.send_video(chat_id=channel_id, video=post.file_id, caption=post.caption, parse_mode=ParseMode.MARKDOWN)
                post.is_published = True
                db_session.commit()
            except Exception as e:
                logging.error(f"Ошибка при отправке поста в канал: {e}")
                db_session.rollback()

    except ValueError:
        await message.answer("Пожалуйста, введите число.")
    except Exception as e:
        logging.exception(f"Ошибка при установке интервала: {e}")
        await message.answer(f"Произошла ошибка: {e}")
    finally:
        db_session.close()
    await state.clear()

# Обработчик callback запросов
@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def handle_callback_query(call: CallbackQuery):
    user_id = call.from_user.id
    db_session = SessionLocal()
    try:
        user = db_session.query(User).filter_by(chat_id=user_id).first()
        if user and user.is_admin:
            post_id = int(call.data.split("_")[1])
            post = db_session.query(Post).filter_by(id=post_id).first()
            if post:
                # Удаляем пост из базы данных
                db_session.delete(post)
                db_session.commit()
                # Отправляем сообщение об успешном удалении
                await call.message.answer("Пост успешно удален!")
            else:
                await call.message.answer("Пост не найден!")
        else:
            await call.message.answer("У вас нет доступа к этой команде.")
    except Exception as e:
        logging.exception(f"Ошибка при удалении поста: {e}")
        await call.message.answer(f"Произошла ошибка: {e}")
    finally:
        db_session.close()

# Обработчик админского меню
@dp.callback_query(lambda c: c.data == 'admin_menu')
async def admin_menu(call: CallbackQuery):
    user_id = call.from_user.id
    db_session = SessionLocal()
    try:
        user = db_session.query(User).filter_by(chat_id=user_id).first()
        if user and user.is_admin:
            keyboard = [
                [InlineKeyboardButton(text="Управление интервалом", callback_data="set_interval")],
                [InlineKeyboardButton(text="Управление постами", callback_data="show_posts")]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await call.message.answer("Админское меню:", reply_markup=reply_markup)
        else:
            await call.message.answer("У вас нет доступа к этому меню.")
    except Exception as e:
        logging.exception(f"Ошибка при открытии админского меню: {e}")
        await call.message.answer(f"Произошла ошибка: {e}")
    finally:
        db_session.close()

# Функция для отправки постов на канал с заданным интервалом
async def send_posts_to_channel():
    while True:
        db_session = SessionLocal()
        try:
            settings = db_session.query(Settings).first()
            if settings and settings.interval:
                post = db_session.query(Post).filter_by(is_published=False).order_by(Post.created_at.asc()).first()
                if post:
                    try:
                        if post.type == 'photo':
                            await bot.send_photo(chat_id=channel_id, photo=post.file_id, caption=post.caption, parse_mode=ParseMode.MARKDOWN)
                        elif post.type == 'video':
                            await bot.send_video(chat_id=channel_id, video=post.file_id, caption=post.caption, parse_mode=ParseMode.MARKDOWN)
                        post.is_published = True
                        db_session.commit()
                    except Exception as e:
                        logging.error(f"Ошибка при отправке поста {post.id}: {e}")
                        db_session.rollback()  # Откатываем транзакцию в случае ошибки отправки

                    await asyncio.sleep(settings.interval * 60)  # Интервал задан в минутах, преобразуем в секунды
                else:
                    await asyncio.sleep(60)  # Если нет доступных постов, ждем 1 минуту перед следующей проверкой
            else:
                await asyncio.sleep(60)  # Если интервал не установлен, ждем 1 минуту перед следующей проверкой
        except Exception as e:
            logging.exception(f"Ошибка при отправке постов на канал: {e}")
        finally:
            db_session.close()
        await asyncio.sleep(1)  # Небольшая пауза между циклами

# Запуск бота и функции отправки постов на канал
async def main():
    asyncio.create_task(send_posts_to_channel())
    await dp.start_polling(bot) #bot обязателен

if __name__ == '__main__':
    asyncio.run(main())