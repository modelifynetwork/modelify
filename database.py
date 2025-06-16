import sqlite3

# Conectar ao banco e criar tabelas se não existirem
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Tabela de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            email TEXT UNIQUE,
            google_id TEXT UNIQUE
        )
    ''')
    
    # Tabela de produtos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_email TEXT,
            nome TEXT,
            descricao TEXT,
            preco REAL,
            url_checkout TEXT,
            FOREIGN KEY(usuario_email) REFERENCES usuarios(email)
        )
    ''')
    
    conn.commit()
    conn.close()

# Executar a criação do banco ao importar este módulo
init_db()
