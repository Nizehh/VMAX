import io
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask import Flask, request, render_template, redirect, url_for, make_response, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
import os
import csv
from io import StringIO
from werkzeug.utils import secure_filename
from functools import wraps
import qrcode
from sqlalchemy import or_, and_
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from datetime import timedelta
import locale
from cryptography.fernet import Fernet
from io import TextIOWrapper
from flask import make_response
from fpdf import FPDF
from flask import Response


if not os.path.exists("secret.key"):
    key = Fernet.generate_key()
    with open("secret.key", "wb") as key_file:
        key_file.write(key)
else:
    with open("secret.key", "rb") as key_file:
        key = key_file.read()

cipher_suite = Fernet(key)

# Configurações de Caminho
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, template_folder=os.path.join(base_dir, 'templates'))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'inventario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'static/uploads')
app.config['QR_FOLDER'] = os.path.join(base_dir, 'static/qrcodes')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7) 
app.secret_key = 'chave_snipeit_clone_segura'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configuração do "Lembrar-me" (7 dias)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Configurações do Servidor de E-mail (Exemplo Gmail)
# app.config['MAIL_SERVER'] = 'smtp.gmail.com'
# app.config['MAIL_PORT'] = 587
# app.config['MAIL_USE_TLS'] = True
# IMPORTANTE: Use variáveis de ambiente ou App Password do Google para segurança
# app.config['MAIL_USERNAME'] = 'seu_email_ti@gmail.com' 
# app.config['MAIL_PASSWORD'] = 'sua_senha_de_app'      
# app.config['MAIL_DEFAULT_SENDER'] = ('TI VMAX Suporte', 'seu_email_ti@gmail.com')

# Configurações de teste (SEM SMTP REAL)
app.config['MAIL_SERVER'] = 'localhost'
app.config['MAIL_PORT'] = 1025
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEBUG'] = True  # Isso faz o e-mail aparecer no terminal
app.config['MAIL_SUPPRESS_SEND'] = True # Impede o Flask de tentar conectar a um servidor real
app.config['MAIL_DEFAULT_SENDER'] = ('Sistema VMAX', 'nao-responda@vmax.com.br')
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Garante a existência das pastas de mídia
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['QR_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# --- MODELOS DE BANCO DE DADOS ---

class Usuario(UserMixin,db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(20), default='leitor')
    nome_completo = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    foto = db.Column(db.String(100), default='default_user.png')
    email_confirmado = db.Column(db.Boolean, default=False) 

class Colaborador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    setor = db.Column(db.String(100))
    ativos = db.relationship('Equipamento', backref='responsavel', lazy=True)

class Equipamento(db.Model):
    __tablename__ = 'equipamento'
    id = db.Column(db.Integer, primary_key=True)
    ativo_tag = db.Column(db.String(50), unique=True, nullable=True)
    hostname = db.Column(db.String(100)) # Usado como Modelo ou Nome da Licença
    marca = db.Column(db.String(100))
    serial_st = db.Column(db.String(100), nullable=True) # Removi unique=True pois Hardware/Acessorio podem não ter
    express_code = db.Column(db.String(100))
    termo = db.relationship('TermoResponsabilidade', backref='equipamento_rel', uselist=False, order_by='desc(TermoResponsabilidade.id)')
    imei1 = db.Column(db.String(50))
    imei2 = db.Column(db.String(50))
    email_licenca = db.Column(db.String(100)) # Novo para Licenças
    tipo_periferico = db.Column(db.String(50)) 
    
    # Financeiro (Compra vs Locação)
    tipo_aquisicao = db.Column(db.String(20), default='Compra') # 'Compra' ou 'Locacao'
    valor_locacao = db.Column(db.Float, nullable=True)
    data_locacao = db.Column(db.Date, nullable=True)
    vencimento_locacao = db.Column(db.Date, nullable=True)
    
    categoria = db.Column(db.String(50)) 
    status = db.Column(db.String(50), default="Pronto para implantar")
    foto = db.Column(db.String(200))
    observacoes = db.Column(db.Text)
    link_nf = db.Column(db.String(500))
    
    valor_compra = db.Column(db.Float, nullable=True)
    data_compra = db.Column(db.Date, nullable=True)
    garantia_expira = db.Column(db.Date, nullable=True)
    
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaborador.id'), nullable=True)
    ultimo_checkin = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    data_cadastro = db.Column(db.String(20), default=lambda: datetime.now().strftime('%d/%m/%Y'))

class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamento.id'), nullable=True)
    acao = db.Column(db.String(50)) 
    usuario_nome = db.Column(db.String(100))
    detalhe = db.Column(db.Text)
    data_hora = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class LogSistema(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100))  # Nome do usuário que fez a ação
    acao = db.Column(db.String(50))      # Ex: 'Criar', 'Editar', 'Excluir'
    detalhes = db.Column(db.String(500)) # Ex: 'Notebook Dell ID 5 excluído'
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)

class TermoResponsabilidade(db.Model):
    __tablename__ = 'termos_responsabilidade'
    id = db.Column(db.Integer, primary_key=True)
    conteudo = db.Column(db.Text, nullable=False)
    data_geracao = db.Column(db.DateTime, default=datetime.now)
    tipo_equipamento = db.Column(db.String(50)) # Adicione esta linha se não tiver, para salvar a categoria
    
    # AJUSTADO: Removido o "es" do final para bater com o nome das tabelas acima
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaborador.id')) 
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamento.id'))

class GerenciadorSenha(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_nome = db.Column(db.String(100), nullable=False)
    setor = db.Column(db.String(100))
    status = db.Column(db.String(50))
    email = db.Column(db.String(100))
    senha_email = db.Column(db.String(100))
    senha_ad = db.Column(db.String(100))
    usuario_dominio = db.Column(db.String(100))
    senha_sat = db.Column(db.String(100))
    ramal = db.Column(db.String(20))
    senha_ramal = db.Column(db.String(100))
    observacoes = db.Column(db.Text)

# Inicialização do Banco
with app.app_context():
    db.create_all()
    # Verifica se existe o admin
    admin_user = Usuario.query.filter_by(username='admin').first()

    if admin_user:
        admin_user.role = 'admin' # Força a promoção para admin
        db.session.commit()
        print("Usuário admin promovido com sucesso!")

    if not admin_user:
        # Se não existe, cria como ADMIN
        admin_padrao = Usuario(username='admin', senha='admin', role='admin')
        db.session.add(admin_padrao)
        db.session.commit()
    else:
        # (Opcional) Se o admin já existe mas não tem role (migration manual), forçamos aqui:
        if not admin_user.role:
            admin_user.role = 'admin'
            db.session.commit()

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.utf8')
except:
    locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil')

# --- CRIPTOGRAFIA ---

def encrypt_password(password):
    if not password: return None
    return cipher_suite.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    if not encrypted_password: return ""
    try:
        return cipher_suite.decrypt(encrypted_password.encode()).decode()
    except:
        return "Erro ao descriptografar"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

# --- FUNÇÕES AUXILIARES ---

def registrar_log(acao, detalhe, equip_id=None):
    novo_log = Historico(
        acao=acao,
        usuario_nome=session.get('username', 'Sistema'),
        detalhe=detalhe,
        equipamento_id=equip_id
    )
    db.session.add(novo_log)
    db.session.commit()

def gerar_qrcode_imagem(equip_id):
    dados = f"ID:{equip_id}" 
    qr = qrcode.make(dados)
    qr.save(os.path.join(app.config['QR_FOLDER'], f'qr_{equip_id}.png'))

def parse_date_safe(date_str):
    if date_str and date_str.strip():
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return None
    return None

def parse_float_safe(float_str):
    if float_str and float_str.strip():
        try:
            return float(float_str.replace(',', '.'))
        except ValueError:
            return None
    return None

@app.route('/importar_ativos', methods=['POST'])
@login_required
def importar_ativos():
    file = request.files.get('file')
    if not file:
        flash("Selecione um arquivo CSV.", "warning")
        return redirect(url_for('index'))

    try:
        stream = TextIOWrapper(file.stream, encoding='utf-8-sig')
        # Forçamos o delimitador ponto e vírgula que você está usando
        reader = csv.DictReader(stream, delimiter=';')

        itens_importados = 0
        for row in reader:
            # MAPEAMENTO: Pegamos o nome exato das colunas do seu arquivo
            # .get() com o nome que está no seu CSV: 'Tag', 'Serial', etc.
            tag = row.get('Tag', '').strip()
            
            # Se a Tag estiver vazia (como no seu ID 1), vamos usar o Serial ou o ID para não pular
            if not tag:
                tag = row.get('Serial', '').strip() or f"SN-{row.get('ID')}"

            # Tratamento para Marca/Modelo (Divide a string se houver uma barra)
            marca_modelo = row.get('Marca/Modelo', '')
            if '/' in marca_modelo:
                marca, modelo = marca_modelo.split('/', 1)
            else:
                marca = marca_modelo
                modelo = marca_modelo

            novo_item = Equipamento(
                ativo_tag=tag,
                categoria=row.get('Categoria', 'Outros').strip(),
                hostname=modelo.strip(),
                marca=marca.strip(),
                serial_st=row.get('Serial', '').strip(),
                status=row.get('Status', 'Disponível').strip(),
                data_cadastro=datetime.now().strftime('%d/%m/%Y')
            )
            db.session.add(novo_item)
            itens_importados += 1
        
        db.session.commit()
        flash(f"Sucesso! {itens_importados} itens importados.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Erro na leitura: {str(e)}", "danger")
        print(f"Erro detalhado: {e}")

    return redirect(url_for('index'))

@app.route('/exportar_ativos')
def exportar_ativos():
    ativos = Equipamento.query.all()
    
    def generate():
        data = io.StringIO()
        writer = csv.writer(data, delimiter=';')
        
        # Cabeçalho
        writer.writerow(['TIPO', 'NOME DO PC', 'SETOR', 'MODELO', 'ST', 'ATIVO', 'PROCESSADOR', 'MEMORIA', 'HD_SSD', 'WINDOWS'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)

        for a in ativos:
            writer.writerow([a.tipo, a.nome_pc, a.setor, a.modelo, a.service_tag, a.ativo, a.processador, a.memoria, a.hd_ssd, a.windows])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    response = Response(generate(), mimetype='text/csv')
    response.headers.set("Content-Disposition", "attachment", filename="inventario_vmax.csv")
    return response

# --- DECORADORES ---

def enviar_email_convite(email_destino, token):
    link = url_for('definir_senha', token=token, _external=True)
    
    # ESTA LINHA VAI GARANTIR QUE O LINK APAREÇA NO TERMINAL
    print("\n" + "="*50)
    print(f"📧 E-MAIL DE CONVITE PARA: {email_destino}")
    print(f"🔗 LINK DE ATIVAÇÃO: {link}")
    print("="*50 + "\n")

    msg = Message('Bem-vindo ao S-Inventário - Defina sua senha', recipients=[email_destino])
    msg.body = f'Olá! Sua conta foi criada. Clique no link para ativar: {link}'
    # ... resto do código da função
    #mail.send(msg)
    print(f"DEBUG: Link gerado: {link}")

@app.route('/salvar-termo/<int:equip_id>', methods=['POST'])
def salvar_termo(equip_id):
    equip = db.session.get(Equipamento, equip_id)
    
    # Pega o texto que o usuário pode ter editado na tela
    conteudo_final = request.form.get('conteudo_termo')
    
    if equip and equip.responsavel:
        novo_termo = TermoResponsabilidade(
            conteudo=conteudo_final,
            colaborador_id=equip.responsavel.id, # Atrelando ao colaborador
            equipamento_id=equip.id,
            data_geracao=datetime.now()
        )
        
        # Log do Sistema
        log = LogSistema(
            usuario=session.get('usuario_nome', 'Admin'),
            acao="Termo Salvo",
            detalhes=f"Termo oficializado para o ativo {equip.tag}",
            data_hora=datetime.now()
        )
        
        db.session.add(novo_termo)
        db.session.add(log)
        db.session.commit()
        
        flash("Termo salvo com sucesso!", "success")
        return redirect(url_for('visualizar_termo', termo_id=novo_termo.id))
    
    flash("Erro ao salvar: Equipamento sem responsável.", "danger")
    return redirect(url_for('dashboard'))


# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    user = Usuario.query.filter_by(username=session['username']).first()
    
    if request.method == 'POST':
        user.nome_completo = request.form.get('nome_completo')
        user.email = request.form.get('email')
        
        # 1. Validação de Senha
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')
        if nova_senha:
            if nova_senha == confirmar_senha:
                user.senha = nova_senha 
                registrar_log("Segurança", "Alterou a própria senha")
            else:
                flash('As senhas não coincidem!', 'danger')
                return redirect(url_for('perfil'))

        # 2. Upload de Foto com Regra de Limpeza
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '':
                # Define a extensão e o novo nome
                extensao = file.filename.rsplit('.', 1)[1].lower()
                nome_foto = secure_filename(f"profile_user_{user.id}.{extensao}")
                caminho_novo = os.path.join(app.config['UPLOAD_FOLDER'], nome_foto)

                # --- REGRA DE LIMPEZA: Apaga a foto antiga se ela existir e for diferente da nova ---
                if user.foto and user.foto != 'default_user.png':
                    caminho_antigo = os.path.join(app.config['UPLOAD_FOLDER'], user.foto)
                    if os.path.exists(caminho_antigo):
                        try:
                            os.remove(caminho_antigo)
                        except Exception as e:
                            print(f"Erro ao eliminar foto antiga: {e}")

                # Guarda a nova foto
                file.save(caminho_novo)
                user.foto = nome_foto
                session['user_foto'] = nome_foto

        db.session.commit()
        registrar_log("Perfil", "Atualizou informações de perfil")
        flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('perfil'))

    atividades = Historico.query.filter_by(usuario_nome=user.username)\
                                .order_by(Historico.data_hora.desc())\
                                .limit(5).all()
    
    return render_template('perfil.html', user=user, atividades=atividades)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 1. LIMPA O LIXO ANTES DE TENTAR LOGAR (O lugar correto é aqui)
        session.clear() 
        
        username = request.form.get('username')
        senha = request.form.get('senha')
        user = Usuario.query.filter_by(username=username).first()

        if user and user.senha == senha:
            if not user.email_confirmado:
                flash('Sua conta ainda não foi ativada.', 'warning')
                return redirect(url_for('login'))

            # 2. AGORA SIM, LOGA O USUÁRIO (A chave fica gravada na sessão)
            login_user(user, remember=True)
            
            session['username'] = user.username
            session['role'] = user.role
            session['user_id'] = user.id
            session['user_foto'] = user.foto if user.foto else 'default_user.png'
            session.permanent = True 
            
            return redirect(url_for('index'))
        
        flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # O current_user é preenchido automaticamente pelo Flask-Login
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Acesso negado. Você precisa ser administrador.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    if 'user_id' in session:
        user = Usuario.query.get(session['user_id'])
        return dict(usuario_logado=user)
    return dict(usuario_logado=None)

@app.route('/logout')
def logout():
    # --- LOG ADICIONADO ---
    if 'username' in session:
        registrar_log("Logout", f"Usuário {session['username']} saiu do sistema.")
    
    session.clear()
    return redirect(url_for('login'))

# --- SISTEMA DE EMAIL --- 

def gerar_token(email):
    return serializer.dumps(email, salt='recuperacao-senha')

def verificar_token(token, expiracao=3600): # 3600 segundos = 1 hora
    try:
        email = serializer.loads(token, salt='recuperacao-senha', max_age=expiracao)
        return email
    except:
        return None

def enviar_email_convite(email_destino, token):
    # Geramos o link primeiro
    link = url_for('definir_senha', token=token, _external=True)
    
    # FORÇAMOS O PRINT ANTES DE QUALQUER COISA DE E-MAIL
    print("\n" + "!"*50)
    print(f"ALERTA DE SISTEMA - CONVITE GERADO")
    print(f"PARA: {email_destino}")
    print(f"LINK: {link}")
    print("!"*50 + "\n")

    try:
        msg = Message('Bem-vindo ao S-Inventário', recipients=[email_destino])
        msg.body = f'Ative sua conta: {link}'
        # mail.send(msg) # Deixe comentado por enquanto para não travar no SMTP
    except Exception as e:
        print(f"Erro interno no Mail: {e}")

def enviar_email_recuperacao(email_destino, token):
    msg = Message('Recuperação de Senha - S-Inventário', recipients=[email_destino])
    link = url_for('definir_senha', token=token, _external=True)
    msg.body = f'Para redefinir sua senha, clique aqui: {link}'
    msg.html = f"""
    <h3>Esqueceu sua senha?</h3>
    <p>Não se preocupe. Clique no link abaixo para criar uma nova:</p>
    <a href="{link}" style="background:#0d6efd; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">Redefinir Senha</a>
    <p>Se você não solicitou isso, ignore este e-mail.</p>
    """
    mail.send(msg)

@app.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        user = Usuario.query.filter_by(email=email).first()
        
        if user:
            token = gerar_token(email)
            # Usando a função que já imprime no terminal para teste
            enviar_email_convite(email, token) 
            flash('Se o e-mail estiver cadastrado, você receberá um link em instantes.', 'info')
        else:
            # Por segurança, não confirmamos se o e-mail existe ou não
            flash('Se o e-mail estiver cadastrado, você receberá um link em instantes.', 'info')
        
        return redirect(url_for('login'))
        
    return render_template('esqueci_senha.html')

@app.route('/definir-senha/<token>', methods=['GET', 'POST'])
def definir_senha(token):
    email = verificar_token(token)
    if not email:
        flash('Link inválido ou expirado.', 'danger')
        return redirect(url_for('login'))
    
    user = Usuario.query.filter_by(email=email).first()
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        senha = request.form.get('senha')
        confirmar = request.form.get('confirmar')
        
        if senha == confirmar:
            user.senha = senha # Hash aqui se usar
            user.email_confirmado = True # Conta ativada!
            db.session.commit()
            registrar_log("Senha", f"Senha definida/alterada pelo usuário {user.username}")
            flash('Senha definida com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('As senhas não coincidem.', 'danger')

    return render_template('reset_senha.html', token=token)



# --- ROTAS DE USUÁRIOS (SISTEMA) ---

@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required 
def usuarios():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))

    if request.method == 'POST':
        print("DEBUG 1: Recebi o formulário de novo usuário")
        username = request.form.get('username')
        email = request.form.get('email')
        role = request.form.get('role')
        
        print(f"DEBUG 2: Dados extraídos - User: {username}, Email: {email}")

        usuario_existe = Usuario.query.filter((Usuario.username == username) | (Usuario.email == email)).first()
        
        if usuario_existe:
            print("DEBUG 3: Usuário já existe no banco")
            flash('Usuário ou E-mail já cadastrados.', 'danger')
        else:
            try:
                print("DEBUG 4: Tentando salvar no banco...")
                novo = Usuario(username=username, email=email, role=role, email_confirmado=False)
                db.session.add(novo)
                db.session.commit()
                print("DEBUG 5: Salvo no banco com sucesso!")

                print("DEBUG 6: Gerando token...")
                token = gerar_token(email)
                
                print("DEBUG 7: Chamando função de envio...")
                enviar_email_convite(email, token)
                
                flash(f'Convite enviado para {email}!', 'success')
            except Exception as e:
                print(f"DEBUG ERRO: Aconteceu um erro: {str(e)}")
                db.session.rollback()
                flash(f'Erro: {str(e)}', 'danger')

        return redirect(url_for('usuarios'))
    
    lista_usuarios = Usuario.query.all()
    return render_template('usuarios.html', usuarios=lista_usuarios)

@app.route('/deletar_usuario/<int:id>')
@login_required
@admin_required
def deletar_usuario(id):
    user = db.session.get(Usuario, id)
    if user:
        if user.username == 'admin':
            flash('O usuário administrador principal não pode ser removido.', 'warning')
        else:
            nome = user.username
            db.session.delete(user)
            db.session.commit()
            # O Log já existia aqui, mantido.
            registrar_log("Remoção de Usuário", f"Acesso removido: {nome}")
            flash('Acesso removido.', 'success')
    return redirect(url_for('usuarios'))

# --- ROTAS DE COLABORADORES ---

@app.route('/colaboradores', methods=['GET', 'POST'])
@login_required
@admin_required
def colaboradores():
    if request.method == 'POST':
        nome = request.form.get('nome')
        setor = request.form.get('setor')
        novo = Colaborador(nome=nome, cpf=request.form.get('cpf'), setor=setor)
        try:
            db.session.add(novo)
            db.session.commit()
            
            # --- LOG ADICIONADO ---
            registrar_log("Novo Colaborador", f"Cadastrou colaborador: {nome} (Setor: {setor})")
            
            flash('Colaborador cadastrado!', 'success')
        except:
            db.session.rollback()
            flash('Erro: CPF já cadastrado.', 'danger')
        return redirect(url_for('colaboradores'))
    lista = Colaborador.query.all()
    return render_template('colaboradores.html', colaboradores=lista)

# --- GESTÃO DE EQUIPAMENTOS ---

@app.route('/')
@login_required
def index():
    search_query = request.args.get('q', '').strip()
    query = Equipamento.query

    if search_query:
        query = query.join(Colaborador, isouter=True).filter(
            (Equipamento.ativo_tag.contains(search_query)) |
            (Equipamento.serial_st.contains(search_query)) |
            (Equipamento.hostname.contains(search_query)) |
            (Colaborador.nome.contains(search_query))
        )
    
    equipamentos = query.all()
    colaboradores = Colaborador.query.all()
    
    categorias = ['Notebook','Desktop', 'Monitor', 'Celular', 'Periférico', 'Acessório', 'Hardware', 'Ferramenta', 'Licença', 'Telefonia']
    resumo = {cat: Equipamento.query.filter_by(categoria=cat).count() for cat in categorias}
    
    total_valor = sum([e.valor_compra for e in equipamentos if e.valor_compra])
    alertas_garantia = 0
    hoje = datetime.now().date()
    for e in equipamentos:
        if e.garantia_expira and e.garantia_expira < hoje:
            alertas_garantia += 1

    stats = {
        'disponivel': Equipamento.query.filter_by(colaborador_id=None).count(),
        'em_uso': Equipamento.query.filter(Equipamento.colaborador_id != None).count(),
        'valor_patrimonio': f"{total_valor:,.2f}",
        'alertas': alertas_garantia
    }
    
    return render_template('index.html', equipamentos=equipamentos, colaboradores=colaboradores, resumo=resumo, stats=stats, hoje=hoje, search_query=search_query)

@app.route('/cadastrar_ativo', methods=['POST'])
@login_required
@admin_required
def cadastrar_ativo():
    try:
        categoria = request.form.get('categoria')
        
        # --- TRATAMENTO DE STRINGS VAZIAS ---
        # .strip() remove espaços extras. Se a string for vazia, o 'or None' transforma em None.
        serial = request.form.get('serial_st', '').strip() or None
        patrimonio = request.form.get('ativo', '').strip() or None
        
        # Validação de Duplicidade para Serial (Apenas se não for None)
        if serial:
            if Equipamento.query.filter_by(serial_st=serial).first():
                flash(f"Erro: O Serial/Service Tag '{serial}' já está cadastrado!", "danger")
                return redirect(url_for('index'))

        # Validação de Duplicidade para Patrimônio (Apenas se não for None)
        if patrimonio:
            if Equipamento.query.filter_by(ativo_tag=patrimonio).first():
                flash(f"Erro: O Patrimônio '{patrimonio}' já existe no sistema!", "danger")
                return redirect(url_for('index'))
        
        # Lógica de Aquisição
        tipo_aq = request.form.get('tipo_aquisicao', 'Compra')
        if categoria not in ['Notebook / Desktop', 'Monitor']:
            tipo_aq = 'Compra'

        # Upload de Foto
        foto_nome = 'default.png'
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '':
                foto_nome = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

        # Criação do Objeto com as variáveis tratadas (serial e patrimonio)
        novo_item = Equipamento(
            categoria=categoria,
            serial_st=serial,      # Variável limpa
            ativo_tag=patrimonio,  # Variável limpa
            hostname=request.form.get('nome'),
            marca=request.form.get('marca'),
            status='Pronto para implantar',
            foto=foto_nome,
            observacoes=request.form.get('observacoes'),
            link_nf=request.form.get('link_nf'),
            tipo_aquisicao=tipo_aq,
            valor_compra=parse_float_safe(request.form.get('valor_compra')),
            data_compra=parse_date_safe(request.form.get('data_compra')),
            garantia_expira=parse_date_safe(request.form.get('garantia_expira')),
            valor_locacao=parse_float_safe(request.form.get('valor_locacao')),
            data_locacao=parse_date_safe(request.form.get('data_locacao')),
            vencimento_locacao=parse_date_safe(request.form.get('vencimento_locacao')),
            imei1=request.form.get('imei1'),
            imei2=request.form.get('imei2'),
            email_licenca=request.form.get('email_licenca'),
            tipo_periferico=request.form.get('tipo_periferico')
        )

        db.session.add(novo_item)
        db.session.commit()
        
        # Gerar QR Code e Log
        gerar_qrcode_imagem(novo_item.id)
        registrar_log("Cadastro Ativo", f"{categoria} cadastrado: {novo_item.hostname}", novo_item.id)
        
        flash(f"{categoria} cadastrado com sucesso!", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Erro crítico ao cadastrar: {str(e)}", "danger")
        print(f"DEBUG ERRO: {e}") # Ajuda a ver no terminal o erro real
        
    return redirect(url_for('index'))

@app.route('/checkout/<int:id>', methods=['POST'])
@login_required
@admin_required
def checkout(id):
    equip = db.session.get(Equipamento, id)
    colab = db.session.get(Colaborador, request.form.get('colaborador_id'))
    if colab and equip:
        equip.colaborador_id = colab.id
        equip.status = "Em uso"
        # O Log já existia aqui, mantido.
        registrar_log("Checkout", f"Entregue para {colab.nome}", equip.id)
        db.session.commit()
        flash(f'Ativo entregue para {colab.nome}', 'primary')
    return redirect(request.referrer or url_for('index'))

@app.route('/equipamentos')
@login_required
def equipamentos():
    search_query = request.args.get('q', '').strip()
    filtro_cat = request.args.get('categoria', '').strip()
    filtro_status = request.args.get('status', '').strip()

    query = Equipamento.query

    if search_query:
        query = query.join(Colaborador, isouter=True).filter(
            (Equipamento.ativo_tag.contains(search_query)) |
            (Equipamento.serial_st.contains(search_query)) |
            (Equipamento.hostname.contains(search_query)) |
            (Colaborador.nome.contains(search_query))
        )

    if filtro_cat:
        query = query.filter(Equipamento.categoria == filtro_cat)

    if filtro_status:
        query = query.filter(Equipamento.status == filtro_status)

    itens = query.all()
    colaboradores = Colaborador.query.all()

    total = len(itens)
    em_uso = sum(1 for i in itens if i.status == 'Em uso')
    disponivel = sum(1 for i in itens if i.status == 'Pronto para implantar')
    manutencao = sum(1 for i in itens if i.status == 'Em manutenção')

    stats = {
        'total': total,
        'em_uso': em_uso,
        'disponivel': disponivel,
        'manutencao': manutencao
    }

    from collections import Counter
    marcas_raw = [i.marca for i in itens if i.marca]
    top_marcas = dict(Counter(marcas_raw).most_common(5))

    return render_template('equipamentos.html', 
                           equipamentos=itens, 
                           colaboradores=colaboradores,
                           stats=stats,
                           top_marcas=top_marcas,
                           filtros={'q': search_query, 'cat': filtro_cat, 'status': filtro_status})

@app.route('/checkin/<int:id>')
@login_required
@admin_required
def checkin(id):
    equip = db.session.get(Equipamento, id)
    if equip:
        nome_antigo = equip.responsavel.nome if equip.responsavel else "Estoque"
        equip.colaborador_id = None
        equip.status = "Pronto para implantar"
        # O Log já existia aqui, mantido.
        registrar_log("Checkin", f"Devolvido por {nome_antigo}", equip.id)
        db.session.commit()
        flash('Ativo retornado ao estoque', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/deletar/<int:id>')
@login_required
@admin_required
def deletar(id):
    if session.get('role') != 'admin':
        flash("Acesso negado! Você não tem permissão para excluir.", "danger")
        return redirect(url_for('dashboard'))

    item = db.session.get(Equipamento, id)
    
    if item:
        if item.colaborador_id:
            flash('Erro: Realize o Check-in antes de excluir.', 'danger')
        else:
            # Pegamos o nome do usuário logado
            usuario_logado = session.get('username') or "Desconhecido"
            
            modelo_equip = item.hostname or "Sem Modelo"
            serial_equip = item.serial_st or "Sem Serial"
            
            log = Historico(
                usuario_nome=usuario_logado,
                acao='Excluir',
                detalhe=f"Deletou o equipamento {modelo_equip} (Serial: {serial_equip})",
                equipamento_id=None # Definimos como None porque o item será deletado e o ID deixará de existir
            )
            
            db.session.add(log)
            db.session.delete(item)
            db.session.commit()
            flash('Item removido e log registrado.', 'success')
            
    return redirect(request.referrer or url_for('index'))

@app.route('/editar/<int:id>', methods=['POST'])
@login_required
@admin_required
def editar(id):
    item = db.session.get(Equipamento, id)
    if not item: return redirect(url_for('index'))

    # Captura valores antigos para o log (opcional, mas bom para detalhe)
    nome_antigo = item.hostname

    item.ativo_tag = request.form.get('ativo')
    item.hostname = request.form.get('nome')
    item.marca = request.form.get('marca')
    item.serial_st = request.form.get('serial_st')
    item.observacoes = request.form.get('observacoes')
    
    item.valor_compra = parse_float_safe(request.form.get('valor_compra'))
    item.garantia_expira = parse_date_safe(request.form.get('garantia_expira'))
    
    db.session.commit()
    
    # --- LOG ADICIONADO ---
    registrar_log("Edição", f"Atualizou dados do ativo: {nome_antigo} -> {item.hostname}", item.id)
    
    flash('Alterações salvas.', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/logs')
@login_required
def ver_logs():
    if session.get('role') != 'admin':
        os.abort(403)

    # Captura filtros da URL
    query_text = request.args.get('q', '').strip()
    user_filter = request.args.get('user', '').strip()
    acao_filter = request.args.get('acao', '').strip()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Base da consulta
    query = Historico.query

    # Filtro de Texto Geral (Descrição, ID ou Detalhe)
    if query_text:
        query = query.filter(or_(
            Historico.detalhe.contains(query_text),
            Historico.equipamento_id.contains(query_text)
        ))

    # Filtro de Usuário
    if user_filter:
        query = query.filter(Historico.usuario_nome.contains(user_filter))

    # Filtro de Ação
    if acao_filter:
        query = query.filter(Historico.acao == acao_filter)

    # Filtro de Data
    if start_date:
        query = query.filter(Historico.data_hora >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        # Adiciona 23:59:59 ao final da data para pegar o dia inteiro
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        query = query.filter(Historico.data_hora <= end_dt)

    # Ordenação e limite
    logs = query.order_by(Historico.data_hora.desc()).limit(500).all()
    
    return render_template('logs.html', logs=logs)

@app.route('/senhas', methods=['GET'])
@login_required
@admin_required
def gerenciar_senhas():
    query = request.args.get('q', '')
    setor_filtro = request.args.get('setor', '')
    
    # Busca base
    contas_query = GerenciadorSenha.query
    
    if query:
        contas_query = contas_query.filter(
            or_(
                GerenciadorSenha.usuario_nome.contains(query),
                GerenciadorSenha.email.contains(query),
                GerenciadorSenha.usuario_dominio.contains(query)
            )
        )
    
    if setor_filtro:
        contas_query = contas_query.filter_by(setor=setor_filtro)
    
    contas = contas_query.all()
    
    # Descriptografar senhas para exibição na tabela
    for c in contas:
        c.senha_email_dec = decrypt_password(c.senha_email)
        c.senha_ad_dec = decrypt_password(c.senha_ad)
        c.senha_sat_dec = decrypt_password(c.senha_sat)
        c.senha_ramal_dec = decrypt_password(c.senha_ramal)
    
    # Lista de setores únicos para o filtro
    setores = db.session.query(GerenciadorSenha.setor).distinct().all()
    setores = [s[0] for s in setores if s[0]]

    return render_template('senhas.html', senhas=contas, setores=setores)

@app.route('/salvar_senha', methods=['POST'])
@login_required
@admin_required
def salvar_senha():
    try:
        id_conta = request.form.get('id')
        # Garante que sempre haja um nome, mesmo se a sessão falhar
        usuario_operador = session.get('username') or 'Admin_Sistema'
        
        # Coleta de dados do formulário
        nome_usuario_alvo = request.form.get('usuario_nome')
        setor_alvo = request.form.get('setor')

        dados = {
            "usuario_nome": nome_usuario_alvo,
            "setor": setor_alvo,
            "status": request.form.get('status'),
            "email": request.form.get('email'),
            "senha_email": encrypt_password(request.form.get('senha_email')),
            "senha_ad": encrypt_password(request.form.get('senha_ad')),
            "usuario_dominio": request.form.get('usuario_dominio'),
            "senha_sat": encrypt_password(request.form.get('senha_sat')),
            "ramal": request.form.get('ramal'),
            "senha_ramal": encrypt_password(request.form.get('senha_ramal'))
        }

        if id_conta:
            conta = GerenciadorSenha.query.get(id_conta)
            for key, value in dados.items():
                setattr(conta, key, value)
            
            # Prepara o log de Edição
            log = LogSistema(
                usuario=usuario_operador,
                acao='Editar',
                detalhes=f"Editou acessos de: {nome_usuario_alvo} (Setor: {setor_alvo})"
            )
        else:
            nova_conta = GerenciadorSenha(**dados)
            db.session.add(nova_conta)
            
            # Prepara o log de Criação
            log = LogSistema(
                usuario=usuario_operador,
                acao='Criar',
                detalhes=f"Cadastrou novo usuário: {nome_usuario_alvo} no setor {setor_alvo}"
            )

        db.session.add(log)
        db.session.commit() # Salva tudo de uma vez
        
        flash("Operação realizada e registrada no log!", "success")
    except Exception as e:
        db.session.rollback() # Cancela se der erro
        flash(f"Erro ao salvar: {str(e)}", "danger")
        print(f"ERRO DE LOG: {e}") # Aparece no seu terminal do VS Code

    return redirect(url_for('gerenciar_senhas'))
@app.route('/deletar_senha/<int:id>')
@login_required
@admin_required
def deletar_senha(id):
    try:
        # Procura a credencial no banco de dados
        item = db.session.get(GerenciadorSenha, id)
        
        if item:
            nome_usuario = item.usuario_nome
            setor_usuario = item.setor
            
            # Remove do banco
            db.session.delete(item)
            db.session.commit()
            
            # Regista a ação nos logs (importante para segurança de TI)
            registrar_log("Exclusão de Credencial", f"Removeu acesso de {nome_usuario} ({setor_usuario})")
            
            flash(f"As credenciais de {nome_usuario} foram removidas com sucesso.", "warning")
        else:
            flash("Credencial não encontrada.", "danger")
            
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao eliminar: {str(e)}", "danger")
        
    return redirect(url_for('gerenciar_senhas'))

@app.route('/gerar-termo/<int:equip_id>', methods=['GET', 'POST'])
def gerar_termo(equip_id):
    # Usando db.session.get para evitar o LegacyAPIWarning
    equip = db.session.get(Equipamento, equip_id)
    if not equip:
        return "Equipamento não encontrado", 404

    if request.method == 'POST':
        conteudo = request.form.get('conteudo_termo')
        
        if not equip.responsavel:
            flash("Este equipamento não possui um responsável atrelado!", "danger")
            return redirect(url_for('equipamentos'))
        # 1. Salva o Termo
        novo_termo = TermoResponsabilidade(
            conteudo=conteudo,
            colaborador_id=equip.responsavel.id,  
            equipamento_id=equip.id,
            tipo_equipamento=equip.categoria,
            data_geracao=datetime.now()
        )
        db.session.add(novo_termo)
        
        # 2. LogSistema (Mesma lógica de antes)
        tag_log = getattr(equip, 'ativo_tag', getattr(equip, 'tag', 'N/A'))
        novo_log = LogSistema(
            usuario=session.get('usuario_nome', 'Admin'), 
            acao="Termo Gerado",
            detalhes=f"Termo criado para o ativo {tag_log}",
            data_hora=datetime.now()
        )
        db.session.add(novo_log)
        
        db.session.commit()
        return redirect(url_for('visualizar_termo', termo_id=novo_termo.id))

    # --- TEXTO COMPLETO (Baseado na sua imagem da VMAX) ---
    # Garantindo que as variáveis não venham vazias
    categoria = equip.categoria.upper() if equip.categoria else "NOTEBOOK"
    marca = equip.marca.upper() if equip.marca else "N/A"
    modelo = equip.modelo.upper() if hasattr(equip, 'modelo') and equip.modelo else "N/A"
    serial = equip.serial_st if hasattr(equip, 'serial_st') else "N/A"
    tag = getattr(equip, 'ativo_tag', getattr(equip, 'tag', 'N/A'))

    texto_base = f"""Declaro, para todos os fins e efeitos de direito, que recebi nesta data, para utilização funcional, 01 (um) {categoria} {marca} {modelo} ID-VMAX SERVICE TAG: {serial} - ATIVO: {tag}, com as seguintes especificações: especificações do notebook e Mochila para Notebook 15,6", o qual pertence à empresa VMAX TELECOM, CNPJ 14.609.353/0001-06, e que o uso deste equipamento está liberado de forma exclusiva para a comunicação entre as áreas da empresa e clientes, e apenas nos horários de execução de serviços, sendo expressamente proibido o uso após a jornada de trabalho, bem como é expressamente proibido o uso para fins particulares ou que não estejam ligados a execuções de serviços.

Declaro ainda que o equipamento e todos os demais itens me foram entregues nesta data em perfeito estado de funcionamento.

Responsabilizo-me pelo correto manuseio do equipamento e acessórios, comprometendo-me a mantê-los, conservá-los e guardá-los de forma correta, sendo responsável por eventuais perdas e danos, mau uso, bem como furto e roubo por negligência e imprudência, sendo que nestas hipóteses obrigo-me a reparar tais eventos arcando com os seus respectivos custos, bem como autorizo a EMPRESA a efetuar o desconto destes valores diretamente em folha de pagamento.

Comprometo-me a comunicar à empresa sobre a eventual necessidade de substituição em função do tempo de uso e de seu desgaste natural. Comprometo-me ainda a devolver em perfeito estado de uso os aparelhos e acessórios, na hipótese de eventual rescisão do contrato de trabalho, ou quando solicitado pela empresa.

Tenho ciência que devo realizar a devolução dos equipamentos ao setor de Tecnologia da Informação (TI) antes do início do período de férias, afastamento ou qualquer outro evento que suspenda ou interrompa a execução do meu contrato de trabalho, independente de notificação formal por parte da empregadora.

Declaro, finalmente, ter plena ciência de que o descumprimento dos procedimentos previstos neste termo de responsabilidade sobre a utilização e conservação do equipamento e seus acessórios caracteriza falta grave, estando sujeito à adoção das medidas cabíveis.

E, por ser verdade, firmo o presente termo, para que produza seus regulares efeitos de direito."""

    return render_template('editar_termo.html', equip=equip, texto=texto_base)

@app.route('/termos')
def listar_todos_termos():
    # Procura todos os termos e carrega os dados do colaborador e equipamento atrelados
    # Usamos o order_by para mostrar os últimos termos gerados no topo
    termos = TermoResponsabilidade.query.order_by(TermoResponsabilidade.data_geracao.desc()).all()
    
    # Criamos um dicionário para mapear os nomes dos colaboradores, já que o relacionamento pode ser manual
    # Isso evita o erro de 'colaborador' não definido que tivemos antes
    colaboradores = {c.id: c.nome for c in Colaborador.query.all()}
    
    return render_template('lista_termos.html', termos=termos, colaboradores=colaboradores)

@app.route('/etiqueta/<int:id>')
@login_required
def gerar_etiqueta(id):
    equip = db.session.get(Equipamento, id)
    caminho_qr = os.path.join(app.config['QR_FOLDER'], f'qr_{id}.png')
    if not os.path.exists(caminho_qr): gerar_qrcode_imagem(id)
    
    # --- LOG ADICIONADO ---
    registrar_log("Documento", f"Gerou Etiqueta QR Code para {equip.hostname}", equip.id)
    
    return render_template('etiqueta.html', e=equip)

@app.route('/visualizar-termo/<int:termo_id>')
def visualizar_termo(termo_id):
    termo = db.session.get(TermoResponsabilidade, termo_id)
    if not termo:
        return "Termo não encontrado", 404
    
    # Buscamos o colaborador separadamente
    colaborador = db.session.get(Colaborador, termo.colaborador_id)
    
    # Passamos as duas variáveis para o template
    return render_template('termo_vmax.html', termo=termo, colaborador=colaborador)


@app.route('/importar_csv', methods=['POST'])
@login_required
@admin_required
def importar_csv():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)

    if file:
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        
        for row in csv_input:
            nova_conta = GerenciadorSenha(
                usuario_nome=row.get('usuario_nome'),
                setor=row.get('setor'),
                status=row.get('status'),
                email=row.get('email'),
                senha_email=encrypt_password(row.get('senha_email')),
                senha_ad=encrypt_password(row.get('senha_ad')),
                usuario_dominio=row.get('usuario_dominio'),
                senha_sat=encrypt_password(row.get('senha_sat')),
                ramal=row.get('ramal'),
                senha_ramal=encrypt_password(row.get('senha_ramal'))
            )
            db.session.add(nova_conta)
        
        db.session.commit()
        flash("Importação concluída!", "success")
    
    return redirect(url_for('gerenciar_senhas'))

@app.route('/exportar')
@login_required
def exportar_csv():
    equipamentos = Equipamento.query.all()
    si = StringIO()
    cw = csv.writer(si, delimiter=';')
    cw.writerow(['ID', 'Tag', 'Marca/Modelo', 'Serial', 'Categoria', 'Status', 'Responsavel'])
    for e in equipamentos:
        resp = e.responsavel.nome if e.responsavel else "Estoque"
        cw.writerow([e.id, e.ativo_tag, e.marca, e.serial_st, e.categoria, e.status, resp])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=inventario.csv"
    output.headers["Content-type"] = "text/csv"
    
    # --- LOG ADICIONADO ---
    registrar_log("Exportação", "Gerou relatório completo em CSV (Download)")
    
    return output

@app.route('/relatorio_pdf')
@login_required
@admin_required
def relatorio_pdf():
    contas = GerenciadorSenha.query.all()
    
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Relatório de Credenciais por Setor - VMAX DIGITAL", ln=True, align='C')
    pdf.ln(5)
    
    # Cabeçalho da Tabela
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(238, 117, 17) # Laranja VMAX
    pdf.set_text_color(255, 255, 255)
    
    cols = ["Usuário", "Setor", "E-mail", "Senha E-mail", "Senha AD", "SAT", "Ramal"]
    widths = [40, 30, 50, 40, 40, 40, 35]
    
    for i in range(len(cols)):
        pdf.cell(widths[i], 8, cols[i], 1, 0, 'C', True)
    pdf.ln()
    
    # Dados
    pdf.set_font("Arial", '', 7)
    pdf.set_text_color(0, 0, 0)
    for c in contas:
        pdf.cell(widths[0], 7, str(c.usuario_nome), 1)
        pdf.cell(widths[1], 7, str(c.setor), 1)
        pdf.cell(widths[2], 7, str(c.email), 1)
        pdf.cell(widths[3], 7, decrypt_password(c.senha_email), 1)
        pdf.cell(widths[4], 7, decrypt_password(c.senha_ad), 1)
        pdf.cell(widths[5], 7, decrypt_password(c.senha_sat), 1)
        pdf.cell(widths[6], 7, str(c.ramal), 1)
        pdf.ln()
    
    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=relatorio_senhas.pdf'
    return response

@app.route('/categoria/<tipo>')
@login_required
def ver_categoria(tipo):
    mapa = {
        'notebooks':   {'nome': 'Notebook',           'cor': '#0d6efd'},
        'desktops':    {'nome': 'Desktop',            'cor': "#fd0dc9"},
        'monitores':   {'nome': 'Monitor',            'cor': '#6610f2'},
        'celulares':   {'nome': 'Celular',            'cor': '#fd7e14'},
        'perifericos': {'nome': 'Periférico',         'cor': '#20c997'},
        'acessorios':  {'nome': 'Acessório',          'cor': '#6f42c1'},
        'hardwares':   {'nome': 'Hardware',           'cor': '#adb5bd'},
        'ferramentas': {'nome': 'Ferramenta',         'cor': '#ffc107'},
        'licencas':    {'nome': 'Licença',            'cor': '#198754'},
        'telefonia':   {'nome': 'Telefonia',          'cor': '#dc3545'}
    }
    
    dados_cat = mapa.get(tipo, {'nome': tipo.capitalize(), 'cor': '#6c757d'})
    nome_cat = dados_cat['nome']
    cor_cat = dados_cat['cor']
    
    itens = Equipamento.query.filter_by(categoria=nome_cat).all()
    
    qtd_disponivel = sum(1 for i in itens if i.colaborador_id is None)
    qtd_em_uso = sum(1 for i in itens if i.colaborador_id is not None)
    
    stats = {
        'disponivel': qtd_disponivel,
        'em_uso': qtd_em_uso
    }
    
    colaboradores = Colaborador.query.order_by(Colaborador.nome).all()
    
    return render_template(
        'categoria.html', 
        itens=itens, 
        titulo=nome_cat, 
        cor=cor_cat,
        colaboradores=colaboradores, 
        stats=stats
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)