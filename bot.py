# bot.py
"""
Bot de atendimento simples, baseado em palavras-chave (sem IA externa, sem
custo, sem necessidade de cartão ou conta em serviço nenhum).

Como funciona:
  - Cada regra tem uma ou mais palavras-chave e uma resposta associada
  - Quando o cliente manda uma mensagem, o bot procura a primeira regra cuja
    palavra-chave apareça na mensagem (sem diferenciar maiúsculas/minúsculas
    e ignorando acentos) e responde com o texto daquela regra
  - Se nenhuma regra bater, o bot manda a "resposta padrão"
  - As regras (e a resposta padrão) ficam guardadas no banco
    (tabela bot_respostas e configuracoes) e são editáveis pelo Painel Admin

O bot só responde enquanto nenhum vendedor humano tiver escrito naquele chat
(essa parte do controle continua em app.py, não aqui).
"""

import unicodedata


def _normalizar(texto):
    """Remove acentos e baixa a caixa, pra comparação de palavras-chave
    não depender de acento/maiúscula exatos (ex: 'preço' bate com 'preco')."""
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto


def gerar_resposta(mensagem_cliente, regras, resposta_padrao):
    """
    Procura a primeira regra cuja palavra-chave apareça na mensagem do
    cliente e devolve a resposta associada. Se nenhuma bater, devolve a
    resposta padrão. Sempre devolve uma string (nunca None) — esse bot
    não depende de nenhum serviço externo, então não há cenário de falha.

    mensagem_cliente: texto que o cliente escreveu
    regras: lista de dicts {palavra_chave, resposta}, na ordem de prioridade
    resposta_padrao: texto usado quando nenhuma regra bate
    """
    texto_normalizado = _normalizar(mensagem_cliente)

    for regra in regras:
        palavra_chave = _normalizar(regra["palavra_chave"])
        if palavra_chave and palavra_chave in texto_normalizado:
            return regra["resposta"]

    return resposta_padrao


# Regras padrão sugeridas, inseridas automaticamente na primeira migração
# (o usuário pode editar, remover ou adicionar outras pelo Painel Admin).
REGRAS_PADRAO = [
    {
        "palavra_chave": "preco",
        "resposta": "Você pode ver todos os preços atualizados na página de Stock! Lá tem Pets, Seeds e Gears com preço e quantidade disponível.",
    },
    {
        "palavra_chave": "entrega",
        "resposta": "A entrega é feita dentro do próprio jogo, combinada aqui no chat com o vendedor. Assim que ele entrar, vocês combinam o melhor horário.",
    },
    {
        "palavra_chave": "como comprar",
        "resposta": "É bem simples: escolhe o item na página de Stock, clica em Comprar, e depois finalize a compra no carrinho. Você será levado direto pra esse chat!",
    },
    {
        "palavra_chave": "horario",
        "resposta": "Nossos vendedores costumam responder o mais rápido possível! Em breve alguém vai continuar seu atendimento aqui.",
    },
    {
        "palavra_chave": "trade",
        "resposta": "Para fazer trocas com outros jogadores, acesse a página de Trades no menu principal do site!",
    },
    {
        "palavra_chave": "pagamento",
        "resposta": "As formas de pagamento são combinadas diretamente com o vendedor por aqui no chat.",
    },
]

RESPOSTA_PADRAO_DEFAULT = (
    "Olá! Sou o assistente automático da MYU Store 🤖. Um vendedor vai "
    "continuar seu atendimento em breve. Enquanto isso, você pode perguntar "
    "sobre preços, entrega, como comprar ou trades!"
)
