import os
import smtplib
from email.message import EmailMessage
from flask import Flask, request, redirect, render_template_string
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

# --- FUNÇÃO DE ENVIO DE E-MAIL ---
def enviar_email_acesso(destinatario, tipo_produto, link_acesso):
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
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
            print(f"📧 Email enviado para {destinatario}")
    except Exception as e:
        print(f"❌ Erro email: {e}")

# --- WEBHOOK (RECEBE O PAGAMENTO) ---
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        if data and data.get('type') == 'payment':
            payment_id = data['data']['id']
            payment_info = sdk.payment().get(payment_id)
            payment = payment_info.get("response", {})
            
            if payment.get('status') == 'approved':
                email_cliente = payment['payer']['email']
                ref_code = payment.get('external_reference')
                
                print(f"🔎 Pagamento Aprovado! Ref: {ref_code} | Email: {email_cliente}")
                
                if ref_code == 'REF_VITALICIO':
                    product_type = 'vitalicio'
                elif ref_code == 'REF_DEMO':
                    product_type = 'demo'
                else:
                    product_type = 'demo'
                
                token = str(uuid.uuid4())
                expires = datetime.datetime.now() + datetime.timedelta(hours=24)
                
                # Salva no Banco (Tabela Corrigida)
                supabase.table('tabela-vendas-robo').insert({
                    'payment_id': str(payment_id),
                    'email': email_cliente,
                    'token': token,
                    'expires': expires.isoformat(),
                    'used': False,
                    'product_type': product_type
                }).execute()
                
                link_final = f"https://acesso-produto.onrender.com/acesso?token={token}"
                enviar_email_acesso(email_cliente, product_type, link_final)

        return '', 200
    except Exception as e:
        print(f"❌ Erro webhook: {e}")
        return '', 200

# --- NOVO: GERADOR DE LINKS OFICIAIS ---
@app.route('/admin')
def admin_links():
    # Cria preferência do DEMO (R$ 1,00 para teste)
    pref_demo = sdk.preference().create({
        "items": [{"title": "Robô Scalper Demo (Teste)", "quantity": 1, "unit_price": 1.00}],
        "external_reference": "REF_DEMO",
        "back_urls": {"success": "https://acesso-produto.onrender.com/obrigado"}
    })
    link_demo = pref_demo["response"]["init_point"]

    # Cria preferência do VITALÍCIO (Ex: R$ 10,00 - Edite o valor aqui)
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
        <h1>🏭 Fábrica de Links Oficiais</h1>
        <p>Use estes links para vender. Eles estão conectados ao seu Robô!</p>
        
        <div class="box">
            <h3>🧪 Link DEMO (Teste R$ 1,00)</h3>
            <p>Este link entrega o arquivo DEMO.</p>
            <br>
            <a href="{link_demo}" target="_blank">🔗 Abrir Link de Pagamento</a>
        </div>

        <div class="box">
            <h3>🏆 Link VITALÍCIO (R$ 10,00)</h3>
            <p>Este link entrega o arquivo VITALÍCIO.</p>
            <br>
            <a href="{link_vital}" target="_blank">🔗 Abrir Link de Pagamento</a>
        </div>
    </body>
    </html>
    """)

# --- PÁGINA DE OBRIGADO ---
@app.route('/obrigado')
def obrigado():
    return "<h1>✅ Pagamento Recebido! Verifique seu e-mail.</h1>"

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
            link = "https://drive.google.com/file/d/1gE2ZtwTa-0pVojgHVv0IFFkR0WMpRTmW/view?usp=sharing" # SEU LINK VITALICIO
            nome = "VITALÍCIO"
        else:
            link = "https://drive.google.com/file/d/1HfyvtqEZkPBji1G6jg3VUT97Y8H9tlO0/view?usp=sharing" # SEU LINK DEMO
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