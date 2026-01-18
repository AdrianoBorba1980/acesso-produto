import os
from flask import Flask, request, redirect, render_template_string
from flask_cors import CORS
import mercadopago
import uuid
import datetime
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)  # Permite webhooks do Mercado Pago

# Config Supabase
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

# Config Mercado Pago
sdk = mercadopago.SDK(os.environ.get('MP_ACCESS_TOKEN'))

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Processa notificação
        data = request.json
        
        # Log para debug (opcional)
        print(f"Recebido: {data}")

        if data and data.get('type') == 'payment':
            payment_id = data['data']['id']
            
            # Busca detalhes do pagamento na API do MP
            payment = sdk.payment().get(payment_id) # Atenção: mudei de .find_by_id para .get (padrão novo)
            payment_response = payment["response"] # O SDK retorna um dicionário com "response"
            
            # Se o pagamento foi aprovado
            if payment_response['status'] == 'approved':
                payer_email = payment_response['payer']['email']
                transaction_amount = float(payment_response.get('transaction_amount', 0))
                
                # --- LÓGICA DE PREÇO AQUI ---
                if transaction_amount > 100.00:
                    tipo_produto = 'vitalicio'
                    print(f"💰 Venda VITALÍCIA detectada: R$ {transaction_amount}")
                else:
                    tipo_produto = 'demo'
                    print(f"💰 Venda DEMO detectada: R$ {transaction_amount}")

                # Gera Token
                token = str(uuid.uuid4())
                expires = datetime.datetime.now() + datetime.timedelta(hours=24)
                
                # Salva no Supabase
                data_access = {
                    'payment_id': str(payment_id),
                    'email': payer_email,
                    'token': token,
                    'expires': expires.isoformat(),
                    'used': False,
                    'product_type': tipo_produto
                }
                supabase.table('acessos').insert(data_access).execute()
                
                print(f"✅ Token criado para {payer_email}")
        
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
<a href="https://wa.me/5524981161636" class="btn">📱 Suporte WhatsApp</a>
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
        # Marca como usado IMEDIATAMENTE (segurança contra F5)
        supabase.table('acessos').update({'used': True}).eq('token', token).execute()
        
        # Pega os dados para saber qual link entregar
        registro = response.data[0]
        tipo_produto = registro.get('product_type', 'demo')
        
        # --- LÓGICA DE ENTREGA DOS LINKS ---
        if tipo_produto == 'vitalicio':
            produto_link = "https://drive.google.com/file/d/1gE2ZtwTa-0pVojgHVv0IFFkR0WMpRTmW/view?usp=sharing"
            product_name = "Scalper 72x9 - Acesso VITALÍCIO 🚀"
            cor_titulo = "#d4af37" # Dourado
        else:
            # Caso seja 'demo' ou qualquer outro erro, entrega o demo
            produto_link = "https://drive.google.com/file/d/1HfyvtqEZkPBji1G6jg3VUT97Y8H9tlO0/view?usp=sharing"
            product_name = "Scalper 72x9 - Acesso DEMO (30 dias) ⏳"
            cor_titulo = "#28a745" # Verde
        
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
<h2>❌ Acesso Expirado</h2>
<p>Token inválido, expirado ou já usado.</p>
<p>Entre em contato pelo WhatsApp para suporte.</p>
</body></html>
        """), 403

@app.route('/')
def home():
    return "🚀 API de Proteção Scalper 72x9 Online"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)