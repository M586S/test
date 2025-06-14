from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8079819165:AAGHWs6jVunYUNcKlyOmKKgrLNYMVJ6mzzA"

# /start affiche le clavier principal
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Help"), KeyboardButton("Profile")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Bienvenue sur SMMTasker !", reply_markup=reply_markup)

# Gestion des messages texte envoyés via le clavier
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Help":
        await update.message.reply_text("Voici l'aide ...")

    elif text == "Profile":
        keyboard = [
            [KeyboardButton("Modifier")],
            [KeyboardButton("Retour au menu principal")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Votre profil :", reply_markup=reply_markup)

    elif text == "Modifier":
        await update.message.reply_text("Fonction modification en cours...")

    elif text == "Retour au menu principal":
        keyboard = [
            [KeyboardButton("Help"), KeyboardButton("Profile")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Retour au menu principal.", reply_markup=reply_markup)

    else:
        await update.message.reply_text("Je n'ai pas compris.")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()












"""from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import LoginRequired
import logging

logger = logging.getLogger()
SESSION_FILE_NAME = 'session.json'
USERNAME = 'danniel_ksong'
PASSWORD = 'Mario@123*'

def login_user():

    cl = Client()
    session = None

    if Path(SESSION_FILE_NAME).exists():
        session = cl.load_settings(Path(SESSION_FILE_NAME))

    login_via_session = False
    login_via_pw = False

    if session:
        print('Logging in to Instagram via session...')
        login_via_session = True
        try:
            cl.set_settings(session)
            cl.login(USERNAME, PASSWORD)

            # check if session is valid
            try:
                cl.get_timeline_feed()
            except LoginRequired:
                logger.error("Session is invalid, need to login via username and password")

                old_session = cl.get_settings()

                # use the same device uuids across logins
                cl.set_settings({})
                cl.set_uuids(old_session["uuids"])

                cl.login(USERNAME, PASSWORD)
            login_via_session = True
        except Exception as e:
            logger.error("Couldn't login user using session information: %s" % e)

    if not login_via_session:
        try:
            before_ip = cl._send_public_request("https://api.ipify.org/")
            print(before_ip)
            logger.error("Attempting to login via username and password. username: %s" % USERNAME)
            if cl.login(USERNAME, PASSWORD):
                login_via_pw = True
        except Exception as e:
            logger.error("Couldn't login user using username and password: %s" % e)

    if not login_via_pw and not login_via_session:
        raise Exception("Couldn't login user with either password or session")

if __name__ == '__main__':
    login_user()
"""
