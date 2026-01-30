from pyrogram import Client, filters, types
from pyrogram.types import Message
from bot.config import Script


@Client.on_message(filters.command("xTaR") & filters.private & filters.incoming)
@Client.on_message(filters.regex("xTaR") & filters.private & filters.incoming)
async def start(bot: Client, message: Message):
    markup = types.InlineKeyboardMarkup(
        [
            [
                types.InlineKeyboardButton(
                    "Telegram", url="https://telegram.me/The_real_xTaR"
                ),
                types.InlineKeyboardButton(
                    "GitHub", url="https://github.com/The_real_xTaR"
                ),
            ],
            [
                types.InlineKeyboardButton(
                    "Fiverr", url="https://www.fiverr.com/The_real_xTaR"
                ),
            ],
        ]
    )
    await message.reply_text(
        Script.DEV_MESSAGE,
        disable_web_page_preview=True,
        quote=True,
        reply_markup=markup,
    )
