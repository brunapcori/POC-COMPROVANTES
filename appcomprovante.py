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
    :root {
        --ellenco-blue: #0A2B5E;
        --ellenco-blue-dark: #071E42;
        --ellenco-red: #D7282F;
        --ellenco-gray-bg: #F8F9FA;
        --ellenco-border: #E2E8F0;
    }

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

    /* Estilo dos Cabeçalhos de Etapa */
    .step-box {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-left: 5px solid #0A2B5E;
        padding: 1rem 1.4rem;
        border-radius: 8px;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .step-box-2 {
        background-color: #FFF5F5;
        border: 1px solid #FED7D7;
        border-left: 5px solid #D7282F;
        padding: 1rem 1.4rem;
        border-radius: 8px;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .step-badge {
        display: inline-block;
        background-color: #0A2B5E;
        color: white;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 12px;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .step-badge-2 {
        display: inline-block;
        background-color: #D7282F;
        color: white;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 12px;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .step-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0F172A;
        margin: 0 0 4px 0;
    }
    .step-desc {
        font-size: 0.92rem;
        color: #475569;
        margin: 0;
    }

    .comprovante-card {
        background-color: #FFFFFF;
        border: 1px solid var(--ellenco-border);
        border-left: 5px solid #0A2B5E;
        padding: 1.5rem;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        margin-top: 0.5rem;
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
        font-size: 1.15rem;
    }

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

# Banner corporativo
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

# 3. Descompactar arquivos .zip automaticamente
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
Sua responsabilidade é extrair o nome ou termo distintivo da empresa pagadora, do fornecedor e o valor numérico, se mencionados pelo usuário.

Instruções:
- No campo "empresa", isole o nome distintivo (ex: se citar "Empresa Delta", retorne "Delta"). Caso não mencionado, retorne null.
- No campo "fornecedor", isole o nome distintivo (ex: se citar "Fornecedor Horizonte", retorne "Horizonte"). Caso não mencionado, retorne null.
- No campo "valor", extraia o valor numérico em formato float padrão (ex: se citar "R\$ 8.500,00", retorne 8500.0; se citar "18.790,40", retorne 18790.4). Caso não mencionado, retorne null.
- Retorne estritamente um JSON com a estrutura:
{
  "empresa": null,
  "fornecedor": null,
  "valor": null
}
"""

def converter_texto_para_float(valor_str) -> float:
    if valor_str is None or pd.isna(valor_str):
        return None
    if isinstance(valor_str, (int, float)):
        return float(valor_str)
    
    limpo = str(valor_str).replace("R$", "").replace("r$", "").strip()
    match = re.search(r'[\d.,]+', limpo)
    if not match:
        return None
    num_str = match.group(0)

    if "." in num_str and "," in num_str:
        if num_str.rfind(",") > num_str.rfind("."):
            num_str = num_str.replace(".", "").replace(",", ".")
        else:
            num_str = num_str.replace(",", "")
    elif "," in num_str:
        num_str = num_str.replace(",", ".")
    elif "." in num_str:
        partes = num_str.split(".")
        if len(partes[-1]) == 3 and len(partes) > 1:
            num_str = num_str.replace(".", "")

    try:
        return float(num_str)
    except Exception:
        return None

def extrair_valor_do_texto_usuario(texto: str):
    texto_sem_data = re.sub(r'\b\d{2,4}[-/]\d{2}[-/]\d{2,4}\b', '', texto)
    padroes = re.findall(r'(?:R\$\s*)?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|(?:R\$\s*)?\d+(?:[.,]\d{1,2})?', texto_sem_data)
    if padroes:
        return converter_texto_para_float(padroes[0])
    return None

def extrair_valores_seguros(df: pd.DataFrame, coluna: str) -> list:
    if coluna not in df.columns:
        return []
    dados = df[coluna]
    if isinstance(dados, pd.DataFrame):
        dados = dados.iloc[:, 0]
    return [str(x).strip() for x in dados.dropna().astype(str).tolist() if str(x).strip() != ""]

def extrair_criterios_ia(texto_usuario: str, df: pd.DataFrame) -> dict:
    criterios = {"empresa": None, "fornecedor": None, "valor": None}

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
                    criterios["empresa"] = dados.get("empresa")
                    criterios["fornecedor"] = dados.get("fornecedor")
                    criterios["valor"] = converter_texto_para_float(dados.get("valor"))
                    break
            except Exception:
                continue

    texto_limpo = texto_usuario.lower()
    palavras_ignorar = {"empresa", "empresas", "fornecedor", "fornecedores", "para", "comprovante", "comprovantes", "pagamento", "pagamentos", "de", "da", "do", "valor", "reais"}

    if not df.empty:
        if not criterios.get("empresa"):
            for val in set(extrair_valores_seguros(df, "Empresa")):
                palavras = [p.lower() for p in val.split() if p.lower() not in palavras_ignorar and len(p) > 2]
                if any(p in texto_limpo for p in palavras):
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

    if criterios.get("valor") is None:
        criterios["valor"] = extrair_valor_do_texto_usuario(texto_usuario)

    return criterios

def isolar_termo_relevante(termo: str) -> str:
    if not termo:
        return ""
    termos_ignorar = {"empresa", "fornecedor", "ltda", "ltda.", "s.a.", "sa", "s/a", "de", "da", "do"}
    partes = [p for p in str(termo).split() if p.lower() not in termos_ignorar]
    return partes[0] if partes else str(termo).strip()

def buscar_comprovantes(criterios: dict, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not criterios:
        return pd.DataFrame()

    if not criterios.get("empresa") and not criterios.get("fornecedor") and criterios.get("valor") is None:
        return pd.DataFrame()

    resultado = df.copy()

    if criterios.get("empresa") and "Empresa" in resultado.columns:
        termo_emp = isolar_termo_relevante(criterios["empresa"])
        col_empresa = resultado["Empresa"]
        if isinstance(col_empresa, pd.DataFrame):
            col_empresa = col_empresa.iloc[:, 0]
        resultado = resultado[col_empresa.astype(str).str.contains(termo_emp, case=False, na=False)]

    if criterios.get("fornecedor") and "Fornecedor" in resultado.columns:
        termo_forn = isolar_termo_relevante(criterios["fornecedor"])
        col_forn = resultado["Fornecedor"]
        if isinstance(col_forn, pd.DataFrame):
            col_forn = col_forn.iloc[:, 0]
        resultado = resultado[col_forn.astype(str).str.contains(termo_forn, case=False, na=False)]

    if criterios.get("valor") is not None and "Valor" in resultado.columns:
        valor_busca = float(criterios["valor"])
        col_val = resultado["Valor"]
        if isinstance(col_val, pd.DataFrame):
            col_val = col_val.iloc[:, 0]
        valores_df = col_val.apply(converter_texto_para_float)
        resultado = resultado[valores_df.apply(lambda x: x is not None and abs(x - valor_busca) < 0.01)]

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

def gerar_pdf_consolidado(lista_itens: list) -> bytes:
    writer = PdfWriter()
    for item in lista_itens:
        pdf_path_original = str(item.get("PDF", ""))
        pdf_path = localizar_ficheiro_pdf(pdf_path_original)
        pag_num = converter_para_inteiro(item.get("Página") or item.get("pagina") or 1)
        if os.path.exists(pdf_path):
            reader = PdfReader(pdf_path)
            indice = max(0, min(pag_num - 1, len(reader.pages) - 1))
            writer.add_page(reader.pages[indice])
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()

def gerar_zip_comprovantes(lista_itens: list) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, item in enumerate(lista_itens):
            pdf_path_original = str(item.get("PDF", ""))
            pdf_path = localizar_ficheiro_pdf(pdf_path_original)
            pag_num = converter_para_inteiro(item.get("Página") or item.get("pagina") or 1)
            emp = str(item.get("Empresa", "empresa")).replace(" ", "_")
            nf = str(item.get("Nota Fiscal", f"NF_{idx}")).replace(" ", "_")
            nome_arquivo_individual = f"comprovante_{emp}_{nf}_p{pag_num}.pdf"

            if os.path.exists(pdf_path):
                pdf_bytes = extrair_pagina_pdf(pdf_path, pag_num)
                zf.writestr(nome_arquivo_individual, pdf_bytes)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

# 5. Interface de Pesquisa
st.info("💡 **Como funciona:** A consulta é dividida em **2 etapas**. Na **Etapa 1**, você visualiza a listagem geral de todos os comprovantes encontrados. Na **Etapa 2** (logo abaixo da tabela), você seleciona exatamente quais PDFs deseja baixar.")

entrada_usuario = st.text_input(
    "🔍 Digite o que procura (Empresa, Fornecedor ou Valor):",
    placeholder="Ex.: empresa gama, pagamentos de R\$ 8.500,00 ou Empresa Delta para Horizonte"
)

if entrada_usuario:
    with st.spinner("Consultando registros corporativos..."):
        criterios = extrair_criterios_ia(entrada_usuario, df_indice)
        resultados = buscar_comprovantes(criterios, df_indice)

    if criterios.get("empresa") or criterios.get("fornecedor") or criterios.get("valor") is not None:
        with st.expander("🔍 Parâmetros de Filtro Identificados pela IA", expanded=False):
            st.json(criterios)

    total = len(resultados)

    if total == 0:
        st.warning("Nenhum comprovante correspondente aos termos pesquisados. Verifique o nome da empresa, fornecedor ou valor informado.")
    else:
        # ==================== ETAPA 1 ====================
        st.markdown(f"""
        <div class="step-box">
            <span class="step-badge">Etapa 1 de 2</span>
            <h3 class="step-title">📋 Lista de Comprovantes Localizados ({total} encontrados)</h3>
            <p class="step-desc">Esta tabela é apenas para <b>conferência geral</b> dos lançamentos encontrados. Para escolher e baixar os arquivos PDF, utilize a <b>Etapa 2</b> logo abaixo.</p>
        </div>
        """, unsafe_allow_html=True)

        colunas_mostrar = ["Data", "Empresa", "Fornecedor", "Valor", "Nota Fiscal", "PDF"]
        st.dataframe(
            resultados[[c for c in colunas_mostrar if c in resultados.columns]],
            width="stretch"
        )

        # ==================== ETAPA 2 ====================
        st.markdown("""
        <div class="step-box-2">
            <span class="step-badge-2">Etapa 2 de 2</span>
            <h3 class="step-title">📥 Seleção e Download dos Comprovantes em PDF</h3>
            <p class="step-desc">Escolha abaixo um ou mais registros (identificados com <b>Fornecedor</b>, Data, Valor e NF) para gerar e baixar os PDFs desejados.</p>
        </div>
        """, unsafe_allow_html=True)

        # Opções da Etapa 2 agora incluem Fornecedor e Empresa de forma clara
        mapa_opcoes = {
            f"Registro #{idx} | Fornecedor: {row.get('Fornecedor', 'N/D')} | Empresa: {row.get('Empresa', 'N/D')} | Data: {row.get('Data', 'N/D')} | Valor: R\$ {row.get('Valor', 'N/D')} | NF: {row.get('Nota Fiscal', 'N/D')}": idx
            for idx, row in resultados.iterrows()
        }
        todas_opcoes = list(mapa_opcoes.keys())

        col_ctrl1, col_ctrl2 = st.columns([1, 3])
        with col_ctrl1:
            selecionar_tudo = st.checkbox("Selecionar todos os comprovantes listados", value=False)

        itens_default = todas_opcoes if selecionar_tudo else ([todas_opcoes[0]] if todas_opcoes else [])

        escolhas = st.multiselect(
            "Clique no campo abaixo para adicionar ou remover comprovantes da lista de download:",
            options=todas_opcoes,
            default=itens_default
        )

        if escolhas:
            indices_selecionados = [mapa_opcoes[opt] for opt in escolhas]
            itens_selecionados = [resultados.loc[i] for i in indices_selecionados]
            qtd_sel = len(itens_selecionados)

            col_detalhes, col_download = st.columns([1.5, 1])

            with col_detalhes:
                if qtd_sel == 1:
                    item_sel = itens_selecionados[0]
                    st.markdown(f"""
                    <div class="comprovante-card">
                        <div class="card-title">Resumo do Lançamento Selecionado</div>
                        <div class="card-row"><span class="card-label">Empresa Pagadora:</span> <span class="card-value">{item_sel.get('Empresa', 'N/D')}</span></div>
                        <div class="card-row"><span class="card-label">Fornecedor / Favorecido:</span> <span class="card-value">{item_sel.get('Fornecedor', 'N/D')}</span></div>
                        <div class="card-row"><span class="card-label">Data de Liquidação:</span> <span class="card-value">{item_sel.get('Data', 'N/D')}</span></div>
                        <div class="card-row"><span class="card-label">Documento / Nota Fiscal:</span> <span class="card-value">{item_sel.get('Nota Fiscal', 'N/D')}</span></div>
                        <div class="card-row"><span class="card-label">Valor Liquidado:</span> <span class="card-value-highlight">R\$ {item_sel.get('Valor', 'N/D')}</span></div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    valores_num = []
                    for it in itens_selecionados:
                        val_conv = converter_texto_para_float(it.get('Valor', 0))
                        if val_conv is not None:
                            valores_num.append(val_conv)
                    total_soma = sum(valores_num)

                    st.markdown(f"""
                    <div class="comprovante-card">
                        <div class="card-title">Resumo do Lote Selecionado</div>
                        <div class="card-row"><span class="card-label">Quantidade de Comprovantes:</span> <span class="card-value">{qtd_sel} documentos</span></div>
                        <div class="card-row"><span class="card-label">Fornecedores Selecionados:</span> <span class="card-value">{', '.join(set([str(it.get('Fornecedor', '')) for it in itens_selecionados]))}</span></div>
                        <div class="card-row"><span class="card-label">Empresas Envolvidas:</span> <span class="card-value">{', '.join(set([str(it.get('Empresa', '')) for it in itens_selecionados]))}</span></div>
                        <div class="card-row"><span class="card-label">Valor Total do Lote:</span> <span class="card-value-highlight">R\$ {total_soma:,.2f}</span></div>
                    </div>
                    """, unsafe_allow_html=True)

            with col_download:
                if qtd_sel == 1:
                    item_sel = itens_selecionados[0]
                    pdf_path_original = str(item_sel.get("PDF", ""))
                    pdf_path = localizar_ficheiro_pdf(pdf_path_original)
                    pag_num = converter_para_inteiro(item_sel.get("Página") or item_sel.get("pagina") or 1)
                    nome_emp_seguro = str(item_sel.get('Empresa', 'doc')).replace(' ', '_')
                    nome_forn_seguro = str(item_sel.get('Fornecedor', 'forn')).replace(' ', '_')

                    st.markdown(f"""
                    <div class="comprovante-card" style="border-left-color: #D7282F;">
                        <div class="card-title">Arquivo Pronto para Download</div>
                        <div class="card-row"><span class="card-label">Arquivo Base:</span> <span class="card-value">{os.path.basename(pdf_path_original)}</span></div>
                        <div class="card-row"><span class="card-label">Página do Comprovante:</span> <span class="card-value">Pág. {pag_num}</span></div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.write("")

                    if os.path.exists(pdf_path):
                        pdf_bytes = extrair_pagina_pdf(pdf_path, pag_num)
                        st.download_button(
                            label="📥 Baixar Comprovante (PDF Individual)",
                            data=pdf_bytes,
                            file_name=f"comprovante_{nome_emp_seguro}_{nome_forn_seguro}_pag{pag_num}.pdf",
                            mime="application/pdf",
                            width="stretch"
                        )
                    else:
                        st.error(f"O arquivo `{os.path.basename(pdf_path_original)}` não foi localizado no diretório extraído.")
                else:
                    st.markdown(f"""
                    <div class="comprovante-card" style="border-left-color: #D7282F;">
                        <div class="card-title">Opções de Download em Lote</div>
                        <div class="card-row"><span class="card-label">Total Selecionado:</span> <span class="card-value">{qtd_sel} comprovantes</span></div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.write("")

                    pdf_lote_bytes = gerar_pdf_consolidado(itens_selecionados)
                    st.download_button(
                        label="📄 Baixar Todos em um Único PDF Consolidado",
                        data=pdf_lote_bytes,
                        file_name=f"comprovantes_lote_{qtd_sel}_itens.pdf",
                        mime="application/pdf",
                        width="stretch"
                    )

                    st.write("")
                    zip_lote_bytes = gerar_zip_comprovantes(itens_selecionados)
                    st.download_button(
                        label="📦 Baixar Todos Separados em Arquivo ZIP",
                        data=zip_lote_bytes,
                        file_name=f"comprovantes_lote_{qtd_sel}_arquivos.zip",
                        mime="application/zip",
                        width="stretch"
                    )
