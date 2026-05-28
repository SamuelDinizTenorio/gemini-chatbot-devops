import streamlit as st
from google import genai
import os
import time
from dotenv import load_dotenv
import logging
from typing import List, Dict

# Carrega as variáveis de ambiente necessárias para a execução
load_dotenv()

# ==============================================================================
# SISTEMA DE LOGS E RASTREAMENTO
# ==============================================================================

class SessionFilter(logging.Filter):
    """Filtro personalizado para injetar o ID da sessão do Streamlit nos logs.
    
    Isso permite rastrear as interações de um usuário específico de forma isolada,
    mesmo que múltiplos usuários estejam acessando o chatbot simultaneamente.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        # Importação e método oficial para capturar o contexto atual da sessão
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        
        # Recupera o ID de sessão único gerado pelo Streamlit para o usuário atual
        ctx = get_script_run_ctx()
        # Checagem segura: só acessa .session_id se o ctx realmente existir
        record.session_id = ctx.session_id if (ctx and hasattr(ctx, 'session_id')) else "LOCAL"
        return True

@st.cache_resource
def setup_logging() -> logging.Logger:
    """Configuração limpa e de alta performance para CloudWatch/Fargate."""
    logger = logging.getLogger("ChatBot")
    logger.setLevel(logging.INFO)
    
    if logger.hasHandlers():
        logger.handlers.clear()
        
    # Formato padronizado que as ferramentas de busca da AWS (como CloudWatch Insights)
    # conseguem ler e filtrar facilmente.
    log_format = '%(asctime)s - [%(session_id)s] - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)
    
    # Envia tudo para o console (stdout). A AWS captura isso automaticamente.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger.addFilter(SessionFilter())
    logger.addHandler(console_handler)
    
    return logger

# Inicializa o logger global
logger = setup_logging()

# ==============================================================================
# INICIALIZAÇÃO DE COMPONENTES CORE
# ==============================================================================

try:
    # O SDK conecta automaticamente usando a variável GEMINI_API_KEY do .env
    client = genai.Client()
except Exception as e:
    logger.critical(f"Falha crítica na inicialização do cliente Gemini: {str(e)}")
    st.error("Erro interno de configuração. Por favor, contate o administrador.")
    st.stop()

# Nome do modelo padrão caso não esteja definido no arquivo .env
MODEL_NAME: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ==============================================================================
# DOCUMENTAÇÃO E TRATAMENTO DE DADOS
# ==============================================================================

def prepare_gemini_history(messages: List[Dict[str, str]]) -> List[genai.types.Content]:
    """Converte o histórico de mensagens do Streamlit no formato oficial do Gemini SDK.
    
    A API do Gemini exige uma estrutura estrita baseada em objetos de Content e Parts,
    além de requerer a alternância correta entre os papéis 'user' e 'model'.

    Args:
        messages (List[Dict[str, str]]): Lista de dicionários contendo o histórico 
            no formato [{"role": "...", "content": "..."}].

    Returns:
        List[genai.types.Content]: Lista de objetos formatados prontos para a API.
    """
    gemini_history: List[genai.types.Content] = []
    for msg in messages:
        gemini_history.append(
            genai.types.Content(
                role=msg["role"],
                parts=[genai.types.Part.from_text(text=msg["content"])]
            )
        )
    return gemini_history

# ==============================================================================
# INTERFACE E FLUXO DA CONVERSA (STREAMLIT)
# ==============================================================================

def main():
    st.write("# ChatBot with AI")

    # Inicialização segura do estado da sessão do chat
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # Captura a entrada do usuário na barra de chat
    user_input: str = st.chat_input()

    # Renderização do histórico em tela
    for message in st.session_state.messages:
        role_display = "assistant" if message["role"] == "model" else "user"
        st.chat_message(role_display).write(message["content"])

    # Processamento da nova mensagem enviada
    if user_input:
        # Atualiza a interface e o estado local com a mensagem do usuário
        st.chat_message("user").write(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        logger.info(f"Mensagem recebida. Tamanho do histórico local: {len(st.session_state.messages)} mensagens.")
        
        # Conversão do histórico de mensagens
        gemini_history = prepare_gemini_history(st.session_state.messages)
        
        try:
            logger.info(f"Iniciando requisição à API (Modelo: {MODEL_NAME})")
            
            # Início do cronômetro para medir a latência da resposta
            start_time = time.time()
            
            historical_past = prepare_gemini_history(st.session_state.messages[:-1])
            
            chat = client.chats.create(
                model=MODEL_NAME, 
                history=historical_past
            )
            
            response = chat.send_message(user_input)
            ai_response = response.text
            
            # Fim do cronômetro
            latency = time.time() - start_time
            
            # Extração opcional de metadados de tokens (se suportado pelo objeto de resposta)
            token_info = ""
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                prompt_tokens = response.usage_metadata.prompt_token_count
                candidates_tokens = response.usage_metadata.candidates_token_count
                token_info = f" | Prompt Tokens: {prompt_tokens} | Output Tokens: {candidates_tokens}"
            
            # Log enriquecido com métricas de performance e custo
            logger.info(f"Resposta gerada com sucesso | Tempo de Resposta: {latency:.2f}s{token_info}")
            
            # Atualiza a interface e o estado local com a resposta do modelo
            st.chat_message("assistant").write(ai_response)
            st.session_state.messages.append({"role": "model", "content": ai_response})
            
        except Exception as e:
            # Captura detalhada de falhas, incluindo o rastreio da pilha de execução (Stacktrace)
            logger.error(f"Falha na comunicação com o provedor de IA: {str(e)}", exc_info=True)
            st.error("Desculpe, tive um problema ao processar sua requisição. Por favor, tente novamente.")
        
if __name__ == "__main__":
    main()
    