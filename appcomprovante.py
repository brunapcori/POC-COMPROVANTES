import os
import re
import json
import io
import zipfile
import pandas as pd
import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader, PdfWriter

# 1. Configuração da página e identidade visual
st.set_page_config(
    page_title="Ellenco | ComprovanteIA",
    page_icon="🏗️",
    layout="wide"
)

# Estilização CSS inspirada no portal corporativo da Ellenco
st.markdown("""
<style>
    /* Variáveis e paleta Ellenco */
    :root {
        --ellenco-blue: #0A2B5E;
        --ellenco-blue-dark: #071E42;
        --ellenco-red: #D7282F;
        --ellenco-gray-bg: #F8F9FA;
        --ellenco-border: #E2E8F0;
    }

    /* Cabeçalho corporativo */
    .ellenco-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1.2rem 2rem;
        background: linear-gradient(90deg, #071E42 0%, #0A2B5E 70%, #D7282F 100%);
        border-radius: 10px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    .ellenco-brand-title {
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin: 0;
        color: #FFFFFF;
    }
    .ellenco-brand-subtitle {
        font-size: 0.95rem;
        color: #E2E8F0;
        margin-top: 4px;
        font-weight: 400;
    }
    .ellenco-tag {
        background-color: rgba(255, 255, 255, 0.15);
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid rgba(255, 255, 255, 0.25);
    }

    /* Cartão de Detalhes do Comprovante */
    .comprovante-card {
        background-color: #FFFFFF;
        border: 1px solid var(--ellenco-border);
        border-left: 5px solid #0A2B5E;
        padding: 1.5rem;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        margin-top: 1rem;
    }
    .card-title {
        color: #0A2B5E;
        font-weight: 700;
        font-size: 1.15rem;
        margin-bottom: 1rem;
        border-bottom: 1px solid #EEF2F6;
        padding-bottom: 0.5rem;
    }
    .card-row {
        display: flex;
        justify-content: space-between;
        margin-bottom: 0.6rem;
        font-size: 0.95rem;
    }
    .card-label {
        color: #64748B;
        font-weight: 500;
    }
    .card-value {
        color: #1E293B;
        font-weight: 600;
    }
    .card-value-highlight {
        color: #D7282F;
        font-weight: 700;
        font-size: 1.1rem;
    }

    /* Ajuste para botões */
    div.stButton > button:first-child, div.stDownloadButton > button:first-child {
        background-color: #0A2B5E;
        color: white;
        border-radius: 6px;
        border: none;
        padding: 0.6rem 1.4rem;
        font-weight: 600;
        transition: all 0.3s;
    }
    div.stButton > button:first-child:hover, div.stDownloadButton > button:first-child:hover {
        background-color: #D7282F;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Banner superior da Ellenco
st.markdown("""
<div class="ellenco-header">
    <div>
        <h1 class="ellenco-brand-title">Ellenco <span style="color: #D7282F;">•</span> ComprovanteIA</h1>
        <div class="ellenco-brand-subtitle">Central Inteligente de Consulta e Validação de Comprovantes Financeiros</div>
    </div>
    <div class="ellenco-tag">Módulo Financeiro</div>
</div>
""", unsafe_allow_html=True)

# 2. Configurar chave de API Gemini
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if api_key:
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.warning(f"Aviso de configuração da API: {e}")

# 3. Descompactar arquivos .zip do repositório automaticamente
for item in os.listdir("."):
    if item.endswith(".zip"):
        try:
            with zipfile.ZipFile(item, 'r') as zip_ref:
                zip_ref.extractall(".")
        except Exception:
            pass

# 4. Leitura e normalização do catálogo CSV
CSV_FILE = "indice_comprovantes_ficticios.csv"

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
        elif "pagina" in col or "pag" in col:
            if "pagamento" not in col and "paga" not in col:
                renomear[col] = "Página"
            
    df = df.rename(columns=renomear)
    df = df.loc[:, ~df.columns.duplicated()]
    return df

df_indice = carregar_dados()

PROMPT_SISTEMA = """
Você é o assistente de busca do sistema corporativo ComprovanteIA da Ellenco.
Sua responsabilidade é extrair exclusivamente o nome ou identificador específico da empresa pagadora e do fornecedor.

Instruções cruciais:
- No campo "empresa", isole o nome distintivo (por exemplo, se o usuário citar "Empresa Delta", extraia apenas "Delta"; se citar "Alfa Engenharia", extraia "Alfa").
- No campo "fornecedor", isole o nome distintivo (por exemplo, se citar "Fornecedor Horizonte", extraia "Horizonte").
- Ignore datas, valores ou notas fiscais.
- Retorne estritamente um JSON com a estrutura:
{
  "empresa": null,
  "fornecedor": null
}
"""

def extrair_valores_seguros(df: pd.DataFrame, coluna: str) -> list:
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

    # Fallback refinado sem palavras genéricas como "empresa" ou "fornecedor"
    texto_limpo = texto_usuario.lower()
    palavras_ignorar = {"empresa", "empresas", "fornecedor", "fornecedores", "para", "comprovante", "comprovantes", "pagamento", "pagamentos", "de", "da", "do"}

    if not df.empty:
        if not criterios.get("empresa"):
            for val in set(extrair_valores_seguros(df, "Empresa")):
                palavras = [p.lower() for p in val.split() if p.lower() not in palavras_ignorar and len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    # Salva apenas a palavra distintiva (ex: Delta)
                    for p in palavras:
                        if p in texto_limpo:
                            criterios["empresa"] = p
                            break
                    break

        if not criterios.get("fornecedor"):
            for val in set(extrair_valores_seguros(df, "Fornecedor")):
                palavras = [p.lower() for p in val.split() if p.lower() not in palavras_ignorar and len(p) > 2]
                if any(p in texto_limpo for p in palavras):
                    for p in palavras:
                        if p in texto_limpo:
                            criterios["fornecedor"] = p
                            break
                    break

    return criterios

def isolar_termo_relevante(termo: str) -> str:
    """Remove termos genéricos como 'empresa', 'ltda', 's.a.' para buscar com precisão exata."""
    if not termo:
        return ""
    termos_ignorar = {"empresa", "fornecedor", "ltda", "ltda.", "s.a.", "sa", "s/a", "de", "da", "do"}
    partes = [p for p in str(termo).split() if p.lower() not in termos_ignorar]
    return partes[0] if partes else str(termo).strip()

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not criterios:
        return pd.DataFrame()

    resultado = df.copy()

    # Filtra por termo específico da Empresa (ex: "Delta")
    if criterios.get("empresa") and "Empresa" in resultado.columns:
        termo_emp = isolar_termo_relevante(criterios["empresa"])
        col_empresa = resultado["Empresa"]
        if isinstance(col_empresa, pd.DataFrame):
            col_empresa = col_empresa.iloc[:, 0]
        resultado = resultado[col_empresa.astype(str).str.contains(termo_emp, case=False, na=False)]

    # Filtra por termo específico do Fornecedor (ex: "Horizonte")
    if criterios.get("fornecedor") and "Fornecedor" in resultado.columns:
        termo_forn = isolar_termo_relevante(criterios["fornecedor"])
        col_forn = resultado["Fornecedor"]
        if isinstance(col_forn, pd.DataFrame):
            col_forn = col_forn.iloc[:, 0]
        resultado = resultado[col_forn.astype(str).str.contains(termo_forn, case=False, na=False)]

    return resultado

def converter_para_inteiro(valor_pagina) -> int:
    if pd.isna(valor_pagina):
        return 1
    numeros = re.findall(r'\d+', str(valor_pagina))
    return int(numeros[0]) if numeros else 1

def localizar_ficheiro_pdf(caminho_original: str) -> str:
    if not caminho_original:
        return ""
    caminho_limpo = caminho_original.replace("\\", os.sep).replace("/", os.sep).strip()
    if os.path.exists(caminho_limpo):
        return caminho_limpo

    nome_ficheiro = os.path.basename(caminho_limpo)
    for raiz, _, ficheiros in os.walk("."):
        if nome_ficheiro in ficheiros:
            return os.path.join(raiz, nome_ficheiro)
    return caminho_original

def extrair_pagina_pdf(caminho_pdf: str, numero_pagina: int) -> bytes:
    reader = PdfReader(caminho_pdf)
    writer = PdfWriter()
    indice = max(0, min(numero_pagina - 1, len(reader.pages) - 1))
    writer.add_page(reader.pages[indice])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# 5. Interface de Pesquisa
entrada_usuario = st.text_input(
    "Localizar Comprovante por Linguagem Natural",
    placeholder="Ex.: Empresa Delta para o fornecedor Horizonte"
)

if entrada_usuario:
    with st.spinner("Consultando registros corporativos..."):
        criterios = extrair_criterios_ia(entrada_usuario, df_indice)
        resultados = buscar_comprovantes(criterios, df_indice)

    if criterios.get("empresa") or criterios.get("fornecedor"):
        with st.expander("🔍 Parâmetros de Filtro Identificados", expanded=False):
            st.json(criterios)

    total = len(resultados)

    if total == 0:
        st.warning("Nenhum comprovante correspondente aos termos pesquisados. Verifique se o nome da empresa ou fornecedor está correto.")
    else:
        st.success(f"**{total}** comprovante(s) localizado(s) com sucesso para o filtro solicitado.")

        # Tabela corporativa
        colunas_mostrar = ["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF"]
        st.dataframe(
            resultados[[c for c in colunas_mostrar if c in resultados.columns]],
            width="stretch"
        )

        st.markdown("---")
        st.subheader("📑 Visualização e Download do Documento")

        opcoes = [
            f"Registro #{idx} | Data: {row.get('Data', 'N/D')} | Valor: R\$ {row.get('Valor', 'N/D')} | NF: {row.get('Nota Fiscal', 'N/D')}"
            for idx, row in resultados.iterrows()
        ]

        escolha = st.selectbox("Selecione o registro para emitir o PDF:", opcoes)

        if escolha:
            idx_sel = int(escolha.split(" | ")[0].replace("Registro #", ""))
            item_sel = resultados.loc[idx_sel]

            pdf_path_original = str(item_sel.get("PDF", ""))
            pdf_path = localizar_ficheiro_pdf(pdf_path_original)
            
            col_pagina_val = item_sel.get("Página") or item_sel.get("pagina") or 1
            pag_num = converter_para_inteiro(col_pagina_val)

            # Cartão de Detalhes
            col_detalhes, col_download = st.columns([1.5, 1])

            with col_detalhes:
                st.markdown(f"""
                <div class="comprovante-card">
                    <div class="card-title">Resumo do Lançamento</div>
                    <div class="card-row"><span class="card-label">Empresa Pagadora:</span> <span class="card-value">{item_sel.get('Empresa', 'N/D')}</span></div>
                    <div class="card-row"><span class="card-label">Fornecedor / Favorecido:</span> <span class="card-value">{item_sel.get('Fornecedor', 'N/D')}</span></div>
                    <div class="card-row"><span class="card-label">Data de Liquidação:</span> <span class="card-value">{item_sel.get('Data', 'N/D')}</span></div>
                    <div class="card-row"><span class="card-label">Documento / Nota Fiscal:</span> <span class="card-value">{item_sel.get('Nota Fiscal', 'N/D')}</span></div>
                    <div class="card-row"><span class="card-label">Valor Liquidado:</span> <span class="card-value-highlight">R\$ {item_sel.get('Valor', 'N/D')}</span></div>
                </div>
                """, unsafe_allow_html=True)

            with col_download:
                st.markdown(f"""
                <div class="comprovante-card" style="border-left-color: #D7282F;">
                    <div class="card-title">Arquivo Consolidado</div>
                    <div class="card-row"><span class="card-label">Arquivo:</span> <span class="card-value">{os.path.basename(pdf_path_original)}</span></div>
                    <div class="card-row"><span class="card-label">Página do Comprovante:</span> <span class="card-value">Pág. {pag_num}</span></div>
                </div>
                """, unsafe_allow_html=True)
                st.write("")
                
                if os.path.exists(pdf_path):
                    pdf_bytes = extrair_pagina_pdf(pdf_path, pag_num)
                    st.download_button(
                        label="📥 Baixar Comprovante (Página Individual em PDF)",
                        data=pdf_bytes,
                        file_name=f"comprovante_{item_sel.get('Empresa','doc')}_pag{pag_num}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error(f"O arquivo `{os.path.basename(pdf_path_original)}` não foi localizado no diretório extraído.")
