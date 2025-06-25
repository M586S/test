import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Optional
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telethon import TelegramClient
from telethon.tl.types import KeyboardButtonCallback

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelegramBotManager:
    def __init__(self, bot_name: str, api_id: int, api_hash: str, message: str, session_dir: str = "telegram_sessions"):
        self.bot_name = bot_name
        self.api_id = api_id
        self.api_hash = api_hash
        self.message = message
        self.session_dir = session_dir
        self.clients: dict[int, TelegramClient] = {}
        self.click_counts: dict[int, int] = {}  # Compteur de clics par utilisateur
        self.balances: dict[int, list[tuple[str, str, str]]] = {}  # Historique des balances (balance, time, label)
        self.collected_amounts: dict[int, list[float]] = {}  # Montants collectés par clic
        self._ensure_session_directory()

    def _ensure_session_directory(self):
        try:
            os.makedirs(self.session_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Erreur lors de la création du répertoire {self.session_dir} : {e}")
            raise

    def _get_session_file(self, telegram_id: int) -> str:
        return os.path.join(self.session_dir, f"session_{telegram_id}")

    async def _get_client(self, telegram_id: int, context: ContextTypes.DEFAULT_TYPE) -> TelegramClient:
        if telegram_id in self.clients:
            client = self.clients[telegram_id]
            if not client.is_connected():
                await client.connect()
            return client

        session_file = self._get_session_file(telegram_id)
        client = TelegramClient(session_file, self.api_id, self.api_hash)
        self.clients[telegram_id] = client
        await client.connect()
        return client

    async def run_task(self, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
        context.user_data["stop_tasks"] = False
        if telegram_id not in self.click_counts:
            self.click_counts[telegram_id] = 0
            self.balances[telegram_id] = []
            self.collected_amounts[telegram_id] = []
        start_time = datetime.now().strftime("%H:%M")
        client = await self._get_client(telegram_id, context)

        async with client:
            try:
                entity = await client.get_input_entity(self.bot_name)
                async with client.conversation(self.bot_name) as conv:
                    while not context.user_data.get("stop_tasks", False):
                        # Envoyer le message spécifié
                        await conv.send_message(self.message)
                        logger.info(f"Message '{self.message}' envoyé par telegram_id {telegram_id}")

                        # Attendre la réponse avec le bouton
                        response = await conv.get_response(timeout=10)
                        logger.info(f"Réponse reçue pour telegram_id {telegram_id} : {response.text}")

                        # Vérifier si la réponse contient un bouton InlineKeyboard
                        if hasattr(response, 'reply_markup') and response.reply_markup:
                            for row in response.reply_markup.rows:
                                for button in row.buttons:
                                    if isinstance(button, KeyboardButtonCallback):
                                        # Cliquer sur le premier bouton trouvé
                                        await response.click(data=button.data)
                                        self.click_counts[telegram_id] += 1
                                        logger.info(f"Bouton cliqué par telegram_id {telegram_id} : {button.text}")
                                        break
                                else:
                                    continue
                                break
                            else:
                                logger.warning(f"Aucun bouton InlineKeyboard trouvé pour telegram_id {telegram_id}")
                                await context.bot.send_message(
                                    chat_id=telegram_id,
                                    text="⚠️ Aucun bouton InlineKeyboard trouvé dans la réponse.",
                                    reply_markup=self._get_task_keyboard(False)
                                )

                        # Récupérer le dernier message pour extraire la balance et le montant collecté
                        async for message in client.iter_messages(entity, limit=5, reverse=True):
                            if "✅ You successfully collected" in message.text:
                                balance_match = re.search(r"💰 New Balance: (\d+\.\d{8} Bnb)", message.text)
                                collected_match = re.search(r"✅ You successfully collected (\d+\.\d{8} Bnb)", message.text)
                                if balance_match:
                                    balance = balance_match.group(0)
                                    message_time = message.date.strftime("%H:%M")
                                    if not self.balances[telegram_id]:
                                        self.balances[telegram_id].append((balance, message_time, "Démarrage"))
                                    else:
                                        self.balances[telegram_id].append((balance, message_time, "Maintenant"))
                                if collected_match:
                                    try:
                                        collected_amount = float(collected_match.group(1))
                                        self.collected_amounts[telegram_id].append(collected_amount)
                                    except ValueError:
                                        logger.warning(f"Impossible de convertir le montant collecté : {collected_match.group(1)}")
                                break

                        # Attendre 1 minute avant la prochaine itération
                        await asyncio.sleep(60)

            except asyncio.TimeoutError:
                logger.error(f"Timeout lors de l'attente de la réponse pour telegram_id {telegram_id}")
                await self._send_stop_message(context, telegram_id, reason="Timeout : aucune réponse reçue du bot cible.")
            except Exception as e:
                logger.error(f"Erreur dans run_task pour telegram_id {telegram_id} : {e}")
                await self._send_stop_message(context, telegram_id, reason=f"Erreur : {str(e)}")
            finally:
                context.user_data["stop_tasks"] = False
                context.user_data.pop("bot_task", None)
                logger.info(f"Tâche arrêtée pour telegram_id {telegram_id}")

    async def _send_stop_message(self, context: ContextTypes.DEFAULT_TYPE, telegram_id: int, reason: str = None):
        """Envoie un message d'arrêt avec un résumé des collectes."""
        click_count = self.click_counts.get(telegram_id, 0)
        collected_total = sum(self.collected_amounts.get(telegram_id, []))
        summary = f"🛑 Tâche arrêtée.\n📊 Résumé :\n- Nombre de collectes : {click_count}\n- Total collecté : {collected_total:.8f} Bnb"
        if reason:
            summary += f"\n⚠️ Raison : {reason}"
        await context.bot.send_message(
            chat_id=telegram_id,
            text=summary,
            reply_markup=self._get_task_keyboard(False)
        )
        # Réinitialiser les compteurs après l'arrêt
        self.click_counts[telegram_id] = 0
        self.balances[telegram_id] = []
        self.collected_amounts[telegram_id] = []

    def _get_task_keyboard(self, task_running: bool) -> ReplyKeyboardMarkup:
        """Retourne un clavier avec des boutons pour démarrer/arrêter la tâche et voir les statistiques."""
        button_text = "▶️ Démarrer la tâche" if not task_running else "🛑 Arrêter la tâche"
        return ReplyKeyboardMarkup([[button_text], ["📊 Statistiques"]], resize_keyboard=True)

    def get_stats(self, telegram_id: int) -> str:
        """Retourne les statistiques pour l'utilisateur."""
        click_count = self.click_counts.get(telegram_id, 0)
        balances = self.balances.get(telegram_id, [])
        collected_total = sum(self.collected_amounts.get(telegram_id, []))
        stats = f"📊 Statistiques :\n- Nombre de clics : {click_count}\n- Total collecté : {collected_total:.8f} Bnb\n"
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
        """Retourne un clavier avec des boutons pour démarrer/arrêter la tâche et voir les statistiques."""
        return self.tg_manager._get_task_keyboard(task_running)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = update.effective_user.id
        context.user_data["authenticated"] = True
        task_running = bool(context.user_data.get("bot_task"))
        await update.message.reply_text(
            "👋 Bienvenue ! Utilisez les boutons ci-dessous pour contrôler la tâche ou voir les statistiques.",
            reply_markup=self._get_task_keyboard(task_running)
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = update.effective_user.id
        text = update.message.text.strip()

        # Gérer les commandes du clavier
        if text == "▶️ Démarrer la tâche":
            if not context.user_data.get("bot_task"):
                context.user_data["bot_task"] = asyncio.create_task(
                    self.tg_manager.run_task(context, telegram_id)
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
            stats = self.tg_manager.get_stats(telegram_id)
            await update.message.reply_text(
                stats,
                reply_markup=self._get_task_keyboard(bool(context.user_data.get("bot_task")))
            )
        else:
            await update.message.reply_text(
                "❓ Veuillez utiliser les boutons ci-dessous pour contrôler la tâche ou voir les statistiques.",
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
