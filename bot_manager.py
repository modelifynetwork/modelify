import os
import sqlite3
import asyncio
import hashlib
import json
import requests
import base64
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

import mercadopago  # Para consulta de pagamento Mercado Pago

# Caminho do banco no volume persistente do Fly.io
def connect_db():
    db_path = os.path.join(os.path.dirname(__file__), 'db', 'database.db')
    return sqlite3.connect(db_path)
    
POLL_INTERVAL = 5  # segundos

# Mercado Pago token
MERCADOPAGO_ACCESS_TOKEN = "APP_USR-6436253612422218-033017-115c16f1f9ddf7fca0c289fb9f1081a8-2359242973"

# URL do backend Flask, pode ser sobrescrito por variável de ambiente (ideal para produção!)
FLASK_URL = os.environ.get("FLASK_URL", "http://127.0.0.1:8080")

def get_bots_snapshot():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT bot_token, mensagens, botao_texto, id, oferta, link_vip, uuid
        FROM bots
        WHERE ativo=1
        ORDER BY bot_token
    """)
    bots = cursor.fetchall()
    conn.close()
    # Evita tokens duplicados (por segurança)
    unique_bots = []
    seen_tokens = set()
    for bot in bots:
        if bot[0] not in seen_tokens:
            unique_bots.append(bot)
            seen_tokens.add(bot[0])
    hash_str = "".join([str(bot) for bot in unique_bots])
    return hashlib.md5(hash_str.encode()).hexdigest(), unique_bots

async def run_bot(app):
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

def build_app(token, mensagens_json, botao_texto, bot_id, oferta, link_vip, uuid):
    app = Application.builder().token(token).build()

    # Handler para /start
    async def start(update, context):
        try:
            mensagens = json.loads(mensagens_json) if mensagens_json else []
            for msg in mensagens:
                await update.message.reply_text(msg)
            # Botão com texto customizado
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
            print(f"[BotManager] Erro no envio de mensagens automáticas: {e}")

    # Handler do botão (callback)
    async def button_callback(update, context):
        query = update.callback_query
        await query.answer()

        payload = {
            "uuid": uuid,  # uuid do produto/bot (vem do banco bots)
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

                # Envia o QRCode como imagem (converte base64 para BytesIO)
                if qrcode_base64:
                    if qrcode_base64.startswith('data:image'):
                        qrcode_base64 = qrcode_base64.split(',')[1]
                    img_bytes = base64.b64decode(qrcode_base64)
                    bio = BytesIO(img_bytes)
                    bio.name = "qrcode.png"
                    bio.seek(0)
                    await query.message.reply_photo(bio, caption="Escaneie o QRCode ou copie o código Pix abaixo:")

                # Envia o copia-e-cola
                if pix_copia_cola:
                    await query.message.reply_text(f"`{pix_copia_cola}`", parse_mode="Markdown")

            else:
                await query.message.reply_text("Erro ao gerar o pagamento. Tente novamente em instantes.")
        except Exception as e:
            print(f"[BotManager] Erro ao gerar pagamento Pix: {e}")
            await query.message.reply_text("Erro ao gerar o pagamento. Tente novamente mais tarde.")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^quero_vip$"))
    return app

# Verifica pagamentos pendentes e atualiza status se aprovado no Mercado Pago
async def verificar_pagamentos_aprovados():
    sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)
    while True:
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM pagamentos WHERE status = 'PENDENTE'")
            pagamentos = cursor.fetchall()
            for (id_transacao,) in pagamentos:
                try:
                    resultado = sdk.payment().search({"external_reference": id_transacao})
                    results = resultado["response"].get("results", [])
                    if results:
                        status_mp = results[0]["status"]
                        if status_mp == "approved":
                            cursor.execute("UPDATE pagamentos SET status = 'APROVADO' WHERE id = ?", (id_transacao,))
                            conn.commit()
                            print(f"[Verificador] Pagamento {id_transacao} aprovado!")
                except Exception as e:
                    print(f"[Verificador] Erro ao consultar Mercado Pago para {id_transacao}: {e}")
            conn.close()
        except Exception as e:
            print(f"[Verificador] Erro ao verificar pagamentos: {e}")
        await asyncio.sleep(10)

# Rotina: entrega link VIP se pagamento aprovado
async def entregar_vip(bot_token):
    bot = Bot(token=bot_token)
    while True:
        try:
            conn = connect_db()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.telegram_id, b.link_vip, p.id
                FROM pagamentos p
                JOIN bots b ON p.bot_id = b.id
                WHERE (p.status = 'APROVADO' OR p.status = 'approved' OR p.status = 'APPROVED')
                  AND (p.link_entregue IS NULL OR p.link_entregue = 0)
                  AND p.telegram_id IS NOT NULL
                  AND b.link_vip IS NOT NULL
            """)
            rows = cursor.fetchall()
            for row in rows:
                telegram_id = row["telegram_id"]
                link_vip = row["link_vip"]
                id_pagamento = row["id"]

                if not telegram_id or not link_vip:
                    continue

                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=(
                            "✅ *Pagamento confirmado!*\n\n"
                            f"Aqui está o acesso do seu grupo VIP:\n{link_vip}"
                        ),
                        parse_mode="Markdown"
                    )
                    cursor.execute(
                        "UPDATE pagamentos SET link_entregue = 1, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
                        (id_pagamento,)
                    )
                    conn.commit()
                except Exception as e:
                    print(f"[Entregador] Erro ao enviar para {telegram_id}: {e}")
                    continue
        except Exception as e:
            print("[Entregador] Erro no processo de entrega:", e)
        finally:
            if conn:
                conn.close()
        await asyncio.sleep(10)

async def manage_bots():
    last_hash = None
    running = []
    bots_tokens = []
    verificador_task = None
    while True:
        current_hash, bots_info = get_bots_snapshot()
        if current_hash != last_hash:
            print("[BotManager] Mudança detectada na tabela bots. Reiniciando bots ativos...")
            # Cancela tarefas antigas
            for app, task in running:
                try:
                    await app.updater.stop()
                    await app.stop()
                    await app.shutdown()
                    task.cancel()
                except Exception as e:
                    print(f"[BotManager] Erro ao parar bot: {e}")
            running.clear()
            bots_tokens.clear()
            await asyncio.sleep(1)
            # Inicia bots novos
            for bot in bots_info:
                try:
                    token, mensagens_json, botao_texto, bot_id, oferta, link_vip, uuid = bot
                    app = build_app(token, mensagens_json, botao_texto, bot_id, oferta, link_vip, uuid)
                    task = asyncio.create_task(run_bot(app))
                    running.append((app, task))
                    bots_tokens.append(token)
                    print(f"[BotManager] Bot {token[:10]}... iniciado.")
                except Exception as e:
                    print(f"[BotManager] Erro ao iniciar bot {token[:10]}...: {e}")
            # Inicia a rotina de entrega VIP para cada bot ativo
            for bot_token in bots_tokens:
                asyncio.create_task(entregar_vip(bot_token))
            # Inicia/verifica a rotina do verificador só uma vez
            if not verificador_task or verificador_task.done():
                verificador_task = asyncio.create_task(verificar_pagamentos_aprovados())
            last_hash = current_hash
        await asyncio.sleep(POLL_INTERVAL)

### INICIALIZAÇÃO FLASK E BOTS PARA FLY.IO

from app import app as flask_app  # importa seu Flask principal

import threading

def start_flask():
    # Importante: Fly.io espera na porta 8080!
    flask_app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    print("[BotManager] Iniciando monitoramento dos bots...")
    # Roda o Flask numa thread separada
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()
    # Roda o sistema dos bots no thread principal
    try:
        # Certifique-se de ter a coluna 'link_entregue' em pagamentos!
        asyncio.run(manage_bots())
    except KeyboardInterrupt:
        print("[BotManager] Encerrado pelo usuário.")
