#Início do projeto
import os
import json
import io
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pypdf import PdfReader, PdfWriter

# Carrega variáveis de ambiente
load_dotenv()

# Configuração da página do Streamlit
st.set_page_config(
    page_title="ComprovanteIA",
    page_icon="🧾",
    layout="wide"
)

# Inicializa o cliente LLM
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Carrega o catálogo de comprovantes
@st.cache_data
def carregar_dados():
    df = pd.read_csv("indice_comprovantes_ficticios.csv")
    # Garante padronização nas colunas de texto para buscas insensíveis a maiúsculas
    return df

df_indice = carregar_dados()

# Prompt do Sistema para Extração de Entidades
PROMPT_SISTEMA = """
Você é o assistente inteligente de busca do sistema ComprovanteIA.
Sua responsabilidade é receber uma solicitação em linguagem natural e extrair os critérios exatos necessários para localizar comprovantes no índice.

Campos a extrair:
- empresa: Nome da empresa pagadora (ex.: "Alfa", "Empresa Alfa Engenharia S.A."). Se ausente, retorne null.
- fornecedor: Nome do fornecedor/beneficiário (ex.: "Horizonte", "Fornecedor Horizonte Ltda."). Se ausente, retorne null.
- data: Data no formato DD/MM/AAAA (ex.: "01/09/2026"). Ano padrão: 2026. Se ausente, retorne null.
- nota_fiscal: Número da NF (ex.: "NF-202600004", "NF-004"). Se ausente, retorne null.
- valor: Valor numérico float (ex.: 12350.0). Se ausente, retorne null.

Responda ESTRITAMENTE em formato JSON puro, sem marcações markdown ou texto extra:
{
  "empresa": null,
  "fornecedor": null,
  "data": null,
  "nota_fiscal": null,
  "valor": null
}
"""

def extrair_criterios_ia(texto_usuario: str) -> dict:
    """Chama a LLM para converter o texto em critérios estruturados."""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=texto_usuario,
        config=types.GenerateContentConfig(
            system_instruction=PROMPT_SISTEMA,
            response_mime_type="application/json",
            temperature=0.0
        )
    )
    return json.loads(response.text)

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Aplica os filtros dinâmicos via Pandas no índice."""
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
    """Extrai apenas a página específica do PDF consolidado para visualização/download."""
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    writer.add_page(reader.pages[numero_pagina - 1])  # 0-indexed
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# --- INTERFACE STREAMLIT ---
st.title("🧾 ComprovanteIA")
st.caption("Localização inteligente de comprovantes de pagamento a partir de linguagem natural")

# Barra de busca principal
entrada_usuario = st.text_input(
    "Como posso te ajudar?",
    placeholder="Ex.: Preciso do comprovante da Empresa Alfa pago para o Fornecedor Horizonte no dia 01/09."
)

if entrada_usuario:
    with st.spinner("Interpretando critérios e pesquisando..."):
        criterios = extrair_criterios_ia(entrada_usuario)
        resultados = buscar_comprovantes(criterios, df_indice)

    # Exibe os critérios identificados pela IA em um expansor
    with st.expander("🔍 Critérios identificados pela IA", expanded=False):
        st.json(criterios)

    # Tratamento dos resultados encontrados
    total_encontrados = len(resultados)

    if total_encontrados == 0:
        st.warning("Nenhum comprovante foi encontrado com os critérios informados. Tente detalhar melhor a busca.")
    
    elif total_encontrados == 1:
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
            st.info(f"📄 **Arquivo:** `{item.get('PDF', 'N/D')}`\n\n📌 **Página:** `{item.get('Página', 'N/D')}`")
            
            caminho_arquivo = item.get("PDF", "")
            pagina = int(item.get("Página", 1))

            if os.path.exists(caminho_arquivo):
                pdf_bytes = extrair_pagina_pdf(caminho_arquivo, pagina)
                st.download_button(
                    label="📥 Baixar Comprovante (Página Extraída)",
                    data=pdf_bytes,
                    file_name=f"comprovante_p{pagina}.pdf",
                    mime="application/pdf"
                )

    else:
        # Cenário de múltiplos resultados para desempate do usuário
        st.info(f"Foram encontrados **{total_encontrados}** comprovantes correspondentes. Selecione um abaixo:")
        
        st.dataframe(
            resultados[["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF", "Página"]],
            use_container_width=True
        )

        # Seletor para baixar/ver comprovante individual
        opcoes = [f"Linha {idx} - Data: {row['Data']} | NF: {row['Nota Fiscal']} | Valor: R\$ {row['Valor']}" 
                  for idx, row in resultados.iterrows()]
        escolha = st.selectbox("Escolha o comprovante para detalhes e download:", opcoes)
        
        if escolha:
            indice_selecionado = int(escolha.split(" - ")[0].replace("Linha ", ""))
            item_sel = resultados.loc[indice_selecionado]
            caminho_arquivo = item_sel.get("PDF", "")
            pagina = int(item_sel.get("Página", 1))

            if os.path.exists(caminho_arquivo):
                pdf_bytes = extrair_pagina_pdf(caminho_arquivo, pagina)
                st.download_button(
                    label=f"📥 Baixar Comprovante da Página {pagina}",
                    data=pdf_bytes,
                    file_name=f"comprovante_p{pagina}.pdf",
                    mime="application/pdf"
                )
