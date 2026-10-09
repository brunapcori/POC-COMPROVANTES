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

# 1. Configurar chave do Google AI Studio
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("Chave GEMINI_API_KEY não configurada nos Secrets do Streamlit.")
    st.stop()

# Configuração direta com o pacote google-generativeai
genai.configure(api_key=api_key)

# 2. Descompactar arquivos se necessário
ZIP_FILE = "comprovanteia_poc_consolidada.zip"
if os.path.exists(ZIP_FILE) and not os.path.exists("indice_comprovantes_ficticios.csv"):
    with zipfile.ZipFile(ZIP_FILE, 'r') as zip_ref:
        zip_ref.extractall(".")

# 3. Carregar índice de comprovativos
@st.cache_data
def carregar_dados():
    if not os.path.exists("indice_comprovantes_ficticios.csv"):
        return pd.DataFrame()
    return pd.read_csv("indice_comprovantes_ficticios.csv")

df_indice = carregar_dados()

# Prompt focado em extrair apenas Empresa e Fornecedor
PROMPT_SISTEMA = """
Você é o assistente de busca do sistema ComprovanteIA.
Sua responsabilidade é extrair termos parciais ou aproximados da empresa pagadora e do fornecedor mencionados pelo usuário.

Regras:
- Extraia o nome ou termo da empresa pagadora no campo "empresa". Caso não encontre, retorne null.
- Extraia o nome ou termo do fornecedor/beneficiário no campo "fornecedor". Caso não encontre, retorne null.
- Não extraia nem exija datas, valores ou número de nota fiscal.
- Retorne ESTRITAMENTE um JSON com esta estrutura:
{
  "empresa": null,
  "fornecedor": null
}
"""

def extrair_criterios_ia(texto_usuario: str) -> dict:
    """Interpreta a solicitação do usuário utilizando o modelo Gemini."""
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=PROMPT_SISTEMA,
            generation_config={"response_mime_type": "application/json", "temperature": 0.0}
        )
        response = model.generate_content(texto_usuario)
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Erro na consulta à IA: {e}")
        return {}

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Filtra o DataFrame por correspondência parcial sem exigir valores exatos."""
    if df.empty or not criterios:
        return pd.DataFrame()

    resultado = df.copy()

    if criterios.get("empresa"):
        termo = str(criterios["empresa"]).strip()
        resultado = resultado[resultado["Empresa"].astype(str).str.contains(termo, case=False, na=False)]

    if criterios.get("fornecedor"):
        termo = str(criterios["fornecedor"]).strip()
        resultado = resultado[resultado["Fornecedor"].astype(str).str.contains(termo, case=False, na=False)]

    return resultado

def extrair_pagina_pdf(caminho_pdf: str, numero_pagina: int) -> bytes:
    """Extrai apenas a página indicada do arquivo PDF."""
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    writer.add_page(reader.pages[numero_pagina - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# --- INTERFACE STREAMLIT ---
st.title("🧾 ComprovanteIA")
st.caption("Consulte comprovativos informando apenas a empresa pagadora e o fornecedor")

entrada_usuario = st.text_input(
    "Como posso ajudar?",
    placeholder="Ex.: Pagamentos da Alfa para o fornecedor Horizonte"
)

if entrada_usuario:
    with st.spinner("Pesquisando comprovativos..."):
        criterios = extrair_criterios_ia(entrada_usuario)
        resultados = buscar_comprovantes(criterios, df_indice)

    if criterios:
        with st.expander("🔍 Critérios identificados", expanded=False):
            st.json(criterios)

    total = len(resultados)

    if total == 0:
        st.warning("Nenhum comprovativo encontrado para os termos indicados. Tente ajustar o nome da empresa ou fornecedor.")
    else:
        st.success(f"Foram encontrados **{total}** comprovativo(s) correspondente(s).")

        colunas = ["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF", "Página"]
        st.dataframe(resultados[[c for c in colunas if c in resultados.columns]], use_container_width=True)

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
