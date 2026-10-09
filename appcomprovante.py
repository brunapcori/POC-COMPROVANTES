#Início do projeto
import os
import json
import io
import zipfile
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from pypdf import PdfReader, PdfWriter

st.set_page_config(
    page_title="ComprovanteIA",
    page_icon="🧾",
    layout="wide"
)

# 1. Carregar chave de API (Streamlit Secrets prioritário, seguido por ambiente local)
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("Chave GEMINI_API_KEY não configurada nos Secrets do Streamlit.")
    st.stop()

client = genai.Client(api_key=api_key)

# 2. Descompactar ficheiros se necessário
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

# Prompt focado apenas na extração flexível de Empresa e Fornecedor
PROMPT_SISTEMA = """
Você é o assistente de busca do sistema ComprovanteIA.
Sua única responsabilidade é identificar a empresa pagadora e o fornecedor que foi pago mencionados pelo usuário, mesmo que os nomes sejam parciais ou aproximados.

Regras:
- Extraia apenas o termo ou nome da empresa pagadora no campo "empresa". Se não identificado, retorne null.
- Extraia apenas o termo ou nome do fornecedor/beneficiário no campo "fornecedor". Se não identificado, retorne null.
- NÃO exija nem extraia datas, valores ou números de notas fiscais.
- Retorne ESTRITAMENTE um JSON no seguinte formato:
{
  "empresa": "string ou null",
  "fornecedor": "string ou null"
}
"""

def extrair_criterios_ia(texto_usuario: str) -> dict:
    """Extrai os termos de empresa e fornecedor utilizando o modelo Gemini."""
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=texto_usuario,
            config=types.GenerateContentConfig(
                system_instruction=PROMPT_SISTEMA,
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Erro na interpretação da consulta: {e}")
        return {}

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Filtra o catálogo por correspondência parcial de empresa e fornecedor."""
    if df.empty or not criterios:
        return pd.DataFrame()

    resultado = df.copy()

    # Filtro parcial para Empresa (sem exigir correspondência exata)
    if criterios.get("empresa"):
        termo_empresa = str(criterios["empresa"]).strip()
        resultado = resultado[resultado["Empresa"].astype(str).str.contains(termo_empresa, case=False, na=False)]

    # Filtro parcial para Fornecedor (sem exigir correspondência exata)
    if criterios.get("fornecedor"):
        termo_fornecedor = str(criterios["fornecedor"]).strip()
        resultado = resultado[resultado["Fornecedor"].astype(str).str.contains(termo_fornecedor, case=False, na=False)]

    return resultado

def extrair_pagina_pdf(caminho_pdf: str, numero_pagina: int) -> bytes:
    """Extrai a página pretendida do ficheiro PDF consolidado."""
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    writer.add_page(reader.pages[numero_pagina - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# --- INTERFACE DE UTILIZADOR ---
st.title("🧾 ComprovanteIA")
st.caption("Consulte comprovativos informando apenas a empresa pagadora e o fornecedor")

entrada_usuario = st.text_input(
    "Como posso ajudar?",
    placeholder="Ex.: Pagamentos da Alfa para o fornecedor Horizonte"
)

if entrada_usuario:
    with st.spinner("A identificar termos e a pesquisar..."):
        criterios = extrair_criterios_ia(entrada_usuario)
        resultados = buscar_comprovantes(criterios, df_indice)

    if criterios:
        with st.expander("🔍 Critérios identificados", expanded=False):
            st.json(criterios)

    total_encontrados = len(resultados)

    if total_encontrados == 0:
        st.warning("Nenhum comprovativo encontrado para os termos indicados. Tente ajustar o nome da empresa ou do fornecedor.")
    else:
        st.success(f"Foram encontrados **{total_encontrados}** comprovativo(s) correspondente(s).")

        # Tabela com as colunas essenciais: Data, Empresa, Fornecedor, Valor e NF
        colunas_exibicao = ["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF", "Página"]
        st.dataframe(
            resultados[[c for c in colunas_exibicao if c in resultados.columns]],
            use_container_width=True
        )

        st.markdown("---")
        st.subheader("📑 Selecionar e descarregar comprovativo")

        # Menu de seleção para o utilizador escolher o registo pretendido
        opcoes = [
            f"Registo #{idx} | Data: {row.get('Data', 'N/D')} | Valor: R\$ {row.get('Valor', 'N/D')} | NF: {row.get('Nota Fiscal', 'N/D')}"
            for idx, row in resultados.iterrows()
        ]
        
        escolha = st.selectbox("Selecione o comprovativo na lista:", opcoes)

        if escolha:
            indice_selecionado = int(escolha.split(" | ")[0].replace("Registo #", ""))
            item_selecionado = resultados.loc[indice_selecionado]
            
            caminho_arquivo = str(item_selecionado.get("PDF", ""))
            numero_pagina = int(item_selecionado.get("Página", 1))

            col_det1, col_det2 = st.columns(2)
            with col_det1:
                st.write(f"**Empresa:** {item_selecionado.get('Empresa', 'N/D')}")
                st.write(f"**Fornecedor:** {item_selecionado.get('Fornecedor', 'N/D')}")
                st.write(f"**Data:** {item_selecionado.get('Data', 'N/D')}")
                st.write(f"**Valor:** R\$ {item_selecionado.get('Valor', 'N/D')}")
                st.write(f"**Nota Fiscal:** {item_selecionado.get('Nota Fiscal', 'N/D')}")

            with col_det2:
                st.info(f"📄 **Ficheiro:** `{caminho_arquivo}`\n\n📌 **Página:** `{numero_pagina}`")

                if os.path.exists(caminho_arquivo):
                    pdf_bytes = extrair_pagina_pdf(caminho_arquivo, numero_pagina)
                    st.download_button(
                        label="📥 Descarregar Comprovativo (Página Individual)",
                        data=pdf_bytes,
                        file_name=f"comprovativo_p{numero_pagina}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.warning(f"O ficheiro `{caminho_arquivo}` não foi encontrado no servidor.")
