import sqlite3

db_path = "database.db"  # Altere se quiser outro nome ou caminho para o banco

schema = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    email TEXT UNIQUE,
    google_id TEXT
);

CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    preco REAL,
    imagem TEXT,
    usuario_email TEXT,
    descricao TEXT,
    url_checkout TEXT,
    url_flow TEXT,
    uuid TEXT UNIQUE,
    categoria TEXT,
    quantidade_vendas INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS acessos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    access_key TEXT,
    produto_uuid TEXT,
    criado_em TEXT
);

CREATE TABLE IF NOT EXISTS conteudos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_usuario TEXT,
    nome TEXT,
    conteudo TEXT,
    produto_uuid TEXT,
    data_envio TEXT
);

CREATE TABLE IF NOT EXISTS bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT,
    bot_name TEXT,
    bot_token TEXT,
    mensagens TEXT,
    botao_texto TEXT,
    group_id TEXT,
    photo_filename TEXT,
    link_vip TEXT,
    oferta TEXT,
    uuid TEXT,
    ativo INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    produto_uuid TEXT
);

CREATE TABLE IF NOT EXISTS pagamentos (
    id TEXT PRIMARY KEY,
    produto_id INTEGER,
    produto_nome TEXT,
    valor REAL,
    status TEXT,
    qrcode_base64 TEXT,
    qrcode_url TEXT,
    pix_copia_cola TEXT,
    uuid TEXT,
    cliente TEXT,
    telefone_cliente TEXT,
    email_cliente TEXT,
    user_email TEXT,
    bot_id INTEGER,
    telegram_id TEXT,
    link_entregue INTEGER DEFAULT 0,
    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT,
    title TEXT,
    category TEXT,
    priority TEXT,
    due_date TEXT,
    completed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS saques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT,
    nome_completo TEXT,
    chave_pix TEXT,
    data_pedido TEXT,
    status TEXT,
    banco TEXT,
    tipo_chave TEXT,
    valor REAL
);

CREATE TABLE IF NOT EXISTS fluxogramas (
    id TEXT PRIMARY KEY,
    usuario_email TEXT,
    nome TEXT,
    dados TEXT
);
"""

def create_database():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript(schema)
    conn.commit()
    conn.close()
    print(f"Banco de dados '{db_path}' criado/configurado com sucesso!")

if __name__ == "__main__":
    create_database()
