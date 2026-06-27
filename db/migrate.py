# db/migrate.py
"""
Script de migração: parte do seu database.db original (que já tinha a
tabela "vendedores" com senha em texto puro) e:

  1. Aplica o schema novo (cria as tabelas que faltam: pets, seeds, gears,
     carrinho_itens, pedidos, pedido_itens, trades, trade_itens)
  2. Converte toda senha de vendedor que ainda esteja em texto puro
     para hash (usando werkzeug.security, que já vem com o Flask)
  3. Insere alguns itens de exemplo em pets/seeds/gears (os mesmos que já
     estavam fixos no HTML), só para a loja não começar vazia

Rode com: python db/migrate.py
Pode rodar várias vezes sem problema (é tudo idempotente).
"""

import sqlite3
import os
import sys
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# Garante que a raiz do projeto (onde está bot.py) esteja no path,
# independente de onde este script é executado (ex: "python db/migrate.py"
# vs "python migrate.py" de dentro da pasta db/).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    cur.executescript(schema)
    print("[migrate] Schema aplicado (tabelas criadas/confirmadas).")

    # --- Adiciona a coluna "vendedor_respondeu" em bancos criados antes
    # dessa coluna existir (ALTER TABLE ADD COLUMN é seguro/idempotente
    # se checarmos antes se a coluna já existe). ---
    colunas_chats = [c[1] for c in cur.execute("PRAGMA table_info(chats)").fetchall()]
    if "vendedor_respondeu" not in colunas_chats:
        cur.execute("ALTER TABLE chats ADD COLUMN vendedor_respondeu INTEGER NOT NULL DEFAULT 0")
        print("[migrate] Coluna 'vendedor_respondeu' adicionada à tabela chats.")

    # --- Adiciona a coluna "emoji" em pets/seeds/gears, em bancos criados
    # antes dessa coluna existir. ---
    for tabela in ("pets", "seeds", "gears"):
        colunas = [c[1] for c in cur.execute(f"PRAGMA table_info({tabela})").fetchall()]
        if "emoji" not in colunas:
            cur.execute(f"ALTER TABLE {tabela} ADD COLUMN emoji TEXT")
            print(f"[migrate] Coluna 'emoji' adicionada à tabela {tabela}.")

    # --- Mensagens antigas com autor_tipo limitado a 'cliente'/'vendedor'
    # continuam funcionando: o CHECK novo permite 'bot' além desses dois,
    # então não precisa migrar dados, só a definição da tabela (já coberta
    # pelo schema.sql para bancos novos; bancos antigos no SQLite não
    # reforçam CHECK retroativamente em ALTER, então nem precisa de ação aqui).

    # --- Converte senhas de vendedores que ainda estão em texto puro ---
    cur.execute("SELECT id, usuario, senha FROM vendedores")
    vendedores = cur.fetchall()

    convertidos = 0
    for vendedor_id, usuario, senha in vendedores:
        # Hash do werkzeug sempre começa com "scrypt:" ou "pbkdf2:".
        # Se a senha não tiver esse prefixo, ainda está em texto puro.
        if not (senha.startswith("scrypt:") or senha.startswith("pbkdf2:")):
            novo_hash = generate_password_hash(senha)
            cur.execute(
                "UPDATE vendedores SET senha = ? WHERE id = ?",
                (novo_hash, vendedor_id),
            )
            convertidos += 1
            print(f"[migrate] Senha de '{usuario}' convertida para hash.")

    if convertidos == 0:
        print("[migrate] Nenhuma senha em texto puro encontrada (tudo já está em hash).")

    # --- Itens de exemplo (só insere se as tabelas estiverem vazias) ---
    cur.execute("SELECT COUNT(*) FROM pets")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO pets (nome, stock, preco, imagem) VALUES (?, ?, ?, ?)",
            [
                ("Baby Dragon", 10, 120.00, "assets/pet1.png"),
                ("Forest Fox", 25, 60.00, "assets/pet2.png"),
                ("Crystal Owl", 8, 200.00, "assets/pet3.png"),
            ],
        )
        print("[migrate] Itens de exemplo inseridos em 'pets'.")

    cur.execute("SELECT COUNT(*) FROM seeds")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO seeds (nome, stock, preco, imagem) VALUES (?, ?, ?, ?)",
            [
                ("Carrot Seed", 150, 3.50, "assets/carrot.png"),
                ("Apple Seed", 80, 5.00, "assets/apple.png"),
                ("Crystal Seed", 25, 12.00, "assets/crystal.png"),
            ],
        )
        print("[migrate] Itens de exemplo inseridos em 'seeds'.")

    cur.execute("SELECT COUNT(*) FROM gears")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO gears (nome, stock, preco, imagem) VALUES (?, ?, ?, ?)",
            [
                ("Basic Gear", 120, 8.00, "assets/gear1.png"),
                ("Speed Gear", 60, 15.00, "assets/gear2.png"),
                ("Power Gear", 25, 30.00, "assets/gear3.png"),
            ],
        )
        print("[migrate] Itens de exemplo inseridos em 'gears'.")

    # --- Texto padrão da página "Sobre Nós" (só insere se ainda não existir) ---
    cur.execute("SELECT valor FROM configuracoes WHERE chave = 'sobre_nos'")
    if cur.fetchone() is None:
        texto_padrao = (
            "A MYU Store nasceu da paixão por Grow a Garden! Somos uma loja "
            "feita por fãs, para fãs, oferecendo os melhores Pets, Seeds e "
            "Gears do jogo com entrega rápida e atendimento direto pelo chat. "
            "Edite este texto pelo Painel Admin sempre que quiser."
        )
        cur.execute(
            "INSERT INTO configuracoes (chave, valor) VALUES ('sobre_nos', ?)",
            (texto_padrao,),
        )
        print("[migrate] Texto padrão de 'Sobre Nós' inserido.")

    # --- Regras padrão do bot de atendimento (só insere se a tabela estiver vazia) ---
    import bot

    cur.execute("SELECT COUNT(*) FROM bot_respostas")
    if cur.fetchone()[0] == 0:
        for i, regra in enumerate(bot.REGRAS_PADRAO):
            cur.execute(
                "INSERT INTO bot_respostas (palavra_chave, resposta, ordem) VALUES (?, ?, ?)",
                (regra["palavra_chave"], regra["resposta"], i),
            )
        print("[migrate] Regras padrão do bot de atendimento inseridas.")

    cur.execute("SELECT valor FROM configuracoes WHERE chave = 'bot_resposta_padrao'")
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO configuracoes (chave, valor) VALUES ('bot_resposta_padrao', ?)",
            (bot.RESPOSTA_PADRAO_DEFAULT,),
        )
        print("[migrate] Resposta padrão do bot inserida.")

    # --- Texto padrão da página "Dúvidas" (FAQ), editável pelo Painel Admin ---
    cur.execute("SELECT valor FROM configuracoes WHERE chave = 'duvidas_texto'")
    if cur.fetchone() is None:
        duvidas_padrao = (
            "P: Como faço para comprar um item?\n"
            "R: Acesse a página de Stock, escolha o item, clique em Comprar e finalize no carrinho.\n\n"
            "P: Como funciona o pagamento?\n"
            "R: O pagamento é combinado diretamente com o vendedor pelo chat do seu pedido.\n\n"
            "P: Posso trocar itens com outros jogadores?\n"
            "R: Sim! Acesse a página de Trades no menu para propor trocas.\n\n"
            "P: Quanto tempo demora a entrega?\n"
            "R: A entrega é combinada com o vendedor no chat, geralmente é rápida.\n\n"
            "Edite estas perguntas e respostas pelo Painel Admin sempre que quiser."
        )
        cur.execute(
            "INSERT INTO configuracoes (chave, valor) VALUES ('duvidas_texto', ?)",
            (duvidas_padrao,),
        )
        print("[migrate] Texto padrão de 'Dúvidas' inserido.")

    conn.commit()
    conn.close()
    print("[migrate] Concluído.")


if __name__ == "__main__":
    main()
