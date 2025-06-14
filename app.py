from flask import Flask, request, render_template, jsonify, session, redirect, url_for, send_file
from flask_cors import CORS
import os
import requests
from datetime import datetime
import base64
from io import BytesIO
from PyPDF2 import PdfFileReader, PdfFileWriter
# Version simplifiée sans reportlab

app = Flask(__name__)
CORS(app)  # Active CORS pour toutes les routes
app.secret_key = 'votre_clef_secrete_aleatoire'  # Nécessaire pour les sessions

# Dossier de stockage temporaire pour les PDF signés
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/', methods=['GET'])
def index():
    # Si aucune donnée en session, retourner un message d'attente
    if not session.get('client_data'):
        return render_template('attente.html')
    
    # Récupérer les données client stockées en session
    client_data = session.get('client_data')
    pdf_path = session.get('pdf_path')
    
    return render_template('index.html', client=client_data, pdf_path=pdf_path)

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    # Récupérer les données du webhook
    data = request.json
    
    # Vérifier que toutes les données nécessaires sont présentes
    if not all(key in data for key in ['prenom', 'nom', 'email', 'telephone']):
        return jsonify({'status': 'error', 'message': 'Données incomplètes'})
    
    # Télécharger le PDF
    pdf_url = "https://docs.google.com/spreadsheets/d/1PDQD2OPBlrVJ26qrfEXJGrviyRnVM_v41vSxhMzGm0Y/export?format=pdf&gid=23261508"
    response = requests.get(pdf_url)
    
    if response.status_code != 200:
        return jsonify({'status': 'error', 'message': 'Échec du téléchargement du PDF'})
    
    # Sauvegarder temporairement le PDF
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    pdf_filename = f"{timestamp}_{data['prenom']}_{data['nom']}.pdf"
    pdf_path = os.path.join(UPLOAD_FOLDER, pdf_filename)
    
    with open(pdf_path, 'wb') as f:
        f.write(response.content)
    
    # Stocker les données dans la session
    session['client_data'] = data
    session['pdf_path'] = pdf_path
    
    # Retourner une URL à rediriger pour l'interface utilisateur
    return jsonify({
        'status': 'success', 
        'redirect': url_for('index'), 
        'message': 'Données reçues, veuillez consulter l\'interface utilisateur'
    })

@app.route('/view-pdf')
def view_pdf():
    """Route pour afficher le PDF dans l'iframe"""
    pdf_path = session.get('pdf_path')
    if not pdf_path or not os.path.exists(pdf_path):
        return "PDF non disponible", 404
    
    from flask import send_file
    return send_file(pdf_path, mimetype='application/pdf')

@app.route('/sign', methods=['POST'])
def sign_pdf():
    # Récupérer les données
    signature_data = request.json.get('signature')
    client_data = session.get('client_data')
    pdf_path = session.get('pdf_path')
    
    if not signature_data or not client_data or not pdf_path:
        return jsonify({'status': 'error', 'message': 'Données manquantes'})
    
    try:
        # Version simplifiée: sauvegarder uniquement la signature
        signature_data = signature_data.split(',')[1]
        
        # Créer un fichier pour la signature
        signature_path = os.path.join(UPLOAD_FOLDER, f"signature_{client_data['prenom']}_{client_data['nom']}.png")
        
        # Écrire les données base64 décodées dans le fichier
        with open(signature_path, 'wb') as f:
            f.write(base64.b64decode(signature_data))
        
        # Copier le PDF original comme document final
        # Dans une version complète, on fusionnerait la signature dans le PDF
        output_pdf = os.path.join(UPLOAD_FOLDER, f"contrat-{client_data['prenom']}-{client_data['nom']}.pdf")
        with open(pdf_path, 'rb') as src_pdf:
            with open(output_pdf, 'wb') as dest_pdf:
                dest_pdf.write(src_pdf.read())
        
        # Nettoyer la session
        session.pop('client_data', None)
        session.pop('pdf_path', None)
        
        return jsonify({
            'status': 'ok',
            'client': f"{client_data['prenom']} {client_data['nom']}",
            'message': 'Signature enregistrée avec succès',
            'signature_path': signature_path,
            'pdf_path': output_pdf
        })
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# La fonction add_signature_to_pdf a été supprimée car elle nécessitait reportlab
# Elle est remplacée par une simple copie de fichier dans la fonction sign_pdf

if __name__ == '__main__':
    # Utiliser le port défini par l'environnement pour Render
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
