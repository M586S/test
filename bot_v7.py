import asyncio
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Optional
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telethon import TelegramClient
from telethon.errors import TypeNotFoundError, RPCError, SessionExpiredError
from telethon.tl.types import KeyboardButtonCallback

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TelegramBotManager:
    def __init__(self, bot_name: str, api_id: int, api_hash: str, message: str, session_dir: str = "telegram_sessions",
                 db_file: str = "bot_users.db"):
        self.bot_name = bot_name
        self.api_id = api_id
        self.api_hash = api_hash
        self.message = message
        self.session_dir = session_dir
        self.db_file = db_file
        self.clients: dict[int, TelegramClient] = {}
        self.click_counts: dict[int, int] = {}  # Compteur de clics par utilisateur
        self.balances: dict[int, list[tuple[str, str, str]]] = {}  # Historique des balances
        self.start_times: dict[int, str] = {}  # Heure de démarrage par utilisateur
        self.current_interaction_ids: dict[int, str] = {}  # ID de l'interaction en cours par utilisateur
        self._ensure_session_directory()
        self._init_db()

    def _ensure_session_directory(self):
        try:
            os.makedirs(self.session_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Erreur lors de la création du répertoire {self.session_dir} : {e}")
            raise

    def _init_db(self):
        """Initialise la base de données SQLite."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # Table users
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        telegram_id INTEGER UNIQUE,
                        first_name TEXT,
                        last_name TEXT,
                        username TEXT,
                        phone_number TEXT,
                        click_count INTEGER,
                        start_time TEXT,
                        last_balance TEXT,
                        last_balance_time TEXT
                    )
                ''')
                # Table interactions
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS interactions (
                        id TEXT PRIMARY KEY,
                        telegram_id INTEGER,
                        date TEXT,
                        start_time TEXT,
                        end_time TEXT,
                        click_count INTEGER,
                        last_balance TEXT,
                        last_balance_time TEXT,
                        FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
                    )
                ''')
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de la base de données : {e}")
            raise

    def _save_user(self, telegram_id: int, first_name: str = None, last_name: str = None, username: str = None,
                   phone_number: str = None, click_count: int = None, start_time: str = None, last_balance: str = None,
                   last_balance_time: str = None):
        """Enregistre ou met à jour les informations de l'utilisateur dans la table users."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
                result = cursor.fetchone()
                if not result:
                    user_id = str(uuid.uuid4())
                    cursor.execute('''
                        INSERT INTO users (id, telegram_id, first_name, last_name, username, phone_number, click_count, start_time, last_balance, last_balance_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                    user_id, telegram_id, first_name, last_name, username, phone_number, click_count or 0, start_time,
                    last_balance, last_balance_time))
                else:
                    update_fields = []
                    update_values = []
                    if first_name:
                        update_fields.append("first_name = ?")
                        update_values.append(first_name)
                    if last_name:
                        update_fields.append("last_name = ?")
                        update_values.append(last_name)
                    if username:
                        update_fields.append("username = ?")
                        update_values.append(username)
                    if phone_number:
                        update_fields.append("phone_number = ?")
                        update_values.append(phone_number)
                    if click_count is not None:
                        update_fields.append("click_count = ?")
                        update_values.append(click_count)
                    if start_time:
                        update_fields.append("start_time = ?")
                        update_values.append(start_time)
                    if last_balance:
                        update_fields.append("last_balance = ?")
                        update_values.append(last_balance)
                    if last_balance_time:
                        update_fields.append("last_balance_time = ?")
                        update_values.append(last_balance_time)
                    if update_fields:
                        query = f"UPDATE users SET {', '.join(update_fields)} WHERE telegram_id = ?"
                        update_values.append(telegram_id)
                        cursor.execute(query, update_values)
                conn.commit()
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'utilisateur {telegram_id} : {e}")

    def _save_interaction(self, telegram_id: int, interaction_id: str, date: str, start_time: str, end_time: str = None,
                          click_count: int = 0, last_balance: str = None, last_balance_time: str = None):
        """Enregistre ou met à jour une interaction dans la table interactions."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM interactions WHERE id = ?", (interaction_id,))
                result = cursor.fetchone()
                if not result:
                    cursor.execute('''
                        INSERT INTO interactions (id, telegram_id, date, start_time, end_time, click_count, last_balance, last_balance_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (interaction_id, telegram_id, date, start_time, end_time, click_count, last_balance,
                          last_balance_time))
                else:
                    update_fields = ["click_count = ?", "end_time = ?"]
                    update_values = [click_count, end_time]
                    if last_balance:
                        update_fields.append("last_balance = ?")
                        update_values.append(last_balance)
                    if last_balance_time:
                        update_fields.append("last_balance_time = ?")
                        update_values.append(last_balance_time)
                    query = f"UPDATE interactions SET {', '.join(update_fields)} WHERE id = ?"
                    update_values.append(interaction_id)
                    cursor.execute(query, update_values)
                conn.commit()
        except Exception as e:
            logger.error(
                f"Erreur lors de la sauvegarde de l'interaction {interaction_id} pour telegram_id {telegram_id} : {e}")

    async def get_interaction_history(self, telegram_id: int) -> str:
        """Récupère l'historique des interactions pour un utilisateur, trié du plus ancien au plus récent."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT date, start_time, end_time, click_count, last_balance, last_balance_time
                    FROM interactions
                    WHERE telegram_id = ?
                    ORDER BY date ASC, start_time ASC
                ''', (telegram_id,))
                interactions = cursor.fetchall()
                if not interactions:
                    return "📜 Aucun historique d'interaction trouvé."

                history = "📜 Historique des interactions :\n"
                for interaction in interactions:
                    date, start_time, end_time, click_count, last_balance, last_balance_time = interaction
                    history += f"- Date: {date}, Début: {start_time}, Fin: {end_time or 'En cours'}, Clics: {click_count}"
                    if last_balance:
                        history += f", Balance: {last_balance} ({last_balance_time})"
                    history += "\n"
                return history
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'historique pour telegram_id {telegram_id} : {e}")
            return f"⚠️ Erreur lors de la récupération de l'historique : {str(e)}"

    def _get_session_file(self, telegram_id: int) -> str:
        return os.path.join(self.session_dir, f"session_{telegram_id}")

    async def _get_client(self, telegram_id: int, context: ContextTypes.DEFAULT_TYPE) -> TelegramClient:
        if telegram_id in self.clients:
            client = self.clients[telegram_id]
            if not client.is_connected():
                logger.info(f"Tentative de reconnexion pour telegram_id {telegram_id}")
                try:
                    await client.connect()
                except Exception as e:
                    logger.error(f"Échec de la reconnexion pour telegram_id {telegram_id} : {e}")
                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=f"⚠️ Erreur de connexion au client Telegram : {str(e)}. Réessayez plus tard.",
                        reply_markup=self._get_task_keyboard(bool(context.user_data.get("bot_task")))
                    )
                    raise
            return client

        session_file = self._get_session_file(telegram_id)
        client = TelegramClient(session_file, self.api_id, self.api_hash)
        self.clients[telegram_id] = client
        try:
            await client.connect()
        except Exception as e:
            logger.error(f"Échec de la connexion initiale pour telegram_id {telegram_id} : {e}")
            await context.bot.send_message(
                chat_id=telegram_id,
                text=f"⚠️ Erreur de connexion initiale au client Telegram : {str(e)}. Réessayez plus tard.",
                reply_markup=self._get_task_keyboard(bool(context.user_data.get("bot_task")))
            )
            raise
        return client

    async def run_task(self, context: ContextTypes.DEFAULT_TYPE, telegram_id: int, first_name: str = None,
                       last_name: str = None, username: str = None, phone_number: str = None):
        context.user_data["stop_tasks"] = False
        # Réinitialiser les compteurs au démarrage
        self.click_counts[telegram_id] = 0
        self.balances[telegram_id] = []
        self.start_times[telegram_id] = datetime.now().strftime("%H:%M:%S")
        # Créer une nouvelle interaction
        interaction_id = str(uuid.uuid4())
        self.current_interaction_ids[telegram_id] = interaction_id
        current_date = datetime.now().strftime("%Y-%m-%d")
        # Enregistrer l'utilisateur dans la table users
        self._save_user(telegram_id, first_name, last_name, username, phone_number, click_count=0,
                        start_time=self.start_times[telegram_id])
        # Enregistrer l'interaction dans la table interactions
        self._save_interaction(telegram_id, interaction_id, current_date, self.start_times[telegram_id],
                               end_time="En cours", click_count=0)

        client = await self._get_client(telegram_id, context)

        async with client:
            try:
                entity = await client.get_input_entity(self.bot_name)
                while not context.user_data.get("stop_tasks", False):
                    try:
                        if not client.is_connected():
                            logger.warning(
                                f"Client déconnecté pour telegram_id {telegram_id}. Tentative de reconnexion.")
                            await client.connect()

                        # Créer une nouvelle conversation à chaque tour de boucle
                        async with client.conversation(self.bot_name, timeout=20) as conv:
                            # Envoyer le message
                            await conv.send_message(self.message)
                            logger.info(f"Message '{self.message}' envoyé par telegram_id {telegram_id}")

                            try:
                                response = await conv.get_response(timeout=10)
                                logger.info(f"Réponse reçue pour telegram_id {telegram_id} : {response.text}")
                            except asyncio.TimeoutError:
                                logger.warning(f"Timeout pour telegram_id {telegram_id}. Réessai dans 10 secondes.")
                                await asyncio.sleep(10)
                                continue
                            except TypeNotFoundError as e:
                                logger.error(f"TypeNotFoundError pour telegram_id {telegram_id} : {e}")
                                await context.bot.send_message(
                                    chat_id=telegram_id,
                                    text="⚠️ Erreur lors de la réception de la réponse. Réessayez plus tard.",
                                    reply_markup=self._get_task_keyboard(True)
                                )
                                await asyncio.sleep(10)
                                continue

                            # Cliquer sur le bouton s’il y en a un
                            if hasattr(response, 'reply_markup') and response.reply_markup:
                                for row in response.reply_markup.rows:
                                    for button in row.buttons:
                                        if isinstance(button, KeyboardButtonCallback):
                                            try:
                                                await response.click(data=button.data)
                                                self.click_counts[telegram_id] += 1

                                                # Mise à jour des données utilisateur
                                                self._save_user(telegram_id, click_count=self.click_counts[telegram_id])
                                                self._save_interaction(
                                                    telegram_id,
                                                    interaction_id,
                                                    current_date,
                                                    self.start_times[telegram_id],
                                                    end_time="En cours",
                                                    click_count=self.click_counts[telegram_id]
                                                )
                                                logger.info(
                                                    f"Bouton cliqué par telegram_id {telegram_id} : {button.text}")
                                            except RPCError as e:
                                                if "GetBotCallbackAnswerRequest" in str(e):
                                                    logger.warning(
                                                        f"Erreur GetBotCallbackAnswerRequest ignorée pour telegram_id {telegram_id} : {e}")
                                                else:
                                                    logger.error(
                                                        f"Erreur lors du clic sur le bouton pour telegram_id {telegram_id} : {e}")
                                            break
                                    else:
                                        continue
                                    break
                                else:
                                    logger.warning(f"Aucun bouton InlineKeyboard trouvé pour telegram_id {telegram_id}")
                                    await context.bot.send_message(
                                        chat_id=telegram_id,
                                        text="⚠️ Aucun bouton InlineKeyboard trouvé dans la réponse.",
                                        reply_markup=self._get_task_keyboard(True)
                                    )

                        await asyncio.sleep(60)  # attendre 1 min avant prochaine itération

                    except Exception as e:
                        if "Cannot send requests while disconnected" in str(e):
                            logger.warning(
                                f"Déconnexion détectée pour telegram_id {telegram_id}. Réessai dans 20 secondes.")
                            await context.bot.send_message(
                                chat_id=telegram_id,
                                text="⚠️ Client déconnecté. Réessai dans 20 secondes.",
                                reply_markup=self._get_task_keyboard(True)
                            )
                            await asyncio.sleep(20)
                            continue
                        logger.error(f"Erreur inattendue dans run_task pour telegram_id {telegram_id} : {e}")
                        await context.bot.send_message(
                            chat_id=telegram_id,
                            text=f"⚠️ Erreur inattendue : {str(e)}. La tâche continue.",
                            reply_markup=self._get_task_keyboard(True)
                        )
                        await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Erreur critique dans run_task pour telegram_id {telegram_id} : {e}")
                await self._send_stop_message(context, telegram_id, reason=f"Erreur critique : {str(e)}")
            finally:
                # Nettoyage et arrêt propre
                context.user_data["stop_tasks"] = False
                context.user_data.pop("bot_task", None)

                interaction_id = self.current_interaction_ids.get(telegram_id)
                if interaction_id:
                    end_time = datetime.now().strftime("%H:%M:%S")
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    click_count = self.click_counts.get(telegram_id, 0)
                    self._save_interaction(
                        telegram_id,
                        interaction_id,
                        current_date,
                        self.start_times.get(telegram_id, "Inconnu"),
                        end_time=end_time,
                        click_count=click_count
                    )
                    logger.info(f"✔️ Interaction clôturée pour telegram_id {telegram_id}")

            logger.info(f"Tâche arrêtée pour telegram_id {telegram_id}")

    async def _send_stop_message(self, context: ContextTypes.DEFAULT_TYPE, telegram_id: int, reason: str = None):
        """Envoie un message d'arrêt avec un résumé des collectes."""
        click_count = self.click_counts.get(telegram_id, 0)
        calculated_total = click_count * 0.0000179434  # Calcul basé sur le prix par clic
        start_time = self.start_times.get(telegram_id, "Inconnu")
        interaction_id = self.current_interaction_ids.get(telegram_id)
        end_time = datetime.now().strftime("%H:%M:%S")
        # Mettre à jour l'interaction avec l'heure de fin
        if interaction_id:
            current_date = datetime.now().strftime("%Y-%m-%d")
            self._save_interaction(telegram_id, interaction_id, current_date, start_time, end_time=end_time,
                                   click_count=click_count)
        summary = (
            f"🛑 Tâche arrêtée.\n"
            f"📊 Résumé :\n"
            f"- Heure de démarrage : {start_time}\n"
            f"- Nombre de collectes : {click_count}\n"
            f"- Total calculé (clics x 0.0000179434 BNB) : {calculated_total:.8f} Bnb"
        )
        if reason:
            summary += f"\n⚠️ Raison : {reason}"
        await context.bot.send_message(
            chat_id=telegram_id,
            text=summary,
            reply_markup=self._get_task_keyboard(False)
        )
        # Réinitialiser les compteurs et mettre à jour la base de données
        self._save_user(telegram_id, click_count=0, start_time=None, last_balance=None, last_balance_time=None)
        self.click_counts[telegram_id] = 0
        self.balances[telegram_id] = []
        self.start_times.pop(telegram_id, None)
        self.current_interaction_ids.pop(telegram_id, None)

    def _get_task_keyboard(self, task_running: bool) -> ReplyKeyboardMarkup:
        """Retourne un clavier avec des boutons pour démarrer/arrêter la tâche, voir les statistiques et l'historique."""
        button_text = "▶️ Démarrer la tâche" if not task_running else "🛑 Arrêter la tâche"
        return ReplyKeyboardMarkup([[button_text], ["📊 Statistiques"], ["📜 Historique"]], resize_keyboard=True)

    async def get_stats(self, telegram_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Retourne les statistiques pour l'utilisateur, avec la balance extraite du dernier message."""
        click_count = self.click_counts.get(telegram_id, 0)
        calculated_total = click_count * 0.0000179434  # Calcul basé sur le prix par clic
        start_time = self.start_times.get(telegram_id, "Inconnu")
        balances = self.balances.get(telegram_id, [])

        # Calculer la durée depuis le démarrage
        duration = "N/A"
        if start_time != "Inconnu":
            try:
                start_dt = datetime.strptime(start_time, "%H:%M:%S")
                current_dt = datetime.now()
                # Ajuster pour la date du jour
                start_dt = start_dt.replace(year=current_dt.year, month=current_dt.month, day=current_dt.day)
                delta = current_dt - start_dt
                hours, remainder = divmod(delta.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            except ValueError as e:
                logger.warning(f"Erreur lors du calcul de la durée pour telegram_id {telegram_id} : {e}")
                duration = "Erreur de calcul"

        # Récupérer la dernière balance depuis le bot cible
        client = await self._get_client(telegram_id, context)
        latest_balance = "Aucune balance trouvée"
        latest_time = "N/A"
        try:
            entity = await client.get_input_entity(self.bot_name)
            async for message in client.iter_messages(entity, limit=10, reverse=False):
                    balance_match = re.search(r"💰 New Balance: (\d+\.\d{8} Bnb)", message.text)
                    if balance_match:
                        latest_balance = balance_match.group(0)
                        latest_time = message.date.strftime("%H:%M:%S")
                        # Mettre à jour l'historique des balances si nécessaire
                        if not balances or balances[-1][0] != latest_balance:
                            if not balances:
                                balances.append((latest_balance, latest_time, "Démarrage"))
                            else:
                                balances.append((latest_balance, latest_time, "Maintenant"))
                        # Mettre à jour l'interaction en cours
                        interaction_id = self.current_interaction_ids.get(telegram_id)
                        if interaction_id:
                            current_date = datetime.now().strftime("%Y-%m-%d")
                            self._save_interaction(telegram_id, interaction_id, current_date,
                                                   self.start_times.get(telegram_id, "Inconnu"), end_time="En cours",
                                                   click_count=click_count, last_balance=latest_balance,
                                                   last_balance_time=latest_time)
                        break
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la balance pour telegram_id {telegram_id} : {e}")
            latest_balance = f"Erreur lors de la récupération : {str(e)}"

        self.balances[telegram_id] = balances
        # Mettre à jour la base de données users avec la dernière balance
        self._save_user(telegram_id, click_count=click_count, last_balance=latest_balance,
                        last_balance_time=latest_time)

        stats = (
            f"📊 Statistiques :\n"
            f"- Heure de démarrage : {start_time}\n"
            f"- Durée depuis le démarrage : {duration}\n"
            f"- Nombre de clics : {click_count}\n"
            f"- Total calculé (clics x 0.0000179434 BNB) : {calculated_total:.8f} Bnb\n"
            f"- Dernière balance : {latest_balance} ({latest_time})\n"
        )
        if balances:
            stats += "💰 Historique des balances :\n"
            for balance, time, label in balances:
                stats += f"- {balance} ({time} - {label})\n"
        else:
            stats += "💰 Aucune balance enregistrée.\n"
        return stats


class SimpleBot:
    def __init__(self):
        self.tg_manager = None

    def _get_task_keyboard(self, task_running: bool) -> ReplyKeyboardMarkup:
        """Retourne un clavier avec des boutons pour démarrer/arrêter la tâche, voir les statistiques et l'historique."""
        return self.tg_manager._get_task_keyboard(task_running)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = update.effective_user.id
        user = update.effective_user
        first_name = user.first_name
        last_name = user.last_name
        username = user.username
        phone_number = None  # Telegram ne fournit pas le numéro sauf si partagé explicitement
        context.user_data["authenticated"] = True
        task_running = bool(context.user_data.get("bot_task"))
        # Enregistrer l'utilisateur
        self.tg_manager._save_user(telegram_id, first_name, last_name, username, phone_number)
        await update.message.reply_text(
            "👋 Bienvenue ! Utilisez les boutons ci-dessous pour contrôler la tâche, voir les statistiques ou l'historique.",
            reply_markup=self._get_task_keyboard(task_running)
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = update.effective_user.id
        user = update.effective_user
        first_name = user.first_name
        last_name = user.last_name
        username = user.username
        phone_number = None
        text = update.message.text.strip()

        # Gérer les commandes du clavier
        if text == "▶️ Démarrer la tâche":
            if not context.user_data.get("bot_task"):
                context.user_data["bot_task"] = asyncio.create_task(
                    self.tg_manager.run_task(context, telegram_id, first_name, last_name, username, phone_number)
                )
                await update.message.reply_text(
                    "▶️ Tâche démarrée : envoi du message et clic sur le bouton toutes les minutes.",
                    reply_markup=self._get_task_keyboard(True)
                )
            else:
                await update.message.reply_text(
                    "⚠️ Tâche déjà en cours.",
                    reply_markup=self._get_task_keyboard(True)
                )
        elif text == "🛑 Arrêter la tâche":
            context.user_data["stop_tasks"] = True
            if context.user_data.get("bot_task"):
                context.user_data["bot_task"].cancel()
                context.user_data.pop("bot_task")
                await self.tg_manager._send_stop_message(context, telegram_id)
            else:
                await update.message.reply_text(
                    "⚠️ Aucune tâche en cours.",
                    reply_markup=self._get_task_keyboard(False)
                )
        elif text == "📊 Statistiques":
            stats = await self.tg_manager.get_stats(telegram_id, context)
            await update.message.reply_text(
                stats,
                reply_markup=self._get_task_keyboard(bool(context.user_data.get("bot_task")))
            )
        elif text == "📜 Historique":
            history = await self.tg_manager.get_interaction_history(telegram_id)
            await update.message.reply_text(
                history,
                reply_markup=self._get_task_keyboard(bool(context.user_data.get("bot_task")))
            )
        else:
            await update.message.reply_text(
                "❓ Veuillez utiliser les boutons ci-dessous pour contrôler la tâche, voir les statistiques ou l'historique.",
                reply_markup=self._get_task_keyboard(bool(context.user_data.get("bot_task")))
            )


def main():
    # Configuration
    env = {
        "telegram_token": "7533805897:AAFwnJrCj9kiEa-75r2ZpeUuup2Fv15H6a4",
        "bot_name": "@Free_Binance_Bnb_Pay_Bot",
        "api_id": 22529395,
        "api_hash": "844420e11340bbf3de40ff40d6c0cfe3",
        "message": "✅ Free Bnb Collect 🎰"
    }

    tg_manager = TelegramBotManager(
        bot_name=env["bot_name"],
        api_id=env["api_id"],
        api_hash=env["api_hash"],
        message=env["message"]
    )

    bot = SimpleBot()
    bot.tg_manager = tg_manager

    app = Application.builder().token(env["telegram_token"]).build()
    app.bot_data["tg_manager"] = tg_manager

    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    logger.info("Bot lancé !")
    app.run_polling()


if __name__ == "__main__":
    main()
