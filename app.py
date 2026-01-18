import os
import smtplib
import threading  # <--- IMPORTANTE: Biblioteca para segundo plano
from email.message import EmailMessage
from flask import Flask, request, render_template_string
from flask_cors import CORS
import mercadopago
import uuid
import datetime
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES ---
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(supabase_url, supabase_key)
sdk = mercadopago.SDK(os.environ.get('MP_ACCESS_TOKEN'))

# Configurações de Email
EMAIL_ADDRESS = os.environ.get('EMAIL_REMETENTE')
EMAIL_PASSWORD = os.environ.get('EMAIL_SENHA')

# --- FUNÇÃO DE ENVIO (AGORA RODA EM SEGUNDO PLANO) ---
def enviar_email_tarefa(destinatario, tipo_produto, link_acesso):
    """Esta função roda separada para não travar o servidor"""
    print(f"📧 Iniciando envio para {destinatario} em background...")
    
    msg = EmailMessage()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = destinatario
    
    if tipo_produto == 'vitalicio':
        msg['Subject'] = "🏆 Seu Acesso Vitalício Chegou! - Scalper 72x9"
        corpo = f"""
        Olá! Parabéns pela decisão.
        Aqui está seu acesso VIP e Vitalício ao Robô Scalper 72x9.
        
        🔗 CLIQUE PARA BAIXAR:
        {link_acesso}
        
        Importante: Este link é exclusivo e pessoal.
        """
    else:
        msg['Subject'] = "⏳ Seu Acesso Demo Chegou! - Scalper 72x9"
        corpo = f"""
        Olá! Obrigado por testar nosso robô.
        Aqui está seu acesso de demonstração (30 dias).
        
        🔗 CLIQUE PARA BAIXAR:
        {link_acesso}
        
        Importante: Este link é exclusivo e pessoal.
        """

    msg.set_content(corpo)

    try:
        # TENTATIVA 1: Porta 587 (TLS) - Geralmente melhor para Cloud
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
            print(f"✅ Email enviado com sucesso para {destinatario}")
    except Exception as e:
        print(f"❌ Erro ao enviar email (Porta 587): {e}")
        # TENTATIVA 2: Porta 465 (SSL) - Backup
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                smtp.send_message(msg)
                print(f"✅ Email enviado com sucesso (Backup SSL) para {destinatario}")
        except Exception as e2:
            print(f"❌ Erro fatal no envio de email: {e2}")

def disparar_email_async(destinatario, tipo_produto, link_acesso):
    # Cria a thread que vai rodar a função acima sem travar o código
    thread = threading.Thread(target=enviar_email_tarefa, args=(destinatario, tipo_produto, link_acesso))
    thread.start()

# --- WEBHOOK ---
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        if data and data.get('type') == 'payment':
            payment_id = data['data']['id']
            # Busca pagamento no MP
            payment_info = sdk.payment().get(payment_id)
            payment = payment_info.get("response", {})
            
            if payment.get('status') == 'approved':
                email_cliente = payment['payer']['email']
                ref_code = payment.get('external_reference')
                
                print(f"🔎 Pagamento Aprovado: {payment_id} | Email: {email_cliente}")
                
                if ref_code == 'REF_VITALICIO':
                    product_type = 'vitalicio'
                else:
                    product_type = 'demo'
                
                token = str(uuid.uuid4())
                expires = datetime.datetime.now() + datetime.timedelta(hours=24)
                
                # 1. Salva no Banco (Rápido)
                supabase.table('tabela-vendas-robo').insert({
                    'payment_id': str(payment_id),
                    'email': email_cliente,
                    'token': token,
                    'expires': expires.isoformat(),
                    'used': False,
                    'product_type': product_type
                }).execute()
                print("💾 Dados salvos no Supabase.")
                
                # 2. Dispara e-mail em SEGUNDO PLANO (Não espera resposta)
                link_final = f"https://acesso-produto.onrender.com/acesso?token={token}"
                disparar_email_async(email_cliente, product_type, link_final)

        # Responde OK imediatamente para o Mercado Pago não dar Timeout
        return '', 200
    except Exception as e:
        print(f"❌ Erro webhook: {e}")
        return '', 200

# --- GERADOR DE LINKS ---
@app.route('/admin')
def admin_links():
    pref_demo = sdk.preference().create({
        "items": [{"title": "Robô Scalper Demo (Teste)", "quantity": 1, "unit_price": 1.00}],
        "external_reference": "REF_DEMO",
        "back_urls": {"success": "https://acesso-produto.onrender.com/obrigado"}
    })
    link_demo = pref_demo["response"]["init_point"]

    pref_vital = sdk.preference().create({
        "items": [{"title": "Robô Scalper VITALÍCIO", "quantity": 1, "unit_price": 10.00}],
        "external_reference": "REF_VITALICIO",
        "back_urls": {"success": "https://acesso-produto.onrender.com/obrigado"}
    })
    link_vital = pref_vital["response"]["init_point"]

    return render_template_string(f"""
    <html>
    <head><style>body{{font-family:sans-serif;padding:40px;text-align:center;}} .box{{border:1px solid #ccc;padding:20px;margin:20px;border-radius:10px;}} a{{background:#009ee3;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;}}</style></head>
    <body>
        <h1>🏭 Fábrica de Links</h1>
        <div class="box"><h3>🧪 Demo (R$ 1,00)</h3><a href="{link_demo}" target="_blank">🔗 Link Pagamento</a></div>
        <div class="box"><h3>🏆 Vitalício (R$ 10,00)</h3><a href="{link_vital}" target="_blank">🔗 Link Pagamento</a></div>
    </body>
    </html>
    """)

# --- ROTA OBRIGADO (Monitoramento) ---
@app.route('/obrigado')
def obrigado():
    return "<h1>✅ Sistema Online e Monitorado.</h1>"

# --- ROTA DE DOWNLOAD ---
@app.route('/acesso')
def acesso():
    token = request.args.get('token')
    if not token: return "Token inválido", 403
    
    now = datetime.datetime.now().isoformat()
    res = supabase.table('tabela-vendas-robo').select('*').eq('token', token).eq('used', False).gte('expires', now).execute()
    
    if res.data:
        registro = res.data[0]
        supabase.table('tabela-vendas-robo').update({'used': True}).eq('token', token).execute()
        
        if registro.get('product_type') == 'vitalicio':
            link = "https://drive.google.com/file/d/1gE2ZtwTa-0pVojgHVv0IFFkR0WMpRTmW/view?usp=sharing"
            nome = "VITALÍCIO"
        else:
            link = "https://drive.google.com/file/d/1HfyvtqEZkPBji1G6jg3VUT97Y8H9tlO0/view?usp=sharing"
            nome = "DEMO (30 Dias)"
            
        return render_template_string(f"""
        <h1>🎉 Acesso Liberado: {nome}</h1>
        <a href="{link}">⬇️ Baixar Agora</a>
        """)
    else:
        return "<h1>Link expirado ou já usado.</h1>", 403

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)