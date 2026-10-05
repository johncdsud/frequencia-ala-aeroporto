from datetime import datetime, date
import streamlit as st
import pandas as pd
from supabase import create_client, Client
from PIL import Image
import io

# Configuração da Página
st.set_page_config(
    page_title="Frequência - Ala Aeroporto",
    page_icon="⛪",
    layout="wide"
)

# --- CONFIGURAÇÃO DO SUPABASE ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "SUA_URL_DO_SUPABASE")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "SUA_CHAVE_SUPABASE")

@st.cache_resource
def init_connection():
    if SUPABASE_URL == "SUA_URL_DO_SUPABASE" or SUPABASE_KEY == "SUA_CHAVE_SUPABASE":
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

if not supabase:
    st.error("⚠️ Configure as suas credenciais do Supabase nos Secrets do Streamlit antes de usar!")
    st.stop()

# --- FUNÇÕES AUXILIARES ---
def calcular_idade(data_nasc):
    if not data_nasc:
        return 0
    hoje = date.today()
    nasc = datetime.strptime(str(data_nasc), "%Y-%m-%d").date()
    return hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))

def obter_organizacao_efetiva(org, data_nasc, estado_civil):
    """Aplica a regra dos JAS: 18 a 35 anos + Solteiro no Quórum de Élderes ou Sociedade de Socorro"""
    idade = calcular_idade(data_nasc)
    if org in ["Quórum de Élderes", "Sociedade de Socorro"]:
        if 18 <= idade <= 35 and estado_civil == "Solteiro":
            return f"JAS - {org}"
    return org

# --- MENU LATERAL ---
st.sidebar.title("⛪ Ala Aeroporto")
st.sidebar.subheader("Controlo de Frequência")
menu = st.sidebar.radio("Navegação", [
    "📋 Frequência Dominical", 
    "👥 Gerir Membros", 
    "📥 Importar Planilha (Excel)", 
    "📊 Relatórios"
])

# ==========================================
# 1. FREQUÊNCIA DOMINICAL (CHAMADA)
# ==========================================
if menu == "📋 Frequência Dominical":
    st.title("📋 Chamada da Reunião Sacramental")
    
    hoje = date.today()
    idx = (hoje.weekday() + 1) % 7
    domingo_padrao = hoje - pd.Timedelta(days=idx)
    
    data_selecionada = st.date_input("Escolha a Data do Domingo:", value=domingo_padrao)
    
    if data_selecionada.weekday() != 6:
        st.warning("⚠️ A data selecionada não cai num domingo. As reuniões sacramentais ocorrem aos domingos.")

    response = supabase.table("membros").select("*").execute()
    membros = response.data

    if not membros:
        st.info("Nenhum membro registado. Vá a 'Gerir Membros' ou importe uma planilha.")
    else:
        orgs_disponiveis = [
            "Todas", 
            "Quórum de Élderes", 
            "Sociedade de Socorro", 
            "JAS - Quórum de Élderes", 
            "JAS - Sociedade de Socorro", 
            "Primária", 
            "Moças", 
            "Rapazes"
        ]
        filtro_org = st.selectbox("Filtrar por Organização:", orgs_disponiveis)

        freq_resp = supabase.table("frequencias").select("*").eq("data_domingo", str(data_selecionada)).execute()
        freq_map = {f["membro_id"]: f["presente"] for f in freq_resp.data}

        membros_filtrados = []
        for m in membros:
            org_efetiva = obter_organizacao_efetiva(m["organizacao"], m["data_nascimento"], m["estado_civil"])
            if filtro_org == "Todas" or filtro_org == org_efetiva:
                m_copia = m.copy()
                m_copia["org_efetiva"] = org_efetiva
                membros_filtrados.append(m_copia)

        st.write(f"A exibir **{len(membros_filtrados)}** membros para a organização: **{filtro_org}**")
        st.divider()

        for m in membros_filtrados:
            col1, col2, col3 = st.columns([1, 4, 2])
            
            with col1:
                if m.get("foto_url"):
                    st.image(m["foto_url"], width=60)
                else:
                    st.image("https://via.placeholder.com/60?text=Foto", width=60)
            
            with col2:
                st.markdown(f"**{m['nome']}**")
                st.caption(f"Org: {m['org_efetiva']} | Civil: {m.get('estado_civil', 'N/D')}")
            
            with col3:
                status_atual = freq_map.get(m["id"], None)
                
                b_col1, b_col2 = st.columns(2)
                with b_col1:
                    btn_presente = st.button("✓", key=f"p_{m['id']}", type="primary" if status_atual is True else "secondary")
                with b_col2:
                    btn_ausente = st.button("X", key=f"a_{m['id']}", type="primary" if status_atual is False else "secondary")
                
                if btn_presente:
                    supabase.table("frequencias").upsert({
                        "membro_id": m["id"],
                        "data_domingo": str(data_selecionada),
                        "presente": True
                    }, on_conflict="membro_id,data_domingo").execute()
                    st.rerun()
                
                if btn_ausente:
                    supabase.table("frequencias").upsert({
                        "membro_id": m["id"],
                        "data_domingo": str(data_selecionada),
                        "presente": False
                    }, on_conflict="membro_id,data_domingo").execute()
                    st.rerun()

            st.divider()

# ==========================================
# 2. GERIR MEMBROS
# ==========================================
elif menu == "👥 Gerir Membros":
    st.title("👥 Gestão de Membros")
    
    tab1, tab2 = st.tabs(["Registar / Editar", "Lista de Membros"])
    
    with tab1:
        st.subheader("Adicionar Novo Membro")
        with st.form("form_membro"):
            nome = st.text_input("Nome Completo")
            data_nascimento = st.date_input("Data de Nascimento", value=date(1990, 1, 1))
            organizacao = st.selectbox("Organização Base", ["Quórum de Élderes", "Sociedade de Socorro", "Primária", "Moças", "Rapazes"])
            estado_civil = st.selectbox("Estado Civil", ["Solteiro", "Casado", "Divorciado", "Viúvo"])
            telefone = st.text_input("Telefone (WhatsApp)")
            foto_arquivo = st.file_uploader("Foto do Membro", type=["jpg", "jpeg", "png"])
            
            submit = st.form_submit_button("Salvar Membro")
            
            if submit and nome:
                foto_url = None
                if foto_arquivo:
                    file_bytes = foto_arquivo.read()
                    file_path = f"membros/{datetime.now().timestamp()}_{foto_arquivo.name}"
                    supabase.storage.from_("fotos_membros").upload(file_path, file_bytes, {"content-type": foto_arquivo.type})
                    foto_url = supabase.storage.from_("fotos_membros").get_public_url(file_path)
                
                supabase.table("membros").insert({
                    "nome": nome,
                    "data_nascimento": str(data_nascimento),
                    "organizacao": organizacao,
                    "estado_civil": estado_civil,
                    "telefone": telefone,
                    "foto_url": foto_url
                }).execute()
                st.success(f"Membro {nome} registado com sucesso!")
                st.rerun()

    with tab2:
        st.subheader("Membros Registados")
        response = supabase.table("membros").select("*").execute()
        membros = response.data
        if membros:
            df = pd.DataFrame(membros)
            df['Idade'] = df['data_nascimento'].apply(calcular_idade)
            df['Org. Efetiva'] = df.apply(lambda row: obter_organizacao_efetiva(row['organizacao'], row['data_nascimento'], row['estado_civil']), axis=1)
            st.dataframe(df[['nome', 'Idade', 'Org. Efetiva', 'estado_civil', 'telefone']])
        else:
            st.info("Nenhum membro registado.")

# ==========================================
# 3. IMPORTAR PLANILHA (EXCEL)
# ==========================================
elif menu == "📥 Importar Planilha (Excel)":
    st.title("📥 Importação em Massa (Excel)")
    st.markdown("""
    Envie um ficheiro em formato **Excel (.xlsx)** contendo as seguintes colunas exatas:
    * `nome`
    * `data_nascimento` (Formato AAAA-MM-DD ou DD/MM/AAAA)
    * `organizacao` (Quórum de Élderes, Sociedade de Socorro, Primária, Moças, Rapazes)
    * `estado_civil` (Solteiro ou Casado)
    * `telefone`
    """)
    
    arquivo_excel = st.file_uploader("Escolha o ficheiro Excel", type=["xlsx"])
    
    if arquivo_excel:
        df_import = pd.read_excel(arquivo_excel)
        st.write("Pré-visualização dos dados encontrados:")
        st.dataframe(df_import.head())
        
        if st.button("Confirmar Importação"):
            contador = 0
            for _, row in df_import.iterrows():
                try:
                    dt_nasc = pd.to_datetime(row['data_nascimento']).strftime('%Y-%m-%d')
                    supabase.table("membros").insert({
                        "nome": str(row['nome']),
                        "data_nascimento": dt_nasc,
                        "organizacao": str(row['organizacao']),
                        "estado_civil": str(row.get('estado_civil', 'Solteiro')),
                        "telefone": str(row.get('telefone', ''))
                    }).execute()
                    contador += 1
                except Exception as e:
                    print(f"Erro ao importar {row.get('nome')}: {e}")
            st.success(f"{contador} membros importados com sucesso!")

# ==========================================
# 4. RELATÓRIOS
# ==========================================
elif menu == "📊 Relatórios":
    st.title("📊 Relatórios de Frequência")
    
    freq_resp = supabase.table("frequencias").select("data_domingo").execute()
    if freq_resp.data:
        datas = sorted(list(set([f["data_domingo"] for f in freq_resp.data])), reverse=True)
        data_escolhida = st.selectbox("Selecione o Domingo para ver o resumo:", datas)
        
        if data_escolhida:
            detalhes = supabase.table("frequencias").select("presente, membros(nome, organizacao, data_nascimento, estado_civil)").eq("data_domingo", data_escolhida).execute()
            
            dados_rel = []
            for item in detalhes.data:
                m = item["membros"]
                if m:
                    org_ef = obter_organizacao_efetiva(m["organizacao"], m["data_nascimento"], m["estado_civil"])
                    dados_rel.append({
                        "Nome": m["nome"],
                        "Organização": org_ef,
                        "Presente": "Sim" if item["presente"] else "Não"
                    })
            
            if dados_rel:
                df_rel = pd.DataFrame(dados_rel)
                st.dataframe(df_rel)
                
                total = len(df_rel)
                presentes = len(df_rel[df_rel["Presente"] == "Sim"])
                st.metric("Total Presentes", f"{presentes} / {total} ({int((presentes/total)*100)}% se houver lista completa)")
    else:
        st.info("Nenhum registo de frequência encontrado ainda.")
              
