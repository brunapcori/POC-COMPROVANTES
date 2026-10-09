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

# 1. Carregar chave de API
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("Chave GEMINI_API_KEY não configurada nos Secrets do Streamlit.")
    st.stop()

client = genai.Client(api_key=api_key)

# 2. Descompactar arquivos se necessário
ZIP_FILE = "comprovanteia_poc_consolidada.zip"
if os.path.exists(ZIP_FILE) and not os.path.exists("indice_comprovantes_ficticios.csv"):
    with zipfile.ZipFile(ZIP_FILE, 'r') as zip_ref:
        zip_ref.extractall(".")

# 3. Carregar o índice de comprovantes
@st.cache_data
def carregar_dados():
    if not os.path.exists("indice_comprovantes_ficticios.csv"):
        return pd.DataFrame()
    return pd.read_csv("indice_comprovantes_ficticios.csv")

df_indice = carregar_dados()

PROMPT_SISTEMA = """
Você é o assistente inteligente de busca do sistema ComprovanteIA.
Sua responsabilidade é receber uma solicitação em linguagem natural e extrair os critérios exatos para busca.

Campos a extrair:
- empresa: Nome da empresa pagadora (ex.: "Alfa", "Empresa Alfa"). Se ausente, retorne null.
- fornecedor: Nome do fornecedor/beneficiário (ex.: "Horizonte"). Se ausente, retorne null.
- data: Data no formato DD/MM/AAAA (ex.: "01/09/2026"). Ano padrão: 2026. Se ausente, retorne null.
- nota_fiscal: Número da NF (ex.: "NF-202600004"). Se ausente, retorne null.
- valor: Valor numérico float (ex.: 12350.0). Se ausente, retorne null.

Responda ESTRITAMENTE em formato JSON puro, sem markdown:
{
  "empresa": null,
  "fornecedor": null,
  "data": null,
  "nota_fiscal": null,
  "valor": null
}
"""

def extrair_criterios_ia(texto_usuario: str) -> dict:
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
        st.error(f"Erro na consulta à IA: {e}")
        return {}

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not criterios:
        return pd.DataFrame()
    resultado = df.copy()
    if criterios.get("empresa"):
        resultado = resultado[resultado["Empresa"].str.contains(criterios["empresa"], case=False, na=False)]
    if criterios.get("fornecedor"):
        resultado = resultado[resultado["Fornecedor"].str.contains(criterios["fornecedor"], case=False, na=False)]
    if criterios.get("data"):
        resultado = resultado[resultado["Data"].astype(str).str.contains(criterios["data"], case=False, na=False)]
    if criterios.get("nota_fiscal"):
        resultado = resultado[resultado["Nota Fiscal"].astype(str).str.contains(criterios["nota_fiscal"], case=False, na=False)]
    if criterios.get("valor") is not None:
        resultado = resultado[resultado["Valor"] == float(criterios["valor"])]
    return resultado

def extrair_pagina_pdf(caminho_pdf: str, numero_pagina: int) -> bytes:
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    writer.add_page(reader.pages[numero_pagina - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

st.title("🧾 ComprovanteIA")
st.caption("Localização inteligente de comprovantes de pagamento a partir de linguagem natural")

entrada_usuario = st.text_input(
    "Como posso te ajudar?",
    placeholder="Ex.: Preciso do comprovante da Empresa Alfa pago para o Fornecedor Horizonte no dia 01/09."
)

if entrada_usuario:
    with st.spinner("Pesquisando..."):
        criterios = extrair_criterios_ia(entrada_usuario)
        resultados = buscar_comprovantes(criterios, df_indice)

    if criterios:
        with st.expander("🔍 Critérios identificados pela IA", expanded=False):
            st.json(criterios)

    total = len(resultados)
    if total == 0:
        st.warning("Nenhum comprovante foi encontrado com os critérios informados.")
    elif total == 1:
        item = resultados.iloc[0]
        st.success("✅ Comprovante Encontrado!")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Empresa:** {item.get('Empresa', 'N/D')}")
            st.markdown(f"**Fornecedor:** {item.get('Fornecedor', 'N/D')}")
            st.markdown(f"**Data:** {item.get('Data', 'N/D')}")
            st.markdown(f"**Valor:** R\$ {item.get('Valor', 'N/D')}")
            st.markdown(f"**Nota Fiscal:** {item.get('Nota Fiscal', 'N/D')}")
        with col2:
            st.info(f"📄 Arquivo: `{item.get('PDF', 'N/D')}` | Página: `{item.get('Página', 'N/D')}`")
            pdf_path = str(item.get("PDF", ""))
            pag = int(item.get("Página", 1))
            if os.path.exists(pdf_path):
                pdf_bytes = extrair_pagina_pdf(pdf_path, pag)
                st.download_button(
                    label="📥 Baixar Comprovante",
                    data=pdf_bytes,
                    file_name=f"comprovante_p{pag}.pdf",
                    mime="application/pdf"
                )
    else:
        st.info(f"Foram encontrados **{total}** comprovantes correspondentes.")
        st.dataframe(resultados[["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF", "Página"]], use_container_width=True)
