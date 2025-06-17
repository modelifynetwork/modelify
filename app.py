import smtplib
from flask import Flask, redirect, url_for, session, render_template, request, jsonify
import requests
from flask_cors import CORS
import mercadopago
import stripe
from PIL import Image
from werkzeug.utils import secure_filename
from flask import Flask, redirect, url_for, session, render_template
from authlib.integrations.flask_client import OAuth
from flask_session import Session
from flask import send_from_directory
import json
import sqlite3
import uuid
import random
import os
import secrets
from datetime import datetime
from email.mime.text import MIMEText

def connect_db():
    db_path = os.path.join(os.path.dirname(__file__), 'db', 'database.db')
    return sqlite3.connect(db_path)

mp = mercadopago.SDK("APP_USR-6436253612422218-033017-115c16f1f9ddf7fca0c289fb9f1081a8-2359242973")
stripe.api_key = os.getenv("STRIPE_API_KEY")
app = Flask(__name__, static_folder='static')
app.secret_key = os.urandom(24)
CORS(app)

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB
REQUIRED_WIDTH = 600
REQUIRED_HEIGHT = 400
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'mp4', 'mp3', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_bot_username(token):
    """
    Extrai o user_id (parte antes dos dois pontos) do token do Telegram.
    Exemplo de token: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
    Retorna: '123456789'
    Se não houver ':', retorna o próprio token como string.
    """
    if isinstance(token, str) and ":" in token:
        return token.split(":")[0]
    return str(token)

def enviar_chave_por_email(destinatario, chave):
    remetente = "modelifynetwork@gmail.com"  # Troque para seu email
    senha = "knhi lpkh ifyy oxlx"         # Troque para sua senha de app do Gmail

    corpo = f"""
Olá!

Sua chave de acesso ao painel exclusivo é:

{chave}

Guarde esta chave com segurança. Você precisará dela para acessar seu painel.

Qualquer dúvida, basta responder este e-mail.

Att,
Equipe Modelify
    """

    msg = MIMEText(corpo)
    msg["Subject"] = "Sua chave de acesso | Modelify"
    msg["From"] = remetente
    msg["To"] = destinatario

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(remetente, senha)
            server.sendmail(remetente, destinatario, msg.as_string())
    except Exception as e:
        print(f"Erro ao enviar e-mail para {destinatario}: {e}")

# --- Função para inserir ou resgatar chave do banco ---
def inserir_acesso(email, access_key, produto_uuid):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT access_key FROM acessos WHERE email = ? AND produto_uuid = ?", (email, produto_uuid))
    existe = cursor.fetchone()
    if existe:
        conn.close()
        return existe[0]
    cursor.execute(
        "INSERT INTO acessos (email, access_key, produto_uuid, criado_em) VALUES (?, ?, ?, ?)",
        (email, access_key, produto_uuid, datetime.utcnow())
    )
    conn.commit()
    conn.close()
    return access_key

print("=== VARIÁVEIS DE AMBIENTE NO RENDER ===")
for key, value in os.environ.items():
    print(f"{key} = {value}")

# Configuração da sessão
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['UPLOAD_FOLDER'] = 'static/uploads'  # Pasta para wsalvar as imagens
Session(app)

# Configurações do OAuth
oauth = OAuth(app)
app.config['SESSION_COOKIE_NAME'] = 'login-session'
app.config['GOOGLE_CLIENT_ID'] = os.getenv("GOOGLE_CLIENT_ID")
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv("GOOGLE_CLIENT_SECRET")
app.config['GOOGLE_DISCOVERY_URL'] = 'https://accounts.google.com/.well-known/openid-configuration'

# Registrar wOAuth com o Google
google = oauth.register(
    'google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url=app.config['GOOGLE_DISCOVERY_URL'],
    client_kwargs={'scope': 'openid email profile'},
)

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    print("Erro global capturado:", traceback.format_exc())
    return jsonify({"error": "Erro interno no servidor", "detalhes": str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    return '', 204  # No Content

from flask import session

@app.route('/api/vendas', methods=['GET'])
def api_vendas():
    vendas = []
    import sqlite3
    # Obtém o email do usuário logado na sessão
    user_email = session.get("user", {}).get("email")
    if not user_email:
        return jsonify({"error": "Usuário não autenticado"}), 401

    with sqlite3.connect('database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                cliente, telefone_cliente, email_cliente,
                produto_nome, valor as produto_preco,
                criado_em as data_venda
            FROM pagamentos
            WHERE user_email = ?
            ORDER BY criado_em DESC
        ''', (user_email,))
        for row in cursor.fetchall():
            vendas.append({
                "cliente": row["cliente"],
                "telefone_cliente": row["telefone_cliente"],
                "email_cliente": row["email_cliente"],
                "produto_nome": row["produto_nome"],
                "produto_preco": row["produto_preco"],
                "data_venda": row["data_venda"]
            })
    return jsonify(vendas)

@app.route('/api/gerar-modelo', methods=['POST'])
def gerar_modelo():
    data = request.json
    descricao = data.get('descricao', '')
    if not descricao:
        return jsonify({"error": "Descrição não enviada!"}), 400

    api_key = 'sk-shsjLZnxMfiJfxS6o25zqHzmBXXafZnahYFeV7l2S9U4Opi9'
    url = "https://api.stability.ai/v2beta/stable-image/generate/core"

    # multipart/form-data
    multipart_data = {
        "prompt": (None, descricao),
        "model_id": (None, "stable-diffusion-xl-1024-v1-0"),
        "output_format": (None, "png"),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",  # ou "image/*" para pegar imagem binária
    }

    response = requests.post(url, files=multipart_data, headers=headers)
    print('status:', response.status_code)
    print('body:', response.text)
    if response.status_code == 200:
        output = response.json()
        image_base64 = output['image']
        image_url = f"data:image/png;base64,{image_base64}"
        return jsonify({"image_url": image_url})
    else:
        return jsonify({"error": "Falha na geração", "debug": response.text}), 400

@app.route('/api/add_content_produto', methods=['POST'])
def add_content_produto():
    # Autenticação: precisa estar logado
    if "user" not in session or "email" not in session["user"]:
        return jsonify({"error": "Usuário não autenticado"}), 401

    email_usuario = session["user"]["email"]
    nome = request.form.get("nome", "").strip()
    produto_uuid = request.form.get("produto_id") or request.form.get("produto_uuid")

    # Validação básica
    if not nome or not produto_uuid or 'file' not in request.files:
        return jsonify({"error": "Dados insuficientes"}), 400

    file = request.files['file']
    UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']
    from datetime import datetime
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        conteudo_url = f"/{filepath}"
    else:
        return jsonify({"error": "Arquivo inválido ou ausente"}), 400

    data_envio = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Insere no banco
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO conteudos (email_usuario, nome, conteudo, produto_uuid, data_envio)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email_usuario, nome, conteudo_url, produto_uuid, data_envio)
        )
        conn.commit()
        content_id = cursor.lastrowid
        conn.close()
    except Exception as e:
        return jsonify({"error": f"Erro ao salvar no banco: {e}"}), 500

    return jsonify({
        "success": True,
        "id": content_id,
        "email_usuario": email_usuario,
        "nome": nome,
        "conteudo": conteudo_url,
        "produto_uuid": produto_uuid,
        "data_envio": data_envio
    }), 200

@app.route('/editar_produto/<product_uuid>', methods=['GET'])
def editar_produto(product_uuid):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM produtos WHERE uuid = ?", (product_uuid,))
    produto = cursor.fetchone()
    conn.close()
    if not produto:
        return jsonify({'error': 'Produto não encontrado'}), 404

    # Ajuste os índices conforme o schema da sua tabela
    produto_data = {
        'id': produto[0],
        'nome': produto[1],
        'preco': produto[2],
        'imagem': produto[3],
        'usuario_email': produto[4],
        'descricao': produto[5],
        'url_checkout': produto[6],
        'url_flow': produto[7],
        'uuid': produto[8],
        'categoria': produto[9],
        'quantidade_vendas': produto[10]
    }
    # Segurança: só o dono pode editar
    if produto[4].strip().lower() != session['user']['email'].strip().lower():
        return jsonify({'error': 'Acesso negado'}), 403

    return jsonify(produto_data)

@app.route('/excluir_produto/<product_uuid>', methods=['DELETE'])
def excluir_produto(product_uuid):
    if 'user' not in session or 'email' not in session['user']:
        return jsonify({'error': 'Não autenticado'}), 401

    user_email = session['user']['email']

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM produtos WHERE uuid = ? AND usuario_email = ?', (product_uuid, user_email))
    produto = cursor.fetchone()
    if not produto:
        conn.close()
        return jsonify({'error': 'Produto não encontrado ou acesso negado'}), 404

    cursor.execute('DELETE FROM produtos WHERE uuid = ?', (product_uuid,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Produto excluído com sucesso!'})

@app.route('/salvar_edicao_produto', methods=['POST'])
def salvar_edicao_produto():
    if 'user' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    user_email = session['user']['email']
    product_uuid = request.form.get('uuid')
    if not product_uuid:
        return jsonify({'error': 'Produto não identificado'}), 400

    # Conectar ao banco e buscar o produto
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM produtos WHERE uuid = ?", (product_uuid,))
    produto = cursor.fetchone()
    if not produto:
        conn.close()
        return jsonify({'error': 'Produto não encontrado'}), 404

    # Segurança: só o dono pode editar
    if produto[4].strip().lower() != user_email.strip().lower():
        conn.close()
        return jsonify({'error': 'Acesso negado'}), 403

    # Dados do formulário
    nome = request.form.get('nome')
    preco = request.form.get('preco')
    descricao = request.form.get('descricao')
    categoria = request.form.get('categoria')

    # Atualizar imagem só se enviada
    imagem = produto[3]
    if 'imagem' in request.files and request.files['imagem']:
        file = request.files['imagem']
        if file and file.filename:
            filename = secure_filename(file.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'])
            os.makedirs(path, exist_ok=True)
            file_path = os.path.join(path, filename)
            file.save(file_path)
            imagem = os.path.join('uploads', filename)  # ajuste o path se necessário

    # Atualizar no banco
    cursor.execute("""
        UPDATE produtos
        SET nome=?, preco=?, imagem=?, descricao=?, categoria=?
        WHERE uuid=?
    """, (nome, preco, imagem, descricao, categoria, product_uuid))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Produto atualizado com sucesso!'})

@app.route("/api/meus_bots")
def api_meus_bots():
    if 'user' not in session or 'email' not in session['user']:
        return jsonify([])
    user_email = session['user']['email']
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT *, COALESCE(ativo, 1) as ativo FROM bots WHERE user_email=? ORDER BY created_at DESC", (user_email,))
    except sqlite3.OperationalError:
        cursor.execute("SELECT * FROM bots WHERE user_email=? ORDER BY created_at DESC", (user_email,))
    bots = []
    for row in cursor.fetchall():
        bot = dict(row)
        bot['link_username'] = extract_bot_username(bot['bot_token'])
        bots.append(bot)
    conn.close()
    return jsonify(bots)

@app.route("/pausar_bot/<int:bot_id>", methods=["POST"])
def pausar_bot(bot_id):
    if 'user' not in session or 'email' not in session['user']:
        return redirect(url_for('login'))
    user_email = session['user']['email']
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT uuid FROM bots WHERE id=? AND user_email=?", (bot_id, user_email))
    row = cursor.fetchone()
    product_uuid = row["uuid"] if row else None
    try:
        conn.execute("UPDATE bots SET ativo=0 WHERE id=? AND user_email=?", (bot_id, user_email))
        conn.commit()
    except Exception as e:
        print("Erro ao pausar bot:", e)
    conn.close()
    if product_uuid:
        return redirect(url_for("bot", product_uuid=product_uuid))
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/ativar_bot/<int:bot_id>", methods=["POST"])
def ativar_bot(bot_id):
    if 'user' not in session or 'email' not in session['user']:
        return redirect(url_for('login'))
    user_email = session['user']['email']
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT uuid FROM bots WHERE id=? AND user_email=?", (bot_id, user_email))
    row = cursor.fetchone()
    product_uuid = row["uuid"] if row else None
    try:
        conn.execute("UPDATE bots SET ativo=1 WHERE id=? AND user_email=?", (bot_id, user_email))
        conn.commit()
    except Exception as e:
        print("Erro ao ativar bot:", e)
    conn.close()
    if product_uuid:
        return redirect(url_for("bot", product_uuid=product_uuid))
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/excluir_bot/<int:bot_id>", methods=["POST"])
def excluir_bot(bot_id):
    if 'user' not in session or 'email' not in session['user']:
        return redirect(url_for('login'))
    user_email = session['user']['email']
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT uuid FROM bots WHERE id=? AND user_email=?", (bot_id, user_email))
    row = cursor.fetchone()
    product_uuid = row["uuid"] if row else None
    conn.execute("DELETE FROM bots WHERE id=? AND user_email=?", (bot_id, user_email))
    conn.commit()
    conn.close()
    if product_uuid:
        return redirect(url_for("bot", product_uuid=product_uuid))
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/editar_bot/<int:bot_id>", methods=["GET", "POST"])
def editar_bot(bot_id):
    if 'user' not in session or 'email' not in session['user']:
        return redirect(url_for('login'))
    user_email = session['user']['email']
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bots WHERE id=? AND user_email=?", (bot_id, user_email))
    bot = cursor.fetchone()
    if not bot:
        conn.close()
        return redirect(url_for("dashboard"))

    mensagens = []
    if bot['mensagens']:
        try:
            mensagens = json.loads(bot['mensagens'])
        except Exception:
            mensagens = []

    if request.method == "POST":
        bot_name = request.form.get('bot_name')
        bot_token = request.form.get('bot_token')
        mensagens_form = request.form.getlist('mensagens')
        mensagens_form = [m for m in mensagens_form if m.strip()]
        mensagens_json = json.dumps(mensagens_form)
        botao_texto = request.form.get('botao_texto', 'QUERO TER ACESSO AO VIP')
        group_id = request.form.get('group_id')
        link_vip = request.form.get('link_vip')
        oferta = request.form.get('oferta')
        foto = bot['photo_filename']
        if 'bot_photo' in request.files:
            file = request.files['bot_photo']
            if file and file.filename:
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], 'bots')
                os.makedirs(path, exist_ok=True)
                file_path = os.path.join(path, filename)
                file.save(file_path)
                foto = f"bots/{filename}"
        cursor.execute("""
            UPDATE bots
               SET bot_name=?, bot_token=?, mensagens=?, botao_texto=?, group_id=?, link_vip=?, oferta=?, photo_filename=?
             WHERE id=? AND user_email=?
        """, (bot_name, bot_token, mensagens_json, botao_texto, group_id, link_vip, oferta, foto, bot_id, user_email))
        conn.commit()
        product_uuid = bot["uuid"]
        conn.close()
        return redirect(url_for("bot", product_uuid=product_uuid))

    conn.close()
    return render_template("editar_bot.html", bot=dict(bot), mensagens=mensagens)

@app.route('/api/get_content', methods=['GET'])
def get_content():
    # Garante que o usuário está autenticado
    if 'user' not in session or 'email' not in session['user']:
        return jsonify({'error': 'Usuário não autenticado'}), 401

    email_usuario = session['user']['email']

    try:
        conn = connect_db()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email_usuario, nome, conteudo, produto_uuid, data_envio FROM conteudos WHERE email_usuario = ?",
            (email_usuario,)
        )
        conteudos = cursor.fetchall()
        conn.close()

        # Transforma os resultados em uma lista de dicionários
        conteudos_list = [
            {
                "id": row["id"],
                "email_usuario": row["email_usuario"],
                "nome": row["nome"],
                "conteudo": row["conteudo"],
                "produto_uuid": row["produto_uuid"],
                "data_envio": row["data_envio"]
            }
            for row in conteudos
        ]

        return jsonify(conteudos_list), 200

    except Exception as e:
        return jsonify({"error": f"Erro ao buscar conteúdos: {e}"}), 500

@app.route('/api/criar_bot', methods=['POST'])
def api_criar_bot():
    import json

    # Garante usuário logado
    if 'user' not in session or 'email' not in session['user']:
        return jsonify({'error': 'Usuário não autenticado'}), 401

    user_email = session['user']['email']

    bot_name = request.form.get('bot_name')
    bot_token = request.form.get('bot_token')
    group_id = request.form.get('group_id')
    link_vip = request.form.get('link_vip')
    oferta = request.form.get('oferta')
    photo_filename = None

    # Pega o product_uuid enviado pelo formulário (input hidden)
    product_uuid = request.form.get('product_uuid')

    # Novos campos para múltiplas mensagens e botão customizado
    mensagens = request.form.getlist('mensagens')  # lista de mensagens automáticas
    mensagens = [m for m in mensagens if m.strip()]  # remove vazias
    mensagens_json = json.dumps(mensagens)
    botao_texto = request.form.get('botao_texto', 'QUERO TER ACESSO AO VIP')

    # Validação básica de campos do bot
    if not bot_name or not bot_token or not mensagens:
        return jsonify({'error': 'Preencha todos os campos obrigatórios!'}), 400

    if not product_uuid:
        return jsonify({'error': 'Produto não selecionado!'}), 400

    # Upload da foto do bot (opcional)
    upload_folder = os.path.join(app.root_path, 'static', 'bots')
    os.makedirs(upload_folder, exist_ok=True)
    if 'bot_photo' in request.files:
        file = request.files['bot_photo']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            photo_filename = f"bots/{filename}"

    try:
        conn = connect_db()
        cursor = conn.cursor()
        # Verifica se existe este produto E se ele pertence ao usuário logado
        cursor.execute('SELECT uuid FROM produtos WHERE uuid = ? AND usuario_email = ?', (product_uuid, user_email))
        produto = cursor.fetchone()
        if not produto:
            conn.close()
            return jsonify({'error': 'Produto não encontrado ou não pertence ao usuário!'}), 403

        # Agora insere o bot vinculado ao product_uuid, com mensagens e botão customizados
        cursor.execute('''
            INSERT INTO bots
                (user_email, bot_name, bot_token, mensagens, botao_texto, group_id, photo_filename, link_vip, oferta, uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_email, bot_name, bot_token, mensagens_json, botao_texto,
            group_id, photo_filename, link_vip, oferta, product_uuid
        ))
        conn.commit()
        bot_id = cursor.lastrowid
        conn.close()
        return jsonify({'success': True, 'bot_id': bot_id}), 201
    except Exception as e:
        return jsonify({'error': f'Erro ao salvar bot: {e}'}), 500

@app.route('/criar_bot/<product_uuid>')
def criar_bot_form(product_uuid):
    # Busca o produto pelo UUID na tabela produtos
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM produtos WHERE uuid = ?', (product_uuid,))
    produto = cursor.fetchone()
    conn.close()

    if not produto:
        return "Produto não encontrado", 404

    produto_info = {
        "id": produto["id"],
        "nome": produto["nome"],
        "preco": produto["preco"],
        "uuid": produto["uuid"]
        # adicione outros campos que quiser exibir no template
    }

    return render_template(
        "bot.html",
        produto=produto_info,
        produto_nome=produto["nome"]
    )

@app.route('/modelo-ia')
def modelo_ia():
	return render_template('geraria.html')

@app.route('/acessar_conteudos')
def acessar_conteudos():
	return render_template('login_acesso.html')

@app.route('/acesso-conteudos')
def acesso_conteudos():
    if 'cliente_email' not in session or 'cliente_key' not in session:
        return redirect(url_for('acessar_conteudos'))

    cliente_email = session['cliente_email']
    access_key = session['cliente_key']

    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Buscar todos os produtos que o cliente tem acesso
    cursor.execute("""
        SELECT produto_uuid FROM acessos
        WHERE email = ? AND access_key = ?
    """, (cliente_email, access_key))
    produto_uuids = [row['produto_uuid'] for row in cursor.fetchall() if row['produto_uuid']]

    produtos = []
    conteudos = []

    if produto_uuids:
        placeholders = ','.join(['?'] * len(produto_uuids))

        # 2. Buscar detalhes dos produtos
        cursor.execute(f"""
            SELECT * FROM produtos
            WHERE uuid IN ({placeholders})
        """, produto_uuids)
        produtos = cursor.fetchall()

        # 3. Buscar conteúdos associados aos produtos
        cursor.execute(f"""
            SELECT * FROM conteudos
            WHERE produto_uuid IN ({placeholders})
        """, produto_uuids)
        conteudos = cursor.fetchall()

    conn.close()

    return render_template(
        'painelcliente.html',
        produtos=produtos,
        conteudos=conteudos
    )


@app.route('/registrar_chave', methods=['POST'])
def registrar_chave():
    data = request.get_json()
    email = data.get('email')
    produto_id = data.get('produto_id')  # produto_id vem do front ou do contexto do backend

    if not email or not produto_id:
        return jsonify({"error": "email e produto_id obrigatórios"}), 400

    # Busca o produto_uuid no banco de dados usando produto_id
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT uuid FROM produtos WHERE id = ?", (produto_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return jsonify({"error": "Produto não encontrado"}), 404
    produto_uuid = result[0]

    access_key = secrets.token_urlsafe(32)
    chave_final = inserir_acesso(email, access_key, produto_uuid)

    # Envia a chave por email
    try:
        enviar_chave_por_email(email, chave_final)
    except Exception as e:
        print(f"Erro ao enviar email: {e}")

    conn.close()
    return jsonify({
        "access_key": chave_final
    })

@app.route('/painel_auth', methods=['POST'])
def painel_auth():
    data = request.get_json()
    chave = data.get('access_key')
    email = data.get('email')
    if not chave or not email:
        return jsonify({"error": "E-mail e chave obrigatórios"}), 400

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM acessos WHERE email = ? AND access_key = ?", (email, chave))
    resultado = cursor.fetchone()
    conn.close()
    if resultado:
        session['cliente_email'] = email
        session['cliente_key'] = chave
        return jsonify({"status": "ok", "msg": "Acesso liberado"})
    else:
        return jsonify({"error": "Chave ou e-mail inválidos"}), 403

@app.route('/criar_pagamento_pix', methods=['POST'])
def criar_pagamento_pix():
    try:
        data = request.json
        produto_id = data.get('id')
        cliente_nome = data.get('nome')
        cliente_snome = data.get('sobrenome')
        cliente_email = data.get('email')
        cliente_celular = data.get('celular')
        cliente_doc = data.get('cpf')
        id_transacao = str(uuid.uuid4())
        status = 'pendente'

        if not produto_id:
            return jsonify({"error": "ID do produto não fornecido"}), 400

        # Buscar o produto NO BANCO, incluindo o email do usuário dono do produto
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT nome, preco, uuid, usuario_email FROM produtos WHERE id = ?', (produto_id,)
        )
        produto = cursor.fetchone()

        if not produto:
            conn.close()
            return jsonify({"error": "Produto não encontrado"}), 404

        produto_nome, produto_preco, produto_uuid, user_email = (
            produto['nome'],
            produto['preco'],
            produto['uuid'],
            produto['usuario_email']  # aqui pega o email do criador do produto
        )

        payment_data = {
            "transaction_amount": produto_preco,
            "description": produto_nome,
            "payment_method_id": "pix",
            "payer": {
                "email": cliente_email,
                "first_name": cliente_nome,
                "last_name": cliente_snome,
                "identification": {
                    "type": "CPF",
                    "number": cliente_doc
                }
            }
        }

        payment = mp.payment().create(payment_data)
        payment_response = payment["response"]

        if payment_response.get("status") == "pending":
            pix_data = payment_response["point_of_interaction"]["transaction_data"]
            payment_id = payment_response["id"]

            cliente_fullname = f"{cliente_nome} {cliente_snome}".strip()

            # INSERIR user_email (do criador do produto) no insert de pagamentos
            cursor.execute(
                '''INSERT INTO pagamentos (
                    id, produto_id, produto_nome, valor, status, qrcode_base64, qrcode_url, pix_copia_cola, uuid,
                    cliente, telefone_cliente, email_cliente, user_email
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    id_transacao, produto_id, produto_nome, produto_preco, "PENDENTE", pix_data['qr_code_base64'],
                    pix_data["qr_code"], pix_data["qr_code"], produto_uuid,
                    cliente_fullname, cliente_celular, cliente_email, user_email  # <-- aqui!
                )
            )

            cursor.execute(
                'UPDATE produtos SET quantidade_vendas = quantidade_vendas + 1 WHERE uuid = ?',
                (produto_uuid,)
            )

            conn.commit()
            conn.close()

            return jsonify({
                "paymentId": payment_id,
                "idTransacao": id_transacao,
                "qrcode": f"data:image/png;base64,{pix_data['qr_code_base64']}",
                "qrcode_url": pix_data["qr_code"]
            })
        else:
            error_message = payment_response.get("message", "Erro ao criar pagamento")
            conn.close()
            return jsonify({"error": error_message}), 400

    except Exception as e:
        print("Erro ao criar pagamento:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/verificar-pagamento', methods=['GET'])
def verificar_pagamento():
    try:
        # Recuperar o ID do pagamento do parâmetro de consulta (query parameter)
        payment_id = request.args.get('payment_id')

        if not payment_id:
            return jsonify({"error": "ID de pagamento não fornecido"}), 400

        # Chamar a API do Mercado Pago para verificar o status do pagamento
        payment = mp.payment().get(payment_id)

        # Log para ver a resposta completa da API
        print(f"Resposta completa da API do Mercado Pago: {payment}")

        payment_response = payment['response']
        payment_status = payment_response.get("status")

        # Verificar se o status do pagamento foi retornado corretamente
        if payment_status:
            # Retornar o status do pagamento
            return jsonify({
                "paymentId": payment_id,
                "status": payment_status
            })
        else:
            return jsonify({"error": "Status do pagamento não encontrado"}), 400

    except Exception as e:
        print("Erro ao verificar pagamento:", str(e))
        return jsonify({"error": "Erro ao verificar pagamento: " + str(e)}), 500

@app.route('/atualizar_pagamento', methods=['POST'])
def atualizar_pagamento():
    try:
        # Receber o ID do pagamento e o novo status
        data = request.json
        payment_id = data.get('payment_id')
        novo_status = data.get('status')

        if not payment_id or not novo_status:
            return jsonify({"error": "ID do pagamento ou status não fornecido"}), 400

        # Conectar ao banco de dados
        conn = connect_db()
        cursor = conn.cursor()

        # Atualizar o status do pagamento no banco de dados
        cursor.execute('UPDATE pagamentos SET status = ? WHERE id = ?', (novo_status, payment_id))
        conn.commit()
        conn.close()

        return jsonify({"message": "Pagamento atualizado com sucesso"}), 200

    except Exception as e:
        print("Erro ao atualizar pagamento:", str(e))
        return jsonify({"error": "Erro ao atualizar pagamento: " + str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Dados enviados pelo Mercado Pago
        webhook_data = request.json

        if webhook_data and webhook_data.get("type") == "payment":
            payment_id = webhook_data["data"]["id"]

            # Consulta o pagamento para verificar o status
            payment = mp.payment().get(payment_id)
            payment_status = payment["response"]["status"]

            if payment_status == "approved":
                # Atualize o status do pagamento no banco ou sistema
                return jsonify({"message": "Pagamento aprovado"}), 200

        return jsonify({"message": "Webhook recebido"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/criar_pagamento_pix_telegram', methods=['POST'])
def criar_pagamento_pix_telegram():
    try:
        data = request.json
        produto_uuid = data.get('uuid')
        produto_nome = data.get('produto_nome')
        telegram_id = data.get('telegram_id')
        user_email = data.get('user_email')
        bot_id = data.get('bot_id')

        print(f"[DEBUG] Dados recebidos: {data}")  # LOG para debug

        if not produto_uuid or not produto_nome or not telegram_id:
            return jsonify({"error": "Dados insuficientes: uuid, produto_nome e telegram_id são obrigatórios"}), 400

        id_transacao = str(uuid.uuid4())

        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            'SELECT id, usuario_email, preco FROM produtos WHERE uuid = ?', (produto_uuid,)
        )
        produto = cursor.fetchone()
        if not produto:
            conn.close()
            return jsonify({"error": "Produto não encontrado"}), 404

        produto_id = produto["id"]
        preco = produto["preco"]
        dono_email = produto["usuario_email"] if produto["usuario_email"] else user_email

        payment_data = {
            "transaction_amount": float(preco),
            "description": produto_nome,
            "payment_method_id": "pix",
            "payer": {
                "email": "telegram@bot.com",
                "first_name": "Telegram",
                "last_name": "User",
                "identification": {
                    "type": "CPF",
                    "number": "00000000191"
                }
            },
            "external_reference": id_transacao
        }

        payment = mp.payment().create(payment_data)
        payment_response = payment["response"]

        if payment_response.get("status") == "pending":
            pix_data = payment_response["point_of_interaction"]["transaction_data"]
            payment_id = payment_response["id"]

            # INSERIR PAGAMENTO NO BANCO
            cursor.execute(
                '''INSERT INTO pagamentos (
                    id, bot_id, produto_id, produto_nome, valor, status, qrcode_base64, qrcode_url, pix_copia_cola, uuid,
                    cliente, telefone_cliente, email_cliente, user_email, telegram_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    id_transacao, bot_id, produto_id, produto_nome, preco, "PENDENTE",
                    pix_data['qr_code_base64'], pix_data["qr_code"], pix_data["qr_code"], produto_uuid,
                    "Telegram User", None, "telegram@bot.com", dono_email, telegram_id
                )
            )

            # INCREMENTA QUANTIDADE DE VENDAS
            cursor.execute(
                'UPDATE produtos SET quantidade_vendas = COALESCE(quantidade_vendas, 0) + 1 WHERE uuid = ?',
                (produto_uuid,)
            )

            conn.commit()
            conn.close()

            return jsonify({
                "paymentId": payment_id,
                "idTransacao": id_transacao,
                "qrcode": f"data:image/png;base64,{pix_data['qr_code_base64']}",
                "pix_copia_cola": pix_data["qr_code"]
            })
        else:
            error_message = payment_response.get("message", "Erro ao criar pagamento")
            conn.close()
            return jsonify({"error": error_message}), 400

    except Exception as e:
        print("Erro ao criar pagamento:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/salvar_produto', methods=['POST'])
def salvar_produto():
    # Verifica se o usuário está logado
    if 'user' not in session or 'email' not in session['user']:
        return jsonify({'error': 'Usuário não autenticado!'}), 401
    try:
        nome = request.form.get('nome')
        preco = request.form.get('preco')
        descricao = request.form.get('descricao')
        categoria = request.form.get('categoria')
        usuario_email = session['user']['email']
        imagem = request.files.get('imagem')  # Arquivo de imagem enviado

        # DEBUG: Mostra o que veio do form
        print("DEBUG FORM DATA:")
        print("  nome:", nome, type(nome))
        print("  preco:", preco, type(preco))
        print("  descricao:", descricao, type(descricao))
        print("  categoria:", categoria, type(categoria))
        print("  usuario_email:", usuario_email, type(usuario_email))
        print("  imagem:", imagem.filename if imagem else None)

        # Verificar se os campos obrigatórios estão preenchidos
        if not nome or not preco or not descricao or not usuario_email:
            return jsonify({'error': 'Todos os campos obrigatórios devem ser preenchidos!'}), 400

        # Validar o preço como um número
        try:
            preco = float(preco)
        except ValueError:
            return jsonify({'error': 'Preço inválido!'}), 400

        # Validação SEGURA no backend: preço mínimo de R$ 5,00
        if preco < 5:
            return jsonify({'error': 'O preço mínimo para cadastrar um produto é R$ 5,00.'}), 400

        # Salvar a imagem no servidor, se fornecida
        if imagem and imagem.filename.strip() != "":
            filename = secure_filename(imagem.filename)
            imagem_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            imagem.save(imagem_path)
        else:
            imagem_path = ""

        # Geração da URL de checkout
        produto_uuid = str(uuid.uuid4())
        url_checkout = f'/checkout/{produto_uuid}'
        url_flow = f'{produto_uuid}/flow'

        # Limpeza dos valores antes de salvar
        nome = str(nome).strip()
        imagem_path = str(imagem_path).strip()
        usuario_email = str(usuario_email).strip()
        descricao = str(descricao).strip()
        url_checkout = str(url_checkout).strip()
        url_flow = str(url_flow).strip()

        # DEBUG: Mostra o que vai para o banco
        print("DEBUG DADOS PARA O BANCO:")
        print("  nome:", nome, type(nome))
        print("  preco:", preco, type(preco))
        print("  imagem_path:", imagem_path, type(imagem_path))
        print("  usuario_email:", usuario_email, type(usuario_email))
        print("  descricao:", descricao, type(descricao))
        print("  url_checkout:", url_checkout, type(url_checkout))
        print("  url_flow:", url_flow, type(url_flow))
        print("  produto_uuid:", produto_uuid, type(produto_uuid))
        print("  categoria:", categoria, type(categoria))

        # Inserir os dados no banco de dados
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO produtos (nome, preco, imagem, usuario_email, descricao, url_checkout, url_flow, uuid, categoria)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (nome, preco, imagem_path, usuario_email, descricao, url_checkout, url_flow, produto_uuid, categoria)
        )
        conn.commit()
        conn.close()

        return jsonify({
            'success': 'Produto salvo com sucesso!',
            'url_checkout': url_checkout,
            'url_flow': url_flow,
            'uuid': produto_uuid,
        }), 201

    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'error': f'Ocorreu um erro: {str(e)}'}), 500

@app.route('/afiliado/<uuid>', methods=['GET'])
def afiliado(uuid):
	return render_template('sejaafiliado.html')

@app.route('/checkout/<uuid>', methods=['GET'])
def checkout(uuid):
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Busca o produto pelo UUID contido na URL de checkout
    cursor.execute(
        'SELECT id, nome, descricao, preco, imagem, url_flow FROM produtos WHERE url_checkout LIKE ?',
        (f'%/checkout/{uuid}',)
    )
    produto = cursor.fetchone()
    conn.close()

    if not produto:
        return "Produto não encontrado", 404

    product_details = {
        'id': produto['id'],
        'nome': produto['nome'],
        'descricao': produto['descricao'],
        'preco': produto['preco'],
        'imagem': produto['imagem'],
        'url_flow': produto['url_flow'],
        'uuid': uuid
    }

    return render_template('checkout.html', produto=product_details)

@app.route('/<uuid>/flow', methods=['GET'])
def fluxograma(uuid):
    # Conexão com o banco de dados
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        # Busca o produto pelo UUID (extraído da URL, está como parte de url_checkout)
        cursor.execute('''
            SELECT id, nome, preco, imagem, quantidade_vendas, usuario_email, descricao, url_checkout, url_flow 
            FROM produtos 
            WHERE url_checkout LIKE ?
        ''', (f'%/checkout/{uuid}',))
        produto = cursor.fetchone()

    # Verifica se o produto foi encontrado
    if not produto:
        return "Produto não encontrado", 404

    # Dados do produto extraídos do banco
    product_details = {
        'id': produto[0],
        'nome': produto[1],
        'preco': produto[2],
        'imagem': produto[3],
        'quantidade_vendas': produto[4],
        'usuario_email': produto[5],
        'descricao': produto[6],
        'url_checkout': produto[7],
        'url_flow': produto[8],
        'uuid': uuid
    }

    # Renderiza a página de fluxograma com os detalhes do produto
    return render_template('flow.html', produto=product_details)

@app.route('/modelos/<pasta>/<subpasta>/<filename>')
def serve_modelos(pasta, subpasta, filename):
    caminho = os.path.join(app.root_path, 'modelos', pasta, subpasta, filename)
    if os.path.exists(caminho):
        return send_from_directory(os.path.dirname(caminho), os.path.basename(caminho))
    else:
        return "Arquivo não encontrado", 404

@app.route('/aulas')
def aulas():
    if 'user' not in session:
         return redirect(url_for('login'))
    return render_template('aulas.html', user=session['user'])

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/afiliados')
def aff():
    if 'user' not in session:
         return redirect(url_for('login'))
    return render_template('afiliados.html', user=session['user'])

@app.route('/vendas', methods=['GET', 'POST'])
def vendas():
    if 'user' not in session:
         return redirect(url_for('login'))
    return render_template('vendas.html', user=session['user'])

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_email = session['user']['email']

    # Conexão com banco via função segura
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Total de vendas
    cursor.execute('SELECT SUM(quantidade_vendas) FROM produtos WHERE usuario_email = ?', (user_email,))
    total_sales = cursor.fetchone()[0] or 0

    # Receita gerada
    cursor.execute('SELECT SUM(preco * quantidade_vendas) FROM produtos WHERE usuario_email = ?', (user_email,))
    receita_gerada = cursor.fetchone()[0] or 0.0

    # Total de produtos vendidos
    cursor.execute('SELECT COUNT(*) FROM produtos WHERE usuario_email = ? AND quantidade_vendas > 0', (user_email,))
    produtos_vendidos = cursor.fetchone()[0] or 0

    # Busca bots do usuário
    cursor.execute('SELECT * FROM bots WHERE user_email = ?', (user_email,))
    bots_rows = cursor.fetchall()

    user_bots = []
    for row in bots_rows:
        bot = {
            'id': row['id'],
            'user_email': row['user_email'],
            'bot_name': row['bot_name'],
            'bot_token': row['bot_token'],
            'welcome_message': row['welcome_message'],
            'confirmation_keyword': row['confirmation_keyword'],
            'confirmation_message': row['confirmation_message'],
            'group_id': row['group_id'],
            'photo_filename': row['photo_filename'],
            'created_at': row['created_at'],
            'link_username': (row['bot_token'].split(":")[0] if ":" in row['bot_token'] else row['bot_token'])
        }
        user_bots.append(bot)

    conn.close()

    # Renderiza com variáveis
    return render_template(
        'dashboard.html',
        user=session['user'],
        total_sales=total_sales,
        receita_gerada=receita_gerada,
        produtos_vendidos=produtos_vendidos,
        user_bots=user_bots
    )

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    if 'user' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    user_email = session['user']['email']
    conn = get_db()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE user_email = ?", (user_email,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in tasks])

def get_db():
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/tasks', methods=['POST'])
def add_task():
    if 'user' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    user_email = session['user']['email']
    data = request.json
    title = data.get('title')
    category = data.get('category')
    priority = data.get('priority')
    due_date = data.get('due_date')
    if not title:
        return jsonify({'error': 'Título obrigatório'}), 400
    conn = get_db()
    conn.execute(
        "INSERT INTO tasks (user_email, title, category, priority, due_date, completed) VALUES (?, ?, ?, ?, ?, 0)",
        (user_email, title, category, priority, due_date)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True}), 201

@app.route('/api/tasks/<int:task_id>', methods=['PATCH'])
def update_task(task_id):
    if 'user' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    user_email = session['user']['email']
    data = request.json
    completed = data.get('completed')
    # Você pode adicionar outros campos se quiser
    conn = get_db()
    conn.execute(
        "UPDATE tasks SET completed = ? WHERE id = ? AND user_email = ?",
        (completed, task_id, user_email)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if 'user' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    user_email = session['user']['email']
    conn = get_db()
    conn.execute(
        "DELETE FROM tasks WHERE id = ? AND user_email = ?",
        (task_id, user_email)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})

def get_receita_gerada(user_email):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(preco * quantidade_vendas) FROM produtos WHERE usuario_email = ?', (user_email,))
        receita_gerada = cursor.fetchone()[0]
        if receita_gerada is None:
            receita_gerada = 0.0
    return receita_gerada

def get_saldo_disponivel(user_email):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        # Receita total (vendas)
        cursor.execute('SELECT SUM(preco * quantidade_vendas) FROM produtos WHERE usuario_email = ?', (user_email,))
        receita_gerada = cursor.fetchone()[0] or 0.0
        # Total de saques já realizados (exceto cancelados)
        cursor.execute("SELECT SUM(valor) FROM saques WHERE user_email = ? AND status != 'cancelado'", (user_email,))
        total_sacado = cursor.fetchone()[0] or 0.0
    saldo_disponivel = receita_gerada - total_sacado
    return round(saldo_disponivel, 2)

@app.route('/saque', methods=['GET', 'POST'])
def saque():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_email = session['user']['email']
    saldo_disponivel = get_saldo_disponivel(user_email)

    if request.method == 'POST':
        nome_completo = request.form.get('nome')
        banco        = request.form.get('banco')
        tipo_chave   = request.form.get('tipo_chave')
        chave_pix    = request.form.get('chave')
        valor_str    = request.form.get('valor')

        if not valor_str:
            return render_template(
                'saque.html',
                user=session['user'],
                saldo_disponivel=saldo_disponivel,
                mensagem='Erro: campo valor não enviado.'
            )
        try:
            valor = float(valor_str)
        except Exception as e:
            return render_template(
                'saque.html',
                user=session['user'],
                saldo_disponivel=saldo_disponivel,
                mensagem='Erro: valor inválido.'
            )

        # Verifica se há saldo suficiente antes de permitir o saque
        if valor > saldo_disponivel:
            return render_template(
                'saque.html',
                user=session['user'],
                saldo_disponivel=saldo_disponivel,
                mensagem='Erro: você não possui saldo suficiente para esse saque.'
            )

        status       = 'pendente'
        data_pedido  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO saques (user_email, nome_completo, chave_pix, data_pedido, status, banco, tipo_chave, valor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_email, nome_completo, chave_pix, data_pedido, status, banco, tipo_chave, valor))
            conn.commit()

        # Atualiza o saldo para exibir o novo valor após o saque
        novo_saldo = get_saldo_disponivel(user_email)
        return render_template(
            'saque.html',
            user=session['user'],
            saldo_disponivel=novo_saldo,
            mensagem=f'Solicitação de saque enviada com sucesso! Valor: R$ {valor:.2f}'
        )

    # GET: Exibe o saldo disponível
    return render_template(
        'saque.html',
        user=session['user'],
        saldo_disponivel=saldo_disponivel
    )

def get_receita_gerada(user_email):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(preco * quantidade_vendas) FROM produtos WHERE usuario_email = ?', (user_email,))
        receita_gerada = cursor.fetchone()[0]
        if receita_gerada is None:
            receita_gerada = 0.0
    return receita_gerada

@app.route('/10012006/admin/saques/financeiro')
def painel_saques():
    import sqlite3
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Saques pendentes
    cur.execute("SELECT * FROM saques WHERE status!='liberado' ORDER BY data_pedido DESC")
    saques_pendentes = cur.fetchall()
    # Saques já liberados
    cur.execute("SELECT * FROM saques WHERE status='liberado' ORDER BY data_pedido DESC")
    saques_liberados = cur.fetchall()
    conn.close()
    return render_template(
        'painelsaque.html',
        saques_pendentes=saques_pendentes,
        saques_liberados=saques_liberados
    )

@app.route('/flows', methods=['GET', 'POST'])
def flows():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        data = request.json
        flow_id = data.get('id', str(uuid.uuid4()))
        flow_name = data.get('name')
        flow_data = data.get('data')
        user_email = session['user']['email']

        flow_data_str = json.dumps(flow_data)  # Converte dict para string

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO fluxogramas (id, usuario_email, nome, dados)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, dados=excluded.dados
                ''', (flow_id, user_email, flow_name, flow_data_str))
                conn.commit()
                return jsonify({'message': 'Fluxograma salvo com sucesso!', 'id': flow_id}), 201
            except Exception as e:
                print('Erro ao salvar o fluxograma:', e)  # Log do erro
                return jsonify({'message': 'Erro ao salvar o fluxograma.'}), 500

    if request.method == 'GET':
        user_email = session['user']['email']
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, nome FROM fluxogramas WHERE usuario_email = ?
            ''', (user_email,))
            fluxos = cursor.fetchall()

        return render_template('flows.html', user=session['user'], fluxos=fluxos)

@app.route('/flow/<flow_id>', methods=['GET', 'DELETE'])
def load_or_delete_flow(flow_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    # Conexão com o banco de dados
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Se o método for DELETE
    if request.method == 'DELETE':
        cursor.execute("DELETE FROM fluxogramas WHERE id = ?", (flow_id,))
        conn.commit()
        conn.close()

        # Verifica se o fluxo foi realmente deletado
        if cursor.rowcount == 0:
            return jsonify({"message": "Fluxograma não encontrado ou não pertence ao usuário"}), 404

        return jsonify({"message": "Fluxograma excluído com sucesso!"}), 200

    # Se o método for GET
    elif request.method == 'GET':
        cursor.execute("SELECT * FROM fluxogramas WHERE id = ?", (flow_id,))
        flow = cursor.fetchone()
        conn.close()

        if flow:
            return render_template("flow.html", flow_id=flow["id"], flow_data=flow["dados"])
        else:
            return "Fluxograma não encontrado", 404

@app.route('/flow')
def flow():
    return render_template('flow.html', user=session['user'])

    user_email = session['user']['email']
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT dados, nome FROM fluxogramas WHERE id = ? AND usuario_email = ?
        ''', (flow_id, user_email))
        fluxo = cursor.fetchone()

    if not fluxo:
        return "Fluxograma não encontrado", 404

    return render_template('flow.html', user=session['user'], flow_id=flow_id, flow_data=fluxo[0], flow_name=fluxo[1])

@app.route('/membros/area/<product_uuid>')
def membros(product_uuid):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM produtos WHERE uuid = ?', (product_uuid,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        return "Produto não encontrado", 404

    # Verificar se o produto pertence ao usuário logado
    user_id = session['user']['email']  # Ajuste conforme a lógica de autenticação
    print(f"user_id: '{user_id}'")
    print(f"product[4]: '{product[4]}'")
    print(f"Comparação: {product[4] == user_id}")

    if product[4].strip().lower() != user_id.strip().lower():
        return "Acesso negado", 403

    product_details = {
        'id': product[0],
        'nome': product[1],
        'preco': product[2],
        'imagem': product[3],
        'email_dono': product[4],  # usuario_email
        'descricao': product[5],
        'url_checkout': product[6],
        'url_flow': product[7],
        'uuid': product[8],
        'categoria': product[9],
        'quantidade_vendas': product[10]
    }
    return render_template('area-membros.html', user=session.get('user', ''), product=product_details)

@app.route('/meus_bots/<product_uuid>')
def bot(product_uuid):
    if 'user' not in session or 'email' not in session['user']:
        return redirect(url_for('login'))

    user_email = session['user']['email']
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, nome, preco, uuid FROM produtos WHERE uuid = ? AND usuario_email = ?',
        (product_uuid, user_email)
    )
    produto = cursor.fetchone()
    conn.close()

    if not produto:
        # Passa apenas a flag para mostrar o alerta no template
        return render_template('meusbots.html', produto_nao_encontrado=True)

    produto_info = {
        'id': produto['id'],
        'nome': produto['nome'],
        'preco': produto['preco'],
        'uuid': produto['uuid']
    }
    return render_template('meusbots.html', produto=produto_info)

@app.route('/auth/google')
def auth_google():
    # Se estiver no Render, manda pra URL de produção
    return google.authorize_redirect(
        redirect_uri="https://modelify.onrender.com/auth/google/callback"
    )

@app.route('/auth/google/callback')
def auth_google_callback():
    try:
        token = google.authorize_access_token()
        user_info = google.parse_id_token(token, nonce=None)
        session['user'] = {'email': user_info['email']}

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO usuarios (nome, email, google_id)
                VALUES (?, ?, ?)
            ''', (user_info['name'], user_info['email'], user_info['sub']))
            conn.commit()

        return redirect(url_for("dashboard"))

    except Exception as e:
        print(f"Erro ao validar o token: {e}")
        return redirect(url_for("login"))

@app.route('/produtos')
def listar_produtos():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('SELECT id, nome, descricao, preco, imagem, url_checkout, url_flow FROM produtos')
    rows = cursor.fetchall()
    conn.close()

    produtos = []
    for row in rows:
        produtos.append({
            'id': row[0],
            'nome': row[1],
            'descricao': row[2],
            'preco': row[3],
            'imagem': row[4],
            'url_checkout': row[5],
            'url_flow': row[6]
        })

    return render_template('produtos.html', user=session.get('user'), produtos=produtos)

def get_produtos(email_usuario):
    conn = connect_db()
    conn.row_factory = sqlite3.Row  # Permite acessar por nome da coluna
    cursor = conn.cursor()
    # Filtra os produtos pelo email do usuário
    cursor.execute('SELECT * FROM produtos WHERE usuario_email = ?', (email_usuario,))
    produtos = cursor.fetchall()
    conn.close()
    return produtos

@app.route('/produtos_lista')
def produtos_lista():
    # Recupera o email do usuário armazenado no dicionário dentro da sessão
    user_info = session.get("user")
    email_usuario = user_info.get("email") if user_info else None

    if not email_usuario:
        app.logger.error("Usuário não autenticado. Email não encontrado na sessão.")
        return jsonify({'error': 'Usuário não autenticado'}), 401

    # Busca os produtos do usuário autenticado
    produtos = get_produtos(email_usuario)
    produtos_lista = []

    for produto in produtos:
        produto_dict = {
            'id': produto['id'],
            'uuid': produto['uuid'],
            'nome': produto['nome'],
            'preco': produto['preco'],
            'imagem': produto['imagem'],
            'quantidade_vendas': produto['quantidade_vendas'],
            'descricao': produto['descricao'],
            'url_checkout': produto['url_checkout'],
            'url_flow': produto['url_flow'],
            'categoria': produto['categoria']
        }
        produtos_lista.append(produto_dict)

    return jsonify(produtos_lista)

@app.route('/adicionar_produto', methods=['POST'])
def adicionar_produto():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        usuario_email = session['user']['email']
        data = request.get_json()

        # Extrai os dados do JSON enviado
        nome = data.get('nome', '').strip()
        preco = data.get('preco', None)
        url_checkout = data.get('url_checkout', '').strip()

        # Validações de campos obrigatórios
        if not nome or not url_checkout:
            return jsonify({"error": "Campos obrigatórios estão faltando!"}), 400

        try:
            preco = float(preco)
            if preco < 0:
                return jsonify({"error": "O preço não pode ser negativo!"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "O preço deve ser um número válido!"}), 400

        # Salvar os dados do produto no banco de dados
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO produtos (usuario_email, nome, preco, url_checkout)
                VALUES (?, ?, ?, ?)
            ''', (usuario_email, nome, preco, url_checkout))
            conn.commit()

        return jsonify({"message": "Produto salvo com sucesso!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/deletar_produto/<int:id>', methods=['DELETE'])
def deletar_produto(id):
    if 'user' not in session:
        return redirect(url_for('login'))

    usuario_email = session['user']['email']
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM produtos WHERE id = ? AND usuario_email = ?', (id, usuario_email))
        conn.commit()

    return jsonify({"message": "Produto excluído com sucesso!"})

@app.route('/acessar/produto/<uuid>')
def acessar_produto():
    return render_template('acessar-produto.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    return redirect(url_for('dashboard')) if 'user' in session else redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
