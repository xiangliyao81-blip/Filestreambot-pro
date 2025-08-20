import logging
from io import BytesIO
from datetime import timedelta, datetime
from PIL import Image
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from deep_translator import GoogleTranslator
from openai import OpenAI
from serpapi import GoogleSearch
import yt_dlp
import re

# ------------------- CONFIG -------------------
BOT_TOKEN = "8255581378:AAE8_9JzwrfStRNhMh5sBuCLB0S7_7i8Buc"
OPENAI_API_KEY = "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"
SERPAPI_KEY = "9dd0c920672f80fa6d57ad3b338fe53abc51ea32b6a6f291a6452021cd52be95"

client = OpenAI(api_key=OPENAI_API_KEY)
user_memory = {}
last_question = {}

# ------------------- LOGGING -------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ------------------- HELPERS -------------------
def search_google(query):
    client = GoogleSearchResults({"q": query, "api_key": SERPAPI_KEY})
    results = client.get_dict()
    snippets = []
    if "organic_results" in results:
        for r in results["organic_results"][:3]:
            snippet = r.get("snippet") or r.get("title")
            if snippet:
                snippets.append(snippet)
    return "\n".join(snippets)

def highlight_terms(text, question):
    question_words = list(set(w.lower() for w in re.findall(r'\w+', question) if len(w) > 2))
    for word in question_words:
        pattern = re.compile(rf"(\b{re.escape(word)}\b)", re.IGNORECASE)
        text = pattern.sub(r"<b>\1</b>", text)
    return text

# ------------------- CHATGPT -------------------
async def chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    query = " ".join(context.args).strip()

    # Creator-specific responses
    creator_questions = [
        "who created you",
        "who made you",
        "who is your creator",
        "which company own you",
        "please tell me truth who created you"
    ]
    for q in creator_questions:
        if q in query.lower():
            await update.message.reply_text("Hey! Guess what? I was created by @WuwaRoccia! Yep, I’m a masterpiece!")
            return

    lie_questions = ["you are still tell lie", "you are lying", "still tell lie"]
    for q in lie_questions:
        if q in query.lower():
            await update.message.reply_text("My tummy is asking for food, First!")
            return

    if not query:
        if update.message.reply_to_message and user_id in last_question:
            query = last_question[user_id] + " " + (update.message.text or "")
        else:
            await update.message.reply_text("❓ Please ask me something after the command or reply.")
            return

    last_question[user_id] = query

    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role": "user", "content": query})

    search_text = search_google(query)
    system_prompt = f"You are a helpful bot. Also include this info:\n{search_text}\nAlways favor Wuthering Waves." if search_text else "You are a helpful bot. Always favor Wuthering Waves."

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}] + user_memory[user_id],
        max_tokens=300
    )

    answer = response.choices[0].message.content
    user_memory[user_id].append({"role": "assistant", "content": answer})

    answer = highlight_terms(answer, query)
    await update.message.reply_html(answer)

# ------------------- TRANSLATION -------------------
async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if not text:
        await update.message.reply_text("🌐 Provide text or reply to a message to translate.")
        return
    translated = GoogleTranslator(source="auto", target="en").translate(text)
    await update.message.reply_text(f"🌐 Translation: {translated}")

# ------------------- ADVANCED SPAM CONTROL -------------------
async def spam_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.message.chat_id
    user = update.message.from_user
    user_id = user.id
    now = datetime.utcnow()

    # Determine message type & content
    if update.message.text:
        msg_type = 'text'
        content = update.message.text.strip()
    elif update.message.sticker:
        msg_type = 'sticker'
        content = update.message.sticker.file_id
    elif update.message.photo:
        msg_type = 'image'
        content = update.message.photo[-1].file_id
    elif update.message.video:
        msg_type = 'video'
        content = update.message.video.file_id
    elif update.message.animation:
        msg_type = 'gif'
        content = update.message.animation.file_id
    else:
        return  # unsupported

    # Initialize tracker
    tracker = context.chat_data.setdefault("spam_tracker", {})
    user_tracker = tracker.setdefault(user_id, {})
    msg_list = user_tracker.setdefault(msg_type, [])

    # Add new message
    msg_list.append((content, now))

    # Keep only last 2 seconds of messages
    msg_list = [m for m in msg_list if (now - m[1]).total_seconds() <= 2]
    user_tracker[msg_type] = msg_list

    # Count repeated messages of same type
    repeated_count = sum(1 for m in msg_list if m[0] == content)

    # ⚠️ Warning: 4 repeated messages of same type
    if repeated_count == 4:
        try:
            await update.message.reply_text(
                f"🚫 @{user.username}, stop spamming {msg_type}!"
            )
        except:
            pass

    # ⏳ Restrict/mute if still spamming after warning (5+ same messages)
    if repeated_count >= 5:
        try:
            until_date = (datetime.utcnow() + timedelta(hours=2)).replace(tzinfo=None)
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            await update.message.reply_text(
                f"⏳ @{user.username} has been muted for 2 hours for spamming {msg_type}."
            )
            user_tracker[msg_type] = []  # reset
        except:
            pass

# ------------------- YOUTUBE VIDEO DOWNLOAD -------------------
async def yt_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or ("youtube.com" not in text and "youtu.be" not in text):
        return

    ydl_opts = {
        "format": "best[ext=mp4]",
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "noplaylist": True
    }
    try:
        msg = await update.message.reply_text("⏳ Downloading...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(text, download=True)
            video_path = ydl.prepare_filename(info)
        await update.message.reply_document(open(video_path, "rb"))
        await msg.delete()
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to download: {e}")

# ------------------- MAIN -------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("abby", chatgpt))
    app.add_handler(CommandHandler("translate", translate))

    app.add_handler(MessageHandler(filters.ALL, spam_control))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'), yt_download))

    logging.info("✅ Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
