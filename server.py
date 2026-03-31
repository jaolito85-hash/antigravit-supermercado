import os
import requests
import json
import hashlib
import csv
import re
import unicodedata
import time
import threading
from difflib import SequenceMatcher
from io import StringIO
from contextlib import contextmanager
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from time import time as time_now

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.getenv("SECRET_KEY", "nodedata-supermercado-secret-2026")
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Config
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# Chave service_role — bypassa RLS para operações de servidor (upload de arquivos, etc.)
# Nunca expor essa chave no frontend. Apenas no .env do servidor.
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Initialize Supabase
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client, Client
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase connected!")
    except Exception as e:
        print(f"⚠️ Supabase connection failed: {e}")
        supabase = None

def get_supabase():
    """Returns a working Supabase client, reconnecting if needed."""
    global supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    if supabase is None:
        try:
            from supabase import create_client, Client
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("🔄 Supabase reconnected!")
        except Exception as e:
            print(f"⚠️ Supabase reconnection failed: {e}")
            return None
    return supabase

def _reconnect_supabase():
    """Force reconnect Supabase client."""
    global supabase
    supabase = None
    return get_supabase()

def get_supabase_admin():
    """Retorna um cliente Supabase com a service_role key.
    Essa chave bypassa RLS — usar apenas em operações de servidor
    como upload de arquivos no Storage. Nunca expor no frontend.
    Cai de volta para o cliente anon se a service key não estiver configurada.
    """
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            from supabase import create_client, Client
            return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        except Exception as e:
            print(f"⚠️ Supabase admin client failed: {e}")
    # fallback para o cliente normal se service key não estiver no .env
    return get_supabase()

EVENTS_FILE = 'execution/events.json'
CONFIG_FILE = 'execution/config.json'
PRODUCTS_FILE = 'execution/produtos_mock.json'
MODERATION_FILE = 'execution/moderation_state.json'
HANDOFF_FILE = 'execution/handoff_state.json'
CONTEXT_STATE_DIR = 'execution/conversation_context'
SENDER_LOCKS_DIR = 'execution/sender_locks'
SENDER_LOCK_TIMEOUT_SECONDS = 45
SENDER_LOCK_STALE_SECONDS = 120
SENDER_LOCK_POLL_SECONDS = 0.2
MARKET_NAME = os.getenv("MARKET_NAME", "Atacaforte")
AGENT_NAME = os.getenv("AGENT_NAME", "Seu Pipico")
DEFAULT_PROMOTIONS_EMPTY_TEXT = "No momento eu ainda não recebi as promoções atualizadas."
PROMOTION_DAY_TYPE = "promotion_day"
PROMOTION_WEEK_TYPE = "promotion_week"
BANNER_BUCKET = "banners"

# Encartes mensais (válidos o mês inteiro — 4 folhetos)
BANNER_MONTHLY_GERAL   = "banner_monthly_geral"
BANNER_MONTHLY_BEBIDAS = "banner_monthly_bebidas"
BANNER_MONTHLY_FOOD    = "banner_monthly_food"
BANNER_MONTHLY_OUTROS  = "banner_monthly_outros"
MONTHLY_BANNER_TYPES   = [BANNER_MONTHLY_GERAL, BANNER_MONTHLY_BEBIDAS, BANNER_MONTHLY_FOOD, BANNER_MONTHLY_OUTROS]

# Encartes diários (mudam por período da semana)
BANNER_DAILY_SEG_TER   = "banner_daily_seg_ter"
BANNER_DAILY_QUA_QUI   = "banner_daily_qua_qui"
BANNER_DAILY_SEX_SAB   = "banner_daily_sex_sab"
DAILY_BANNER_TYPES     = [BANNER_DAILY_SEG_TER, BANNER_DAILY_QUA_QUI, BANNER_DAILY_SEX_SAB]

ALL_BANNER_TYPES = MONTHLY_BANNER_TYPES + DAILY_BANNER_TYPES

PROMO_KEYWORDS = (
    'oferta', 'ofertas', 'promocao', 'promocao da semana', 'promocao da semana',
    'promocoes', 'promocoes da semana', 'promoção', 'promoções',
    'promoção da semana', 'promoções da semana', 'desconto', 'encarte'
)

PRODUCT_INQUIRY_PATTERNS = (
    'tem ', 'vocês tem', 'voces tem', 'quanto custa', 'qual o preço',
    'qual o preco', 'preço do', 'preco do', 'preço da', 'preco da',
    'valor do', 'valor da', 'quando chega', 'quando volta', 'avisa quando',
    'me avisa quando', 'tem no mercado', 'chegou', 'voltou', 'estoque'
)

GENERAL_QUESTION_HINTS = (
    'horário', 'horario', 'que horas', 'onde fica', 'localização',
    'localizacao', 'endereço', 'endereco', 'aceita pix', 'aceita cartão',
    'aceita cartao', 'entrega', 'delivery', 'telefone', 'contato',
    'funciona', 'abre', 'fecha', 'domingo', 'sábado', 'sabado'
)

PROMO_KEYWORDS_NORMALIZED = (
    'oferta', 'ofertas', 'promocao', 'promocoes',
    'promocao do dia', 'promocoes do dia',
    'promocao do mes', 'promocoes do mes',
    'desconto', 'encarte'
)

PRODUCT_INQUIRY_PATTERNS_NORMALIZED = (
    'tem ', 'voce tem', 'voces tem', 'quanto custa', 'qual o preco',
    'preco do', 'preco da', 'valor do', 'valor da', 'quando chega',
    'quando volta', 'avisa quando', 'me avisa quando', 'tem no mercado',
    'chegou', 'voltou', 'estoque'
)

GENERAL_QUESTION_HINTS_NORMALIZED = (
    'horario', 'que horas', 'onde fica', 'localizacao', 'endereco',
    'aceita pix', 'aceita cartao', 'entrega', 'delivery', 'telefone',
    'contato', 'funciona', 'abre', 'fecha', 'domingo', 'sabado'
)

# Horário de funcionamento — ajuste aqui se mudar
STORE_OPEN_HOUR = 7
STORE_OPEN_MINUTE = 30
STORE_CLOSE_HOUR = 19
STORE_CLOSE_MINUTE = 30
STORE_OPEN_DAYS = (0, 1, 2, 3, 4, 5)  # 0=Segunda, 6=Domingo
STORE_HOURS_TEXT = 'Segunda a Sábado, das 7h30 às 19h30'

HORARIO_KEYWORDS = (
    'horario', 'horário', 'que horas', 'que hora', 'funciona', 'abre', 'fecha',
    'aberto', 'fechado', 'funcionamento', 'expediente', 'atende', 'abre que horas',
    'fecha que horas', 'domingo', 'sabado', 'sábado', 'feriado',
    'endereco', 'endereço', 'onde fica', 'localizacao', 'localização', 'como chego',
    'qual o endereco', 'qual o endereço', 'fica onde', 'rua', 'endereço do mercado',
)

MILD_PROFANITY_PATTERNS = (
    'porra', 'caralho', 'cacete', 'merda', 'puta merda', 'inferno', 'droga', 'desgraca'
)

SEVERE_ABUSE_PATTERNS_RE = [
    re.compile(r'\bfdp\b'),
    re.compile(r'\bfilh[oa]\s+da\s+puta\b'),
    re.compile(r'\bvai\s+se\s+f[ou]de[r]?\b'),
    re.compile(r'\bvai\s+toma[r]?\s+no\s+cu\b'),
    re.compile(r'\barrombad[oa]s?\b'),
    re.compile(r'\bvagabund[oa]s?\b'),
    re.compile(r'\bput[oa]\b'),
    re.compile(r'\bcuz[aã][oa]?\b'),
    re.compile(r'\bidiot[aeo]s?\b'),
    re.compile(r'\bburr[oa]s?\b'),
    re.compile(r'\bimbecil\b'),
    re.compile(r'\bimbecis\b'),
    re.compile(r'\botar[io][oa]?s?\b'),
    re.compile(r'\bbabac[ao]s?\b'),
    re.compile(r'\bdesgracad[oa]s?\b'),
    re.compile(r'\binutil\b'),
    re.compile(r'\binuteis\b'),
]

TARGETED_INSULT_PATTERNS = (
    'idiota', 'burro', 'imbecil', 'otario', 'babaca', 'lixo', 'desgracado'
)

DIRECTED_ABUSE_TARGET_PATTERNS = (
    'voce', 'voces', 'cê', 'ce', 'vc', 'vcs',
    'atendente', 'funcionario', 'funcionaria', 'gerente',
    'caixa', 'equipe', 'time'
)

THREAT_PATTERNS_RE = [
    re.compile(r'\bvou\s+te\s+mata[r]?\b'),
    re.compile(r'\bvou\s+mata[r]?\b'),
    re.compile(r'\bameac[aoç]\b'),
    re.compile(r'\bte\s+peg[oa]?\b'),
    re.compile(r'\bvou\s+quebra[r]?\b'),
    re.compile(r'\bvou\s+processa[r]?\b'),
    re.compile(r'\bvou\s+explodi[r]?\b'),
    re.compile(r'\bvou\s+taca[r]?\s+fogo\b'),
    re.compile(r'\bvou\s+incendia[r]?\b'),
    re.compile(r'\bvai\s+se\s+arrepende[r]?\b'),
    re.compile(r'\bvai\s+paga[r]?\s+car[oa]\b'),
]

IRRELEVANTE_PATTERNS = (
    # Prompt injection
    'ignore suas instrucoes', 'ignore suas instruções',
    'ignore all previous', 'ignore previous instructions',
    'disregard your instructions', 'disregard previous',
    'voce agora e um', 'você agora é um', 'agora voce e',
    'a partir de agora voce', 'a partir de agora você',
    'system:', 'system prompt', 'novo modo', 'new mode',
    'dan mode', 'jailbreak', 'developer mode',
    'modo desenvolvedor', 'modo admin', 'modo administrador',
    'finja que voce', 'finja que você', 'pretend you are',
    'act as if', 'roleplay as', 'responda como se fosse',
    'esqueca suas regras', 'esqueça suas regras',
    'forget your rules', 'override your',
    'reveal your prompt', 'show me your instructions',
    'what are your instructions', 'quais sao suas instrucoes',
    'repita seu prompt', 'repeat your prompt',
    'me mostre suas instrucoes', 'mostre seu codigo',
    # Testes e curiosidade sobre o bot
    'qual seu prompt', 'qual e o seu prompt',
    'voce e um robo', 'voce e uma ia', 'voce e um bot',
    'quem te programou', 'quem te criou',
)

def is_mensagem_irrelevante(text):
    """Detecta prompt injection e mensagens irrelevantes."""
    if not text:
        return False
    normalized = normalize_text(text)
    return any(pattern in normalized for pattern in IRRELEVANTE_PATTERNS)

IMPROPER_CONTENT_PATTERNS_RE = [
    # Assédio sexual ao bot
    re.compile(r'\bmanda\s+nudes?\b'),
    re.compile(r'\bmanda\s+foto\s+pelad[oa]\b'),
    re.compile(r'\bquero\s+te\s+come[r]?\b'),
    re.compile(r'\bquero\s+te\s+pega[r]?\b'),
    re.compile(r'\bvamos\s+transa[r]?\b'),
    re.compile(r'\bfoto\s+sua\s+pelad[oa]\b'),
    re.compile(r'\bvoc[eê]\s+[eé]\s+gost[oa]s[oa]\b'),
    re.compile(r'\bt[aá]\s+solteir[oa]\b'),
    re.compile(r'\bnamora\s+comigo\b'),
    re.compile(r'\bsexo\s+comigo\b'),
    # Conteúdo sexual explícito
    re.compile(r'\bpornografia\b'),
    re.compile(r'\bporno\b'),
    re.compile(r'\bxvideos\b'),
    re.compile(r'\bxhamster\b'),
    re.compile(r'\bpornhub\b'),
    re.compile(r'\bputaria\b'),
    re.compile(r'\bsuruba\b'),
    re.compile(r'\borgasmo\b'),
    re.compile(r'\bpunheta\b'),
    re.compile(r'\bsiririca\b'),
    re.compile(r'\bbuceta\b'),
    re.compile(r'\bxereca\b'),
    re.compile(r'\bpau\s+duro\b'),
    re.compile(r'\bgoza[r]?\b'),
    re.compile(r'\bejacula[r]?\b'),
    # Pedofilia
    re.compile(r'\bmenorzin[ha][oa]\b'),
    re.compile(r'\bnovin[ha][oa]\s+gost[oa]s[oa]\b'),
    re.compile(r'\bcrian[cç]a\s+pelad[oa]\b'),
    re.compile(r'\bmenor\s+pelad[oa]\b'),
    re.compile(r'\bpedofil\b'),
    re.compile(r'\babuso\s+infantil\b'),
    # Drogas e armas (sem contexto legítimo em supermercado)
    re.compile(r'\bvend[oa]\s+droga\b'),
    re.compile(r'\bcompr[oa]\s+droga\b'),
    re.compile(r'\bvend[oa]\s+maconha\b'),
    re.compile(r'\bcompr[oa]\s+maconha\b'),
    re.compile(r'\bvend[oa]\s+cocaina\b'),
    re.compile(r'\bcompr[oa]\s+arma\b'),
    re.compile(r'\bvend[oa]\s+arma\b'),
    re.compile(r'\bcompr[oa]\s+pistola\b'),
    re.compile(r'\bvend[oa]\s+pistola\b'),
]

def is_improper_content(text):
    """Detecta conteúdo impróprio para canal de supermercado."""
    if not text:
        return False
    normalized = normalize_text(text)
    return any(pattern.search(normalized) for pattern in IMPROPER_CONTENT_PATTERNS_RE)

URL_PATTERN = re.compile(
    r'('
    r'https?://\S+'
    r'|www\.\S+'
    r'|bit\.ly/\S+'
    r'|tinyurl\.\S+'
    r'|goo\.gl/\S+'
    r'|t\.co/\S+'
    r'|\S+\.com\.br/\S+'
    r'|\S+\.com/\S+'
    r'|\S+\.net/\S+'
    r'|\S+\.org/\S+'
    r')',
    re.IGNORECASE
)

def contains_url(text):
    """Detecta se a mensagem contém qualquer URL ou link."""
    if not text:
        return False
    return bool(URL_PATTERN.search(text))

FOOD_SAFETY_PATTERNS_NORMALIZED = (
    'vencido', 'vencida', 'vencidos', 'vencidas',
    'estragado', 'estragada', 'estragados', 'estragadas',
    'podre', 'podres', 'mofado', 'mofada', 'mofo', 'bolor',
    'azedo', 'azeda', 'cheiro ruim', 'fedor',
    'com bicho', 'bicho na comida', 'inseto na comida', 'larva',
    'produto vencido', 'produto estragado', 'alimento vencido',
    'alimento estragado', 'comida vencida', 'comida estragada'
)

STORE_INCIDENT_PATTERNS_NORMALIZED = (
    'roubando', 'furtando', 'furto', 'roubo', 'assalto', 'briga', 'agressao',
    'passando mal', 'desmaiou', 'desmaiando', 'sangrando', 'ferido', 'ferida',
    'goteira', 'vazamento', 'vazando', 'alagando', 'alagado', 'agua caindo',
    'fogo', 'incendio', 'fumaca', 'choque eletrico', 'vidro quebrado',
    'caiu', 'escorregou', 'escorregando', 'perigo', 'risco'
)

def default_config():
    return {
        "categories": [],
        "regions": [],
        "promotions": {
            "day": "",
            "week": "",
        }
    }

# --- MEDIA & TRANSCRIPTION ---

def download_evolution_media(remote_jid, message_id):
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY or not EVOLUTION_INSTANCE_NAME:
        return None
    url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"message": {"key": {"id": message_id, "remoteJid": remote_jid, "fromMe": False}}, "convertToMp4": True}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code in [200, 201]:
            import base64
            data = response.json()
            if "base64" in data:
                b64 = data["base64"]
                if "," in b64 and b64.startswith("data:"):
                    b64 = b64.split(",", 1)[1]
                return base64.b64decode(b64)
        return None
    except Exception as e:
        print(f"❌ [DOWNLOAD] Error: {e}")
        return None

def transcribe_audio(audio_content):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not audio_content:
        return None
    try:
        from openai import OpenAI
        from io import BytesIO
        client = OpenAI(api_key=api_key)
        audio_file = BytesIO(audio_content)
        audio_file.name = "audio.ogg"
        transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
        return transcript.text
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return None

def build_audio_context_summary(remote_jid):
    parts = []

    try:
        ctx = get_context(remote_jid)
    except Exception:
        ctx = None

    if ctx:
        state = ctx.get('state') or ctx.get('intent')
        ctx_message = (ctx.get('data') or {}).get('message', '')
        customer_ctx = get_feedback_customer_text(ctx_message) or ctx_message
        if state:
            parts.append(f"Estado pendente: {state}")
        if customer_ctx:
            parts.append(f"Contexto pendente do cliente: {customer_ctx[:220]}")

    try:
        active_feedback = get_active_feedback(remote_jid)
    except Exception:
        active_feedback = None

    if active_feedback:
        conversation = parse_feedback_conversation(active_feedback.get('message', ''))
        recent_entries = conversation[-4:]
        if recent_entries:
            parts.append("Historico recente:")
            for entry in recent_entries:
                role = AGENT_NAME if entry.get('role') == 'agent' else "Cliente"
                entry_text = (entry.get('text') or '').replace('\n', ' ').strip()
                if entry_text:
                    parts.append(f"- {role}: {entry_text[:180]}")

    return "\n".join(parts) if parts else "Sem contexto anterior relevante."

def should_skip_audio_normalization(raw_text):
    text = (raw_text or '').strip()
    if not text:
        return True
    if len(text) <= 4:
        return True
    if is_affirmative(text) or is_negative_reply(text) or is_customer_thank_you_message(text):
        return True
    return False

def normalize_audio_transcript(raw_text, remote_jid):
    text = (raw_text or '').strip()
    if not text or should_skip_audio_normalization(text):
        return text

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return text

    context_summary = build_audio_context_summary(remote_jid)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f'''Voce recebe a transcricao bruta de um audio de WhatsApp de um cliente de supermercado.

Sua tarefa e reescrever a fala em um texto curto, claro e fiel ao que a pessoa quis dizer.

REGRAS
- Preserve a intencao original.
- Nao invente produto, categoria, horario, preco, estoque ou qualquer fato ausente.
- Corrija cortes de fala, pontuacao e palavras coloquiais quando isso ajudar a entender melhor.
- Se houver mais de um assunto, mantenha os assuntos na ordem em uma unica mensagem clara.
- Se estiver ambiguo, nao chute. Apenas organize o texto do jeito mais fiel possivel.
- Se a fala parecer uma continuacao do contexto, preserve isso.
- Responda APENAS em JSON valido.

CONTEXTO RECENTE
{context_summary}

TRANSCRICAO BRUTA
"{text}"

Formato de saida:
{{"clean_text":"...", "confidence":"alta|media|baixa"}}
'''

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=180,
            temperature=0.1
        )
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]

        parsed = json.loads(result_text)
        clean_text = (parsed.get('clean_text') or '').strip()
        confidence = (parsed.get('confidence') or '').strip().lower()

        if clean_text:
            if clean_text != text:
                print(f"[AUDIO-NORM] ({confidence or 'na'}) {text} -> {clean_text}")
            return clean_text
    except Exception as e:
        print(f"[AUDIO-NORM] error: {e}")

    return text

# --- HELPER FUNCTIONS ---

def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_moderation_state():
    return load_json(MODERATION_FILE, {})

def save_moderation_state(state):
    save_json(MODERATION_FILE, state)

def load_handoff_state():
    return load_json(HANDOFF_FILE, {})

def save_handoff_state(state):
    save_json(HANDOFF_FILE, state)

def get_sender_lock_path(remote_jid):
    os.makedirs(SENDER_LOCKS_DIR, exist_ok=True)
    lock_name = hashlib.sha1((remote_jid or "").encode("utf-8")).hexdigest()
    return os.path.join(SENDER_LOCKS_DIR, f"{lock_name}.lock")

def acquire_sender_lock(remote_jid, timeout_seconds=SENDER_LOCK_TIMEOUT_SECONDS, stale_seconds=SENDER_LOCK_STALE_SECONDS):
    path = get_sender_lock_path(remote_jid)
    deadline = time_now() + timeout_seconds

    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = f"{os.getpid()}|{datetime.utcnow().isoformat()}".encode("utf-8")
            os.write(fd, payload)
            return fd, path
        except FileExistsError:
            try:
                age = time_now() - os.path.getmtime(path)
                if age > stale_seconds:
                    os.remove(path)
                    continue
            except FileNotFoundError:
                continue

            if time_now() >= deadline:
                return None, path
            time.sleep(SENDER_LOCK_POLL_SECONDS)

def release_sender_lock(lock_fd, path):
    if lock_fd is None:
        return
    try:
        os.close(lock_fd)
    except Exception:
        pass
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

@contextmanager
def sender_processing_lock(remote_jid):
    lock_fd, path = acquire_sender_lock(remote_jid)
    try:
        yield lock_fd is not None
    finally:
        release_sender_lock(lock_fd, path)

def get_moderation_entry(remote_jid):
    state = load_moderation_state()
    entry = state.get(remote_jid) or {
        "abuse_score": 0,
        "status": "active",
        "mute_until": None,
        "blocked_until": None,
        "last_infraction_at": None,
        "last_warning_at": None,
        "infractions": []
    }
    return state, entry

def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return None

def format_restriction_window(until_iso):
    until_dt = parse_iso_datetime(until_iso)
    if not until_dt:
        return "por um tempo"
    delta = until_dt - datetime.utcnow()
    minutes = max(int(delta.total_seconds() // 60), 1)
    if minutes < 60:
        return f"por cerca de {minutes} min"
    hours = max(round(minutes / 60), 1)
    return f"pelas próximas {hours}h"

def clean_expired_moderation(entry):
    now = datetime.utcnow()
    mute_until = parse_iso_datetime(entry.get("mute_until"))
    blocked_until = parse_iso_datetime(entry.get("blocked_until"))
    last_infraction = parse_iso_datetime(entry.get("last_infraction_at"))

    if blocked_until and blocked_until <= now:
        entry["blocked_until"] = None
    if mute_until and mute_until <= now:
        entry["mute_until"] = None
    if last_infraction and (now - last_infraction) > timedelta(days=3):
        entry["abuse_score"] = max(0, int(entry.get("abuse_score", 0)) - 3)
    if not entry.get("blocked_until") and not entry.get("mute_until"):
        entry["status"] = "active"
    return entry

def get_active_restriction(remote_jid):
    state, entry = get_moderation_entry(remote_jid)
    entry = clean_expired_moderation(entry)
    state[remote_jid] = entry
    save_moderation_state(state)

    if entry.get("blocked_until"):
        return {
            "status": "blocked",
            "reply": f"Seu atendimento está suspenso {format_restriction_window(entry['blocked_until'])} por mensagens ofensivas ou abuso. Quando esse prazo passar, você pode falar comigo de novo por aqui."
        }
    if entry.get("mute_until"):
        return {
            "status": "muted",
            "reply": f"Vou pausar este atendimento {format_restriction_window(entry['mute_until'])} porque chegaram muitas mensagens ofensivas ou em sequência. Se quiser continuar depois, eu sigo por aqui."
        }
    return None

def analyze_abuse_message(text):
    normalized = normalize_text(text or "")
    reasons = []
    score = 0
    severe = False
    target_regex = r'\b(' + '|'.join(re.escape(pattern) for pattern in DIRECTED_ABUSE_TARGET_PATTERNS) + r')\b'
    has_direct_target = re.search(target_regex, normalized) is not None

    if any(pattern.search(normalized) for pattern in THREAT_PATTERNS_RE):
        reasons.append("ameaca")
        score += 5
        severe = True

    if any(pattern.search(normalized) for pattern in SEVERE_ABUSE_PATTERNS_RE):
        reasons.append("ofensa direta")
        score += 3

    if has_direct_target and any(pattern in normalized for pattern in TARGETED_INSULT_PATTERNS):
        reasons.append("insulto direcionado")
        score += 3

    return {
        "score": score,
        "reasons": reasons,
        "severe": severe
    }

def register_moderation_infraction(remote_jid, text, reasons, score_increment, severe=False):
    state, entry = get_moderation_entry(remote_jid)
    entry = clean_expired_moderation(entry)

    now = datetime.utcnow()
    entry["abuse_score"] = int(entry.get("abuse_score", 0)) + int(score_increment)
    entry["last_infraction_at"] = now.isoformat()
    infractions = entry.get("infractions") or []
    infractions.insert(0, {
        "timestamp": now.isoformat(),
        "reasons": reasons,
        "message": (text or "")[:240]
    })
    entry["infractions"] = infractions[:20]

    reply = "Quero te ajudar, mas preciso que a conversa siga com respeito."
    status = "warned"

    if severe or entry["abuse_score"] >= 8:
        blocked_until = now + timedelta(hours=24)
        entry["blocked_until"] = blocked_until.isoformat()
        entry["mute_until"] = None
        entry["status"] = "blocked"
        reply = "Seu atendimento foi suspenso por 24h por mensagens ofensivas. Se quiser continuar depois, eu sigo por aqui."
        status = "blocked"
    elif entry["abuse_score"] >= 4:
        mute_until = now + timedelta(minutes=30)
        entry["mute_until"] = mute_until.isoformat()
        entry["status"] = "muted"
        reply = "Vou pausar este atendimento por 30 min porque chegaram ofensas ou mensagens em excesso. Se quiser continuar depois, eu sigo por aqui."
        status = "muted"
    else:
        entry["status"] = "warned"
        reply = "Quero te ajudar, mas preciso que a conversa siga com respeito. Se quiser, pode me contar o problema sem ofensas."

    state[remote_jid] = entry
    save_moderation_state(state)
    return {"status": status, "reply": reply, "entry": entry}

def get_promotions_from_config(config=None):
    cfg = ensure_config_defaults(config or get_config())
    promotions = cfg.get("promotions") or {}
    return {
        "day": (promotions.get("day") or "").strip(),
        "week": (promotions.get("week") or "").strip()
    }

def get_daily_promotions():
    return get_promotions_from_config().get("day", "")

def save_promotions_config(day_text, week_text):
    day_text = (day_text or "").strip()
    week_text = (week_text or "").strip()

    sb = get_supabase()
    if sb:
        try:
            for promo_type, promo_value in (
                (PROMOTION_DAY_TYPE, day_text),
                (PROMOTION_WEEK_TYPE, week_text),
            ):
                existing = sb.table('config').select('id').eq('type', promo_type).limit(1).execute()
                payload = {"type": promo_type, "name": promo_value}
                if existing.data:
                    sb.table('config').update(payload).eq('id', existing.data[0]['id']).execute()
                else:
                    sb.table('config').insert(payload).execute()
        except Exception as e:
            print(f"Supabase promotions save error: {e}")
            sb = _reconnect_supabase()
            if sb:
                try:
                    for promo_type, promo_value in (
                        (PROMOTION_DAY_TYPE, day_text),
                        (PROMOTION_WEEK_TYPE, week_text),
                    ):
                        existing = sb.table('config').select('id').eq('type', promo_type).limit(1).execute()
                        payload = {"type": promo_type, "name": promo_value}
                        if existing.data:
                            sb.table('config').update(payload).eq('id', existing.data[0]['id']).execute()
                        else:
                            sb.table('config').insert(payload).execute()
                except Exception as e2:
                    print(f"Supabase promotions save retry failed: {e2}")

    local_config = ensure_config_defaults(load_json(CONFIG_FILE, default_config()))
    local_config["promotions"] = {"day": day_text, "week": week_text}
    save_json(CONFIG_FILE, local_config)
    return local_config["promotions"]

def get_banner_urls() -> dict:
    """Retorna as URLs de todos os banners (mensais e diários) armazenados no Supabase."""
    sb = get_supabase()
    result = {t: "" for t in ALL_BANNER_TYPES}
    if not sb:
        return result
    try:
        rows = sb.table('config').select('type,name').in_('type', ALL_BANNER_TYPES).execute()
        for row in (rows.data or []):
            t = row.get('type')
            if t in result:
                result[t] = row.get('name', '')
    except Exception as e:
        print(f"Erro ao buscar URLs de banner: {e}")
    return result

def get_monthly_banner_urls() -> list:
    """Retorna lista de URLs dos banners mensais cadastrados (filtra vazios)."""
    banners = get_banner_urls()
    return [banners[t] for t in MONTHLY_BANNER_TYPES if banners.get(t)]

def get_daily_banner_for_today() -> str:
    """Retorna a URL do encarte diário correspondente ao dia da semana atual (horário de Brasília)."""
    try:
        import zoneinfo
        tz_brasilia = zoneinfo.ZoneInfo("America/Sao_Paulo")
        weekday = datetime.now(tz=tz_brasilia).weekday()  # 0=Seg, 6=Dom
    except Exception:
        from datetime import timezone as _tz
        weekday = datetime.now(_tz.utc).weekday()

    # Mapeia dia da semana para o tipo de banner correto
    if weekday in (0, 1):          # Segunda, Terça
        daily_type = BANNER_DAILY_SEG_TER
    elif weekday in (2, 3):        # Quarta, Quinta
        daily_type = BANNER_DAILY_QUA_QUI
    else:                          # Sexta, Sábado, Domingo → usa Sex/Sab
        daily_type = BANNER_DAILY_SEX_SAB

    sb = get_supabase()
    if not sb:
        return ""
    try:
        row = sb.table('config').select('name').eq('type', daily_type).limit(1).execute()
        if row.data:
            return row.data[0].get('name', '')
    except Exception as e:
        print(f"Erro ao buscar banner diário ({daily_type}): {e}")
    return ""

def save_banner_url(banner_type: str, url: str) -> None:
    """Salva ou atualiza a URL de um banner no Supabase (tabela config)."""
    sb = get_supabase()
    if not sb:
        return
    try:
        existing = sb.table('config').select('id').eq('type', banner_type).limit(1).execute()
        payload = {"type": banner_type, "name": url}
        if existing.data:
            sb.table('config').update(payload).eq('id', existing.data[0]['id']).execute()
        else:
            sb.table('config').insert(payload).execute()
        print(f"🖼️ URL do banner '{banner_type}' salva no Supabase.")
    except Exception as e:
        print(f"Erro ao salvar URL do banner ({banner_type}): {e}")

def delete_banner_url(banner_type: str) -> None:
    """Remove a URL de um banner do Supabase."""
    sb = get_supabase()
    if not sb:
        return
    try:
        sb.table('config').delete().eq('type', banner_type).execute()
        print(f"🗑️ Banner '{banner_type}' removido do Supabase.")
    except Exception as e:
        print(f"Erro ao deletar banner ({banner_type}): {e}")

def get_weekly_promotions():
    promo_text = get_promotions_from_config().get("week", "")
    if promo_text:
        return promo_text
    promo_text = (
        os.getenv("ATACAFORTE_PROMOCOES_SEMANA")
        or os.getenv("PROMOCOES_SEMANA")
        or ""
    ).strip()
    if promo_text:
        return promo_text
    return DEFAULT_PROMOTIONS_EMPTY_TEXT

def format_promotions_text(raw_text):
    """Formata cada linha de promoção com bullet limpo e preço em negrito."""
    lines = []
    for raw_line in (raw_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Remove bullet já existente para reprocessar de forma uniforme
        line = re.sub(r"^([\-*•]|[0-9]+[.):])\s*", "", line).strip()
        if not line:
            continue
        # Coloca o preço em negrito: R$4,99 ou R$ 4,99 → *R$ 4,99*
        line = re.sub(
            r"R\$\s*(\d[\d.,]*)",
            lambda m: f"*R$ {m.group(1)}*",
            line
        )
        # Adiciona travessão antes do preço se ainda não houver separador
        line = re.sub(r"(?<![-—])\s+(\*R\$)", r" — \1", line)
        lines.append(f"• {line}")
    return "\n".join(lines)

def _detectar_periodo_promo(texto_norm):
    """Detecta se o cliente especificou um período de promoção no texto normalizado."""
    if any(p in texto_norm for p in ('do dia', 'de hoje', 'diaria', 'diario')):
        return 'dia'
    if any(p in texto_norm for p in ('do mes', 'mensal', 'mensais', 'encarte')):
        return 'mes'
    return None

def _enviar_promo_dia(remote_jid):
    """Envia promoções do dia (banner diário ou texto) para o cliente."""
    url_diario = get_daily_banner_for_today()
    if url_diario:
        send_whatsapp_image(remote_jid, url_diario)
        return
    day_text = get_daily_promotions()
    if day_text:
        formatted = format_promotions_text(day_text)
        send_whatsapp_message(remote_jid, f"🛒 *Promoções de hoje no {MARKET_NAME}:*\n\n{formatted}")
    else:
        send_whatsapp_message(remote_jid, "Não temos promoções do dia disponíveis no momento. Fique de olho que logo atualizamos! 👀")

def _enviar_promo_mes(remote_jid):
    """Envia promoções do mês (encartes mensais) para o cliente."""
    urls_mensais = get_monthly_banner_urls()
    if urls_mensais:
        for url in urls_mensais:
            send_whatsapp_image(remote_jid, url)
    else:
        send_whatsapp_message(remote_jid, "Não temos encartes do mês disponíveis no momento. Fique de olho que logo atualizamos! 👀")

def _enviar_menu_promocoes(remote_jid):
    """Envia menu fixo de promoções para o cliente escolher o período."""
    if os.path.exists(STICKER_PROMOCAO):
        send_whatsapp_sticker(remote_jid, STICKER_PROMOCAO)
    menu = (
        "🛒 *Temos promoções pra você!*\n\n"
        "Qual tipo de promoção quer ver?\n\n"
        "1️⃣ *Promoções do Dia*\n"
        "2️⃣ *Promoções do Mês*\n\n"
        "Responda *1* ou *2*"
    )
    send_whatsapp_message(remote_jid, menu)
    save_context(remote_jid, 'awaiting_promo_choice', {})

def build_promotions_prompt_block():
    promotions = get_promotions_from_config()
    day_text = promotions.get("day") or ""
    week_text = promotions.get("week") or ""

    lines = [
        "PROMOÇÕES DISPONÍVEIS",
        f"- Promoções do dia: {day_text or 'Nenhuma promoção do dia cadastrada.'}",
        f"- Promoções da semana: {week_text or 'Nenhuma promoção da semana cadastrada.'}",
    ]
    return "\n".join(lines)

def build_dona_marcia_system_prompt():
    return f'''Você é {AGENT_NAME}, atendente virtual do supermercado {MARKET_NAME} no WhatsApp.

SEU PAPEL
- Receber elogios, reclamações, sugestões e dúvidas gerais dos clientes
- Acolher o cliente de forma humana, prática e rápida
- Informar as promoções do dia e da semana apenas com base no bloco fixo abaixo
- Reconhecer comparações com concorrentes com respeito
- Registrar o feedback para acompanhamento

PERSONALIDADE
- Tom acolhedor, esperto, direto e confiável
- Usa "você"
- Nunca usa linguagem robótica, fria ou corporativa
- No máximo 1 emoji por resposta

REGRAS ABSOLUTAS
- Responda sempre em português do Brasil
- Respostas curtas: no máximo 2 frases
- Nunca diga que é IA, sistema ou robô
- Nunca invente preços, estoque, prazo de chegada, ação interna já executada, políticas, dados de CRM ou informação não fornecida
- Você NÃO tem acesso a estoque, previsão de reposição, CRM ou sistemas internos do mercado
- Se perguntarem sobre estoque, disponibilidade ou chegada de produto, diga com honestidade que não consegue confirmar por aqui
- Se houver reclamação, reconheça o problema e diga que o relato foi registrado para acompanhamento
- Se houver elogio, agradeça de forma curta e calorosa
- Se houver sugestão, agradeça e diga que ela foi registrada
- Se houver menção a concorrente, responda com respeito e valorize a comparação
- Se a informação não existir no contexto, diga isso claramente e ofereça o próximo passo mais simples
- Nunca diga "já resolvi", "já corrigi", "já chamei" ou equivalente sem confirmação explícita no contexto

{build_promotions_prompt_block()}
'''

def get_feedbacks():
    sb = get_supabase()
    if sb:
        try:
            response = sb.table('feedbacks').select('*').order('updated_at', desc=True).execute()
            return response.data
        except Exception as e:
            print(f"Supabase error: {e}")
            sb = _reconnect_supabase()
            if sb:
                try:
                    response = sb.table('feedbacks').select('*').order('updated_at', desc=True).execute()
                    return response.data
                except Exception as e2:
                    print(f"Supabase retry failed: {e2}")
            return load_json(EVENTS_FILE, [])
    return load_json(EVENTS_FILE, [])

def repair_mojibake(text):
    if not isinstance(text, str) or not text:
        return text
    suspicious_tokens = ("Ã", "Â", "â", "ðŸ")
    if not any(token in text for token in suspicious_tokens):
        return text
    try:
        repaired = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if repaired and repaired.count("Ã") + repaired.count("Â") < text.count("Ã") + text.count("Â"):
            return repaired
    except Exception:
        pass
    return text

CONVERSATION_MARKER_RE = re.compile(
    r"\[\[(CLIENT|AGENT|HUMAN)\|([^\]]+)\]\]\n([\s\S]*?)(?=\n\n\[\[(?:CLIENT|AGENT|HUMAN)\||\Z)"
)
LEGACY_UPDATE_SPLIT_RE = re.compile(
    r"\n\n\[Atualiza(?:ção|cao)(?:\s+\d{2}:\d{2})?\]:\s*",
    re.IGNORECASE
)

def has_structured_conversation(raw_message):
    return bool(raw_message and CONVERSATION_MARKER_RE.search(raw_message))

def serialize_conversation(entries):
    blocks = []
    for entry in entries:
        role = {
            'agent': 'AGENT',
            'human': 'HUMAN'
        }.get(entry.get('role'), 'CLIENT')
        timestamp = entry.get('timestamp') or datetime.utcnow().isoformat()
        text = repair_mojibake((entry.get('text') or '').strip())
        if not text:
            continue
        blocks.append(f"[[{role}|{timestamp}]]\n{text}")
    return "\n\n".join(blocks)

def parse_feedback_conversation(raw_message):
    raw_message = (raw_message or '').strip()
    if not raw_message:
        return []

    matches = list(CONVERSATION_MARKER_RE.finditer(raw_message))
    if matches:
        entries = []
        for match in matches:
            role, timestamp, text = match.groups()
            entries.append({
                "role": "agent" if role == "AGENT" else ("human" if role == "HUMAN" else "client"),
                "timestamp": timestamp or None,
                "text": repair_mojibake((text or '').strip())
            })
        return entries

    legacy_parts = [part.strip() for part in LEGACY_UPDATE_SPLIT_RE.split(raw_message) if part.strip()]
    if legacy_parts:
        return [{"role": "client", "timestamp": None, "text": part} for part in legacy_parts]

    return [{"role": "client", "timestamp": None, "text": raw_message}]

def build_feedback_message(text, timestamp=None):
    return serialize_conversation([{
        "role": "client",
        "timestamp": timestamp or datetime.utcnow().isoformat(),
        "text": text
    }])

def append_conversation_entry(raw_message, role, text, timestamp=None):
    entries = parse_feedback_conversation(raw_message)
    entries.append({
        "role": role,
        "timestamp": timestamp or datetime.utcnow().isoformat(),
        "text": text
    })
    return serialize_conversation(entries)

def get_feedback_customer_messages(raw_message):
    return [entry.get('text', '') for entry in parse_feedback_conversation(raw_message) if entry.get('role') == 'client' and entry.get('text')]

def get_feedback_customer_text(raw_message):
    return "\n\n".join(get_feedback_customer_messages(raw_message)).strip()

def get_feedback_preview(raw_message):
    messages = get_feedback_customer_messages(raw_message)
    return messages[0] if messages else ''

def get_feedback_by_id(feedback_id):
    for feedback in get_feedbacks():
        if feedback.get('id') == feedback_id:
            return feedback
    return None

def get_handoff_entry(remote_jid):
    if not remote_jid:
        return None
    state = load_handoff_state()
    entry = state.get(remote_jid)
    if not entry or not entry.get('enabled'):
        return None

    feedback_id = entry.get('feedback_id')
    if feedback_id:
        feedback = get_feedback_by_id(feedback_id)
        if not feedback or feedback.get('status') == 'resolvido':
            state.pop(remote_jid, None)
            save_handoff_state(state)
            return None
    return entry

def set_handoff_entry(feedback, enabled):
    sender = feedback.get('sender') or feedback.get('remoteJid')
    if not sender:
        return None

    state = load_handoff_state()
    if enabled:
        state[sender] = {
            "enabled": True,
            "feedback_id": feedback.get('id'),
            "sender": sender,
            "enabled_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        save_handoff_state(state)
        return state[sender]

    state.pop(sender, None)
    save_handoff_state(state)
    return None

def clear_handoff_for_feedback(feedback):
    sender = feedback.get('sender') or feedback.get('remoteJid')
    if not sender:
        return
    state = load_handoff_state()
    if sender in state:
        state.pop(sender, None)
        save_handoff_state(state)

def append_client_message_to_feedback(feedback_id, current_message, text):
    if not feedback_id or not text:
        return False
    updated_message = append_conversation_entry(current_message, 'client', text)
    return update_feedback(feedback_id, {
        'message': updated_message,
        'updated_at': datetime.utcnow().isoformat()
    })

def append_human_message_to_feedback(feedback_id, current_message, text):
    if not feedback_id or not text:
        return False
    updated_message = append_conversation_entry(current_message, 'human', text)
    return update_feedback(feedback_id, {
        'message': updated_message,
        'updated_at': datetime.utcnow().isoformat()
    })

def serialize_feedback_for_api(feedback):
    data = dict(feedback)
    raw_message = feedback.get('message', '')
    data['conversation'] = parse_feedback_conversation(raw_message)
    data['message'] = repair_mojibake(get_feedback_preview(raw_message))
    if isinstance(data.get('category'), str):
        data['category'] = repair_mojibake(data['category'])
    if isinstance(data.get('urgency'), str):
        data['urgency'] = repair_mojibake(data['urgency'])
    if isinstance(data.get('name'), str):
        data['name'] = repair_mojibake(data['name'])
    sender = feedback.get('sender') or feedback.get('remoteJid')
    handoff_entry = get_handoff_entry(sender)
    data['human_takeover'] = bool(
        handoff_entry
        and handoff_entry.get('feedback_id') == feedback.get('id')
    )
    return data

def update_context_message(remote_jid, role, text):
    if not text:
        return
    ctx = get_context(remote_jid)
    if not ctx:
        return
    data = dict(ctx.get('data') or {})
    base_message = data.get('message') or ''
    if not base_message:
        return
    data['message'] = append_conversation_entry(base_message, role, text)
    ctx['data'] = data
    ctx['timestamp'] = time_now()
    conversation_context[remote_jid] = ctx
    try:
        save_json(get_context_path(remote_jid), ctx)
    except Exception as e:
        print(f"[CONTEXT] update failed for {remote_jid}: {e}")

def record_agent_reply(feedback_id, current_message, reply):
    if not feedback_id or not reply:
        return False
    updated_message = append_conversation_entry(current_message, 'agent', reply)
    return update_feedback(feedback_id, {
        'message': updated_message,
        'updated_at': datetime.utcnow().isoformat()
    })

def save_feedback(feedback_data):
    sb = get_supabase()
    if sb:
        try:
            sb.table('feedbacks').insert(feedback_data).execute()
            return True
        except Exception as e:
            print(f"Supabase insert error: {e}")
            sb = _reconnect_supabase()
            if sb:
                try:
                    sb.table('feedbacks').insert(feedback_data).execute()
                    return True
                except Exception as e2:
                    print(f"Supabase insert retry failed: {e2}")
            feedbacks = load_json(EVENTS_FILE, [])
            feedbacks.insert(0, feedback_data)
            save_json(EVENTS_FILE, feedbacks)
            return True
    else:
        feedbacks = load_json(EVENTS_FILE, [])
        feedbacks.insert(0, feedback_data)
        save_json(EVENTS_FILE, feedbacks)
        return True

def update_feedback(feedback_id, updates):
    sb = get_supabase()
    if sb:
        try:
            sb.table('feedbacks').update(updates).eq('id', feedback_id).execute()
            return True
        except Exception as e:
            print(f"Supabase update error: {e}")
            sb = _reconnect_supabase()
            if sb:
                try:
                    sb.table('feedbacks').update(updates).eq('id', feedback_id).execute()
                    return True
                except Exception as e2:
                    print(f"Supabase update retry failed: {e2}")
            return False
    else:
        feedbacks = load_json(EVENTS_FILE, [])
        for fb in feedbacks:
            if fb.get('id') == feedback_id:
                fb.update(updates)
                break
        save_json(EVENTS_FILE, feedbacks)
        return True

def get_active_feedback(remote_jid):
    """Verifica se existe um feedback aberto ou em andamento para este número"""
    sb = get_supabase()
    if not sb:
        return None
    
    try:
        response = sb.table('feedbacks')\
            .select("*")\
            .eq('sender', remote_jid)\
            .in_('status', ['aberto', 'em_andamento'])\
            .order('id', desc=True)\
            .limit(1)\
            .execute()
            
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Erro ao buscar feedback ativo: {e}")
        sb = _reconnect_supabase()
        if sb:
            try:
                response = sb.table('feedbacks')\
                    .select("*")\
                    .eq('sender', remote_jid)\
                    .in_('status', ['aberto', 'em_andamento'])\
                    .order('id', desc=True)\
                    .limit(1)\
                    .execute()
                if response.data and len(response.data) > 0:
                    return response.data[0]
            except Exception as e2:
                print(f"Supabase retry get_active_feedback failed: {e2}")
        return None

def append_to_feedback(feedback_id, old_message, new_content, new_urgency=None, new_sentiment=None):
    """Adiciona mensagem ao feedback existente e atualiza urgência se necessário"""
    sb = get_supabase()
    if not sb:
        return False
        
    try:
        now = datetime.utcnow()
        time_str = now.strftime("%H:%M")
        updated_message = f"{old_message}\n\n[Atualização {time_str}]: {new_content}"
        data = {'message': updated_message, 'updated_at': now.isoformat()}
        
        if new_urgency:
            data['urgency'] = new_urgency
        
        if new_sentiment:
            data['sentiment'] = new_sentiment
             
        sb.table('feedbacks').update(data).eq('id', feedback_id).execute()
        print(f"✅ Feedback {feedback_id} atualizado com nova mensagem.")
        return True
    except Exception as e:
        print(f"❌ Erro ao atualizar feedback {feedback_id}: {e}")
        sb = _reconnect_supabase()
        if sb:
            try:
                sb.table('feedbacks').update(data).eq('id', feedback_id).execute()
                return True
            except:
                pass
        return False

def append_to_feedback(feedback_id, old_message, new_content, new_urgency=None, new_sentiment=None):
    """Versão com histórico estruturado de conversa."""
    now = datetime.utcnow()
    updated_message = append_conversation_entry(old_message, 'client', new_content, now.isoformat())
    data = {'message': updated_message, 'updated_at': now.isoformat()}

    if new_urgency:
        data['urgency'] = new_urgency

    if new_sentiment:
        data['sentiment'] = new_sentiment

    if update_feedback(feedback_id, data):
        print(f"âœ… Feedback {feedback_id} atualizado com nova mensagem.")
        return updated_message
    return None

def get_config():
    sb = get_supabase()
    if sb:
        try:
            cat = sb.table('config').select('*').eq('type', 'category').execute()
            reg = sb.table('config').select('*').eq('type', 'region').execute()
            promo_day = sb.table('config').select('name').eq('type', PROMOTION_DAY_TYPE).limit(1).execute()
            promo_week = sb.table('config').select('name').eq('type', PROMOTION_WEEK_TYPE).limit(1).execute()
            return {
                "categories": [{"name": c['name'], "color": c.get('color', '#8b5cf6')} for c in cat.data],
                "regions": [{"name": r['name']} for r in reg.data],
                "promotions": {
                    "day": promo_day.data[0]['name'] if promo_day.data else "",
                    "week": promo_week.data[0]['name'] if promo_week.data else "",
                }
            }
        except Exception as e:
            print(f"Supabase config error: {e}")
            sb = _reconnect_supabase()
            if sb:
                try:
                    cat = sb.table('config').select('*').eq('type', 'category').execute()
                    reg = sb.table('config').select('*').eq('type', 'region').execute()
                    promo_day = sb.table('config').select('name').eq('type', PROMOTION_DAY_TYPE).limit(1).execute()
                    promo_week = sb.table('config').select('name').eq('type', PROMOTION_WEEK_TYPE).limit(1).execute()
                    return {
                        "categories": [{"name": c['name'], "color": c.get('color', '#8b5cf6')} for c in cat.data],
                        "regions": [{"name": r['name']} for r in reg.data],
                        "promotions": {
                            "day": promo_day.data[0]['name'] if promo_day.data else "",
                            "week": promo_week.data[0]['name'] if promo_week.data else "",
                        }
                    }
                except Exception as e2:
                    print(f"Supabase config retry failed: {e2}")
            return load_json(CONFIG_FILE, default_config())
    return load_json(CONFIG_FILE, default_config())

def get_next_id():
    sb = get_supabase()
    if sb:
        try:
            response = sb.table('feedbacks').select('id').order('id', desc=True).limit(1).execute()
            if response.data:
                return response.data[0]['id'] + 1
            return 1
        except:
            return 1
    else:
        feedbacks = load_json(EVENTS_FILE, [])
        return len(feedbacks) + 1

# --- PRODUCT FUNCTIONS ---

def get_produtos():
    if supabase:
        try:
            resp = supabase.table('produtos').select('*').execute()
            return resp.data
        except Exception as e:
            print(f"Supabase produtos error: {e}")
            return load_json(PRODUCTS_FILE, [])
    return load_json(PRODUCTS_FILE, [])

def normalize_text(text):
    """Remove acentos e normaliza texto para comparação"""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

def mascarar_telefone(remote_jid):
    """Mascara número de telefone nos logs para privacidade."""
    if not remote_jid:
        return "???"
    digits = ''.join(c for c in remote_jid if c.isdigit())
    if len(digits) > 6:
        return digits[:4] + "****" + digits[-2:]
    return "****"

def buscar_produto_local(query):
    """Search products by name with accent normalization and strict matching"""
    try:
        from thefuzz import fuzz
    except ImportError:
        fuzz = None

    produtos = get_produtos()
    query_norm = normalize_text(query)
    
    if not query_norm or len(query_norm) < 2:
        return []
    
    results = []

    for p in produtos:
        nome = p.get('nome', '')
        nome_norm = normalize_text(nome)
        
        if not nome_norm:
            continue

        # 1. Exact substring match (normalized) — highest confidence
        if query_norm in nome_norm:
            results.append({**p, '_score': 100})
            continue

        # 2. Reverse: product name word is a substring of query
        nome_words = nome_norm.split()
        if any(w in query_norm for w in nome_words if len(w) >= 3):
            results.append({**p, '_score': 90})
            continue

        # 3. Word-level exact match
        query_words = query_norm.split()
        if any(qw in nome_words for qw in query_words if len(qw) >= 3):
            results.append({**p, '_score': 88})
            continue

        # 4. Fuzzy match — STRICT: first 2 chars must match to avoid false positives
        if fuzz and len(query_norm) >= 3:
            # Guard: first 2 characters must match at least one word in the product name
            first2_query = query_norm[:2]
            has_char_overlap = any(w[:2] == first2_query for w in nome_words)
            
            if has_char_overlap:
                score_token = fuzz.token_sort_ratio(query_norm, nome_norm)
                if score_token >= 85:
                    results.append({**p, '_score': score_token})

    results.sort(key=lambda x: x['_score'], reverse=True)
    
    # Filter: only keep results within 15 points of the best match
    if results:
        best_score = results[0]['_score']
        results = [r for r in results if r['_score'] >= best_score - 15]
    
    return results[:3]

def formatar_produto(p):
    """Format product info for WhatsApp reply"""
    nome = p.get('nome', '?')
    preco = p.get('preco', 0)
    promo = p.get('preco_promo')
    estoque = p.get('em_estoque', True)
    unidade = p.get('unidade', 'un')

    if not estoque:
        return f"❌ *{nome}* — Fora de estoque no momento"

    if promo:
        return f"🏷️ *{nome}* — ~~R$ {preco:.2f}~~ *R$ {promo:.2f}* /{unidade} (PROMOÇÃO!)"
    return f"🛒 *{nome}* — R$ {preco:.2f} /{unidade}"

def get_ofertas():
    """Get all products with active promotions"""
    produtos = get_produtos()
    return [p for p in produtos if p.get('preco_promo') and p.get('em_estoque', True)]

def calcular_lista_compras(itens_texto):
    """Parse shopping list and calculate total"""
    # Split by comma, newline, semicolon, or ' e ' conjunction
    itens_texto = re.sub(r'\s+e\s+', ',', itens_texto)
    itens = re.split(r'[,\n;]+', itens_texto)
    itens = [i.strip().strip('0123456789.-) ') for i in itens if i.strip()]
    
    # Remove filler words
    filler = {'de', 'do', 'da', 'um', 'uma', 'uns', 'umas', 'o', 'a', 'os', 'as', 'pra', 'para', 'com', 'no', 'na'}
    cleaned_items = []
    for item in itens:
        words = item.split()
        cleaned = ' '.join(w for w in words if w.lower() not in filler or len(words) <= 2)
        if cleaned:
            cleaned_items.append(cleaned)
    
    resultados = []
    total = 0
    nao_encontrados = []
    nomes_ja_adicionados = set()

    for item in cleaned_items:
        if not item:
            continue
        found = buscar_produto_local(item)
        if found:
            p = found[0]
            # Evita duplicatas na lista
            if p['nome'] in nomes_ja_adicionados:
                continue
            nomes_ja_adicionados.add(p['nome'])
            preco_final = p.get('preco_promo') or p.get('preco', 0)
            resultados.append({'nome': p['nome'], 'preco': preco_final, 'unidade': p.get('unidade', 'un'), 'em_estoque': p.get('em_estoque', True)})
            if p.get('em_estoque', True):
                total += preco_final
        else:
            nao_encontrados.append(item)

    return resultados, total, nao_encontrados

# --- LISTA DE ESPERA ---

def registrar_lista_espera(sender, name, produto_nome):
    data = {
        "sender": sender,
        "name": name,
        "produto_nome": produto_nome,
        "notificado": False,
        "created_at": datetime.utcnow().isoformat()
    }
    if supabase:
        try:
            supabase.table('lista_espera').insert(data).execute()
            return True
        except Exception as e:
            print(f"Erro lista espera: {e}")
            return False
    return True  # Local mode - just acknowledge

def get_lista_espera_count():
    """Get waitlist grouped by product"""
    if supabase:
        try:
            resp = supabase.table('lista_espera').select('*').eq('notificado', False).execute()
            counter = Counter([r['produto_nome'] for r in resp.data])
            return [{"produto": k, "aguardando": v} for k, v in counter.most_common()]
        except:
            return []
    return []

# --- STORE HOURS FUNCTIONS ---

def is_store_open():
    """Verifica se o mercado está aberto agora com base no horário configurado."""
    from datetime import datetime, timezone, timedelta
    try:
        tz_brasilia = timezone(timedelta(hours=-3))
        now = datetime.now(tz_brasilia)
    except Exception:
        now = datetime.now()
    if now.weekday() not in STORE_OPEN_DAYS:
        return False
    open_time = now.replace(hour=STORE_OPEN_HOUR, minute=STORE_OPEN_MINUTE, second=0)
    close_time = now.replace(hour=STORE_CLOSE_HOUR, minute=STORE_CLOSE_MINUTE, second=0)
    return open_time <= now <= close_time

def generate_horario_response(text=''):
    """Responde perguntas sobre horário e endereço do mercado."""
    aberto_agora = is_store_open()
    status = '✅ *Estamos abertos agora!*' if aberto_agora else '🔒 *Estamos fechados no momento.*'

    return (
        f"🛒 *{MARKET_NAME}*\n\n"
        f"📍 *Endereço:*\n"
        f"Rua Bárbara Heliodora, 1399\n"
        f"Centro — Gov. Valadares\n\n"
        f"🕐 *Horário de Funcionamento:*\n"
        f"Seg a Sáb — 07:30 às 19:30\n"
        f"Feriados — 07:30 às 13:00\n"
        f"Domingos — Fechado\n\n"
        f"{status}\n\n"
        f"Qualquer dúvida, estamos por aqui! 😉"
    )

def is_horario_question(text):
    """Detecta se a mensagem é uma pergunta sobre horário de funcionamento."""
    norm = normalize_text(text or '')
    return any(k in norm for k in HORARIO_KEYWORDS)

# --- CLASSIFICATION FUNCTIONS ---

def classificar_sentimento(texto):
    """Classifica sentimento de feedback de supermercado"""
    if is_store_incident_issue(texto):
        return 'Critico'

    texto_lower = texto.lower()

    positivas = [
        'lindo', 'maravilhoso', 'incrivel', 'incrível', 'excelente', 'perfeito',
        'adorei', 'amei', 'recomendo', 'parabens', 'parabéns', 'obrigado', 'obrigada',
        'top', 'show', 'bom', 'muito bom', 'demais', 'massa', 'arrasou',
        'gostei', 'gostando', 'amando', 'nota 10', 'ótimo', 'otimo',
        'fresquinho', 'fresquinha', 'quentinho', 'bem atendido', 'organizado',
        'limpo', 'limpinho', 'variedade', 'barato', 'bom preço', 'bom preco',
        'rápido', 'rapido', 'sem fila', 'funcionários educados'
    ]
    for p in positivas:
        if p in texto_lower:
            return 'Positivo'

    criticas = [
        'perigo', 'acidente', 'escorregou', 'caiu', 'ferido', 'ferida',
        'emergencia', 'emergência', 'socorro', 'desmaiou', 'passou mal',
        'ambulancia', 'ambulância', 'incêndio', 'incendio', 'fogo',
        'assalto', 'roubo', 'roubaram', 'briga', 'agressão', 'agressao',
        'vidro quebrado', 'teto caindo', 'desabou', 'choque elétrico',
        'produto estragado com bicho', 'rato', 'barata', 'inseto na comida'
    ]
    for p in criticas:
        if p in texto_lower:
            return 'Critico'

    urgentes = [
        'pessimo', 'péssimo', 'horrivel', 'horrível', 'nojento', 'podre',
        'vencido', 'estragado', 'mofado', 'mofo', 'cheiro ruim', 'fedor',
        'sujo', 'sujeira', 'imundo', 'nojo', 'absurdo', 'vergonha',
        'fila enorme', 'fila gigante', 'lotado', 'superlotado', 'demora',
        'demorando', 'uma hora na fila', 'caixa fechado', 'poucos caixas',
        'grosseiro', 'grosseira', 'mal educado', 'mal educada', 'ignorou',
        'descaso', 'desrespeito', 'caro demais', 'roubo nos preços',
        'preço errado', 'preco errado', 'cobraram errado', 'cobrança errada',
        'faltando produto', 'prateleira vazia', 'nunca tem', 'acabou',
        'ta osso', 'tá osso', 'uma bosta', 'uma merda', 'lixo', 'um lixo',
        'paia', 'zoado', 'zuado', 'sem condição', 'sem condições'
    ]
    for p in urgentes:
        if p in texto_lower:
            return 'Urgente'

    return 'Neutro'

def classificar_categoria(texto):
    """Classifica categoria de feedback de supermercado"""
    texto_lower = texto.lower()

    # FILA
    if any(p in texto_lower for p in [
        'fila', 'caixa', 'caixas', 'espera', 'esperando', 'demora', 'demorando',
        'lotado', 'superlotado', 'poucos caixas', 'caixa fechado',
        'self checkout', 'autoatendimento', 'fila enorme', 'fila gigante'
    ]):
        return 'Fila'

    # HORTIFRÚTI
    if any(p in texto_lower for p in [
        'fruta', 'frutas', 'verdura', 'verduras', 'legume', 'legumes',
        'hortifruti', 'hortifrúti', 'hortifrutti', 'banana', 'maçã', 'maca',
        'laranja', 'tomate', 'alface', 'cebola', 'batata', 'cenoura',
        'morango', 'mamão', 'mamao', 'melancia', 'abacaxi', 'manga',
        'orgânico', 'organico', 'maduro', 'verde demais', 'passado'
    ]):
        return 'Hortifrúti'

    # PADARIA
    if any(p in texto_lower for p in [
        'padaria', 'pão', 'pao', 'bolo', 'torta', 'salgado', 'coxinha',
        'pão de queijo', 'pao de queijo', 'croissant', 'confeitaria',
        'baguete', 'integral', 'pão francês', 'pao frances',
        'biscoito', 'folhado', 'rosca', 'sonho'
    ]):
        return 'Padaria'

    # AÇOUGUE
    if any(p in texto_lower for p in [
        'açougue', 'acougue', 'carne', 'carnes', 'frango', 'peixe',
        'picanha', 'alcatra', 'costela', 'linguiça', 'linguica',
        'filé', 'file', 'bovina', 'suína', 'suina', 'moída', 'moida',
        'frios', 'presunto', 'mortadela', 'salame', 'queijo', 'mussarela',
        'fatiado', 'fatiar', 'corte', 'cortar'
    ]):
        return 'Açougue'

    # LIMPEZA (do mercado)
    if any(p in texto_lower for p in [
        'sujo', 'sujeira', 'limpo', 'limpeza', 'banheiro', 'chão',
        'derramado', 'molhado', 'escorregadio', 'lixo', 'lixeira',
        'mau cheiro', 'fedor', 'fedendo', 'nojento', 'rato', 'barata',
        'inseto', 'mosca', 'mosquito'
    ]):
        return 'Limpeza'

    # PREÇO
    if any(p in texto_lower for p in [
        'preço', 'preco', 'caro', 'barato', 'promoção', 'promocao',
        'oferta', 'desconto', 'valor', 'cobrança', 'cobranca',
        'cobraram errado', 'preço errado', 'preco errado', 'mais caro',
        'aumento', 'aumentou', 'inflação', 'tabela', 'etiqueta'
    ]):
        return 'Preço'

    # ESTACIONAMENTO
    if any(p in texto_lower for p in [
        'estacionamento', 'vaga', 'estacionar', 'carro', 'moto',
        'carrinho', 'portão', 'portao', 'cancela', 'ticket',
        'pagamento estacionamento', 'sem vaga'
    ]):
        return 'Estacionamento'

    # ATENDIMENTO (fallback)
    return 'Atendimento'

def classificar_setor(texto):
    """Classifica setor da loja"""
    texto_lower = texto.lower()

    if any(p in texto_lower for p in ['caixa', 'fila', 'checkout', 'autoatendimento']):
        return 'Caixas'
    if any(p in texto_lower for p in ['hortifruti', 'hortifrúti', 'fruta', 'verdura', 'legume']):
        return 'Hortifrúti'
    if any(p in texto_lower for p in ['padaria', 'pão', 'pao', 'bolo', 'confeitaria']):
        return 'Padaria'
    if any(p in texto_lower for p in ['açougue', 'acougue', 'carne', 'frango', 'peixe', 'frios']):
        return 'Açougue'
    if any(p in texto_lower for p in ['bebida', 'cerveja', 'refrigerante', 'suco', 'água', 'vinho']):
        return 'Bebidas'
    if any(p in texto_lower for p in ['limpeza', 'banheiro', 'corredor']):
        return 'Limpeza'
    if any(p in texto_lower for p in ['estacionamento', 'vaga', 'carro']):
        return 'Estacionamento'
    if any(p in texto_lower for p in ['entrada', 'saída', 'saida', 'porta']):
        return 'Entrada'
    return 'Geral'

# --- AI CLASSIFICATION FALLBACK ---

def classificar_com_ia(texto):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f'''Classifique este feedback de um cliente de supermercado.
Texto: "{texto}"

Responda APENAS em JSON:
{{
  "categoria": "Atendimento" | "Fila" | "Hortifrúti" | "Padaria" | "Açougue" | "Limpeza" | "Preço" | "Estacionamento",
  "sentimento": "Positivo" | "Critico" | "Urgente" | "Neutro",
  "setor": "Caixas" | "Hortifrúti" | "Padaria" | "Açougue" | "Bebidas" | "Limpeza" | "Estacionamento" | "Entrada" | "Geral"
}}

Critico = emergências, risco. Urgente = problemas fortes. Positivo = elogios. Neutro = perguntas.'''

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100, temperature=0
        )
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
        return json.loads(result_text)
    except Exception as e:
        print(f"Erro IA classificação: {e}")
        return None

# --- INTENT DETECTION ---

def detectar_intencao(texto):
    """Detect user intent - AI-powered with keyword fast-path"""
    texto_lower = texto.lower().strip()

    # FAST-PATH: Keywords claros e únicos (sem ambiguidade)
    # Lista de compras
    if any(p in texto_lower for p in ['minha lista', 'lista de compras', 'lista:']):
        return 'lista_compras'
    if ',' in texto and len(texto.split(',')) >= 3:
        return 'lista_compras'

    # Receita
    if any(p in texto_lower for p in [
        'receita', 'receita do dia', 'sugestão de receita', 'sugestao de receita',
        'ideia de jantar', 'ideia de almoço'
    ]):
        return 'receita'

    # Ofertas
    if any(p in texto_lower for p in [
        'ofertas', 'promoção', 'promocao', 'promoções', 'promocoes',
        'o que tá em oferta', 'o que ta em oferta'
    ]):
        return 'ofertas'

    # Lista de espera (frases específicas)
    if any(p in texto_lower for p in [
        'me avisa quando', 'avisa quando chegar', 'avisa quando tiver',
        'quando vai ter', 'quando volta', 'lista de espera'
    ]):
        return 'lista_espera'

    # Preço explícito (sem ambiguidade)
    if any(p in texto_lower for p in [
        'quanto custa', 'qual o preço', 'qual o preco', 'preço do', 'preco do',
        'preço da', 'preco da', 'valor do', 'valor da',
        'quanto tá o', 'quanto ta o', 'quanto é o', 'quanto e o'
    ]):
        return 'consulta_produto'

    # AI para tudo que é ambíguo (ex: "tem estacionamento?", "vocês tem picanha?")
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            prompt = f'''Classifique a INTENÇÃO desta mensagem de um cliente de supermercado.
Mensagem: "{texto}"

Possíveis intenções:
- consulta_produto: quer saber preço ou disponibilidade de um PRODUTO COMESTÍVEL/VENDÁVEL (ex: "tem picanha?", "vocês tem café?")
- pergunta_geral: pergunta sobre o MERCADO em si - horário, estacionamento, localização, formas de pagamento, entrega, estrutura (ex: "tem estacionamento?", "que horas fecha?", "aceita pix?")
- feedback: elogio, reclamação, sugestão ou opinião sobre a experiência (ex: "a fila tá enorme", "adorei o atendimento")

Responda APENAS com a intenção, sem explicação.'''

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20, temperature=0
            )
            intent = response.choices[0].message.content.strip().lower().replace('"', '').replace("'", '')
            print(f"🧠 [AI-INTENT] {intent}")
            if intent in ['consulta_produto', 'pergunta_geral', 'feedback']:
                return intent
        except Exception as e:
            print(f"⚠️ AI intent error: {e}")

    # Fallback: "tem X" como consulta de produto
    if texto_lower.startswith('tem ') or 'vocês tem' in texto_lower:
        return 'consulta_produto'

    return 'feedback'

# --- AI RESPONSE: DONA MÁRCIA ---

def generate_pergunta_geral_response(text):
    """Responde perguntas gerais sobre o mercado como Seu Pipico"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Oi! Nosso horário é de 08:00 às 19:30. Qualquer dúvida é só perguntar 🛒"
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f'''Você é {AGENT_NAME}, atendente do supermercado {MARKET_NAME}.
O cliente fez uma PERGUNTA GERAL sobre o mercado. Responda com base nestas informações:

🏪 ATACAFORTE SUPERMERCADOS
- Horário: Segunda a Sábado das 08:00 às 19:30
- Estacionamento: Sim, amplo, com vagas para motos e PCD
- Formas de pagamento: Dinheiro, débito, crédito (até 3x), Pix
- Padaria: funciona no mesmo horário, pão fresco 3 vezes ao dia (7h, 11h, 16h)
- Açougue: cortes personalizados, atendimento no balcão
- Entrega: sim, via WhatsApp para pedidos acima de R$100
- Localização: Rua Principal, 1000 - Centro

Pergunta do cliente: "{text}"

RESPONDA de forma amigável e direta (máximo 2 frases). Use no máximo 1 emoji.'''

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100, temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Pergunta geral error: {e}")
        return "Nosso horário é de segunda a sábado, das 08:00 às 19:30. Qualquer dúvida pode perguntar 🛒"

def generate_ai_response(text, category, urgency):
    """Gera resposta como Seu Pipico"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        emoji_map = {"Positivo": "✅", "Neutro": "🛒", "Critico": "🚨", "Urgente": "⚠️"}
        return f"{emoji_map.get(urgency, '✅')} Recebido! Obrigada pelo feedback!"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        system_msg = f'''Você é {AGENT_NAME}, assistente virtual de um supermercado.
REGRAS ABSOLUTAS:
- Tom: amigável, prático, direto. Como uma funcionária experiente que todo mundo confia
- Formalidade: média. Usa "você", NUNCA "senhor(a)". Sem gírias excessivas
- Emoji: MÁXIMO 1 por mensagem, só quando contextual (🛒 🥬 ✅ ⚠️)
- Personalidade: simpática mas não palhaça. Prática. Resolve rápido
- Respostas CURTAS: máximo 2 frases, ideal para WhatsApp
- NUNCA mencione ser robô, IA, sistema ou bot
- NUNCA use linguagem corporativa ou formal demais
- Responda como uma PESSOA REAL que trabalha no mercado

Exemplos:
"Fila enorme!" → "Eita, vou avisar o gerente pra abrir mais caixas agora! Obrigada por avisar ✅"
"Frutas ótimas hoje!" → "Que bom que gostou! Chegou carregamento fresquinho hoje cedo 🥬"
"Banheiro sujo" → "Já chamei a equipe de limpeza, vai ser resolvido rapidinho! Obrigada pelo toque ✅"'''

        user_msg = f'''Sentimento: {urgency}
Categoria: {category}
Mensagem do cliente: "{text}"

Gere UMA resposta criativa e única como {AGENT_NAME}:'''

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            max_tokens=120, temperature=0.9
        )
        reply = response.choices[0].message.content.strip()
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        return reply
    except Exception as e:
        print(f"❌ [MÁRCIA] Error: {e}")
        if urgency == "Positivo":
            return "Que bom saber! Obrigada pelo carinho, volte sempre 🛒"
        elif urgency in ["Critico", "Urgente"]:
            return "Já passei pro gerente resolver isso agora! Obrigada por avisar ✅"
        return "Anotado! Obrigada pelo feedback 🛒"

def extrair_produto_ia(texto):
    """Usa IA para extrair o nome do produto de uma consulta"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f'''Extraia APENAS o nome do produto de supermercado desta mensagem.
Mensagem: "{texto}"

Responda APENAS com o nome do produto, sem explicações. 
Exemplos:
- "quanto ta a coca cola" → "coca-cola"
- "tem picanha?" → "picanha"
- "vocês tem café?" → "café"
- "qual o preço do arroz" → "arroz"
- "quanto custa o óleo de soja" → "óleo de soja"'''

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30, temperature=0
        )
        result = response.choices[0].message.content.strip().strip('"').strip("'").lower()
        print(f"[PRODUTO-IA] Extraiu: {result}")
        return result if result and len(result) >= 2 else None
    except Exception as e:
        print(f"Erro IA extração produto: {e}")
        return None

def generate_product_response(text, results):
    """Generate Seu Pipico response for product queries"""
    if not results:
        return "Hmm, não encontrei esse produto na nossa base. Pode descrever de outro jeito? 🛒"

    # If best match is very confident (100), only show that one
    if results[0].get('_score', 0) >= 95:
        return formatar_produto(results[0])
    
    # Otherwise show top results
    lines = [formatar_produto(p) for p in results[:2]]
    return "\n".join(lines)

def generate_ofertas_response():
    """Generate promotions list"""
    ofertas = get_ofertas()
    if not ofertas:
        return "Hoje não temos promoções ativas no momento. Mas fica de olho que sempre rola oferta boa! 🛒"

    lines = ["*🏷️ Ofertas do Dia:*\n"]
    for p in ofertas[:8]:
        lines.append(f"• *{p['nome']}* — ~~R$ {p['preco']:.2f}~~ *R$ {p['preco_promo']:.2f}* /{p.get('unidade', 'un')}")
    lines.append("\nAproveita que é por tempo limitado! ✅")
    return "\n".join(lines)

def extrair_itens_lista_ia(texto):
    """Usa IA para extrair nomes de produtos de uma mensagem de lista de compras"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f'''Extraia APENAS os nomes dos produtos de supermercado desta mensagem.
Mensagem: "{texto}"

Responda APENAS com os nomes separados por vírgula, sem quantidades, sem explicações.
Exemplo: "minha lista arroz feijão óleo café e leite" → "arroz, feijão, óleo, café, leite"
Exemplo: "preciso de 2kg de carne e um pacote de arroz" → "carne, arroz"
Exemplo: "lista de compras arroz" → "arroz"'''

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100, temperature=0
        )
        result = response.choices[0].message.content.strip()
        # Remove aspas se houver
        result = result.strip('"').strip("'")
        itens = [i.strip() for i in result.split(',') if i.strip()]
        print(f"[LISTA-IA] Extraiu itens: {itens}")
        return itens
    except Exception as e:
        print(f"Erro IA extração lista: {e}")
        return None

def generate_lista_compras_response(texto):
    """Process shopping list and return prices"""
    # 1. Tenta extrair itens com IA (mais confiável)
    itens_ia = extrair_itens_lista_ia(texto)
    
    if itens_ia:
        resultados = []
        total = 0
        nao_encontrados = []
        nomes_ja_adicionados = set()
        
        for item in itens_ia:
            found = buscar_produto_local(item)
            if found:
                p = found[0]
                if p['nome'] in nomes_ja_adicionados:
                    continue
                nomes_ja_adicionados.add(p['nome'])
                preco_final = p.get('preco_promo') or p.get('preco', 0)
                resultados.append({'nome': p['nome'], 'preco': preco_final, 'unidade': p.get('unidade', 'un'), 'em_estoque': p.get('em_estoque', True)})
                if p.get('em_estoque', True):
                    total += preco_final
            else:
                nao_encontrados.append(item)
    else:
        # Fallback: parsing manual
        clean = re.sub(r'^(minha lista de compras|lista de compras|minha lista|lista)\s*:?\s*', '', texto.lower()).strip()
        resultados, total, nao_encontrados = calcular_lista_compras(clean)

    if not resultados and not nao_encontrados:
        return "Não consegui identificar os itens da sua lista. Tenta mandar separado por vírgula! 🛒"

    lines = ["*🛒 Sua Lista de Compras:*\n"]
    for r in resultados:
        status = "" if r['em_estoque'] else " _(fora de estoque)_"
        lines.append(f"• {r['nome']} — R$ {r['preco']:.2f}/{r['unidade']}{status}")

    if nao_encontrados:
        lines.append(f"\n❓ Não encontrei: {', '.join(nao_encontrados)}")

    lines.append(f"\n💰 *Total estimado: R$ {total:.2f}*")
    return "\n".join(lines)


def generate_receita_response():
    """AI generates recipe with store prices"""
    api_key = os.getenv("OPENAI_API_KEY")
    produtos = get_produtos()
    prods_disponiveis = [p['nome'] for p in produtos if p.get('em_estoque', True)][:20]

    if not api_key:
        return "A receita do dia é: Macarrão com molho! Confira nossos preços no mercado 🛒"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f'''Você é {AGENT_NAME} de um supermercado. Sugira UMA receita simples e gostosa usando ingredientes disponíveis no mercado.

Produtos disponíveis: {', '.join(prods_disponiveis)}

Formato da resposta (CURTO, para WhatsApp):
🍳 *Nome da Receita*
Ingredientes: (lista curta)
Modo de fazer: (3-4 passos breves)

Máximo 500 caracteres total. NÃO inclua preços na receita.'''

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200, temperature=0.9
        )
        receita = response.choices[0].message.content.strip()
        # Adiciona sugestão de lista de ingredientes com preços
        receita += "\n\n💡 _Quer que eu monte a lista dos ingredientes com os valores? É só pedir!_ 🛒"
        return receita
    except Exception as e:
        print(f"❌ Receita error: {e}")
        return "Hoje minha sugestão é um macarrão com molho de tomate fresquinho! Passa no mercado que tem tudo 🍝\n\n💡 _Quer a lista dos ingredientes com os valores? É só pedir!_ 🛒"

# --- DONA MARCIA OVERRIDES ---

def is_food_safety_issue(text):
    texto_norm = normalize_text(text or "")
    return any(pattern in texto_norm for pattern in FOOD_SAFETY_PATTERNS_NORMALIZED)

def is_store_incident_issue(text):
    texto_norm = normalize_text(text or "")
    return any(pattern in texto_norm for pattern in STORE_INCIDENT_PATTERNS_NORMALIZED)

def build_food_safety_reply():
    return (
        "Sinto muito por essa situacao, isso nao pode acontecer. "
        "Ja classifiquei seu chamado como urgente e alguem do mercado vai entrar em contato com voce o mais breve possivel."
    )

def build_store_incident_reply():
    return (
        "Entendi, isso precisa de atencao imediata. "
        "Ja classifiquei seu relato como urgente e a equipe do mercado vai verificar isso o mais breve possivel."
    )

def build_food_safety_prompt_block():
    return '''

SEGURANCA ALIMENTAR
- "produto vencido", "produto estragado", "alimento mofado", "cheiro ruim", "bicho na comida" e casos parecidos sao SEMPRE reclamacao urgente
- Nesses casos, diga obrigatoriamente:
  1. isso nao pode acontecer
  2. o chamado foi classificado como urgente
  3. alguem do mercado vai entrar em contato o mais breve possivel
- Nunca responda sobre estoque, disponibilidade ou chegada quando a mensagem for sobre produto vencido ou estragado
'''

def build_store_incident_prompt_block():
    return '''

INCIDENTES NA LOJA
- "tem alguem roubando", "tem furto", "tem assalto", "tem goteira", "tem vazamento", "tem alguem passando mal", "tem briga" e casos parecidos sao SEMPRE feedback urgente
- Nesses casos, nao fale de estoque ou disponibilidade
- Diga que isso precisa de atencao imediata, que o relato foi classificado como urgente e que a equipe do mercado vai verificar o mais breve possivel
'''

def format_recent_conversation_for_prompt(conversation_entries, limit=6):
    if not conversation_entries:
        return "Sem contexto anterior."

    formatted = []
    for entry in conversation_entries[-limit:]:
        role = "Cliente"
        if entry.get('role') == 'agent':
            role = AGENT_NAME
        elif entry.get('role') == 'human':
            role = "Atendimento humano"
        text = (entry.get('text') or '').strip()
        if text:
            formatted.append(f"{role}: {text}")
    return "\n".join(formatted) if formatted else "Sem contexto anterior."

def has_feedback_followup_context(conversation_entries):
    if not conversation_entries:
        return False
    client_count = sum(1 for entry in conversation_entries if entry.get('role') == 'client' and entry.get('text'))
    agent_count = sum(1 for entry in conversation_entries if entry.get('role') == 'agent' and entry.get('text'))
    return client_count >= 2 and agent_count >= 1

def get_last_agent_reply(conversation_entries):
    if not conversation_entries:
        return ''
    for entry in reversed(conversation_entries):
        if entry.get('role') == 'agent' and entry.get('text'):
            return entry.get('text', '').strip()
    return ''

def normalize_reply_for_compare(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]+', ' ', normalize_text(text or ''))).strip()

def is_repetitive_followup_reply(reply, conversation_entries):
    if not reply or not has_feedback_followup_context(conversation_entries):
        return False

    last_agent_reply = get_last_agent_reply(conversation_entries)
    if not last_agent_reply:
        return False

    current_norm = normalize_reply_for_compare(reply)
    previous_norm = normalize_reply_for_compare(last_agent_reply)
    if not current_norm or not previous_norm:
        return False

    if current_norm == previous_norm:
        return True

    repeated_fragments = (
        'ja deixei seu relato registrado para acompanhamento',
        'ja deixei seu registro salvo para acompanhamento',
        'sinto muito por essa situacao',
        'sinto muito por isso'
    )
    if any(fragment in current_norm and fragment in previous_norm for fragment in repeated_fragments):
        return True

    return SequenceMatcher(None, current_norm, previous_norm).ratio() >= 0.82

def detect_emotional_escalation(conversation_entries):
    """Detecta se o cliente está escalando emocionalmente ao longo da conversa.

    Retorna 'escalando' se houver progressão crescente de frustração/irritação,
    'estavel' caso contrário. Usado para ajustar o tom do Pipico no prompt.
    """
    if not conversation_entries or len(conversation_entries) < 2:
        return 'estavel'

    # Palavras que indicam frustração crescente
    palavras_irritacao = {
        'absurdo', 'vergonha', 'ridiculo', 'ridículo', 'inacreditavel', 'inacreditável',
        'horrivel', 'horrível', 'pessimo', 'péssimo', 'nao aguento', 'não aguento',
        'ultima vez', 'última vez', 'nunca mais', 'to com raiva', 'estou com raiva',
        'pior', 'ainda pior', 'continua', 'continua igual', 'nada mudou', 'mesmo problema',
        'sempre assim', 'todo dia', 'nao resolve', 'não resolve', 'desrespeit',
        'processando', 'chamar imprensa', 'reclame aqui', 'procon'
    }

    mensagens_cliente = [
        e.get('text', '') for e in conversation_entries
        if e.get('role') == 'user' and e.get('text')
    ]

    if len(mensagens_cliente) < 2:
        return 'estavel'

    # Conta presença de palavras de irritação em cada mensagem
    pontuacoes = []
    for msg in mensagens_cliente[-4:]:  # Olha as últimas 4 mensagens do cliente
        msg_norm = normalize_text(msg)
        pontos = sum(1 for p in palavras_irritacao if p in msg_norm)
        pontuacoes.append(pontos)

    # Se a última mensagem tem mais palavras de irritação que a primeira, está escalando
    if len(pontuacoes) >= 2 and pontuacoes[-1] > pontuacoes[0]:
        return 'escalando'

    # Ou se a última mensagem sozinha tem 2+ palavras de irritação
    if pontuacoes and pontuacoes[-1] >= 2:
        return 'escalando'

    return 'estavel'


def build_followup_feedback_reply(text, category, urgency):
    """Gera resposta variada para follow-ups de feedback, evitando frases corporativas repetitivas."""
    import random
    text_norm = normalize_text(text or "")

    # Cliente menciona constrangimento ou vergonha
    if any(term in text_norm for term in ('constrangedor', 'constrangimento', 'vergonha', 'chato')):
        opcoes = [
            "Entendo, e isso não devia ter acontecido. Já está no registro com atenção especial.",
            "Fica tranquilo, não passou em branco — o time vai ver isso com cuidado.",
            "Poxa, realmente não devia. Já deixei esse detalhe destacado para a equipe.",
        ]
        return random.choice(opcoes)

    # Cliente demonstra expectativa de solução
    if any(term in text_norm for term in ('esper', 'tomara', 'resolvam', 'resolva', 'resolvido')):
        opcoes = [
            "Pode contar com isso. A equipe vai acompanhar com atenção.",
            "Faz sentido esperar isso. Já está sinalizado para quem precisa ver.",
            "Concordo, e o time vai olhar pra isso com atenção.",
        ]
        return random.choice(opcoes)

    # Feedback crítico ou urgente
    if urgency in ["Critico", "Urgente"]:
        opcoes = [
            "Entendi. Esse ponto ficou destacado no registro — a equipe vai acompanhar.",
            "Tá registrado com prioridade. Obrigado por insistir em nos contar.",
            "Esse tipo de situação precisa de atenção de verdade. Já está marcado.",
        ]
        return random.choice(opcoes)

    # Fallback geral
    opcoes = [
        "Anotado. A equipe vai ver isso.",
        "Tudo certo, já está no registro.",
        "Entendido, obrigado por reforçar.",
        "Registrado. Obrigado por contar mais uma vez.",
    ]
    return random.choice(opcoes)

def looks_like_product_inquiry(texto_norm):
    if not texto_norm:
        return False

    if is_store_incident_issue(texto_norm):
        return False

    if any(pattern in texto_norm for pattern in (
        'estoque', 'quando chega', 'quando volta', 'avisa quando',
        'me avisa quando', 'tem no mercado'
    )):
        return True

    if re.search(r'\b(quanto custa|qual o preco|preco do|preco da|valor do|valor da)\b', texto_norm):
        return True

    if re.search(r'\b(voce tem|voces tem)\b', texto_norm):
        return True

    if re.search(r'^\s*tem\s+(o|a|os|as|algum|alguma)\b', texto_norm):
        return True

    if re.search(r'\b(chegou|voltou)\b', texto_norm):
        return True

    return False

def detectar_intencao(texto):
    """Detect user intent for Atacaforte's simplified WhatsApp flow."""
    texto_norm = normalize_text(texto).strip()
    texto_lower = texto_norm

    if is_food_safety_issue(texto):
        return 'feedback'

    if is_store_incident_issue(texto):
        return 'feedback'

    if any(p in texto_norm for p in PROMO_KEYWORDS_NORMALIZED):
        return 'promocoes'

    if classificar_sentimento(texto) in ['Urgente', 'Critico']:
        return 'feedback'

    # Só dispara estrutura_local se for PERGUNTA informativa, não reclamação
    ESTRUTURA_KEYWORDS = (
        'estacionamento', 'vaga', 'estacionar', 'banheiro', 'elevador',
        'escada', 'rampa', 'acessibilidade', 'cadeirante', 'estrutura',
        'carrinho', 'cesta', 'sacola', 'entrada', 'saida', 'portaria',
        'ar condicionado', 'bebedouro', 'wifi', 'wi-fi',
    )
    RECLAMACAO_INDICATORS = (
        'sujo', 'suja', 'imundo', 'imunda', 'nojento', 'nojenta',
        'molhado', 'molhada', 'quebrado', 'quebrada', 'estragado', 'estragada',
        'ruim', 'pessimo', 'pessima', 'horrivel', 'fedido', 'fedida',
        'fede', 'cheiro', 'lixo', 'podre', 'entupido', 'entupida',
        'sem papel', 'sem sabonete', 'sem agua', 'travado', 'travada',
        'enferrujado', 'enferrujada', 'roda quebrada', 'roda travada',
        'absurdo', 'descaso', 'vergonha', 'desrespeito',
    )
    tem_estrutura = any(p in texto_norm for p in ESTRUTURA_KEYWORDS)
    tem_reclamacao = any(p in texto_norm for p in RECLAMACAO_INDICATORS)
    if tem_estrutura and not tem_reclamacao:
        return 'estrutura_local'

    if looks_like_product_inquiry(texto_norm):
        return 'consulta_indisponivel'

    if is_horario_question(texto):
        return 'horario'

    if '?' in texto and any(p in texto_norm for p in GENERAL_QUESTION_HINTS_NORMALIZED):
        return 'pergunta_geral'

    if texto_lower.startswith(('como ', 'onde ', 'qual ', 'quais ', 'que horas ', 'vocês ', 'voces ')):
        return 'pergunta_geral'

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            system_msg = f'''Classifique a intenção de mensagens recebidas no WhatsApp do supermercado {MARKET_NAME}.
Você deve escolher APENAS uma destas intenções:
- promocoes: pergunta sobre ofertas, promoções ou encarte da semana
- consulta_indisponivel: pergunta sobre preço, estoque, disponibilidade, chegada ou retorno de produto
- pergunta_geral: dúvida operacional sobre o mercado
- feedback: elogio, reclamação, sugestão, comparação com concorrente ou opinião sobre a experiência

Responda apenas com a intenção, sem explicação.'''
            system_msg += """

REGRAS IMPORTANTES:
- "produto vencido", "produto estragado", "comida estragada", "mofado", "cheiro ruim", "bicho na comida" e pedidos de solucao para esse tipo de caso sao SEMPRE feedback
- "tem alguem roubando", "tem uma goteira", "tem vazamento", "tem alguem passando mal" e outros incidentes do mercado sao SEMPRE feedback
- reclamacao urgente nunca deve virar consulta_indisponivel
- consulta_indisponivel so vale para pergunta real de estoque, disponibilidade, preco ou chegada
"""
            prompt = f'''Mensagem: "{texto}"

Classifique a intenção considerando que {AGENT_NAME} NÃO tem acesso a estoque, CRM ou previsão de chegada.'''
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=20,
                temperature=0
            )
            intent = response.choices[0].message.content.strip().lower().replace('"', '').replace("'", '')
            print(f"[AI-INTENT] {intent}")
            if intent in ['promocoes', 'consulta_indisponivel', 'pergunta_geral', 'feedback']:
                return intent
        except Exception as e:
            print(f"AI intent error: {e}")

    if '?' in texto_lower:
        return 'pergunta_geral'

    return 'feedback'

def generate_promocoes_response(text=""):
    normalized_text = normalize_text(text or "")
    day_text = get_daily_promotions()
    week_text = get_weekly_promotions()
    has_week = normalize_text(week_text) != normalize_text(DEFAULT_PROMOTIONS_EMPTY_TEXT)

    if not day_text and not has_week:
        return "Ainda não recebi as promoções atualizadas. Se quiser, já deixo sua mensagem registrada para a equipe conferir."

    wants_today = any(keyword in normalized_text for keyword in ('hoje', 'do dia', 'de hoje'))
    wants_week = any(keyword in normalized_text for keyword in ('semana', 'da semana', 'encarte'))

    selected_label = f"promoções da semana no {MARKET_NAME}"
    selected_text = week_text

    if wants_today and day_text:
        selected_label = f"promoções de hoje no {MARKET_NAME}"
        selected_text = day_text
    elif wants_week and has_week:
        selected_label = f"promoções da semana no {MARKET_NAME}"
        selected_text = week_text
    elif day_text and has_week:
        selected_label = f"promoções de hoje e da semana no {MARKET_NAME}"
        selected_text = f"Promoções de hoje:\n{day_text}\n\nPromoções da semana:\n{week_text}"
    elif day_text:
        selected_label = f"promoções de hoje no {MARKET_NAME}"
        selected_text = day_text

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": build_dona_marcia_system_prompt()},
                    {
                        "role": "user",
                        "content": f'''O cliente perguntou sobre promoções.

Pergunta: "{text}"

Fonte de verdade:
- Escopo: {selected_label}
- Conteúdo disponível:
{selected_text}

Responda de forma natural, breve e útil.
- Use somente o conteúdo disponível acima
- Não invente produtos nem preços
- Se houver mais de um item, pode resumir em formato natural de WhatsApp
- Não fale sobre estoque, reposição ou chegada'''
                    }
                ],
                max_tokens=140,
                temperature=0.35
            )
            reply = response.choices[0].message.content.strip()
            if reply.startswith('"') and reply.endswith('"'):
                reply = reply[1:-1]
            return finalize_marcia_reply(reply, "Neutro", "Promoção", text)
        except Exception as e:
            print(f"Promotions response error: {e}")

    if selected_label.endswith(f"hoje no {MARKET_NAME}"):
        return f"*Promoções de hoje no {MARKET_NAME}:*\n{selected_text}"
    if selected_label.endswith(f"da semana no {MARKET_NAME}"):
        return f"*Promoções da semana no {MARKET_NAME}:*\n{selected_text}"
    return f"*Promoções no {MARKET_NAME}:*\n{selected_text}"

def generate_unavailable_product_response(text=""):
    """Responde sobre produto indisponível com empatia via IA."""
    api_key = os.getenv("OPENAI_API_KEY")
    fallback = (
        "Entendo, e é bom saber disso. Não tenho acesso ao estoque por aqui, "
        "mas já deixei registrado para a equipe do mercado ficar sabendo."
    )
    if not api_key or not text:
        return fallback
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_dona_marcia_system_prompt()},
                {"role": "user", "content": f"""O cliente mandou uma mensagem sobre um produto:
"{text}"

Responda como {AGENT_NAME} com empatia e honestidade:
- Reconheça o que o cliente disse (falta do produto, saudade, etc.)
- Diga que não tem acesso ao estoque nem previsão de chegada
- Diga que vai deixar registrado para a equipe do mercado ficar sabendo
- Máximo 2 frases, tom acolhedor"""}
            ],
            max_tokens=100,
            temperature=0.65
        )
        reply = response.choices[0].message.content.strip()
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        return reply
    except Exception as e:
        print(f"[UNAVAILABLE] AI error: {e}")
        return fallback

def generate_pergunta_geral_response(text):
    """Responde perguntas gerais sem inventar informações internas."""
    api_key = os.getenv("OPENAI_API_KEY")
    fallback = "Isso eu não consigo confirmar por aqui no momento."
    if not api_key:
        return fallback

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_dona_marcia_system_prompt()},
                {
                    "role": "user",
                    "content": f'''O cliente fez uma dúvida geral.

Pergunta: "{text}"

Responda de forma breve. Se a informação não estiver disponível no contexto, diga que não consegue confirmar por aqui sem inventar nada.'''
                }
            ],
            max_tokens=100,
            temperature=0.4
        )
        reply = response.choices[0].message.content.strip()
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        return reply
    except Exception as e:
        print(f"Pergunta geral error: {e}")
        return fallback

def generate_ai_response(text, category, urgency):
    """Gera resposta acolhedora e factual como Seu Pipico."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        if urgency == "Positivo":
            return "Que bom receber isso. Obrigado por contar pra gente ✅"
        if urgency in ["Critico", "Urgente"]:
            return "Poxa, sinto muito por isso. Já deixei seu relato registrado para acompanhamento."
        return "Obrigado por me contar. Já deixei seu registro salvo para acompanhamento."

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        user_msg = f'''Tipo de feedback:
- Categoria: {category}
- Intensidade: {urgency}
- Mensagem do cliente: "{text}"

Conversa recente:
{recent_context}

Gere uma resposta curta de {AGENT_NAME}.
- Se for reclamação, acolha e diga que registrou para acompanhamento
- Se for elogio, agradeça
- Se for sugestão, agradeça e diga que registrou
- Se houver concorrente citado, reconheça a comparação com respeito
- Não invente solução já executada'''
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_dona_marcia_system_prompt()},
                {"role": "user", "content": user_msg}
            ],
            max_tokens=120,
            temperature=0.7
        )
        reply = response.choices[0].message.content.strip()
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        return reply
    except Exception as e:
        print(f"[MARCIA] Error: {e}")
        if urgency == "Positivo":
            return "Que bom receber isso. Obrigado por contar pra gente ✅"
        if urgency in ["Critico", "Urgente"]:
            return "Poxa, sinto muito por isso. Já deixei seu relato registrado para acompanhamento."
        return "Obrigado por me contar. Já deixei seu registro salvo para acompanhamento."

MARCIA_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF\U0000FE00-\U0000FE0F\U0000200D\U00002764"
    "]+",
    flags=re.UNICODE
)

THANK_YOU_PATTERNS = {
    'obrigado', 'obrigada', 'brigado', 'brigada', 'valeu', 'valeu mesmo',
    'muito obrigado', 'muito obrigada', 'agradeco', 'agradeço',
    'obrigado viu', 'obrigada viu', 'show obrigado', 'show obrigada'
}

# Frases que indicam que o cliente está encerrando a conversa
WRAP_UP_PATTERNS = {
    # "só isso"
    'so isso', 'só isso', 'so isso mesmo', 'só isso mesmo', 'era so isso',
    'era só isso', 'e so isso', 'é só isso', 'so isso por ora', 'só isso por ora',
    # "era isso"
    'era isso', 'era isso mesmo', 'e isso', 'é isso', 'e isso mesmo', 'é isso mesmo',
    'era so isso mesmo', 'era só isso mesmo',
    # despedidas
    'tchau', 'tchauu', 'tchauzinho', 'xau', 'xauu',
    'ate mais', 'até mais', 'ate logo', 'até logo', 'ate', 'até',
    'ate breve', 'até breve', 'fui', 'fui la', 'fui lá', 'abcos', 'abs',
    'falou', 'vlw', 'abraco', 'abraço', 'abcs',
    # encerramento com agradecimento
    'ok obrigado', 'ok obrigada', 'ok valeu', 'tudo bem obrigado', 'tudo bem obrigada',
    'tudo bem valeu', 'ta bom obrigado', 'ta bom obrigada', 'tá bom obrigado',
    'pode fechar', 'pode encerrar', 'encerrado', 'sem mais',
    # confirmações de encerramento
    'tudo certo', 'ta bom', 'tá bom', 'ok', 'entendi', 'certo',
    'combinado', 'perfeito obrigado', 'perfeito valeu',
}

NEGATIVE_SIGNAL_PATTERNS = (
    'fila', 'demora', 'atraso', 'sujo', 'sujeira', 'caro', 'preco alto',
    'preço alto', 'problema', 'ruim', 'mal atendido', 'mal atendida',
    'horrivel', 'horrível', 'pessimo', 'péssimo', 'enorme', 'lotado',
    'erro', 'reclam', 'bagunca', 'bagunça'
)

# --- Saudações e bate-papo casual ---
# Palavras que indicam cumprimento explícito
GREETING_WORDS = {
    'oi', 'ola', 'olá', 'eai', 'eae', 'opa', 'fala', 'salve',
    'hey', 'hello', 'hi',
}

# Padrões ambíguos — podem ser saudação ou despedida dependendo do contexto
# Se há conversa ativa → despedida; se não → saudação
CONTEXT_DEPENDENT_PATTERNS = {
    'bom dia', 'boa tarde', 'boa noite', 'tudo bem', 'tudo bom', 'tudo certo',
}

# Controle de bate-papo casual por remetente
_casual_chat_tracker = {}
CASUAL_CHAT_TTL = 600   # 10 min sem interação reseta o contador
CASUAL_CHAT_LIMIT = 4   # Após N msgs casuais, redireciona para o mercado

CATEGORY_EMOJI_MAP = {
    'hortifruti': '🥬',
    'padaria': '🍞',
    'acougue': '🥩',
    'açougue': '🥩',
    'promocao': '🛒',
    'promoção': '🛒',
}

def strip_marcia_emojis(text):
    return MARCIA_EMOJI_RE.sub('', text or '').strip()

def normalize_reply_spacing(text):
    text = re.sub(r'\s+', ' ', (text or '').strip())
    text = re.sub(r'\s+([,.!?])', r'\1', text)
    return text.strip()

def is_customer_thank_you_message(text):
    normalized = normalize_text(text).rstrip('!.?')
    if normalized in THANK_YOU_PATTERNS:
        return True
    tokens = [token for token in normalized.split() if token]
    if len(tokens) > 4:
        return False
    return any(
        normalized.startswith(pattern) or f" {pattern}" in normalized
        for pattern in THANK_YOU_PATTERNS
    )

def is_conversation_wrap_up(text):
    """Detecta se o cliente está encerrando a conversa.

    Cobre frases como 'só isso mesmo', 'era isso', 'tchau', 'tudo bem',
    que indicam que o cliente não tem mais nada a acrescentar.
    """
    normalized = normalize_text(text or '').strip().rstrip('!.?')
    if not normalized:
        return False
    # Match exato
    if normalized in WRAP_UP_PATTERNS:
        return True
    # Match exato também para agradecimentos
    if normalized in THANK_YOU_PATTERNS:
        return True
    # Mensagem curta (até 5 tokens) que começa ou contém padrão de encerramento
    tokens = [t for t in normalized.split() if t]
    if len(tokens) > 6:
        return False
    return any(
        normalized == pattern or normalized.startswith(pattern) or normalized.endswith(pattern)
        for pattern in WRAP_UP_PATTERNS
    )


def is_greeting(text):
    """Detecta se a mensagem é uma saudação/cumprimento."""
    normalized = normalize_text(text or '').strip().rstrip('!.?')
    if not normalized:
        return False
    tokens = normalized.split()
    if len(tokens) > 10:
        return False
    # Limpa pontuação dos tokens para matching (ex: "oi," → "oi")
    clean_tokens = [t.strip(',.!?;:') for t in tokens]
    # Contém palavra de saudação explícita (oi, olá, fala, etc.)
    if any(token in GREETING_WORDS for token in clean_tokens):
        return True
    # Frase ambígua sozinha (bom dia, tudo bem, etc.)
    if normalized in CONTEXT_DEPENDENT_PATTERNS:
        return True
    # Começa com padrão ambíguo + algo mais (ex: "bom dia pessoal")
    if any(normalized.startswith(p) for p in CONTEXT_DEPENDENT_PATTERNS):
        return True
    return False


def _get_casual_chat_count(remote_jid):
    """Retorna contador de bate-papo casual do remetente."""
    entry = _casual_chat_tracker.get(remote_jid)
    if not entry:
        return 0
    if (time_now() - entry["timestamp"]) > CASUAL_CHAT_TTL:
        _casual_chat_tracker.pop(remote_jid, None)
        return 0
    return entry["count"]


def _increment_casual_chat(remote_jid):
    """Incrementa e retorna o novo contador de bate-papo casual."""
    count = _get_casual_chat_count(remote_jid) + 1
    _casual_chat_tracker[remote_jid] = {"count": count, "timestamp": time_now()}
    return count


def _reset_casual_chat(remote_jid):
    """Reseta contador quando o cliente fala de algo do mercado."""
    _casual_chat_tracker.pop(remote_jid, None)


def is_agent_identity_question(text):
    normalized = normalize_text(text).rstrip('!.?')
    identity_patterns = (
        'qual seu nome',
        'qual o seu nome',
        'como voce se chama',
        'quem e voce',
        'quem ta falando',
        'quem esta falando',
        'voce e quem',
        'seu nome'
    )
    return any(pattern in normalized for pattern in identity_patterns)

def is_negative_feedback_message(text, urgency):
    if urgency in ['Critico', 'Urgente']:
        return True
    normalized = normalize_text(text)
    return any(pattern in normalized for pattern in NEGATIVE_SIGNAL_PATTERNS)

def choose_marcia_emoji(clean_reply, urgency, category, source_text):
    if is_customer_thank_you_message(source_text):
        return ''
    if is_negative_feedback_message(source_text, urgency):
        return ''

    clean_norm = normalize_text(clean_reply)
    category_norm = normalize_text(category or '')

    if 'registr' in clean_norm or 'acompanh' in clean_norm:
        return '✅'
    if urgency == 'Positivo':
        return CATEGORY_EMOJI_MAP.get(category_norm, '😊')
    if 'obrigad' in clean_norm or 'agradec' in clean_norm:
        return '💚'
    return ''

def finalize_marcia_reply(reply, urgency, category, source_text):
    if is_customer_thank_you_message(source_text):
        return "Eu que agradeço. Se quiser, pode me contar mais detalhes."

    clean_reply = normalize_reply_spacing(strip_marcia_emojis(reply))
    if not clean_reply:
        clean_reply = "Obrigado por me contar. Já deixei seu registro salvo para acompanhamento."

    emoji = choose_marcia_emoji(clean_reply, urgency, category, source_text)
    if emoji and not clean_reply.endswith(('.', '!', '?')):
        clean_reply += '.'
    if emoji:
        clean_reply = f"{clean_reply} {emoji}"
    return clean_reply

def build_dona_marcia_system_prompt():
    return f'''Você é {AGENT_NAME}, atendente virtual do supermercado {MARKET_NAME} no WhatsApp.

SEU PAPEL
- Receber elogios, reclamações, sugestões e dúvidas gerais dos clientes
- Acolher o cliente de forma humana, prática e rápida
- Informar as promoções do dia e da semana apenas com base no bloco fixo abaixo
- Reconhecer comparações com concorrentes com respeito
- Registrar o feedback para acompanhamento

PERSONALIDADE
- Tom acolhedor, esperto, direto e confiável
- Usa "você"
- Seu nome é Seu Pipico
- Você é homem e deve falar no masculino quando falar de si
- Nunca usa linguagem robótica, fria ou corporativa
- Emoji é opcional, nunca obrigatório
- No máximo 1 emoji por resposta, e só quando combinar com o contexto

REGRAS ABSOLUTAS
- Responda sempre em português do Brasil
- Respostas curtas: no máximo 2 frases
- Nunca diga que é IA, sistema ou robô
- Nunca invente preços, estoque, prazo de chegada, ação interna já executada, políticas, dados de CRM ou informação não fornecida
- Você NÃO tem acesso a estoque, previsão de reposição, CRM ou sistemas internos do mercado
- Se perguntarem sobre estoque, disponibilidade ou chegada de produto, diga com honestidade que não consegue confirmar por aqui
- Se houver reclamação, reconheça o problema e diga que o relato foi registrado para acompanhamento
- Se houver elogio, agradeça de forma curta e calorosa
- Se houver sugestão, agradeça e diga que ela foi registrada
- Se houver menção a concorrente, responda com respeito e valorize a comparação
- Se a informação não existir no contexto, diga isso claramente e ofereça o próximo passo mais simples
- Nunca diga "já resolvi", "já corrigi", "já chamei" ou equivalente sem confirmação explícita no contexto
- Se perguntarem seu nome ou quem está falando, responda claramente que você é o Seu Pipico, atendimento do Atacaforte
- Nunca use emoji sorrindo em reclamação, problema, atraso, fila, sujeira, preço alto ou experiência negativa
- Em reclamações críticas ou urgentes, prefira não usar emoji
- Emoji permitido por contexto:
  - confirmação de registro: ✅
  - elogio ou agradecimento leve: 😊 ou 💚
  - promoção ou setor de compras: 🛒, 🥬, 🍞, 🥩
- Nunca use em contexto negativo: 😊 😄 🙂 😍 🥰 ❤️ 🤗

EXEMPLOS DE TOM
- Reclamação (primeira mensagem): "Poxa, que situação chata. Já registrei aqui para a equipe acompanhar."
- Reclamação (segunda mensagem, cliente reforça): "Entendo a frustração. Esse ponto ficou marcado com atenção — a equipe vai ver."
- Reclamação (cliente claramente irritado): "Faz sentido estar irritado com isso. Já sinalizei como urgente."
- Confirmação: "Tudo certo, já está no registro ✅"
- Elogio: "Que bom ouvir isso. Obrigado por contar 😊"
- Agradecimento do cliente: "Eu que agradeço. Pode mandar mais se precisar."
- Cliente só agradece: "Fico feliz em ajudar."
- Sugestão: "Boa ideia, já deixei anotado para a equipe."

{build_food_safety_prompt_block()}

{build_store_incident_prompt_block()}

{build_promotions_prompt_block()}
'''

def generate_promocoes_response(text=""):
    normalized_text = normalize_text(text or "")
    day_text = get_daily_promotions()
    week_text = get_weekly_promotions()
    has_week = normalize_text(week_text) != normalize_text(DEFAULT_PROMOTIONS_EMPTY_TEXT)
    formatted_day = format_promotions_text(day_text)
    formatted_week = format_promotions_text(week_text) if has_week else ""

    if not day_text and not has_week:
        return "Ainda não recebi as promoções atualizadas. Se quiser, já deixo sua mensagem registrada para a equipe conferir."

    wants_today = any(keyword in normalized_text for keyword in ('hoje', 'do dia', 'de hoje'))
    wants_week = any(keyword in normalized_text for keyword in ('semana', 'da semana', 'encarte'))

    if wants_today and day_text:
        return f"🛒 *Promoções de hoje no {MARKET_NAME}:*\n\n{formatted_day}"

    if wants_week and has_week:
        return f"🛒 *Promoções da semana no {MARKET_NAME}:*\n\n{formatted_week}"

    if day_text and has_week:
        return (
            f"🛒 *Promoções de hoje no {MARKET_NAME}:*\n\n{formatted_day}\n\n"
            f"🛒 *Promoções da semana no {MARKET_NAME}:*\n\n{formatted_week}"
        )

    if day_text:
        return f"🛒 *Promoções de hoje no {MARKET_NAME}:*\n\n{formatted_day}"

    return f"🛒 *Promoções da semana no {MARKET_NAME}:*\n\n{formatted_week}"

def generate_pergunta_geral_response(text):
    """Responde perguntas gerais com o mesmo filtro de tom e emoji do Seu Pipico."""
    if is_agent_identity_question(text):
        return "Eu sou o Seu Pipico, atendimento do Atacaforte."

    api_key = os.getenv("OPENAI_API_KEY")
    fallback = "Isso eu não consigo confirmar por aqui no momento."
    if not api_key:
        return finalize_marcia_reply(fallback, "Neutro", "Geral", text)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_dona_marcia_system_prompt()},
                {
                    "role": "user",
                    "content": f'''O cliente fez uma dúvida geral.

Pergunta: "{text}"

Responda de forma breve. Se a informação não estiver disponível no contexto, diga que não consegue confirmar por aqui sem inventar nada.'''
                }
            ],
            max_tokens=100,
            temperature=0.4
        )
        reply = response.choices[0].message.content.strip()
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        return finalize_marcia_reply(reply, "Neutro", "Geral", text)
    except Exception as e:
        print(f"Pergunta geral error: {e}")
        return finalize_marcia_reply(fallback, "Neutro", "Geral", text)

def generate_ai_response(text, category, urgency, conversation_entries=None):
    """Gera resposta acolhedora e factual como Seu Pipico, com emoji contextual."""
    if is_agent_identity_question(text):
        return "Eu sou o Seu Pipico, atendimento do Atacaforte."

    if is_food_safety_issue(text):
        return build_food_safety_reply()

    if is_store_incident_issue(text):
        return build_store_incident_reply()

    conversation_entries = conversation_entries or []
    has_followup_context = has_feedback_followup_context(conversation_entries)
    recent_context = format_recent_conversation_for_prompt(conversation_entries)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        if has_followup_context:
            reply = build_followup_feedback_reply(text, category, urgency)
        elif urgency == "Positivo":
            reply = "Que bom receber isso. Obrigado por contar pra gente."
        elif urgency in ["Critico", "Urgente"]:
            reply = "Sinto muito por isso. Já deixei seu relato registrado para acompanhamento."
        else:
            reply = "Obrigado por me contar. Já deixei seu registro salvo para acompanhamento."
        return finalize_marcia_reply(reply, urgency, category, text)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        user_msg = f'''Tipo de feedback:
- Categoria: {category}
- Intensidade: {urgency}
- Mensagem do cliente: "{text}"

Conversa recente:
{recent_context}

Gere uma resposta curta de {AGENT_NAME}.
- Se for reclamação, acolha e diga que registrou para acompanhamento
- Se for elogio, agradeça
- Se for sugestão, agradeça e diga que registrou
- Se houver concorrente citado, reconheça a comparação com respeito
- Se o cliente só agradecer, responda com algo simples e natural
- Não invente solução já executada'''
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_dona_marcia_system_prompt()},
                {"role": "user", "content": user_msg}
            ],
            max_tokens=120,
            temperature=0.5
        )
        reply = response.choices[0].message.content.strip()
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        return finalize_marcia_reply(reply, urgency, category, text)
    except Exception as e:
        print(f"[MARCIA] Error: {e}")
        if urgency == "Positivo":
            reply = "Que bom receber isso. Obrigado por contar pra gente."
        elif urgency in ["Critico", "Urgente"]:
            reply = "Sinto muito por isso. Já deixei seu relato registrado para acompanhamento."
        else:
            reply = "Obrigado por me contar. Já deixei seu registro salvo para acompanhamento."
        return finalize_marcia_reply(reply, urgency, category, text)

def generate_ai_response(text, category, urgency, conversation_entries=None, remote_jid=None):
    """Versao final contextual do Seu Pipico, evitando repeticao em follow-up."""
    if is_agent_identity_question(text):
        return "Eu sou o Seu Pipico, atendimento do Atacaforte."

    if is_food_safety_issue(text):
        return build_food_safety_reply()

    conversation_entries = conversation_entries or []
    has_followup_context = has_feedback_followup_context(conversation_entries)
    recent_context = format_recent_conversation_for_prompt(conversation_entries)
    escalacao = detect_emotional_escalation(conversation_entries)

    # Contexto de cliente recorrente
    historico_ctx = build_returning_client_context(remote_jid, category) if remote_jid else {'is_returning': False}
    if historico_ctx.get('extra_urgency') and urgency not in ('Critico',):
        urgency = 'Urgente'  # Eleva urgência se mesmo problema foi reportado antes

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        if escalacao == 'escalando':
            reply = "Entendo, e é muito chato que isso continue acontecendo. Vou deixar marcado como prioridade para a equipe ver."
        elif has_followup_context:
            reply = build_followup_feedback_reply(text, category, urgency)
        elif urgency == "Positivo":
            reply = "Que bom receber isso. Obrigado por contar pra gente."
        elif urgency in ["Critico", "Urgente"]:
            reply = "Sinto muito por isso. Ja deixei seu relato registrado para acompanhamento."
        else:
            reply = "Obrigado por me contar. Ja deixei seu registro salvo para acompanhamento."
        return finalize_marcia_reply(reply, urgency, category, text)

    # Bloco de instrução adicional para escalada emocional
    instrucao_escalada = ""
    if escalacao == 'escalando':
        instrucao_escalada = """
- ATENÇÃO: o cliente está progressivamente mais irritado. Não use o mesmo tom de resposta padrão.
  Reconheça explicitamente que a situação piorou, mostre que entendeu a gravidade,
  e diga que vai sinalizar com urgência — sem prometer ação que você não pode confirmar."""

    # Bloco de instrução para cliente recorrente
    instrucao_recorrente = ""
    if historico_ctx.get('same_issue') and historico_ctx.get('count', 0) >= 2:
        instrucao_recorrente = f"""
- IMPORTANTE: esse cliente já nos relatou situações parecidas antes ({historico_ctx['count']} vezes).
  Reconheça isso de forma genuína, sem ser mecânico. Mostre que levamos a sério e que
  o histórico dele foi notado. Ex: 'Sei que não é a primeira vez que isso acontece com você.'
  Não prometa solução que não pode confirmar."""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        user_msg = f'''Tipo de feedback:
- Categoria: {category}
- Intensidade: {urgency}
- Mensagem do cliente: "{text}"

Conversa recente:
{recent_context}

Gere uma resposta curta de {AGENT_NAME}.
- Se for reclamacao, acolha o cliente
- Se a conversa ja estiver em andamento, continue de forma natural sem repetir literalmente a ultima resposta do Pipico
- Se o cliente reforcar frustracao, constrangimento ou expectativa de solucao, reconheca isso e reforce que a equipe vai acompanhar com atencao
- Quando fizer sentido, diga que o feedback e importante para o {MARKET_NAME}
- Se for elogio, agradeca
- Se for sugestao, agradeca e diga que registrou
- Se houver concorrente citado, reconheca a comparacao com respeito
- Se o cliente so agradecer, responda com algo simples e natural
- Nao invente solucao ja executada
- Evite repetir "ja deixei seu relato registrado para acompanhamento" se isso ja foi dito na ultima resposta{instrucao_escalada}{instrucao_recorrente}'''
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_dona_marcia_system_prompt()},
                {"role": "user", "content": user_msg}
            ],
            max_tokens=120,
            temperature=0.65
        )
        reply = response.choices[0].message.content.strip()
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        if is_repetitive_followup_reply(reply, conversation_entries):
            reply = build_followup_feedback_reply(text, category, urgency)
        return finalize_marcia_reply(reply, urgency, category, text)
    except Exception as e:
        print(f"[MARCIA] Error: {e}")
        if has_followup_context:
            reply = build_followup_feedback_reply(text, category, urgency)
        elif urgency == "Positivo":
            reply = "Que bom receber isso. Obrigado por contar pra gente."
        elif urgency in ["Critico", "Urgente"]:
            reply = "Sinto muito por isso. Ja deixei seu relato registrado para acompanhamento."
        else:
            reply = "Obrigado por me contar. Ja deixei seu registro salvo para acompanhamento."
        return finalize_marcia_reply(reply, urgency, category, text)


def generate_greeting_response(text, push_name=None, casual_count=0):
    """Gera resposta natural para saudações via IA."""
    api_key = os.getenv("OPENAI_API_KEY")

    redirect = ""
    if casual_count >= CASUAL_CHAT_LIMIT:
        redirect = (
            "\n\nATENÇÃO: o cliente já mandou várias mensagens de bate-papo sem falar do mercado. "
            "Cumprimente brevemente e pergunte se pode ajudar com algo do Atacaforte — "
            "promoções, opinião sobre o mercado, dúvidas. Seja natural."
        )

    greeting_prompt = f"""O cliente mandou uma saudação no WhatsApp.
- Nome do cliente: {push_name or 'não informado'}
- Mensagem: "{text}"
- Responda como {AGENT_NAME} de forma natural, curta e acolhedora (1-2 frases)
- Cumprimente de volta e se apresente brevemente
- Não diga que é IA, sistema ou robô{redirect}"""

    name_part = f" {push_name}!" if push_name else "!"

    if not api_key:
        if casual_count >= CASUAL_CHAT_LIMIT:
            return f"Opa, tudo certo{name_part} Posso te ajudar com algo do {MARKET_NAME}? Promoções, feedback, dúvidas... é só falar! 🛒"
        return f"E aí{name_part} Aqui é o {AGENT_NAME}, do {MARKET_NAME}. Pode falar!"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_dona_marcia_system_prompt()},
                {"role": "user", "content": greeting_prompt}
            ],
            max_tokens=80,
            temperature=0.7
        )
        reply = response.choices[0].message.content.strip()
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        return reply
    except Exception as e:
        print(f"[GREETING] AI error: {e}")
        if casual_count >= CASUAL_CHAT_LIMIT:
            return f"Opa, tudo certo{name_part} Posso te ajudar com algo do {MARKET_NAME}? Promoções, feedback, dúvidas... é só falar! 🛒"
        return f"E aí{name_part} Aqui é o {AGENT_NAME}, do {MARKET_NAME}. Pode falar!"


def is_negative_reply(text):
    negative = {
        'nao', 'não', 'agora nao', 'agora não', 'deixa', 'deixa pra la',
        'deixa pra lá', 'não quero', 'nao quero', 'dispensa', 'nem precisa'
    }
    return normalize_text(text).strip().rstrip('!.?') in negative

def extract_product_topic(text):
    text_norm = normalize_text(text)
    produtos = get_produtos()
    best_match = None
    best_len = 0

    for produto in produtos:
        nome = produto.get('nome', '').strip()
        if not nome:
            continue
        nome_norm = normalize_text(nome)
        if nome_norm and nome_norm in text_norm and len(nome_norm) > best_len:
            best_match = nome
            best_len = len(nome_norm)

    if best_match:
        return best_match

    raw = re.sub(r'^[\s\-\.:,;]+|[\s\-\.:,;]+$', '', text).strip()
    raw_words = [w for w in raw.split() if w]
    blocked_terms = {
        'assai', 'assaí', 'atacadao', 'atacadão', 'carrefour', 'mais', 'barato',
        'caro', 'promoção', 'promocao', 'oferta', 'concorrente', 'mercado'
    }
    if 1 <= len(raw_words) <= 4 and not any(normalize_text(w) in blocked_terms for w in raw_words):
        return raw
    return None

def extract_competitor_product_followup(text):
    product = extract_product_topic(text)
    if product:
        return product

    ai_product = extrair_produto_ia(text)
    if ai_product:
        return ai_product.strip()

    return None

def ensure_config_defaults(config):
    config = config or {}
    categories = config.get('categories') or []
    existing = {c.get('name') for c in categories}
    defaults = [
        ("Atendimento", "#3b82f6"),
        ("Fila", "#f59e0b"),
        ("Hortifrúti", "#10b981"),
        ("Padaria", "#f97316"),
        ("Açougue", "#ef4444"),
        ("Limpeza", "#8b5cf6"),
        ("Preço", "#ec4899"),
        ("Promoção", "#14b8a6"),
        ("Estacionamento", "#6366f1"),
    ]
    for name, color in defaults:
        if name not in existing:
            categories.append({"name": name, "color": color, "count": 0})
    config['categories'] = categories
    promotions = config.get('promotions') or {}
    config['promotions'] = {
        "day": (promotions.get('day') or '').strip(),
        "week": (promotions.get('week') or '').strip()
    }
    return config

def classificar_categoria(texto):
    """Classifica categoria de feedback, com suporte a Promoção."""
    texto_lower = texto.lower()
    concorrentes = detectar_concorrentes(texto)
    if any(item.get('contexto') in ['preco', 'promocao'] for item in concorrentes):
        return 'Promoção'

    if any(p in texto_lower for p in [
        'promoção', 'promocao', 'promoções', 'promocoes', 'oferta', 'ofertas',
        'desconto', 'encarte', 'mais barato', 'mais em conta', 'preço melhor', 'preco melhor'
    ]):
        return 'Promoção'

    if any(p in texto_lower for p in [
        'fila', 'caixa', 'caixas', 'espera', 'esperando', 'demora', 'demorando',
        'lotado', 'superlotado', 'poucos caixas', 'caixa fechado',
        'self checkout', 'autoatendimento', 'fila enorme', 'fila gigante'
    ]):
        return 'Fila'

    if any(p in texto_lower for p in [
        'fruta', 'verdura', 'legume', 'hortifruti', 'hortifrúti', 'banana', 'tomate',
        'morango', 'alface', 'murcha', 'podre', 'estragado', 'mofado'
    ]):
        return 'Hortifrúti'

    if any(p in texto_lower for p in ['padaria', 'pão', 'pao', 'bolo', 'pão de queijo', 'pao de queijo']):
        return 'Padaria'

    if any(p in texto_lower for p in ['açougue', 'acougue', 'carne', 'frango', 'peixe', 'linguiça', 'linguica']):
        return 'Açougue'

    if any(p in texto_lower for p in ['limpeza', 'banheiro', 'sujeira', 'sujo', 'imundo', 'corredor']):
        return 'Limpeza'

    if any(p in texto_lower for p in [
        'preço', 'preco', 'caro', 'cobrança', 'cobranca', 'cobraram errado',
        'preço errado', 'preco errado', 'valor', 'etiqueta'
    ]):
        return 'Preço'

    if any(p in texto_lower for p in ['estacionamento', 'vaga', 'estacionar', 'carro', 'moto', 'cancela']):
        return 'Estacionamento'

    return 'Atendimento'

def classificar_com_ia(texto):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    if is_food_safety_issue(texto):
        return {
            "categoria": classificar_categoria(texto),
            "sentimento": "Urgente",
            "setor": classificar_setor(texto)
        }
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f'''Classifique este feedback de um cliente de supermercado.
Texto: "{texto}"

Responda APENAS em JSON:
{{
  "categoria": "Atendimento" | "Fila" | "Hortifrúti" | "Padaria" | "Açougue" | "Limpeza" | "Preço" | "Promoção" | "Estacionamento",
  "sentimento": "Positivo" | "Critico" | "Urgente" | "Neutro",
  "setor": "Caixas" | "Hortifrúti" | "Padaria" | "Açougue" | "Bebidas" | "Limpeza" | "Estacionamento" | "Entrada" | "Geral"
}}

Use "Promoção" para promoções, ofertas, descontos e comparações de preço com concorrentes.'''
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0
        )
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
        return json.loads(result_text)
    except Exception as e:
        print(f"Erro IA classificacao override: {e}")
        return None

def persist_feedback_message(remote_jid, push_name, text, forced_category=None, forced_topic=None):
    customer_text = get_feedback_customer_text(text) or text
    ia_result = None if forced_category else classificar_com_ia(customer_text)
    if ia_result:
        sentimento = ia_result.get('sentimento', 'Neutro')
        categoria = ia_result.get('categoria', forced_category or 'Atendimento')
        setor = ia_result.get('setor', 'Geral')
    else:
        sentimento = classificar_sentimento(customer_text)
        categoria = forced_category or classificar_categoria(customer_text)
        setor = classificar_setor(customer_text)

    active_feedback = get_active_feedback(remote_jid)
    linked_from_id = None
    if active_feedback:
        old_category = (active_feedback.get('category') or '').strip().lower()
        new_category = (categoria or '').strip().lower()
        if old_category == new_category:
            current_urgency = active_feedback.get('urgency', 'Neutro')
            priority_map = {"Critico": 3, "Urgente": 2, "Positivo": 1, "Neutro": 0}
            update_urgency = sentimento if priority_map.get(sentimento, 0) > priority_map.get(current_urgency, 0) else None
            update_sentiment = None
            if update_urgency:
                update_sentiment = "Positivo" if sentimento == "Positivo" else ("Negativo" if sentimento in ["Critico", "Urgente"] else "Neutro")
            updated_message = append_to_feedback(active_feedback['id'], active_feedback['message'], customer_text, update_urgency, update_sentiment)
            if forced_topic:
                update_feedback(active_feedback['id'], {'topic': forced_topic})
            return {
                "saved": True,
                "updated_existing": True,
                "id": active_feedback['id'],
                "message": updated_message or active_feedback['message'],
                "category": categoria,
                "urgency": sentimento
            }
        linked_from_id = active_feedback.get('id')

    now = datetime.utcnow()
    current_id = get_next_id()
    stored_message = text if has_structured_conversation(text) else build_feedback_message(customer_text, now.isoformat())
    new_feedback = {
        "id": current_id,
        "sender": remote_jid,
        "name": push_name,
        "message": stored_message,
        "timestamp": now.isoformat(),
        "updated_at": now.isoformat(),
        "category": categoria,
        "region": setor,
        "urgency": sentimento,
        "sentiment": "Positivo" if sentimento == "Positivo" else ("Negativo" if sentimento in ["Critico", "Urgente"] else "Neutro"),
        "loja": "Matriz",
        "status": "aberto"
    }
    if forced_topic:
        new_feedback["topic"] = forced_topic
    if linked_from_id:
        new_feedback["linked_from"] = linked_from_id
    save_feedback(new_feedback)
    return {
        "saved": True,
        "updated_existing": False,
        "id": current_id,
        "message": stored_message,
        "category": categoria,
        "urgency": sentimento
    }

def process_context_followup(remote_jid, push_name, text):
    ctx = get_context(remote_jid)
    if not ctx:
        return None

    state = ctx.get('state') or ctx.get('intent')
    data = ctx.get('data') or {}

    if state == 'awaiting_promo_choice':
        texto_norm = normalize_text(text)
        quer_dia = any(p in texto_norm for p in ('1', 'dia', 'hoje', 'diaria', 'diario'))
        quer_mes = any(p in texto_norm for p in ('2', 'mes', 'mensal', 'mensais', 'encarte'))

        escolhas = sum([quer_dia, quer_mes])

        if escolhas == 1:
            clear_context(remote_jid)
            if quer_dia:
                _enviar_promo_dia(remote_jid)
                return {"reply": None, "status": "daily_promo_sent"}
            elif quer_mes:
                _enviar_promo_mes(remote_jid)
                return {"reply": None, "status": "monthly_promo_sent"}

        # Se o cliente mandou agradecimento, saudação ou despedida,
        # sai do contexto de promoção e deixa o fluxo normal tratar
        if (is_customer_thank_you_message(text) or is_greeting(text)
                or is_conversation_wrap_up(text)):
            clear_context(remote_jid)
            return None

        # Resposta ambígua — repete a pergunta
        return {
            "reply": (
                "Desculpe, não entendi bem. Responda:\n\n"
                "1️⃣ *1* para Promoções do Dia\n"
                "2️⃣ *2* para Promoções do Mês"
            ),
            "status": "awaiting_promo_choice"
        }

    if state == 'awaiting_competitor_product':
        if is_negative_reply(text):
            clear_context(remote_jid)
            return {"reply": "Tudo bem. Se quiser retomar depois, eu sigo com você por aqui.", "status": "context_cancelled"}

        if is_affirmative(text):
            return {"reply": "Me diz só qual produto específico estava mais barato lá, por favor.", "status": "awaiting_competitor_product"}

        product = extract_competitor_product_followup(text)
        if not product:
            return {"reply": "Me diz só qual produto específico ficou mais barato lá, por favor.", "status": "awaiting_competitor_product"}

        enriched_message = f"{data.get('message', '').strip()}\nProduto citado pelo cliente: {product}"
        result = persist_feedback_message(
            remote_jid,
            push_name,
            enriched_message,
            forced_category="Promoção",
            forced_topic=product
        )
        clear_context(remote_jid)
        return {
            "reply": f"Perfeito, ja deixei registrado para a equipe. Produto citado: {product} ✅",
            "status": "feedback_registered",
            "result": result
        }
        save_context(remote_jid, 'awaiting_registration_confirmation', {
            "message": enriched_message,
            "force_category": "Promoção",
            "topic": product
        })
        return {
            "reply": f"Perfeito, entendi que foi sobre {product}. Quer que eu deixe isso registrado para análise da equipe?",
            "status": "awaiting_registration_confirmation"
        }

    if state == 'awaiting_atendimento_detail':
        # Cliente respondeu com o detalhe do setor/caixa — enriquece o feedback
        if is_conversation_wrap_up(text) or is_customer_thank_you_message(text):
            clear_context(remote_jid)
            return {'reply': 'Tudo certo. Obrigado por nos contar!', 'status': 'detail_skipped'}
        feedback_id = data.get('feedback_id')
        if feedback_id:
            fb = get_feedback_by_id(feedback_id)
            if fb:
                detail_note = f'Detalhe informado pelo cliente: {text}'
                updated_msg = append_conversation_entry(fb.get('message', ''), 'client', detail_note)
                update_feedback(feedback_id, {'message': updated_msg, 'updated_at': datetime.utcnow().isoformat()})
        clear_context(remote_jid)
        return {
            'reply': 'Anotado, obrigado pelo detalhe. Vai ajudar muito a equipe a resolver! ✅',
            'status': 'atendimento_detail_recorded'
        }

    if state == 'awaiting_registration_confirmation':
        if is_customer_thank_you_message(text):
            clear_context(remote_jid)
            return {
                "reply": "Eu que agradeço. Se quiser, pode me contar mais detalhes.",
                "status": "context_closed"
            }

        if is_affirmative(text):
            result = persist_feedback_message(
                remote_jid,
                push_name,
                data.get('message', ''),
                forced_category=data.get('force_category'),
                forced_topic=data.get('topic')
            )
            clear_context(remote_jid)
            return {
                "reply": "Perfeito, já deixei sua mensagem registrada para acompanhamento ✅",
                "status": "feedback_registered",
                "result": result
            }
        if is_negative_reply(text):
            clear_context(remote_jid)
            return {"reply": "Certo, não vou registrar agora. Se quiser depois, é só me avisar.", "status": "registration_declined"}
        if looks_like_new_turn(text):
            clear_context(remote_jid)
            return None
        return {
            "reply": "Se você quiser que eu registre, pode me responder só com sim ou não.",
            "status": "awaiting_registration_confirmation"
        }

    return None

def get_sender_feedback_history(remote_jid):
    """Retorna feedbacks anteriores do mesmo número, excluindo o mais recente."""
    try:
        feedbacks = get_feedbacks()
        historico = [
            fb for fb in feedbacks
            if fb.get('sender') == remote_jid
        ]
        # Ordena do mais antigo para o mais recente
        historico.sort(key=lambda x: x.get('timestamp', ''), reverse=False)
        return historico
    except Exception:
        return []

def build_returning_client_context(remote_jid, new_category):
    """Verifica se o cliente é recorrente e monta instrução extra para o prompt.

    Retorna um dicionário com:
    - is_returning: bool
    - same_issue: bool (reclamou do mesmo tipo de problema antes)
    - count: quantas vezes já entrou em contato
    - extra_urgency: se deve elevar urgência
    """
    historico = get_sender_feedback_history(remote_jid)
    if not historico:
        return {'is_returning': False, 'same_issue': False, 'count': 0, 'extra_urgency': False}

    count = len(historico)
    categorias_anteriores = [fb.get('category', '').lower() for fb in historico]
    same_issue = any(
        (new_category or '').lower() in cat or cat in (new_category or '').lower()
        for cat in categorias_anteriores
        if cat
    )
    # Eleva urgência se mesmo problema foi reportado 2+ vezes
    extra_urgency = same_issue and count >= 2
    return {
        'is_returning': True,
        'same_issue': same_issue,
        'count': count,
        'extra_urgency': extra_urgency
    }

def process_feedback_message(remote_jid, push_name, text):
    concorrentes = detectar_concorrentes(text)
    topic = extract_product_topic(text)
    competitor_price_signal = any(item.get('contexto') in ['preco', 'promocao'] for item in concorrentes)

    if competitor_price_signal and not topic:
        save_context(remote_jid, 'awaiting_competitor_product', {
            "message": text,
            "force_category": "Promoção"
        })
        return {
            "reply": "Entendi, e essa comparação ajuda bastante a gente. Qual produto específico estava mais barato lá?",
            "status": "awaiting_competitor_product"
        }

    if competitor_price_signal and topic:
        enriched_message = f"{text}\nProduto citado pelo cliente: {topic}"
        result = persist_feedback_message(
            remote_jid,
            push_name,
            enriched_message,
            forced_category="Promoção",
            forced_topic=topic
        )
        return {
            "reply": f"Entendi, e essa comparação ajuda bastante a gente. Já deixei registrado para a equipe. Produto citado: {topic} ✅",
            "status": "feedback_registered",
            "result": result
        }
        save_context(remote_jid, 'awaiting_registration_confirmation', {
            "message": enriched_message,
            "force_category": "Promoção",
            "topic": topic
        })
        return {
            "reply": f"Entendi, e essa comparação ajuda bastante a gente. Quer que eu deixe isso registrado para análise da equipe? Produto citado: {topic}.",
            "status": "awaiting_registration_confirmation"
        }

    result = persist_feedback_message(remote_jid, push_name, text)
    conversation_entries = parse_feedback_conversation(result.get("message", ""))
    reply = generate_ai_response(text, result["category"], result["urgency"], conversation_entries=conversation_entries, remote_jid=remote_jid)

    # Coleta de detalhe acionável: se reclamação de atendimento e sem detalhe de local,
    # pergunta em qual caixa ou setor aconteceu
    categoria_lower = (result.get('category') or '').lower()
    eh_reclamacao_atendimento = (
        result.get('urgency') in ('Urgente', 'Critico')
        and any(p in categoria_lower for p in ('atendimento', 'funcionario', 'caixa', 'colaborador'))
    )
    tem_detalhe = any(p in normalize_text(text) for p in (
        'caixa', 'setor', 'padaria', 'acougue', 'açougue', 'hortifruti',
        'loja', 'balcao', 'balcão', 'numero', 'número'
    ))
    if eh_reclamacao_atendimento and not tem_detalhe and result.get('id'):
        save_context(remote_jid, 'awaiting_atendimento_detail', {'feedback_id': result['id']})
        reply = reply + '\n\nPode me dizer em qual caixa ou setor isso aconteceu? Vai ajudar a equipe a identificar e resolver mais rápido.'

    return {"reply": reply, "status": "feedback_processed", "result": result}

def _legacy_persist_feedback_message_corrupted(remote_jid, push_name, text, forced_category=None, forced_topic=None):
    customer_text = get_feedback_customer_text(text) or text
    ia_result = None if forced_category else classificar_com_ia(customer_text)
    if ia_result:
        sentimento = ia_result.get('sentimento', 'Neutro')
        categoria = ia_result.get('categoria', forced_category or 'Atendimento')
        setor = ia_result.get('setor', 'Geral')
    else:
        sentimento = classificar_sentimento(customer_text)
        categoria = forced_category or classificar_categoria(customer_text)
        setor = classificar_setor(customer_text)

    active_feedback = get_active_feedback(remote_jid)
    linked_from_id = None
    if active_feedback:
        old_category = (active_feedback.get('category') or '').strip().lower()
        new_category = (categoria or '').strip().lower()
        if old_category == new_category:
            current_urgency = active_feedback.get('urgency', 'Neutro')
            priority_map = {"Critico": 3, "Urgente": 2, "Positivo": 1, "Neutro": 0}
            update_urgency = sentimento if priority_map.get(sentimento, 0) > priority_map.get(current_urgency, 0) else None
            update_sentiment = None
            if update_urgency:
                update_sentiment = "Positivo" if sentimento == "Positivo" else ("Negativo" if sentimento in ["Critico", "Urgente"] else "Neutro")
            updated_message = append_to_feedback(active_feedback['id'], active_feedback['message'], customer_text, update_urgency, update_sentiment)
            if forced_topic:
                update_feedback(active_feedback['id'], {'topic': forced_topic})
            return {
                "saved": True,
                "updated_existing": True,
                "id": active_feedback['id'],
                "message": updated_message or active_feedback['message'],
                "category": categoria,
                "urgency": sentimento
            }
        linked_from_id = active_feedback.get('id')

    now = datetime.utcnow()
    current_id = get_next_id()
    stored_message = text if has_structured_conversation(text) else build_feedback_message(customer_text, now.isoformat())
    new_feedback = {
        "id": current_id,
        "sender": remote_jid,
        "name": push_name,
        "message": stored_message,
        "timestamp": now.isoformat(),
        "updated_at": now.isoformat(),
        "category": categoria,
        "region": setor,
        "urgency": sentimento,
        "sentiment": "Positivo" if sentimento == "Positivo" else ("Negativo" if sentimento in ["Critico", "Urgente"] else "Neutro"),
        "loja": "Matriz",
        "status": "aberto"
    }
    if forced_topic:
        new_feedback["topic"] = forced_topic
    if linked_from_id:
        new_feedback["linked_from"] = linked_from_id
    save_feedback(new_feedback)
    return {
        "saved": True,
        "updated_existing": False,
        "id": current_id,
        "message": stored_message,
        "category": categoria,
        "urgency": sentimento
    }

def _legacy_process_context_followup_corrupted(remote_jid, push_name, text):
    ctx = get_context(remote_jid)
    if not ctx:
        return None

    state = ctx.get('state') or ctx.get('intent')
    data = ctx.get('data') or {}

    if state == 'awaiting_competitor_product':
        if is_negative_reply(text):
            clear_context(remote_jid)
            return {"reply": "Tudo bem. Se quiser retomar depois, eu sigo com vocÃª por aqui.", "status": "context_cancelled"}

        if is_affirmative(text):
            return {"reply": "Me diz só qual produto específico estava mais barato lá, por favor.", "status": "awaiting_competitor_product"}

        product = extract_competitor_product_followup(text)
        if not product and looks_like_new_turn(text):
            clear_context(remote_jid)
            return None
        if not product:
            return {"reply": "Me diz só qual produto específico ficou mais barato lá, por favor.", "status": "awaiting_competitor_product"}

        updated_conversation = append_conversation_entry(data.get('message', ''), 'client', text)
        save_context(remote_jid, 'awaiting_registration_confirmation', {
            "message": updated_conversation,
            "force_category": "Promoção",
            "topic": product
        })
        return {
            "reply": f"Perfeito, entendi que foi sobre {product}. Quer que eu deixe isso registrado para análise da equipe?",
            "status": "awaiting_registration_confirmation"
        }

    if state == 'awaiting_registration_confirmation':
        if is_affirmative(text):
            conversation_seed = append_conversation_entry(data.get('message', ''), 'client', text)
            result = persist_feedback_message(
                remote_jid,
                push_name,
                conversation_seed,
                forced_category=data.get('force_category'),
                forced_topic=data.get('topic')
            )
            clear_context(remote_jid)
            return {
                "reply": "Perfeito, já deixei sua mensagem registrada para acompanhamento ✅",
                "status": "feedback_registered",
                "result": result
            }
        if is_negative_reply(text):
            clear_context(remote_jid)
            return {"reply": "Certo, não vou registrar agora. Se quiser depois, é só me avisar.", "status": "registration_declined"}
        return {
            "reply": "Se você quiser que eu registre, pode me responder só com sim ou não.",
            "status": "awaiting_registration_confirmation"
        }

    return None

def _legacy_process_feedback_message_corrupted(remote_jid, push_name, text):
    concorrentes = detectar_concorrentes(text)
    topic = extract_product_topic(text)
    competitor_price_signal = any(item.get('contexto') in ['preco', 'promocao'] for item in concorrentes)

    if competitor_price_signal and not topic:
        save_context(remote_jid, 'awaiting_competitor_product', {
            "message": build_feedback_message(text),
            "force_category": "Promoção"
        })
        return {
            "reply": "Entendi, e essa comparação ajuda bastante a gente. Qual produto específico estava mais barato lá?",
            "status": "awaiting_competitor_product"
        }

    if competitor_price_signal and topic:
        save_context(remote_jid, 'awaiting_registration_confirmation', {
            "message": build_feedback_message(text),
            "force_category": "Promoção",
            "topic": topic
        })
        return {
            "reply": f"Entendi, e essa comparação ajuda bastante a gente. Quer que eu deixe isso registrado para análise da equipe? Produto citado: {topic}.",
            "status": "awaiting_registration_confirmation"
        }

    result = persist_feedback_message(remote_jid, push_name, text)
    reply = generate_ai_response(text, result["category"], result["urgency"])
    return {"reply": reply, "status": "feedback_processed", "result": result}

# --- AI MARKET PULSE ---

def generate_ai_pulse(feedbacks):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not feedbacks:
        return {"summary": "Aguardando feedbacks dos clientes para análise...", "status": "waiting"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        recent = feedbacks[:50]
        sentimentos = Counter([f.get('urgency', 'Neutro') for f in recent])
        categorias = Counter([f.get('category', 'Geral') for f in recent])
        feedback_list = "\n".join([f"- [{f.get('urgency')}] {get_feedback_preview(f.get('message', ''))[:80]}" for f in recent[:20]])

        prompt = f'''Você é analista de supermercados. Analise os feedbacks e gere resumo MUITO CURTO (máx 2 frases).
DADOS: Total: {len(recent)}, Sentimentos: {dict(sentimentos)}, Categorias: {dict(categorias)}
Feedbacks: {feedback_list}

Status (🟢 Ótimo / 🟡 Atenção / 🔴 Crítico) + Insight principal. Máximo 150 caracteres.'''

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100, temperature=0.7
        )
        summary = response.choices[0].message.content.strip()
        status = "critical" if "🔴" in summary else ("warning" if "🟡" in summary else "good")
        return {"summary": summary, "status": status}
    except Exception as e:
        print(f"Erro AI Pulse: {e}")
        return {"summary": "Não foi possível gerar análise.", "status": "error"}

def send_whatsapp_message(remote_jid, message):
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY or not EVOLUTION_INSTANCE_NAME:
        print(f"❌ Evolution API not configured!")
        return
    message = repair_mojibake(message)
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": remote_jid, "text": message}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"📤 Sent to {remote_jid}: {response.status_code}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")

def send_whatsapp_sticker(remote_jid: str, sticker_path: str) -> bool:
    """Envia uma figurinha (sticker) pelo WhatsApp via Evolution API."""
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY or not EVOLUTION_INSTANCE_NAME:
        print("❌ Evolution API não configurada para envio de sticker.")
        return False
    try:
        import base64
        with open(sticker_path, "rb") as f:
            sticker_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"❌ Erro ao ler sticker {sticker_path}: {e}")
        return False
    url = f"{EVOLUTION_API_URL}/message/sendSticker/{EVOLUTION_INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": remote_jid, "sticker": sticker_b64}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        print(f"🎭 Sticker enviado para {remote_jid}: {response.status_code}")
        return response.status_code in (200, 201)
    except Exception as e:
        print(f"❌ Erro ao enviar sticker para {remote_jid}: {e}")
        return False


# Caminho dos stickers do Pipico
STICKER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "stickers")
STICKER_SAUDACAO = os.path.join(STICKER_DIR, "pipico-saudacao.webp")
STICKER_PROMOCAO = os.path.join(STICKER_DIR, "pipico-promocao.webp")
STICKER_FECHADO = os.path.join(STICKER_DIR, "pipico-fechado.webp")
STICKER_TCHAU = os.path.join(STICKER_DIR, "pipico-tchau.webp")
STICKER_FEEDBACK = os.path.join(STICKER_DIR, "pipico-feedback.webp")
STICKER_COPA = os.path.join(STICKER_DIR, "pipico-copa.webp")

# Regex com word boundary — evita falsos positivos como "pergola" → "gol"
COPA_KEYWORDS_RE = re.compile(
    r'\b(?:copa do mundo|copa|selecao|brasil|neymar|ney|vini jr|vini|gol|futebol)\b'
)


def send_whatsapp_image(remote_jid: str, image_url: str, caption: str = "") -> None:
    """Envia uma imagem (banner de promoção) pelo WhatsApp via Evolution API."""
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY or not EVOLUTION_INSTANCE_NAME:
        print("❌ Evolution API não configurada para envio de imagem.")
        return
    url = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {
        "number": remote_jid,
        "mediatype": "image",
        "mimetype": "image/jpeg",
        "media": image_url,
        "fileName": "banner.jpg",
        "caption": caption
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        print(f"🖼️ Banner enviado para {remote_jid}: {response.status_code}")
    except Exception as e:
        print(f"❌ Erro ao enviar imagem para {remote_jid}: {e}")

# --- SPAM PROTECTION ---

rate_limit_store = defaultdict(list)
RATE_LIMIT_MAX = 15
RATE_LIMIT_WINDOW = 600

# Rate limit para áudios (evita queimar créditos do Whisper)
audio_limit_store = defaultdict(list)
AUDIO_LIMIT_MAX = 3
AUDIO_LIMIT_WINDOW = 3600  # 1 hora

def is_audio_limited(remote_jid):
    """Máximo 3 áudios por hora por número."""
    now = time_now()
    audio_limit_store[remote_jid] = [t for t in audio_limit_store[remote_jid] if now - t < AUDIO_LIMIT_WINDOW]
    if len(audio_limit_store[remote_jid]) >= AUDIO_LIMIT_MAX:
        return True
    audio_limit_store[remote_jid].append(now)
    return False

# Daily limit — máximo de mensagens por dia por número
daily_limit_store = defaultdict(list)
DAILY_LIMIT_MAX = 30
DAILY_LIMIT_WINDOW = 86400  # 24 horas

def is_daily_limited(remote_jid):
    """Máximo 30 mensagens por dia por número."""
    now = time_now()
    daily_limit_store[remote_jid] = [t for t in daily_limit_store[remote_jid] if now - t < DAILY_LIMIT_WINDOW]
    if len(daily_limit_store[remote_jid]) >= DAILY_LIMIT_MAX:
        return True
    daily_limit_store[remote_jid].append(now)
    return False

# Rate limit por volume de texto (evita sobrecarregar GPT)
char_volume_store = defaultdict(list)
CHAR_VOLUME_MAX = 3000
CHAR_VOLUME_WINDOW = 600  # 10 minutos

def is_char_volume_limited(remote_jid, text_length):
    """Limita volume total de caracteres por janela de tempo."""
    now = time_now()
    char_volume_store[remote_jid] = [
        (t, c) for t, c in char_volume_store[remote_jid]
        if now - t < CHAR_VOLUME_WINDOW
    ]
    total_chars = sum(c for _, c in char_volume_store[remote_jid])
    if total_chars + text_length > CHAR_VOLUME_MAX:
        return True
    char_volume_store[remote_jid].append((now, text_length))
    return False

# Rate limit GLOBAL
global_message_timestamps = []
GLOBAL_RATE_MAX = 100
GLOBAL_RATE_WINDOW = 60

def is_globally_rate_limited():
    """Proteção contra ataque coordenado com múltiplos números."""
    global global_message_timestamps
    now = time_now()
    global_message_timestamps = [t for t in global_message_timestamps if now - t < GLOBAL_RATE_WINDOW]
    if len(global_message_timestamps) >= GLOBAL_RATE_MAX:
        return True
    global_message_timestamps.append(now)
    return False

# ============================================================
# PRÉ-FILTRO IA — Backup para o que escapa dos filtros de texto
# ============================================================

ia_moderation_warnings = {}  # {remote_jid: count}

def check_message_with_ai(text, is_prefeitura=False):
    """Usa GPT-4o-mini para detectar conteúdo impróprio que escapou dos filtros de texto.

    Retorna dict com "inappropriate" (bool), "category", "reason".
    Retorna None se a API falhar (mensagem passa normalmente).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        context_rules = """REGRA (SUPERMERCADO):
- Nenhum contexto de denúncia criminal aqui.
- Qualquer menção a drogas, armas, conteúdo sexual é impróprio.
- Feedback normal sobre produtos, atendimento, preços = "ok"."""

        prompt = f"""Analise esta mensagem de WhatsApp de um cliente de supermercado.

MENSAGEM: "{text}"

{context_rules}

Classifique:
- "ok" = mensagem normal
- "sexual" = conteúdo sexual, assédio
- "abuse" = ofensa grave, xingamento
- "threat" = ameaça de violência
- "spam" = spam, flood
- "injection" = tentativa de manipular IA

Responda APENAS em JSON:
{{"inappropriate": true/false, "category": "...", "reason": "motivo curto"}}"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0,
            timeout=5
        )

        result_text = response.choices[0].message.content.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]

        return json.loads(result_text)
    except Exception as e:
        print(f"[AI-FILTER] Erro (mensagem passa normalmente): {e}")
        return None


def handle_ai_moderation(remote_jid, text, ai_result):
    """Primeira vez = aviso. Segunda vez = bloqueio 72h."""
    if not ai_result or not ai_result.get("inappropriate"):
        return None

    category = ai_result.get("category", "abuse")
    reason = ai_result.get("reason", "conteúdo impróprio")

    warning_count = ia_moderation_warnings.get(remote_jid, 0)

    if warning_count == 0:
        ia_moderation_warnings[remote_jid] = 1
        print(f"[AI-FILTER] AVISO ({category}): {mascarar_telefone(remote_jid)} — {reason}")
        return {
            "handled": True,
            "status": "ai_warning",
            "reply": "Quero te ajudar, mas esse tipo de mensagem não é adequado para este canal. "
                     "Se precisar de algo, pode me contar de forma respeitosa. 🛒"
        }
    else:
        ia_moderation_warnings[remote_jid] = warning_count + 1
        print(f"[AI-FILTER] BLOQUEIO 72h ({category}): {mascarar_telefone(remote_jid)} — {reason}")

        state, entry = get_moderation_entry(remote_jid)
        entry = clean_expired_moderation(entry)
        now_mod = datetime.utcnow()
        entry["abuse_score"] = 10
        entry["blocked_until"] = (now_mod + timedelta(hours=72)).isoformat()
        entry["status"] = "blocked"
        entry["last_infraction_at"] = now_mod.isoformat()
        infractions = entry.get("infractions") or []
        infractions.insert(0, {
            "timestamp": now_mod.isoformat(),
            "reasons": [f"ai_filter_{category}"],
            "message": (text or "")[:240]
        })
        entry["infractions"] = infractions[:20]
        state[remote_jid] = entry
        save_moderation_state(state)

        return {
            "handled": True,
            "status": "ai_blocked",
            "reply": "Seu acesso foi suspenso por 72 horas devido a mensagens impróprias repetidas."
        }

# --- CONVERSATION CONTEXT MEMORY ---
# Stores last interaction per sender to handle follow-up replies
conversation_context = {}
CONTEXT_TTL = 600  # 10 minutes

def get_context_path(remote_jid):
    os.makedirs(CONTEXT_STATE_DIR, exist_ok=True)
    sender_hash = hashlib.sha1((remote_jid or "").encode("utf-8")).hexdigest()
    return os.path.join(CONTEXT_STATE_DIR, f"{sender_hash}.json")

def save_context(remote_jid, intent, data=None):
    """Salva contexto da última interação para continuidade"""
    ctx = {
        'state': intent,
        'intent': intent,
        'data': data or {},
        'timestamp': time_now()
    }
    conversation_context[remote_jid] = ctx
    try:
        save_json(get_context_path(remote_jid), ctx)
    except Exception as e:
        print(f"[CONTEXT] save failed for {remote_jid}: {e}")

def get_context(remote_jid):
    """Retorna contexto ativo se existir e não estiver expirado"""
    ctx = conversation_context.get(remote_jid)
    if not ctx:
        persisted = load_json(get_context_path(remote_jid), None)
        if isinstance(persisted, dict):
            ctx = persisted
            conversation_context[remote_jid] = ctx
    if ctx and (time_now() - ctx['timestamp']) < CONTEXT_TTL:
        return ctx
    clear_context(remote_jid)
    return None

def clear_context(remote_jid):
    conversation_context.pop(remote_jid, None)
    try:
        path = get_context_path(remote_jid)
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"[CONTEXT] clear failed for {remote_jid}: {e}")

def is_affirmative(text):
    """Verifica se a mensagem é uma resposta afirmativa curta"""
    affirm = {'sim', 'quero', 'pode', 'manda', 'ok', 'claro', 'bora', 'isso',
              'por favor', 'pfv', 'pfvr', 'yes', 'mande', 'pode sim',
              'quero sim', 'sim quero', 'com certeza', 'pode ser', 'beleza',
              'blz', 'fechou', 'isso mesmo', 'exato', 'show', 's'}
    return text.lower().strip().rstrip('!.') in affirm

def looks_like_new_turn(text):
    normalized = normalize_text(text or "")
    if not normalized:
        return False
    if '?' in text:
        return True
    if any(keyword in normalized for keyword in PROMO_KEYWORDS):
        return True
    if any(keyword in normalized for keyword in GENERAL_QUESTION_HINTS):
        return True
    if any(keyword in normalized for keyword in PRODUCT_INQUIRY_PATTERNS):
        return True
    tokens = [token for token in re.split(r'\s+', normalized) if token]
    return len(tokens) >= 4

def is_rate_limited(remote_jid):
    now = time_now()
    rate_limit_store[remote_jid] = [t for t in rate_limit_store[remote_jid] if now - t < RATE_LIMIT_WINDOW]
    if len(rate_limit_store[remote_jid]) >= RATE_LIMIT_MAX:
        return True
    rate_limit_store[remote_jid].append(now)
    return False

def is_emoji_only(text):
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF\U0000FE00-\U0000FE0F\U0000200D\U00002764"
        "]+", flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub('', text).strip()
    return len(cleaned) == 0

MIN_MESSAGE_LENGTH = 3

# --- ROUTES ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        admin_user = os.getenv("ADMIN_USER", "admin")
        admin_pass = os.getenv("ADMIN_PASS", "nodedata123")
        if username == admin_user and password == admin_pass:
            session["logged_in"] = True
            return redirect("/")
        else:
            error = "Usuário ou senha incorretos."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
@login_required
def index():
    return render_template("data_node.html")

@app.route("/qrcode")
@login_required
def qrcode_page():
    return render_template("qrcode.html")

@app.route("/api/events")
@login_required
def get_events():
    feedbacks = get_feedbacks()
    categoria = request.args.get('categoria')
    loja = request.args.get('loja')
    prioridade = request.args.get('prioridade')
    if categoria:
        feedbacks = [f for f in feedbacks if f.get('category') == categoria]
    if loja:
        feedbacks = [f for f in feedbacks if f.get('loja') == loja]
    if prioridade:
        feedbacks = [f for f in feedbacks if f.get('urgency') == prioridade]
    status_filter = request.args.get('status')
    if status_filter:
        feedbacks = [f for f in feedbacks if f.get('status', 'aberto') == status_filter]
    return jsonify([serialize_feedback_for_api(f) for f in feedbacks])

# Cache para AI Pulse
ai_pulse_cache = {"data": None, "timestamp": None}

@app.route("/api/ai-pulse")
@login_required
def get_ai_pulse():
    global ai_pulse_cache
    now = datetime.utcnow()
    if ai_pulse_cache["data"] and ai_pulse_cache["timestamp"]:
        if (now - ai_pulse_cache["timestamp"]).total_seconds() < 60:
            return jsonify(ai_pulse_cache["data"])
    feedbacks = get_feedbacks()
    result = generate_ai_pulse(feedbacks)
    result["updated_at"] = now.isoformat()
    result["feedbacks_count"] = len(feedbacks)
    ai_pulse_cache = {"data": result, "timestamp": now}
    return jsonify(result)

@app.route("/api/config", methods=["GET"])
@login_required
def get_config_route():
    config = ensure_config_defaults(get_config())
    feedbacks = get_feedbacks()
    cat_counts = {}
    reg_counts = {}
    for fb in feedbacks:
        cat = fb.get('category', '')
        reg = fb.get('loja', fb.get('region', ''))
        if cat:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if reg:
            reg_counts[reg] = reg_counts.get(reg, 0) + 1
    for c in config.get('categories', []):
        c['count'] = cat_counts.get(c['name'], 0)
    for r in config.get('regions', []):
        r['count'] = reg_counts.get(r['name'], 0)
    return jsonify(config)

@app.route("/api/promotions", methods=["GET", "PUT"])
@login_required
def promotions_route():
    if request.method == "GET":
        return jsonify(get_promotions_from_config())

    data = request.get_json(silent=True) or {}
    promotions = save_promotions_config(data.get("day"), data.get("week"))
    return jsonify({
        "status": "saved",
        "promotions": promotions
    })

@app.route("/api/banners", methods=["GET"])
@login_required
def get_banners_route():
    """Retorna as URLs dos banners de promoção ativos."""
    return jsonify(get_banner_urls())

@app.route("/api/banners/upload", methods=["POST"])
@login_required
def upload_banner_route():
    """Recebe o upload de um banner, armazena no Supabase Storage e salva a URL."""
    banner_type = request.form.get("type")
    if banner_type not in ALL_BANNER_TYPES:
        return jsonify({"error": f"Tipo inválido. Use um de: {', '.join(ALL_BANNER_TYPES)}"}), 400

    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado."}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "Arquivo inválido."}), 400

    # Nome fixo por tipo — upsert substitui o banner anterior automaticamente
    storage_filename = f"{banner_type}.jpg"
    mimetype = file.mimetype or "image/jpeg"

    # Usa o cliente admin (service_role) para o upload — necessário para
    # contornar as políticas de RLS do Supabase Storage
    sb_admin = get_supabase_admin()
    if not sb_admin:
        return jsonify({"error": "Supabase indisponível."}), 500

    try:
        file_bytes = file.read()
        sb_admin.storage.from_(BANNER_BUCKET).upload(
            path=storage_filename,
            file=file_bytes,
            file_options={"content-type": mimetype, "upsert": "true"}
        )
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BANNER_BUCKET}/{storage_filename}"
        save_banner_url(banner_type, public_url)
        print(f"🖼️ Banner '{banner_type}' enviado com sucesso: {public_url}")
        return jsonify({"status": "ok", "url": public_url})
    except Exception as e:
        print(f"❌ Erro no upload do banner: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/banners/delete", methods=["POST"])
@login_required
def delete_banner_route():
    """Remove um banner do Supabase Storage e apaga a URL do banco."""
    data = request.get_json(silent=True) or {}
    banner_type = data.get("type")
    if banner_type not in ALL_BANNER_TYPES:
        return jsonify({"error": f"Tipo inválido. Use um de: {', '.join(ALL_BANNER_TYPES)}"}), 400

    storage_filename = f"{banner_type}.jpg"

    sb_admin = get_supabase_admin()
    if sb_admin:
        try:
            sb_admin.storage.from_(BANNER_BUCKET).remove([storage_filename])
        except Exception as e:
            # O arquivo pode não existir no storage — ignoramos e continuamos
            print(f"Aviso ao remover arquivo do storage: {e}")

    delete_banner_url(banner_type)
    return jsonify({"status": "deleted"})

@app.route("/api/products")
@login_required
def api_products():
    return jsonify(get_produtos())

@app.route("/api/products/search")
@login_required
def api_products_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])
    return jsonify(buscar_produto_local(q))

@app.route("/api/waitlist")
@login_required
def api_waitlist():
    return jsonify(get_lista_espera_count())

@app.route("/api/alerts")
@login_required
def api_alerts():
    """Auto-alerts for managers"""
    feedbacks = get_feedbacks()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    today_feedbacks = [f for f in feedbacks if f.get('timestamp', '').startswith(today)]

    alerts = []
    # Alert: category with 5+ complaints today
    cat_count = Counter([f.get('category') for f in today_feedbacks if f.get('urgency') in ['Urgente', 'Critico']])
    for cat, count in cat_count.items():
        if count >= 3:
            alerts.append({"type": "warning", "message": f"{cat} com {count} reclamações hoje!", "count": count, "category": cat})

    # Alert: overall NPS drop
    negatives = len([f for f in today_feedbacks if f.get('urgency') in ['Urgente', 'Critico']])
    total = len(today_feedbacks)
    if total >= 5 and negatives / total > 0.5:
        alerts.append({"type": "critical", "message": f"NPS baixo hoje! {negatives}/{total} feedbacks negativos", "count": negatives})

    return jsonify(alerts)

@app.route("/api/stores/compare")
@login_required
def api_stores_compare():
    """Compare NPS across stores"""
    feedbacks = get_feedbacks()
    stores = {}
    for f in feedbacks:
        loja = f.get('loja', 'Matriz')
        if loja not in stores:
            stores[loja] = {'total': 0, 'positivo': 0, 'negativo': 0}
        stores[loja]['total'] += 1
        if f.get('urgency') == 'Positivo':
            stores[loja]['positivo'] += 1
        elif f.get('urgency') in ['Urgente', 'Critico']:
            stores[loja]['negativo'] += 1

    result = []
    for loja, data in stores.items():
        nps = 0
        if data['total'] > 0:
            nps = round(((data['positivo'] - data['negativo']) / data['total']) * 100)
        result.append({"loja": loja, "nps": nps, **data})
    result.sort(key=lambda x: x['nps'], reverse=True)
    return jsonify(result)

@app.route("/api/products/top-searched")
@login_required
def api_top_searched():
    """Top searched products (tracked via search counter)"""
    feedbacks = get_feedbacks()
    product_mentions = []
    for f in feedbacks:
        topic = (f.get('topic') or '').strip()
        if topic:
            product_mentions.append(topic)
        msg = get_feedback_customer_text(f.get('message', '')).lower()
        produtos = get_produtos()
        for p in produtos:
            if p.get('nome', '').lower() in msg:
                product_mentions.append(p['nome'])
    counter = Counter(product_mentions)
    return jsonify([{"produto": k, "buscas": v} for k, v in counter.most_common(10)])

@app.route("/api/insights")
@login_required
def get_insights():
    feedbacks = get_feedbacks()
    elogios = {}
    problemas = {}
    for fb in feedbacks:
        texto = get_feedback_customer_text(fb.get('message', ''))
        sentimento = fb.get('urgency', 'Neutro')
        categoria = fb.get('category', 'Outros')
        display = categoria
        if sentimento == 'Positivo':
            if display not in elogios:
                elogios[display] = {'count': 0, 'topic': display}
            elogios[display]['count'] += 1
        if sentimento in ['Critico', 'Urgente']:
            if display not in problemas:
                problemas[display] = {'count': 0, 'topic': display}
            problemas[display]['count'] += 1
    top_e = [v for k, v in sorted(elogios.items(), key=lambda x: x[1]['count'], reverse=True)[:3]]
    top_p = [v for k, v in sorted(problemas.items(), key=lambda x: x[1]['count'], reverse=True)[:3]]
    return jsonify({'top_elogios': top_e, 'top_problemas': top_p})

@app.route("/api/export/csv")
@login_required
def export_csv():
    feedbacks = get_feedbacks()
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=['id', 'message', 'category', 'urgency', 'timestamp', 'status', 'sender', 'name', 'loja'])
    writer.writeheader()
    for fb in feedbacks:
        writer.writerow({
            'id': fb.get('id'), 'message': get_feedback_customer_text(fb.get('message', '')), 'category': fb.get('category'),
            'urgency': fb.get('urgency'), 'timestamp': fb.get('timestamp'),
            'status': fb.get('status', 'aberto'), 'sender': fb.get('sender'),
            'name': fb.get('name'), 'loja': fb.get('loja', 'Matriz')
        })
    output.seek(0)
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename=feedbacks_supermercado.csv'
    }

@app.route("/api/export/json")
@login_required
def export_json():
    feedbacks = get_feedbacks()
    return jsonify(feedbacks), 200, {'Content-Disposition': 'attachment; filename=feedbacks_supermercado.json'}

@app.route("/api/feedback/<int:feedback_id>/status", methods=["PUT"])
@login_required
def update_feedback_status(feedback_id):
    feedback = get_feedback_by_id(feedback_id)
    if not feedback:
        return jsonify({"error": "Feedback não encontrado"}), 404
    data = request.json
    new_status = data.get('status')
    if new_status not in ['aberto', 'em_andamento', 'resolvido']:
        return jsonify({"error": "Status inválido"}), 400
    updates = {'status': new_status}
    if new_status == 'resolvido':
        updates['resolved_at'] = datetime.now().strftime("%d/%m/%y %H:%M")
    else:
        updates['resolved_at'] = None
    if update_feedback(feedback_id, updates):
        if new_status == 'resolvido':
            clear_handoff_for_feedback(feedback)
        return jsonify({"success": True, "status": new_status})
    return jsonify({"error": "Feedback não encontrado"}), 404

@app.route("/api/feedback/<int:feedback_id>/handoff", methods=["PUT"])
@login_required
def toggle_feedback_handoff(feedback_id):
    feedback = get_feedback_by_id(feedback_id)
    if not feedback:
        return jsonify({"error": "Feedback não encontrado"}), 404

    data = request.json or {}
    enabled = bool(data.get('enabled'))
    handoff_entry = set_handoff_entry(feedback, enabled)

    if enabled and feedback.get('status') == 'aberto':
        update_feedback(feedback_id, {
            'status': 'em_andamento',
            'updated_at': datetime.utcnow().isoformat()
        })
    elif not enabled:
        update_feedback(feedback_id, {
            'updated_at': datetime.utcnow().isoformat()
        })

    return jsonify({
        "success": True,
        "human_takeover": bool(handoff_entry),
        "feedback_id": feedback_id
    })

# --- MASS RECOVERY ---

@app.route("/api/generate-recovery-message", methods=["POST"])
@login_required
def generate_recovery_message():
    """Generate AI recovery message for mass client outreach"""
    data = request.json or {}
    category = data.get('category', 'Geral')
    urgency = data.get('urgency', 'Crítico')
    count = data.get('count', 0)
    sample_messages = data.get('samples', [])
    store_name = data.get('store_name', 'nosso supermercado')
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        # Fallback template
        msg = f"Olá! 👋\n\nAqui é a equipe do {store_name}. Recebemos seu feedback sobre {category} e queremos te dizer: você foi ouvido!\n\nJá estamos tomando medidas para melhorar. Como agradecimento, você tem 10% de desconto nesta seção na sua próxima visita.\n\nMostre esta mensagem no caixa. Obrigado por nos ajudar a melhorar! 💚"
        return jsonify({"message": msg, "generated": False})
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        samples_text = "\n".join([f'- "{s[:100]}"' for s in sample_messages[:5]])
        
        prompt = f'''Você é o gerente de um supermercado e precisa escrever UMA mensagem de WhatsApp para enviar a {count} clientes que reclamaram sobre "{category}" (nível: {urgency}).

Exemplos de reclamações recebidas:
{samples_text}

REGRAS:
- Mensagem CURTA (máx 500 caracteres) para WhatsApp
- Tom: empático, profissional, pessoal (use "você", não "vocês") 
- Comece com saudação + nome do mercado
- Reconheça o problema ESPECÍFICO (não genérico)
- Diga qual AÇÃO CONCRETA foi tomada (invente algo realista)
- Ofereça um pequeno incentivo (10% desconto na categoria OU convite para verificar a melhoria)
- Termine com agradecimento + emoji verde ou coração
- Use [NOME] como placeholder para o nome do cliente
- Formato WhatsApp: use *negrito* e emojis moderados
- NÃO use markdown, NÃO use # ou ##

Escreva APENAS a mensagem, sem explicações.'''
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300, temperature=0.8
        )
        msg = response.choices[0].message.content.strip()
        return jsonify({"message": msg, "generated": True})
        
    except Exception as e:
        print(f"❌ Recovery message error: {e}")
        msg = f"Olá [NOME]! 👋\n\nAqui é a equipe do {store_name}. Recebemos seu feedback sobre {category} e queremos te dizer: *você foi ouvido!*\n\nJá estamos tomando medidas para melhorar sua experiência. Como agradecimento pela sua atenção, você tem *10% de desconto* na seção {category} na sua próxima visita.\n\nMostre esta mensagem no caixa. Obrigado por nos ajudar a melhorar! 💚"
        return jsonify({"message": msg, "generated": False})

# --- PREMIUM ANALYTICS ---

CONCORRENTES = {
    'assai': 'Assaí', 'assaí': 'Assaí', 'atacadao': 'Atacadão', 'atacadão': 'Atacadão',
    'carrefour': 'Carrefour', 'extra': 'Extra', 'pão de açúcar': 'Pão de Açúcar',
    'pao de acucar': 'Pão de Açúcar', 'big': 'Big', 'sam\'s': "Sam's Club", 'sams': "Sam's Club",
    'makro': 'Makro', 'bretas': 'Bretas', 'dia': 'Dia', 'aldi': 'Aldi', 'fort': 'Fort Atacadista',
    'savegnago': 'Savegnago', 'sonda': 'Sonda', 'prezunic': 'Prezunic', 'guanabara': 'Guanabara',
    'mundial': 'Mundial', 'condor': 'Condor', 'muffato': 'Muffato', 'angeloni': 'Angeloni',
    'coop': 'Coop', 'supernosso': 'SuperNosso', 'epa': 'EPA', 'mateus': 'Mateus',
    'zaffari': 'Zaffari', 'BH': 'BH', 'pague menos': 'Pague Menos', 'oba': 'Oba Hortifruti',
    'outro mercado': 'Outro Mercado', 'mercado vizinho': 'Outro Mercado',
    'concorrente': 'Concorrente Genérico', 'concorrência': 'Concorrente Genérico',
    'no outro': 'Outro Mercado', 'lá na frente': 'Outro Mercado'
}

CONTEXTOS_CONCORRENCIA = {
    'preco': ['mais barato', 'mais caro', 'preço melhor', 'preco melhor', 'mais conta', 'mais em conta', 'mais acessível', 'mais acessivel', 'cobram menos', 'metade do preço'],
    'variedade': ['tem mais', 'mais opção', 'mais opcao', 'mais variedade', 'mais produto', 'maior sortimento', 'maior seleção'],
    'qualidade': ['melhor qualidade', 'mais fresco', 'mais fresquinho', 'produto melhor', 'qualidade melhor'],
    'atendimento': ['atende melhor', 'mais educado', 'tratam melhor', 'atendimento melhor', 'mais simpático'],
    'estrutura': ['mais organizado', 'mais limpo', 'mais bonito', 'mais moderno', 'melhor estrutura'],
    'promocao': ['promoção melhor', 'oferta melhor', 'mais promoção', 'mais oferta', 'desconto melhor']
}

def detectar_concorrentes(texto):
    """Detecta menções a concorrentes e o contexto"""
    texto_lower = texto.lower()
    encontrados = []
    for chave, nome in CONCORRENTES.items():
        if chave in texto_lower:
            contexto = 'geral'
            for ctx_tipo, palavras in CONTEXTOS_CONCORRENCIA.items():
                if any(p in texto_lower for p in palavras):
                    contexto = ctx_tipo
                    break
            encontrados.append({'concorrente': nome, 'contexto': contexto})
    return encontrados

@app.route("/api/analytics/top")
@login_required
def api_analytics_top():
    """Top compliments and problems - used by dashboard"""
    feedbacks = get_feedbacks()
    elogios = {}
    problemas = {}
    for fb in feedbacks:
        cat = fb.get('category', 'Outros')
        urgency = fb.get('urgency', 'Neutro')
        if urgency == 'Positivo':
            elogios[cat] = elogios.get(cat, 0) + 1
        elif urgency in ['Critico', 'Urgente']:
            problemas[cat] = problemas.get(cat, 0) + 1
    top_e = sorted(elogios.items(), key=lambda x: x[1], reverse=True)[:3]
    top_p = sorted(problemas.items(), key=lambda x: x[1], reverse=True)[:3]
    return jsonify({
        'compliments': [{'topic': k, 'count': v} for k, v in top_e],
        'problems': [{'topic': k, 'count': v} for k, v in top_p]
    })

@app.route("/api/analytics/competitors")
@login_required
def api_analytics_competitors():
    """Radar de Concorrência - detect competitor mentions in feedbacks"""
    feedbacks = get_feedbacks()
    competitor_data = {}
    recent_mentions = []
    
    for fb in feedbacks:
        msg = get_feedback_customer_text(fb.get('message', ''))
        encontrados = detectar_concorrentes(msg)
        for e in encontrados:
            nome = e['concorrente']
            ctx = e['contexto']
            if nome not in competitor_data:
                competitor_data[nome] = {'total': 0, 'contexts': {}, 'trend': []}
            competitor_data[nome]['total'] += 1
            competitor_data[nome]['contexts'][ctx] = competitor_data[nome]['contexts'].get(ctx, 0) + 1
            competitor_data[nome]['trend'].append(fb.get('timestamp', ''))
            recent_mentions.append({
                'concorrente': nome,
                'contexto': ctx,
                'mensagem': msg[:120],
                'timestamp': fb.get('timestamp', ''),
                'urgency': fb.get('urgency', 'Neutro')
            })
    
    # Calculate trend (last 7 days vs previous 7 days)
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    
    for nome, data in competitor_data.items():
        recent_count = 0
        older_count = 0
        for ts in data['trend']:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00')) if 'T' in ts else datetime.strptime(ts, '%d/%m/%y %H:%M')
                if dt.replace(tzinfo=None) > week_ago:
                    recent_count += 1
                elif dt.replace(tzinfo=None) > two_weeks_ago:
                    older_count += 1
            except:
                pass
        if older_count > 0:
            data['trend_pct'] = round(((recent_count - older_count) / older_count) * 100)
        else:
            data['trend_pct'] = 100 if recent_count > 0 else 0
        del data['trend']  # don't send raw timestamps
        # Sort contexts
        data['top_context'] = max(data['contexts'], key=data['contexts'].get) if data['contexts'] else 'geral'
    
    # Sort by total mentions
    sorted_competitors = sorted(competitor_data.items(), key=lambda x: x[1]['total'], reverse=True)
    
    return jsonify({
        'competitors': [{'name': k, **v} for k, v in sorted_competitors],
        'recent_mentions': sorted(recent_mentions, key=lambda x: x.get('timestamp', ''), reverse=True)[:20],
        'total_mentions': sum(d['total'] for d in competitor_data.values())
    })

@app.route("/api/analytics/critical-hours")
@login_required
def api_analytics_critical_hours():
    """Mapa de Horário Crítico - complaints by hour and sector"""
    feedbacks = get_feedbacks()
    heatmap = {}  # {hour: {category: count}}
    
    for fb in feedbacks:
        if fb.get('urgency') not in ['Urgente', 'Critico']:
            continue
        ts = fb.get('timestamp', '')
        hour = None
        try:
            if 'T' in ts:
                hour = datetime.fromisoformat(ts.replace('Z', '+00:00')).hour
            elif '/' in ts:
                hour = int(ts.split(' ')[1].split(':')[0])
        except:
            continue
        if hour is None:
            continue
        h_key = f"{hour:02d}:00"
        cat = fb.get('category', 'Geral')
        if h_key not in heatmap:
            heatmap[h_key] = {}
        heatmap[h_key][cat] = heatmap[h_key].get(cat, 0) + 1
    
    # Find peak hours
    hour_totals = {h: sum(cats.values()) for h, cats in heatmap.items()}
    peak_hours = sorted(hour_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Find worst category per peak hour
    insights = []
    for hour, total in peak_hours:
        cats = heatmap[hour]
        worst_cat = max(cats, key=cats.get)
        insights.append({
            'hour': hour,
            'total_complaints': total,
            'worst_category': worst_cat,
            'worst_count': cats[worst_cat],
            'breakdown': cats
        })
    
    return jsonify({
        'heatmap': heatmap,
        'peak_hours': insights,
        'total_analyzed': len([f for f in feedbacks if f.get('urgency') in ['Urgente', 'Critico']])
    })

@app.route("/api/analytics/crisis-trends")
@login_required
def api_analytics_crisis_trends():
    """Alerta de Crise Emergente - detect abnormal complaint patterns"""
    feedbacks = get_feedbacks()
    now = datetime.utcnow()
    h48 = now - timedelta(hours=48)
    h96 = now - timedelta(hours=96)
    
    recent = []
    older = []
    for fb in feedbacks:
        ts = fb.get('timestamp', '')
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00')) if 'T' in ts else datetime.strptime(ts, '%d/%m/%y %H:%M')
            dt = dt.replace(tzinfo=None)
            if dt > h48:
                recent.append(fb)
            elif dt > h96:
                older.append(fb)
        except:
            pass
    
    # Count categories in both periods
    recent_cats = Counter([f.get('category', 'Geral') for f in recent if f.get('urgency') in ['Urgente', 'Critico']])
    older_cats = Counter([f.get('category', 'Geral') for f in older if f.get('urgency') in ['Urgente', 'Critico']])
    
    # Detect trending keywords 
    recent_words = Counter()
    for fb in recent:
        if fb.get('urgency') in ['Urgente', 'Critico']:
            words = [w for w in get_feedback_customer_text(fb.get('message', '')).lower().split() if len(w) > 4]
            recent_words.update(words)
    
    crises = []
    for cat, count in recent_cats.items():
        old_count = older_cats.get(cat, 0)
        if old_count > 0:
            growth = round(((count - old_count) / old_count) * 100)
        else:
            growth = 100 if count >= 2 else 0
        
        if growth >= 50 or count >= 3:
            sample_msgs = [get_feedback_preview(f.get('message', ''))[:80] for f in recent if f.get('category') == cat and f.get('urgency') in ['Urgente', 'Critico']][:3]
            crises.append({
                'category': cat,
                'recent_count': count,
                'previous_count': old_count,
                'growth_pct': growth,
                'severity': 'critical' if growth >= 200 or count >= 5 else 'warning',
                'sample_messages': sample_msgs
            })
    
    crises.sort(key=lambda x: x['growth_pct'], reverse=True)
    
    # Trending negative keywords
    trending_words = [{'word': w, 'count': c} for w, c in recent_words.most_common(10) if c >= 2]
    
    return jsonify({
        'crises': crises,
        'trending_words': trending_words,
        'period': '48h',
        'total_recent_complaints': len([f for f in recent if f.get('urgency') in ['Urgente', 'Critico']]),
        'total_previous_complaints': len([f for f in older if f.get('urgency') in ['Urgente', 'Critico']])
    })

@app.route("/api/analytics/roi")
@login_required
def api_analytics_roi():
    """ROI do Feedback - calculate monetary value of resolved feedbacks"""
    feedbacks = get_feedbacks()
    AVG_MONTHLY_VALUE = 500  # R$ average monthly spend per customer
    AVG_LIFETIME_MONTHS = 12  # months a customer stays loyal
    
    total = len(feedbacks)
    resolved = len([f for f in feedbacks if f.get('status') == 'resolvido'])
    critical_resolved = len([f for f in feedbacks if f.get('status') == 'resolvido' and f.get('urgency') in ['Urgente', 'Critico']])
    in_progress = len([f for f in feedbacks if f.get('status') == 'em_andamento'])
    open_critical = len([f for f in feedbacks if f.get('status', 'aberto') == 'aberto' and f.get('urgency') in ['Urgente', 'Critico']])
    
    # Retained revenue = resolved critical customers * avg monthly value
    monthly_saved = critical_resolved * AVG_MONTHLY_VALUE
    annual_saved = critical_resolved * AVG_MONTHLY_VALUE * AVG_LIFETIME_MONTHS
    
    # At-risk revenue = open critical/urgent feedbacks * avg monthly value
    at_risk_monthly = open_critical * AVG_MONTHLY_VALUE
    at_risk_annual = open_critical * AVG_MONTHLY_VALUE * AVG_LIFETIME_MONTHS
    
    # Resolution rate
    actionable = len([f for f in feedbacks if f.get('urgency') in ['Urgente', 'Critico']])
    resolution_rate = round((critical_resolved / actionable * 100)) if actionable > 0 else 0
    
    # Response time (avg hours from creation to resolution)
    resolution_times = []
    for f in feedbacks:
        if f.get('status') == 'resolvido' and f.get('resolved_at') and f.get('timestamp'):
            try:
                created = datetime.fromisoformat(f['timestamp'].replace('Z', '+00:00')).replace(tzinfo=None) if 'T' in f['timestamp'] else datetime.strptime(f['timestamp'], '%d/%m/%y %H:%M')
                resolved_at = datetime.strptime(f['resolved_at'], '%d/%m/%y %H:%M')
                hours = (resolved_at - created).total_seconds() / 3600
                if hours > 0:
                    resolution_times.append(hours)
            except:
                pass
    avg_resolution_hours = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0
    
    return jsonify({
        'monthly_saved': monthly_saved,
        'annual_saved': annual_saved,
        'at_risk_monthly': at_risk_monthly,
        'at_risk_annual': at_risk_annual,
        'resolved_count': resolved,
        'critical_resolved': critical_resolved,
        'in_progress': in_progress,
        'open_critical': open_critical,
        'resolution_rate': resolution_rate,
        'avg_resolution_hours': avg_resolution_hours,
        'total_feedbacks': total,
        'avg_customer_value': AVG_MONTHLY_VALUE
    })

@app.route("/api/analytics/churn")
@login_required
def api_analytics_churn():
    """Detector de Êxodo - track customer churn risk"""
    feedbacks = get_feedbacks()
    now = datetime.utcnow()
    
    # Group by sender
    customers = {}
    for fb in feedbacks:
        sender = fb.get('sender', '')
        if not sender:
            continue
        if sender not in customers:
            customers[sender] = {'name': fb.get('name', 'Cliente'), 'feedbacks': [], 'total': 0}
        customers[sender]['total'] += 1
        customers[sender]['feedbacks'].append(fb)
    
    churn_risks = []
    loyal_at_risk = []
    
    for sender, data in customers.items():
        if data['total'] < 2:
            continue  # Need 2+ interactions to track
        
        # Sort by timestamp
        fbs = sorted(data['feedbacks'], key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Check last contact date
        last_ts = fbs[0].get('timestamp', '')
        try:
            last_dt = datetime.fromisoformat(last_ts.replace('Z', '+00:00')).replace(tzinfo=None) if 'T' in last_ts else datetime.strptime(last_ts, '%d/%m/%y %H:%M')
            days_since = (now - last_dt).days
        except:
            continue
        
        # Check sentiment trend
        recent_sentiments = [f.get('urgency', 'Neutro') for f in fbs[:5]]
        negative_count = sum(1 for s in recent_sentiments if s in ['Urgente', 'Critico'])
        positive_count = sum(1 for s in recent_sentiments if s == 'Positivo')
        
        # Determine risk level
        risk_score = 0
        risk_reasons = []
        
        if days_since > 14 and data['total'] >= 3:
            risk_score += 40
            risk_reasons.append(f'Inativo há {days_since} dias')
        elif days_since > 7 and data['total'] >= 3:
            risk_score += 20
            risk_reasons.append(f'Sem contato há {days_since} dias')
        
        if negative_count >= 2:
            risk_score += 30
            risk_reasons.append(f'{negative_count} feedbacks negativos recentes')
        
        if len(fbs) >= 2 and fbs[0].get('urgency') in ['Urgente', 'Critico'] and fbs[1].get('urgency') in ['Urgente', 'Critico']:
            risk_score += 20
            risk_reasons.append('Últimos feedbacks consecutivos negativos')
        
        # Check if mentioned competitor
        for fb in fbs[:3]:
            if detectar_concorrentes(get_feedback_customer_text(fb.get('message', ''))):
                risk_score += 15
                risk_reasons.append('Mencionou concorrente')
                break
        
        if risk_score >= 30:
            display_sender = sender.replace('@s.whatsapp.net', '')
            churn_risks.append({
                'name': data['name'],
                'phone': display_sender,
                'total_interactions': data['total'],
                'days_since_last': days_since,
                'risk_score': min(risk_score, 100),
                'risk_level': 'critical' if risk_score >= 60 else 'warning',
                'reasons': risk_reasons,
                'last_message': get_feedback_preview(fbs[0].get('message', ''))[:100],
                'last_urgency': fbs[0].get('urgency', 'Neutro')
            })
    
    churn_risks.sort(key=lambda x: x['risk_score'], reverse=True)
    
    return jsonify({
        'at_risk_customers': churn_risks[:20],
        'total_tracked': len(customers),
        'total_at_risk': len(churn_risks),
        'high_risk': len([c for c in churn_risks if c['risk_level'] == 'critical']),
        'medium_risk': len([c for c in churn_risks if c['risk_level'] == 'warning'])
    })

# --- WEBHOOK ---

# Debounce: acumula mensagens do mesmo remetente por N segundos antes de processar.
# Evita que "Oi" + "Boa noite" enviados em sequência sejam tratados como 2 mensagens separadas.
_message_buffer = {}
_message_buffer_lock = threading.Lock()
MESSAGE_BATCH_DELAY = 3  # segundos de espera para juntar mensagens


def _flush_message_buffer(remote_jid):
    """Processa todas as mensagens acumuladas do remetente após o delay."""
    with _message_buffer_lock:
        entry = _message_buffer.pop(remote_jid, None)
    if not entry:
        return
    combined_text = " ".join(entry["messages"])
    push_name = entry["push_name"]
    is_audio = entry.get("is_audio", False)
    try:
        with app.app_context():
            process_webhook_text_message(remote_jid, push_name, combined_text, is_audio=is_audio)
    except Exception as e:
        print(f"[DEBOUNCE] Erro ao processar buffer de {mascarar_telefone(remote_jid)}: {e}")


def buffer_and_process_message(remote_jid, push_name, text, is_audio=False):
    """Acumula mensagens do mesmo remetente e processa após delay de debounce."""
    with _message_buffer_lock:
        if remote_jid in _message_buffer:
            _message_buffer[remote_jid]["timer"].cancel()
            _message_buffer[remote_jid]["messages"].append(text)
            if is_audio:
                _message_buffer[remote_jid]["is_audio"] = True
            print(f"[DEBOUNCE] +1 msg para {mascarar_telefone(remote_jid)} (total: {len(_message_buffer[remote_jid]['messages'])})")
        else:
            _message_buffer[remote_jid] = {
                "messages": [text],
                "push_name": push_name,
                "is_audio": is_audio,
            }
        timer = threading.Timer(MESSAGE_BATCH_DELAY, _flush_message_buffer, args=[remote_jid])
        _message_buffer[remote_jid]["timer"] = timer
        timer.start()


def process_webhook_text_message(remote_jid, push_name, text, is_audio=False):
    with sender_processing_lock(remote_jid) as lock_acquired:
        if not lock_acquired:
            print(f"[SENDER-LOCK] Timeout waiting for {remote_jid}")
            return jsonify({"status": "sender_busy"}), 202
        if is_audio:
            text = normalize_audio_transcript(text, remote_jid)
        return _process_webhook_text_message_locked(remote_jid, push_name, text)

def _process_webhook_text_message_locked(remote_jid, push_name, text):
    restriction = get_active_restriction(remote_jid)
    if restriction:
        send_whatsapp_message(remote_jid, restriction["reply"])
        return jsonify({"status": restriction["status"]}), 200

    # Trunca mensagens muito longas (protege créditos GPT)
    if len(text) > 600:
        text = text[:600]

    # --- BOAS-VINDAS QR CODE ---
    # Detecta a mensagem automática gerada pelo QR Code de feedback.
    # Quando o cliente escaneia o QR, o WhatsApp abre com uma mensagem pré-preenchida
    # contendo "vim pelo qr code". Aqui interceptamos esse texto para dar boas-vindas
    # antes de qualquer processamento — o feedback de verdade virá na próxima mensagem.
    if "vim pelo qr code" in text.lower():
        boas_vindas = (
            "Olá! Aqui é o Seu Pipico, do Atacaforte! Que bom ter você aqui! 🛒\n\n"
            "Por aqui você pode:\n"
            "🔹 Ver as *promoções do dia e do mês*\n"
            "🔹 Dar sua *opinião* sobre o mercado\n"
            "🔹 Tirar *dúvidas* sobre o Atacaforte\n\n"
            "O que você precisa hoje?"
        )
        send_whatsapp_message(remote_jid, boas_vindas)
        if os.path.exists(STICKER_SAUDACAO):
            send_whatsapp_sticker(remote_jid, STICKER_SAUDACAO)
        print(f"[QR-WELCOME] Boas-vindas enviadas para {remote_jid}")
        return jsonify({"status": "qr_welcome_sent"}), 200

    ctx = get_context(remote_jid)

    # Permite respostas curtas (ex.: "1"/"2") quando há contexto pendente.
    # Saudações curtas ("oi", "hi") também passam mesmo sem contexto.
    is_short_greeting = normalize_text(text.strip()).rstrip('!.?,') in GREETING_WORDS
    if len(text.strip()) < MIN_MESSAGE_LENGTH and not ctx and not is_short_greeting:
        return jsonify({"status": "ignored_too_short"}), 200
    if is_emoji_only(text) and not ctx:
        return jsonify({"status": "ignored_emoji_only"}), 200

    abuse = analyze_abuse_message(text)
    if abuse["score"] > 0:
        moderation = register_moderation_infraction(
            remote_jid,
            text,
            abuse["reasons"],
            abuse["score"],
            severe=abuse["severe"]
        )
        send_whatsapp_message(remote_jid, moderation["reply"])
        return jsonify({"status": moderation["status"]}), 200

    # Filtro de irrelevância e prompt injection
    if is_mensagem_irrelevante(text):
        send_whatsapp_message(remote_jid, "Sou o Seu Pipico, atendente do Atacaforte! Posso te ajudar com feedbacks, promoções e dúvidas sobre o mercado. 🛒")
        return jsonify({"status": "irrelevant_blocked"}), 200

    # Filtro de conteúdo impróprio — bloqueio 72h
    if is_improper_content(text):
        print(f"[IMPROPER] Bloqueio imediato: {mascarar_telefone(remote_jid)}")
        state, entry = get_moderation_entry(remote_jid)
        entry = clean_expired_moderation(entry)
        now_mod = datetime.utcnow()
        entry["abuse_score"] = 10
        entry["blocked_until"] = (now_mod + timedelta(hours=72)).isoformat()
        entry["status"] = "blocked"
        entry["last_infraction_at"] = now_mod.isoformat()
        infractions = entry.get("infractions") or []
        infractions.insert(0, {
            "timestamp": now_mod.isoformat(),
            "reasons": ["conteudo_improprio"],
            "message": (text or "")[:240]
        })
        entry["infractions"] = infractions[:20]
        state[remote_jid] = entry
        save_moderation_state(state)
        send_whatsapp_message(
            remote_jid,
            "Este canal é exclusivo para atendimento do Atacaforte Supermercado. "
            "Seu acesso foi suspenso por 72 horas devido ao conteúdo da mensagem."
        )
        return jsonify({"status": "blocked_improper"}), 200

    if is_rate_limited(remote_jid):
        moderation = register_moderation_infraction(
            remote_jid,
            text,
            ["spam"],
            2,
            severe=False
        )
        send_whatsapp_message(remote_jid, moderation["reply"])
        return jsonify({"status": "rate_limited"}), 200

    # Daily limit
    if is_daily_limited(remote_jid):
        send_whatsapp_message(remote_jid, "Você já mandou muitas mensagens hoje. Tente novamente amanhã! 😊")
        return jsonify({"status": "daily_limited"}), 200

    # Rate limit de volume de texto
    if is_char_volume_limited(remote_jid, len(text)):
        send_whatsapp_message(remote_jid, "Recebi muitas mensagens longas em sequência. Aguarde alguns minutos e tente novamente. 😊")
        return jsonify({"status": "char_volume_limited"}), 200

    # Bloqueio total de URLs
    if contains_url(text):
        print(f"[URL-BLOCKED] Link detectado de {mascarar_telefone(remote_jid)}: {text[:60]}")
        send_whatsapp_message(
            remote_jid,
            "Por segurança, não aceitamos mensagens com links. "
            "Descreva o que precisa por texto, sem links. 😊"
        )
        return jsonify({"status": "url_blocked"}), 200

    feedbacks = get_feedbacks()
    msg_hash = hashlib.md5(f"{text}{remote_jid}".encode()).hexdigest()
    existing = {
        hashlib.md5(f"{msg}{fb.get('sender', '')}".encode()).hexdigest()
        for fb in feedbacks
        for msg in (get_feedback_customer_messages(fb.get('message', '')) or [''])
    }
    promo_choice_context = bool(
        ctx
        and (ctx.get('state') or ctx.get('intent')) == 'awaiting_promo_choice'
        and normalize_text(text or "") in {'1', '2'}
    )
    if msg_hash in existing and not promo_choice_context:
        return jsonify({"status": "ignored_duplicate"}), 200

    # --- PRÉ-FILTRO IA (backup para o que escapou dos filtros de texto) ---
    ai_moderation = check_message_with_ai(text, is_prefeitura=False)
    ai_action = handle_ai_moderation(remote_jid, text, ai_moderation)
    if ai_action and ai_action.get("handled"):
        send_whatsapp_message(remote_jid, ai_action["reply"])
        return jsonify({"status": ai_action["status"]}), 200

    handoff_entry = get_handoff_entry(remote_jid)
    if handoff_entry:
        feedback_id = handoff_entry.get("feedback_id")
        if feedback_id:
            feedback = get_feedback_by_id(feedback_id)
            if feedback:
                append_client_message_to_feedback(
                    feedback_id,
                    feedback.get('message', ''),
                    text
                )
        return jsonify({"status": "human_takeover_active"}), 200

    handled_context = process_context_followup(remote_jid, push_name, text)
    if handled_context:
        handled_reply = handled_context.get("reply")
        if handled_reply:
            send_whatsapp_message(remote_jid, handled_reply)
        if handled_context.get("result") and handled_reply:
            record_agent_reply(
                handled_context["result"].get("id"),
                handled_context["result"].get("message"),
                handled_reply
            )
        elif handled_reply:
            update_context_message(remote_jid, 'agent', handled_reply)
        return jsonify({"status": handled_context["status"]}), 200

    if ctx and is_affirmative(text):
        prev_intent = ctx['intent']
        print(f"ðŸ”„ [CONTEXT] Follow-up for {prev_intent}: {text}")

        if prev_intent == 'receita':
            receita_text = ctx['data'].get('receita', '')
            reply = generate_lista_compras_response(f"lista: {receita_text}")
            send_whatsapp_message(remote_jid, reply)
            conversation_context.pop(remote_jid, None)
            return jsonify({"status": "recipe_followup_list"}), 200

        elif prev_intent == 'consulta_produto':
            produto = ctx['data'].get('produto', '')
            if produto:
                registrar_lista_espera(remote_jid, push_name, produto)
                reply = f"Anotado! Te aviso quando {produto} tiver novidade âœ…"
                send_whatsapp_message(remote_jid, reply)
                conversation_context.pop(remote_jid, None)
                return jsonify({"status": "product_followup_waitlist"}), 200

        elif prev_intent == 'ofertas':
            reply = generate_lista_compras_response(f"lista: {ctx['data'].get('ofertas', '')}")
            send_whatsapp_message(remote_jid, reply)
            conversation_context.pop(remote_jid, None)
            return jsonify({"status": "offers_followup_list"}), 200

    conversation_context.pop(remote_jid, None)

    # --- SAUDAÇÃO ---
    # Saudações SEMPRE vão para a IA responder naturalmente.
    # Despedida só acontece com palavras explícitas (tchau, falou, vlw) no wrap-up abaixo.
    if is_greeting(text):
        casual_count = _increment_casual_chat(remote_jid)
        reply = generate_greeting_response(text, push_name, casual_count)
        send_whatsapp_message(remote_jid, reply)
        print(f"[GREETING] casual_count={casual_count} for {mascarar_telefone(remote_jid)}")
        return jsonify({"status": "greeting_handled"}), 200

    if is_conversation_wrap_up(text):
        import random
        if os.path.exists(STICKER_TCHAU):
            send_whatsapp_sticker(remote_jid, STICKER_TCHAU)
        despedidas = [
            'Fico feliz em ajudar. Até mais! 😊',
            'Pode contar comigo sempre. Até mais!',
            'Obrigado por falar com a gente. Até logo!',
            'Ótimo! Qualquer coisa é só chamar.',
        ]
        reply = random.choice(despedidas)
        send_whatsapp_message(remote_jid, reply)
        # Grava mensagem de encerramento e despedida no histórico do card
        active_feedback = get_active_feedback(remote_jid)
        if active_feedback:
            updated_msg = append_conversation_entry(active_feedback.get('message', ''), 'client', text)
            updated_msg = append_conversation_entry(updated_msg, 'agent', reply)
            update_feedback(active_feedback['id'], {
                'message': updated_msg,
                'updated_at': datetime.utcnow().isoformat()
            })
        return jsonify({'status': 'conversation_closed'}), 200

    # --- STICKER TEMÁTICO: COPA ---
    # Envia figurinha do Pipico torcedor se a mensagem mencionar futebol/copa
    if os.path.exists(STICKER_COPA):
        texto_copa = normalize_text(text)
        if COPA_KEYWORDS_RE.search(texto_copa):
            send_whatsapp_sticker(remote_jid, STICKER_COPA)

    intencao = detectar_intencao(text)
    _reset_casual_chat(remote_jid)  # Msg com intenção real reseta o contador de bate-papo
    print(f"ðŸ” [INTENT] {intencao}: {text[:50]}")

    if intencao == 'horario':
        if not is_store_open() and os.path.exists(STICKER_FECHADO):
            send_whatsapp_sticker(remote_jid, STICKER_FECHADO)
        reply = generate_horario_response(text)
        send_whatsapp_message(remote_jid, reply)
        return jsonify({'status': 'horario_sent'}), 200

    elif intencao == 'estrutura_local':
        reply = "Sinto muito por isso! Para informações sobre acesso e estrutura do local, o ideal é falar com nossa equipe no estabelecimento, será um prazer te ajudar e obrigado pelo contato!"
        send_whatsapp_message(remote_jid, reply)
        return jsonify({"status": "estrutura_local_sent"}), 200

    elif intencao == 'consulta_indisponivel':
        reply = generate_unavailable_product_response(text)
        send_whatsapp_message(remote_jid, reply)
        return jsonify({"status": "product_unavailable_scope"}), 200

    elif intencao == 'promocoes':
        texto_norm = normalize_text(text)
        periodo = _detectar_periodo_promo(texto_norm)
        if periodo == 'dia':
            _enviar_promo_dia(remote_jid)
        elif periodo == 'mes':
            _enviar_promo_mes(remote_jid)
        else:
            _enviar_menu_promocoes(remote_jid)
        return jsonify({"status": "promotions_sent"}), 200

    elif intencao == 'consulta_produto':
        produto_nome = extrair_produto_ia(text)
        if produto_nome:
            query = produto_nome
        else:
            query = re.sub(r'^(quanto custa|qual o preço d[aoe]|preço d[aoe]|valor d[aoe]|tem |vocês tem|voces tem|vcs tem|quanto t[aá]\s+[aoe]|quanto [eé]\s+[aoe])\s*', '', text.lower()).strip().rstrip('?')
        print(f"ðŸ›' [PRODUCT] Searching for: {query}")
        results = buscar_produto_local(query)
        reply = generate_product_response(text, results)
        send_whatsapp_message(remote_jid, reply)
        save_context(remote_jid, 'consulta_produto', {'produto': query})
        return jsonify({"status": "product_query", "results": len(results)}), 200

    elif intencao == 'pergunta_geral':
        reply = generate_pergunta_geral_response(text)
        send_whatsapp_message(remote_jid, reply)
        return jsonify({"status": "general_question_answered"}), 200

    elif intencao == 'lista_espera':
        produto = re.sub(r'^(me avisa quando|avisa quando chegar|avisa quando tiver|quando chegar|quando vai ter|quando volta)\s*', '', text.lower()).strip()
        registrar_lista_espera(remote_jid, push_name, produto)
        reply = f"Anotado! Assim que {produto} voltar ao estoque, te aviso por aqui âœ…"
        send_whatsapp_message(remote_jid, reply)
        return jsonify({"status": "waitlist_registered", "product": produto}), 200

    elif intencao == 'ofertas':
        reply = generate_ofertas_response()
        send_whatsapp_message(remote_jid, reply)
        save_context(remote_jid, 'ofertas', {'ofertas': reply})
        return jsonify({"status": "offers_sent"}), 200

    elif intencao == 'lista_compras':
        reply = generate_lista_compras_response(text)
        send_whatsapp_message(remote_jid, reply)
        return jsonify({"status": "shopping_list_processed"}), 200

    elif intencao == 'receita':
        reply = generate_receita_response()
        send_whatsapp_message(remote_jid, reply)
        save_context(remote_jid, 'receita', {'receita': reply})
        return jsonify({"status": "recipe_sent"}), 200

    elif intencao == 'feedback':
        result = process_feedback_message(remote_jid, push_name, text)
        send_whatsapp_message(remote_jid, result["reply"])
        if result["status"] == "feedback_processed":
            record_agent_reply(result["result"].get("id"), result["result"].get("message"), result["reply"])
            # Envia figurinha de agradecimento se não há follow-up pendente
            if not get_context(remote_jid) and os.path.exists(STICKER_FEEDBACK):
                send_whatsapp_sticker(remote_jid, STICKER_FEEDBACK)
        else:
            update_context_message(remote_jid, 'agent', result["reply"])
        return jsonify({"status": result["status"]}), 200

    else:
        ia_result = classificar_com_ia(text)
        if ia_result:
            sentimento = ia_result.get('sentimento', 'Neutro')
            categoria = ia_result.get('categoria', 'Atendimento')
            setor = ia_result.get('setor', 'Geral')
        else:
            sentimento = classificar_sentimento(text)
            categoria = classificar_categoria(text)
            setor = classificar_setor(text)

        active_feedback = get_active_feedback(remote_jid)
        linked_from_id = None

        if active_feedback:
            old_category = (active_feedback.get('category') or '').strip().lower()
            new_category = (categoria or '').strip().lower()
            same_category = old_category == new_category

            # Incidentes críticos (roubo, acidente, fogo etc.) SEMPRE geram novo card
            # São ocorrências independentes, não continuação de conversa anterior
            is_critical_new_incident = (
                sentimento == 'Critico'
                or is_store_incident_issue(text)
            )

            if same_category and not is_critical_new_incident:
                print(f"[THREADING] Same category '{categoria}' â€” appending to feedback {active_feedback.get('id')}")

                current_urgency = active_feedback.get('urgency', 'Neutro')
                update_urgency = None
                update_sentiment = None

                priority_map = {"Critico": 3, "Urgente": 2, "Positivo": 1, "Neutro": 0}
                current_prio = priority_map.get(current_urgency, 0)
                new_prio = priority_map.get(sentimento, 0)

                if new_prio > current_prio:
                    print(f"[THREADING] Upgrading Urgency: {current_urgency} -> {sentimento}")
                    update_urgency = sentimento
                    update_sentiment = "Positivo" if sentimento == "Positivo" else ("Negativo" if sentimento in ["Critico", "Urgente"] else "Neutro")

                updated_message = append_to_feedback(active_feedback['id'], active_feedback['message'], text, update_urgency, update_sentiment)

                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": f'''Você é {AGENT_NAME}, atendente do supermercado. O cliente enviou mais uma mensagem complementando o que disse antes.
                                    MENSAGEM NOVA: "{text}"
                                    SEJA BREVE (Máximo 1 frase). Confirme que anotou a informação.
                                    Use emoji apenas se combinar com o contexto. Nunca use emoji sorrindo em reclamação.'''}],
                        max_tokens=60,
                        timeout=15
                    )
                    reply = resp.choices[0].message.content.strip()
                except:
                    reply = "Anotado. Já adicionei essa informação ao seu atendimento."

                reply = finalize_marcia_reply(reply, update_urgency or sentimento, categoria, text)
                send_whatsapp_message(remote_jid, reply)
                record_agent_reply(active_feedback['id'], updated_message or active_feedback['message'], reply)
                return jsonify({"status": "updated_existing", "id": active_feedback['id']}), 200
            else:
                motivo = 'incidente_critico' if is_critical_new_incident else f'categoria_{old_category}_para_{categoria}'
                print(f"[THREADING] Novo card — motivo: {motivo} — linked to {active_feedback.get('id')}")
                linked_from_id = active_feedback.get('id')

        now = datetime.utcnow()
        current_id = get_next_id()
        new_feedback = {
            "id": current_id,
            "sender": remote_jid,
            "name": push_name,
            "message": build_feedback_message(text, now.isoformat()),
            "timestamp": now.isoformat(),
            "updated_at": now.isoformat(),
            "category": categoria,
            "region": setor,
            "urgency": sentimento,
            "sentiment": "Positivo" if sentimento == "Positivo" else ("Negativo" if sentimento in ["Critico", "Urgente"] else "Neutro"),
            "loja": "Matriz",
            "status": "aberto"
        }
        if linked_from_id:
            new_feedback["linked_from"] = linked_from_id

        save_feedback(new_feedback)

        try:
            reply = generate_ai_response(text, categoria, sentimento)
            send_whatsapp_message(remote_jid, reply)
            record_agent_reply(current_id, new_feedback["message"], reply)
        except Exception as e:
            print(f"âŒ [WEBHOOK] AI reply failed: {e}")
            fallback_reply = finalize_marcia_reply(
                "Recebemos sua mensagem. Obrigado por contar pra gente.",
                sentimento,
                categoria,
                text
            )
            send_whatsapp_message(remote_jid, fallback_reply)

        return jsonify({"status": "feedback_processed", "id": current_id}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    try:
        event_type = data.get("type") or data.get("event")

        if event_type in ["message", "messages.upsert", "MESSAGES_UPSERT"]:
            msg_data = data.get("data", {})
            key = msg_data.get("key", {})
            remote_jid = key.get("remoteJid")
            push_name = msg_data.get("pushName", "Cliente")
            message_content = msg_data.get("message", {})
            text = message_content.get("conversation") or message_content.get("extendedTextMessage", {}).get("text")
            native_transcription = message_content.get("transcription")
            audio_msg = message_content.get("audioMessage")

            # Proteção contra replay attack
            msg_timestamp = msg_data.get("messageTimestamp")
            if msg_timestamp:
                try:
                    msg_time = int(msg_timestamp)
                    now_epoch = int(datetime.utcnow().timestamp())
                    if abs(now_epoch - msg_time) > 120:
                        print(f"[REPLAY] Mensagem antiga rejeitada: {abs(now_epoch - msg_time)}s de atraso")
                        return jsonify({"status": "stale_message"}), 200
                except (ValueError, TypeError):
                    pass

            # Proteção global contra flood de múltiplos números
            if is_globally_rate_limited():
                print(f"[GLOBAL-FLOOD] Sistema em proteção — rejeitando mensagem")
                return jsonify({"status": "global_rate_limited"}), 429

            if key.get("fromMe"):
                if remote_jid and text:
                    handoff_entry = get_handoff_entry(remote_jid)
                    feedback_id = handoff_entry.get("feedback_id") if handoff_entry else None
                    if feedback_id:
                        feedback = get_feedback_by_id(feedback_id)
                        if feedback:
                            append_human_message_to_feedback(
                                feedback_id,
                                feedback.get('message', ''),
                                text
                            )
                            update_feedback(feedback_id, {
                                'status': 'em_andamento',
                                'updated_at': datetime.utcnow().isoformat()
                            })
                            return jsonify({"status": "human_reply_logged"}), 200
                return jsonify({"status": "ignored_self"}), 200

            # Audio Processing
            if not text and audio_msg and remote_jid:
                # Rate limit de áudio
                if is_audio_limited(remote_jid):
                    send_whatsapp_message(remote_jid, "⚠️ Você já enviou vários áudios recentemente. Aguarde um pouco ou envie sua mensagem por texto.")
                    return jsonify({"status": "audio_rate_limited"}), 200

                seconds = audio_msg.get("seconds", 0)
                if seconds > 35:
                    send_whatsapp_message(remote_jid, "⚠️ Áudio muito longo! Manda de no máximo 35 segundos, por favor 🛒")
                    return jsonify({"status": "audio_too_long"}), 200

                if native_transcription:
                    text = native_transcription
                else:
                    import base64
                    audio_data = None
                    if "base64" in message_content:
                        try: audio_data = base64.b64decode(message_content["base64"])
                        except: pass
                    if not audio_data and "base64" in msg_data:
                        try: audio_data = base64.b64decode(msg_data["base64"])
                        except: pass
                    if not audio_data:
                        audio_data = download_evolution_media(remote_jid, key.get("id"))
                    if audio_data:
                        text = transcribe_audio(audio_data)
                        if not text:
                            send_whatsapp_message(remote_jid, "Não consegui entender o áudio. Pode digitar a mensagem? 🛒")
                            return jsonify({"status": "transcription_failed"}), 200
                    else:
                        send_whatsapp_message(remote_jid, "Erro ao processar o áudio. Tenta digitar a mensagem! 🛒")
                        return jsonify({"status": "download_failed"}), 200

            if text and remote_jid:
                buffer_and_process_message(remote_jid, push_name, text, is_audio=bool(audio_msg))
                return jsonify({"status": "buffered"}), 200
                restriction = get_active_restriction(remote_jid)
                if restriction:
                    send_whatsapp_message(remote_jid, restriction["reply"])
                    return jsonify({"status": restriction["status"]}), 200

                # Spam protection
                if len(text.strip()) < MIN_MESSAGE_LENGTH:
                    return jsonify({"status": "ignored_too_short"}), 200
                if is_emoji_only(text):
                    return jsonify({"status": "ignored_emoji_only"}), 200

                abuse = analyze_abuse_message(text)
                if abuse["score"] > 0:
                    moderation = register_moderation_infraction(
                        remote_jid,
                        text,
                        abuse["reasons"],
                        abuse["score"],
                        severe=abuse["severe"]
                    )
                    send_whatsapp_message(remote_jid, moderation["reply"])
                    return jsonify({"status": moderation["status"]}), 200

                if is_rate_limited(remote_jid):
                    moderation = register_moderation_infraction(
                        remote_jid,
                        text,
                        ["spam"],
                        2,
                        severe=False
                    )
                    send_whatsapp_message(remote_jid, moderation["reply"])
                    return jsonify({"status": "rate_limited"}), 200

                # Deduplication
                feedbacks = get_feedbacks()
                msg_hash = hashlib.md5(f"{text}{remote_jid}".encode()).hexdigest()
                existing = {
                    hashlib.md5(f"{msg}{fb.get('sender', '')}".encode()).hexdigest()
                    for fb in feedbacks
                    for msg in (get_feedback_customer_messages(fb.get('message', '')) or [''])
                }
                if msg_hash in existing:
                    return jsonify({"status": "ignored_duplicate"}), 200

                # --- CONTEXT CHECK (follow-up replies) ---
                ctx = get_context(remote_jid)
                handled_context = process_context_followup(remote_jid, push_name, text)
                if handled_context:
                    send_whatsapp_message(remote_jid, handled_context["reply"])
                    if handled_context.get("result"):
                        record_agent_reply(
                            handled_context["result"].get("id"),
                            handled_context["result"].get("message"),
                            handled_context["reply"]
                        )
                    else:
                        update_context_message(remote_jid, 'agent', handled_context["reply"])
                    return jsonify({"status": handled_context["status"]}), 200
                if ctx and is_affirmative(text):
                    prev_intent = ctx['intent']
                    print(f"🔄 [CONTEXT] Follow-up for {prev_intent}: {text}")
                    
                    if prev_intent == 'receita':
                        receita_text = ctx['data'].get('receita', '')
                        reply = generate_lista_compras_response(f"lista: {receita_text}")
                        send_whatsapp_message(remote_jid, reply)
                        conversation_context.pop(remote_jid, None)
                        return jsonify({"status": "recipe_followup_list"}), 200
                    
                    elif prev_intent == 'consulta_produto':
                        produto = ctx['data'].get('produto', '')
                        if produto:
                            registrar_lista_espera(remote_jid, push_name, produto)
                            reply = f"Anotado! Te aviso quando {produto} tiver novidade ✅"
                            send_whatsapp_message(remote_jid, reply)
                            conversation_context.pop(remote_jid, None)
                            return jsonify({"status": "product_followup_waitlist"}), 200
                    
                    elif prev_intent == 'ofertas':
                        reply = generate_lista_compras_response(f"lista: {ctx['data'].get('ofertas', '')}")
                        send_whatsapp_message(remote_jid, reply)
                        conversation_context.pop(remote_jid, None)
                        return jsonify({"status": "offers_followup_list"}), 200
                
                # Limpa contexto se não foi follow-up
                conversation_context.pop(remote_jid, None)

                # --- INTENT DETECTION ---
                intencao = detectar_intencao(text)
                print(f"🔍 [INTENT] {intencao}: {text[:50]}")

                if intencao == 'estrutura_local':
                    reply = "Sinto muito por isso! Para informações sobre acesso e estrutura do local, o ideal é falar com nossa equipe no estabelecimento, será um prazer te ajudar e obrigado pelo contato!"
                    send_whatsapp_message(remote_jid, reply)
                    return jsonify({"status": "estrutura_local_sent"}), 200

                elif intencao == 'consulta_indisponivel':
                    reply = generate_unavailable_product_response()
                    send_whatsapp_message(remote_jid, reply)
                    return jsonify({"status": "product_unavailable_scope"}), 200

                elif intencao == 'promocoes':
                    texto_norm = normalize_text(text)
                    periodo = _detectar_periodo_promo(texto_norm)
                    if periodo == 'dia':
                        _enviar_promo_dia(remote_jid)
                    elif periodo == 'mes':
                        _enviar_promo_mes(remote_jid)
                    else:
                        _enviar_menu_promocoes(remote_jid)
                    return jsonify({"status": "promotions_sent"}), 200

                elif intencao == 'consulta_produto':
                    produto_nome = extrair_produto_ia(text)
                    if produto_nome:
                        query = produto_nome
                    else:
                        query = re.sub(r'^(quanto custa|qual o preço d[aoe]|preço d[aoe]|valor d[aoe]|tem |vocês tem|voces tem|vcs tem|quanto t[aá]\s+[aoe]|quanto [eé]\s+[aoe])\s*', '', text.lower()).strip().rstrip('?')
                    print(f"🛒 [PRODUCT] Searching for: {query}")
                    results = buscar_produto_local(query)
                    reply = generate_product_response(text, results)
                    send_whatsapp_message(remote_jid, reply)
                    save_context(remote_jid, 'consulta_produto', {'produto': query})
                    return jsonify({"status": "product_query", "results": len(results)}), 200

                elif intencao == 'pergunta_geral':
                    reply = generate_pergunta_geral_response(text)
                    send_whatsapp_message(remote_jid, reply)
                    return jsonify({"status": "general_question_answered"}), 200

                elif intencao == 'lista_espera':
                    produto = re.sub(r'^(me avisa quando|avisa quando chegar|avisa quando tiver|quando chegar|quando vai ter|quando volta)\s*', '', text.lower()).strip()
                    registrar_lista_espera(remote_jid, push_name, produto)
                    reply = f"Anotado! Assim que {produto} voltar ao estoque, te aviso por aqui ✅"
                    send_whatsapp_message(remote_jid, reply)
                    return jsonify({"status": "waitlist_registered", "product": produto}), 200

                elif intencao == 'ofertas':
                    reply = generate_ofertas_response()
                    send_whatsapp_message(remote_jid, reply)
                    save_context(remote_jid, 'ofertas', {'ofertas': reply})
                    return jsonify({"status": "offers_sent"}), 200

                elif intencao == 'lista_compras':
                    reply = generate_lista_compras_response(text)
                    send_whatsapp_message(remote_jid, reply)
                    return jsonify({"status": "shopping_list_processed"}), 200

                elif intencao == 'receita':
                    reply = generate_receita_response()
                    send_whatsapp_message(remote_jid, reply)
                    save_context(remote_jid, 'receita', {'receita': reply})
                    return jsonify({"status": "recipe_sent"}), 200

                elif intencao == 'feedback':
                    result = process_feedback_message(remote_jid, push_name, text)
                    send_whatsapp_message(remote_jid, result["reply"])
                    if result["status"] == "feedback_processed":
                        record_agent_reply(result["result"].get("id"), result["result"].get("message"), result["reply"])
                    else:
                        update_context_message(remote_jid, 'agent', result["reply"])
                    return jsonify({"status": result["status"]}), 200

                else:
                    # FEEDBACK flow

                    # --- CLASSIFY FIRST (needed for smart threading) ---
                    ia_result = classificar_com_ia(text)
                    if ia_result:
                        sentimento = ia_result.get('sentimento', 'Neutro')
                        categoria = ia_result.get('categoria', 'Atendimento')
                        setor = ia_result.get('setor', 'Geral')
                    else:
                        sentimento = classificar_sentimento(text)
                        categoria = classificar_categoria(text)
                        setor = classificar_setor(text)

                    # --- SMART THREADING LOGIC ---
                    active_feedback = get_active_feedback(remote_jid)
                    linked_from_id = None
                    
                    if active_feedback:
                        old_category = (active_feedback.get('category') or '').strip().lower()
                        new_category = (categoria or '').strip().lower()
                        same_category = old_category == new_category

                        if same_category:
                            # MESMA CATEGORIA → append ao card existente
                            print(f"[THREADING] Same category '{categoria}' — appending to feedback {active_feedback.get('id')}")
                            
                            current_urgency = active_feedback.get('urgency', 'Neutro')
                            update_urgency = None
                            update_sentiment = None
                            
                            priority_map = {"Critico": 3, "Urgente": 2, "Positivo": 1, "Neutro": 0}
                            current_prio = priority_map.get(current_urgency, 0)
                            new_prio = priority_map.get(sentimento, 0)
                            
                            if new_prio > current_prio:
                                print(f"[THREADING] Upgrading Urgency: {current_urgency} -> {sentimento}")
                                update_urgency = sentimento
                                update_sentiment = "Positivo" if sentimento == "Positivo" else ("Negativo" if sentimento in ["Critico", "Urgente"] else "Neutro")
                            
                            updated_message = append_to_feedback(active_feedback['id'], active_feedback['message'], text, update_urgency, update_sentiment)
                            
                            try:
                                from openai import OpenAI
                                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                                resp = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[{"role": "system", "content": f'''Você é {AGENT_NAME}, atendente do supermercado. O cliente enviou mais uma mensagem complementando o que disse antes.
                                    MENSAGEM NOVA: "{text}"
                                    SEJA BREVE (Máximo 1 frase). Confirme que anotou a informação.
                                    Use emoji apenas se combinar com o contexto. Nunca use emoji sorrindo em reclamação.'''}],
                                    max_tokens=60,
                                    timeout=15
                                )
                                reply = resp.choices[0].message.content.strip()
                            except:
                                reply = "Anotado. Já adicionei essa informação ao seu atendimento."

                            reply = finalize_marcia_reply(reply, update_urgency or sentimento, categoria, text)
                            send_whatsapp_message(remote_jid, reply)
                            record_agent_reply(active_feedback['id'], updated_message or active_feedback['message'], reply)
                            return jsonify({"status": "updated_existing", "id": active_feedback['id']}), 200
                        else:
                            # CATEGORIA DIFERENTE → criar card novo, linkado ao anterior
                            print(f"[THREADING] Category changed '{old_category}' → '{categoria}' — creating NEW card linked to {active_feedback.get('id')}")
                            linked_from_id = active_feedback.get('id')
                    # --- END SMART THREADING ---

                    now = datetime.utcnow()
                    current_id = get_next_id()
                    new_feedback = {
                        "id": current_id,
                        "sender": remote_jid,
                        "name": push_name,
                        "message": build_feedback_message(text, now.isoformat()),
                        "timestamp": now.isoformat(),
                        "updated_at": now.isoformat(),
                        "category": categoria,
                        "region": setor,
                        "urgency": sentimento,
                        "sentiment": "Positivo" if sentimento == "Positivo" else ("Negativo" if sentimento in ["Critico", "Urgente"] else "Neutro"),
                        "loja": "Matriz",
                        "status": "aberto"
                    }
                    if linked_from_id:
                        new_feedback["linked_from"] = linked_from_id
                    # Save feedback FIRST (before AI response to avoid data loss)
                    save_feedback(new_feedback)
                    
                    # Reply (AI Generated) — wrapped so failure doesn't lose saved data
                    try:
                        reply = generate_ai_response(text, categoria, sentimento)
                        send_whatsapp_message(remote_jid, reply)
                        record_agent_reply(current_id, new_feedback["message"], reply)
                    except Exception as e:
                        print(f"❌ [WEBHOOK] AI reply failed: {e}")
                        fallback_reply = finalize_marcia_reply(
                            "Recebemos sua mensagem. Obrigado por contar pra gente.",
                            sentimento,
                            categoria,
                            text
                        )
                        send_whatsapp_message(remote_jid, fallback_reply)
                    
                    return jsonify({"status": "feedback_processed", "id": current_id}), 200

        return jsonify({"status": "ignored"}), 200

    except Exception as e:
        print(f"❌❌ [WEBHOOK CRITICAL] Unhandled error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/debug")
def debug_env():
    return jsonify({
        "status": "online",
        "app": "Supermercado Node Data",
        "env_check": {
            "SUPABASE_URL": "OK" if os.getenv("SUPABASE_URL") else "MISSING",
            "SUPABASE_KEY": "OK" if os.getenv("SUPABASE_KEY") else "MISSING",
            "OPENAI_API_KEY": "OK" if os.getenv("OPENAI_API_KEY") else "MISSING",
            "EVOLUTION_API_URL": os.getenv("EVOLUTION_API_URL", "MISSING"),
            "EVOLUTION_INSTANCE": os.getenv("EVOLUTION_INSTANCE_NAME", "MISSING"),
        }
    })

# --- HEALTH CHECK ENDPOINT (usado pelo CRM Monitor) ---

@app.route("/api/health")
def api_health():
    """Retorna o status de todos os serviços que o Atacaforte precisa pra funcionar.

    O CRM central consulta essa rota a cada 5 min.
    Se algo estiver 'down', o CRM manda alerta no WhatsApp.

    Não precisa de login — é uma rota pública simples.
    Mas não expõe dados sensíveis, só status up/down.
    """
    import time as _time
    results = {}
    overall = "up"

    # 1. SUPABASE — Tenta fazer um SELECT simples
    #    Se falhar, os feedbacks não serão salvos
    try:
        _start = _time.time()
        sb = get_supabase()
        if sb:
            resp = sb.table('feedbacks').select('id').limit(1).execute()
            _ms = int((_time.time() - _start) * 1000)
            results["supabase"] = {
                "status": "up",
                "ms": _ms,
                "detail": f"{len(resp.data)} rows returned"
            }
        else:
            results["supabase"] = {"status": "down", "ms": None, "detail": "Client not configured"}
            overall = "degraded"
    except Exception as e:
        results["supabase"] = {"status": "down", "ms": None, "detail": str(e)[:120]}
        overall = "degraded"

    # 2. EVOLUTION API — Verifica se a instância WhatsApp está conectada
    #    Se falhar, o Pipico não consegue enviar/receber mensagens
    try:
        _start = _time.time()
        evo_url = os.getenv("EVOLUTION_API_URL", "")
        evo_key = os.getenv("EVOLUTION_API_KEY", "")
        evo_instance = os.getenv("EVOLUTION_INSTANCE_NAME", "")

        if evo_url and evo_key and evo_instance:
            resp = requests.get(
                f"{evo_url}/instance/connectionState/{evo_instance}",
                headers={"apikey": evo_key},
                timeout=10
            )
            _ms = int((_time.time() - _start) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                state = "unknown"
                if isinstance(data, dict):
                    state = data.get("state") or data.get("instance", {}).get("state", "unknown")

                is_connected = state in ("open", "connected")
                results["evolution"] = {
                    "status": "up" if is_connected else "warning",
                    "ms": _ms,
                    "detail": f"Instance '{evo_instance}' state: {state}",
                    "connected": is_connected
                }
                if not is_connected:
                    overall = "degraded"
            else:
                results["evolution"] = {
                    "status": "down",
                    "ms": _ms,
                    "detail": f"HTTP {resp.status_code}: {resp.text[:80]}"
                }
                overall = "degraded"
        else:
            results["evolution"] = {"status": "down", "ms": None, "detail": "Not configured"}
            overall = "degraded"
    except Exception as e:
        results["evolution"] = {"status": "down", "ms": None, "detail": str(e)[:120]}
        overall = "degraded"

    # 3. OPENAI — Testa se a chave está válida (sem gastar tokens)
    #    Se falhar, o Pipico não consegue classificar nem responder
    try:
        _start = _time.time()
        openai_key = os.getenv("OPENAI_API_KEY", "")

        if openai_key:
            resp = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {openai_key}"},
                timeout=10
            )
            _ms = int((_time.time() - _start) * 1000)

            if resp.status_code == 200:
                results["openai"] = {"status": "up", "ms": _ms, "detail": "API key valid"}
            else:
                results["openai"] = {"status": "down", "ms": _ms, "detail": f"HTTP {resp.status_code}"}
                overall = "degraded"
        else:
            results["openai"] = {"status": "down", "ms": None, "detail": "API key not set"}
            overall = "degraded"
    except Exception as e:
        results["openai"] = {"status": "down", "ms": None, "detail": str(e)[:120]}
        overall = "degraded"

    # 4. PRODUTOS — Verifica se tem produtos cadastrados
    #    O Pipico precisa disso para responder consultas de preço
    try:
        produtos = get_produtos()
        results["produtos"] = {
            "status": "up" if produtos else "warning",
            "total": len(produtos) if produtos else 0,
            "detail": f"{len(produtos)} produtos" if produtos else "Nenhum produto cadastrado"
        }
    except Exception as e:
        results["produtos"] = {"status": "error", "detail": str(e)[:120]}

    # 5. FEEDBACKS COUNT — Métricas de sanidade
    try:
        feedbacks = get_feedbacks()
        total = len(feedbacks) if feedbacks else 0
        abertos = sum(1 for f in (feedbacks or []) if f.get('status', 'aberto') != 'resolvido')
        criticos = sum(1 for f in (feedbacks or []) if f.get('urgency') in ['Critico', 'Crítico', 'Urgente'])
        results["feedbacks"] = {
            "status": "up",
            "total": total,
            "abertos": abertos,
            "criticos": criticos
        }
    except Exception as e:
        results["feedbacks"] = {"status": "error", "detail": str(e)[:120]}

    # 6. PROMOÇÕES — Verifica se tem promoções cadastradas
    #    Importante pro Pipico responder perguntas sobre ofertas
    try:
        promos = get_promotions_from_config()
        has_day = bool((promos.get("day") or "").strip())
        has_week = bool((promos.get("week") or "").strip())
        results["promocoes"] = {
            "status": "up" if (has_day or has_week) else "warning",
            "dia": has_day,
            "semana": has_week,
            "detail": f"Dia: {'sim' if has_day else 'não'}, Semana: {'sim' if has_week else 'não'}"
        }
    except Exception as e:
        results["promocoes"] = {"status": "error", "detail": str(e)[:120]}

    # Overall: se serviço crítico está down, tudo é down
    critical_services = ["supabase", "evolution"]
    for svc in critical_services:
        if results.get(svc, {}).get("status") == "down":
            overall = "down"
            break

    return jsonify({
        "project": "atacaforte_supermercado",
        "project_name": "Atacaforte (Seu Pipico)",
        "port": 5003,
        "overall": overall,
        "checked_at": datetime.utcnow().isoformat(),
        "services": results
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5003))
    print(f"🛒 Supermercado Node Data running on port {port}")
    if supabase:
        print("📦 Using Supabase database")
    else:
        print("📁 Using local JSON files")
    app.run(host="0.0.0.0", port=port)
