# 1. Usa uma imagem oficial do Python em versão leve (slim)
FROM python:3.11-slim

# 2. Evita que o apt-get tente abrir janelas de diálogo interativas durante o build
ENV DEBIAN_FRONTEND=noninteractive

# 3. Define variáveis de ambiente para o Python rodar bem em containers
# PYTHONDONTWRITEBYTECODE: Evita que o Python escreva arquivos .pyc no disco
# PYTHONUNBUFFERED: Garante que os logs saiam no terminal INSTANTANEAMENTE
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true

# 4. Define a pasta de trabalho dentro do container
WORKDIR /app

# 5. Instala as dependências do sistema operacional necessárias (se houver)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 6. Copia primeiro o arquivo de dependências (otimiza o cache do Docker)
COPY requirements.txt .

# 7. Instala as bibliotecas Python
RUN pip install --no-cache-dir -r requirements.txt

# 8. Copia o restante do código para dentro do container
COPY . .

# 9. Informa que o container vai rodar na porta padrão do Streamlit
EXPOSE 8501

# 10. Comando para iniciar o Streamlit assim que o container ligar
CMD ["streamlit", "run", "app.py"]
