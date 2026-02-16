from app import app, db, Usuario

with app.app_context():
    # Busca o usuário admin existente
    admin = Usuario.query.filter_by(username='admin').first()
    
    if admin:
        admin.email_confirmado = True
        # Se você resetou o banco, aproveite para garantir que ele tenha um e-mail
        if not admin.email:
            admin.email = 'admin@vmax.com.br'
        
        db.session.commit()
        print(f"✅ Sucesso: O usuário '{admin.username}' foi confirmado e agora pode logar!")
    else:
        # Se por algum motivo ele não existir, cria do zero
        novo_admin = Usuario(
            username='admin',
            email='admin@vmax.com.br',
            role='admin',
            senha='admin',
            email_confirmado=True
        )
        db.session.add(novo_admin)
        db.session.commit()
        print("✅ Sucesso: Usuário admin criado do zero e confirmado!")