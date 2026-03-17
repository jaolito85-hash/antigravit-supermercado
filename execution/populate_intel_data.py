"""
Popula o Supabase com dados realistas para testar as features premium:
- Radar de Concorrência (menções a concorrentes)
- Alertas de Crise (padrões anormais)
- Detector de Êxodo (clientes recorrentes em risco)
"""
import os, sys, random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Configure SUPABASE_URL e SUPABASE_KEY no .env")
    sys.exit(1)

from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

now = datetime.utcnow()

# === CLIENTES RECORRENTES (para Detector de Êxodo) ===
CLIENTES = [
    {"sender": "5511999001001@s.whatsapp.net", "name": "Maria Silva"},
    {"sender": "5511999002002@s.whatsapp.net", "name": "João Pereira"},
    {"sender": "5511999003003@s.whatsapp.net", "name": "Ana Souza"},
    {"sender": "5511999004004@s.whatsapp.net", "name": "Carlos Mendes"},
    {"sender": "5511999005005@s.whatsapp.net", "name": "Fernanda Lima"},
    {"sender": "5511999006006@s.whatsapp.net", "name": "Roberto Santos"},
    {"sender": "5511999007007@s.whatsapp.net", "name": "Patrícia Oliveira"},
    {"sender": "5511999008008@s.whatsapp.net", "name": "Marcos Ribeiro"},
]

# === FEEDBACKS COM MENÇÕES A CONCORRENTES ===
COMPETITOR_FEEDBACKS = [
    # Assaí - preço
    {"message": "Gente, fui no Assaí semana passada e a carne tava metade do preço de vocês. Tem como melhorar?", "category": "Preço", "urgency": "Urgente", "region": "Açougue", "loja": "Matriz"},
    {"message": "No Assaí o arroz tá 3 reais mais barato que aqui, absurdo a diferença", "category": "Preço", "urgency": "Urgente", "region": "Geral", "loja": "Filial Centro"},
    {"message": "Minha vizinha só compra no Assaí porque é mais em conta, vocês precisam competir", "category": "Preço", "urgency": "Neutro", "region": "Geral", "loja": "Matriz"},
    # Atacadão - variedade
    {"message": "O Atacadão tem mais variedade de cervejas importadas, vocês só tem as básicas", "category": "Atendimento", "urgency": "Urgente", "region": "Bebidas", "loja": "Filial Centro"},
    {"message": "Fui no Atacadão e encontrei tudo que precisava, aqui sempre falta produto", "category": "Atendimento", "urgency": "Urgente", "region": "Geral", "loja": "Matriz"},
    # Carrefour - qualidade
    {"message": "O Carrefour tem hortifrúti de melhor qualidade, as frutas de vocês tão sempre passadas", "category": "Hortifrúti", "urgency": "Urgente", "region": "Hortifrúti", "loja": "Filial Bairro"},
    {"message": "Sinceramente o Carrefour atende melhor, os funcionários lá são mais simpáticos", "category": "Atendimento", "urgency": "Urgente", "region": "Geral", "loja": "Matriz"},
    # Extra e outros
    {"message": "No Extra a promoção é muito melhor, vocês quase não fazem oferta boa", "category": "Preço", "urgency": "Neutro", "region": "Geral", "loja": "Filial Centro"},
    {"message": "Pão de Açúcar tem produtos orgânicos muito melhores que os de vocês", "category": "Hortifrúti", "urgency": "Neutro", "region": "Hortifrúti", "loja": "Filial Bairro"},
    {"message": "Meu marido prefere ir no outro mercado da esquina porque tem mais vaga no estacionamento", "category": "Estacionamento", "urgency": "Neutro", "region": "Estacionamento", "loja": "Matriz"},
    {"message": "A concorrência tá com preço melhor em quase tudo, vocês precisam reagir", "category": "Preço", "urgency": "Urgente", "region": "Geral", "loja": "Filial Centro"},
]

# === FEEDBACKS DE CRISE (Hortifrúti - muitas reclamações recentes) ===
CRISIS_HORTIFRUTTI = [
    {"message": "Banana toda preta, já é a terceira vez essa semana que pego fruta estragada", "category": "Hortifrúti", "urgency": "Critico", "region": "Hortifrúti", "loja": "Matriz"},
    {"message": "Tomate podre na prateleira, isso é falta de respeito com o cliente", "category": "Hortifrúti", "urgency": "Critico", "region": "Hortifrúti", "loja": "Matriz"},
    {"message": "Alface murcha e com bicho!!! Absurdo, vocês não fazem controle de qualidade?", "category": "Hortifrúti", "urgency": "Critico", "region": "Hortifrúti", "loja": "Filial Centro"},
    {"message": "Morango mofado dentro da embalagem, comprei hoje e já tava ruim", "category": "Hortifrúti", "urgency": "Critico", "region": "Hortifrúti", "loja": "Filial Bairro"},
    {"message": "Cheiro horrível perto das frutas, parece que tem coisa estragada embaixo", "category": "Hortifrúti", "urgency": "Urgente", "region": "Hortifrúti", "loja": "Matriz"},
    {"message": "Mamão já chegou podre em casa, comprei aqui ontem", "category": "Hortifrúti", "urgency": "Urgente", "region": "Hortifrúti", "loja": "Filial Centro"},
]

# === FEEDBACKS DE CRISE (Fila - pico de reclamações) ===
CRISIS_FILA = [
    {"message": "Uma hora na fila do caixa! Só tem 2 caixas abertos num sábado!", "category": "Fila", "urgency": "Critico", "region": "Caixas", "loja": "Matriz"},
    {"message": "Fila gigantesca, todo mundo reclamando, pessoal largando carrinho e indo embora", "category": "Fila", "urgency": "Critico", "region": "Caixas", "loja": "Matriz"},
    {"message": "Nunca vi tanta fila assim, precisam abrir mais caixas urgente", "category": "Fila", "urgency": "Urgente", "region": "Caixas", "loja": "Filial Centro"},
    {"message": "Self checkout tudo quebrado e fila enorme nos caixas normais", "category": "Fila", "urgency": "Urgente", "region": "Caixas", "loja": "Matriz"},
]

# === FEEDBACKS POSITIVOS (para balancear) ===
POSITIVOS = [
    {"message": "Adorei o atendimento da moça do açougue, super educada e cortou do jeitinho que pedi!", "category": "Açougue", "urgency": "Positivo", "region": "Açougue", "loja": "Matriz"},
    {"message": "Pão francês quentinho às 17h, melhor padaria da região!", "category": "Padaria", "urgency": "Positivo", "region": "Padaria", "loja": "Filial Centro"},
    {"message": "Promoção de cerveja muito boa essa semana, aproveitei bem!", "category": "Preço", "urgency": "Positivo", "region": "Bebidas", "loja": "Filial Bairro"},
    {"message": "Mercado sempre limpinho, banheiro impecável. Parabéns!", "category": "Limpeza", "urgency": "Positivo", "region": "Limpeza", "loja": "Matriz"},
    {"message": "O gerente me ajudou a encontrar um produto, atendimento nota 10!", "category": "Atendimento", "urgency": "Positivo", "region": "Geral", "loja": "Filial Centro"},
]

def insert_feedback(fb, timestamp, cliente=None):
    """Insert a feedback into Supabase"""
    data = {
        "message": fb["message"],
        "category": fb["category"],
        "urgency": fb["urgency"],
        "region": fb.get("region", "Geral"),
        "loja": fb.get("loja", "Matriz"),
        "sentiment": "Positivo" if fb["urgency"] == "Positivo" else ("Negativo" if fb["urgency"] in ["Critico", "Urgente"] else "Neutro"),
        "timestamp": timestamp.isoformat(),
        "status": random.choice(["aberto", "aberto", "aberto", "em_andamento"]) if fb["urgency"] in ["Critico", "Urgente"] else "aberto",
        "sender": cliente["sender"] if cliente else f"5511{random.randint(900000000, 999999999)}@s.whatsapp.net",
        "name": cliente["name"] if cliente else random.choice(["Cliente", "Visitante", "Comprador"]),
    }
    try:
        supabase.table("feedbacks").insert(data).execute()
        return True
    except Exception as e:
        print(f"  ❌ Erro: {e}")
        return False

count = 0

# 1. Cliente Maria (frequente, últimos negativos, mencionou concorrente → ALTO RISCO)
print("👤 Inserindo cliente Maria Silva (alto risco de êxodo)...")
maria = CLIENTES[0]
maria_feedbacks = [
    ({"message": "Adorei a promoção de frutas!", "category": "Hortifrúti", "urgency": "Positivo", "region": "Hortifrúti", "loja": "Matriz"}, now - timedelta(days=30)),
    ({"message": "Muito bom o atendimento hoje!", "category": "Atendimento", "urgency": "Positivo", "region": "Geral", "loja": "Matriz"}, now - timedelta(days=25)),
    ({"message": "Padaria ótima como sempre", "category": "Padaria", "urgency": "Positivo", "region": "Padaria", "loja": "Matriz"}, now - timedelta(days=20)),
    ({"message": "Que absurdo cobrarem R$35 no frango, no Assaí é R$18!", "category": "Preço", "urgency": "Critico", "region": "Açougue", "loja": "Matriz"}, now - timedelta(days=16)),
    ({"message": "Péssimo atendimento hoje, caixa mal educada", "category": "Atendimento", "urgency": "Urgente", "region": "Caixas", "loja": "Matriz"}, now - timedelta(days=15)),
]
for fb, ts in maria_feedbacks:
    if insert_feedback(fb, ts, maria): count += 1

# 2. João (frequente, sumiu há 18 dias, último negativo → ALTO RISCO)
print("👤 Inserindo cliente João Pereira (inativo, alto risco)...")
joao = CLIENTES[1]
joao_feedbacks = [
    ({"message": "Sempre compro aqui, gosto do estacionamento", "category": "Estacionamento", "urgency": "Positivo", "region": "Estacionamento", "loja": "Filial Centro"}, now - timedelta(days=45)),
    ({"message": "Bom atendimento na padaria", "category": "Padaria", "urgency": "Positivo", "region": "Padaria", "loja": "Filial Centro"}, now - timedelta(days=35)),
    ({"message": "Preços subindo demais, tá ficando caro", "category": "Preço", "urgency": "Urgente", "region": "Geral", "loja": "Filial Centro"}, now - timedelta(days=22)),
    ({"message": "Vou começar a ir no Atacadão, lá os preços são mais acessíveis", "category": "Preço", "urgency": "Urgente", "region": "Geral", "loja": "Filial Centro"}, now - timedelta(days=18)),
]
for fb, ts in joao_feedbacks:
    if insert_feedback(fb, ts, joao): count += 1

# 3. Ana (frequente, 2 negativos consecutivos recentes → MÉDIO RISCO)
print("👤 Inserindo cliente Ana Souza (sentimento caindo)...")
ana = CLIENTES[2]
ana_feedbacks = [
    ({"message": "Amo fazer compras aqui, sempre encontro tudo!", "category": "Atendimento", "urgency": "Positivo", "region": "Geral", "loja": "Filial Bairro"}, now - timedelta(days=20)),
    ({"message": "Carne com cheiro estranho, tive que jogar fora", "category": "Açougue", "urgency": "Urgente", "region": "Açougue", "loja": "Filial Bairro"}, now - timedelta(days=5)),
    ({"message": "De novo produto vencido na prateleira, isso é recorrente", "category": "Atendimento", "urgency": "Critico", "region": "Geral", "loja": "Filial Bairro"}, now - timedelta(days=2)),
]
for fb, ts in ana_feedbacks:
    if insert_feedback(fb, ts, ana): count += 1

# 4. Carlos (frequente, satisfeito → SEM RISCO, para contraste)
print("👤 Inserindo cliente Carlos Mendes (satisfeito, sem risco)...")
carlos = CLIENTES[3]
carlos_feedbacks = [
    ({"message": "Melhor mercado da região!", "category": "Atendimento", "urgency": "Positivo", "region": "Geral", "loja": "Matriz"}, now - timedelta(days=10)),
    ({"message": "Promoção excelente essa semana", "category": "Preço", "urgency": "Positivo", "region": "Geral", "loja": "Matriz"}, now - timedelta(days=3)),
]
for fb, ts in carlos_feedbacks:
    if insert_feedback(fb, ts, carlos): count += 1

# 5. Fernanda (mencionou concorrente + negativo recente → RISCO)
print("👤 Inserindo cliente Fernanda Lima (mencionou concorrente)...")
fernanda = CLIENTES[4]
fernanda_feedbacks = [
    ({"message": "Gosto da padaria de vocês", "category": "Padaria", "urgency": "Positivo", "region": "Padaria", "loja": "Filial Centro"}, now - timedelta(days=25)),
    ({"message": "O Carrefour tem mais opção de produtos importados que vocês", "category": "Atendimento", "urgency": "Neutro", "region": "Geral", "loja": "Filial Centro"}, now - timedelta(days=8)),
    ({"message": "Fila absurda hoje, quase fui pro Carrefour", "category": "Fila", "urgency": "Urgente", "region": "Caixas", "loja": "Filial Centro"}, now - timedelta(days=3)),
]
for fb, ts in fernanda_feedbacks:
    if insert_feedback(fb, ts, fernanda): count += 1

# 6. Roberto (3 interações, último positivo → SEM RISCO)
print("👤 Inserindo cliente Roberto Santos (fiel)...")
roberto = CLIENTES[5]
roberto_feedbacks = [
    ({"message": "Bom atendimento como sempre", "category": "Atendimento", "urgency": "Positivo", "region": "Geral", "loja": "Matriz"}, now - timedelta(days=14)),
    ({"message": "Gostei da reforma no estacionamento", "category": "Estacionamento", "urgency": "Positivo", "region": "Estacionamento", "loja": "Matriz"}, now - timedelta(days=7)),
    ({"message": "Voltei a comprar frango aqui, melhorou muito!", "category": "Açougue", "urgency": "Positivo", "region": "Açougue", "loja": "Matriz"}, now - timedelta(days=1)),
]
for fb, ts in roberto_feedbacks:
    if insert_feedback(fb, ts, roberto): count += 1

# 7. Menções a concorrentes (de clientes avulsos)
print("\n🕵️ Inserindo menções a concorrentes...")
for fb in COMPETITOR_FEEDBACKS:
    ts = now - timedelta(hours=random.randint(2, 72))
    if insert_feedback(fb, ts): count += 1

# 8. Crise Hortifrúti (muitas reclamações recentes)
print("🚨 Inserindo crise de Hortifrúti (últimas 48h)...")
for fb in CRISIS_HORTIFRUTTI:
    ts = now - timedelta(hours=random.randint(1, 36))
    if insert_feedback(fb, ts): count += 1

# 9. Crise Fila (reclamações nas horas de pico)
print("⏰ Inserindo reclamações de fila em horários de pico...")
for fb in CRISIS_FILA:
    # Set specific peak hours (17h-19h)
    peak_hour = random.choice([17, 18, 19])
    ts = now.replace(hour=peak_hour, minute=random.randint(0, 59)) - timedelta(days=random.randint(0, 2))
    if insert_feedback(fb, ts): count += 1

# 10. Positivos (para balancear ROI)
print("✅ Inserindo feedbacks positivos...")
for fb in POSITIVOS:
    ts = now - timedelta(hours=random.randint(1, 48))
    if insert_feedback(fb, ts): count += 1

# 11. Feedbacks resolvidos (para ROI mostrar receita retida)
print("💰 Inserindo feedbacks resolvidos (para ROI)...")
resolved_feedbacks = [
    {"message": "Reclamei da carne estragada e trocaram na hora", "category": "Açougue", "urgency": "Critico", "region": "Açougue", "loja": "Matriz"},
    {"message": "Produto vencido, mas o gerente resolveu rápido", "category": "Atendimento", "urgency": "Critico", "region": "Geral", "loja": "Filial Centro"},
    {"message": "Cobraram errado no caixa, mas devolveram a diferença", "category": "Preço", "urgency": "Urgente", "region": "Caixas", "loja": "Matriz"},
    {"message": "Banheiro estava sujo mas limparam quando avisei", "category": "Limpeza", "urgency": "Urgente", "region": "Limpeza", "loja": "Filial Bairro"},
    {"message": "Fila enorme mas abriram mais caixas depois da reclamação", "category": "Fila", "urgency": "Urgente", "region": "Caixas", "loja": "Matriz"},
]
for fb in resolved_feedbacks:
    ts = now - timedelta(days=random.randint(1, 7))
    resolved_ts = ts + timedelta(hours=random.randint(1, 8))
    data = {
        "message": fb["message"],
        "category": fb["category"],
        "urgency": fb["urgency"],
        "region": fb.get("region", "Geral"),
        "loja": fb.get("loja", "Matriz"),
        "sentiment": "Negativo",
        "timestamp": ts.isoformat(),
        "status": "resolvido",
        "resolved_at": resolved_ts.strftime("%d/%m/%y %H:%M"),
        "sender": f"5511{random.randint(900000000, 999999999)}@s.whatsapp.net",
        "name": random.choice(["Cliente", "Visitante"]),
    }
    try:
        supabase.table("feedbacks").insert(data).execute()
        count += 1
    except Exception as e:
        print(f"  ❌ Erro: {e}")

print(f"\n✅ {count} feedbacks inseridos com sucesso!")
print("\n📊 Resumo dos dados inseridos:")
print(f"  🕵️ {len(COMPETITOR_FEEDBACKS)} menções a concorrentes (Assaí, Atacadão, Carrefour, Extra, Pão de Açúcar)")
print(f"  🚨 {len(CRISIS_HORTIFRUTTI)} reclamações de Hortifrúti (crise ativa)")
print(f"  ⏰ {len(CRISIS_FILA)} reclamações de Fila (horários de pico 17h-19h)")
print(f"  👤 8 clientes rastreáveis (3 alto risco, 2 médio risco, 3 satisfeitos)")
print(f"  💰 {len(resolved_feedbacks)} feedbacks resolvidos (para ROI)")
print(f"  ✅ {len(POSITIVOS)} feedbacks positivos")
print("\n🔄 Recarregue o dashboard em http://localhost:5003 e clique em 'Inteligência'!")
