# app.py
"""
MYU Store - Backend Flask

Sistema de:
  - Login de vendedor (sessão Flask)
  - Painel admin pra editar stock de pets/seeds/gears
  - Criação de vendedor (qualquer vendedor logado pode criar outro,
    igual ao criar_vendedor.html original)
  - Carrinho de compras (guardado na sessão do visitante)
  - Trades entre jogadores (sem necessidade de login)
"""

import os
import json
import secrets
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename

from db.queries import get_db, close_db
import push
import bot

app = Flask(__name__)

# Chave de sessão: necessária pra Flask assinar o cookie de sessão.
# Em produção, defina a variável de ambiente SECRET_KEY com um valor fixo
# (senão, toda vez que reiniciar o servidor, todo mundo é deslogado).
app.secret_key = os.environ.get("SECRET_KEY", "troque-essa-chave-em-producao-" + secrets.token_hex(8))

app.teardown_appcontext(close_db)


# ------------------------------------------------------------------
# Helpers de autenticação
# ------------------------------------------------------------------

def login_obrigatorio(view_func):
    """Decorator: redireciona para /login se não houver vendedor logado na sessão."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("usuario"):
            return redirect(url_for("login", erro="login_necessario"))
        return view_func(*args, **kwargs)
    return wrapper


# ------------------------------------------------------------------
# Tema global do site (cores, fundo, transparência, fonte)
# Guardado em configuracoes(chave='tema_site') como JSON.
# Qualquer vendedor logado pode alterar (mesma regra do Sobre Nós / Bot).
# ------------------------------------------------------------------

TEMA_PADRAO = {
    "bg_image": "",
    "bg_color": "#0f0f1a",
    "primary_color": "#ff9f43",
    "secondary_color": "#2ecc71",
    "accent_color": "#4da6ff",
    "text_color": "#ffffff",
    "card_color": "#1a1a2e",
    "overlay_opacity": "0.5",
    "card_opacity": "0.9",
    "font_family": "Fredoka",
}

FONTES_DISPONIVEIS = ["Fredoka", "Poppins", "Nunito", "Montserrat", "Baloo 2", "Quicksand", "Rubik"]

THEME_UPLOAD_FOLDER = os.path.join("static", "uploads", "theme")


def get_tema(db):
    row = db.execute("SELECT valor FROM configuracoes WHERE chave = 'tema_site'").fetchone()
    tema = dict(TEMA_PADRAO)
    if row and row["valor"]:
        try:
            tema.update(json.loads(row["valor"]))
        except (ValueError, TypeError):
            pass
    return tema


@app.context_processor
def injetar_tema():
    """Deixa a variável 'tema' disponível em TODOS os templates automaticamente."""
    db = get_db()
    return {"tema": get_tema(db), "fontes_disponiveis": FONTES_DISPONIVEIS}


def get_or_create_cart_session_id():
    """
    O carrinho não exige login. Usamos um ID aleatório guardado na sessão
    do Flask (cookie) pra saber quais itens pertencem a qual visitante.
    """
    if "carrinho_session_id" not in session:
        session["carrinho_session_id"] = secrets.token_hex(16)
    return session["carrinho_session_id"]


def bot_ja_respondeu_isso(db, tabela_mensagens, coluna_fk, valor_fk, texto):
    """
    Verifica se o bot já mandou esse EXATO texto antes, nessa mesma sala
    de chat/conversa de suporte. Usado pra evitar que o bot fique repetindo
    a mesma resposta várias vezes quando o cliente escreve mensagens
    parecidas (ex: manda "preço" de novo, ou insiste na mesma dúvida) — a
    resposta já está visível mais acima na conversa, então não precisa
    repetir.
    """
    existente = db.execute(
        f"SELECT id FROM {tabela_mensagens} "
        f"WHERE {coluna_fk} = ? AND autor_tipo = 'bot' AND mensagem = ? LIMIT 1",
        (valor_fk, texto),
    ).fetchone()
    return existente is not None


# ------------------------------------------------------------------
# Páginas públicas
# ------------------------------------------------------------------

@app.route("/")
@app.route("/index")
def index():
    db = get_db()
    ofertas = buscar_ofertas_do_dia(db)
    return render_template("Index.html", ofertas=ofertas)


@app.route("/pets")
@app.route("/PETS_STOCK.html")
def pets_stock():
    db = get_db()
    pets = db.execute("SELECT * FROM pets ORDER BY id DESC").fetchall()
    return render_template("PETS_STOCK.html", pets=pets)


@app.route("/seeds")
@app.route("/SEEDS_STOCK.html")
def seeds_stock():
    db = get_db()
    seeds = db.execute("SELECT * FROM seeds ORDER BY id DESC").fetchall()
    return render_template("SEEDS_STOCK.html", seeds=seeds)


@app.route("/gears")
@app.route("/GEARS_STOCK.html")
def gears_stock():
    db = get_db()
    gears = db.execute("SELECT * FROM gears ORDER BY id DESC").fetchall()
    return render_template("GEARS_STOCK.html", gears=gears)


@app.route("/stock")
def stock_unificado():
    """
    Página única de Stock, juntando Pets, Seeds e Gears em abas.
    As rotas /pets, /seeds, /gears continuam existindo separadamente
    (por compatibilidade), mas o menu agora aponta só pra esta página.
    """
    db = get_db()
    pets = db.execute("SELECT * FROM pets ORDER BY id DESC").fetchall()
    seeds = db.execute("SELECT * FROM seeds ORDER BY id DESC").fetchall()
    gears = db.execute("SELECT * FROM gears ORDER BY id DESC").fetchall()
    return render_template("Stock.html", pets=pets, seeds=seeds, gears=gears)


@app.route("/sobre-nos")
def sobre_nos():
    db = get_db()
    config = db.execute("SELECT valor FROM configuracoes WHERE chave = 'sobre_nos'").fetchone()
    texto = config["valor"] if config else ""
    return render_template("SobreNos.html", texto=texto)


@app.route("/avaliacoes")
def avaliacoes_lista():
    db = get_db()
    avaliacoes = db.execute(
        "SELECT * FROM avaliacoes ORDER BY criado_em DESC LIMIT 50"
    ).fetchall()

    media = db.execute("SELECT AVG(nota) AS media, COUNT(*) AS total FROM avaliacoes").fetchone()
    media_nota = round(media["media"], 1) if media["media"] else 0
    total_avaliacoes = media["total"]

    return render_template(
        "Avaliacoes.html", avaliacoes=avaliacoes, media_nota=media_nota, total_avaliacoes=total_avaliacoes
    )


@app.route("/chat/<int:pedido_id>/avaliar", methods=["POST"])
def avaliar_pedido(pedido_id):
    db = get_db()

    pedido = db.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if not pedido:
        flash("Pedido não encontrado.")
        return redirect(url_for("index"))

    # Só quem fez o pedido (mesma sessão do carrinho) pode avaliar — vendedor não.
    eh_dono_do_pedido = session.get("carrinho_session_id") == pedido["session_id"]
    if not eh_dono_do_pedido:
        flash("Só quem fez este pedido pode avaliá-lo.")
        return redirect(url_for("chat_pedido", pedido_id=pedido_id))

    # A opção de avaliar só existe depois que o vendedor libera, normalmente
    # após finalizar o atendimento/entrega combinada no chat.
    chat = db.execute("SELECT * FROM chats WHERE pedido_id = ?", (pedido_id,)).fetchone()
    if not chat or not chat["avaliacao_liberada"]:
        flash("A avaliação deste pedido ainda não foi liberada pelo vendedor.")
        return redirect(url_for("chat_pedido", pedido_id=pedido_id))

    existente = db.execute("SELECT id FROM avaliacoes WHERE pedido_id = ?", (pedido_id,)).fetchone()
    if existente:
        flash("Este pedido já foi avaliado.")
        return redirect(url_for("chat_pedido", pedido_id=pedido_id))

    try:
        nota = int(request.form.get("nota", "0"))
    except ValueError:
        nota = 0

    comentario = request.form.get("comentario", "").strip()

    if nota < 1 or nota > 5:
        flash("Escolha uma nota de 1 a 5 estrelas.")
        return redirect(url_for("chat_pedido", pedido_id=pedido_id))

    if len(comentario) > 1000:
        flash("Comentário muito longo (máximo 1000 caracteres).")
        return redirect(url_for("chat_pedido", pedido_id=pedido_id))

    db.execute(
        "INSERT INTO avaliacoes (pedido_id, nota, comentario) VALUES (?, ?, ?)",
        (pedido_id, nota, comentario or None),
    )
    db.commit()

    flash("Obrigado pela sua avaliação! ⭐")
    return redirect(url_for("chat_pedido", pedido_id=pedido_id))


@app.route("/chat/<int:pedido_id>/liberar-avaliacao", methods=["POST"])
@login_obrigatorio
def liberar_avaliacao(pedido_id):
    """
    O vendedor libera a opção de avaliação para o cliente — pensado pra ser
    usado depois que o atendimento no chat termina e a compra já foi
    finalizada/entregue. Uma vez liberada, fica liberada pra sempre (não dá
    pra "desliberar"), e a avaliação em si, depois de enviada pelo cliente,
    é permanente (fica salva no banco e não existe rota de exclusão/edição).
    """
    db = get_db()

    pedido = db.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if not pedido:
        flash("Pedido não encontrado.")
        return redirect(url_for("painel_adm"))

    chat = db.execute("SELECT * FROM chats WHERE pedido_id = ?", (pedido_id,)).fetchone()
    if not chat:
        cur = db.execute("INSERT INTO chats (pedido_id) VALUES (?)", (pedido_id,))
        db.commit()
        chat = db.execute("SELECT * FROM chats WHERE id = ?", (cur.lastrowid,)).fetchone()

    if chat["avaliacao_liberada"]:
        flash("A avaliação deste pedido já estava liberada.")
    else:
        db.execute("UPDATE chats SET avaliacao_liberada = 1 WHERE id = ?", (chat["id"],))
        db.commit()
        flash("Avaliação liberada! O cliente já pode avaliar este pedido.")

    return redirect(url_for("chat_pedido", pedido_id=pedido_id))


@app.route("/duvidas")
def duvidas():
    db = get_db()
    config = db.execute("SELECT valor FROM configuracoes WHERE chave = 'duvidas_texto'").fetchone()
    texto = config["valor"] if config else ""
    return render_template("Duvidas.html", texto=texto)


@app.route("/update_duvidas", methods=["POST"])
@login_obrigatorio
def update_duvidas():
    db = get_db()
    texto = request.form.get("texto", "").strip()

    if not texto:
        flash("O texto de Dúvidas não pode ficar vazio.")
        return redirect(url_for("painel_adm"))

    if len(texto) > 8000:
        flash("Texto muito longo (máximo 8000 caracteres).")
        return redirect(url_for("painel_adm"))

    db.execute(
        "INSERT INTO configuracoes (chave, valor) VALUES ('duvidas_texto', ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (texto,),
    )
    db.commit()
    flash("Texto de 'Dúvidas' atualizado!")
    return redirect(url_for("painel_adm"))


# ------------------------------------------------------------------
# Suporte (chat geral com o bot, sem precisar de pedido nem login)
# ------------------------------------------------------------------

def get_or_create_suporte_conversa(db, session_id):
    """Busca a conversa de suporte da sessão atual, ou cria uma nova."""
    conversa = db.execute(
        "SELECT * FROM suporte_conversas WHERE session_id = ?", (session_id,)
    ).fetchone()

    if not conversa:
        cur = db.execute(
            "INSERT INTO suporte_conversas (session_id) VALUES (?)", (session_id,)
        )
        db.commit()
        conversa = db.execute(
            "SELECT * FROM suporte_conversas WHERE id = ?", (cur.lastrowid,)
        ).fetchone()

    return conversa


@app.route("/suporte")
def suporte():
    db = get_db()
    session_id = get_or_create_cart_session_id()
    conversa = get_or_create_suporte_conversa(db, session_id)

    autor_tipo_atual = "vendedor" if session.get("usuario") else "cliente"
    autor_nome_atual = session.get("usuario") if session.get("usuario") else get_or_create_cliente_nome()

    return render_template(
        "Suporte.html",
        conversa_id=conversa["id"],
        autor_tipo_atual=autor_tipo_atual,
        autor_nome_atual=autor_nome_atual,
    )


@app.route("/suporte/<int:conversa_id>/mensagens", methods=["GET"])
def suporte_listar_mensagens(conversa_id):
    db = get_db()
    desde = request.args.get("desde", 0, type=int)

    mensagens = db.execute(
        "SELECT * FROM suporte_mensagens WHERE conversa_id = ? AND id > ? ORDER BY id ASC",
        (conversa_id, desde),
    ).fetchall()

    return jsonify({
        "mensagens": [
            {
                "id": m["id"],
                "autor_tipo": m["autor_tipo"],
                "autor_nome": m["autor_nome"],
                "mensagem": m["mensagem"],
                "criado_em": m["criado_em"],
            }
            for m in mensagens
        ]
    })


@app.route("/suporte/<int:conversa_id>/enviar", methods=["POST"])
def suporte_enviar_mensagem(conversa_id):
    db = get_db()

    conversa = db.execute("SELECT * FROM suporte_conversas WHERE id = ?", (conversa_id,)).fetchone()
    if not conversa:
        return jsonify({"erro": "Conversa não encontrada."}), 404

    eh_vendedor = bool(session.get("usuario"))
    eh_dono_da_conversa = session.get("carrinho_session_id") == conversa["session_id"]

    if not eh_vendedor and not eh_dono_da_conversa:
        return jsonify({"erro": "Sem acesso a esta conversa."}), 403

    mensagem = request.form.get("mensagem", "").strip()
    if not mensagem:
        return jsonify({"erro": "Mensagem vazia."}), 400
    if len(mensagem) > 1000:
        return jsonify({"erro": "Mensagem muito longa (máximo 1000 caracteres)."}), 400

    autor_tipo = "vendedor" if eh_vendedor else "cliente"
    autor_nome = session.get("usuario") if eh_vendedor else get_or_create_cliente_nome()

    cur = db.execute(
        "INSERT INTO suporte_mensagens (conversa_id, autor_tipo, autor_nome, mensagem) VALUES (?, ?, ?, ?)",
        (conversa_id, autor_tipo, autor_nome, mensagem),
    )

    vendedor_respondeu = bool(conversa["vendedor_respondeu"])
    if eh_vendedor and not vendedor_respondeu:
        db.execute("UPDATE suporte_conversas SET vendedor_respondeu = 1 WHERE id = ?", (conversa_id,))
        vendedor_respondeu = True

    db.commit()

    nova = db.execute("SELECT * FROM suporte_mensagens WHERE id = ?", (cur.lastrowid,)).fetchone()
    mensagem_resposta = {
        "id": nova["id"],
        "autor_tipo": nova["autor_tipo"],
        "autor_nome": nova["autor_nome"],
        "mensagem": nova["mensagem"],
        "criado_em": nova["criado_em"],
    }

    resposta_bot = None
    if not eh_vendedor and not vendedor_respondeu:
        regras = db.execute(
            "SELECT palavra_chave, resposta FROM bot_respostas ORDER BY ordem ASC"
        ).fetchall()
        regras_dicts = [dict(r) for r in regras]

        config_padrao = db.execute(
            "SELECT valor FROM configuracoes WHERE chave = 'bot_resposta_padrao'"
        ).fetchone()
        resposta_padrao = config_padrao["valor"] if config_padrao else bot.RESPOSTA_PADRAO_DEFAULT

        texto_bot = bot.gerar_resposta(mensagem, regras_dicts, resposta_padrao)

        if not bot_ja_respondeu_isso(db, "suporte_mensagens", "conversa_id", conversa_id, texto_bot):
            cur_bot = db.execute(
                "INSERT INTO suporte_mensagens (conversa_id, autor_tipo, autor_nome, mensagem) VALUES (?, 'bot', 'Assistente MYU', ?)",
                (conversa_id, texto_bot),
            )
            db.commit()
            nova_bot = db.execute("SELECT * FROM suporte_mensagens WHERE id = ?", (cur_bot.lastrowid,)).fetchone()
            resposta_bot = {
                "id": nova_bot["id"],
                "autor_tipo": nova_bot["autor_tipo"],
                "autor_nome": nova_bot["autor_nome"],
                "mensagem": nova_bot["mensagem"],
                "criado_em": nova_bot["criado_em"],
            }

    resultado = {"mensagem": mensagem_resposta}
    if resposta_bot:
        resultado["resposta_bot"] = resposta_bot

    return jsonify(resultado)


@app.route("/suporte/conversas")
@login_obrigatorio
def suporte_lista_conversas():
    """Painel admin: lista todas as conversas de suporte, mais recentes primeiro."""
    db = get_db()
    conversas = db.execute(
        "SELECT * FROM suporte_conversas ORDER BY criado_em DESC LIMIT 30"
    ).fetchall()

    resultado = []
    for c in conversas:
        ultima_msg = db.execute(
            "SELECT * FROM suporte_mensagens WHERE conversa_id = ? ORDER BY id DESC LIMIT 1",
            (c["id"],),
        ).fetchone()
        resultado.append({"conversa": c, "ultima_mensagem": ultima_msg})

    return render_template("SuporteConversas.html", conversas=resultado)


@app.route("/suporte/admin/<int:conversa_id>")
@login_obrigatorio
def suporte_admin_chat(conversa_id):
    """Painel admin: abre uma conversa de suporte específica para responder."""
    db = get_db()
    conversa = db.execute("SELECT * FROM suporte_conversas WHERE id = ?", (conversa_id,)).fetchone()
    if not conversa:
        flash("Conversa não encontrada.")
        return redirect(url_for("suporte_lista_conversas"))

    return render_template(
        "Suporte.html",
        conversa_id=conversa["id"],
        autor_tipo_atual="vendedor",
        autor_nome_atual=session.get("usuario"),
        eh_painel_admin=True,
    )


def buscar_ofertas_do_dia(db):
    """
    Busca todas as ofertas do dia, já trazendo os dados do item original
    (nome, imagem, emoji, stock) de pets/seeds/gears, na ordem definida.
    Como não há JOIN possível entre tabelas diferentes por categoria,
    fazemos uma consulta por categoria e juntamos em Python.
    """
    ofertas_raw = db.execute("SELECT * FROM ofertas_do_dia ORDER BY ordem ASC").fetchall()

    resultado = []
    for oferta in ofertas_raw:
        item = db.execute(
            f"SELECT * FROM {oferta['categoria']} WHERE id = ?", (oferta["item_id"],)
        ).fetchone()
        if not item:
            continue  # item foi excluído mas a oferta não foi limpa (segurança extra)
        resultado.append({
            "oferta_id": oferta["id"],
            "categoria": oferta["categoria"],
            "item_id": item["id"],
            "nome": item["nome"],
            "imagem": item["imagem"],
            "emoji": item["emoji"],
            "stock": item["stock"],
            "preco_original": item["preco"],
            "preco_promocional": oferta["preco_promocional"],
        })
    return resultado


@app.route("/ofertas", methods=["POST"])
@login_obrigatorio
def ofertas_criar():
    db = get_db()
    categoria = request.form.get("categoria", "").strip()
    item_id = request.form.get("item_id", "")
    preco_promocional = request.form.get("preco_promocional", "")

    if categoria not in ("pets", "seeds", "gears"):
        flash("Categoria inválida.")
        return redirect(url_for("painel_adm"))

    try:
        item_id = int(item_id)
        preco_promocional = float(preco_promocional)
    except ValueError:
        flash("Item ou preço promocional inválido.")
        return redirect(url_for("painel_adm"))

    if preco_promocional < 0:
        flash("Preço promocional não pode ser negativo.")
        return redirect(url_for("painel_adm"))

    item = db.execute(f"SELECT id FROM {categoria} WHERE id = ?", (item_id,)).fetchone()
    if not item:
        flash("Item não encontrado.")
        return redirect(url_for("painel_adm"))

    existente = db.execute(
        "SELECT id FROM ofertas_do_dia WHERE categoria = ? AND item_id = ?", (categoria, item_id)
    ).fetchone()

    if existente:
        db.execute(
            "UPDATE ofertas_do_dia SET preco_promocional = ? WHERE id = ?",
            (preco_promocional, existente["id"]),
        )
        flash("Oferta atualizada.")
    else:
        maior_ordem = db.execute("SELECT COALESCE(MAX(ordem), -1) AS m FROM ofertas_do_dia").fetchone()["m"]
        db.execute(
            "INSERT INTO ofertas_do_dia (categoria, item_id, preco_promocional, ordem) VALUES (?, ?, ?, ?)",
            (categoria, item_id, preco_promocional, maior_ordem + 1),
        )
        flash("Oferta do dia adicionada!")

    db.commit()
    return redirect(url_for("painel_adm"))


@app.route("/ofertas/<int:oferta_id>/excluir", methods=["POST"])
@login_obrigatorio
def ofertas_excluir(oferta_id):
    db = get_db()
    db.execute("DELETE FROM ofertas_do_dia WHERE id = ?", (oferta_id,))
    db.commit()
    flash("Oferta do dia removida.")
    return redirect(url_for("painel_adm"))


# ------------------------------------------------------------------
# Carrinho
# ------------------------------------------------------------------

@app.route("/carrinho")
@app.route("/Carrinho.html")
def carrinho():
    db = get_db()
    session_id = get_or_create_cart_session_id()

    itens_raw = db.execute(
        "SELECT * FROM carrinho_itens WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()

    itens = []
    total = 0.0
    for item in itens_raw:
        tabela = item["categoria"]  # 'pets' | 'seeds' | 'gears'
        produto = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (item["item_id"],)).fetchone()
        if not produto:
            continue
        subtotal = produto["preco"] * item["quantidade"]
        total += subtotal
        itens.append({
            "carrinho_item_id": item["id"],
            "nome": produto["nome"],
            "imagem": produto["imagem"],
            "preco": produto["preco"],
            "quantidade": item["quantidade"],
            "subtotal": subtotal,
            "categoria": tabela,
        })

    return render_template("Carrinho.html", itens=itens, total=total, quantidade_itens=len(itens))


@app.route("/carrinho/adicionar", methods=["POST"])
def carrinho_adicionar():
    db = get_db()
    session_id = get_or_create_cart_session_id()

    categoria = request.form.get("categoria")
    item_id = request.form.get("item_id")
    quantidade = request.form.get("quantidade", "1")

    if categoria not in ("pets", "seeds", "gears"):
        flash("Categoria inválida.")
        return redirect(request.referrer or url_for("index"))

    try:
        item_id = int(item_id)
        quantidade = max(1, int(quantidade))
    except (TypeError, ValueError):
        flash("Item ou quantidade inválida.")
        return redirect(request.referrer or url_for("index"))

    produto = db.execute(f"SELECT * FROM {categoria} WHERE id = ?", (item_id,)).fetchone()
    if not produto:
        flash("Item não encontrado.")
        return redirect(request.referrer or url_for("index"))

    # Se já existe esse item no carrinho dessa sessão, só soma a quantidade
    existente = db.execute(
        "SELECT * FROM carrinho_itens WHERE session_id = ? AND categoria = ? AND item_id = ?",
        (session_id, categoria, item_id),
    ).fetchone()

    if existente:
        db.execute(
            "UPDATE carrinho_itens SET quantidade = quantidade + ? WHERE id = ?",
            (quantidade, existente["id"]),
        )
    else:
        db.execute(
            "INSERT INTO carrinho_itens (session_id, categoria, item_id, quantidade) VALUES (?, ?, ?, ?)",
            (session_id, categoria, item_id, quantidade),
        )

    db.commit()
    flash(f'"{produto["nome"]}" adicionado ao carrinho!')
    return redirect(request.referrer or url_for("carrinho"))


@app.route("/carrinho/remover/<int:carrinho_item_id>", methods=["POST"])
def carrinho_remover(carrinho_item_id):
    db = get_db()
    session_id = get_or_create_cart_session_id()

    # Só permite remover item que pertence à própria sessão (evita um
    # visitante remover item do carrinho de outro só adivinhando o ID)
    db.execute(
        "DELETE FROM carrinho_itens WHERE id = ? AND session_id = ?",
        (carrinho_item_id, session_id),
    )
    db.commit()
    return redirect(url_for("carrinho"))


@app.route("/carrinho/finalizar", methods=["POST"])
def carrinho_finalizar():
    db = get_db()
    session_id = get_or_create_cart_session_id()

    itens_raw = db.execute(
        "SELECT * FROM carrinho_itens WHERE session_id = ?",
        (session_id,),
    ).fetchall()

    if not itens_raw:
        flash("Seu carrinho está vazio.")
        return redirect(url_for("carrinho"))

    total = 0.0
    pedido_itens = []
    for item in itens_raw:
        tabela = item["categoria"]
        produto = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (item["item_id"],)).fetchone()
        if not produto:
            continue
        if produto["stock"] < item["quantidade"]:
            flash(f'Estoque insuficiente para "{produto["nome"]}".')
            return redirect(url_for("carrinho"))
        subtotal = produto["preco"] * item["quantidade"]
        total += subtotal
        pedido_itens.append((tabela, produto["nome"], produto["preco"], item["quantidade"], produto["id"]))

    # Cria o pedido, debita o stock e limpa o carrinho — tudo em uma transação
    cur = db.execute("INSERT INTO pedidos (session_id, total) VALUES (?, ?)", (session_id, total))
    pedido_id = cur.lastrowid

    for tabela, nome, preco, quantidade, produto_id in pedido_itens:
        db.execute(
            "INSERT INTO pedido_itens (pedido_id, categoria, nome, preco, quantidade) VALUES (?, ?, ?, ?, ?)",
            (pedido_id, tabela, nome, preco, quantidade),
        )
        db.execute(f"UPDATE {tabela} SET stock = stock - ? WHERE id = ?", (quantidade, produto_id))

    db.execute("DELETE FROM carrinho_itens WHERE session_id = ?", (session_id,))

    # Cria a sala de chat vinculada a este pedido — todos os vendedores e o
    # cliente caem na mesma sala.
    cur = db.execute("INSERT INTO chats (pedido_id) VALUES (?)", (pedido_id,))
    chat_id = cur.lastrowid

    db.commit()

    # Dispara notificação push para todos os vendedores com token registrado.
    # Se o Firebase não estiver configurado (rodando local, sem HTTPS), essa
    # chamada simplesmente não faz nada — não trava o checkout.
    tokens_rows = db.execute("SELECT token FROM vendedor_push_tokens").fetchall()
    tokens = [r["token"] for r in tokens_rows]
    push.enviar_notificacao_pedido(tokens, pedido_id, total)

    flash(f"Pedido #{pedido_id} finalizado com sucesso! Total: R$ {total:.2f}")
    return redirect(url_for("chat_pedido", pedido_id=pedido_id))


# ------------------------------------------------------------------
# Chat por pedido (cliente + todos os vendedores numa sala só)
# ------------------------------------------------------------------

def get_or_create_cliente_nome():
    """
    O cliente não faz login, então usamos um nome guardado na sessão
    (cookie) pra identificar as mensagens dele no chat. Se ainda não
    tiver nome definido, usa um genérico baseado no id da sessão.
    """
    if "cliente_nome" not in session:
        session["cliente_nome"] = "Cliente"
    return session["cliente_nome"]


@app.route("/chat/<int:pedido_id>")
def chat_pedido(pedido_id):
    db = get_db()

    pedido = db.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if not pedido:
        flash("Pedido não encontrado.")
        return redirect(url_for("index"))

    chat = db.execute("SELECT * FROM chats WHERE pedido_id = ?", (pedido_id,)).fetchone()
    if not chat:
        # Pedidos antigos (criados antes dessa funcionalidade existir) não têm chat.
        # Criamos um na hora pra não travar o acesso.
        cur = db.execute("INSERT INTO chats (pedido_id) VALUES (?)", (pedido_id,))
        db.commit()
        chat = db.execute("SELECT * FROM chats WHERE id = ?", (cur.lastrowid,)).fetchone()

    itens = db.execute("SELECT * FROM pedido_itens WHERE pedido_id = ?", (pedido_id,)).fetchall()

    # Só permite acesso de cliente se for a mesma sessão que fez o pedido,
    # ou se for um vendedor logado (vendedores veem todos os chats).
    eh_vendedor = bool(session.get("usuario"))
    eh_dono_do_pedido = session.get("carrinho_session_id") == pedido["session_id"]

    if not eh_vendedor and not eh_dono_do_pedido:
        flash("Você não tem acesso a este chat.")
        return redirect(url_for("index"))

    autor_tipo_atual = "vendedor" if eh_vendedor else "cliente"
    autor_nome_atual = session.get("usuario") if eh_vendedor else get_or_create_cliente_nome()

    avaliacao = db.execute("SELECT * FROM avaliacoes WHERE pedido_id = ?", (pedido_id,)).fetchone()

    return render_template(
        "chat.html",
        pedido=pedido,
        itens=itens,
        chat_id=chat["id"],
        autor_tipo_atual=autor_tipo_atual,
        autor_nome_atual=autor_nome_atual,
        eh_dono_do_pedido=eh_dono_do_pedido,
        eh_vendedor=eh_vendedor,
        avaliacao=avaliacao,
        avaliacao_liberada=bool(chat["avaliacao_liberada"]),
    )


@app.route("/chat/<int:pedido_id>/mensagens", methods=["GET"])
def chat_listar_mensagens(pedido_id):
    """
    Endpoint JSON consultado periodicamente pelo navegador (polling) pra
    buscar mensagens novas sem precisar recarregar a página inteira.
    Aceita ?desde=<id> pra retornar só mensagens com id maior que esse.
    """
    db = get_db()

    chat = db.execute("SELECT * FROM chats WHERE pedido_id = ?", (pedido_id,)).fetchone()
    if not chat:
        return jsonify({"mensagens": []})

    desde = request.args.get("desde", 0, type=int)

    mensagens = db.execute(
        "SELECT * FROM chat_mensagens WHERE chat_id = ? AND id > ? ORDER BY id ASC",
        (chat["id"], desde),
    ).fetchall()

    return jsonify({
        "mensagens": [
            {
                "id": m["id"],
                "autor_tipo": m["autor_tipo"],
                "autor_nome": m["autor_nome"],
                "mensagem": m["mensagem"],
                "criado_em": m["criado_em"],
            }
            for m in mensagens
        ]
    })


@app.route("/chat/<int:pedido_id>/enviar", methods=["POST"])
def chat_enviar_mensagem(pedido_id):
    db = get_db()

    pedido = db.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if not pedido:
        return jsonify({"erro": "Pedido não encontrado."}), 404

    chat = db.execute("SELECT * FROM chats WHERE pedido_id = ?", (pedido_id,)).fetchone()
    if not chat:
        cur = db.execute("INSERT INTO chats (pedido_id) VALUES (?)", (pedido_id,))
        db.commit()
        chat_id = cur.lastrowid
        vendedor_respondeu = False
    else:
        chat_id = chat["id"]
        vendedor_respondeu = bool(chat["vendedor_respondeu"])

    eh_vendedor = bool(session.get("usuario"))
    eh_dono_do_pedido = session.get("carrinho_session_id") == pedido["session_id"]

    if not eh_vendedor and not eh_dono_do_pedido:
        return jsonify({"erro": "Sem acesso a este chat."}), 403

    mensagem = request.form.get("mensagem", "").strip()
    if not mensagem:
        return jsonify({"erro": "Mensagem vazia."}), 400
    if len(mensagem) > 1000:
        return jsonify({"erro": "Mensagem muito longa (máximo 1000 caracteres)."}), 400

    autor_tipo = "vendedor" if eh_vendedor else "cliente"
    autor_nome = session.get("usuario") if eh_vendedor else get_or_create_cliente_nome()

    cur = db.execute(
        "INSERT INTO chat_mensagens (chat_id, autor_tipo, autor_nome, mensagem) VALUES (?, ?, ?, ?)",
        (chat_id, autor_tipo, autor_nome, mensagem),
    )

    # Assim que um vendedor humano escreve, o bot para de responder
    # naquela sala pra sempre (mesmo que o vendedor não escreva de novo).
    if eh_vendedor and not vendedor_respondeu:
        db.execute("UPDATE chats SET vendedor_respondeu = 1 WHERE id = ?", (chat_id,))
        vendedor_respondeu = True

    db.commit()

    nova = db.execute("SELECT * FROM chat_mensagens WHERE id = ?", (cur.lastrowid,)).fetchone()
    mensagem_resposta = {
        "id": nova["id"],
        "autor_tipo": nova["autor_tipo"],
        "autor_nome": nova["autor_nome"],
        "mensagem": nova["mensagem"],
        "criado_em": nova["criado_em"],
    }

    # Se foi o cliente que escreveu e nenhum vendedor respondeu ainda,
    # o bot responde na mesma chamada (assim a resposta aparece rápido
    # pro cliente, sem precisar esperar o próximo polling). Esse bot é
    # baseado em palavras-chave (sem dependência externa), então sempre
    # tem uma resposta disponível.
    resposta_bot = None
    if not eh_vendedor and not vendedor_respondeu:
        regras = db.execute(
            "SELECT palavra_chave, resposta FROM bot_respostas ORDER BY ordem ASC"
        ).fetchall()
        regras_dicts = [dict(r) for r in regras]

        config_padrao = db.execute(
            "SELECT valor FROM configuracoes WHERE chave = 'bot_resposta_padrao'"
        ).fetchone()
        resposta_padrao = config_padrao["valor"] if config_padrao else bot.RESPOSTA_PADRAO_DEFAULT

        texto_bot = bot.gerar_resposta(mensagem, regras_dicts, resposta_padrao)

        if not bot_ja_respondeu_isso(db, "chat_mensagens", "chat_id", chat_id, texto_bot):
            cur_bot = db.execute(
                "INSERT INTO chat_mensagens (chat_id, autor_tipo, autor_nome, mensagem) VALUES (?, 'bot', 'Assistente MYU', ?)",
                (chat_id, texto_bot),
            )
            db.commit()
            nova_bot = db.execute("SELECT * FROM chat_mensagens WHERE id = ?", (cur_bot.lastrowid,)).fetchone()
            resposta_bot = {
                "id": nova_bot["id"],
                "autor_tipo": nova_bot["autor_tipo"],
                "autor_nome": nova_bot["autor_nome"],
                "mensagem": nova_bot["mensagem"],
                "criado_em": nova_bot["criado_em"],
            }

    resultado = {"mensagem": mensagem_resposta}
    if resposta_bot:
        resultado["resposta_bot"] = resposta_bot

    return jsonify(resultado)


# ------------------------------------------------------------------
# Notificações push (Firebase Cloud Messaging)
# ------------------------------------------------------------------

@app.route("/firebase-messaging-sw.js")
def firebase_service_worker():
    """
    Serve o Service Worker do Firebase a partir da RAIZ do site
    (https://seusite.com/firebase-messaging-sw.js), exigência do navegador
    para que o Service Worker tenha permissão de receber push de todo o domínio.
    """
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "firebase-messaging-sw.js",
        mimetype="application/javascript",
    )


@app.route("/push/registrar", methods=["POST"])
@login_obrigatorio
def push_registrar_token():
    """
    Chamado pelo JS do navegador do vendedor depois que ele autoriza
    notificações e o Firebase gera um token pra esse dispositivo.
    """
    db = get_db()
    token = request.json.get("token") if request.is_json else request.form.get("token")

    if not token:
        return jsonify({"erro": "Token ausente."}), 400

    # Evita duplicar o mesmo token; se já existe (de outro vendedor por
    # engano, ou re-registro), apenas garante que está ligado ao vendedor atual.
    existente = db.execute("SELECT id FROM vendedor_push_tokens WHERE token = ?", (token,)).fetchone()
    if existente:
        db.execute(
            "UPDATE vendedor_push_tokens SET vendedor_id = ? WHERE id = ?",
            (session["vendedor_id"], existente["id"]),
        )
    else:
        db.execute(
            "INSERT INTO vendedor_push_tokens (vendedor_id, token) VALUES (?, ?)",
            (session["vendedor_id"], token),
        )
    db.commit()

    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Autenticação de vendedor
# ------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    db = get_db()
    usuario = request.form.get("usuario", "").strip()
    senha = request.form.get("senha", "")

    from werkzeug.security import check_password_hash

    vendedor = db.execute("SELECT * FROM vendedores WHERE usuario = ?", (usuario,)).fetchone()

    if not vendedor or not check_password_hash(vendedor["senha"], senha):
        return redirect(url_for("login", erro="1"))

    session["usuario"] = vendedor["usuario"]
    session["vendedor_id"] = vendedor["id"]
    return redirect(url_for("painel_adm"))


@app.route("/logout")
def logout():
    session.pop("usuario", None)
    session.pop("vendedor_id", None)
    return redirect(url_for("login"))


# ------------------------------------------------------------------
# Painel admin (somente vendedor logado)
# ------------------------------------------------------------------

@app.route("/painel")
@login_obrigatorio
def painel_adm():
    db = get_db()
    pets = db.execute("SELECT * FROM pets ORDER BY id DESC").fetchall()
    seeds = db.execute("SELECT * FROM seeds ORDER BY id DESC").fetchall()
    gears = db.execute("SELECT * FROM gears ORDER BY id DESC").fetchall()
    pedidos = db.execute("SELECT * FROM pedidos ORDER BY id DESC LIMIT 20").fetchall()
    config = db.execute("SELECT valor FROM configuracoes WHERE chave = 'sobre_nos'").fetchone()
    sobre_nos_texto = config["valor"] if config else ""

    bot_regras = db.execute("SELECT * FROM bot_respostas ORDER BY ordem ASC").fetchall()
    config_bot = db.execute("SELECT valor FROM configuracoes WHERE chave = 'bot_resposta_padrao'").fetchone()
    bot_resposta_padrao = config_bot["valor"] if config_bot else bot.RESPOSTA_PADRAO_DEFAULT

    config_duvidas = db.execute("SELECT valor FROM configuracoes WHERE chave = 'duvidas_texto'").fetchone()
    duvidas_texto = config_duvidas["valor"] if config_duvidas else ""

    ofertas = buscar_ofertas_do_dia(db)

    return render_template(
        "Painel_ADM.html", pets=pets, seeds=seeds, gears=gears, pedidos=pedidos,
        push_disponivel=push.push_disponivel(), sobre_nos_texto=sobre_nos_texto,
        bot_regras=bot_regras, bot_resposta_padrao=bot_resposta_padrao,
        duvidas_texto=duvidas_texto, ofertas=ofertas,
    )


@app.route("/update_sobre_nos", methods=["POST"])
@login_obrigatorio
def update_sobre_nos():
    db = get_db()
    texto = request.form.get("texto", "").strip()

    if not texto:
        flash("O texto de Sobre Nós não pode ficar vazio.")
        return redirect(url_for("painel_adm"))

    if len(texto) > 5000:
        flash("Texto muito longo (máximo 5000 caracteres).")
        return redirect(url_for("painel_adm"))

    db.execute(
        "INSERT INTO configuracoes (chave, valor) VALUES ('sobre_nos', ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (texto,),
    )
    db.commit()
    flash("Texto de 'Sobre Nós' atualizado!")
    return redirect(url_for("painel_adm"))


# ------------------------------------------------------------------
# Tema global do site
# ------------------------------------------------------------------

@app.route("/update_tema", methods=["POST"])
@login_obrigatorio
def update_tema():
    db = get_db()
    tema_atual = get_tema(db)

    novo_tema = {
        "bg_color": request.form.get("bg_color", tema_atual["bg_color"]),
        "primary_color": request.form.get("primary_color", tema_atual["primary_color"]),
        "secondary_color": request.form.get("secondary_color", tema_atual["secondary_color"]),
        "accent_color": request.form.get("accent_color", tema_atual["accent_color"]),
        "text_color": request.form.get("text_color", tema_atual["text_color"]),
        "card_color": request.form.get("card_color", tema_atual["card_color"]),
        "overlay_opacity": request.form.get("overlay_opacity", tema_atual["overlay_opacity"]),
        "card_opacity": request.form.get("card_opacity", tema_atual["card_opacity"]),
        "font_family": request.form.get("font_family", tema_atual["font_family"]),
        "bg_image": tema_atual["bg_image"],
    }

    if request.form.get("remover_bg_image") == "1":
        novo_tema["bg_image"] = ""

    arquivo = request.files.get("bg_image")
    if arquivo and arquivo.filename:
        extensoes_permitidas = {"png", "jpg", "jpeg", "webp", "gif"}
        ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
        if ext in extensoes_permitidas:
            os.makedirs(THEME_UPLOAD_FOLDER, exist_ok=True)
            nome_seguro = secure_filename(arquivo.filename)
            nome_final = f"bg_{secrets.token_hex(6)}_{nome_seguro}"
            caminho_disco = os.path.join(THEME_UPLOAD_FOLDER, nome_final)
            arquivo.save(caminho_disco)
            novo_tema["bg_image"] = "/" + caminho_disco.replace("\\", "/")
        else:
            flash("Formato de imagem não suportado (use png, jpg, jpeg, webp ou gif).")
            return redirect(url_for("painel_adm"))

    db.execute(
        "INSERT INTO configuracoes (chave, valor) VALUES ('tema_site', ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (json.dumps(novo_tema),),
    )
    db.commit()
    flash("Tema do site atualizado!")
    return redirect(url_for("painel_adm"))


@app.route("/resetar_tema", methods=["POST"])
@login_obrigatorio
def resetar_tema():
    db = get_db()
    db.execute(
        "INSERT INTO configuracoes (chave, valor) VALUES ('tema_site', ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (json.dumps(TEMA_PADRAO),),
    )
    db.commit()
    flash("Tema resetado para o padrão.")
    return redirect(url_for("painel_adm"))


# ------------------------------------------------------------------
# Bot de atendimento (regras por palavra-chave, editáveis pelo painel)
# ------------------------------------------------------------------

@app.route("/bot/regras", methods=["POST"])
@login_obrigatorio
def bot_criar_regra():
    db = get_db()
    palavra_chave = request.form.get("palavra_chave", "").strip()
    resposta = request.form.get("resposta", "").strip()

    if not palavra_chave or not resposta:
        flash("Preencha a palavra-chave e a resposta do bot.")
        return redirect(url_for("painel_adm"))

    if len(palavra_chave) > 100:
        flash("Palavra-chave muito longa (máximo 100 caracteres).")
        return redirect(url_for("painel_adm"))

    if len(resposta) > 1000:
        flash("Resposta muito longa (máximo 1000 caracteres).")
        return redirect(url_for("painel_adm"))

    maior_ordem = db.execute("SELECT COALESCE(MAX(ordem), -1) AS m FROM bot_respostas").fetchone()["m"]

    db.execute(
        "INSERT INTO bot_respostas (palavra_chave, resposta, ordem) VALUES (?, ?, ?)",
        (palavra_chave, resposta, maior_ordem + 1),
    )
    db.commit()
    flash(f'Regra "{palavra_chave}" adicionada ao bot.')
    return redirect(url_for("painel_adm"))


@app.route("/bot/regras/<int:regra_id>", methods=["POST"])
@login_obrigatorio
def bot_editar_regra(regra_id):
    db = get_db()
    existente = db.execute("SELECT id FROM bot_respostas WHERE id = ?", (regra_id,)).fetchone()
    if not existente:
        flash("Regra não encontrada.")
        return redirect(url_for("painel_adm"))

    palavra_chave = request.form.get("palavra_chave", "").strip()
    resposta = request.form.get("resposta", "").strip()

    if not palavra_chave or not resposta:
        flash("Preencha a palavra-chave e a resposta do bot.")
        return redirect(url_for("painel_adm"))

    if len(palavra_chave) > 100 or len(resposta) > 1000:
        flash("Texto muito longo (palavra-chave: 100, resposta: 1000 caracteres).")
        return redirect(url_for("painel_adm"))

    db.execute(
        "UPDATE bot_respostas SET palavra_chave = ?, resposta = ? WHERE id = ?",
        (palavra_chave, resposta, regra_id),
    )
    db.commit()
    flash("Regra do bot atualizada.")
    return redirect(url_for("painel_adm"))


@app.route("/bot/regras/<int:regra_id>/excluir", methods=["POST"])
@login_obrigatorio
def bot_excluir_regra(regra_id):
    db = get_db()
    db.execute("DELETE FROM bot_respostas WHERE id = ?", (regra_id,))
    db.commit()
    flash("Regra do bot removida.")
    return redirect(url_for("painel_adm"))


@app.route("/bot/resposta-padrao", methods=["POST"])
@login_obrigatorio
def bot_atualizar_resposta_padrao():
    db = get_db()
    texto = request.form.get("texto", "").strip()

    if not texto:
        flash("A resposta padrão do bot não pode ficar vazia.")
        return redirect(url_for("painel_adm"))

    if len(texto) > 1000:
        flash("Resposta padrão muito longa (máximo 1000 caracteres).")
        return redirect(url_for("painel_adm"))

    db.execute(
        "INSERT INTO configuracoes (chave, valor) VALUES ('bot_resposta_padrao', ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (texto,),
    )
    db.commit()
    flash("Resposta padrão do bot atualizada.")
    return redirect(url_for("painel_adm"))


@app.route("/update_pet", methods=["POST"])
@login_obrigatorio
def update_pet():
    return _update_item("pets")


@app.route("/update_seed", methods=["POST"])
@login_obrigatorio
def update_seed():
    return _update_item("seeds")


@app.route("/update_gear", methods=["POST"])
@login_obrigatorio
def update_gear():
    return _update_item("gears")


def _update_item(tabela):
    """
    Lógica compartilhada pelos 3 forms do painel admin.
    Se o "nome" já existir na tabela, atualiza stock/preço/imagem/emoji.
    Se não existir, cria um item novo.
    """
    db = get_db()
    nome = request.form.get("name", "").strip()
    stock = request.form.get("stock", "0")
    preco = request.form.get("price", "0")
    imagem = request.form.get("image", "").strip()
    emoji = request.form.get("emoji", "").strip()

    if not nome:
        flash("Nome do item é obrigatório.")
        return redirect(url_for("painel_adm"))

    try:
        stock = int(stock)
        preco = float(preco)
    except ValueError:
        flash("Stock deve ser inteiro e preço deve ser número.")
        return redirect(url_for("painel_adm"))

    if len(emoji) > 10:
        flash("Emoji muito longo (máximo 10 caracteres).")
        return redirect(url_for("painel_adm"))

    existente = db.execute(f"SELECT id FROM {tabela} WHERE nome = ?", (nome,)).fetchone()

    if existente:
        db.execute(
            f"UPDATE {tabela} SET stock = ?, preco = ?, imagem = ?, emoji = ? WHERE id = ?",
            (stock, preco, imagem or None, emoji or None, existente["id"]),
        )
        flash(f'"{nome}" atualizado em {tabela}.')
    else:
        db.execute(
            f"INSERT INTO {tabela} (nome, stock, preco, imagem, emoji) VALUES (?, ?, ?, ?, ?)",
            (nome, stock, preco, imagem or None, emoji or None),
        )
        flash(f'"{nome}" criado em {tabela}.')

    db.commit()
    return redirect(url_for("painel_adm"))


@app.route("/delete_item/<tabela>/<int:item_id>", methods=["POST"])
@login_obrigatorio
def delete_item(tabela, item_id):
    if tabela not in ("pets", "seeds", "gears"):
        flash("Categoria inválida.")
        return redirect(url_for("painel_adm"))

    db = get_db()
    db.execute(f"DELETE FROM {tabela} WHERE id = ?", (item_id,))
    # Remove também a oferta do dia que referenciasse esse item, se existir
    # (já que não há FOREIGN KEY entre ofertas_do_dia e pets/seeds/gears,
    # pois a tabela de destino varia conforme a categoria).
    db.execute("DELETE FROM ofertas_do_dia WHERE categoria = ? AND item_id = ?", (tabela, item_id))
    db.commit()
    flash("Item removido.")
    return redirect(url_for("painel_adm"))


# ------------------------------------------------------------------
# Criar vendedor (somente vendedor já logado pode criar outro)
# ------------------------------------------------------------------

@app.route("/criar_vendedor", methods=["GET", "POST"])
@login_obrigatorio
def criar_vendedor():
    from werkzeug.security import generate_password_hash

    if request.method == "GET":
        return render_template("criar_vendedor.html", mensagem="")

    db = get_db()
    usuario = request.form.get("usuario", "").strip()
    senha = request.form.get("senha", "")

    if not usuario or not senha:
        return render_template("criar_vendedor.html", mensagem="Preencha usuário e senha.")

    existente = db.execute("SELECT id FROM vendedores WHERE usuario = ?", (usuario,)).fetchone()
    if existente:
        return render_template("criar_vendedor.html", mensagem="Esse usuário já existe.")

    senha_hash = generate_password_hash(senha)
    db.execute("INSERT INTO vendedores (usuario, senha) VALUES (?, ?)", (usuario, senha_hash))
    db.commit()

    return render_template("criar_vendedor.html", mensagem=f'Vendedor "{usuario}" criado com sucesso!')


# ------------------------------------------------------------------
# Trades (não exige login — qualquer jogador pode propor/responder)
# ------------------------------------------------------------------

@app.route("/trades")
def trades_lista():
    db = get_db()
    nome = request.args.get("nome", "").strip()

    recebidas = enviadas = []
    if nome:
        recebidas = db.execute(
            "SELECT * FROM trades WHERE nome_receptor = ? ORDER BY criado_em DESC",
            (nome,),
        ).fetchall()
        enviadas = db.execute(
            "SELECT * FROM trades WHERE nome_ofertante = ? ORDER BY criado_em DESC",
            (nome,),
        ).fetchall()

        # Anexa os itens de cada trade
        def com_itens(trade_rows):
            resultado = []
            for t in trade_rows:
                itens = db.execute("SELECT * FROM trade_itens WHERE trade_id = ?", (t["id"],)).fetchall()
                ofertados = [i for i in itens if i["lado"] == "oferta"]
                pedidos = [i for i in itens if i["lado"] == "pedido"]
                resultado.append({"trade": t, "ofertados": ofertados, "pedidos": pedidos})
            return resultado

        recebidas = com_itens(recebidas)
        enviadas = com_itens(enviadas)

    return render_template("trades.html", nome=nome, recebidas=recebidas, enviadas=enviadas)


@app.route("/trades/criar", methods=["POST"])
def trades_criar():
    db = get_db()

    nome_ofertante = request.form.get("nome_ofertante", "").strip()
    nome_receptor = request.form.get("nome_receptor", "").strip()
    mensagem = request.form.get("mensagem", "").strip()

    itens_oferta = request.form.getlist("item_oferta[]")
    qtd_oferta = request.form.getlist("qtd_oferta[]")
    itens_pedido = request.form.getlist("item_pedido[]")
    qtd_pedido = request.form.getlist("qtd_pedido[]")

    if not nome_ofertante or not nome_receptor:
        flash("Preencha seu nome e o nome de quem vai receber a proposta.")
        return redirect(url_for("trades_lista", nome=nome_ofertante))

    if nome_ofertante == nome_receptor:
        flash("Você não pode propor uma trade para você mesmo.")
        return redirect(url_for("trades_lista", nome=nome_ofertante))

    ofertados = [(n.strip(), q) for n, q in zip(itens_oferta, qtd_oferta) if n.strip()]
    pedidos = [(n.strip(), q) for n, q in zip(itens_pedido, qtd_pedido) if n.strip()]

    if not ofertados or not pedidos:
        flash("Adicione ao menos 1 item oferecido e 1 item pedido.")
        return redirect(url_for("trades_lista", nome=nome_ofertante))

    codigo = secrets.token_hex(6)

    cur = db.execute(
        "INSERT INTO trades (codigo, nome_ofertante, nome_receptor, mensagem) VALUES (?, ?, ?, ?)",
        (codigo, nome_ofertante, nome_receptor, mensagem or None),
    )
    trade_id = cur.lastrowid

    for nome_item, qtd in ofertados:
        try:
            qtd = max(1, int(qtd))
        except ValueError:
            qtd = 1
        db.execute(
            "INSERT INTO trade_itens (trade_id, lado, nome_item, quantidade) VALUES (?, 'oferta', ?, ?)",
            (trade_id, nome_item, qtd),
        )

    for nome_item, qtd in pedidos:
        try:
            qtd = max(1, int(qtd))
        except ValueError:
            qtd = 1
        db.execute(
            "INSERT INTO trade_itens (trade_id, lado, nome_item, quantidade) VALUES (?, 'pedido', ?, ?)",
            (trade_id, nome_item, qtd),
        )

    db.commit()
    flash(f"Proposta de trade enviada para {nome_receptor}!")
    return redirect(url_for("trades_lista", nome=nome_ofertante))


@app.route("/trades/<int:trade_id>/aceitar", methods=["POST"])
def trades_aceitar(trade_id):
    return _resolver_trade(trade_id, "aceita")


@app.route("/trades/<int:trade_id>/recusar", methods=["POST"])
def trades_recusar(trade_id):
    return _resolver_trade(trade_id, "recusada")


@app.route("/trades/<int:trade_id>/cancelar", methods=["POST"])
def trades_cancelar(trade_id):
    return _resolver_trade(trade_id, "cancelada")


def _resolver_trade(trade_id, novo_status):
    db = get_db()
    nome = request.form.get("nome", "").strip()

    trade = db.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if not trade:
        flash("Trade não encontrada.")
        return redirect(url_for("trades_lista", nome=nome))

    if trade["status"] != "pendente":
        flash(f'Essa trade já foi resolvida (status: {trade["status"]}).')
        return redirect(url_for("trades_lista", nome=nome))

    # Só o receptor pode aceitar/recusar; só o ofertante pode cancelar
    if novo_status in ("aceita", "recusada") and nome != trade["nome_receptor"]:
        flash("Só quem recebeu a proposta pode aceitar ou recusar.")
        return redirect(url_for("trades_lista", nome=nome))

    if novo_status == "cancelada" and nome != trade["nome_ofertante"]:
        flash("Só quem propôs a trade pode cancelá-la.")
        return redirect(url_for("trades_lista", nome=nome))

    db.execute(
        "UPDATE trades SET status = ?, resolvido_em = datetime('now') WHERE id = ?",
        (novo_status, trade_id),
    )
    db.commit()
    flash(f"Trade marcada como {novo_status}.")
    return redirect(url_for("trades_lista", nome=nome))


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_mode, port=int(os.environ.get("PORT", 5000)))
