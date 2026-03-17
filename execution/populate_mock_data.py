"""
Populate mock data for Supermercado Node Data
Generates realistic feedback data for testing the dashboard.
Usage: python execution/populate_mock_data.py
"""
import json
import random
import os
from datetime import datetime, timedelta

EVENTS_FILE = os.path.join(os.path.dirname(__file__), 'events.json')

CATEGORIAS = ['Atendimento', 'Fila', 'Hortifrúti', 'Padaria', 'Açougue', 'Limpeza', 'Preço', 'Estacionamento']
SENTIMENTOS = ['Positivo', 'Neutro', 'Urgente', 'Critico']
SENTIMENTO_PESOS = [0.35, 0.30, 0.25, 0.10]
LOJAS = ['Matriz', 'Filial Centro', 'Filial Norte', 'Filial Sul']
SETORES = ['Caixas', 'Hortifrúti', 'Padaria', 'Açougue', 'Bebidas', 'Limpeza', 'Estacionamento', 'Entrada', 'Geral']

NOMES = [
    'Maria', 'João', 'Ana', 'Carlos', 'Fernanda', 'Pedro', 'Juliana', 'Lucas',
    'Patrícia', 'Rafael', 'Camila', 'Gustavo', 'Bruna', 'Diego', 'Larissa',
    'Thiago', 'Amanda', 'Bruno', 'Letícia', 'Marcelo', 'Renata', 'Felipe',
    'Daniela', 'Roberto', 'Vanessa', 'Rodrigo', 'Aline', 'Eduardo', 'Carla'
]

MENSAGENS = {
    'Atendimento': {
        'Positivo': ['Funcionários muito educados, adorei o atendimento!', 'A moça do caixa foi super simpática, parabéns!', 'Atendimento nota 10, voltarei com certeza!'],
        'Neutro': ['Fui atendido normalmente, sem reclamações.', 'Atendimento ok, nada de especial.'],
        'Urgente': ['Funcionário foi grosseiro comigo! Absurdo!', 'Ninguém pra ajudar, todos no celular!', 'Péssimo atendimento, descaso total!'],
        'Critico': ['Funcionário me agrediu verbalmente! Quero providências!', 'Briga entre funcionários na frente dos clientes!']
    },
    'Fila': {
        'Positivo': ['Passei rápido no caixa, sem fila nenhuma!', 'Hoje o caixa tava voando, muito rápido!'],
        'Neutro': ['Fila normal, demorou uns 5 minutos.', 'Tinha fila mas andou rápido.'],
        'Urgente': ['Fila enorme! Só 2 caixas abertos e o mercado lotado!', 'Uma hora na fila! Poucos caixas funcionando!', 'Fila gigante, funcionários conversando e não abrindo caixa!'],
        'Critico': ['Idosa passou mal na fila de tão lotado! Isso é um absurdo!']
    },
    'Hortifrúti': {
        'Positivo': ['Frutas fresquinhas hoje! O morango tava uma delícia!', 'Hortifrúti muito bem organizado, verduras ótimas!', 'Adorei a variedade de orgânicos!'],
        'Neutro': ['Hortifrúti normal, poderia ter mais variedade.'],
        'Urgente': ['Tomate todo amassado e mofado! Vergonha!', 'Frutas podres na prateleira, nojento!', 'Alface toda murcha, batata verde!'],
        'Critico': ['Encontrei inseto no meio das verduras! Absurdo!']
    },
    'Padaria': {
        'Positivo': ['Pão francês quentinho e crocante! O melhor da região!', 'Bolo de chocolate maravilhoso!', 'Pão de queijo fresquinho, amei!'],
        'Neutro': ['Padaria ok, pão normal.'],
        'Urgente': ['Pão duro, parece de ontem! Horário de pão fresco nunca cumprem!', 'Poucos salgados, tudo acabado antes das 10h!'],
        'Critico': ['Achei cabelo no pão! Inaceitável!']
    },
    'Açougue': {
        'Positivo': ['Carnes sempre frescas, açougueiro muito atencioso!', 'Picanha excelente, cortada como eu pedi!'],
        'Neutro': ['Açougue normal, preços medianos.'],
        'Urgente': ['Carne com cheiro estranho! Parece que não tá fresca!', 'Frios com data próxima do vencimento!'],
        'Critico': ['Carne completamente estragada, verde por baixo!']
    },
    'Limpeza': {
        'Positivo': ['Mercado muito limpo e organizado! Parabéns!', 'Banheiro impecável, sempre limpo!'],
        'Neutro': ['Limpeza normal do mercado.'],
        'Urgente': ['Banheiro imundo! Sem papel e sem sabonete!', 'Chão molhado e escorregadio, quase caí!', 'Mau cheiro forte no corredor de frios!'],
        'Critico': ['Vi rato perto dos cereais! Fiscalização já!']
    },
    'Preço': {
        'Positivo': ['Preços ótimos comparado aos concorrentes!', 'Promoção de arroz e feijão muito boa!', 'Barato e bom, melhor custo-benefício!'],
        'Neutro': ['Preços normais, nada de mais.'],
        'Urgente': ['Preço da etiqueta diferente do caixa! Cobraram mais caro!', 'Tudo caro demais! Preços abusivos!', 'Promoção enganosa, na hora de pagar o preço é outro!'],
        'Critico': ['Cobrança fraudulenta! Passaram item em duplicidade!']
    },
    'Estacionamento': {
        'Positivo': ['Estacionamento amplo, sempre acho vaga!', 'Gostei que agora tem vaga para gestante!'],
        'Neutro': ['Estacionamento normal, encontrei vaga.'],
        'Urgente': ['Sem vagas! Rodei 20 minutos pra estacionar!', 'Cancela do estacionamento quebrada, fila enorme!'],
        'Critico': ['Arranharam meu carro no estacionamento e ninguém assumiu!']
    }
}

def generate_mock_feedbacks(count=80):
    feedbacks = []
    for i in range(count):
        cat = random.choice(CATEGORIAS)
        sent = random.choices(SENTIMENTOS, weights=SENTIMENTO_PESOS, k=1)[0]
        msgs = MENSAGENS[cat].get(sent, MENSAGENS[cat].get('Neutro', ['Feedback geral.']))
        msg = random.choice(msgs)
        nome = random.choice(NOMES)
        loja = random.choice(LOJAS)
        setor = random.choice(SETORES)
        days_ago = random.randint(0, 14)
        hours_ago = random.randint(0, 23)
        ts = datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago)

        feedbacks.append({
            "id": i + 1,
            "sender": f"5511{random.randint(900000000, 999999999)}@s.whatsapp.net",
            "name": nome,
            "message": msg,
            "timestamp": ts.isoformat(),
            "category": cat,
            "region": setor,
            "urgency": sent,
            "sentiment": "Positivo" if sent == "Positivo" else ("Negativo" if sent in ["Critico","Urgente"] else "Neutro"),
            "loja": loja,
            "status": random.choice(['aberto', 'aberto', 'aberto', 'em_andamento', 'resolvido'])
        })

    feedbacks.sort(key=lambda x: x['timestamp'], reverse=True)
    return feedbacks

if __name__ == '__main__':
    feedbacks = generate_mock_feedbacks(80)
    with open(EVENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(feedbacks, f, ensure_ascii=False, indent=2)
    print(f"✅ Generated {len(feedbacks)} mock feedbacks in {EVENTS_FILE}")
    cats = {}
    for fb in feedbacks:
        c = fb['category']
        cats[c] = cats.get(c, 0) + 1
    print(f"📊 By category: {cats}")
    sents = {}
    for fb in feedbacks:
        s = fb['urgency']
        sents[s] = sents.get(s, 0) + 1
    print(f"💬 By sentiment: {sents}")
