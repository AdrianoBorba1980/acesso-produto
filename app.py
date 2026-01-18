import os
from flask import Flask, request, redirect, render_template_string
from flask_cors import CORS
import mercadopago
import uuid
import datetime
from supabase import create_client, Client

# Carrega variáveis de ambiente
load_dotenv()   

app = Flask(__name__)
CORS(app)  # Permite webhooks do Mercado Pago

# Config Supabase
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

# Config Mercado Pago (sandbox/teste)
sdk = mercadopago.SDK(os.environ.get('MP_ACCESS_TOKEN'))

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        body = request.get_data()
        signature_header = request.headers.get('x-signature')
        
        # Verifica signature (segurança)
        if signature_header:
            sdk.payment().get_received_events(body, signature_header)
        
        # Processa pagamento aprovado
        data = request.json
        if data and data.get('type') == 'payment':
            payment_id = data['data']['id']
            
            # Busca detalhes do pagamento
            payment = sdk.payment().find_by_id(payment_id)
            if payment.response['status'] == 'approved':
                email = payment.response['payer']['email']
                token = str(uuid.uuid4())
                expires = datetime.datetime.now() + datetime.timedelta(hours=24)
                
                # Salva no Supabase
                data_access = {
                    'payment_id': payment_id,
                    'email': email,
                    'token': token,
                    'expires': expires.isoformat(),
                    'used': False,
                    'product_type': 'demo'  # ou 'vitalicio' - você precisa configurar isso no webhook do Mercado Pago
                }
                supabase.table('acessos').insert(data_access).execute()
                
                print(f"✅ Token {token} criado para {email} (pagamento {payment_id})")
        
        return '', 200
    except Exception as e:
        print(f"❌ Erro webhook: {e}")
        return '', 200

@app.route('/obrigado')
def obrigado():
    payment_id = request.args.get('payment_id', 'N/A')
    return render_template_string(f"""
<!DOCTYPE html>
<html>
<head><title>Obrigado!</title>
<style>
body {{ font-family: Arial; max-width: 600px; margin: 50px auto; text-align: center; }}
.btn {{ background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 18px; }}
</style>
</head>
<body>
<h1>✅ Pagamento aprovado!</h1>
<p>ID: <strong>{payment_id}</strong></p>
<p>Seu link de acesso único foi enviado para seu e-mail.</p>
<p>Verifique a caixa de entrada ou spam. Expira em 24h.</p>
<a href="https://wa.me/5511999999999" class="btn">📱 Suporte WhatsApp</a>
</body>
</html>
    """)

@app.route('/acesso')
def acesso():
    token = request.args.get('token')
    if not token:
        return "❌ Token inválido", 403
    
    # Valida token no Supabase
    now = datetime.datetime.now().isoformat()
    response = (supabase.table('acessos')
                .select('*')
                .eq('token', token)
                .eq('used', False)
                .gte('expires', now)
                .execute())
    
    if response.data:
        # Marca como usado
        supabase.table('acessos').update({'used': True}).eq('token', token).execute()
        
        # Links específicos por tipo de produto
        response_data = response.data[0]
        product_type = response_data.get('product_type', 'demo')
        
        if product_type == 'demo':
            produto_link = "https://drive.google.com/file/d/1HfyvtqEZkPBji1G6jg3VUT97Y8H9tlO0/view?usp=sharing"
            product_name = "Scalper 72x9 - Acesso Demo (30 dias)"
        elif product_type == 'vitalicio':
            produto_link = "https://drive.google.com/file/d/1gE2ZtwTa-0pVojgHVv0IFFkR0WMpRTmW/view?usp=sharing"
            product_name = "Scalper 72x9 - Acesso Vitalício"
        else:
            produto_link = "https://drive.google.com/file/d/1HfyvtqEZkPBji1G6jg3VUT97Y8H9tlO0/view?usp=sharing"
            product_name = "Scalper 72x9"
        
        return render_template_string(f"""
<!DOCTYPE html>
<html>
<head><title>Acesso Liberado</title>
<style>
body {{ font-family: Arial; max-width: 600px; margin: 50px auto; text-align: center; background: #f8f9fa; }}
.container {{ background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
.btn {{ background: #007bff; color: white; padding: 20px 40px; text-decoration: none; border-radius: 8px; font-size: 20px; display: inline-block; margin: 20px 0; }}
h1 {{ color: #28a745; }}
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
<h2>❌ Acesso Expirado</h2>
<p>Token inválido, expirado ou já usado.</p>
<p>Entre em contato pelo WhatsApp para suporte.</p>
</body></html>
        """), 403

@app.route('/')
def home():
    return "🚀 API de Proteção de Produtos Online"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
