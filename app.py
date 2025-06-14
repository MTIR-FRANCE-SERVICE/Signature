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
    signature_positions = data.get('signature_positions', [])
    
    if not client_data or not pdf_path or not os.path.exists(pdf_path):
        print(f"Données corrompues pour le token: {token}")
        return render_template('attente.html', error="Données introuvables")
    
    print(f"Données client trouvées pour token {token}: {client_data['prenom']} {client_data['nom']}")
    print(f"PDF path: {pdf_path}, Existe: {os.path.exists(pdf_path)}")
    print(f"Nombre de positions de signature: {len(signature_positions)}")
    
    # Transmettre toutes les données au template
    return render_template('index.html', 
                           client=client_data, 
                           pdf_path=pdf_path, 
                           token=token,
                           signature_positions=json.dumps(signature_positions))

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
        
        # Créer le fichier JSON avec les infos de session
        # Créer un token unique pour cette session
        token_base = f"{timestamp}_{data['prenom']}_{data['nom']}"
        token = sign_data(token_base)
        
        # Préparer les données à stocker
        token_data = {
            'client_data': {
                'prenom': data['prenom'],
                'nom': data['nom'],
                'email': data['email'],
                'telephone': data.get('telephone', 'Non spécifié')
            },
            'pdf_path': pdf_path,
            'timestamp': timestamp,
            'token': token,
            'date_creation': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Vérifier si des positions de signature sont fournies
        if 'signature_positions' in data:
            token_data['signature_positions'] = data['signature_positions']
            print(f"Positions de signature reçues: {len(data['signature_positions'])}")
        else:
            print("Aucune position de signature spécifiée")
            token_data['signature_positions'] = []
        
        # Enregistrer les informations dans un fichier JSON
        info = token_data
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
    # Vérifier que le token est valide
    token_file = os.path.join(UPLOAD_FOLDER, f"{token}.json")
    if not os.path.exists(token_file):
        return jsonify({'status': 'error', 'message': 'Session de signature invalide ou expirée'})
    
    # Charger les données de la session
    with open(token_file, 'r') as f:
        token_data = json.load(f)
    
    # Récupérer les données JSON envoyées
    data = request.json
    
    # Extraire les informations client et PDF
    client_data = token_data.get('client_data')
    pdf_path = token_data.get('pdf_path')
    
    if not client_data or not pdf_path or not os.path.exists(pdf_path):
        return jsonify({'status': 'error', 'message': 'Données de session incohérentes'})
    
    try:
        # Déterminer le mode (signature unique ou multiple)
        signatures_directory = os.path.join(UPLOAD_FOLDER, f"signatures_{token}")
        os.makedirs(signatures_directory, exist_ok=True)
        
        # Vérifier si nous avons plusieurs signatures ou une seule
        if 'signatures' in data and isinstance(data['signatures'], list):
            print(f"Reçu {len(data['signatures'])} signatures")
            # Mode multi-signature avec positions
            signature_files = []
            
            for i, sig_data in enumerate(data['signatures']):
                # Vérifier les données de signature
                signature_image = sig_data.get('image')
                if not signature_image:
                    continue
                
                # Position de la signature
                position = sig_data.get('position', {})
                
                # Décoder et sauvegarder l'image
                signature_image = signature_image.replace('data:image/png;base64,', '')
                signature_image = signature_image.replace('data:image/jpeg;base64,', '')
                
                # Chemin d'image unique pour cette signature
                sig_path = os.path.join(signatures_directory, f"signature_{i}.png")
                
                with open(sig_path, 'wb') as f:
                    f.write(base64.b64decode(signature_image))
                
                # Stocker le chemin et la position
                signature_files.append({
                    'path': sig_path,
                    'position': position,
                    'index': sig_data.get('index', i)
                })
            
            # Aucune signature valide
            if not signature_files:
                return jsonify({'status': 'error', 'message': 'Aucune signature valide fournie'})
                
        else:
            # Mode signature unique (ancienne version)
            signature_data = data.get('signature')
            
            if not signature_data:
                return jsonify({'status': 'error', 'message': 'Aucune signature fournie'})
            
            # Créer une seule image de signature
            signature_image_path = os.path.join(UPLOAD_FOLDER, f"signature_{token}.png")
            
            # Décoder et enregistrer la signature
            signature_data = signature_data.replace('data:image/png;base64,', '')
            signature_data = signature_data.replace('data:image/jpeg;base64,', '')
            
            with open(signature_image_path, 'wb') as f:
                f.write(base64.b64decode(signature_data))
            
            signature_files = [{'path': signature_image_path, 'position': None, 'index': 0}]
        
        # Copier le PDF pour la version signée (pour l'instant, juste une copie)
        signed_pdf_path = os.path.join(UPLOAD_FOLDER, f"contrat-{token}.pdf")
        
        # Copier le fichier original (sans modification pour l'instant)
        with open(pdf_path, 'rb') as src, open(signed_pdf_path, 'wb') as dst:
            dst.write(src.read())
        
        # Mettre à jour les données de signature dans le fichier JSON
        token_data['signature_files'] = [s['path'] for s in signature_files]
        token_data['signature_positions'] = [s['position'] for s in signature_files]
        token_data['signed_pdf'] = signed_pdf_path
        token_data['date_signature'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Enregistrer les données mises à jour
        with open(token_file, 'w') as f:
            json.dump(token_data, f)
        
        return jsonify({'status': 'success', 'message': 'Signature(s) enregistrée(s) avec succès'})
    
    except Exception as e:
        print(f"Erreur lors du traitement de la signature: {str(e)}")
        return jsonify({'status': 'error', 'message': f"Une erreur s'est produite: {str(e)}"})


# La fonction add_signature_to_pdf a été supprimée car elle nécessitait reportlab
# Elle est remplacée par une simple copie de fichier dans la fonction sign_pdf

if __name__ == '__main__':
    # Utiliser le port défini par l'environnement pour Render
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
