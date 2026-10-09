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

# 3. Carregamento e mapeamento seguro das colunas do CSV
@st.cache_data
def carregar_dados():
    csv_file = "indice_comprovantes_ficticios.csv"
    if not os.path.exists(csv_file):
        return pd.DataFrame()
    
    # Deteta separador (vírgula, ponto e vírgula, etc.)
    try:
        df = pd.read_csv(csv_file, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(csv_file)
        
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Mapeia os cabeçalhos originais da POC para nomes padronizados
    mapa = {}
    for c in df.columns:
        if "empresa" in c or "pagadora" in c:
            mapa[c] = "Empresa"
        elif "fornecedor" in c or "beneficiario" in c:
            mapa[c] = "Fornecedor"
        elif "data" in c:
            mapa[c] = "Data"
        elif "valor" in c:
            mapa[c] = "Valor"
        elif "nf" in c or "nota" in c:
            mapa[c] = "Nota Fiscal"
        elif "pdf" in c or "arquivo" in c:
            mapa[c] = "PDF"
        elif "pag" in c:
            mapa[c] = "Página"
            
    df = df.rename(columns=mapa)
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
    """Interpreta os critérios da consulta via Gemini ou por correspondência direta no catálogo."""
    criterios = {"empresa": None, "fornecedor": None}

    # Tentativa via Gemini API
    if api_key:
        for nome_modelo in ["gemini-1.5-flash-latest", "gemini-2.0-flash", "gemini-1.5-pro-latest"]:
            try:
                model = genai.GenerativeModel(
                    model_name=nome_modelo,
                    system_instruction=PROMPT_SISTEMA,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.0}
                )
                response = model.generate_content(texto_usuario)
                dados = json.loads(response.text)
                if isinstance(dados, dict):
                    criterios = dados
                    break
            except Exception:
                continue

    # Fallback automático: identifica termos conhecidos diretamente no texto
    texto_limpo = texto_usuario.lower()
    if not df.empty:
        if not criterios.get("empresa") and "Empresa" in df.columns:
            for emp in df["Empresa"].dropna().unique():
                palavras = [p.lower() for p in str(emp).split() if len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    criterios["empresa"] = emp
                    break

        if not criterios.get("fornecedor") and "Fornecedor" in df.columns:
            for forn in df["Fornecedor"].dropna().unique():
                palavras = [p.lower() for p in str(forn).split() if len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    criterios["fornecedor"] = forn
                    break

    return criterios

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Filtra o índice permitindo correspondência flexível."""
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
    """Extrai apenas a página indicada do arquivo PDF consolidado."""
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
    placeholder="Ex.: comprovantes da alfa para o fornecedor horizonte"
)

if entrada_usuario:
    with st.spinner("A pesquisar comprovativos..."):
        criterios = extrair_criterios_ia(entrada_usuario, df_indice)
        resultados = buscar_comprovantes(criterios, df_indice)

    if criterios.get("empresa") or criterios.get("fornecedor"):
        with st.expander("🔍 Critérios identificados", expanded=False):
            st.json(criterios)

    total = len(resultados)

    if total == 0:
        st.warning("Nenhum comprovativo encontrado para os termos indicados. Tente ajustar o nome da empresa ou fornecedor.")
    else:
        st.success(f"Foram encontrados **{total}** comprovativo(s) correspondente(s).")

        colunas = ["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF", "Página"]
        st.dataframe(
            resultados[[c for c in colunas if c in resultados.columns]],
            use_container_width=True
        )

        st.markdown("---")
        st.subheader("📑 Selecionar e descarregar comprovativo")

        opcoes = [
            f"Registo #{idx} | Data: {row.get('Data', 'N/D')} | Valor: R\$ {row.get('Valor', 'N/D')} | NF: {row.get('Nota Fiscal', 'N/D')}"
            for idx, row in resultados.iterrows()
        ]

        escolha = st.selectbox("Selecione o comprovativo na lista:", opcoes)

        if escolha:
            idx_sel = int(escolha.split(" | ")[0].replace("Registo #", ""))
            item_sel = resultados.loc[idx_sel]

            pdf_path = str(item_sel.get("PDF", ""))
            pag_num = int(item_sel.get("Página", 1))

            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Empresa:** {item_sel.get('Empresa', 'N/D')}")
                st.write(f"**Fornecedor:** {item_sel.get('Fornecedor', 'N/D')}")
                st.write(f"**Data:** {item_sel.get('Data', 'N/D')}")
                st.write(f"**Valor:** R\$ {item_sel.get('Valor', 'N/D')}")
                st.write(f"**Nota Fiscal:** {item_sel.get('Nota Fiscal', 'N/D')}")

            with col2:
                st.info(f"📄 **Ficheiro:** `{pdf_path}`\n\n📌 **Página:** `{pag_num}`")

                if os.path.exists(pdf_path):
                    pdf_bytes = extrair_pagina_pdf(pdf_path, pag_num)
                    st.download_button(
                        label="📥 Descarregar Comprovativo (Página Individual)",
                        data=pdf_bytes,
                        file_name=f"comprovativo_p{pag_num}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.warning(f"O ficheiro `{pdf_path}` não foi encontrado.")
