import json
import secrets
import os
import time
from google.cloud import firestore
from google.oauth2 import service_account
from web3 import Web3
from web3._utils.events import get_event_data



# === Configuration ===
JSON_FILE_PATH = "/etc/secrets/tranquil-lore-396810-a584b05b6b14.json"
HTTP_URL = os.getenv('HTTP_URL')
CONTRACT_ADDRESS = "0xcbD7cDEBC30E2673925304199b4c7545dafA425E"
POLLING_INTERVAL = 10

CONTRACT_ABI = [
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "NumberOfMonths",
				"type": "uint256"
			}
		],
		"name": "payForAccess",
		"outputs": [],
		"stateMutability": "payable",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "_price",
				"type": "uint256"
			}
		],
		"stateMutability": "nonpayable",
		"type": "constructor"
	},
	{
		"anonymous": False,
		"inputs": [
			{
				"indexed": True,
				"internalType": "address",
				"name": "user",
				"type": "address"
			},
			{
				"indexed": False,
				"internalType": "uint256",
				"name": "amount",
				"type": "uint256"
			},
			{
				"indexed": False,
				"internalType": "uint256",
				"name": "newExpirationDate",
				"type": "uint256"
			}
		],
		"name": "PaymentReceived",
		"type": "event"
	},
	{
		"anonymous": False,
		"inputs": [
			{
				"indexed": False,
				"internalType": "uint256",
				"name": "newPrice",
				"type": "uint256"
			}
		],
		"name": "PriceUpdated",
		"type": "event"
	},
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "_newPrice",
				"type": "uint256"
			}
		],
		"name": "updatePrice",
		"outputs": [],
		"stateMutability": "nonpayable",
		"type": "function"
	},
	{
		"inputs": [],
		"name": "withdraw",
		"outputs": [],
		"stateMutability": "nonpayable",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "address",
				"name": "",
				"type": "address"
			}
		],
		"name": "expirationDates",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "address",
				"name": "user",
				"type": "address"
			}
		],
		"name": "hasActiveAccess",
		"outputs": [
			{
				"internalType": "bool",
				"name": "",
				"type": "bool"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [],
		"name": "owner",
		"outputs": [
			{
				"internalType": "address",
				"name": "",
				"type": "address"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [],
		"name": "price",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			}
		],
		"stateMutability": "view",
		"type": "function"
	}
]


# === Fonctions utilitaires ===
def load_credentials_from_file(json_file_path):
    with open(json_file_path) as json_file:
        credentials_info = json.load(json_file)
    return service_account.Credentials.from_service_account_info(credentials_info)


def get_firestore_client(credentials):
    return firestore.Client(credentials=credentials)


def add_api_key(db, address, expiration_date):
    try:
        collection_ref = db.collection('collection api')
        existing_doc = collection_ref.where('address', '==', address).get()

        if existing_doc:
            for doc in existing_doc:
                doc.reference.update({
                    'api_key': secrets.token_hex(32),
                    'expiry_date': expiration_date
                })
            print(f"Document mis à jour avec succès pour l'adresse {address}")
        else:
            collection_ref.add({
                'address': address,
                'api_key': secrets.token_hex(32),
                'expiry_date': expiration_date
            })
            print(f"Document ajouté avec succès pour l'adresse {address}")

    except Exception as e:
        print(f"Erreur lors de l'ajout ou de la mise à jour du document : {e}")


def listen_for_payments(web3, db, contract, payment_event):
    last_checked_block = web3.eth.block_number
    print("Écoute des paiements en cours...")

    while True:
        try:
            current_block = web3.eth.block_number
            if current_block > last_checked_block:
                logs = web3.eth.get_logs({
                    "fromBlock": last_checked_block + 1,
                    "toBlock": current_block,
                    "address": CONTRACT_ADDRESS,
                })

                for log in logs:
                    try:
                        decoded_event = get_event_data(
                            web3.codec,
                            payment_event._get_event_abi(),
                            log
                        )
                        user_address = decoded_event['args']['user']
                        amount = decoded_event['args']['amount']
                        expiration_date = decoded_event['args']['newExpirationDate']
                        print(f"Paiement reçu de {user_address} pour {amount}, expiration : {expiration_date}")
                        add_api_key(db, user_address.lower(), expiration_date)
                    except Exception as e:
                        print(f"Erreur lors du décodage de l'événement : {e}")

                last_checked_block = current_block

            time.sleep(POLLING_INTERVAL)

        except Exception as e:
            print(f"Erreur dans la boucle principale : {e}")
            time.sleep(5)  # Attente avant de réessayer en cas d'erreur


# === Fonction principale ===
def main():
    # Initialisation des clients et connexion
    credentials = load_credentials_from_file(JSON_FILE_PATH)
    db = get_firestore_client(credentials)
    web3 = Web3(Web3.HTTPProvider(HTTP_URL))

    if not web3.is_connected():
        print("Impossible de se connecter au réseau.")
        return

    print("Connexion réussie à Polygon.")
    contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    payment_event = contract.events.PaymentReceived

    # Écoute des paiements
    listen_for_payments(web3, db, contract, payment_event)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Arrêt de l'application.")
