import os
import json
import io
import zipfile
import pandas as pd
import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader, PdfWriter

# 1. Configuração inicial da página
st.set_page_config(
    page_title="ComprovanteIA",
    page_icon="🧾",
    layout="wide"
)

st.title("🧾 ComprovanteIA")
st.caption("Consulte comprovativos indicando apenas a empresa pagadora e o fornecedor")

# 2. Configurar chave de API
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if api_key:
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.warning(f"Aviso de configuração da API: {e}")

# 3. Descompactar ficheiros se necessário
ZIP_FILE = "comprovanteia_poc_consolidada.zip"
CSV_FILE = "indice_comprovantes_ficticios.csv"

if os.path.exists(ZIP_FILE) and not os.path.exists(CSV_FILE):
    try:
        with zipfile.ZipFile(ZIP_FILE, 'r') as zip_ref:
            zip_ref.extractall(".")
    except Exception as e:
        st.error(f"Erro ao descompactar ficheiro ZIP: {e}")

# 4. Carregar e padronizar os dados
def carregar_dados():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(CSV_FILE, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            df = pd.read_csv(CSV_FILE)
        except Exception:
            return pd.DataFrame()
        
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

def extrair_valores_seguros(df: pd.DataFrame, coluna: str) -> list:
    """Extrai uma lista de strings limpa de forma totalmente compatível com PyArrow e Pandas."""
    if coluna not in df.columns:
        return []
    dados = df[coluna]
    if isinstance(dados, pd.DataFrame):
        dados = dados.iloc[:, 0]
    return [str(x).strip() for x in dados.dropna().astype(str).tolist() if str(x).strip() != ""]

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
        # Identificação de termos de Empresa
        if not criterios.get("empresa"):
            for val in set(extrair_valores_seguros(df, "Empresa")):
                palavras = [p.lower() for p in val.split() if len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    criterios["empresa"] = val
                    break

        # Identificação de termos de Fornecedor
        if not criterios.get("fornecedor"):
            for val in set(extrair_valores_seguros(df, "Fornecedor")):
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
    writer.add_page(reader.pages[numero_pagina - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# 5. Entrada do utilizador e apresentação de resultados
entrada_usuario = st.text_input(
    "Como posso ajudar?",
    placeholder="Ex.: empresa alfa para o fornecedor horizonte"
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

        colunas_mostrar = ["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF", "Página"]
        st.dataframe(
            resultados[[c for c in colunas_mostrar if c in resultados.columns]],
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
                    st.warning(f"O ficheiro `{pdf_path}` não foi encontrado no servidor.")
