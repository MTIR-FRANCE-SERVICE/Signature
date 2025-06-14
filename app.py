from flask import Flask, request, render_template, jsonify, redirect, url_for, send_file, abort
from flask_cors import CORS
import os
import requests
from datetime import datetime
import base64
from io import BytesIO
import json
import hashlib
import time
import urllib.parse
from PyPDF2 import PdfFileReader, PdfFileWriter
# Version simplifiée sans reportlab

app = Flask(__name__)
CORS(app)  # Active CORS pour toutes les routes
app.secret_key = 'b29fa6845a0f3190e69382d255e8567c'  # Clé forte pour signer les URLs

# Stockage temporaire des tokens par IP client
client_redirects = {}

# Fonction pour créer une signature de données client
def sign_data(data):
    data_str = json.dumps(data, sort_keys=True)
    signature = hashlib.sha256((data_str + app.secret_key).encode()).hexdigest()
    return signature[:12]  # Version courte pour l'URL

# Dossier de stockage temporaire pour les PDF signés
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/', methods=['GET'])
def index():
    # Récupérer l'adresse IP du client
    client_ip = request.remote_addr
    print(f"Accès à la page d'accueil depuis IP: {client_ip}")
    
    # Vérifier si cette IP a un token de redirection en attente
    if client_ip in client_redirects:
        token = client_redirects[client_ip]
        print(f"Redirection trouvée pour IP {client_ip} vers token: {token}")
        
        # Supprimer le token de la liste après utilisation
        del client_redirects[client_ip]
        
        # Rediriger vers la page de signature
        return redirect(url_for('signature_page', token=token))
    
    # Par défaut, afficher la page d'attente
    print(f"Aucune redirection trouvée pour IP {client_ip}, affichage de l'attente")
    return render_template('attente.html')

@app.route('/signature/<token>', methods=['GET'])
def signature_page(token):
    # Vérifier si le token existe dans le répertoire de stockage
    info_path = os.path.join(UPLOAD_FOLDER, f"{token}.json")
    
    if not os.path.exists(info_path):
        print(f"Token invalide ou expiré: {token}")
        return render_template('attente.html', error="Lien invalide ou expiré")
    
    # Lire le fichier de données client
    with open(info_path, 'r') as f:
        data = json.load(f)
    
    client_data = data.get('client_data')
    pdf_path = data.get('pdf_path')
    
    if not client_data or not pdf_path or not os.path.exists(pdf_path):
        print(f"Données corrompues pour le token: {token}")
        return render_template('attente.html', error="Données introuvables")
    
    print(f"Données client trouvées pour token {token}: {client_data['prenom']} {client_data['nom']}")
    print(f"PDF path: {pdf_path}, Existe: {os.path.exists(pdf_path)}")
    
    # Stocker le token pour les routes suivantes
    return render_template('index.html', client=client_data, pdf_path=pdf_path, token=token)

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    # Récupérer les données du webhook
    data = request.json
    print(f"Données reçues: {data}")  # Log les données reçues
    
    # Rendre le champ téléphone optionnel
    required_fields = ['prenom', 'nom', 'email']
    if not all(key in data for key in required_fields):
        missing = [f for f in required_fields if f not in data]
        print(f"Champs manquants: {missing}")  # Log les champs manquants
        return jsonify({'status': 'error', 'message': 'Données incomplètes: ' + ', '.join(missing)})
    
    # Ajouter un numéro de téléphone par défaut s'il est manquant
    if 'telephone' not in data:
        data['telephone'] = 'Non spécifié'
    
    # Vérifier si un lien PDF est fourni dans les données
    pdf_url = data.get('pdf_url')
    if not pdf_url:
        # Utiliser l'URL par défaut si aucune n'est fournie
        pdf_url = "https://docs.google.com/spreadsheets/d/1PDQD2OPBlrVJ26qrfEXJGrviyRnVM_v41vSxhMzGm0Y/export?format=pdf&gid=23261508"
        print(f"Aucun lien PDF fourni, utilisation de l'URL par défaut")
    
    print(f"Téléchargement du PDF depuis: {pdf_url}")
    
    try:
        response = requests.get(pdf_url)
        
        if response.status_code != 200:
            print(f"Échec du téléchargement: status {response.status_code}")
            return jsonify({'status': 'error', 'message': f'Échec du téléchargement du PDF (code: {response.status_code})'})
        
        # Sauvegarder temporairement le PDF
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        pdf_filename = f"{timestamp}_{data['prenom']}_{data['nom']}.pdf"
        pdf_path = os.path.join(UPLOAD_FOLDER, pdf_filename)
        
        with open(pdf_path, 'wb') as f:
            f.write(response.content)
        
        print(f"PDF sauvegardé: {pdf_path}")
        
        # Générer un token unique basé sur les données client et l'horodatage
        client_data = {
            'prenom': data['prenom'],
            'nom': data['nom'],
            'email': data['email'],
            'telephone': data['telephone']
        }
        
        # Créer une signature basée sur les données et un timestamp
        token_base = f"{timestamp}_{data['prenom']}_{data['nom']}"
        token = sign_data(token_base)
        
        # Stocker les informations dans un fichier JSON pour une récupération ultérieure
        info = {
            'client_data': client_data,
            'pdf_path': pdf_path,
            'timestamp': timestamp,
            'token': token
        }
        
        # Enregistrer les informations dans un fichier JSON
        token_path = os.path.join(UPLOAD_FOLDER, f"{token}.json")
        with open(token_path, 'w') as f:
            json.dump(info, f)
        
        print(f"Token créé: {token} pour {data['prenom']} {data['nom']}")
        
        # Récupérer l'adresse IP du client
        client_ip = request.remote_addr
        
        # Stocker le token pour redirection ultérieure
        client_redirects[client_ip] = token
        
        print(f"Token {token} associé à l'IP {client_ip} pour redirection future")
        
        # Retourner l'URL racine comme avant pour compatibilité
        return jsonify({
            'status': 'success', 
            'redirect': url_for('index', _external=True),
            'message': 'Données reçues avec succès, veuillez consulter l\'interface utilisateur'
        })
    
    except Exception as e:
        print(f"Erreur: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Erreur lors du traitement: {str(e)}'})

@app.route('/view-pdf/<token>')
def view_pdf(token):
    """Route pour afficher le PDF dans l'iframe"""
    # Vérifier si le token existe
    info_path = os.path.join(UPLOAD_FOLDER, f"{token}.json")
    
    if not os.path.exists(info_path):
        return "Token invalide ou expiré", 404
    
    # Lire le fichier de données client
    with open(info_path, 'r') as f:
        data = json.load(f)
    
    pdf_path = data.get('pdf_path')
    
    if not pdf_path or not os.path.exists(pdf_path):
        return "PDF non disponible", 404
    
    return send_file(pdf_path, mimetype='application/pdf')

@app.route('/sign/<token>', methods=['POST'])
def sign_pdf(token):
    # Vérifier si le token existe
    info_path = os.path.join(UPLOAD_FOLDER, f"{token}.json")
    
    if not os.path.exists(info_path):
        return jsonify({'status': 'error', 'message': 'Token invalide ou expiré'})
    
    # Lire le fichier de données client
    with open(info_path, 'r') as f:
        info = json.load(f)
    
    # Récupérer les données
    signature_data = request.json.get('signature')
    client_data = info.get('client_data')
    pdf_path = info.get('pdf_path')
    
    if not signature_data or not client_data or not pdf_path or not os.path.exists(pdf_path):
        return jsonify({'status': 'error', 'message': 'Données manquantes ou invalides'})
    
    try:
        # Version simplifiée: sauvegarder uniquement la signature
        signature_data = signature_data.split(',')[1]
        
        # Créer un fichier pour la signature
        signature_path = os.path.join(UPLOAD_FOLDER, f"signature_{token}.png")
        
        # Écrire les données base64 décodées dans le fichier
        with open(signature_path, 'wb') as f:
            f.write(base64.b64decode(signature_data))
        
        # Copier le PDF original comme document final
        # Dans une version complète, on fusionnerait la signature dans le PDF
        output_pdf = os.path.join(UPLOAD_FOLDER, f"contrat-{token}.pdf")
        with open(pdf_path, 'rb') as src_pdf:
            with open(output_pdf, 'wb') as dest_pdf:
                dest_pdf.write(src_pdf.read())
        
        # Mettre à jour le fichier d'informations
        info['signed'] = True
        info['signature_path'] = signature_path
        info['signed_pdf_path'] = output_pdf
        info['signed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Sauvegarder les informations mises à jour
        with open(info_path, 'w') as f:
            json.dump(info, f)
            
        print(f"Signature enregistrée pour token {token}: {client_data['prenom']} {client_data['nom']}")
        
        return jsonify({
            'status': 'success',
            'client': f"{client_data['prenom']} {client_data['nom']}",
            'message': 'Signature enregistrée avec succès',
            'token': token
        })
    
    except Exception as e:
        print(f"Erreur lors de la signature: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

# La fonction add_signature_to_pdf a été supprimée car elle nécessitait reportlab
# Elle est remplacée par une simple copie de fichier dans la fonction sign_pdf

if __name__ == '__main__':
    # Utiliser le port défini par l'environnement pour Render
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
