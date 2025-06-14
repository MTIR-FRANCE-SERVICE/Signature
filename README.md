# Application de Signature de Documents

Une application web simple qui permet de recevoir des données client via un webhook, afficher un PDF et permettre sa signature manuscrite.

## Fonctionnalités

- Réception des données client via un webhook (prénom, nom, email, téléphone)
- Téléchargement automatique du PDF à signer
- Interface utilisateur adaptée aux tablettes
- Signature manuscrite directe sur l'écran
- Sauvegarde du document signé

## Installation

1. Installer les dépendances :
```
pip install -r requirements.txt
```

2. Lancer l'application :
```
python app.py
```

## Utilisation

1. L'application démarre sur le port 5000 par défaut.
2. Pour envoyer des données client, utilisez un webhook avec une requête POST vers `/webhook` avec le format JSON suivant :
```json
{
  "prenom": "Jean",
  "nom": "Dupont",
  "email": "jean.dupont@example.com",
  "telephone": "0123456789"
}
```

3. Une fois les données reçues, ouvrez l'application dans un navigateur à l'adresse `http://votre-serveur:5000` pour voir l'interface de signature.

## Exemple de requête webhook

```bash
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{"prenom":"Jean","nom":"Dupont","email":"jean.dupont@example.com","telephone":"0123456789"}'
```

## Notes

- L'application stocke les fichiers signés dans le dossier `/uploads`
- Pour une utilisation en production, ajoutez la configuration d'authentification et de Google Drive pour l'envoi des fichiers
