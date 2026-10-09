#Início do projeto
import os
import json
import io
import zipfile
import pandas as pd
import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader, PdfWriter

st.set_page_config(
    page_title="ComprovanteIA",
    page_icon="🧾",
    layout="wide"
)

# 1. Configuração da chave de API
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# 2. Descompactar arquivos se necessário
ZIP_FILE = "comprovanteia_poc_consolidada.zip"
if os.path.exists(ZIP_FILE) and not os.path.exists("indice_comprovantes_ficticios.csv"):
    with zipfile.ZipFile(ZIP_FILE, 'r') as zip_ref:
        zip_ref.extractall(".")

# 3. Carregamento seguro dos dados (sem cache para não travar dados antigos)
def carregar_dados():
    csv_file = "indice_comprovantes_ficticios.csv"
    if not os.path.exists(csv_file):
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(csv_file, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(csv_file)
        
    # Normaliza todos os nomes das colunas (minúsculas sem espaços)
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]

    # Renomeia para as colunas padronizadas esperadas na interface
    renomear = {}
    for col in df.columns:
        if "empresa" in col or "pagadora" in col:
            renomear[col] = "Empresa"
        elif "fornecedor" in col or "beneficiario" in col:
            renomear[col] = "Fornecedor"
        elif "data" in col:
            renomear[col] = "Data"
        elif "valor" in col:
            renomear[col] = "Valor"
        elif "nf" in col or "nota" in col:
            renomear[col] = "Nota Fiscal"
        elif "pdf" in col or "arquivo" in col:
            renomear[col] = "PDF"
        elif "pag" in col:
            renomear[col] = "Página"
            
    df = df.rename(columns=renomear)
    return df

df_indice = carregar_dados()

PROMPT_SISTEMA = """
Você é o assistente inteligente de busca do sistema ComprovanteIA.
Sua única responsabilidade é identificar a empresa pagadora e o fornecedor mencionados pelo usuário, mesmo que sejam nomes parciais ou aproximados.

Regras:
- Extraia o nome ou termo principal da empresa no campo "empresa". Caso não encontre, retorne null.
- Extraia o nome ou termo principal do fornecedor no campo "fornecedor". Caso não encontre, retorne null.
- Não exija datas, valores ou notas fiscais.
- Retorne ESTRITAMENTE um JSON com esta estrutura:
{
  "empresa": null,
  "fornecedor": null
}
"""

def extrair_criterios_ia(texto_usuario: str, df: pd.DataFrame) -> dict:
    criterios = {"empresa": None, "fornecedor": None}

    # Tentativa com os modelos da API
    if api_key:
        for modelo in ["gemini-1.5-flash-latest", "gemini-2.0-flash", "gemini-1.5-pro-latest"]:
            try:
                model = genai.GenerativeModel(
                    model_name=modelo,
                    system_instruction=PROMPT_SISTEMA,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.0}
                )
                res = model.generate_content(texto_usuario)
                dados = json.loads(res.text)
                if isinstance(dados, dict):
                    criterios = dados
                    break
            except Exception:
                continue

    # Verificação direta de texto sem falhas por KeyError ou AttributeError
    texto_limpo = texto_usuario.lower()
    if not df.empty:
        colunas_df = list(df.columns)
        
        # Procura termos de Empresa
        if not criterios.get("empresa") and "Empresa" in colunas_df:
            valores_empresa = [str(x) for x in df["Empresa"].dropna().tolist()]
            for val in set(valores_empresa):
                palavras = [p.lower() for p in val.split() if len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    criterios["empresa"] = val
                    break

        # Procura termos de Fornecedor
        if not criterios.get("fornecedor") and "Fornecedor" in colunas_df:
            valores_forn = [str(x) for x in df["Fornecedor"].dropna().tolist()]
            for val in set(valores_forn):
                palavras = [p.lower() for p in val.split() if len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    criterios["fornecedor"] = val
                    break

    return criterios

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not criterios:
        return pd.DataFrame()

    resultado = df.copy()

    if criterios.get("empresa") and "Empresa" in resultado.columns:
        termo = str(criterios["empresa"]).strip().split()[0]
        resultado = resultado[resultado["Empresa"].astype(str).str.contains(termo, case=False, na=False)]

    if criterios.get("fornecedor") and "Fornecedor" in resultado.columns:
        termo = str(criterios["fornecedor"]).strip().split()[0]
        resultado = resultado[resultado["Fornecedor"].astype(str).str.contains(termo, case=False, na=False)]

    return resultado

def extrair_pagina_pdf(caminho_pdf: str, numero_pagina: int) -> bytes:
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    writer.add_page(reader.pages[numero_pagina - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# --- INTERFACE STREAMLIT ---
st.title("🧾 ComprovanteIA")
st.caption("Consulte comprovativos indicando apenas a empresa pagadora e o fornecedor")

entrada_usuario = st.text_input(
    "Como posso ajudar?",
    placeholder="Ex.: empresa alfa no fornecedor horizonte"
)

if entrada_usuario:
    with st.spinner("A pesquisar comprovativos..."):
        criterios = extrair_criterios_ia(entrada_usuario, df_indice)
        resultados = buscar_comprovantes(criterios, df_indice)

    if criterios.get("empresa") or criterios.get("fornecedor"):
