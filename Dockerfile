# Usar imagem oficial do Python
FROM python:3.11-slim

# Definir diretório de trabalho
WORKDIR /app

# Copiar arquivos de requisitos
COPY requirements.txt .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o código do projeto
COPY . .

# Expor a porta 5003 (supermercado usa porta diferente)
EXPOSE 5003

# Definir variáveis de ambiente padrão (podem ser sobrescritas)
ENV PORT=5003
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Comando de inicialização (Produção usando Gunicorn)
# --timeout 120: permite chamadas OpenAI longas sem matar worker
# --graceful-timeout 60: tempo para shutdown gracioso
CMD ["gunicorn", "-w", "2", "--timeout", "120", "--graceful-timeout", "60", "-b", "0.0.0.0:5003", "server:app"]
