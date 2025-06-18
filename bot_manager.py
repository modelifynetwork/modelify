import os
import psycopg2
import psycopg2.extras
import json
import requests
import base64
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import mercadopago
import threading
import multiprocessing
import sys
import time

from app import app as flask_app

def connect_db():
    return psycopg2.connect(os.environ.get('DATABASE_URL'), cursor_factory=psycopg2.extras.DictCursor)

MERCADOPAGO_ACCESS_TOKEN = "APP_USR-6436253612422218-033017-115c16f1f9ddf7fca0c289fb9f1081a8-2359242973"
FLASK_URL = os.environ.get("FLASK_URL", "https://modelify.onrender.com/")

def get_bots_info():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT bot_token, mensagens, botao_texto, id, oferta, link_vip, uuid
        FROM bots
        WHERE ativo=1
        ORDER BY bot_token
    """)
    bots = cursor.fetchall()
    conn.close()
    unique_bots = []
    seen_tokens = set()
    for bot in bots:
        token = bot['bot_token']
        if token and token not in seen_tokens:
            unique_bots.append(bot)
            seen_tokens.add(token)
    return unique_bots

def run_bot_proc(token, mensagens_json, botao_texto, bot_id, oferta, link_vip, uuid):
    import asyncio
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler

    def build_app():
        app = Application.builder().token(token).build()

        async def start(update, context):
            try:
                mensagens = json.loads(mensagens_json) if mensagens_json else []
                for msg in mensagens:
                    await update.message.reply_text(msg)
                keyboard = [
                    [InlineKeyboardButton(botao_texto or "QUERO TER ACESSO AO VIP", callback_data="quero_vip")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "Clique abaixo para garantir seu acesso VIP:",
                    reply_markup=reply_markup
                )
            except Exception as e:
                await update.message.reply_text("Erro ao processar as mensagens automáticas. Por favor, tente novamente.")

        async def button_callback(update, context):
            query = update.callback_query
            await query.answer()
            payload = {
                "uuid": uuid,
                "produto_nome": "Acesso VIP",
                "telegram_id": query.from_user.id,
                "bot_id": bot_id
            }
            try:
                response = requests.post(f"{FLASK_URL}/criar_pagamento_pix_telegram", json=payload, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    qrcode_base64 = data.get('qrcode')
                    pix_copia_cola = data.get('pix_copia_cola')
                    if qrcode_base64:
                        if qrcode_base64.startswith('data:image'):
                            qrcode_base64 = qrcode_base64.split(',')[1]
                        img_bytes = base64.b64decode(qrcode_base64)
                        bio = BytesIO(img_bytes)
                        bio.name = "qrcode.png"
                        bio.seek(0)
                        await query.message.reply_photo(bio, caption="Escaneie o QRCode ou copie o código Pix abaixo:")
                    if pix_copia_cola:
                        await query.message.reply_text(f"`{pix_copia_cola}`", parse_mode="Markdown")
                else:
                    await query.message.reply_text("Erro ao gerar o pagamento. Tente novamente em instantes.")
            except Exception:
                await query.message.reply_text("Erro ao gerar o pagamento. Tente novamente mais tarde.")

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_callback, pattern="^quero_vip$"))
        return app

    # Windows async policy
    if sys.platform.startswith('win'):
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        app = build_app()
        asyncio.run(app.run_polling())
    except Exception as e:
        print(f"[BotManager] Bot {str(token)[:8]} morreu: {e}")
        time.sleep(5)

def start_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    print("[BotManager] Iniciando Flask e bots (cada bot é um processo próprio)...")
    # Inicia Flask em thread
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bots_info = get_bots_info()
    tokens = [x['bot_token'] for x in bots_info]
    # Check for duplicate tokens
    if len(tokens) != len(set(tokens)):
        print("[FATAL] Há tokens duplicados no banco! Isso causará CONFLICT.")
        sys.exit(1)

    procs = []
    for bot in bots_info:
        token = bot['bot_token']
        mensagens_json = bot['mensagens']
        botao_texto = bot['botao_texto']
        bot_id = bot['id']
        oferta = bot['oferta']
        link_vip = bot['link_vip']
        uuid = bot['uuid']
        p = multiprocessing.Process(
            target=run_bot_proc,
            args=(token, mensagens_json, botao_texto, bot_id, oferta, link_vip, uuid)
        )
        p.start()
        procs.append(p)

    # Aguarda todos os bots terminarem (normalmente nunca termina)
    for p in procs:
        p.join()
