from flask import Flask, render_template, request, redirect, session, send_file, send_from_directory, jsonify
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from collections import defaultdict
from datetime import datetime
import sqlite3
import time
import unicodedata
import os
import shutil
import random
import string
import requests  # 🔥 ADICIONADO
import json       # 🔥 ADICIONADO
import hmac       # 🔥 ADICIONADO (para segurança do webhook)

# ================= CONFIGURAÇÃO =================
app = Flask(__name__)
app.secret_key = "yannykak_super_secreto_2026"

# ================= CONFIGURAÇÃO ZUMBOPAY =================
BASE_URL ="https://zumbopay.com/api/public/v1"
MERCHANT_ID = "MCH_642C490910"
API_KEY = "zk_live_f252d0be4ebad870e131a51109c04bf0a9422c1e356e8bd"
WEBHOOK_URL = "https://yanny230.pythonanywhere.com/webhook/zumbopay"

WALLET_MPESA = "986419"
WALLET_EMOLA = "343493"

VALOR_ACESSO_PADRAO = 10.00
EXPIRES_IN = 300



# Pastas
os.makedirs("relatorios", exist_ok=True)
os.makedirs("backups", exist_ok=True)

# ================= ESCALAS QUALITATIVAS =================
ESCALAS_QUALITATIVAS = [
    {'valor': 0, 'nome': 'Insuficiente', 'cor': '#dc2626'},
    {'valor': 1, 'nome': 'Suficiente', 'cor': '#f59e0b'},
    {'valor': 2, 'nome': 'Bom', 'cor': '#22c55e'},
    {'valor': 3, 'nome': 'Muito Bom', 'cor': '#2563eb'}
]

# ================= FUNÇÕES DE CONEXÃO =================
def conectar():
    return sqlite3.connect("escola.db")

# ================= SEGURANÇA =================
tentativas_login = defaultdict(int)
bloqueio_ip = {}

def is_diretor():
    return session.get("tipo") == "diretor"

def is_professor():
    return session.get("tipo") == "professor"

def is_admin():
    return session.get("tipo") in ["admin", "coordenador"]

# ================= APAGAR TABELAS EXISTENTES E RECRIAR =================
def recriar_banco():
    """Apaga todas as tabelas e recria com a nova estrutura"""
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys = OFF")
    
    tabelas = [
        'ordem_disciplinas',
        'disciplinas_qualitativas',
        'escalas_qualitativas',
        'config_pagamentos',
        'pagamentos_alunos',
        'notas_exame',
        'disciplinas_exames',
        'classes_exames',
        'notas_historico',
        'alunos_historico',
        'historico_transferencias',
        'historico_anos',
        'notas',
        'disciplinas',
        'alunos',
        'periodos',
        'diretores',
        'secretarias',
        'logs',
        'config',
        'turmas',
        'escolas'
    ]
    
    for tabela in tabelas:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {tabela}")
            print(f"✅ Tabela {tabela} removida")
        except Exception as e:
            print(f"⚠️ Erro ao remover {tabela}: {e}")
    
    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()
    print("✅ Todas as tabelas foram removidas!")

# ================= CRIAÇÃO DO BANCO (SEM A TABELA CONFIG) =================
def criar_bd():
    conn = conectar()
    cursor = conn.cursor()
    
    # 🔥 A TABELA CONFIG NÃO É CRIADA AQUI!
    
    # ================= ESCOLAS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS escolas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT,
        telefone TEXT,
        endereco TEXT,
        data_ativacao INTEGER,
        data_expiracao INTEGER,
        ativo INTEGER DEFAULT 1,
        chave_licenca TEXT UNIQUE
    )
    """)
    
    # ================= TURMAS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS turmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        ano TEXT,
        nome TEXT
    )
    """)
    
    # ================= PERIODOS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS periodos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        trimestre TEXT,
        inicio INTEGER,
        fim INTEGER,
        fim_extensao INTEGER
    )
    """)

    # ================= ALUNOS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alunos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        nome TEXT NOT NULL,
        turma_id INTEGER REFERENCES turmas(id) ON DELETE SET NULL,
        faltas_vermelhas INTEGER DEFAULT 0,
        status_pagamento TEXT DEFAULT 'pendente',
        senha TEXT,
        precisa_criar_senha INTEGER DEFAULT 1
    )
    """)
    
    # ================= DISCIPLINAS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS disciplinas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        nome TEXT NOT NULL,
        turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
        professor_nome TEXT,
        professor_senha TEXT,
        precisa_trocar_senha INTEGER DEFAULT 1
    )
    """)

    # ================= NOTAS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        disciplina_id INTEGER REFERENCES disciplinas(id) ON DELETE CASCADE,
        acs1_t1 REAL DEFAULT 0,
        acs2_t1 REAL DEFAULT 0,
        at_t1 REAL DEFAULT 0,
        acs1_t2 REAL DEFAULT 0,
        acs2_t2 REAL DEFAULT 0,
        at_t2 REAL DEFAULT 0,
        acs1_t3 REAL DEFAULT 0,
        acs2_t3 REAL DEFAULT 0,
        at_t3 REAL DEFAULT 0,
        notas_bloqueadas INTEGER DEFAULT 0,
        UNIQUE(aluno_id, disciplina_id)
    )
    """)    

    # ================= DIRETORES =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diretores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        nome TEXT NOT NULL,
        turma_id INTEGER REFERENCES turmas(id) ON DELETE SET NULL,
        senha TEXT,
        precisa_trocar_senha INTEGER DEFAULT 1
    )
    """)
    
    # ================= HISTÓRICO =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historico_anos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        ano_letivo TEXT,
        data_arquivamento INTEGER,
        ativo INTEGER DEFAULT 0
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alunos_historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        ano_letivo TEXT,
        nome TEXT,
        turma_id INTEGER,
        turma_nome TEXT,
        status_pagamento TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notas_historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        ano_letivo TEXT,
        aluno_id INTEGER,
        aluno_nome TEXT,
        disciplina_id INTEGER,
        disciplina_nome TEXT,
        turma_id INTEGER,
        acs1_t1 REAL, acs2_t1 REAL, at_t1 REAL,
        acs1_t2 REAL, acs2_t2 REAL, at_t2 REAL,
        acs1_t3 REAL, acs2_t3 REAL, at_t3 REAL,
        media_final REAL,
        nota_exame REAL,
        media_com_exame REAL,
        aprovado INTEGER
    )
    """)
    
    # 🔥 TABELA DE PAGAMENTOS DE ACESSO
    cursor.execute("""
CREATE TABLE IF NOT EXISTS pagamentos_alunos_acesso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
    aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    valor_pago REAL,
    metodo_pagamento TEXT,
    referencia_pagamento TEXT UNIQUE,
    checkout_id TEXT,
    transacao_id TEXT,
    status TEXT DEFAULT 'pendente',
    data_pagamento INTEGER,
    session_id TEXT,
    ip TEXT,
    observacao TEXT
    )
    """)
    
    # 🔥 TABELA DE ACESSOS LIBERADOS
    cursor.execute("""
CREATE TABLE IF NOT EXISTS acessos_liberados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    data_acesso INTEGER,
    ip TEXT
    )
    """)
    
    # 🔥 TABELA DE CONFIGURAÇÃO DE PAGAMENTO
    cursor.execute("""
CREATE TABLE IF NOT EXISTS config_pagamentos_acesso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    valor REAL NOT NULL,
    mes_referencia TEXT,
    ativo INTEGER DEFAULT 1
    )
    """)
    
    # 🔥 INSERE VALOR PADRÃO
    cursor.execute("SELECT id FROM escolas LIMIT 1")
    escola = cursor.fetchone()
    
    
    if escola:
        escola_id = escola[0]
        cursor.execute("""
        INSERT OR IGNORE INTO config_pagamentos_acesso (escola_id, tipo, valor, ativo)
        VALUES (?, 'notas', 10.00, 1)
    """, (escola_id,))


    
    # ================= CLASSES COM EXAMES =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS classes_exames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        ano TEXT,
        ativo INTEGER DEFAULT 1,
        UNIQUE(escola_id, ano)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS disciplinas_exames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        disciplina_id INTEGER REFERENCES disciplinas(id) ON DELETE CASCADE,
        turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
        ano_letivo TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notas_exame (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        disciplina_id INTEGER REFERENCES disciplinas(id) ON DELETE CASCADE,
        nota_exame REAL DEFAULT 0,
        ano_letivo TEXT,
        UNIQUE(aluno_id, disciplina_id, ano_letivo)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historico_transferencias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        turma_origem_id INTEGER REFERENCES turmas(id) ON DELETE SET NULL,
        turma_destino_id INTEGER REFERENCES turmas(id) ON DELETE SET NULL,
        data_transferencia INTEGER,
        ano_letivo_origem TEXT,
        ano_letivo_destino TEXT,
        aprovado INTEGER
    )
    """)

    # ================= PAGAMENTOS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagamentos_alunos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        tipo TEXT,
        mes INTEGER,
        ano INTEGER,
        valor_pago REAL DEFAULT 0,
        valor_esperado REAL,
        data_pagamento INTEGER,
        status TEXT DEFAULT 'pendente',
        observacao TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config_pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        tipo TEXT,
        valor REAL,
        ano INTEGER,
        ativo INTEGER DEFAULT 1
    )
    """)

    # ================= NOTAS QUALITATIVAS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS escalas_qualitativas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        nome TEXT,
        valor_minimo REAL,
        valor_maximo REAL,
        descricao TEXT,
        ordem INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS disciplinas_qualitativas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        disciplina_id INTEGER REFERENCES disciplinas(id) ON DELETE CASCADE,
        ativo INTEGER DEFAULT 1
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notas_qualitativas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE,
        disciplina_id INTEGER REFERENCES disciplinas(id) ON DELETE CASCADE,
        trimestre INTEGER,
        qualidade TEXT,
        UNIQUE(aluno_id, disciplina_id, trimestre)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordem_disciplinas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        turma_id INTEGER REFERENCES turmas(id) ON DELETE CASCADE,
        disciplina_id INTEGER REFERENCES disciplinas(id) ON DELETE CASCADE,
        ordem INTEGER DEFAULT 0,
        ano_letivo TEXT
    )
    """)

    # ================= LOGS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        usuario TEXT,
        tipo TEXT,
        acao TEXT,
        detalhes TEXT,
        ip TEXT,
        data INTEGER
    )
    """)

    # ================= SECRETARIAS =================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS secretarias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE,
        nome TEXT NOT NULL,
        senha TEXT,
        precisa_trocar_senha INTEGER DEFAULT 1
    )
    """)

    # ================= ÍNDICES =================
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alunos_escola ON alunos(escola_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alunos_turma ON alunos(turma_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notas_aluno ON notas(aluno_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notas_disciplina ON notas(disciplina_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pagamentos_aluno ON pagamentos_alunos(aluno_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pagamentos_mes ON pagamentos_alunos(mes, ano)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pagamentos_escola ON pagamentos_alunos(escola_id)")
    
    # ================= 🔥 NÃO CRIAR ADMIN PADRÃO AQUI! =================
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados criado/verificado com sucesso!")

# ================= RECRIAR CONFIG =================
def recriar_config():
    """Recria a tabela config com a estrutura correta"""
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("DROP TABLE IF EXISTS config")
    cursor.execute("""
    CREATE TABLE config (
        chave TEXT NOT NULL,
        valor TEXT,
        escola_id INTEGER,
        PRIMARY KEY (chave, escola_id)
    )
    """)
    
    # Super Admin
    senha_super_admin = generate_password_hash("super123")
    cursor.execute("""
        INSERT OR IGNORE INTO config (chave, valor, escola_id)
        VALUES ('super_admin_senha', ?, NULL)
    """, (senha_super_admin,))
    
    conn.commit()
    conn.close()
    print("✅ Tabela config recriada com sucesso!")

# ================= CORREÇÃO DO BANCO =================
def corrigir_banco_aluno():
    """Adiciona colunas de senha na tabela alunos se não existirem"""
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(alunos)")
    colunas = [col[1] for col in cursor.fetchall()]
    
    if 'senha' not in colunas:
        cursor.execute("ALTER TABLE alunos ADD COLUMN senha TEXT")
        print("✅ Coluna 'senha' adicionada!")
    
    if 'precisa_criar_senha' not in colunas:
        cursor.execute("ALTER TABLE alunos ADD COLUMN precisa_criar_senha INTEGER DEFAULT 1")
        print("✅ Coluna 'precisa_criar_senha' adicionada!")
    
    if 'escola_id' not in colunas:
        cursor.execute("ALTER TABLE alunos ADD COLUMN escola_id INTEGER REFERENCES escolas(id) ON DELETE CASCADE")
        print("✅ Coluna 'escola_id' adicionada!")
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados corrigido para alunos!")

# ================= 🔥 CHAMAR AS FUNÇÕES CORRIGIDAS =================
# 🔥 REMOVIDO: recriar_banco()   ← ISTO APAGAVA TODOS OS DADOS!
# 🔥 REMOVIDO: criar_bd()        ← ISTO RECRIAVA O BANCO VAZIO!
# 🔥 REMOVIDO: recriar_config()  ← ISTO RECRIAVA A TABELA CONFIG!

# ✅ APENAS CORRIGE O BANCO SE NECESSÁRIO
#corrigir_banco_aluno()

# ================= VERIFICAR SE O BANCO EXISTE =================
def verificar_banco():
    """Verifica se o banco de dados existe e tem tabelas"""
    try:
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='escolas'")
        if not cursor.fetchone():
            print("⚠️ Banco de dados não encontrado! Criando...")
            criar_bd()
            recriar_config()
            corrigir_banco_aluno()
        else:
            print("✅ Banco de dados já existe!")
        conn.close()
    except Exception as e:
        print(f"❌ Erro ao verificar banco: {e}")

# Executa a verificação apenas uma vez
verificar_banco()

# ================= FUNÇÕES AUXILIARES =================

def get_escola_id():
    """Retorna o ID da escola atual da sessão"""
    return session.get("escola_id")

def escola_ativa(escola_id):
    """Verifica se a escola está ativa e com licença válida"""
    if not escola_id:
        return False
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ativo, data_expiracao FROM escolas 
        WHERE id = ? AND ativo = 1
    """, (escola_id,))
    resultado = cursor.fetchone()
    conn.close()
    
    if not resultado:
        return False
    
    agora = int(time.time())
    return resultado[1] > agora

def escola_tem_licenca(escola_id):
    """Verifica se a licença da escola está ativa (alias para escola_ativa)"""
    return escola_ativa(escola_id)

def normalizar(texto):
    if not texto:
        return ""
    return ''.join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).lower()

def gerar_senha(nome):
    """Gera senha padrao: primeiras 6 letras do nome + 123 (sem acentos)"""
    nome = nome.strip().lower()
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    nome = nome.replace(' ', '')
    base = nome[:6] if len(nome) >= 6 else nome
    return base + "123"

def gerar_referencia_pagamento():
    """Gera uma referência única para pagamento"""
    import random
    import string
    
    prefixos = ['MPESA', 'EMOLA', 'MKESH']
    prefixo = random.choice(prefixos)
    
    data = datetime.now().strftime("%Y%m%d")
    codigo = ''.join(random.choices(string.digits, k=6))
    return f"{prefixo}-{data}-{codigo}"

def validar_nome(nome):
    """Valida se o nome contém apenas letras, espaços, acentos e ç"""
    if not nome or len(nome.strip()) < 3:
        return False, "O nome deve ter pelo menos 3 caracteres"
    
    nome_limpo = nome.strip()
    
    if any(c.isdigit() for c in nome_limpo):
        return False, "O nome não pode conter números"
    
    caracteres_especiais = set('@#$%^&*()+=-[]{};:,.<>?/\\|`~')
    if any(c in caracteres_especiais for c in nome_limpo):
        return False, "O nome não pode conter caracteres especiais"
    
    tem_letra = any(c.isalpha() for c in nome_limpo)
    if not tem_letra:
        return False, "O nome deve conter pelo menos uma letra"
    
    return True, nome_limpo

def verificar_nome_existente(tipo, nome, turma_id=None, escola_id=None):
    """Verifica se já existe um nome igual no sistema"""
    conn = conectar()
    cursor = conn.cursor()
    
    nome_normalizado = nome.strip().lower()
    
    if tipo == "professor":
        cursor.execute("SELECT id FROM disciplinas WHERE LOWER(TRIM(professor_nome)) = ? AND escola_id = ?", (nome_normalizado, escola_id))
    elif tipo == "diretor":
        cursor.execute("SELECT id FROM diretores WHERE LOWER(TRIM(nome)) = ? AND escola_id = ?", (nome_normalizado, escola_id))
    elif tipo == "secretaria":
        cursor.execute("SELECT id FROM secretarias WHERE LOWER(TRIM(nome)) = ? AND escola_id = ?", (nome_normalizado, escola_id))
    elif tipo == "aluno":
        cursor.execute("SELECT id FROM alunos WHERE LOWER(TRIM(nome)) = ? AND turma_id = ? AND escola_id = ?", (nome_normalizado, turma_id, escola_id))
    else:
        conn.close()
        return False
    
    existe = cursor.fetchone() is not None
    conn.close()
    return existe

def disciplina_eh_qualitativa(disciplina_id, escola_id):
    """Verifica se uma disciplina usa notas qualitativas"""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM disciplinas_qualitativas 
        WHERE disciplina_id = ? AND escola_id = ? AND ativo = 1
    """, (disciplina_id, escola_id))
    resultado = cursor.fetchone()
    conn.close()
    return resultado is not None

# ================= FUNÇÕES DE CÁLCULO =================

def calcular_trimestre(acs1, acs2, at):
    acs1 = acs1 or 0
    acs2 = acs2 or 0
    at = at or 0
    
    if acs1 == 0 and acs2 == 0 and at == 0:
        return None
    
    media = (acs1 + acs2 + at) / 3
    return round(media)

def calcular_media_final(t1, t2, t3):
    medias = []
    for m in [t1, t2, t3]:
        if m is not None:
            medias.append(m)
    
    if not medias:
        return None
    
    return round(sum(medias) / len(medias))

def calcular_media_com_exame(media_frequencia, nota_exame):
    if nota_exame is None or nota_exame == 0:
        return media_frequencia
    return round((2 * media_frequencia + nota_exame) / 3)

def get_trimestre_ativo():
    """Retorna o trimestre atualmente ativo"""
    conn = conectar()
    cursor = conn.cursor()
    agora = int(time.time())
    escola_id = get_escola_id()
    
    if escola_id:
        cursor.execute("""
            SELECT trimestre, inicio, fim FROM periodos 
            WHERE escola_id = ? 
            ORDER BY id DESC LIMIT 1
        """, (escola_id,))
    else:
        cursor.execute("SELECT trimestre, inicio, fim FROM periodos ORDER BY id DESC LIMIT 1")
    
    periodo = cursor.fetchone()
    conn.close()
    
    if periodo and periodo[1] <= agora <= periodo[2]:
        return int(periodo[0][0])
    
    return 1


# ================= FUNÇÕES ZUMBOPAY =================

def zumbopay_iniciar_pagamento(telefone, valor, referencia, descricao="Acesso Notas"):
    """
    Inicia um pagamento via ZumboPay
    """
    try:
        # 🔥 FORMATA O TELEFONE
        telefone = ''.join(filter(str.isdigit, str(telefone)))
        if telefone.startswith('0'):
            telefone = '258' + telefone[1:]
        elif not telefone.startswith('258'):
            telefone = '258' + telefone
        
        print(f"🔵 Iniciando pagamento ZumboPay:")
        print(f"   Telefone: {telefone}")
        print(f"   Valor: {valor}")
        print(f"   Referência: {referencia}")
        
        # 🔥 PREPARA O PAYLOAD
        payload = {
            "phone": telefone,
            "amount": float(valor),
            "reference": referencia,
            "description": descricao,
            "callback_url": WEBHOOK_URL,
            "expires_in": EXPIRES_IN,
            "wallet_id": WALLET_MPESA  # Usa M-Pesa como padrão
        }
        
        headers = {
            "X-Merchant-Id": MERCHANT_ID,
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        # 🔥 ENVIA A REQUISIÇÃO
        response = requests.post(
            f"{BASE_URL}/payments/request",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"   Response: {response.status_code}")
        
        if response.status_code in [200, 201]:
            data = response.json()
            return {
                "status": "success",
                "checkout_id": data.get("transaction_id"),
                "payment_id": data.get("payment_id"),
                "message": "Pagamento iniciado com sucesso!",
                "data": data
            }
        else:
            return {
                "status": "error",
                "message": f"Erro {response.status_code}: {response.text}",
                "data": None
            }
            
    except Exception as e:
        print(f"❌ Erro no ZumboPay: {e}")
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }


def zumbopay_consultar_status(transaction_id):
    """
    Consulta o status de um pagamento no ZumboPay
    """
    try:
        headers = {
            "X-Merchant-Id": MERCHANT_ID,
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(
            f"{BASE_URL}/payments/status/{transaction_id}",
            headers=headers,
            timeout=30
        )
        
        print(f"🔵 Status Check: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            status = data.get("status", "unknown")
            
            if status in ["completed", "success", "paid", "confirmed"]:
                return {"status": "pago", "data": data}
            elif status in ["pending", "processing", "initiated", "waiting"]:
                return {"status": "pendente", "data": data}
            else:
                return {"status": "desconhecido", "data": data}
        else:
            return {"status": "error", "message": response.text}
            
    except Exception as e:
        print(f"❌ Erro ao consultar: {e}")
        return {"status": "error", "message": str(e)}

# ================= WEBHOOK ZUMBOPAY =================

@app.route("/webhook/zumbopay", methods=["POST"])
def webhook_zumbopay():
    """
    Recebe notificações de pagamento do ZumboPay
    """
    try:
        data = request.get_json()
        
        print(f"🔵 Webhook ZumboPay recebido: {json.dumps(data, indent=2)}")
        
        # 🔥 EXTRAI AS INFORMAÇÕES
        event_type = data.get("type")
        payment_data = data.get("data", {})
        
        reference = payment_data.get("reference")
        payment_id = payment_data.get("payment_id")
        amount = payment_data.get("amount")
        status = payment_data.get("status")
        
        if not reference:
            print("❌ Referência não encontrada")
            return jsonify({"status": "error", "msg": "Referência não encontrada"}), 400
        
        # 🔥 VERIFICA O TIPO DO EVENTO
        if event_type == "payment.succeeded":
            print(f"✅ Pagamento confirmado: {reference}")
            
            conn = conectar()
            cursor = conn.cursor()
            
            # 🔥 BUSCA O PAGAMENTO NO BANCO
            cursor.execute("""
                SELECT id, aluno_id, tipo FROM pagamentos_alunos_acesso 
                WHERE referencia_pagamento = ? AND status = 'pendente'
                ORDER BY id DESC LIMIT 1
            """, (reference,))
            
            pagamento = cursor.fetchone()
            
            if pagamento:
                pagamento_id = pagamento[0]
                aluno_id = pagamento[1]
                tipo = pagamento[2]
                
                agora = int(time.time())
                
                # 🔥 ATUALIZA O STATUS
                cursor.execute("""
                    UPDATE pagamentos_alunos_acesso 
                    SET status = 'pago', 
                        data_pagamento = ?,
                        checkout_id = ?,
                        transacao_id = ?
                    WHERE id = ?
                """, (agora, payment_id, payment_id, pagamento_id))
                
                # 🔥 REGISTRA O ACESSO LIBERADO
                cursor.execute("""
                    INSERT INTO acessos_liberados (aluno_id, tipo, data_acesso, ip)
                    VALUES (?, ?, ?, ?)
                """, (aluno_id, tipo, agora, request.remote_addr))
                
                conn.commit()
                conn.close()
                
                print(f"✅ Acesso liberado para aluno {aluno_id} - Tipo: {tipo}")
                return jsonify({"status": "success", "msg": "Acesso liberado"}), 200
            else:
                print(f"⚠️ Pagamento não encontrado: {reference}")
                return jsonify({"status": "not_found"}), 404
        
        elif event_type == "payment.failed":
            print(f"❌ Pagamento falhou: {reference}")
            
            conn = conectar()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE pagamentos_alunos_acesso 
                SET status = 'cancelado' 
                WHERE referencia_pagamento = ?
            """, (reference,))
            
            conn.commit()
            conn.close()
            
            return jsonify({"status": "failed"}), 200
        
        return jsonify({"status": "ignored"}), 200
        
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500
        

def verificar_acesso_sessao(aluno_id, tipo):
    """Verifica se o aluno tem acesso liberado para um tipo específico"""
    try:
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM pagamentos_alunos_acesso 
            WHERE aluno_id = ? AND tipo = ? AND status = 'pago'
            ORDER BY id DESC LIMIT 1
        """, (aluno_id, tipo))
        resultado = cursor.fetchone()
        conn.close()
        return resultado is not None
    except Exception as e:
        print(f"❌ Erro ao verificar acesso: {e}")
        return False        
                        

@app.route("/aluno/pagar-acesso/<tipo>", methods=["GET", "POST"])
def aluno_pagar_acesso(tipo):
    if session.get("tipo") != "aluno":
        return redirect("/login")
    
    aluno_id = session.get("aluno_id")
    escola_id = get_escola_id()
    
    if tipo not in ['notas', 'biblioteca']:
        return redirect("/aluno/dashboard")
    
    # 🔥 VERIFICA SE JÁ TEM ACESSO
    if verificar_acesso_sessao(aluno_id, tipo):
        return redirect("/aluno/dashboard")
    
    if request.method == "POST":
        telefone = request.form.get("telefone", "").strip()
        
        if not telefone:
            return render_template("aluno_pagar_acesso.html",
                tipo=tipo,
                valor=VALOR_ACESSO_PADRAO,
                aluno_nome=session.get("aluno_nome", "Aluno"),
                erro="⚠️ Digite o número de telefone")
        
        agora = int(time.time())
        referencia = gerar_referencia_pagamento()
        valor = VALOR_ACESSO_PADRAO
        
        # 🔥 INICIA PAGAMENTO NO ZUMBOPAY
        resultado = zumbopay_iniciar_pagamento(telefone, valor, referencia, f"Acesso {tipo}")
        
        if resultado["status"] == "success":
            # 🔥 SALVA NO BANCO
            conn = conectar()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO pagamentos_alunos_acesso 
                (aluno_id, escola_id, tipo, valor_pago, referencia_pagamento, checkout_id, status, data_pagamento, ip)
                VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?, ?)
            """, (aluno_id, escola_id, tipo, valor, referencia, resultado["checkout_id"], agora, request.remote_addr))
            
            conn.commit()
            conn.close()
            
            # 🔥 REDIRECIONA PARA CONFIRMAÇÃO
            return redirect(f"/aluno/pagar-acesso/confirmar/{referencia}")
        else:
            return render_template("aluno_pagar_acesso.html",
                tipo=tipo,
                valor=valor,
                aluno_nome=session.get("aluno_nome", "Aluno"),
                erro=f"❌ Erro: {resultado['message']}")
    
    # 🔥 GET - MOSTRA PÁGINA DE PAGAMENTO
    return render_template("aluno_pagar_acesso.html",
        tipo=tipo,
        valor=VALOR_ACESSO_PADRAO,
        aluno_nome=session.get("aluno_nome", "Aluno"))


import sqlite3

conn = sqlite3.connect("escola.db")
cursor = conn.cursor()


def trimestre_esta_aberto(trimestre):
    """Verifica se um trimestre específico está aberto"""
    conn = conectar()
    cursor = conn.cursor()
    agora = int(time.time())
    escola_id = get_escola_id()
    
    if escola_id:
        cursor.execute("""
            SELECT fim_extensao FROM periodos 
            WHERE trimestre = ? AND escola_id = ?
            ORDER BY id DESC LIMIT 1
        """, (f"{trimestre}º Trimestre", escola_id))
    else:
        cursor.execute("""
            SELECT fim_extensao FROM periodos 
            WHERE trimestre = ? 
            ORDER BY id DESC LIMIT 1
        """, (f"{trimestre}º Trimestre",))
    
    resultado = cursor.fetchone()
    conn.close()
    
    if not resultado:
        return True
    
    return agora < resultado[0]

def pode_editar_notas(disciplina_id, trimestre):
    """Verifica se o professor pode editar notas para o trimestre atual"""
    trimestre_atual = get_trimestre_ativo()
    
    if trimestre != trimestre_atual:
        return False, f"⚠️ Apenas o {trimestre_atual}º Trimestre está ativo para lançamento de notas."
    
    if not trimestre_esta_aberto(trimestre):
        return False, f"⛔ {trimestre}º Trimestre está fechado. Período de lançamento encerrado."
    
    return True, "OK"

def get_ano_letivo_atual():
    """Retorna o ano letivo atual (ex: 2026)"""
    escola_id = get_escola_id()
    
    conn = conectar()
    cursor = conn.cursor()
    
    if escola_id:
        cursor.execute("SELECT valor FROM config WHERE chave = 'ano_letivo_atual' AND escola_id = ?", (escola_id,))
    else:
        cursor.execute("SELECT valor FROM config WHERE chave = 'ano_letivo_atual'")
    
    resultado = cursor.fetchone()
    if not resultado:
        ano = str(datetime.now().year)
        if escola_id:
            cursor.execute("INSERT INTO config (chave, valor, escola_id) VALUES ('ano_letivo_atual', ?, ?)", (ano, escola_id))
        else:
            cursor.execute("INSERT INTO config (chave, valor) VALUES ('ano_letivo_atual', ?)", (ano,))
        conn.commit()
        resultado = (ano,)
    
    conn.close()
    return resultado[0]

def set_ano_letivo_atual(ano):
    """Define o ano letivo atual"""
    escola_id = get_escola_id()
    
    conn = conectar()
    cursor = conn.cursor()
    
    if escola_id:
        cursor.execute("""
            UPDATE config SET valor = ? 
            WHERE chave = 'ano_letivo_atual' AND escola_id = ?
        """, (ano, escola_id))
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO config (chave, valor, escola_id) 
                VALUES ('ano_letivo_atual', ?, ?)
            """, (ano, escola_id))
    else:
        cursor.execute("""
            UPDATE config SET valor = ? 
            WHERE chave = 'ano_letivo_atual'
        """, (ano,))
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO config (chave, valor) 
                VALUES ('ano_letivo_atual', ?)
            """, (ano,))
    
    conn.commit()
    conn.close()

def disciplina_tem_exame(disciplina_id, turma_id, ano_letivo):
    """Verifica se uma disciplina tem exame no ano letivo atual"""
    escola_id = get_escola_id()
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM disciplinas_exames 
        WHERE disciplina_id = ? AND turma_id = ? AND ano_letivo = ? AND escola_id = ?
    """, (disciplina_id, turma_id, ano_letivo, escola_id))
    resultado = cursor.fetchone()
    conn.close()
    return resultado is not None

def verificar_notas_completas(aluno_id, disciplina_id):
    """Verifica se todas as notas do aluno para esta disciplina estão preenchidas"""
    escola_id = get_escola_id()
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT acs1_t1, acs2_t1, at_t1,
               acs1_t2, acs2_t2, at_t2,
               acs1_t3, acs2_t3, at_t3,
               notas_bloqueadas
        FROM notas
        WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
    """, (aluno_id, disciplina_id, escola_id))
    
    notas = cursor.fetchone()
    conn.close()
    
    if not notas:
        return False, False
    
    notas_bloqueadas = notas[9] == 1
    
    todas_preenchidas = all(
        notas[0] != 0 and notas[1] != 0 and notas[2] != 0 and
        notas[3] != 0 and notas[4] != 0 and notas[5] != 0 and
        notas[6] != 0 and notas[7] != 0 and notas[8] != 0
    )
    
    return todas_preenchidas, notas_bloqueadas

# ================= SISTEMA DE PAGAMENTOS =================

MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

MESES_UTEIS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

def get_valor_pagamento(escola_id, tipo):
    """Retorna o valor configurado para um tipo de pagamento"""
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT valor FROM config_pagamentos 
        WHERE escola_id = ? AND tipo = ? AND ativo = 1
        ORDER BY id DESC LIMIT 1
    """, (escola_id, tipo))
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

# ================= ARQUIVAR ANO LETIVO =================

def arquivar_ano_letivo(ano_letivo):
    """Arquiva todos os dados do ano letivo atual para histórico"""
    escola_id = get_escola_id()
    if not escola_id:
        return
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO historico_anos (ano_letivo, data_arquivamento, ativo, escola_id)
        VALUES (?, ?, 0, ?)
    """, (ano_letivo, int(time.time()), escola_id))
    
    cursor.execute("""
        INSERT INTO alunos_historico (ano_letivo, nome, turma_id, turma_nome, status_pagamento, escola_id)
        SELECT ?, a.nome, a.turma_id, CONCAT(t.ano, 'ª ', t.nome), a.status_pagamento, ?
        FROM alunos a
        JOIN turmas t ON a.turma_id = t.id
        WHERE a.escola_id = ?
    """, (ano_letivo, escola_id, escola_id))
    
    cursor.execute("""
        INSERT INTO notas_historico 
        (ano_letivo, aluno_id, aluno_nome, disciplina_id, disciplina_nome, turma_id,
         acs1_t1, acs2_t1, at_t1, acs1_t2, acs2_t2, at_t2, acs1_t3, acs2_t3, at_t3,
         media_final, nota_exame, media_com_exame, aprovado, escola_id)
        SELECT 
            ?, a.id, a.nome, d.id, d.nome, d.turma_id,
            n.acs1_t1, n.acs2_t1, n.at_t1,
            n.acs1_t2, n.acs2_t2, n.at_t2,
            n.acs1_t3, n.acs2_t3, n.at_t3,
            CASE 
                WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                     OR (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0
                     OR (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0
                THEN (COALESCE(
                    (CASE WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                          THEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) / 3 END), 0) +
                     COALESCE(
                    (CASE WHEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0 
                          THEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) / 3 END), 0) +
                     COALESCE(
                    (CASE WHEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0 
                          THEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) / 3 END), 0)) / 3
                ELSE 0
            END,
            ne.nota_exame,
            CASE 
                WHEN ne.nota_exame > 0 
                THEN ((2 * (
                    CASE 
                        WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                             OR (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0
                             OR (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0
                        THEN (COALESCE(
                            (CASE WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                                  THEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) / 3 END), 0) +
                             COALESCE(
                            (CASE WHEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0 
                                  THEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) / 3 END), 0) +
                             COALESCE(
                            (CASE WHEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0 
                                  THEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) / 3 END), 0)) / 3
                        ELSE 0
                    END)) + ne.nota_exame) / 3
                ELSE 
                    CASE 
                        WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                             OR (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0
                             OR (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0
                        THEN (COALESCE(
                            (CASE WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                                  THEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) / 3 END), 0) +
                             COALESCE(
                            (CASE WHEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0 
                                  THEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) / 3 END), 0) +
                             COALESCE(
                            (CASE WHEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0 
                                  THEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) / 3 END), 0)) / 3
                        ELSE 0
                    END
            END,
            CASE 
                WHEN ne.nota_exame > 0 
                THEN ((2 * (
                    CASE 
                        WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                             OR (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0
                             OR (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0
                        THEN (COALESCE(
                            (CASE WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                                  THEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) / 3 END), 0) +
                             COALESCE(
                            (CASE WHEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0 
                                  THEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) / 3 END), 0) +
                             COALESCE(
                            (CASE WHEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0 
                                  THEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) / 3 END), 0)) / 3
                        ELSE 0
                    END)) + ne.nota_exame) / 3 >= 10
                ELSE 
                    CASE 
                        WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                             OR (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0
                             OR (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0
                        THEN (COALESCE(
                            (CASE WHEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) > 0 
                                  THEN (n.acs1_t1 + n.acs2_t1 + n.at_t1) / 3 END), 0) +
                             COALESCE(
                            (CASE WHEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) > 0 
                                  THEN (n.acs1_t2 + n.acs2_t2 + n.at_t2) / 3 END), 0) +
                             COALESCE(
                            (CASE WHEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) > 0 
                                  THEN (n.acs1_t3 + n.acs2_t3 + n.at_t3) / 3 END), 0)) / 3 >= 10
                        ELSE 0
                    END
            END,
            ?
        FROM alunos a
        JOIN notas n ON a.id = n.aluno_id
        JOIN disciplinas d ON n.disciplina_id = d.id
        LEFT JOIN notas_exame ne ON a.id = ne.aluno_id AND d.id = ne.disciplina_id AND ne.ano_letivo = ?
        WHERE a.escola_id = ?
    """, (ano_letivo, escola_id, ano_letivo, escola_id))
    
    conn.commit()
    conn.close()
    print(f"✅ Ano letivo {ano_letivo} arquivado com sucesso!")

def resetar_para_novo_ano():
    """Reseta o sistema para o novo ano letivo"""
    escola_id = get_escola_id()
    if not escola_id:
        return
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM notas WHERE escola_id = ?", (escola_id,))
    cursor.execute("DELETE FROM notas_exame WHERE escola_id = ?", (escola_id,))
    cursor.execute("DELETE FROM alunos WHERE escola_id = ?", (escola_id,))
    cursor.execute("DELETE FROM pagamentos_alunos WHERE escola_id = ?", (escola_id,))
    cursor.execute("DELETE FROM notas_qualitativas WHERE escola_id = ?", (escola_id,))
    
    conn.commit()
    conn.close()
    print("✅ Sistema resetado para novo ano letivo!")

# ================= LOGS =================

def registrar_log(acao, detalhes=""):
    # 🔥 SE FOR SUPER ADMIN, NÃO REGISTA!
    if session.get("tipo") == "super_admin":
        return
    
    try:
        usuario = session.get("user", "Desconhecido")
        tipo = session.get("tipo", "Desconhecido")
        escola_id = session.get("escola_id")
        ip = request.remote_addr

        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO logs (usuario, tipo, acao, detalhes, ip, data, escola_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (usuario, tipo, acao, detalhes, ip, int(time.time()), escola_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print("ERRO LOG:", e)

# ================= VERIFICADOR DE ACESSO =================

@app.before_request
def verificar_acesso():
    """Verifica se o utilizador tem acesso ao sistema"""
    
    # 🔥 REMOVIDO /pre-login e /pre-login/trocar-senha
    rotas_publicas = [
        '/login', '/logout',
        '/super-login', '/super-login/trocar-senha',
        '/aluno', '/buscar-notas',
        '/aluno/criar-senha', '/aluno/login',
        '/static'
    ]
    
    if request.path in rotas_publicas:
        return None
    
    # SUPER ADMIN TEM ACESSO TOTAL
    if session.get("tipo") == "super_admin":
        return None
    
    # ADMIN TEM ACESSO À SUA ESCOLA
    if session.get("tipo") in ["admin", "coordenador"]:
        rotas_admin_sem_escola = [
            '/admin/configurar-escola',
            '/admin/trocar-senha'
        ]
        
        for rota in rotas_admin_sem_escola:
            if request.path.startswith(rota):
                return None
        
        if not session.get("escola_id"):
            conn = conectar()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM escolas LIMIT 1")
            escola = cursor.fetchone()
            conn.close()
            
            if escola:
                session["escola_id"] = escola[0]
                conn = conectar()
                cursor = conn.cursor()
                cursor.execute("SELECT nome FROM escolas WHERE id = ?", (escola[0],))
                nome = cursor.fetchone()
                conn.close()
                if nome:
                    session["escola_nome"] = nome[0]
                return None
            else:
                return redirect("/admin/configurar-escola")
    
    # VERIFICA ESCOLA PARA OUTROS UTILIZADORES
    escola_id = session.get("escola_id")
    
    if not escola_id:
        session.clear()
        return redirect("/login?erro=sem_escola")
    
    if not escola_ativa(escola_id):
        session.clear()
        return redirect("/login?erro=escola_desativada")
    
    return None

# ================= GERAR SENHA ESCOLA =================

def gerar_senha_escola():
    """Gera uma senha aleatória para a escola (6 caracteres: letras + números)"""
    caracteres = string.ascii_uppercase + string.digits
    senha = ''.join(random.choices(caracteres, k=6))
    return senha

# ================= CONFIGURAR ESCOLA =================

@app.route("/admin/configurar-escola", methods=["GET", "POST"])
def configurar_escola():
    if not is_admin() and session.get("tipo") != "super_admin":
        return redirect("/login")
    
    erro = ""
    sucesso = ""
    senha_admin_gerada = ""
    
    if request.method == "POST":
        nome = request.form.get("nome")
        email = request.form.get("email")
        telefone = request.form.get("telefone")
        endereco = request.form.get("endereco")
        
        if not nome:
            erro = "Nome da escola é obrigatório"
        else:
            conn = conectar()
            cursor = conn.cursor()
            
            chave_licenca = f"LIC-{int(time.time())}-{nome[:3].upper()}"
            data_expiracao = int(time.time()) + 365 * 86400
            
            # 🔥 INSERE A NOVA ESCOLA
            cursor.execute("""
                INSERT INTO escolas (nome, email, telefone, endereco, data_ativacao, data_expiracao, chave_licenca)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (nome, email, telefone, endereco, int(time.time()), data_expiracao, chave_licenca))
            
            escola_id = cursor.lastrowid
            
            # 🔥 GERA SENHA ADMIN ÚNICA PARA ESTA ESCOLA
            senha_admin = gerar_senha_escola()
            senha_admin_hash = generate_password_hash(senha_admin)
            
            # 🔥 GUARDA A SENHA ADMIN ESPECÍFICA DA ESCOLA
            cursor.execute("""
                INSERT OR REPLACE INTO config (chave, valor, escola_id)
                VALUES ('admin_senha', ?, ?)
            """, (senha_admin_hash, escola_id))
            
            cursor.execute("""
                INSERT OR REPLACE INTO config (chave, valor, escola_id)
                VALUES ('admin_precisa_trocar', '1', ?)
            """, (escola_id,))
            
            conn.commit()
            conn.close()
            
            session["escola_id"] = escola_id
            session["escola_nome"] = nome
            
            registrar_log("CRIAR_ESCOLA", f"Escola: {nome} - ID: {escola_id} - Senha admin: {senha_admin}")
            sucesso = f"✅ Escola '{nome}' criada com sucesso!"
            senha_admin_gerada = senha_admin
    
    return render_template("admin_configurar_escola.html", 
        erro=erro, 
        sucesso=sucesso,
        senha_admin_gerada=senha_admin_gerada)
        
# ================= SUPER ADMIN LOGIN =================

@app.route("/super-login", methods=["GET", "POST"])
def super_login():
    session.clear()
    erro = ""
    
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")
        
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM config WHERE chave = 'super_admin_senha'")
        super_senha_hash = cursor.fetchone()
        conn.close()
        
        if usuario == "superadmin" and super_senha_hash and check_password_hash(super_senha_hash[0], senha):
            session["tipo"] = "super_admin"
            session["user"] = "Super Admin"
            return redirect("/super-admin")
        else:
            erro = "Acesso negado"
    
    return render_template("super_login.html", erro=erro)

@app.route("/super-login/trocar-senha", methods=["GET", "POST"])
def super_trocar_senha():
    if session.get("tipo") != "super_admin":
        return redirect("/super-login")
    
    erro = ""
    sucesso = ""
    
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")
        
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM config WHERE chave = 'super_admin_senha'")
        super_senha_hash = cursor.fetchone()
        conn.close()
        
        if not super_senha_hash or not check_password_hash(super_senha_hash[0], senha_atual):
            erro = "❌ Senha atual incorreta"
        elif nova_senha != confirmar_senha:
            erro = "❌ As senhas não coincidem"
        elif len(nova_senha) < 4:
            erro = "❌ A senha deve ter pelo menos 4 caracteres"
        else:
            nova_hash = generate_password_hash(nova_senha)
            
            conn = conectar()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE config 
                SET valor = ? 
                WHERE chave = 'super_admin_senha'
            """, (nova_hash,))
            conn.commit()
            conn.close()
            
            return redirect("/super-admin")
    
    return render_template("super_trocar_senha.html", erro=erro, sucesso=sucesso)

# ================= SUPER ADMIN PAINEL =================

@app.route("/super-admin")
def super_admin():
    if session.get("tipo") != "super_admin":
        return redirect("/super-login")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, nome, email, telefone, data_ativacao, data_expiracao, ativo, chave_licenca
        FROM escolas
        ORDER BY nome
    """)
    escolas = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM alunos")
    total_alunos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM escolas WHERE ativo = 1")
    escolas_ativas = cursor.fetchone()[0]
    
    conn.close()
    
    return render_template("super_admin.html", 
        escolas=escolas,
        total_alunos=total_alunos,
        escolas_ativas=escolas_ativas)

@app.route("/super-admin/escolas/selecionar/<int:escola_id>")
def super_selecionar_escola(escola_id):
    if session.get("tipo") != "super_admin":
        return redirect("/super-login")
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome FROM escolas WHERE id = ?", (escola_id,))
    escola = cursor.fetchone()
    conn.close()
    
    if escola:
        session["escola_id"] = escola_id
        session["escola_nome"] = escola[1]
        return redirect("/super-escola")
    
    return redirect("/super-admin")

@app.route("/super-escola")
def super_escola():
    if session.get("tipo") != "super_admin":
        return redirect("/super-login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/super-admin")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT nome FROM escolas WHERE id = ?", (escola_id,))
    escola_nome = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM turmas WHERE escola_id = ?", (escola_id,))
    total_turmas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM alunos WHERE escola_id = ?", (escola_id,))
    total_alunos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM disciplinas WHERE escola_id = ?", (escola_id,))
    total_disciplinas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM diretores WHERE escola_id = ?", (escola_id,))
    total_diretores = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM secretarias WHERE escola_id = ?", (escola_id,))
    total_secretarias = cursor.fetchone()[0]
    
    conn.close()
    
    return render_template("super_escola.html",
        escola_nome=escola_nome,
        total_turmas=total_turmas,
        total_alunos=total_alunos,
        total_disciplinas=total_disciplinas,
        total_diretores=total_diretores,
        total_secretarias=total_secretarias)

@app.route("/super-admin/escolas/desativar/<int:escola_id>")
def super_desativar_escola(escola_id):
    if session.get("tipo") != "super_admin":
        return redirect("/super-login")
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE escolas SET ativo = 0 WHERE id = ?", (escola_id,))
    conn.commit()
    conn.close()
    
    return redirect("/super-admin")

@app.route("/super-admin/escolas/ativar/<int:escola_id>")
def super_ativar_escola(escola_id):
    if session.get("tipo") != "super_admin":
        return redirect("/super-login")
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE escolas SET ativo = 1 WHERE id = ?", (escola_id,))
    conn.commit()
    conn.close()
    
    return redirect("/super-admin")

@app.route("/super-admin/escolas/renovar/<int:escola_id>")
def super_renovar_licenca(escola_id):
    if session.get("tipo") != "super_admin":
        return redirect("/super-login")
    
    nova_data = int(time.time()) + 365 * 86400
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE escolas SET data_expiracao = ? WHERE id = ?", (nova_data, escola_id))
    conn.commit()
    conn.close()
    
    return redirect("/super-admin")

# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = ""

    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha = (request.form.get("senha") or "").strip()
        tipo = request.form.get("tipo")
        codigo_escola = (request.form.get("codigo_escola") or "").strip()
        ip = request.remote_addr

        if ip in bloqueio_ip and time.time() < bloqueio_ip[ip]:
            return "IP bloqueado", 403

        conn = conectar()
        cursor = conn.cursor()

        try:
            # 🔥 IDENTIFICA A ESCOLA PELO CÓDIGO
            escola_id = None
            
            if codigo_escola:
                cursor.execute("""
                    SELECT id FROM escolas 
                    WHERE chave_licenca = ? OR LOWER(nome) = LOWER(?)
                    LIMIT 1
                """, (codigo_escola, codigo_escola))
                escola = cursor.fetchone()
                if escola:
                    escola_id = escola[0]
                    session["escola_id"] = escola_id
                    
                    cursor.execute("SELECT nome FROM escolas WHERE id = ?", (escola_id,))
                    nome_escola = cursor.fetchone()
                    if nome_escola:
                        session["escola_nome"] = nome_escola[0]
            
            if not escola_id:
                escola_id = session.get("escola_id")
                if not escola_id:
                    cursor.execute("SELECT id FROM escolas LIMIT 1")
                    primeira_escola = cursor.fetchone()
                    if primeira_escola:
                        escola_id = primeira_escola[0]
                        session["escola_id"] = escola_id
                    else:
                        erro = "❌ Nenhuma escola disponível. Contacte o Super Admin."
                        return render_template("login.html", erro=erro)

            # ================= ADMIN =================
            if tipo in ["admin", "coordenador"]:
                cursor.execute("""
                    SELECT valor FROM config 
                    WHERE chave = 'admin_senha' AND escola_id = ?
                """, (escola_id,))
                admin_hash = cursor.fetchone()
                
                if not admin_hash:
                    erro = "❌ Senha do administrador não configurada para esta escola. Contacte o Super Admin."
                    return render_template("login.html", erro=erro)

                cursor.execute("""
                    SELECT valor FROM config 
                    WHERE chave = 'admin_precisa_trocar' AND escola_id = ?
                """, (escola_id,))
                troca = cursor.fetchone()

                if admin_hash and check_password_hash(admin_hash[0], senha):
                    session.clear()
                    session["tipo"] = tipo
                    session["user"] = usuario
                    session["escola_id"] = escola_id

                    cursor.execute("SELECT nome FROM escolas WHERE id = ?", (escola_id,))
                    escola_nome = cursor.fetchone()
                    if escola_nome:
                        session["escola_nome"] = escola_nome[0]

                    if troca and troca[0] == "1":
                        return redirect("/admin/trocar-senha")

                    return redirect("/admin")

                erro = "Credenciais inválidas"

            # ================= PROFESSOR =================
            elif tipo == "professor":
                cursor.execute("""
                    SELECT id, professor_senha, professor_nome, precisa_trocar_senha, escola_id
                    FROM disciplinas
                    WHERE LOWER(TRIM(professor_nome)) = LOWER(TRIM(?))
                    AND escola_id = ?
                    LIMIT 1
                """, (usuario, escola_id))

                prof = cursor.fetchone()

                if prof and prof[1] and check_password_hash(prof[1], senha):
                    if not escola_tem_licenca(prof[4]):
                        erro = "⚠️ Licença da escola expirada. Contacte o administrador."
                    else:
                        session.clear()
                        session["tipo"] = "professor"
                        session["user"] = usuario
                        session["professor_nome"] = usuario
                        session["professor_id"] = prof[0]
                        session["escola_id"] = prof[4]

                        cursor.execute("SELECT nome FROM escolas WHERE id = ?", (prof[4],))
                        nome_escola = cursor.fetchone()
                        if nome_escola:
                            session["escola_nome"] = nome_escola[0]

                        if prof[3] == 1:
                            return redirect("/professor/trocar-senha")

                        return redirect("/professor")

                erro = "Professor ou senha inválida"

            # ================= DIRETOR =================
            elif tipo == "diretor":
                cursor.execute("""
                    SELECT id, senha, turma_id, precisa_trocar_senha, escola_id
                    FROM diretores
                    WHERE LOWER(TRIM(nome)) = LOWER(TRIM(?))
                    AND escola_id = ?
                    LIMIT 1
                """, (usuario, escola_id))

                diretor = cursor.fetchone()

                if diretor and diretor[1] and check_password_hash(diretor[1], senha):
                    if not escola_tem_licenca(diretor[4]):
                        erro = "⚠️ Licença da escola expirada. Contacte o administrador."
                    else:
                        session.clear()
                        session["tipo"] = "diretor"
                        session["user"] = usuario
                        session["diretor_id"] = diretor[0]
                        session["turma_id"] = diretor[2]
                        session["escola_id"] = diretor[4]

                        cursor.execute("SELECT nome FROM escolas WHERE id = ?", (diretor[4],))
                        nome_escola = cursor.fetchone()
                        if nome_escola:
                            session["escola_nome"] = nome_escola[0]

                        if diretor[3] == 1:
                            return redirect("/diretor/trocar-senha")

                        return redirect("/diretor")

                erro = "Diretor ou senha inválida"

            # ================= SECRETARIA =================
            elif tipo == "secretaria":
                cursor.execute("""
                    SELECT id, senha, precisa_trocar_senha, escola_id
                    FROM secretarias
                    WHERE LOWER(TRIM(nome)) = LOWER(TRIM(?))
                    AND escola_id = ?
                    LIMIT 1
                """, (usuario, escola_id))

                sec = cursor.fetchone()

                if sec and sec[1] and check_password_hash(sec[1], senha):
                    if not escola_tem_licenca(sec[3]):
                        erro = "⚠️ Licença da escola expirada. Contacte o administrador."
                    else:
                        session.clear()
                        session["tipo"] = "secretaria"
                        session["user"] = usuario
                        session["secretaria_id"] = sec[0]
                        session["escola_id"] = sec[3]

                        cursor.execute("SELECT nome FROM escolas WHERE id = ?", (sec[3],))
                        nome_escola = cursor.fetchone()
                        if nome_escola:
                            session["escola_nome"] = nome_escola[0]

                        if sec[2] == 1:
                            return redirect("/secretaria/trocar-senha")

                        return redirect("/secretaria")

                erro = "Secretaria ou senha inválida"

            # ================= ALUNO - CORRIGIDO =================
            elif tipo == "aluno":
                cursor.execute("""
                    SELECT a.id, a.nome, a.turma_id, a.senha, a.precisa_criar_senha,
                           a.escola_id, t.ano, t.nome
                    FROM alunos a
                    JOIN turmas t ON a.turma_id = t.id
                    WHERE LOWER(TRIM(a.nome)) = LOWER(TRIM(?))
                    AND a.escola_id = ?
                    LIMIT 1
                """, (usuario, escola_id))
                
                aluno = cursor.fetchone()
                
                if not aluno:
                    erro = "❌ Aluno não encontrado"
                # 🔥 REMOVIDA A VERIFICAÇÃO DE STATUS_PAGAMENTO!
                elif aluno[4] == 1:  # precisa_criar_senha
                    erro = "⚠️ Você precisa criar uma senha primeiro! Acesse 'Criar Senha'."
                elif not aluno[3] or not check_password_hash(aluno[3], senha):
                    erro = "🔒 Senha incorreta!"
                else:
                    session.clear()
                    session["tipo"] = "aluno"
                    session["user"] = usuario
                    session["aluno_id"] = aluno[0]
                    session["turma_id"] = aluno[2]
                    session["escola_id"] = aluno[5]

                    cursor.execute("SELECT nome FROM escolas WHERE id = ?", (aluno[5],))
                    nome_escola = cursor.fetchone()
                    if nome_escola:
                        session["escola_nome"] = nome_escola[0]

                    return redirect("/aluno/dashboard")

        finally:
            conn.close()

    return render_template("login.html", erro=erro)
    
    # ================= LOGOUT =================

@app.route("/logout")
def logout():
    registrar_log("LOGOUT", "Saiu")
    session.clear()
    return redirect("/login")

# ================= ADMIN - TROCAR SENHA =================

@app.route("/admin/trocar-senha", methods=["GET", "POST"])
def admin_trocar_senha():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/login")
    
    erro = ""
    sucesso = ""
    
    if request.method == "POST":
        nova = request.form.get("nova")
        confirmar = request.form.get("confirmar")
        
        if nova != confirmar:
            erro = "As senhas não coincidem"
        elif len(nova) < 4:
            erro = "A senha deve ter pelo menos 4 caracteres"
        else:
            senha_hash = generate_password_hash(nova)
            conn = conectar()
            cursor = conn.cursor()
            
            # 🔥 ATUALIZA A SENHA ADMIN ESPECÍFICA DA ESCOLA
            cursor.execute("""
                UPDATE config SET valor = ? 
                WHERE chave = 'admin_senha' AND escola_id = ?
            """, (senha_hash, escola_id))
            
            cursor.execute("""
                UPDATE config SET valor = '0' 
                WHERE chave = 'admin_precisa_trocar' AND escola_id = ?
            """, (escola_id,))
            
            conn.commit()
            conn.close()
            registrar_log("TROCA_SENHA_ADMIN", f"Escola {escola_id} - {session.get('user')}")
            sucesso = "✅ Senha alterada com sucesso!"
            return redirect("/admin")
    
    return render_template("admin_alterar_senha.html", erro=erro, sucesso=sucesso)
    
    
    # ================= ADMIN HOME =================

@app.route("/admin")
def admin_home():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    
    if not escola_id:
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM escolas LIMIT 1")
        escola = cursor.fetchone()
        conn.close()
        
        if escola:
            session["escola_id"] = escola[0]
            return redirect("/admin")
        else:
            return redirect("/admin/configurar-escola")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, ano, nome FROM turmas 
        WHERE escola_id = ? 
        ORDER BY CAST(ano AS INTEGER), nome
    """, (escola_id,))
    turmas_raw = cursor.fetchall()
    
    turmas = []
    for t in turmas_raw:
        turmas.append({
            "id": t[0],
            "ano": t[1],
            "nome": t[2],
            "nome_completo": f"{t[1]}ª {t[2]}"
        })

    cursor.execute("""
        SELECT id, nome, turma_id, professor_nome 
        FROM disciplinas 
        WHERE escola_id = ?
    """, (escola_id,))
    disciplinas_raw = cursor.fetchall()
    
    disciplinas = []
    for d in disciplinas_raw:
        cursor.execute("SELECT ano, nome FROM turmas WHERE id = ?", (d[2],))
        turma = cursor.fetchone()
        nome_turma = f"{turma[0]}ª {turma[1]}" if turma else "Turma não encontrada"
        
        disciplinas.append({
            "id": d[0],
            "nome": d[1],
            "turma_id": d[2],
            "nome_turma": nome_turma,
            "professor_nome": d[3] if d[3] else "Não atribuído"
        })
    
    cursor.execute("""
        SELECT d.id, d.nome, d.turma_id, t.ano, t.nome
        FROM diretores d
        LEFT JOIN turmas t ON d.turma_id = t.id
        WHERE d.escola_id = ?
        ORDER BY d.nome
    """, (escola_id,))
    diretores_raw = cursor.fetchall()
    
    diretores = []
    for d in diretores_raw:
        if d[3]:
            turma_nome = f"{d[3]}ª {d[4]}"
        else:
            turma_nome = "Sem turma associada"
        
        diretores.append({
            "id": d[0],
            "nome": d[1],
            "turma_id": d[2],
            "turma_nome": turma_nome
        })
    
    cursor.execute("SELECT COUNT(*) FROM alunos WHERE escola_id = ?", (escola_id,))
    alunos = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(DISTINCT professor_nome) FROM disciplinas 
        WHERE professor_nome IS NOT NULL AND professor_nome != '' AND escola_id = ?
    """, (escola_id,))
    professores = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM secretarias WHERE escola_id = ?", (escola_id,))
    secretarias = cursor.fetchone()[0]

    conn.close()

    return render_template("admin.html", 
        turmas=turmas,
        disciplinas=disciplinas,
        diretores=diretores,
        alunos=alunos,
        professores=professores,
        secretarias=secretarias)

# ================= ADMIN - CRIAR TURMA =================

@app.route("/admin/criar-turma", methods=["POST"])
def criar_turma():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano = request.form.get("ano")
    nome = request.form.get("nome")
    
    if not ano or not nome:
        return "Ano e nome da turma são obrigatórios", 400
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM turmas WHERE ano = ? AND nome = ? AND escola_id = ?", (ano, nome, escola_id))
    existe = cursor.fetchone()
    
    if existe:
        conn.close()
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro: Turma já existe!</h2>
            <p>A turma {ano}ª {nome} já está cadastrada nesta escola.</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    
    cursor.execute("INSERT INTO turmas (ano, nome, escola_id) VALUES (?, ?, ?)", (ano, nome, escola_id))
    conn.commit()
    conn.close()
    
    registrar_log("CRIAR_TURMA", f"{ano} {nome}")
    return redirect("/admin")

# ================= ADMIN - CRIAR DIRETOR =================

@app.route("/admin/criar-diretor", methods=["POST"])
def criar_diretor():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    nome = request.form.get("nome")
    turma_id = request.form.get("turma_id")
    
    if not nome or not turma_id:
        return "Nome e turma são obrigatórios", 400
    
    valido, mensagem = validar_nome(nome)
    if not valido:
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro ao criar diretor</h2>
            <p>{mensagem}</p>
            <p><strong>Nome tentado:</strong> {nome}</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    
    if verificar_nome_existente("diretor", nome, escola_id=escola_id):
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro: Nome já existe!</h2>
            <p>O nome <strong>'{nome}'</strong> já está cadastrado como diretor nesta escola.</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, nome FROM diretores WHERE turma_id = ? AND escola_id = ?", (turma_id, escola_id))
    existente = cursor.fetchone()
    
    senha_plana = gerar_senha(nome)
    senha_hash = generate_password_hash(senha_plana)
    
    if existente:
        cursor.execute("""
            UPDATE diretores 
            SET nome = ?, senha = ?, precisa_trocar_senha = 1
            WHERE turma_id = ? AND escola_id = ?
        """, (nome, senha_hash, turma_id, escola_id))
        conn.commit()
        conn.close()
        registrar_log("SUBSTITUIR_DIRETOR", f"{existente[1]} -> {nome} (Turma {turma_id})")
        
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: orange;">🔄 Diretor substituído com sucesso!</h2>
            <p><strong>Antigo diretor:</strong> {existente[1]}</p>
            <p><strong>Novo diretor:</strong> {nome}</p>
            <p><strong>Turma:</strong> {turma_id}</p>
            <p><strong>Nova senha:</strong> {senha_plana}</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    else:
        cursor.execute("""
            INSERT INTO diretores (nome, turma_id, senha, precisa_trocar_senha, escola_id) 
            VALUES (?, ?, ?, 1, ?)
        """, (nome, turma_id, senha_hash, escola_id))
        conn.commit()
        conn.close()
        registrar_log("CRIAR_DIRETOR", f"{nome} - Turma {turma_id}")
        
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: green;">✅ Diretor criado com sucesso!</h2>
            <p><strong>Nome:</strong> {nome}</p>
            <p><strong>Turma:</strong> {turma_id}</p>
            <p><strong>Senha:</strong> {senha_plana}</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """

# ================= ADMIN - CRIAR DISCIPLINA =================

@app.route("/admin/criar-disciplina", methods=["POST"])
def criar_disciplina():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    nome = request.form.get("nome")
    turma_id = request.form.get("turma_id")
    
    if not nome or not turma_id:
        return "Nome da disciplina e turma são obrigatórios", 400
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM disciplinas WHERE nome = ? AND turma_id = ? AND escola_id = ?", (nome, turma_id, escola_id))
    existe = cursor.fetchone()
    
    if existe:
        conn.close()
        cursor.execute("SELECT ano, nome FROM turmas WHERE id = ?", (turma_id,))
        turma = cursor.fetchone()
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro: Disciplina já existe!</h2>
            <p>A disciplina "{nome}" já está cadastrada para a turma {turma[0]}ª {turma[1]}.</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    
    cursor.execute("""
        INSERT INTO disciplinas (nome, turma_id, escola_id) 
        VALUES (?, ?, ?)
    """, (nome, turma_id, escola_id))
    conn.commit()
    conn.close()
    
    registrar_log("CRIAR_DISCIPLINA", nome)
    return redirect("/admin")

@app.route("/admin/criar-disciplina-multiplas", methods=["POST"])
def criar_disciplina_multiplas():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    nome = request.form.get("nome")
    turmas_ids = request.form.getlist("turmas_ids")
    
    if not nome:
        return "Nome da disciplina obrigatório", 400
    if not turmas_ids:
        return "Selecione pelo menos uma turma", 400
    
    conn = conectar()
    cursor = conn.cursor()
    
    criadas = 0
    duplicadas = 0
    
    for turma_id in turmas_ids:
        cursor.execute("SELECT id FROM disciplinas WHERE nome = ? AND turma_id = ? AND escola_id = ?", (nome, turma_id, escola_id))
        existe = cursor.fetchone()
        if existe:
            duplicadas += 1
            continue
        cursor.execute("INSERT INTO disciplinas (nome, turma_id, escola_id) VALUES (?, ?, ?)", (nome, turma_id, escola_id))
        criadas += 1
    
    conn.commit()
    conn.close()
    
    registrar_log("CRIAR_DISCIPLINA_MULTIPLAS", f"{nome} -> {criadas} criadas, {duplicadas} duplicadas ignoradas")
    
    return f"""
    <div style="font-family: Arial; text-align: center; margin-top: 50px;">
        <h2 style="color: green;">✅ Processo concluído!</h2>
        <p>Disciplina "{nome}" adicionada a <strong>{criadas}</strong> turma(s).</p>
        {f'<p style="color: orange;">⚠️ {duplicadas} turma(s) já tinham esta disciplina e foram ignoradas.</p>' if duplicadas > 0 else ''}
        <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
    </div>
    """

# ================= ADMIN - ATRIBUIR PROFESSOR =================

@app.route("/admin/atribuir-professor", methods=["POST"])
def atribuir_professor():
    if not is_admin():
        return redirect("/login")

    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")

    disc_id = request.form.get("disciplina_id")
    nome = request.form.get("professor_nome")
    
    if not disc_id or not nome:
        return "Disciplina e nome do professor são obrigatórios", 400
    
    valido, mensagem = validar_nome(nome)
    if not valido:
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro ao atribuir professor</h2>
            <p>{mensagem}</p>
            <p><strong>Nome tentado:</strong> {nome}</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """

    senha = gerar_senha(nome)
    senha_hash = generate_password_hash(senha)

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM disciplinas WHERE id = ? AND escola_id = ?", (disc_id, escola_id))
    if not cursor.fetchone():
        conn.close()
        return "Disciplina não pertence a esta escola", 400

    cursor.execute("""
        UPDATE disciplinas
        SET professor_nome=?, professor_senha=?, precisa_trocar_senha=1
        WHERE id=? AND escola_id=?
    """, (nome, senha_hash, disc_id, escola_id))

    conn.commit()
    conn.close()

    registrar_log("ATRIBUIR_PROFESSOR", nome)

    return f"""
    <div style="font-family: Arial; text-align: center; margin-top: 50px;">
        <h2 style="color: green;">✅ Professor atribuído com sucesso!</h2>
        <p><strong>Nome:</strong> {nome}</p>
        <p><strong>Senha:</strong> {senha}</p>
        <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
    </div>
    """

# ================= ADMIN - CRIAR SECRETARIA =================

@app.route("/admin/criar-secretaria", methods=["POST"])
def criar_secretaria():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    nome = request.form.get("nome")
    
    if not nome:
        return "Nome da secretária é obrigatório", 400
    
    valido, mensagem = validar_nome(nome)
    if not valido:
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro ao criar secretária</h2>
            <p>{mensagem}</p>
            <p><strong>Nome tentado:</strong> {nome}</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    
    if verificar_nome_existente("secretaria", nome, escola_id=escola_id):
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro: Nome já existe!</h2>
            <p>O nome <strong>'{nome}'</strong> já está cadastrado como secretária nesta escola.</p>
            <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    
    senha_plana = "sec123"
    senha_hash = generate_password_hash(senha_plana)
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO secretarias (nome, senha, precisa_trocar_senha, escola_id) 
        VALUES (?, ?, 1, ?)
    """, (nome, senha_hash, escola_id))
    conn.commit()
    conn.close()
    
    registrar_log("CRIAR_SECRETARIA", nome)
    
    return f"""
    <div style="font-family: Arial; text-align: center; margin-top: 50px;">
        <h2 style="color: green;">✅ Secretária criada com sucesso!</h2>
        <p><strong>Nome:</strong> {nome}</p>
        <p><strong>Senha:</strong> {senha_plana}</p>
        <p style="color: orange;">⚠️ Recomendamos alterar a senha no primeiro acesso.</p>
        <a href="/admin"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
    </div>
    """

# ================= ADMIN - PERÍODOS =================

def configurar_trimestre_ativo():
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT valor FROM config WHERE chave = 'trimestre_ativo'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO config (chave, valor) VALUES ('trimestre_ativo', '1')")
        print("✅ Trimestre ativo configurado: 1º Trimestre")
    
    conn.commit()
    conn.close()

configurar_trimestre_ativo()

@app.route("/admin/trimestre-ativo", methods=["GET", "POST"])
def admin_trimestre_ativo():
    if not is_admin():
        return redirect("/login")
    
    erro = ""
    sucesso = ""
    trimestre_atual = get_trimestre_ativo()
    
    if request.method == "POST":
        novo_trimestre = request.form.get("trimestre")
        if novo_trimestre in ['1', '2', '3']:
            conn = conectar()
            cursor = conn.cursor()
            cursor.execute("UPDATE config SET valor = ? WHERE chave = 'trimestre_ativo'", (str(novo_trimestre),))
            conn.commit()
            conn.close()
            registrar_log("ALTERAR_TRIMESTRE_ATIVO", f"Trimestre {novo_trimestre} ativo")
            sucesso = f"Trimestre {novo_trimestre}º ativado com sucesso!"
            trimestre_atual = int(novo_trimestre)
        else:
            erro = "Trimestre inválido!"
    
    return render_template("admin_trimestre.html", 
        trimestre_atual=trimestre_atual, 
        erro=erro, 
        sucesso=sucesso)

def validar_diferenca_4_meses(inicio1, fim1, inicio2, fim2):
    from datetime import datetime
    
    dt_fim1 = datetime.fromtimestamp(fim1)
    dt_inicio2 = datetime.fromtimestamp(inicio2)
    
    diferenca_meses = (dt_inicio2.year - dt_fim1.year) * 12 + (dt_inicio2.month - dt_fim1.month)
    
    if diferenca_meses != 4:
        return False, f"A diferença deve ser de exatamente 4 meses. Atual: {diferenca_meses} meses"
    
    duracao1 = (datetime.fromtimestamp(fim1) - datetime.fromtimestamp(inicio1)).days
    duracao2 = (datetime.fromtimestamp(fim2) - datetime.fromtimestamp(inicio2)).days
    
    if duracao1 < 110 or duracao1 > 130:
        return False, f"1º Trimestre deve ter aproximadamente 4 meses (cerca de 120 dias). Atual: {duracao1} dias"
    
    if duracao2 < 110 or duracao2 > 130:
        return False, f"2º Trimestre deve ter aproximadamente 4 meses. Atual: {duracao2} dias"
    
    return True, "OK"

@app.route("/admin/periodos", methods=["GET", "POST"])
def ver_periodos():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    erro = ""
    sucesso = ""
    
    if request.method == "POST":
        from datetime import datetime
        
        trimestre = request.form.get("trimestre")
        inicio = request.form.get("inicio")
        fim = request.form.get("fim")
        
        if not trimestre or not inicio or not fim:
            erro = "Campos obrigatórios"
        else:
            try:
                inicio_dt = datetime.strptime(inicio, "%Y-%m-%d")
                fim_dt = datetime.strptime(fim, "%Y-%m-%d")
                inicio_ts = int(inicio_dt.timestamp())
                fim_ts = int(fim_dt.timestamp())
                
                duracao = (fim_dt - inicio_dt).days
                if duracao < 110 or duracao > 130:
                    erro = f"O trimestre deve ter aproximadamente 4 meses (cerca de 120 dias). Duração atual: {duracao} dias"
                else:
                    conn = conectar()
                    cursor = conn.cursor()
                    
                    if trimestre == "2º Trimestre":
                        cursor.execute("""
                            SELECT fim FROM periodos 
                            WHERE trimestre = '1º Trimestre' AND escola_id = ?
                            ORDER BY id DESC LIMIT 1
                        """, (escola_id,))
                        primeiro = cursor.fetchone()
                        if primeiro:
                            valido, msg = validar_diferenca_4_meses(primeiro[0], fim_ts, inicio_ts, fim_ts)
                            if not valido:
                                erro = msg
                                conn.close()
                                return render_template("periodo.html", erro=erro, periodos=[])
                    
                    elif trimestre == "3º Trimestre":
                        cursor.execute("""
                            SELECT fim FROM periodos 
                            WHERE trimestre = '2º Trimestre' AND escola_id = ?
                            ORDER BY id DESC LIMIT 1
                        """, (escola_id,))
                        segundo = cursor.fetchone()
                        if segundo:
                            valido, msg = validar_diferenca_4_meses(segundo[0], fim_ts, inicio_ts, fim_ts)
                            if not valido:
                                erro = msg
                                conn.close()
                                return render_template("periodo.html", erro=erro, periodos=[])
                    
                    if not erro:
                        fim_extensao = fim_ts + (15 * 86400)
                        cursor.execute("""
                            INSERT INTO periodos (trimestre, inicio, fim, fim_extensao, escola_id) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (trimestre, inicio_ts, fim_ts, fim_extensao, escola_id))
                        conn.commit()
                        registrar_log("CRIAR_PERIODO", trimestre)
                        sucesso = f"{trimestre} configurado com sucesso!"
                    
                    conn.close()
                    
            except Exception as e:
                erro = f"Erro nas datas: {e}"
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, trimestre, inicio, fim, fim_extensao 
        FROM periodos 
        WHERE escola_id = ?
        ORDER BY id
    """, (escola_id,))
    dados = cursor.fetchall()
    conn.close()
    
    from datetime import datetime
    agora = int(time.time())
    periodos = []
    
    for p in dados:
        try:
            inicio_str = datetime.fromtimestamp(p[2]).strftime("%d/%m/%Y")
            fim_str = datetime.fromtimestamp(p[3]).strftime("%d/%m/%Y")
            restante = max(0, p[4] - agora)
            duracao = (datetime.fromtimestamp(p[3]) - datetime.fromtimestamp(p[2])).days
            
            periodos.append({
                "id": p[0],
                "trimestre": p[1],
                "inicio": inicio_str,
                "fim": fim_str,
                "restante": restante,
                "duracao": duracao
            })
        except:
            periodos.append({
                "id": p[0],
                "trimestre": p[1],
                "inicio": "Data inválida",
                "fim": "Data inválida",
                "restante": 0,
                "duracao": 0
            })
    
    return render_template("periodo.html", periodos=periodos, erro=erro, sucesso=sucesso)

@app.route("/admin/reabrir-periodo", methods=["GET", "POST"])
def reabrir_periodo():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")

    conn = conectar()
    cursor = conn.cursor()
    erro = ""

    if request.method == "POST":
        trimestre = request.form.get("trimestre")
        dias = request.form.get("dias")

        if not trimestre or not dias:
            return "Campos obrigatórios", 400

        try:
            dias = int(dias)
        except:
            return "Dias inválidos", 400

        agora = int(time.time())
        extensao = agora + (dias * 86400)

        cursor.execute("""
            SELECT id FROM periodos
            WHERE trimestre = ? AND escola_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (trimestre, escola_id))

        periodo = cursor.fetchone()

        if not periodo:
            conn.close()
            return "Período não encontrado", 404

        cursor.execute("""
            UPDATE periodos
            SET fim_extensao = ?
            WHERE id = ? AND escola_id = ?
        """, (extensao, periodo[0], escola_id))

        conn.commit()
        conn.close()

        registrar_log("REABRIR_PERIODO", f"{trimestre} +{dias} dias")
        return redirect("/admin/periodos")

    return render_template("reabrir_periodo.html", erro=erro)

# ================= ADMIN - GRÁFICO =================

@app.route("/admin/grafico")
def admin_grafico():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, ano, nome FROM turmas 
        WHERE escola_id = ?
        ORDER BY CAST(ano AS INTEGER), nome
    """, (escola_id,))
    turmas = cursor.fetchall()
    
    dados = []
    
    for turma in turmas:
        turma_id = turma[0]
        turma_nome = f"{turma[1]} {turma[2]}"
        
        cursor.execute("SELECT id FROM alunos WHERE turma_id = ? AND escola_id = ?", (turma_id, escola_id))
        alunos = cursor.fetchall()
        
        if not alunos:
            dados.append({"turma": turma_nome, "media": 0, "percentagem": 0})
            continue
        
        todas_medias = []
        
        for aluno in alunos:
            cursor.execute("""
                SELECT acs1_t1, acs2_t1, at_t1,
                       acs1_t2, acs2_t2, at_t2,
                       acs1_t3, acs2_t3, at_t3
                FROM notas 
                WHERE aluno_id = ? AND escola_id = ?
            """, (aluno[0], escola_id))
            
            notas = cursor.fetchone()
            if notas:
                t1 = calcular_trimestre(notas[0], notas[1], notas[2])
                t2 = calcular_trimestre(notas[3], notas[4], notas[5])
                t3 = calcular_trimestre(notas[6], notas[7], notas[8])
                media_aluno = calcular_media_final(t1, t2, t3)
                todas_medias.append(media_aluno)
        
        if todas_medias:
            media_geral = round(sum(todas_medias) / len(todas_medias), 1)
            aprovados = sum(1 for m in todas_medias if m >= 10)
            percentagem = round((aprovados / len(todas_medias)) * 100, 1)
        else:
            media_geral = 0
            percentagem = 0
        
        dados.append({
            "turma": turma_nome,
            "media": media_geral,
            "percentagem": percentagem
        })
    
    conn.close()
    
    return render_template("admin_grafico.html", dados=dados)

# ================= ADMIN - LOGS =================

@app.route("/admin/logs")
def ver_logs():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    
    conn = conectar()
    cursor = conn.cursor()
    
    if escola_id:
        cursor.execute("""
            SELECT id, usuario, tipo, acao, detalhes, ip, 
                   datetime(data, 'unixepoch', 'localtime') as data_hora
            FROM logs 
            WHERE escola_id = ?
            ORDER BY id DESC 
            LIMIT 200
        """, (escola_id,))
    else:
        cursor.execute("""
            SELECT id, usuario, tipo, acao, detalhes, ip, 
                   datetime(data, 'unixepoch', 'localtime') as data_hora
            FROM logs 
            ORDER BY id DESC 
            LIMIT 200
        """)
    
    logs = cursor.fetchall()
    conn.close()
    
    return render_template("logs.html", logs=logs)

# ================= ADMIN - BACKUP =================

@app.route("/admin/backup/criar")
def criar_backup():
    if not is_admin():
        return redirect("/login")
    
    try:
        os.makedirs("backups", exist_ok=True)
        data = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        origem = "escola.db"
        escola_nome = session.get("escola_nome", "geral")
        destino = f"backups/escola_{escola_nome}_{data}.db"
        
        shutil.copyfile(origem, destino)
        registrar_log("BACKUP", f"Backup criado: {destino}")
        return f"<h2 style='color:green'>Backup criado com sucesso!</h2><p>{destino}</p><a href='/admin'>Voltar</a>"
    except Exception as e:
        return f"Erro no backup: {e}"

@app.route("/admin/backups")
def listar_backups():
    if not is_admin():
        return redirect("/login")
    
    arquivos = os.listdir("backups")
    backups = []
    
    for a in arquivos:
        path = os.path.join("backups", a)
        tamanho = round(os.path.getsize(path) / 1024, 2)
        backups.append({"nome": a, "tamanho": tamanho})
    
    return render_template("backups.html", backups=backups)

@app.route("/admin/backups/download/<filename>")
def download_backup(filename):
    if not is_admin():
        return redirect("/login")
    return send_from_directory("backups", filename, as_attachment=True)

@app.route("/admin/backups/restaurar/<filename>")
def restaurar_backup(filename):
    if not is_admin():
        return redirect("/login")
    
    try:
        caminho = f"backups/{filename}"
        shutil.copyfile(caminho, "escola.db")
        registrar_log("RESTORE", filename)
        return "<h2 style='color:green'>Backup restaurado com sucesso!</h2><a href='/admin'>Voltar</a>"
    except Exception as e:
        return f"Erro: {e}"

# ================= ADMIN - CONFIGURAR EXAMES =================

@app.route("/admin/configurar-exames")
def admin_configurar_exames():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano_letivo = get_ano_letivo_atual()
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT ano FROM turmas 
        WHERE escola_id = ?
        ORDER BY CAST(ano AS INTEGER)
    """, (escola_id,))
    turmas = cursor.fetchall()
    
    cursor.execute("""
        SELECT ano FROM classes_exames 
        WHERE escola_id = ? AND ativo = 1
    """, (escola_id,))
    classes_com_exame = [c[0] for c in cursor.fetchall()]
    
    conn.close()
    
    return render_template("admin_configurar_exames.html", 
        turmas=turmas,
        classes_com_exame=classes_com_exame,
        ano_letivo=ano_letivo)

@app.route("/admin/salvar-classes-exames", methods=["POST"])
def salvar_classes_exames():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    classes_selecionadas = request.form.getlist("classes_exame")
    
    if not classes_selecionadas:
        return redirect("/admin/configurar-exames")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE classes_exames SET ativo = 0 WHERE escola_id = ?", (escola_id,))
    
    for classe in classes_selecionadas:
        cursor.execute("""
            INSERT INTO classes_exames (ano, ativo, escola_id) 
            VALUES (?, 1, ?)
            ON CONFLICT (escola_id, ano) DO UPDATE SET ativo = 1
        """, (classe, escola_id))
    
    conn.commit()
    
    primeira_classe = classes_selecionadas[0]
    cursor.execute("""
        SELECT id, ano, nome FROM turmas 
        WHERE ano = ? AND escola_id = ?
        ORDER BY nome 
        LIMIT 1
    """, (primeira_classe, escola_id))
    
    turma = cursor.fetchone()
    conn.close()
    
    registrar_log("CONFIGURAR_CLASSES_EXAMES", f"Classes: {', '.join(classes_selecionadas)}")
    
    if turma:
        return redirect(f"/admin/disciplinas-exames/{turma[0]}")
    else:
        return redirect("/admin/configurar-exames")

@app.route("/admin/disciplinas-exames/<int:turma_id>")
def admin_disciplinas_exames(turma_id):
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano_letivo = get_ano_letivo_atual()
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT ano, nome FROM turmas WHERE id = ? AND escola_id = ?", (turma_id, escola_id))
    turma = cursor.fetchone()
    
    cursor.execute("SELECT id, nome FROM disciplinas WHERE turma_id = ? AND escola_id = ?", (turma_id, escola_id))
    disciplinas = cursor.fetchall()
    
    cursor.execute("""
        SELECT disciplina_id FROM disciplinas_exames 
        WHERE turma_id = ? AND ano_letivo = ? AND escola_id = ?
    """, (turma_id, ano_letivo, escola_id))
    exames_existentes = [e[0] for e in cursor.fetchall()]
    
    conn.close()
    
    return render_template("admin_disciplinas_exames.html",
        turma=turma,
        disciplinas=disciplinas,
        exames_existentes=exames_existentes,
        turma_id=turma_id,
        ano_letivo=ano_letivo)

@app.route("/admin/salvar-disciplinas-exames", methods=["POST"])
def salvar_disciplinas_exames():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    turma_id = request.form.get("turma_id")
    disciplinas_exame = request.form.getlist("disciplinas_exame")
    ano_letivo = get_ano_letivo_atual()
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM disciplinas_exames 
        WHERE turma_id = ? AND ano_letivo = ? AND escola_id = ?
    """, (turma_id, ano_letivo, escola_id))
    
    for disc_id in disciplinas_exame:
        cursor.execute("""
            INSERT INTO disciplinas_exames (disciplina_id, turma_id, ano_letivo, escola_id)
            VALUES (?, ?, ?, ?)
        """, (disc_id, turma_id, ano_letivo, escola_id))
    
    conn.commit()
    conn.close()
    
    registrar_log("CONFIGURAR_DISCIPLINAS_EXAMES", f"Turma {turma_id}: {len(disciplinas_exame)} disciplinas")
    return redirect(f"/admin/disciplinas-exames/{turma_id}")

# ================= ADMIN - TRANSFERÊNCIA DE ANO =================

@app.route("/admin/transitar-ano")
def admin_transitar_ano():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano_atual = get_ano_letivo_atual()
    ano_novo = str(int(ano_atual) + 1)
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT t.id, t.ano, t.nome, COUNT(a.id) as total_alunos
        FROM turmas t
        LEFT JOIN alunos a ON t.id = a.turma_id
        WHERE t.escola_id = ?
        GROUP BY t.id
        ORDER BY t.ano, t.nome
    """, (escola_id,))
    
    turmas = cursor.fetchall()
    conn.close()
    
    return render_template("admin_transitar_ano.html",
        ano_atual=ano_atual,
        ano_novo=ano_novo,
        turmas=turmas)

@app.route("/admin/executar-transicao", methods=["POST"])
def executar_transicao():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano_atual = get_ano_letivo_atual()
    ano_novo = str(int(ano_atual) + 1)
    
    arquivar_ano_letivo(ano_atual)
    resetar_para_novo_ano()
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, ano, nome FROM turmas WHERE escola_id = ?", (escola_id,))
    turmas_atuais = cursor.fetchall()
    
    for turma in turmas_atuais:
        novo_ano = str(int(turma[1]) + 1)
        cursor.execute("SELECT id FROM turmas WHERE ano = ? AND nome = ? AND escola_id = ?", (novo_ano, turma[2], escola_id))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO turmas (ano, nome, escola_id) VALUES (?, ?, ?)", (novo_ano, turma[2], escola_id))
    
    cursor.execute("UPDATE config SET valor = ? WHERE chave = 'ano_letivo_atual' AND escola_id = ?", (ano_novo, escola_id))
    
    conn.commit()
    conn.close()
    
    registrar_log("TRANSICAO_ANO", f"{ano_atual} → {ano_novo} - Sistema resetado para novo ano")
    return redirect("/admin")

@app.route("/admin/historico/<ano_letivo>")
def ver_historico(ano_letivo):
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT nome, turma_nome, status_pagamento
        FROM alunos_historico
        WHERE ano_letivo = ? AND escola_id = ?
        ORDER BY nome
    """, (ano_letivo, escola_id))
    
    alunos = cursor.fetchall()
    
    cursor.execute("""
        SELECT aluno_nome, disciplina_nome, 
               acs1_t1, acs2_t1, at_t1,
               acs1_t2, acs2_t2, at_t2,
               acs1_t3, acs2_t3, at_t3,
               media_final, nota_exame, media_com_exame, aprovado
        FROM notas_historico
        WHERE ano_letivo = ? AND escola_id = ?
        ORDER BY aluno_nome, disciplina_nome
    """, (ano_letivo, escola_id))
    
    notas = cursor.fetchall()
    
    cursor.execute("""
        SELECT ano_letivo, data_arquivamento 
        FROM historico_anos 
        WHERE escola_id = ?
        ORDER BY ano_letivo DESC
    """, (escola_id,))
    anos_disponiveis = cursor.fetchall()
    
    conn.close()
    
    return render_template("historico_ano.html",
        ano_letivo=ano_letivo,
        alunos=alunos,
        notas=notas,
        anos_disponiveis=anos_disponiveis,
        is_historico=True)

# ================= ADMIN - CONFIGURAR PAGAMENTOS =================

@app.route("/admin/configurar-pagamentos", methods=["GET", "POST"])
def admin_configurar_pagamentos():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    erro = ""
    sucesso = ""
    
    if request.method == "POST":
        valor_matricula = request.form.get("valor_matricula")
        valor_mensalidade = request.form.get("valor_mensalidade")
        valor_testes = request.form.get("valor_testes")
        
        conn = conectar()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE config_pagamentos 
            SET ativo = 0 
            WHERE escola_id = ? AND tipo IN ('matricula', 'mensalidade', 'testes')
        """, (escola_id,))
        
        valores = [
            ('matricula', valor_matricula),
            ('mensalidade', valor_mensalidade),
            ('testes', valor_testes)
        ]
        
        for tipo, valor in valores:
            if valor and float(valor) > 0:
                cursor.execute("""
                    INSERT INTO config_pagamentos (escola_id, tipo, valor, ano, ativo)
                    VALUES (?, ?, ?, ?, 1)
                """, (escola_id, tipo, float(valor), datetime.now().year))
        
        conn.commit()
        conn.close()
        sucesso = "✅ Valores de pagamento atualizados com sucesso!"
        registrar_log("CONFIGURAR_PAGAMENTOS", f"Escola {escola_id}")
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tipo, valor FROM config_pagamentos 
        WHERE escola_id = ? AND ativo = 1
        ORDER BY id DESC
    """, (escola_id,))
    valores = cursor.fetchall()
    conn.close()
    
    valor_matricula = 0
    valor_mensalidade = 0
    valor_testes = 0
    
    for tipo, valor in valores:
        if tipo == 'matricula':
            valor_matricula = valor
        elif tipo == 'mensalidade':
            valor_mensalidade = valor
        elif tipo == 'testes':
            valor_testes = valor
    
    return render_template("admin_configurar_pagamentos.html",
        valor_matricula=valor_matricula,
        valor_mensalidade=valor_mensalidade,
        valor_testes=valor_testes,
        erro=erro,
        sucesso=sucesso)

# ================= SECRETARIA HOME =================

@app.route("/secretaria")
def secretaria_home():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, nome, turma_id FROM alunos 
        WHERE escola_id = ?
        LIMIT 20
    """, (escola_id,))
    alunos = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM alunos WHERE escola_id = ?", (escola_id,))
    total_alunos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM turmas WHERE escola_id = ?", (escola_id,))
    total_turmas = cursor.fetchone()[0]
    
    conn.close()
    
    return render_template("secretaria.html",
        alunos=alunos,
        total_alunos=total_alunos,
        total_turmas=total_turmas)

# ================= SECRETARIA - TROCAR SENHA =================

@app.route("/secretaria/trocar-senha", methods=["GET", "POST"])
def secretaria_trocar_senha():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    erro = ""
    sucesso = ""
    
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual")
        nova_senha = request.form.get("nova_senha")
        confirmar_senha = request.form.get("confirmar_senha")
        
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT senha FROM secretarias WHERE id=?", (session["secretaria_id"],))
        sec = cursor.fetchone()
        
        if not sec or not check_password_hash(sec[0], senha_atual):
            erro = "Senha atual incorreta"
        elif nova_senha != confirmar_senha:
            erro = "As senhas não coincidem"
        elif len(nova_senha) < 4:
            erro = "A senha deve ter pelo menos 4 caracteres"
        else:
            senha_hash = generate_password_hash(nova_senha)
            cursor.execute("UPDATE secretarias SET senha=?, precisa_trocar_senha=0 WHERE id=?", 
                          (senha_hash, session["secretaria_id"]))
            conn.commit()
            registrar_log("TROCA_SENHA_SECRETARIA", session["user"])
            sucesso = "Senha alterada com sucesso!"
            conn.close()
            return redirect("/secretaria")
        
        conn.close()
    
    return render_template("secretaria_trocar_senha.html", erro=erro, sucesso=sucesso)

# ================= SECRETARIA - MATRICULAR =================

@app.route("/secretaria/matricular", methods=["POST"])
def matricular_aluno():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    nome = request.form.get("nome")
    classe = request.form.get("ano")
    
    if not nome or not classe:
        return "Nome e classe são obrigatórios", 400
    
    valido, mensagem = validar_nome(nome)
    if not valido:
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro ao matricular aluno</h2>
            <p>{mensagem}</p>
            <p><strong>Nome tentado:</strong> {nome}</p>
            <a href="/secretaria/alunos"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, ano, nome FROM turmas WHERE ano=? AND escola_id=?", (classe, escola_id))
    turmas = cursor.fetchall()
    
    if not turmas:
        conn.close()
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">❌ Erro: Nenhuma turma criada para a {classe}ª classe</h2>
            <a href="/secretaria/alunos"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
        </div>
        """
    
    for turma in turmas:
        turma_id = turma[0]
        if verificar_nome_existente("aluno", nome, turma_id, escola_id):
            turma_nome = f"{turma[1]}ª {turma[2]}"
            conn.close()
            return f"""
            <div style="font-family: Arial; text-align: center; margin-top: 50px;">
                <h2 style="color: red;">❌ Erro: Aluno já matriculado!</h2>
                <p>O aluno <strong>'{nome}'</strong> já está matriculado na turma <strong>{turma_nome}</strong>.</p>
                <a href="/secretaria/alunos"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
            </div>
            """
    
    menor_turma = None
    menor_qtd = None
    
    for turma in turmas:
        turma_id = turma[0]
        cursor.execute("SELECT COUNT(*) FROM alunos WHERE turma_id=? AND escola_id=?", (turma_id, escola_id))
        qtd = cursor.fetchone()[0]
        
        if menor_qtd is None or qtd < menor_qtd:
            menor_qtd = qtd
            menor_turma = turma_id
    
    cursor.execute("""
        INSERT INTO alunos (nome, turma_id, status_pagamento, senha, precisa_criar_senha, escola_id) 
        VALUES (?, ?, 'pendente', NULL, 1, ?)
    """, (nome, menor_turma, escola_id))
    aluno_id = cursor.lastrowid
    
    cursor.execute("SELECT id FROM disciplinas WHERE turma_id=? AND escola_id=?", (menor_turma, escola_id))
    for d in cursor.fetchall():
        cursor.execute("INSERT OR IGNORE INTO notas (aluno_id, disciplina_id, escola_id) VALUES (?, ?, ?)", (aluno_id, d[0], escola_id))
    
    conn.commit()
    conn.close()
    
    turma_nome = ""
    for turma in turmas:
        if turma[0] == menor_turma:
            turma_nome = f"{turma[1]}ª {turma[2]}"
            break
    
    registrar_log("MATRICULAR_ALUNO", f"{nome} - Turma {turma_nome}")
    
    return f"""
    <div style="font-family: Arial; text-align: center; margin-top: 50px;">
        <h2 style="color: green;">✅ Aluno matriculado com sucesso!</h2>
        <p><strong>Nome:</strong> {nome}</p>
        <p><strong>Turma:</strong> {turma_nome}</p>
        <p><strong>Status de pagamento:</strong> Pendente</p>
        <p style="color: orange; font-size: 14px; margin-top: 15px; border-top: 1px solid #ddd; padding-top: 15px;">
            ⚠️ <strong>Próximo passo:</strong> O aluno deve acessar o Portal do Aluno e criar sua senha.
            <br>
            <strong>Credenciais iniciais:</strong> Nome = <strong>{nome}</strong> | Turma = <strong>{turma_nome}</strong>
            <br>
            <br>
            <a href="/aluno" style="color: #2563eb; font-weight: bold;">🔗 Clique aqui para acessar o Portal do Aluno</a>
        </p>
        <a href="/secretaria/alunos"><button style="padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer;">← Voltar</button></a>
    </div>
    """

# ================= SECRETARIA - ALUNOS =================

@app.route("/secretaria/alunos")
def secretaria_alunos():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    turma_filtro = request.args.get("turma_id")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, ano, nome FROM turmas WHERE escola_id = ? ORDER BY ano, nome", (escola_id,))
    turmas = cursor.fetchall()
    
    if turma_filtro:
        cursor.execute("""
            SELECT alunos.id, alunos.nome, turmas.ano, turmas.nome, alunos.status_pagamento
            FROM alunos 
            JOIN turmas ON alunos.turma_id = turmas.id
            WHERE turmas.id=? AND alunos.escola_id=?
            ORDER BY alunos.nome
        """, (turma_filtro, escola_id))
    else:
        cursor.execute("""
            SELECT alunos.id, alunos.nome, turmas.ano, turmas.nome, alunos.status_pagamento
            FROM alunos 
            JOIN turmas ON alunos.turma_id = turmas.id
            WHERE alunos.escola_id=?
            ORDER BY turmas.ano, turmas.nome
        """, (escola_id,))
    
    alunos = cursor.fetchall()
    conn.close()
    
    return render_template("secretaria_alunos.html", 
        alunos=alunos, 
        turmas=turmas,
        turma_selecionada=turma_filtro)

# ================= SECRETARIA - ALTERAR PAGAMENTO =================

@app.route("/secretaria/alterar-pagamento", methods=["POST"])
def alterar_pagamento():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    aluno_id = request.form.get("aluno_id")
    status = request.form.get("status")
    
    if not aluno_id or status not in ['pago', 'pendente']:
        return "Dados inválidos", 400
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT nome FROM alunos WHERE id = ? AND escola_id = ?", (aluno_id, escola_id))
    aluno = cursor.fetchone()
    
    cursor.execute("UPDATE alunos SET status_pagamento = ? WHERE id = ? AND escola_id = ?", (status, aluno_id, escola_id))
    conn.commit()
    conn.close()
    
    registrar_log("ALTERAR_PAGAMENTO", f"Aluno {aluno[0]} -> {status}")
    
    return redirect("/secretaria/alunos")

# ================= SECRETARIA - MUDAR TURMA =================

@app.route("/secretaria/mudar-turma", methods=["POST"])
def mudar_turma():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    aluno_id = request.form.get("aluno_id")
    nova_turma = request.form.get("turma_id")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE alunos SET turma_id=? WHERE id=? AND escola_id=?", (nova_turma, aluno_id, escola_id))
    cursor.execute("DELETE FROM notas WHERE aluno_id=? AND escola_id=?", (aluno_id, escola_id))
    
    cursor.execute("SELECT id FROM disciplinas WHERE turma_id=? AND escola_id=?", (nova_turma, escola_id))
    disciplinas = cursor.fetchall()
    
    for d in disciplinas:
        cursor.execute("INSERT INTO notas (aluno_id, disciplina_id, escola_id) VALUES (?, ?, ?)", (aluno_id, d[0], escola_id))
    
    conn.commit()
    conn.close()
    
    registrar_log("MUDAR_TURMA", f"Aluno {aluno_id} -> turma {nova_turma}")
    return redirect("/secretaria/alunos")

# ================= SECRETARIA - PDF TURMA =================

@app.route("/secretaria/pdf-turma/<int:turma_id>")
def pdf_turma(turma_id):
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT ano, nome FROM turmas WHERE id=? AND escola_id=?", (turma_id, escola_id))
    turma = cursor.fetchone()
    
    if not turma:
        conn.close()
        return "Turma não encontrada", 404
    
    cursor.execute("SELECT nome FROM alunos WHERE turma_id=? AND escola_id=? ORDER BY nome", (turma_id, escola_id))
    alunos = cursor.fetchall()
    conn.close()
    
    caminho = f"relatorios/turma_{turma_id}.pdf"
    
    doc = SimpleDocTemplate(caminho, pagesize=landscape(A4))
    elementos = []
    estilos = getSampleStyleSheet()
    
    titulo = Paragraph(f"Lista de Alunos - {turma[0]} {turma[1]}", estilos["Title"])
    elementos.append(titulo)
    elementos.append(Spacer(1, 20))
    
    dados = [["Nº", "Nome do Aluno"]]
    contador = 1
    
    for aluno in alunos:
        dados.append([contador, aluno[0]])
        contador += 1
    
    tabela = Table(dados)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.blue),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 1, colors.black),
    ]))
    
    elementos.append(tabela)
    doc.build(elementos)
    
    registrar_log("GERAR_PDF_TURMA", f"Turma {turma_id}")
    return send_file(caminho, as_attachment=True)

# ================= SECRETARIA - PAGAMENTOS DO ALUNO =================

@app.route("/secretaria/pagamentos/<int:aluno_id>")
def ver_pagamentos_aluno(aluno_id):
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano_atual = datetime.now().year
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, nome, turma_id, status_pagamento 
        FROM alunos 
        WHERE id = ? AND escola_id = ?
    """, (aluno_id, escola_id))
    aluno = cursor.fetchone()
    
    if not aluno:
        conn.close()
        return "Aluno não encontrado", 404
    
    cursor.execute("""
        SELECT tipo, mes, ano, valor_pago, valor_esperado, status, data_pagamento
        FROM pagamentos_alunos
        WHERE aluno_id = ? AND escola_id = ?
        ORDER BY ano DESC, mes DESC
    """, (aluno_id, escola_id))
    
    pagamentos = cursor.fetchall()
    conn.close()
    
    valor_mensalidade = get_valor_pagamento(escola_id, 'mensalidade')
    valor_matricula = get_valor_pagamento(escola_id, 'matricula')
    valor_testes = get_valor_pagamento(escola_id, 'testes')
    
    return render_template("pagamentos_aluno.html",
        aluno=aluno,
        pagamentos=pagamentos,
        meses=MESES,
        ano_atual=ano_atual,
        meses_uteis=MESES_UTEIS,
        valor_mensalidade=valor_mensalidade,
        valor_matricula=valor_matricula,
        valor_testes=valor_testes)

@app.route("/secretaria/marcar-pago", methods=["POST"])
def marcar_pago():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    aluno_id = request.form.get("aluno_id")
    tipo = request.form.get("tipo")
    mes = request.form.get("mes")
    ano = request.form.get("ano")
    
    if not aluno_id or not tipo:
        return "Dados inválidos", 400
    
    valor_esperado = get_valor_pagamento(escola_id, tipo)
    if valor_esperado == 0:
        return "Valor não configurado para este tipo de pagamento", 400
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id FROM pagamentos_alunos
        WHERE aluno_id = ? AND tipo = ? AND mes = ? AND ano = ? AND escola_id = ?
    """, (aluno_id, tipo, mes, ano, escola_id))
    
    existe = cursor.fetchone()
    
    if existe:
        cursor.execute("""
            UPDATE pagamentos_alunos
            SET status = 'pago', valor_pago = ?, data_pagamento = ?
            WHERE id = ?
        """, (valor_esperado, int(time.time()), existe[0]))
    else:
        cursor.execute("""
            INSERT INTO pagamentos_alunos 
            (aluno_id, escola_id, tipo, mes, ano, valor_pago, valor_esperado, data_pagamento, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pago')
        """, (aluno_id, escola_id, tipo, mes, ano, valor_esperado, valor_esperado, int(time.time())))
    
    conn.commit()
    conn.close()
    
    registrar_log("MARCAR_PAGO", f"Aluno {aluno_id} - {tipo} - {mes}/{ano}")
    return redirect(f"/secretaria/pagamentos/{aluno_id}")

@app.route("/secretaria/desmarcar-pago", methods=["POST"])
def desmarcar_pago():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    aluno_id = request.form.get("aluno_id")
    tipo = request.form.get("tipo")
    mes = request.form.get("mes")
    ano = request.form.get("ano")
    
    if not aluno_id or not tipo:
        return "Dados inválidos", 400
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE pagamentos_alunos
        SET status = 'pendente', valor_pago = 0
        WHERE aluno_id = ? AND tipo = ? AND mes = ? AND ano = ? AND escola_id = ?
    """, (aluno_id, tipo, mes, ano, escola_id))
    
    conn.commit()
    conn.close()
    
    registrar_log("DESMARCAR_PAGO", f"Aluno {aluno_id} - {tipo} - {mes}/{ano}")
    return redirect(f"/secretaria/pagamentos/{aluno_id}")

# ================= SECRETARIA - RELATÓRIOS FINANCEIROS =================

@app.route("/secretaria/relatorios")
def relatorios_pagamentos():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano_atual = datetime.now().year
    mes_selecionado = request.args.get("mes", type=int)
    turma_filtro = request.args.get("turma_id", type=int)
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, ano, nome FROM turmas 
        WHERE escola_id = ?
        ORDER BY CAST(ano AS INTEGER), nome
    """, (escola_id,))
    turmas = cursor.fetchall()
    
    query = """
        SELECT 
            t.id as turma_id,
            t.ano || 'ª ' || t.nome as turma_nome,
            COUNT(DISTINCT a.id) as total_alunos,
            SUM(CASE WHEN p.tipo = 'matricula' AND p.status = 'pago' THEN p.valor_pago ELSE 0 END) as total_matriculas,
            SUM(CASE WHEN p.tipo = 'mensalidade' AND p.status = 'pago' THEN p.valor_pago ELSE 0 END) as total_mensalidades,
            SUM(CASE WHEN p.tipo = 'testes' AND p.status = 'pago' THEN p.valor_pago ELSE 0 END) as total_testes,
            SUM(CASE WHEN p.status = 'pago' THEN p.valor_pago ELSE 0 END) as total_geral,
            COUNT(CASE WHEN p.status = 'pendente' THEN 1 END) as pendentes
        FROM turmas t
        JOIN alunos a ON t.id = a.turma_id
        LEFT JOIN pagamentos_alunos p ON a.id = p.aluno_id AND p.escola_id = ?
        WHERE t.escola_id = ?
    """
    
    params = [escola_id, escola_id]
    
    if mes_selecionado:
        query += " AND p.mes = ?"
        params.append(mes_selecionado)
    
    if turma_filtro:
        query += " AND t.id = ?"
        params.append(turma_filtro)
    
    query += " GROUP BY t.id ORDER BY t.ano, t.nome"
    
    cursor.execute(query, params)
    relatorios = cursor.fetchall()
    
    query_geral = """
        SELECT 
            SUM(CASE WHEN tipo = 'matricula' AND status = 'pago' THEN valor_pago ELSE 0 END) as total_matriculas,
            SUM(CASE WHEN tipo = 'mensalidade' AND status = 'pago' THEN valor_pago ELSE 0 END) as total_mensalidades,
            SUM(CASE WHEN tipo = 'testes' AND status = 'pago' THEN valor_pago ELSE 0 END) as total_testes,
            SUM(CASE WHEN status = 'pago' THEN valor_pago ELSE 0 END) as total_geral,
            COUNT(CASE WHEN status = 'pendente' THEN 1 END) as pendentes,
            COUNT(CASE WHEN status = 'pago' THEN 1 END) as pagos
        FROM pagamentos_alunos
        WHERE escola_id = ?
    """
    
    params_geral = [escola_id]
    
    if mes_selecionado:
        query_geral += " AND mes = ?"
        params_geral.append(mes_selecionado)
    
    cursor.execute(query_geral, params_geral)
    total_geral = cursor.fetchone()
    
    conn.close()
    
    return render_template("relatorios_pagamentos.html",
        relatorios=relatorios,
        total_geral=total_geral,
        ano_atual=ano_atual,
        meses=MESES,
        meses_uteis=MESES_UTEIS,
        mes_selecionado=mes_selecionado,
        turmas=turmas,
        turma_filtro=turma_filtro)

@app.route("/secretaria/relatorios/pdf")
def relatorios_pagamentos_pdf():
    if session.get("tipo") != "secretaria":
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano_atual = datetime.now().year
    mes_selecionado = request.args.get("mes", type=int)
    
    conn = conectar()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            t.ano || 'ª ' || t.nome as turma_nome,
            COUNT(DISTINCT a.id) as total_alunos,
            SUM(CASE WHEN p.tipo = 'matricula' AND p.status = 'pago' THEN p.valor_pago ELSE 0 END) as total_matriculas,
            SUM(CASE WHEN p.tipo = 'mensalidade' AND p.status = 'pago' THEN p.valor_pago ELSE 0 END) as total_mensalidades,
            SUM(CASE WHEN p.tipo = 'testes' AND p.status = 'pago' THEN p.valor_pago ELSE 0 END) as total_testes,
            SUM(CASE WHEN p.status = 'pago' THEN p.valor_pago ELSE 0 END) as total_geral
        FROM turmas t
        JOIN alunos a ON t.id = a.turma_id
        LEFT JOIN pagamentos_alunos p ON a.id = p.aluno_id AND p.escola_id = ?
        WHERE t.escola_id = ?
    """
    
    params = [escola_id, escola_id]
    
    if mes_selecionado:
        query += " AND p.mes = ?"
        params.append(mes_selecionado)
    
    query += " GROUP BY t.id ORDER BY t.ano, t.nome"
    
    cursor.execute(query, params)
    dados = cursor.fetchall()
    
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status = 'pago' THEN valor_pago ELSE 0 END) as total_geral
        FROM pagamentos_alunos
        WHERE escola_id = ?
    """, (escola_id,))
    total_geral = cursor.fetchone()[0] or 0
    
    conn.close()
    
    caminho = f"relatorios/relatorio_pagamentos_{escola_id}_{int(time.time())}.pdf"
    doc = SimpleDocTemplate(caminho, pagesize=A4)
    elementos = []
    estilos = getSampleStyleSheet()
    
    titulo = Paragraph(f"Relatório de Pagamentos", estilos["Title"])
    elementos.append(titulo)
    
    subtitulo = Paragraph(f"Ano: {ano_atual}" + (f" - Mês: {MESES.get(mes_selecionado, 'Todos')}" if mes_selecionado else " - Todos os Meses"), estilos["Heading2"])
    elementos.append(subtitulo)
    elementos.append(Spacer(1, 0.5*cm))
    
    dados_tabela = [["Turma", "Alunos", "Matrículas", "Mensalidades", "Testes", "Total"]]
    
    for linha in dados:
        dados_tabela.append([
            linha[0],
            str(linha[1]),
            f"{linha[2]:.2f} MT",
            f"{linha[3]:.2f} MT",
            f"{linha[4]:.2f} MT",
            f"{linha[5]:.2f} MT"
        ])
    
    dados_tabela.append(["TOTAL GERAL", "", "", "", "", f"{total_geral:.2f} MT"])
    
    tabela = Table(dados_tabela, colWidths=[4*cm, 2*cm, 3*cm, 3*cm, 3*cm, 3*cm])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    elementos.append(tabela)
    doc.build(elementos)
    
    registrar_log("GERAR_RELATORIO_PAGAMENTOS", f"Escola {escola_id} - PDF gerado")
    return send_file(caminho, as_attachment=True)

# ================= DIRETOR HOME =================

@app.route("/diretor")
def diretor_home():
    if not is_diretor():
        return redirect("/login")
    
    escola_id = get_escola_id()
    turma_id = session.get("turma_id")
    
    if not escola_id:
        return redirect("/admin/escolas")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT ano, nome FROM turmas WHERE id = ? AND escola_id = ?", (turma_id, escola_id))
    turma = cursor.fetchone()
    turma_nome = f"{turma[0]} {turma[1]}" if turma else "Turma não encontrada"
    
    cursor.execute("""
        SELECT d.id, d.nome, COALESCE(o.ordem, 999) as ordem
        FROM disciplinas d
        LEFT JOIN ordem_disciplinas o ON d.id = o.disciplina_id 
            AND o.escola_id = ? AND o.turma_id = ? AND o.ano_letivo = ?
        WHERE d.turma_id = ? AND d.escola_id = ?
        ORDER BY COALESCE(o.ordem, 999), d.nome
    """, (escola_id, turma_id, get_ano_letivo_atual(), turma_id, escola_id))
    
    disciplinas_raw = cursor.fetchall()
    
    disciplinas = []
    for d in disciplinas_raw:
        is_qualitativa = disciplina_eh_qualitativa(d[0], escola_id)
        disciplinas.append({
            "id": d[0],
            "nome": d[1],
            "qualitativa": is_qualitativa
        })
    
    cursor.execute("SELECT id, nome FROM alunos WHERE turma_id = ? AND escola_id = ?", (turma_id, escola_id))
    alunos_raw = cursor.fetchall()
    
    alunos = []
    
    for aluno in alunos_raw:
        aluno_id = aluno[0]
        aluno_nome = aluno[1]
        
        notas_disciplinas = []
        medias_gerais = []
        
        for disc in disciplinas_raw:
            disc_id = disc[0]
            is_qualitativa = disciplina_eh_qualitativa(disc_id, escola_id)
            
            cursor.execute("""
                SELECT acs1_t1, acs2_t1, at_t1,
                       acs1_t2, acs2_t2, at_t2,
                       acs1_t3, acs2_t3, at_t3
                FROM notas
                WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
            """, (aluno_id, disc_id, escola_id))
            
            notas = cursor.fetchone()
            
            qualitativas = {}
            if is_qualitativa:
                cursor.execute("""
                    SELECT trimestre, qualidade FROM notas_qualitativas
                    WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
                """, (aluno_id, disc_id, escola_id))
                for q in cursor.fetchall():
                    qualitativas[q[0]] = q[1]
            
            if notas:
                acs1_t1, acs2_t1, at_t1 = notas[0] or 0, notas[1] or 0, notas[2] or 0
                acs1_t2, acs2_t2, at_t2 = notas[3] or 0, notas[4] or 0, notas[5] or 0
                acs1_t3, acs2_t3, at_t3 = notas[6] or 0, notas[7] or 0, notas[8] or 0
                
                media_t1 = calcular_trimestre(acs1_t1, acs2_t1, at_t1)
                media_t2 = calcular_trimestre(acs1_t2, acs2_t2, at_t2)
                media_t3 = calcular_trimestre(acs1_t3, acs2_t3, at_t3)
                media_final = calcular_media_final(media_t1, media_t2, media_t3) or 0
                medias_gerais.append(media_final)
            else:
                acs1_t1 = acs2_t1 = at_t1 = 0
                acs1_t2 = acs2_t2 = at_t2 = 0
                acs1_t3 = acs2_t3 = at_t3 = 0
                media_t1 = media_t2 = media_t3 = 0
                media_final = 0
                medias_gerais.append(0)
            
            notas_disciplinas.append({
                "acs1_t1": acs1_t1, "acs2_t1": acs2_t1, "at_t1": at_t1, "media_t1": media_t1,
                "acs1_t2": acs1_t2, "acs2_t2": acs2_t2, "at_t2": at_t2, "media_t2": media_t2,
                "acs1_t3": acs1_t3, "acs2_t3": acs2_t3, "at_t3": at_t3, "media_t3": media_t3,
                "media_final": media_final,
                "qualitativa_t1": qualitativas.get(1, ''),
                "qualitativa_t2": qualitativas.get(2, ''),
                "qualitativa_t3": qualitativas.get(3, ''),
                "is_qualitativa": is_qualitativa
            })
        
        media_geral = round(sum(medias_gerais) / len(medias_gerais), 1) if medias_gerais else 0
        
        alunos.append({
            "nome": aluno_nome,
            "notas": notas_disciplinas,
            "media_geral": media_geral
        })
    
    conn.close()
    
    return render_template("diretor.html", 
        alunos=alunos,
        disciplinas=disciplinas,
        turma_nome=turma_nome)

# ================= DIRETOR - TROCAR SENHA =================

@app.route("/diretor/trocar-senha", methods=["GET", "POST"])
def diretor_trocar_senha():
    if not is_diretor():
        return redirect("/login")
    
    escola_id = get_escola_id()
    diretor_id = session.get("diretor_id")
    erro = ""
    
    if request.method == "POST":
        senha = request.form.get("senha")
        confirmar = request.form.get("confirmar_senha")
        
        if not senha:
            erro = "Senha obrigatória"
        elif senha != confirmar:
            erro = "As senhas não coincidem"
        elif len(senha) < 4:
            erro = "A senha deve ter pelo menos 4 caracteres"
        else:
            hash_senha = generate_password_hash(senha)
            conn = conectar()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE diretores 
                SET senha = ?, precisa_trocar_senha = 0 
                WHERE id = ? AND escola_id = ?
            """, (hash_senha, diretor_id, escola_id))
            conn.commit()
            conn.close()
            registrar_log("TROCA_SENHA_DIRETOR", session.get("user"))
            return redirect("/diretor")
    
    return render_template("diretor_trocar_senha.html", erro=erro)

# ================= DIRETOR - GRÁFICO =================

@app.route("/diretor/grafico")
def diretor_grafico():
    if not is_diretor():
        return redirect("/login")
    
    escola_id = get_escola_id()
    turma_id = session.get("turma_id")
    
    if not escola_id:
        return redirect("/admin/escolas")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT ano, nome FROM turmas WHERE id = ? AND escola_id = ?", (turma_id, escola_id))
    turma = cursor.fetchone()
    turma_nome = f"{turma[0]} {turma[1]}" if turma else "Minha Turma"
    
    cursor.execute("""
        SELECT id, nome FROM disciplinas 
        WHERE turma_id = ? AND escola_id = ?
    """, (turma_id, escola_id))
    disciplinas = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM alunos WHERE turma_id = ? AND escola_id = ?", (turma_id, escola_id))
    total_alunos = cursor.fetchone()[0]
    
    dados = []
    
    for d in disciplinas:
        cursor.execute("""
            SELECT aluno_id FROM notas 
            WHERE disciplina_id = ? AND escola_id = ?
        """, (d[0], escola_id))
        alunos_notas = cursor.fetchall()
        
        medias = []
        aprovados = 0
        
        for n in alunos_notas:
            cursor.execute("""
                SELECT acs1_t1, acs2_t1, at_t1,
                       acs1_t2, acs2_t2, at_t2,
                       acs1_t3, acs2_t3, at_t3
                FROM notas 
                WHERE aluno_id = ? AND escola_id = ?
            """, (n[0], escola_id))
            
            x = cursor.fetchone()
            if x:
                t1 = calcular_trimestre(x[0], x[1], x[2])
                t2 = calcular_trimestre(x[3], x[4], x[5])
                t3 = calcular_trimestre(x[6], x[7], x[8])
                media_final = calcular_media_final(t1, t2, t3) or 0
                medias.append(media_final)
                if media_final >= 10:
                    aprovados += 1
        
        media_disciplina = round(sum(medias) / len(medias), 1) if medias else 0
        percentagem = round((aprovados / total_alunos) * 100, 1) if total_alunos > 0 else 0
        
        dados.append({
            "disciplina": d[1],
            "media": media_disciplina,
            "aprovados": aprovados,
            "total": total_alunos,
            "percentagem": percentagem
        })
    
    cursor.execute("SELECT id, ano, nome FROM turmas WHERE escola_id = ?", (escola_id,))
    turmas = cursor.fetchall()
    
    conn.close()
    
    return render_template("diretor_grafico.html",
        dados=dados,
        turma_nome=turma_nome,
        turmas=turmas,
        turma_atual=turma_id)

# ================= DIRETOR - EXAMES =================

@app.route("/diretor/exames")
def diretor_exames():
    if not is_diretor():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    turma_id = session.get("turma_id")
    ano_letivo = get_ano_letivo_atual()
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT ano, nome FROM turmas WHERE id = ? AND escola_id = ?", (turma_id, escola_id))
    turma = cursor.fetchone()
    turma_nome = f"{turma[0]}ª {turma[1]}" if turma else "Turma não encontrada"
    
    cursor.execute("""
        SELECT d.id, d.nome
        FROM disciplinas d
        JOIN disciplinas_exames de ON d.id = de.disciplina_id
        WHERE d.turma_id = ? AND de.ano_letivo = ? AND de.escola_id = ?
    """, (turma_id, ano_letivo, escola_id))
    
    disciplinas_exame = cursor.fetchall()
    
    cursor.execute("SELECT id, nome FROM alunos WHERE turma_id = ? AND escola_id = ? ORDER BY nome", (turma_id, escola_id))
    alunos = cursor.fetchall()
    
    dados = []
    for aluno in alunos:
        aluno_dados = {"nome": aluno[1], "disciplinas": []}
        
        for disc in disciplinas_exame:
            disc_id = disc[0]
            disc_nome = disc[1]
            
            cursor.execute("""
                SELECT acs1_t1, acs2_t1, at_t1,
                       acs1_t2, acs2_t2, at_t2,
                       acs1_t3, acs2_t3, at_t3
                FROM notas 
                WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
            """, (aluno[0], disc_id, escola_id))
            
            notas = cursor.fetchone()
            if notas:
                t1 = calcular_trimestre(notas[0], notas[1], notas[2])
                t2 = calcular_trimestre(notas[3], notas[4], notas[5])
                t3 = calcular_trimestre(notas[6], notas[7], notas[8])
                media_freq = calcular_media_final(t1, t2, t3) or 0
            else:
                media_freq = 0
            
            cursor.execute("""
                SELECT nota_exame FROM notas_exame
                WHERE aluno_id = ? AND disciplina_id = ? AND ano_letivo = ? AND escola_id = ?
            """, (aluno[0], disc_id, ano_letivo, escola_id))
            
            nota_exame = cursor.fetchone()
            nota_exame_valor = nota_exame[0] if nota_exame else 0
            media_final = calcular_media_com_exame(media_freq, nota_exame_valor)
            
            aluno_dados["disciplinas"].append({
                "nome": disc_nome,
                "media_frequencia": media_freq,
                "nota_exame": nota_exame_valor,
                "media_final": media_final,
                "aprovado": media_final >= 10
            })
        
        if aluno_dados["disciplinas"]:
            medias_finais = [d["media_final"] for d in aluno_dados["disciplinas"]]
            aluno_dados["media_geral"] = round(sum(medias_finais) / len(medias_finais), 1)
            aluno_dados["aprovado_geral"] = aluno_dados["media_geral"] >= 10
        else:
            aluno_dados["media_geral"] = 0
            aluno_dados["aprovado_geral"] = False
        
        dados.append(aluno_dados)
    
    conn.close()
    
    return render_template("diretor_exames.html",
        turma_nome=turma_nome,
        alunos=dados,
        disciplinas=disciplinas_exame,
        ano_letivo=ano_letivo)

# ================= PROFESSOR - TROCAR SENHA =================

@app.route("/professor/trocar-senha", methods=["GET", "POST"])
def professor_trocar_senha():
    if session.get("tipo") != "professor":
        return redirect("/login")
    
    escola_id = get_escola_id()
    erro = ""
    sucesso = ""
    
    nome_sessao = session.get("professor_nome")
    
    if request.method == "POST":
        atual = request.form.get("senha_atual")
        nova = request.form.get("nova_senha")
        conf = request.form.get("confirmar_senha")
        
        conn = conectar()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, professor_nome, professor_senha 
            FROM disciplinas 
            WHERE id = ? AND escola_id = ?
        """, (session.get("professor_id"), escola_id))
        resultado = cursor.fetchone()
        
        if not resultado:
            erro = f"Professor não encontrado!"
        else:
            prof_id, prof_nome, senha_hash = resultado
            
            if not check_password_hash(senha_hash, atual):
                senha_gerada = gerar_senha(prof_nome)
                if check_password_hash(senha_hash, senha_gerada):
                    erro = f"Use a senha gerada: {senha_gerada}"
                else:
                    erro = "Senha atual incorreta"
            elif nova != conf:
                erro = "As senhas não coincidem"
            elif len(nova) < 4:
                erro = "A senha deve ter pelo menos 4 caracteres"
            else:
                nova_hash = generate_password_hash(nova)
                cursor.execute("""
                    UPDATE disciplinas 
                    SET professor_senha = ?, precisa_trocar_senha = 0 
                    WHERE id = ? AND escola_id = ?
                """, (nova_hash, prof_id, escola_id))
                conn.commit()
                registrar_log("TROCA_SENHA_PROFESSOR", prof_nome)
                sucesso = "Senha alterada com sucesso!"
                conn.close()
                return redirect("/professor")
        
        conn.close()
    
    return render_template("trocar_senha.html", erro=erro, sucesso=sucesso)

# ================= PROFESSOR HOME =================

@app.route("/professor")
def professor_home():
    if session.get("tipo") != "professor":
        return redirect("/login")

    nome = session["professor_nome"]
    escola_id = get_escola_id()
    
    if not escola_id:
        return redirect("/admin/escolas")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT d.id, d.nome, t.ano, t.nome
        FROM disciplinas d
        JOIN turmas t ON d.turma_id = t.id
        WHERE LOWER(TRIM(d.professor_nome)) = LOWER(TRIM(?))
        AND d.escola_id = ?
    """, (nome, escola_id))

    disciplinas_raw = cursor.fetchall()
    
    disciplinas = []
    for d in disciplinas_raw:
        is_qualitativa = disciplina_eh_qualitativa(d[0], escola_id)
        disciplinas.append({
            "id": d[0],
            "nome": d[1],
            "turma_nome": f"{d[2]}ª {d[3]}",
            "qualitativa": is_qualitativa
        })
    
    conn.close()

    return render_template("professor.html", disciplinas=disciplinas)

# ================= PROFESSOR - VER DISCIPLINA =================

@app.route("/professor/disciplina/<int:disciplina_id>")
def professor_disciplina(disciplina_id):
    if not is_professor():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT nome, turma_id FROM disciplinas WHERE id = ? AND escola_id = ?", (disciplina_id, escola_id))
    disc = cursor.fetchone()
    
    if not disc:
        return "Disciplina não encontrada", 404
    
    disciplina_nome = disc[0]
    turma_id = disc[1]
    
    is_qualitativa = disciplina_eh_qualitativa(disciplina_id, escola_id)
    
    agora = int(time.time())
    cursor.execute("SELECT fim_extensao FROM periodos WHERE escola_id = ? ORDER BY id DESC LIMIT 1", (escola_id,))
    periodo = cursor.fetchone()
    bloqueado_periodo = periodo and periodo[0] < agora if periodo else True
    
    cursor.execute("SELECT id, nome FROM alunos WHERE turma_id = ? AND escola_id = ?", (turma_id, escola_id))
    alunos = cursor.fetchall()
    
    dados = []
    
    for a in alunos:
        aluno_id = a[0]
        
        cursor.execute("""
            SELECT acs1_t1, acs2_t1, at_t1,
                   acs1_t2, acs2_t2, at_t2,
                   acs1_t3, acs2_t3, at_t3,
                   notas_bloqueadas
            FROM notas
            WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
        """, (aluno_id, disciplina_id, escola_id))
        
        n = cursor.fetchone()
        
        qualitativas = {}
        if is_qualitativa:
            cursor.execute("""
                SELECT trimestre, qualidade FROM notas_qualitativas
                WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
            """, (aluno_id, disciplina_id, escola_id))
            for q in cursor.fetchall():
                qualitativas[q[0]] = q[1]
        
        if n:
            media_t1 = calcular_trimestre(n[0], n[1], n[2])
            media_t2 = calcular_trimestre(n[3], n[4], n[5])
            media_t3 = calcular_trimestre(n[6], n[7], n[8])
            media_final = calcular_media_final(media_t1, media_t2, media_t3)
            notas_bloqueadas = n[9] == 1
        else:
            n = (0,0,0,0,0,0,0,0,0,0)
            media_t1 = media_t2 = media_t3 = 0
            media_final = None
            notas_bloqueadas = False
        
        dados.append([
            aluno_id,
            a[1],
            turma_id,
            n[0], n[1], n[2],
            media_t1,
            n[3], n[4], n[5],
            media_t2,
            n[6], n[7], n[8],
            media_t3,
            media_final,
            notas_bloqueadas,
            qualitativas.get(1, ''),
            qualitativas.get(2, ''),
            qualitativas.get(3, ''),
            is_qualitativa
        ])
    
    conn.close()
    
    return render_template("index.html",
        alunos=dados,
        tipo="professor",
        disciplina_info=(disciplina_nome, turma_id),
        disciplina_id=disciplina_id,
        bloqueado=bloqueado_periodo,
        qualitativa=is_qualitativa,
        escalas=ESCALAS_QUALITATIVAS)

# ================= PROFESSOR - SALVAR NOTAS =================

@app.route("/nota/<int:aluno_id>", methods=["POST"])
def salvar_notas(aluno_id):
    if session.get("tipo") != "professor":
        return redirect("/login")
    
    disciplina_id = request.args.get("disciplina_id")
    escola_id = get_escola_id()
    
    is_qualitativa = disciplina_eh_qualitativa(disciplina_id, escola_id)
    
    trimestre_atual = get_trimestre_ativo()
    
    pode, mensagem = pode_editar_notas(disciplina_id, trimestre_atual)
    if not pode:
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: red;">⛔ Acesso Negado</h2>
            <p>{mensagem}</p>
            <a href="/professor/disciplina/{disciplina_id}"><button>Voltar</button></a>
        </div>
        """
    
    def f(v):
        try:
            val = float(v) if v and v.strip() else 0
            if val < 0 or val > 20:
                return None, f"Nota deve ser entre 0 e 20 (valor inserido: {val})"
            return val, None
        except:
            return 0, None
    
    if is_qualitativa:
        qualidade = request.form.get(f"qualidade_t{trimestre_atual}")
        if qualidade and qualidade in ['Muito Bom', 'Bom', 'Suficiente', 'Insuficiente']:
            mapa_valores = {
                'Muito Bom': 18,
                'Bom': 14,
                'Suficiente': 10,
                'Insuficiente': 5
            }
            valor = mapa_valores.get(qualidade, 0)
            acs1 = acs2 = at = valor
            qualidade_texto = qualidade
        else:
            acs1 = acs2 = at = 0
            qualidade_texto = None
    else:
        acs1, erro = f(request.form.get(f"acs1_t{trimestre_atual}"))
        if erro:
            return f"<h2 style='color:red'>❌ Erro: {erro}</h2><a href='/professor/disciplina/{disciplina_id}'>Voltar</a>"
        
        acs2, erro = f(request.form.get(f"acs2_t{trimestre_atual}"))
        if erro:
            return f"<h2 style='color:red'>❌ Erro: {erro}</h2><a href='/professor/disciplina/{disciplina_id}'>Voltar</a>"
        
        at, erro = f(request.form.get(f"at_t{trimestre_atual}"))
        if erro:
            return f"<h2 style='color:red'>❌ Erro: {erro}</h2><a href='/professor/disciplina/{disciplina_id}'>Voltar</a>"
        
        qualidade_texto = None
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT notas_bloqueadas FROM notas 
        WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
    """, (aluno_id, disciplina_id, escola_id))
    resultado = cursor.fetchone()
    
    if resultado and resultado[0] == 1:
        conn.close()
        return f"<h2 style='color:orange'>🔒 Notas Bloqueadas</h2><p>Este aluno já tem todas as notas lançadas e não pode mais ser alterado.</p><a href='/professor/disciplina/{disciplina_id}'>Voltar</a>"
    
    if trimestre_atual == 1:
        cursor.execute("""
            INSERT INTO notas (aluno_id, disciplina_id, acs1_t1, acs2_t1, at_t1, escola_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(aluno_id, disciplina_id) DO UPDATE SET 
                acs1_t1 = excluded.acs1_t1,
                acs2_t1 = excluded.acs2_t1,
                at_t1 = excluded.at_t1
        """, (aluno_id, disciplina_id, acs1, acs2, at, escola_id))
    elif trimestre_atual == 2:
        cursor.execute("""
            INSERT INTO notas (aluno_id, disciplina_id, acs1_t2, acs2_t2, at_t2, escola_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(aluno_id, disciplina_id) DO UPDATE SET 
                acs1_t2 = excluded.acs1_t2,
                acs2_t2 = excluded.acs2_t2,
                at_t2 = excluded.at_t2
        """, (aluno_id, disciplina_id, acs1, acs2, at, escola_id))
    else:
        cursor.execute("""
            INSERT INTO notas (aluno_id, disciplina_id, acs1_t3, acs2_t3, at_t3, escola_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(aluno_id, disciplina_id) DO UPDATE SET 
                acs1_t3 = excluded.acs1_t3,
                acs2_t3 = excluded.acs2_t3,
                at_t3 = excluded.at_t3
        """, (aluno_id, disciplina_id, acs1, acs2, at, escola_id))
    
    if is_qualitativa and qualidade_texto:
        cursor.execute("""
            INSERT INTO notas_qualitativas (aluno_id, disciplina_id, trimestre, qualidade, escola_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(aluno_id, disciplina_id, trimestre) DO UPDATE SET 
                qualidade = excluded.qualidade
        """, (aluno_id, disciplina_id, trimestre_atual, qualidade_texto, escola_id))
    
    cursor.execute("""
        SELECT acs1_t1, acs2_t1, at_t1,
               acs1_t2, acs2_t2, at_t2,
               acs1_t3, acs2_t3, at_t3
        FROM notas
        WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
    """, (aluno_id, disciplina_id, escola_id))
    
    notas = cursor.fetchone()
    
    if notas:
        todas_preenchidas = (
            notas[0] != 0 and notas[1] != 0 and notas[2] != 0 and
            notas[3] != 0 and notas[4] != 0 and notas[5] != 0 and
            notas[6] != 0 and notas[7] != 0 and notas[8] != 0
        )
        
        if todas_preenchidas:
            cursor.execute("""
                UPDATE notas SET notas_bloqueadas = 1
                WHERE aluno_id = ? AND disciplina_id = ? AND escola_id = ?
            """, (aluno_id, disciplina_id, escola_id))
            registrar_log("NOTAS_BLOQUEADAS", f"Aluno {aluno_id} - Disciplina {disciplina_id}")
    
    conn.commit()
    conn.close()
    
    return redirect(f"/professor/disciplina/{disciplina_id}")

# ================= PROFESSOR - EXAMES =================

@app.route("/professor/exames/<int:disciplina_id>")
def professor_exames(disciplina_id):
    if not is_professor():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    ano_letivo = get_ano_letivo_atual()
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT d.nome, d.turma_id, t.ano, t.nome
        FROM disciplinas d
        JOIN turmas t ON d.turma_id = t.id
        WHERE d.id = ? AND d.escola_id = ?
    """, (disciplina_id, escola_id))
    
    disc = cursor.fetchone()
    if not disc:
        conn.close()
        return "Disciplina não encontrada", 404
    
    disciplina_nome = disc[0]
    turma_nome = f"{disc[2]}ª {disc[3]}"
    
    tem_exame = disciplina_tem_exame(disciplina_id, disc[1], ano_letivo)
    if not tem_exame:
        conn.close()
        return f"""
        <div style="text-align: center; margin-top: 50px;">
            <h2>❌ Esta disciplina não tem exame configurado</h2>
            <a href="/professor"><button>Voltar</button></a>
        </div>
        """
    
    cursor.execute("""
        SELECT a.id, a.nome,
               n.acs1_t1, n.acs2_t1, n.at_t1,
               n.acs1_t2, n.acs2_t2, n.at_t2,
               n.acs1_t3, n.acs2_t3, n.at_t3,
               ne.nota_exame
        FROM alunos a
        JOIN notas n ON a.id = n.aluno_id
        LEFT JOIN notas_exame ne ON a.id = ne.aluno_id 
            AND ne.disciplina_id = ? AND ne.ano_letivo = ?
        WHERE a.turma_id = ? AND a.escola_id = ?
        ORDER BY a.nome
    """, (disciplina_id, ano_letivo, disc[1], escola_id))
    
    alunos = cursor.fetchall()
    conn.close()
    
    dados = []
    for aluno in alunos:
        t1 = calcular_trimestre(aluno[2], aluno[3], aluno[4])
        t2 = calcular_trimestre(aluno[5], aluno[6], aluno[7])
        t3 = calcular_trimestre(aluno[8], aluno[9], aluno[10])
        media_frequencia = calcular_media_final(t1, t2, t3) or 0
        
        nota_exame = aluno[11] if aluno[11] else 0
        media_final = calcular_media_com_exame(media_frequencia, nota_exame)
        
        dados.append({
            "id": aluno[0],
            "nome": aluno[1],
            "media_frequencia": media_frequencia,
            "nota_exame": nota_exame,
            "media_final": media_final
        })
    
    return render_template("professor_exames.html",
        disciplina_id=disciplina_id,
        disciplina_nome=disciplina_nome,
        turma_nome=turma_nome,
        alunos=dados)

@app.route("/professor/salvar-exame/<int:aluno_id>", methods=["POST"])
def salvar_nota_exame(aluno_id):
    if not is_professor():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/admin/escolas")
    
    disciplina_id = request.form.get("disciplina_id")
    nota_exame = request.form.get("nota_exame")
    ano_letivo = get_ano_letivo_atual()
    
    try:
        nota = float(nota_exame) if nota_exame else 0
        if nota < 0 or nota > 20:
            return "Nota deve ser entre 0 e 20", 400
    except:
        return "Nota inválida", 400
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO notas_exame (aluno_id, disciplina_id, nota_exame, ano_letivo, escola_id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(aluno_id, disciplina_id, ano_letivo) DO UPDATE SET 
            nota_exame = excluded.nota_exame,
            escola_id = excluded.escola_id
    """, (aluno_id, disciplina_id, nota, ano_letivo, escola_id))
    
    conn.commit()
    conn.close()
    
    registrar_log("SALVAR_NOTA_EXAME", f"Aluno {aluno_id} - Disciplina {disciplina_id}: {nota}")
    return redirect(f"/professor/exames/{disciplina_id}")

# ================= ALUNO - CONSULTAR NOTAS =================

@app.route("/aluno", methods=["GET"])
def aluno_consulta():
    return render_template("consulta.html")

@app.route("/buscar-notas", methods=["POST"])
def buscar_notas():
    nome = request.form.get("nome")
    turma_nome = request.form.get("turma")
    
    escola_id = get_escola_id()
    
    conn = conectar()
    cursor = conn.cursor()
    
    if escola_id:
        cursor.execute("""
            SELECT a.id, a.nome, t.ano, t.nome, a.senha, a.precisa_criar_senha
            FROM alunos a
            JOIN turmas t ON a.turma_id = t.id
            WHERE LOWER(TRIM(a.nome)) = LOWER(TRIM(?)) 
            AND LOWER(TRIM(t.nome)) = LOWER(TRIM(?))
            AND a.escola_id = ?
            LIMIT 1
        """, (nome, turma_nome, escola_id))
    else:
        cursor.execute("""
            SELECT a.id, a.nome, t.ano, t.nome, a.senha, a.precisa_criar_senha
            FROM alunos a
            JOIN turmas t ON a.turma_id = t.id
            WHERE LOWER(TRIM(a.nome)) = LOWER(TRIM(?)) 
            AND LOWER(TRIM(t.nome)) = LOWER(TRIM(?))
            LIMIT 1
        """, (nome, turma_nome))
    
    aluno = cursor.fetchone()
    conn.close()
    
    if not aluno:
        return render_template("consulta.html", 
            erro="❌ Aluno não encontrado. Verifique nome e turma.")
    
    aluno_id, nome_aluno, ano_turma, letra_turma, senha, precisa_criar_senha = aluno
    turma_completa = f"{ano_turma}ª {letra_turma}"
    
    # 🔥 REMOVIDA A VERIFICAÇÃO DE PAGAMENTO DE MENSALIDADE!
    # O aluno pode acessar independente do status de pagamento
    
    session["aluno_temp_id"] = aluno_id
    session["aluno_temp_nome"] = nome_aluno
    session["aluno_temp_turma"] = turma_completa
    
    if precisa_criar_senha == 1 or not senha:
        return redirect("/aluno/criar-senha")
    else:
        return redirect("/aluno/login")
        
        
# ================= ALUNO - CRIAR SENHA =================

@app.route("/aluno/criar-senha", methods=["GET", "POST"])
def aluno_criar_senha():
    erro = ""
    sucesso = ""
    
    if not session.get("aluno_temp_id"):
        return redirect("/aluno")
    
    aluno_id = session.get("aluno_temp_id")
    nome = session.get("aluno_temp_nome")
    turma = session.get("aluno_temp_turma")
    
    if request.method == "POST":
        nova_senha = request.form.get("nova_senha")
        confirmar_senha = request.form.get("confirmar_senha")
        
        if not nova_senha or len(nova_senha) < 4:
            erro = "A senha deve ter pelo menos 4 caracteres"
        elif nova_senha != confirmar_senha:
            erro = "As senhas não coincidem"
        else:
            conn = conectar()
            cursor = conn.cursor()
            
            cursor.execute("SELECT senha, precisa_criar_senha, escola_id FROM alunos WHERE id = ?", (aluno_id,))
            aluno = cursor.fetchone()
            
            if not aluno:
                conn.close()
                erro = "❌ Aluno não encontrado"
            elif aluno[0] is not None and aluno[1] == 0:
                conn.close()
                erro = "⚠️ Você já tem uma senha! Faça login."
            else:
                senha_hash = generate_password_hash(nova_senha)
                cursor.execute("""
                    UPDATE alunos 
                    SET senha = ?, precisa_criar_senha = 0 
                    WHERE id = ?
                """, (senha_hash, aluno_id))
                conn.commit()
                conn.close()
                
                registrar_log("ALUNO_CRIOU_SENHA", f"{nome} - Turma {turma}")
                sucesso = "✅ Senha criada com sucesso!"
                
                session.pop("aluno_temp_id", None)
                session.pop("aluno_temp_nome", None)
                session.pop("aluno_temp_turma", None)
    
    return render_template("aluno_criar_senha.html", 
        erro=erro, 
        sucesso=sucesso,
        nome=nome,
        turma=turma)

# ================= ALUNO - LOGIN =================

@app.route("/aluno/login", methods=["GET", "POST"])
def aluno_login():
    erro = ""
    
    if not session.get("aluno_temp_id"):
        return redirect("/aluno")
    
    nome = session.get("aluno_temp_nome")
    turma = session.get("aluno_temp_turma")
    
    if request.method == "POST":
        senha = request.form.get("senha")
        aluno_id = session.get("aluno_temp_id")
        
        if not senha:
            erro = "🔒 Digite sua senha"
        else:
            conn = conectar()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, nome, senha, precisa_criar_senha, escola_id
                FROM alunos WHERE id = ?
            """, (aluno_id,))
            aluno = cursor.fetchone()
            conn.close()
            
            if not aluno:
                erro = "❌ Aluno não encontrado"
            # 🔥 REMOVIDA A VERIFICAÇÃO DE STATUS_PAGAMENTO!
            elif aluno[3] == 1:
                erro = "⚠️ Você precisa criar uma senha primeiro!"
            elif not aluno[2]:
                erro = "⚠️ Você precisa criar uma senha primeiro!"
            elif not check_password_hash(aluno[2], senha):
                erro = "🔒 Senha incorreta!"
            else:
                session["tipo"] = "aluno"
                session["user"] = aluno[1]
                session["aluno_id"] = aluno[0]
                session["escola_id"] = aluno[4]
                
                session.pop("aluno_temp_id", None)
                session.pop("aluno_temp_nome", None)
                session.pop("aluno_temp_turma", None)
                
                # 🔥 VERIFICA SE TEM ACESSO (pagamento 5-10 MT)
                if verificar_acesso_sessao(aluno[0], 'notas'):
                    return redirect("/aluno/dashboard")
                else:
                    return redirect("/aluno/pagar-acesso/notas")
    
    return render_template("aluno_login.html", 
        nome=nome,
        turma=turma,
        erro=erro)

# ================= ALUNO - DASHBOARD =================

@app.route("/aluno/dashboard")
def aluno_dashboard():
    if session.get("tipo") != "aluno":
        return redirect("/login")
    
    aluno_id = session.get("aluno_id")
    escola_id = get_escola_id()
    
    # 🔥 VERIFICA SE TEM ACESSO (pagamento 5-10 MT)
    if not verificar_acesso_sessao(aluno_id, 'notas'):
        return redirect("/aluno/pagar-acesso/notas")
    
    conn = conectar()
    cursor = conn.cursor()
    
    # 🔥 REMOVIDO o status_pagamento da SELECT
    cursor.execute("""
        SELECT a.nome, t.ano, t.nome
        FROM alunos a
        JOIN turmas t ON a.turma_id = t.id
        WHERE a.id = ? AND a.escola_id = ?
    """, (aluno_id, escola_id))
    
    aluno = cursor.fetchone()
    
    if not aluno:
        conn.close()
        return redirect("/logout")
    
    nome_aluno, ano_turma, letra_turma = aluno
    turma_nome = f"{ano_turma}ª {letra_turma}"
    
    cursor.execute("""
        SELECT d.nome,
               n.acs1_t1, n.acs2_t1, n.at_t1,
               n.acs1_t2, n.acs2_t2, n.at_t2,
               n.acs1_t3, n.acs2_t3, n.at_t3,
               ne.nota_exame,
               (SELECT qualidade FROM notas_qualitativas 
                WHERE aluno_id = n.aluno_id AND disciplina_id = n.disciplina_id AND trimestre = 1) as qualidade_t1,
               (SELECT qualidade FROM notas_qualitativas 
                WHERE aluno_id = n.aluno_id AND disciplina_id = n.disciplina_id AND trimestre = 2) as qualidade_t2,
               (SELECT qualidade FROM notas_qualitativas 
                WHERE aluno_id = n.aluno_id AND disciplina_id = n.disciplina_id AND trimestre = 3) as qualidade_t3
        FROM notas n
        JOIN disciplinas d ON n.disciplina_id = d.id
        LEFT JOIN notas_exame ne ON n.aluno_id = ne.aluno_id 
            AND n.disciplina_id = ne.disciplina_id 
            AND ne.ano_letivo = (SELECT valor FROM config WHERE chave = 'ano_letivo_atual' AND escola_id = ?)
        WHERE n.aluno_id = ? AND n.escola_id = ?
    """, (escola_id, aluno_id, escola_id))
    
    notas = cursor.fetchall()
    conn.close()
    
    disciplinas = []
    for nota in notas:
        nome_disc = nota[0]
        acs1_t1, acs2_t1, at_t1 = nota[1] or 0, nota[2] or 0, nota[3] or 0
        acs1_t2, acs2_t2, at_t2 = nota[4] or 0, nota[5] or 0, nota[6] or 0
        acs1_t3, acs2_t3, at_t3 = nota[7] or 0, nota[8] or 0, nota[9] or 0
        nota_exame = nota[10] if nota[10] else 0
        qualidade_t1 = nota[11] if len(nota) > 11 and nota[11] else ''
        qualidade_t2 = nota[12] if len(nota) > 12 and nota[12] else ''
        qualidade_t3 = nota[13] if len(nota) > 13 and nota[13] else ''
        
        media_t1 = calcular_trimestre(acs1_t1, acs2_t1, at_t1)
        media_t2 = calcular_trimestre(acs1_t2, acs2_t2, at_t2)
        media_t3 = calcular_trimestre(acs1_t3, acs2_t3, at_t3)
        
        media_final = calcular_media_final(media_t1, media_t2, media_t3)
        if media_final is None:
            media_final = 0
        
        if nota_exame > 0 and media_final > 0:
            media_com_exame = calcular_media_com_exame(media_final, nota_exame)
        else:
            media_com_exame = media_final
        
        if media_com_exame is None:
            media_com_exame = 0
        
        is_qualitativa = qualidade_t1 or qualidade_t2 or qualidade_t3
        
        disciplinas.append({
            "nome": nome_disc,
            "acs1_t1": acs1_t1, "acs2_t1": acs2_t1, "at_t1": at_t1, 
            "media_t1": media_t1,
            "acs1_t2": acs1_t2, "acs2_t2": acs2_t2, "at_t2": at_t2, 
            "media_t2": media_t2,
            "acs1_t3": acs1_t3, "acs2_t3": acs2_t3, "at_t3": at_t3, 
            "media_t3": media_t3,
            "media_final": media_final,
            "nota_exame": nota_exame,
            "media_com_exame": media_com_exame,
            "aprovado": media_com_exame >= 10 if media_com_exame is not None else False,
            "is_qualitativa": is_qualitativa,
            "qualidade_t1": qualidade_t1,
            "qualidade_t2": qualidade_t2,
            "qualidade_t3": qualidade_t3
        })
    
    return render_template("ver_notas.html", 
        nome=nome_aluno,
        turma=turma_nome,
        disciplinas=disciplinas)

# ================= ALUNO - TROCAR SENHA =================

@app.route("/aluno/trocar-senha", methods=["GET", "POST"])
def aluno_trocar_senha():
    if session.get("tipo") != "aluno":
        return redirect("/login")
    
    aluno_id = session.get("aluno_id")
    escola_id = get_escola_id()
    erro = ""
    sucesso = ""
    
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual")
        nova_senha = request.form.get("nova_senha")
        confirmar_senha = request.form.get("confirmar_senha")
        
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT senha FROM alunos WHERE id = ? AND escola_id = ?", (aluno_id, escola_id))
        aluno = cursor.fetchone()
        
        if not aluno or not check_password_hash(aluno[0], senha_atual):
            erro = "Senha atual incorreta"
        elif nova_senha != confirmar_senha:
            erro = "As senhas não coincidem"
        elif len(nova_senha) < 4:
            erro = "A senha deve ter pelo menos 4 caracteres"
        else:
            nova_hash = generate_password_hash(nova_senha)
            cursor.execute("""
                UPDATE alunos 
                SET senha = ?, precisa_criar_senha = 0 
                WHERE id = ? AND escola_id = ?
            """, (nova_hash, aluno_id, escola_id))
            conn.commit()
            registrar_log("TROCA_SENHA_ALUNO", session.get("user"))
            sucesso = "Senha alterada com sucesso!"
            conn.close()
            return redirect("/aluno/dashboard")
        
        conn.close()
    
    return render_template("aluno_trocar_senha.html", erro=erro, sucesso=sucesso)

# ================= ERROR HANDLERS =================

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return render_template("405.html"), 405

@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500

# ================= ADMIN - QUALITATIVAS =================

@app.route("/admin/qualitativas", methods=["GET", "POST"])
def admin_qualitativas():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/login")
    
    erro = ""
    sucesso = ""
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT d.id, d.nome, t.ano, t.nome,
               CASE WHEN dq.id IS NOT NULL THEN 1 ELSE 0 END as is_qualitativa
        FROM disciplinas d
        JOIN turmas t ON d.turma_id = t.id
        LEFT JOIN disciplinas_qualitativas dq ON d.id = dq.disciplina_id AND dq.escola_id = ?
        WHERE d.escola_id = ?
        ORDER BY t.ano, t.nome, d.nome
    """, (escola_id, escola_id))
    
    disciplinas = cursor.fetchall()
    
    if request.method == "POST":
        disciplinas_qualitativas = request.form.getlist("qualitativas")
        
        cursor.execute("UPDATE disciplinas_qualitativas SET ativo = 0 WHERE escola_id = ?", (escola_id,))
        
        for disc_id in disciplinas_qualitativas:
            cursor.execute("""
                INSERT OR REPLACE INTO disciplinas_qualitativas (disciplina_id, escola_id, ativo)
                VALUES (?, ?, 1)
            """, (disc_id, escola_id))
        
        conn.commit()
        sucesso = "✅ Configurações de notas qualitativas salvas com sucesso!"
    
    conn.close()
    
    return render_template("admin_qualitativas.html", 
        disciplinas=disciplinas,
        erro=erro,
        sucesso=sucesso)

# ================= ADMIN - HISTÓRICO =================

@app.route("/admin/historico")
def admin_historico():
    if not is_admin():
        return redirect("/login")
    
    escola_id = get_escola_id()
    if not escola_id:
        return redirect("/login")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT ano_letivo, data_arquivamento 
        FROM historico_anos 
        WHERE escola_id = ?
        ORDER BY ano_letivo DESC
    """, (escola_id,))
    
    anos = cursor.fetchall()
    conn.close()
    
    return render_template("admin_historico.html", 
        anos=anos, 
        datetime=datetime)


@app.route("/super-admin/resetar-senha-admin/<int:escola_id>")
def resetar_senha_admin(escola_id):
    """Rota secreta para o Super Admin resetar a senha de uma escola"""
    if session.get("tipo") != "super_admin":
        return redirect("/super-login")
    
    # 🔥 Gera uma nova senha aleatória
    nova_senha = gerar_senha_escola()
    nova_hash = generate_password_hash(nova_senha)
    
    conn = conectar()
    cursor = conn.cursor()
    
    # Buscar o nome da escola
    cursor.execute("SELECT nome FROM escolas WHERE id = ?", (escola_id,))
    escola_nome = cursor.fetchone()
    
    if not escola_nome:
        conn.close()
        return "Escola não encontrada", 404
    
    # 🔥 ATUALIZA A SENHA DO ADMIN
    cursor.execute("""
        UPDATE config 
        SET valor = ? 
        WHERE chave = 'admin_senha' AND escola_id = ?
    """, (nova_hash, escola_id))
    
    # 🔥 FORÇA O ADMIN A TROCAR A SENHA NO PRÓXIMO LOGIN
    cursor.execute("""
        UPDATE config 
        SET valor = '1' 
        WHERE chave = 'admin_precisa_trocar' AND escola_id = ?
    """, (escola_id,))
    
    conn.commit()
    conn.close()
    
    registrar_log("RESETAR_SENHA_ADMIN", f"Escola: {escola_nome[0]} - Nova senha: {nova_senha}")
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VIRTUS - Senha Resetada</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #1a1a2e, #2d1b3d);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }}
            .container {{
                max-width: 500px;
                background: rgba(255,255,255,0.95);
                padding: 40px;
                border-radius: 20px;
                text-align: center;
                box-shadow: 0 25px 60px rgba(0,0,0,0.5);
            }}
            .icon {{
                font-size: 64px;
                margin-bottom: 15px;
                display: block;
            }}
            h1 {{
                color: #1a1a2e;
                font-size: 28px;
                margin-bottom: 10px;
            }}
            .senha {{
                font-size: 36px;
                font-weight: 900;
                color: #1a1a2e;
                background: #fef3c7;
                padding: 15px 30px;
                border-radius: 12px;
                display: inline-block;
                letter-spacing: 6px;
                border: 2px solid #f59e0b;
                font-family: 'Courier New', monospace;
                margin: 15px 0;
            }}
            .info {{
                color: #6c757d;
                font-size: 14px;
                margin: 10px 0;
            }}
            .btn {{
                display: inline-block;
                padding: 12px 30px;
                margin: 10px 5px;
                border-radius: 10px;
                text-decoration: none;
                font-weight: 700;
                transition: all 0.3s ease;
            }}
            .btn-primary {{
                background: linear-gradient(135deg, #4f46e5, #7c3aed);
                color: white;
            }}
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 10px 30px rgba(79,70,229,0.3);
            }}
            .btn-secondary {{
                background: #6c757d;
                color: white;
            }}
            .btn-secondary:hover {{
                background: #5a6268;
                transform: translateY(-2px);
            }}
            .aviso {{
                background: #fef3c7;
                padding: 15px;
                border-radius: 10px;
                margin: 15px 0;
                color: #92400e;
                font-size: 13px;
                border-left: 4px solid #f59e0b;
                text-align: left;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 15px;
                border-top: 1px solid #e2e8f0;
                color: #6c757d;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <span class="icon">🔑</span>
            <h1>Senha Resetada!</h1>
            <p style="color: #6c757d;">Escola: <strong>{{ escola_nome[0] }}</strong></p>
            
            <div class="aviso">
                ⚠️ <strong>Guarda esta senha!</strong>
                <br>
                Será pedida no próximo login do administrador.
            </div>
            
            <p style="font-weight: 600; color: #1a1a2e;">Nova senha do admin:</p>
            <div class="senha">{{ nova_senha }}</div>
            
            <p class="info">👤 Usuário: <strong>admin</strong></p>
            <p class="info" style="color: #dc2626; font-weight: 600;">
                ⚠️ O admin deve alterar esta senha no primeiro acesso!
            </p>
            
            <div>
                <a href="/super-admin" class="btn btn-secondary">← Voltar</a>
                <a href="/login" class="btn btn-primary">🔓 Fazer Login</a>
            </div>
            
            <div class="footer">
                VIRTUS © 2026 — Todos os direitos reservados
            </div>
        </div>
    </body>
    </html>
    """

# ================= INICIALIZAÇÃO =================

if __name__ == "__main__":
    app.run(debug=True)