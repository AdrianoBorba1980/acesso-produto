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
CORS(app)  # Permite webhooks do Mercado Pago

# --- CONFIGURAÇÕES ---
# Supabase
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

# Mercado Pago
sdk = mercadopago.SDK(os.environ.get('MP_ACCESS_TOKEN'))

# E-mail (Gmail)
EMAIL_ADDRESS = os.environ.get('EMAIL_REMETENTE')
EMAIL_PASSWORD = os.environ.get('EMAIL_SENHA')

# --- FUNÇÃO AUXILIAR: ENVIAR EMAIL ---
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
        https://mpago.la/2nQxvKe
        
        Importante: Este link é exclusivo, pessoal e expira em 24h.
        """
    else:
        msg['Subject'] = "⏳ Seu Acesso Demo Chegou! - Scalper 72x9"
        corpo = f"""
        Olá! Obrigado por testar nosso robô.
        
        Aqui está seu acesso de demonstração (30 dias).
        
        🔗 CLIQUE PARA BAIXAR:
        https://mpago.la/1Yj1YWo
        
        Importante: Este link é exclusivo, pessoal e expira em 24h.
        """

    msg.set_content(corpo)

    try:
        # Configuração para Gmail (smtp.gmail.com, porta 465)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
            print(f"📧 Email enviado com sucesso para {destinatario}")
    except Exception as e:
        print(f"❌ Erro ao enviar email: {e}")

# --- WEBHOOK (RECEBE O PAGAMENTO) ---
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        
        # Filtra apenas notificações de pagamento
        if data and data.get('type') == 'payment':
            payment_id = data['data']['id']
            
            # Busca detalhes no Mercado Pago
            payment_info = sdk.payment().get(payment_id)
            payment = payment_info.get("response", {})
            
            if payment.get('status') == 'approved':
                email_cliente = payment['payer']['email']
                # LÊ O CÓDIGO DE REFERÊNCIA (REF_VITALICIO ou REF_DEMO)
                ref_code = payment.get('external_reference')
                
                print(f"🔎 Processando Ref: {ref_code} | Email: {email_cliente}")
                
                # --- DECISÃO PELO CÓDIGO ---
                if ref_code == 'REF_VITALICIO':
                    product_type = 'vitalicio'
                elif ref_code == 'REF_DEMO':
                    product_type = 'demo'
                else:
                    # Segurança: Se não tiver código, entrega o Demo
                    product_type = 'demo'
                    print(f"⚠️ Referência desconhecida ({ref_code}). Entregando DEMO.")

                # Gera Token
                token = str(uuid.uuid4())
                expires = datetime.datetime.now() + datetime.timedelta(hours=24)
                
                # Salva no Supabase
                supabase.table('acessos').insert({
                    'payment_id': str(payment_id),
                    'email': email_cliente,
                    'token': token,
                    'expires': expires.isoformat(),
                    'used': False,
                    'product_type': product_type
                }).execute()
                
                # --- ENVIA O E-MAIL COM O LINK ---
                # Ajuste aqui se sua URL no Render for diferente
                link_final = f"https://acesso-produto.onrender.com/acesso?token={token}"
                enviar_email_acesso(email_cliente, product_type, link_final)
                
                print(f"✅ Token criado e email disparado para {email_cliente}")
        
        return '', 200
    except Exception as e:
        print(f"❌ Erro webhook: {e}")
        return '', 200

# --- PÁGINA DE OBRIGADO ---
@app.route('/obrigado')
def obrigado():
    payment_id = request.args.get('payment_id', 'N/A')
    return render_template_string(f"""
<!DOCTYPE html>
<html>
<head><title>Verifique seu E-mail</title>
<style>
body {{ font-family: Arial; max-width: 600px; margin: 50px auto; text-align: center; }}
.aviso {{ background: #fff3cd; color: #856404; padding: 15px; border-radius: 5px; margin: 20px 0; }}
.btn {{ background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 18px; }}
</style>
</head>
<body>
<h1>✅ Pagamento Confirmado!</h1>
<p>ID do pedido: <strong>{payment_id}</strong></p>

<div class="aviso">
    <h3>🚀 Seu acesso foi enviado!</h3>
    <p>Verifique agora sua <strong>Caixa de Entrada</strong> ou <strong>Spam</strong>.</p>
    <p>O e-mail contém seu link exclusivo de download.</p>
</div>

<p>Dúvidas?</p>
<a href="https://wa.me/5524981161636" class="btn">📱 Suporte WhatsApp</a>
</body>
</html>
    """)

# --- ROTA DE DOWNLOAD (VALIDA O TOKEN) ---
@app.route('/acesso')
def acesso():
    token = request.args.get('token')
    if not token: return "❌ Token inválido", 403
    
    now = datetime.datetime.now().isoformat()
    
    # Valida no Supabase
    response = (supabase.table('acessos')
                .select('*')
                .eq('token', token)
                .eq('used', False)
                .gte('expires', now)
                .execute())
    
    if response.data:
        registro = response.data[0]
        # Queima o token (marca como usado)
        supabase.table('acessos').update({'used': True}).eq('token', token).execute()
        
        tipo_produto = registro.get('product_type', 'demo')
        
        # --- LINKS FINAIS DO DRIVE ---
        if tipo_produto == 'vitalicio':
            produto_link = "https://drive.google.com/file/d/1gE2ZtwTa-0pVojgHVv0IFFkR0WMpRTmW/view?usp=sharing"
            product_name = "Scalper 72x9 - Acesso VITALÍCIO 🏆"
            cor_titulo = "#d4af37" # Dourado
        else:
            produto_link = "https://drive.google.com/file/d/1HfyvtqEZkPBji1G6jg3VUT97Y8H9tlO0/view?usp=sharing"
            product_name = "Scalper 72x9 - Acesso DEMO (30 dias) ⏳"
            cor_titulo = "#28a745" # Verde
        
        # Exibe a tela bonita de download
        return render_template_string(f"""
<!DOCTYPE html>
<html>
<head><title>Acesso Liberado</title>
<style>
body {{ font-family: Arial; max-width: 600px; margin: 50px auto; text-align: center; background: #f8f9fa; }}
.container {{ background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
.btn {{ background: #007bff; color: white; padding: 20px 40px; text-decoration: none; border-radius: 8px; font-size: 20px; display: inline-block; margin: 20px 0; }}
h1 {{ color: {cor_titulo}; }}
.product-name {{ color: #333; font-size: 18px; margin: 10px 0; }}
</style>
</head>
<body>
<div class="container">
<h1>🎉 Acesso Liberado!</h1>
<p class="product-name"><strong>{product_name}</strong></p>
<p>Seu produto está pronto para download.</p>
<p><strong>Este link é único e pessoal.</strong></p>
<a href="{produto_link}" class="btn" target="_blank">⬇️ Baixar Produto Agora</a>
<p style="font-size: 14px; color: #666;">Link expira em 24h ou após 1 uso.</p>
</div>
</body>
</html>
        """)
    else:
        return render_template_string("""
<!DOCTYPE html>
<html><body style="font-family:Arial;text-align:center;padding:50px;">
<h2>❌ Link Expirado ou Já Utilizado</h2>
<p>Por segurança, nossos links são de uso único.</p>
<p>Se você teve problemas com o download, contate o suporte.</p>
<a href="https://wa.me/5524981161636">Chamar no WhatsApp</a>
</body></html>
        """), 403

@app.route('/')
def home():
    return "🚀 API de Proteção Scalper 72x9 Online"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)