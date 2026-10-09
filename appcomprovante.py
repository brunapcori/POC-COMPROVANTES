#Início do projeto
import os
import json
import io
import zipfile
import pandas as pd
import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader, PdfWriter

# Configuração da página da aplicação
st.set_page_config(
    page_title="ComprovanteIA",
    page_icon="🧾",
    layout="wide"
)

# 1. Configurar chave de API
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# 2. Descompactar arquivos do repositório se necessário
ZIP_FILE = "comprovanteia_poc_consolidada.zip"
if os.path.exists(ZIP_FILE) and not os.path.exists("indice_comprovantes_ficticios.csv"):
    with zipfile.ZipFile(ZIP_FILE, 'r') as zip_ref:
        zip_ref.extractall(".")

# 3. Carregar o catálogo de comprovativos
@st.cache_data
def carregar_dados():
    if not os.path.exists("indice_comprovantes_ficticios.csv"):
        return pd.DataFrame()
    return pd.read_csv("indice_comprovantes_ficticios.csv")

df_indice = carregar_dados()

# Prompt focado em extrair apenas a empresa e o fornecedor
PROMPT_SISTEMA = """
Você é o assistente inteligente de busca do sistema ComprovanteIA.
Sua única responsabilidade é identificar a empresa pagadora e o fornecedor que foi pago mencionados pelo usuário, mesmo que sejam nomes parciais ou aproximados.

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
    """Interpreta os critérios da consulta via IA ou através de correspondência inteligente direta."""
    criterios = {"empresa": None, "fornecedor": None}

    # Tentativa de chamada aos modelos disponíveis no Gemini
    if api_key:
        modelos = ["gemini-1.5-flash-latest", "gemini-2.0-flash", "gemini-1.5-pro-latest", "gemini-1.5-flash"]
        for nome_modelo in modelos:
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

    # Mecanismo de contingência (fallback): identifica termos do catálogo diretamente no texto
    texto_limpo = texto_usuario.lower()
    if not df.empty:
        if not criterios.get("empresa"):
            for emp in df["Empresa"].dropna().unique():
                palavras = [p.lower() for p in str(emp).split() if len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    criterios["empresa"] = emp
                    break

        if not criterios.get("fornecedor"):
            for forn in df["Fornecedor"].dropna().unique():
                palavras = [p.lower() for p in str(forn).split() if len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    criterios["fornecedor"] = forn
                    break

    return criterios

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Filtra o índice permitindo correspondência parcial de empresa e fornecedor."""
    if df.empty or not criterios:
        return pd.DataFrame()

    resultado = df.copy()

    # Filtra por empresa se identificada (utiliza o termo principal)
    if criterios.get("empresa"):
        termo = str(criterios["empresa"]).strip().split()[0]
        resultado = resultado[resultado["Empresa"].astype(str).str.contains(termo, case=False, na=False)]

    # Filtra por fornecedor se identificado (utiliza o termo principal)
    if criterios.get("fornecedor"):
        termo = str(criterios["fornecedor"]).strip().split()[0]
        resultado = resultado[resultado["Fornecedor"].astype(str).str.contains(termo, case=False, na=False)]

    return resultado

def extrair_pagina_pdf(caminho_pdf: str, numero_pagina: int) -> bytes:
    """Extrai apenas a página indicada do ficheiro PDF consolidado."""
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    writer.add_page(reader.pages[numero_pagina - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# --- INTERFACE VISUAL STREAMLIT ---
st.title("🧾 ComprovanteIA")
st.caption("Consulte comprovativos indicando apenas a empresa pagadora e o fornecedor")

entrada_usuario = st.text_input(
    "Como posso ajudar?",
    placeholder="Ex.: comprovante da empresa alfa para o fornecedor horizonte"
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

        # Apresentação da tabela completa com Data, Empresa, Fornecedor, Valor e NF
        colunas = ["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF", "Página"]
        st.dataframe(
            resultados[[c for c in colunas if c in resultados.columns]],
            use_container_width=True
        )

        st.markdown("---")
        st.subheader("📑 Selecionar e descarregar comprovativo")

        # Lista suspensa com Data, Valor e NF para escolha precisa
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
