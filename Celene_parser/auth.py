import os
import json
import time
from datetime import datetime
from typing import Optional, List, Tuple, Dict
from urllib.parse import urlparse, urljoin
from http.cookiejar import Cookie
import base64

import requests
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from .utils import logger, CAS_SERVICE_ENUM


class SecureStorage:
    """Classe stockant les informations de session de manière sécurisée"""
    
    def __init__(self, secure_storage_status: bool, 
                 secure_storage_key: Optional[str] = None,
                 secure_storage_iv: Optional[str] = None,
                 storage_dir: Optional[str] = None):
        self._data: Dict[str, str] = {}
        self._secure_storage_key = secure_storage_key
        self._secure_storage_iv = secure_storage_iv
        self._secure_storage_status = secure_storage_status
        self._secure_storage_read_status = False
        
        # Utiliser storage_dir si fourni, sinon utiliser le répertoire courant
        if storage_dir:
            self.SECURE_STORAGE_PATH = os.path.join(storage_dir, ".celene_session", "secStorage.key")
        else:
            self.SECURE_STORAGE_PATH = os.path.join(os.getcwd(), ".celene_session", "secStorage.key")
        
        self._fernet: Optional[Fernet] = None
        
        if self._secure_storage_status:
            self._secure_storage_read_status = self.load_secure_storage()
    
    def _get_fernet(self) -> Fernet:
        """Crée ou retourne l'objet Fernet pour le chiffrement"""
        if self._fernet is None:
            if not self._secure_storage_key:
                raise Exception("Secure storage key is not set")
            
            # Utiliser PBKDF2 pour dériver une clé de 32 bytes
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self._secure_storage_iv.encode() if self._secure_storage_iv else b'default_salt',
                iterations=100000,
                backend=default_backend()
            )
            key = base64.urlsafe_b64encode(kdf.derive(self._secure_storage_key.encode()))
            self._fernet = Fernet(key)
        
        return self._fernet
    
    def load_secure_storage(self) -> bool:
        """Charge et déchiffre le SecureStorage"""
        debug_header = "[SecureStorage - loadSecureStorage]"
        logger(f"{debug_header} - SecureStorage was set")
        
        if not self._secure_storage_key or not self._secure_storage_iv:
            raise Exception("Secure storage was marked as set but no marks of it on the host system")
        
        storage_file = self.SECURE_STORAGE_PATH
        
        if not os.path.exists(storage_file):
            logger(f"{debug_header} - key file does not exist, creating it")
            os.makedirs(os.path.dirname(storage_file), exist_ok=True)
            with open(storage_file, 'w') as f:
                f.write('')
            self._data = {}
            return True
        
        try:
            with open(storage_file, 'rb') as f:
                encrypted_content = f.read()
            
            if not encrypted_content:
                self._secure_storage_read_status = True
                return True
            
            # Déchiffrer les données
            fernet = self._get_fernet()
            decrypted_data = fernet.decrypt(encrypted_content)
            data_str = decrypted_data.decode('utf-8')
            res = json.loads(data_str)
            
            self._secure_storage_read_status = True
            self._data = res
            logger(f"{debug_header} - Data resembles to this {self._data}")
            return True
            
        except Exception as e:
            logger(f"{debug_header} - Error loading secure storage: {e}")
            return False
    
    def dump(self) -> bool:
        """Chiffre le SecureStorage et écrit le fichier sur le disque"""
        debug_header = "[SecureStorage - Dump]"
        
        if not self._secure_storage_read_status:
            logger(f"{debug_header} - FALSE RETURN: SecureStorage wasn't correctly initialized")
            return False
        
        if not all([self._secure_storage_iv, self._secure_storage_key]):
            logger(f"{debug_header} - FALSE RETURN: Missing encryption parameters")
            return False
        
        try:
            # Chiffrer les données
            fernet = self._get_fernet()
            data_str = json.dumps(self._data)
            encrypted = fernet.encrypt(data_str.encode('utf-8'))
            
            # Écrire sur le disque
            os.makedirs(os.path.dirname(self.SECURE_STORAGE_PATH), exist_ok=True)
            with open(self.SECURE_STORAGE_PATH, 'wb') as f:
                f.write(encrypted)
            
            logger(f"{debug_header} - Data saved successfully")
            return True
            
        except Exception as e:
            logger(f"{debug_header} - Error dumping: {e}")
            return False
    
    def get_secure_storage_status(self) -> bool:
        """Vérifie si le SecureStorage est correctement initialisé"""
        return self._secure_storage_read_status
    
    def get_value(self, key: str) -> Optional[str]:
        """Obtient la valeur d'une clé"""
        if self._secure_storage_read_status and self._secure_storage_status:
            return self._data.get(key)
        else:
            raise Exception("SecureStorage function called when no secure storage was set")
    
    def set_value(self, key: str, value: str):
        """Définit une valeur pour une clé"""
        if self._secure_storage_read_status and self._secure_storage_status:
            logger(f"[SecureStorage] - setValue: setting key {key} to value {value}")
            self._data[key] = value
        else:
            raise Exception("SecureStorage function called when no secure storage was set")
    
    def clear_secure_storage(self) -> int:
        """Efface le SecureStorage"""
        if os.path.exists(self.SECURE_STORAGE_PATH):
            os.remove(self.SECURE_STORAGE_PATH)
        
        self._secure_storage_read_status = False
        self._secure_storage_status = False
        self._secure_storage_key = None
        self._secure_storage_iv = None
        self._fernet = None
        return 0


class CASAuth:
    """Classe permettant la connexion au CAS de l'INSA CVL"""
    
    SERVICE_PARAM = "?service="
    
    def __init__(self):
        self.cas_endpoint = "https://cas.insa-cvl.fr/cas/login"
        self.session = requests.Session()
        self.session_date: Optional[datetime] = None
        self._session_status = False
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Encoding': 'gzip, deflate, br'
        }
        
        self.secure_storage: Optional[SecureStorage] = None
    
    def set_secure_storage(self, storage: SecureStorage):
        """Initialise le secure storage"""
        self.secure_storage = storage
        logger("SecureStorage set for CASAuth")
    
    def login_to_cas(self, login: str, password: str, service: str) -> int:
        """
        Connexion au CAS
        
        Args:
            login: Login de l'utilisateur
            password: Mot de passe
            service: Service cible (ex: "Celene")
            
        Returns:
            1 si succès, -1 si erreur
        """
        start_date = datetime.now()
        
        if service not in CAS_SERVICE_ENUM:
            logger("Service passed in parameters isn't supported or doesn't exist")
            return -1
        
        cas_service_endpoint = self.cas_endpoint + self.SERVICE_PARAM + CAS_SERVICE_ENUM[service]
        
        try:
            # Récupérer la page de login
            logger(f"Fetching CAS login page: {cas_service_endpoint}")
            login_page = self.session.get(cas_service_endpoint, headers=self.headers)
            
            if login_page.status_code != 200:
                logger("Failed to receive CAS Login page")
                return -1
            
            # Parser pour extraire les champs du formulaire
            soup = BeautifulSoup(login_page.text, 'html.parser')
            exec_field = soup.find('input', {'name': 'execution'})
            event_id_field = soup.find('input', {'name': '_eventId'})
            
            if not exec_field or not event_id_field:
                logger("Failed finding required form fields")
                return -1
            
            execution = exec_field.get('value')
            event_id = event_id_field.get('value')
            
            logger(f"Form fields: execution={execution}, eventId={event_id}")
            
            # Préparer les données de login
            login_data = {
                'username': login,
                'password': password,
                'execution': execution,
                '_eventId': event_id,
                'submit': 'SE CONNECTER'
            }
            
            # Soumettre le formulaire
            logger("Submitting login form...")
            response = self.session.post(
                cas_service_endpoint,
                headers=self.headers,
                data=login_data,
                allow_redirects=False
            )
            
            logger(f"Login response status: {response.status_code}")
            
            # Gérer les redirections
            if response.status_code in [301, 302, 303]:
                final_response = self._follow_redirects(response)
                logger("Redirected")
                
                if final_response.status_code == 200:
                    self._session_status = True
                    logger("Connection successful")
                    logger(f"Delta: {(datetime.now() - start_date).total_seconds()} seconds")
                    logger(f"Cookies: {[cookie.name for cookie in self.session.cookies]}")
                    return 1
            else:
                logger("Not redirected")
                return -1
                
        except Exception as e:
            logger(f"Exception during CAS login: {e}")
            return -1
        
        return -1
    
    def _follow_redirects(self, response: requests.Response) -> requests.Response:
        """Gère les redirections"""
        redirect_count = 0
        
        while response.status_code in [302, 303] and redirect_count < 10:
            location = response.headers.get('location')
            
            if not location:
                break
            
            if location.startswith('http'):
                new_url = location
            else:
                new_url = urljoin(response.url, location)
            
            logger(f"Following redirect to: {new_url}")
            response = self.session.get(new_url, headers=self.headers, allow_redirects=False)
            redirect_count += 1
            time.sleep(0.01)
        
        if redirect_count >= 10:
            raise Exception("Trop de redirections (boucle probable)")
        
        if response.status_code == 200:
            logger("Successfully connected!")
        
        return response
    
    def load_cas_session(self, keys_to_get: List[Tuple[str, str, str]]) -> bool:
        """
        Charge la session CAS
        
        Args:
            keys_to_get: Liste de (storage_key, cookie_name, url)
        """
        debug_header = "[CASAuth - loadCasSession]"
        
        if not self.secure_storage:
            logger(f"{debug_header} - Secure storage wasn't set")
            return False
        
        if not self.secure_storage.get_secure_storage_status():
            logger(f"{debug_header} - Secure storage exists but hasn't loaded correctly")
            return False
        
        # Vérifier la date de session
        string_session_date = self.secure_storage.get_value("sessionDate")
        
        if not string_session_date:
            logger(f"{debug_header} - Session date value was non-existent")
            return False
        
        try:
            session_date = datetime.strptime(string_session_date, "%d/%m/%Y-%H:%M")
            
            minutes_diff = (datetime.now() - session_date).total_seconds() / 60
            logger(f"{debug_header} - Session age: {minutes_diff:.1f} minutes")
            
            if minutes_diff > 30:
                logger(f"{debug_header} - Session date was too old")
                return False
        except ValueError as e:
            logger(f"{debug_header} - Error parsing session date: {e}")
            return False
        
        # Ajouter le cookie CAS principal
        keys_to_get_copy = keys_to_get.copy()
        keys_to_get_copy.append(("casCookie", "TGC", "https://cas.insa-cvl.fr/"))
        
        # Charger tous les cookies
        for storage_key, cookie_name, url in keys_to_get_copy:
            value = self.secure_storage.get_value(storage_key)
            
            if not value:
                logger(f"{debug_header} - Cookie '{storage_key}' didn't exist in storage")
                return False
            
            parsed_url = urlparse(url)
            
            cookie = Cookie(
                version=0,
                name=cookie_name,
                value=value,
                port=None,
                port_specified=False,
                domain=parsed_url.hostname or '',
                domain_specified=True,
                domain_initial_dot=False,
                path=parsed_url.path or '/',
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False
            )
            
            self.session.cookies.set_cookie(cookie)
            logger(f"{debug_header} - Loaded cookie: {cookie_name}")
        
        self._session_status = True
        logger(f"{debug_header} - Session loaded successfully")
        return True
    
    def save_cas_session(self, cookies_to_save: List[Tuple[str, str]]) -> bool:
        """
        Sauvegarde la session CAS
        
        Args:
            cookies_to_save: Liste de (cookie_name, storage_key)
        """
        debug_header = "[CASAuth - saveCasSession]"
        
        cookies_to_save_copy = cookies_to_save.copy()
        cookies_to_save_copy.append(("TGC", "casCookie"))
        
        if not self.session_date or not self.secure_storage:
            logger(f"{debug_header} - Either session date was null or secure storage wasn't set")
            return False
        
        if not self._session_status:
            logger(f"{debug_header} - Session wasn't initiated correctly")
            return False
        
        minutes_diff = (datetime.now() - self.session_date).total_seconds() / 60
        if minutes_diff > 30:
            logger(f"{debug_header} - Session was too old ({minutes_diff:.1f} minutes)")
            return False
        
        if not self.secure_storage.get_secure_storage_status():
            logger(f"{debug_header} - Secure storage wasn't set properly")
            return False
        
        # Sauvegarder la date
        self.secure_storage.set_value(
            "sessionDate",
            self.session_date.strftime("%d/%m/%Y-%H:%M")
        )
        
        # Sauvegarder chaque cookie
        for cookie_name, storage_key in cookies_to_save_copy:
            cookie_value = None
            
            for cookie in self.session.cookies:
                if cookie.name == cookie_name:
                    cookie_value = cookie.value
                    break
            
            if not cookie_value:
                logger(f"{debug_header} - Cookie '{cookie_name}' wasn't found in session")
                return False
            
            self.secure_storage.set_value(storage_key, cookie_value)
            logger(f"{debug_header} - Saved cookie: {cookie_name}")
        
        return self.secure_storage.dump()
