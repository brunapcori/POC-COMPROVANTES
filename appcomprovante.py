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

# 2. Descompactar ficheiros se necessário
ZIP_FILE = "comprovanteia_poc_consolidada.zip"
if os.path.exists(ZIP_FILE) and not os.path.exists("indice_comprovantes_ficticios.csv"):
    with zipfile.ZipFile(ZIP_FILE, 'r') as zip_ref:
        zip_ref.extractall(".")

# 3. Carregamento e normalização segura do catálogo
def carregar_dados():
    csv_file = "indice_comprovantes_ficticios.csv"
    if not os.path.exists(csv_file):
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(csv_file, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(csv_file)
        
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]

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
    
    # Remove colunas duplicadas que possam ter recebido o mesmo nome padronizado
    df = df.loc[:, ~df.columns.duplicated()]
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

def extrair_valores_coluna(df: pd.DataFrame, nome_coluna: str) -> list:
    """Extrai uma lista de strings limpa de uma coluna com segurança contra duplicações."""
    if nome_coluna not in df.columns:
        return []
    col = df[nome_coluna]
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    return [str(x) for x in col.dropna().unique().tolist()]

def extrair_criterios_ia(texto_usuario: str, df: pd.DataFrame) -> dict:
    criterios = {"empresa": None, "fornecedor": None}

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

    texto_limpo = texto_usuario.lower()
    if not df.empty:
        # Busca termos de Empresa com segurança
        if not criterios.get("empresa"):
            for val in extrair_valores_coluna(df, "Empresa"):
                palavras = [p.lower() for p in val.split() if len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    criterios["empresa"] = val
                    break

        # Busca termos de Fornecedor com segurança
        if not criterios.get("fornecedor"):
            for val in extrair_valores_coluna(df, "Fornecedor"):
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
        col_empresa = resultado["Empresa"]
        if isinstance(col_empresa, pd.DataFrame):
            col_empresa = col_empresa.iloc[:, 0]
        resultado = resultado[col_empresa.astype(str).str.contains(termo, case=False, na=False)]

    if criterios.get("fornecedor") and "Fornecedor" in resultado.columns:
        termo = str(criterios["fornecedor"]).strip().split()[0]
        col_forn = resultado["Fornecedor"]
        if isinstance(col_forn, pd.DataFrame):
            col_forn = col_forn.iloc[:, 0]
        resultado = resultado[col_forn.astype(str).str.contains(termo, case=False, na=False)]

    return resultado

def extrair_pagina_pdf(caminho_pdf: str, numero_pagina: int) -> bytes:
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
