from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
import os
import json
import time
import subprocess
import platform as sys_platform
from http.cookiejar import Cookie
import webbrowser
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64


# Configuration
BASEDIR = os.path.join(os.path.expanduser("~"), "celeneCLI/")
WIN_BASEDIR = os.path.join(os.path.expanduser("~"), "celeneCLI\\") if sys_platform.system() == "Windows" else ""
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'


def logger(content: Any):
    """Logger function - only prints if DEBUG is True"""
    if DEBUG:
        print(str(content))


# Service endpoints pour CAS
CAS_SERVICE_ENUM = {
    "Celene": "https%3A%2F%2Fcelene.insa-cvl.fr%2Flogin%2Findex.php"
}


class SecureStorage:
    """Classe stockant les informations de session de manière sécurisée"""
    
    def __init__(self, secure_storage_status: bool, 
                 secure_storage_key: Optional[str] = None,
                 secure_storage_iv: Optional[str] = None):
        self._data: Dict[str, str] = {}
        self._secure_storage_key = secure_storage_key
        self._secure_storage_iv = secure_storage_iv
        self._secure_storage_status = secure_storage_status
        self._secure_storage_read_status = False
        self.SECURE_STORAGE_PATH = os.path.join(BASEDIR, "secStorage.key")
        self._fernet: Optional[Fernet] = None
        
        if self._secure_storage_status:
            self._secure_storage_read_status = self.load_secure_storage()
    
    def _get_fernet(self) -> Fernet:
        """Crée ou retourne l'objet Fernet pour le chiffrement"""
        if self._fernet is None:
            if not self._secure_storage_key:
                raise Exception("Secure storage key is not set")
            
            # Utiliser PBKDF2 pour dériver une clé de 32 bytes
            kdf = PBKDF2(
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


class FileEntry:
    """Classe représentant un fichier téléchargé depuis Celene"""
    
    def __init__(self, name: str, entry_name: str, file_type: str, 
                 course_id: str, latest: bool, parent: Optional[str] = None,
                 children: Optional[List['FileEntry']] = None):
        self.name = name
        self.entry_name = entry_name
        self.type = file_type
        self.course_id = course_id
        self.latest = latest
        self.parent = parent
        self.children = children
    
    @staticmethod
    def open_file(file: 'FileEntry', root_dir:str, folder: bool = False):
        """Ouvre le fichier dans l'application préférée"""
        system = sys_platform.system()
        
        if folder and file.parent:
            file_path = Path(root_dir) / file.course_id / file.parent / file.name
        else:
            file_path = Path(root_dir) / file.course_id / file.name
        
        try:
            if system == "Darwin":  # macOS
                subprocess.run(["open", file_path])
            elif system == "Windows":
                subprocess.run(['cmd', '/c', 'start', '', file_path], shell=True)
            elif system == "Linux":
                subprocess.run(["xdg-open", file_path])
            else:
                logger(f"Unsupported platform: {system}")
        except Exception as e:
            logger(f"Error opening file: {e}")
    
    @staticmethod
    def open_file_in_explorer(file: 'FileEntry', folder: bool = False):
        """Ouvre le fichier dans l'explorateur de fichiers"""
        system = sys_platform.system()
        
        if folder and file.parent:
            file_path = Path(root_dir) / file.course_id / file.parent / file.name
            folder_path = Path(root_dir) / file.course_id / file.parent
        else:
            file_path = Path(root_dir) / file.course_id / file.name
            folder_path = Path(root_dir) / file.course_id
        
        try:
            if system == "Linux":
                logger("Unable to point to a specific file, opening folder instead")
                subprocess.run(['xdg-open', folder_path])
            elif system == "Darwin":  # macOS
                subprocess.run(['open', '-R', file_path])
            elif system == "Windows":
                subprocess.run(['cmd', '/c', 'explorer', '/select,', file_path], shell=True)
            else:
                raise Exception(f"Unsupported platform: {system}")
        except Exception as e:
            logger(f"Error opening in file explorer: {e}")
    
    @staticmethod
    def open_link(link: str):
        """Ouvre un lien dans le navigateur"""
        system = sys_platform.system()
        
        try:
            if system == "Windows":
                subprocess.run(['cmd', '/c', 'start', '', link], shell=True)
            elif system == "Darwin":  # macOS
                subprocess.run(["open", link])
            else:  # Linux et autres
                webbrowser.open(link)
        except Exception as e:
            logger(f"Error opening link: {e}")
    
    def __str__(self):
        return f"Nom : {self.name}, type : -{self.type}"


class Course:
    """Classe représentant une ressource sur Celene"""
    
    def __init__(self, name: str, link: str, type_: str, topic: Optional[str] = None):
        self.name = name
        self.link = link
        self.type = type_
        self.downloaded = False
        self.from_folder = False
        self.associated_file: Optional[FileEntry] = None
        self.topic = topic
        self.parent_folder: Optional[str] = None
    
    @staticmethod
    def construct_from_celene_info(data, parent: Optional[str] = None):
        """Construit depuis un élément HTML"""
        course_atag = data.find("a", class_="aalink stretched-link")
        logger(f"Course topic: {parent}")
        
        if course_atag:
            course_link = course_atag.get("href")
            span = course_atag.find("span", class_="instancename")
            
            if span and course_link:
                access_hide = span.find("span", class_="accesshide")
                
                if access_hide:
                    course_type = access_hide.get_text(strip=True)
                    access_hide.decompose()
                    course_name = span.get_text(strip=True)
                    
                    return Course(course_name, course_link, course_type, topic=parent)
        
        return None
    
    @staticmethod
    def construct_from_file_info(course_file: FileEntry, topic: Optional[str] = None, 
                                 parent_folder: Optional[str] = None):
        """Construit depuis un FileEntry"""
        sub_course = Course(course_file.name, "https://celene.insa-cvl.fr", 
                           course_file.type, topic=topic)
        sub_course.update_download_status()
        sub_course.from_folder = True
        sub_course.parent_folder = parent_folder
        return sub_course
    
    def update_download_status(self):
        self.downloaded = True
    
    def set_file(self, file: FileEntry):
        self.associated_file = file
    
    def __str__(self):
        topic_str = ""
        if self.topic:
            topic_str = f" ({self.topic}"
            if self.parent_folder:
                topic_str += f"-{self.parent_folder}"
            topic_str += ")"
        return f"Nom : {self.name}{topic_str}    Type : {self.type}"


class Classes:
    """Classe représentant un cours sur Celene"""
    
    def __init__(self, name: str, celene_id: str):
        self.name = name
        self.celene_id = celene_id
        self.save_path = celene_id
    
    def update_save_path(self):
        self.save_path = self.celene_id
    
    def set_save_path(self, save_path: str):
        self.save_path = save_path
    
    @staticmethod
    def construct_from_celene_info(data):
        """Construit depuis HTML"""
        class_url = data.find("a")
        
        if not class_url:
            logger("No <a> containing info found")
            return None
        
        course_url = class_url.get("href")
        course_name = class_url.get_text(strip=True)
        
        if not course_url or not course_name:
            return None
        
        course_name = course_name.replace("\t", " ")
        celene_id = CeleneParser.get_id_from_profile_url(course_url)
        
        return Classes(course_name, str(celene_id))
    
    def __str__(self):
        return self.name


class CeleneParser:
    def __init__(self, courses: List[Classes], root_dir: str): # <-- Ajout de root_dir ici
        self.credentials: Optional[Tuple[str, str]] = None
        self.cas_auth: Optional[CASAuth] = None
        self.logged_in = False
        self.courses = courses
        self.files: Dict[str, List[FileEntry]] = {}
        self.celene_endpoint = "https://celene.insa-cvl.fr"
        self.root_dir =Path(root_dir) # <-- Stockez le root_dir comme un objet Path
    
    def get_class_url(self, c_id: str) -> str:
        """Obtient l'URL d'un cours"""
        return f"{self.celene_endpoint}/course/view.php?id={c_id}"
    
    def get_folder_download_link(self, id_: int) -> str:
        """Obtient l'URL de téléchargement d'un dossier"""
        return f"{self.celene_endpoint}/mod/folder/download_folder.php?id={id_}"
    
    @staticmethod
    def get_id_from_url(url: str) -> int:
        """Extrait l'ID depuis une URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return int(params["id"][0]) if "id" in params else -1
    
    @staticmethod
    def get_id_from_profile_url(url: str) -> int:
        """Extrait l'ID depuis une URL de profil"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return int(params["course"][0]) if "course" in params else -1
    
    def set_credentials(self, credentials: Tuple[str, str]):
        """Définit les credentials"""
        self.credentials = credentials
    
    def clear_credentials(self):
        """Efface les credentials"""
        self.credentials = None
    
    def set_cas(self, cas: CASAuth):
        """Définit l'objet CASAuth"""
        self.cas_auth = cas
    
    def add_file_to_downloaded_files(self, entry: FileEntry, c_id: str):
        """Ajoute un fichier aux fichiers téléchargés"""
        if c_id not in self.files:
            self.files[c_id] = []
        self.files[c_id].append(entry)
    
    def login_to_celene(self) -> bool:
        """Connexion à Celene"""
        if not self.credentials:
            logger("CREDENTIAL NULL SO DOING NOTHING")
            raise Exception("Credentials didn't exist at the time of creation")
        
        logger(f"creds are {self.credentials}")
        
        if not self.cas_auth:
            self.cas_auth = CASAuth()
        
        try:
            cas_result = self.cas_auth.login_to_cas(
                self.credentials[0], 
                self.credentials[1], 
                "Celene"
            )
            
            if cas_result == -1:
                return False
            
            self.cas_auth.session_date = datetime.now()
            self.logged_in = True
            self.save_celene_session()
            return True
            
        except Exception as e:
            logger(f"Exception while connecting to CAS: {e}")
            self.logged_in = False
            return False
    
    def save_celene_session(self) -> bool:
        """Sauvegarde la session"""
        if not self.cas_auth:
            self.cas_auth = CASAuth()
        
        return self.cas_auth.save_cas_session([
            ("MoodleSession", "moodleSession"),
            ("MOODLEID1_", "moodleID")
        ])
    
    def load_celene_session(self) -> bool:
        """Charge la session"""
        if not self.cas_auth:
            self.cas_auth = CASAuth()
        
        result = self.cas_auth.load_cas_session([
            ("moodleID", "MOODLEID1_", "https://celene.insa-cvl.fr/"),
            ("moodleSession", "MoodleSession", "https://celene.insa-cvl.fr")
        ])
        
        self.logged_in = result
        return result
    
    def get_class_data(self, c_id: str) -> List[Course]:
        """Récupère les données d'un cours"""
        downloaded_course = self.files.get(c_id, [])
        logger(f"Files: {self.files}")
        logger("Loaded downloaded courses")
        
        courses = []
        
        if not self.logged_in:
            logger("Not logged in, need to log in to Celene")
            if not self.login_to_celene():
                raise Exception("ERROR WHILE CONNECTING TO CELENE")
            logger("Successfully logged in to Celene")
        
        logger(self.cas_auth.session.cookies if self.cas_auth else "No CAS auth")
        
        if self.cas_auth:
            class_url = self.get_class_url(c_id)
            logger(f"Now retrieving class data: class url is {class_url}")
            logger("CAS AUTH HEADERS")
            
            try:
                class_data = self.cas_auth.session.get(class_url, headers=self.cas_auth.headers)
            except requests.exceptions.RequestException:
                class_data = self.cas_auth.session.get(class_url, headers=self.cas_auth.headers)
            
            logger("Get response finished")
            
            if class_data.status_code == 200:
                logger("GET RESPONSE 200 -> Now parsing the page")
                soup = BeautifulSoup(class_data.text, 'html.parser')
                
                # Tìm ul.topics và lấy tất cả các li con
                ul_topics = soup.find("ul", class_="topics")
                if ul_topics:
                    sections = ul_topics.find_all("li", recursive=False)
                else:
                    sections = []
                
                logger(f"Found {len(sections)} sections")
                
                for section in sections:
                    logger("SectionName")
                    # Tìm tên section - có thể trong h3 hoặc h4
                    topic_elem = section.find("h3", class_="sectionname") or section.find("h4", class_=lambda x: x and "sectionname" in x if x else False)
                    topic = topic_elem.get_text(strip=True) if topic_elem else None
                    
                    # Tìm ul.section chứa các activities
                    content_ul = section.find("ul", class_="section")
                    if content_ul:
                        li_elements = content_ul.find_all("li", recursive=False)
                    else:
                        li_elements = []
                    logger(f"Found {len(li_elements)} li_elements in section '{topic}'")
                    
                    for li in li_elements:
                        new_course = Course.construct_from_celene_info(li, parent=topic)
                        
                        if new_course:
                            print(f"DOWNLOADED COURSES ARE {downloaded_course}")
                            associated_file = next(
                                (e for e in downloaded_course if e.entry_name == new_course.name),
                                None
                            )
                            
                            new_course.downloaded = associated_file is not None
                            new_course.associated_file = associated_file
                            
                            if new_course.type == "Dossier" and new_course.downloaded:
                                logger("The folder is downloaded so we have to add all files in this folder")
                                if associated_file and associated_file.children:
                                    for child in associated_file.children:
                                        logger("Adding subCourse")
                                        sub_course = Course.construct_from_file_info(
                                            child,
                                            topic=topic,
                                            parent_folder=new_course.name
                                        )
                                        sub_course.set_file(child)
                                        courses.append(sub_course)
                            else:
                                courses.append(new_course)
        
        return courses
    
    def get_user_joined_classes(self) -> List[Classes]:
        """Récupère les cours rejoints par l'utilisateur"""
        joined_classes = []
        joined_classes_uri = f"{self.celene_endpoint}/user/profile.php?showallcourses=1"
        
        if not self.logged_in:
            logger("Not logged in, need to log in to Celene")
            if not self.login_to_celene():
                raise Exception("ERROR WHILE CONNECTING TO CELENE")
            logger("Successfully logged in to Celene")
        
        if self.cas_auth:
            logger("CAS AUTH HEADERS")
            
            try:
                class_data = self.cas_auth.session.get(
                    joined_classes_uri,
                    headers=self.cas_auth.headers
                )
            except requests.exceptions.RequestException:
                class_data = self.cas_auth.session.get(
                    joined_classes_uri,
                    headers=self.cas_auth.headers
                )
            
            if class_data.status_code == 200:
                logger("Got all data from class!")
                soup = BeautifulSoup(class_data.text, 'html.parser')
                
                classes_div = soup.find_all("li", class_="contentnode")
                courses_dl = next(
                    (div for div in classes_div if div.find("dt", string="Profils de cours")),
                    None
                )
                
                if not courses_dl:
                    logger("Found no div and no UL")
                    return []
                
                li_elements = courses_dl.find_all("li")
                logger(f"Found {len(li_elements)} li_elements")
                
                for li in li_elements:
                    new_class = Classes.construct_from_celene_info(li)
                    if new_class:
                        joined_classes.append(new_class)
        
        return joined_classes
    
    def _download_file(self, link: str, relative_save_path: str) -> str:
        """Télécharge un fichier disponible sur Celene"""
        if not self.logged_in:
            self.login_to_celene()
        
        logger("Now Downloading file")
        logger(f"Sending GET to {link}")
        
        tries = 0
        try:
            download_response = self.cas_auth.session.get(link, headers=self.cas_auth.headers)
        except requests.exceptions.RequestException:
            download_response = self.cas_auth.session.get(link, headers=self.cas_auth.headers)
            tries += 1
        
        if download_response.status_code == 200:
            logger("Successfully downloaded the file")
            filename = "unknownFile"
            logger(download_response.headers)
            
            content_disposition = download_response.headers.get("content-disposition")
            
            if content_disposition:
                logger("Content disposition is not null so we may have a filename")
                parts = content_disposition.split(";")
                
                if len(parts) > 1:
                    filename_part = parts[1]
                    logger(f"filename length {len(filename_part)}")
                    
                    # Extraire le nom du fichier
                    if "filename=" in filename_part:
                        filename = filename_part.split("=", 1)[1].strip()
                        filename = filename.strip('"\'')
                        # Décoder si nécessaire
                        try:
                            filename = filename.encode('latin1').decode('utf-8')
                        except:
                            pass
                    
                    logger(f"Filename is {filename}")
                    
                    filepath = self.root_dir / relative_save_path / filename
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(filepath, 'wb') as f:
                        f.write(download_response.content)
                    
                    logger("File downloaded and saved on disk")
                    return filename
            
            return ""
        else:
            logger(f"Error while trying to download the file, {download_response.status_code} | {download_response.reason}")
            logger(f"{download_response.text}\n{download_response.headers}")
            return ""
    
    def _download_folder(self, link: str, save_path: str) -> str:
        """Télécharge un dossier disponible sur Celene et l'extrait automatiquement"""
        import zipfile
        import tempfile
        
        logger("Downloading folder")
        obj_id = self.get_id_from_url(link)
        dl_link = self.get_folder_download_link(obj_id)
        
        if not self.logged_in:
            self.login_to_celene()
        
        logger("Now sending data")
        
        try:
            dl_response = self.cas_auth.session.get(dl_link, headers=self.cas_auth.headers)
        except requests.exceptions.RequestException:
            dl_response = self.cas_auth.session.get(dl_link, headers=self.cas_auth.headers)
        
        logger("Received data")
        
        if dl_response.status_code == 200:
            logger("File Download successful")
            filename = "UnknownFile"
            
            content_disposition = dl_response.headers.get("content-disposition")
            
            if content_disposition:
                parts = content_disposition.split(";")
                
                if len(parts) > 1:
                    filename_part = parts[1]
                    logger(filename_part)
                    
                    # Extraire après "filename*=UTF-8''"
                    if "filename*=UTF-8''" in filename_part:
                        filename = filename_part.split("filename*=UTF-8''")[1]
                    elif "filename=" in filename_part:
                        filename = filename_part.split("=", 1)[1]
                    
                    filename = filename.strip('"\'')
                    
                    # Décoder si nécessaire
                    try:
                        filename = filename.encode('latin1').decode('utf-8')
                    except:
                        pass
                    
                    logger(f"Filename is {filename}")
                    
                    # Créer le dossier de destination
                    target_dir = os.path.join(str(self.root_dir), save_path)
                    os.makedirs(target_dir, exist_ok=True)
                    
                    # Sauvegarder le ZIP temporairement
                    filepath = os.path.join(target_dir, filename)
                    with open(filepath, 'wb') as f:
                        f.write(dl_response.content)
                    
                    logger("File downloaded, now extracting...")
                    
                    # Extraire le ZIP si c'est un fichier ZIP
                    if filename.lower().endswith('.zip'):
                        try:
                            # Créer un dossier avec le nom du ZIP (sans extension)
                            folder_name = filename[:-4]  # Enlever .zip
                            extract_dir = os.path.join(target_dir, folder_name)
                            os.makedirs(extract_dir, exist_ok=True)
                            
                            # Extraire le contenu
                            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                                zip_ref.extractall(extract_dir)
                            
                            logger(f"Folder extracted to {extract_dir}")
                            
                            # Supprimer le fichier ZIP après extraction
                            os.remove(filepath)
                            logger("ZIP file removed after extraction")
                            
                            return folder_name
                        except zipfile.BadZipFile:
                            logger("Not a valid ZIP file, keeping as is")
                            return filename
                        except Exception as e:
                            logger(f"Error extracting ZIP: {e}")
                            return filename
                    
                    logger("File saved on disk")
                    return filename
            
            return ""
        
        return ""
    
    def _download_link(self, link: str, save_path: str) -> str:
        """Télécharge un lien disponible sur Celene (ouvre ce lien dans le navigateur)"""
        FileEntry.open_link(link)
        return "downloading"
    
    def download_element(self, link: str, elt_type: str, save_path: str) -> str:
        """
        Fonction faisant appel aux fonctions de téléchargement en fonction du type
        
        Args:
            link: URL de la ressource
            elt_type: Type de l'élément ("Fichier", "Dossier", "URL")
            save_path: Chemin de sauvegarde
            
        Returns:
            Nom du fichier téléchargé ou statut
        """
        function_map = self._bind_parser()
        
        if elt_type in function_map:
            return function_map[elt_type](link, save_path)
        
        return ""
    
    def _bind_parser(self) -> Dict[str, Any]:
        """Fonction associant un type de fichier à une fonction de téléchargement"""
        return {
            "Fichier": self._download_file,
            "Dossier": self._download_folder,
            "URL": self._download_link,
        }


# Exemple d'utilisation
if __name__ == "__main__":
    # Configuration du mode debug
    os.environ['DEBUG'] = 'True'
    
    # Créer un parser
    parser = CeleneParser([])
    
    # Option 1: Connexion avec credentials
    parser.set_credentials(("votre_login", "votre_password"))
    
    # Option 2: Utiliser le SecureStorage pour la persistance
    # secure_storage = SecureStorage(
    #     secure_storage_status=True,
    #     secure_storage_key="votre_cle_secrete",
    #     secure_storage_iv="votre_iv"
    # )
    # cas_auth = CASAuth()
    # cas_auth.set_secure_storage(secure_storage)
    # parser.set_cas(cas_auth)
    
    # Charger une session existante
    # if parser.load_celene_session():
    #     print("Session chargée avec succès!")
    # else:
    #     print("Pas de session valide, connexion nécessaire")
    #     if parser.login_to_celene():
    #         print("Connexion réussie!")
    
    # Récupérer les cours de l'utilisateur
    # try:
    #     joined_classes = parser.get_user_joined_classes()
    #     print(f"\nCours trouvés: {len(joined_classes)}")
    #     for cls in joined_classes:
    #         print(f"  - {cls.name} (ID: {cls.celene_id})")
    # except Exception as e:
    #     print(f"Erreur lors de la récupération des cours: {e}")
    
    # Récupérer les ressources d'un cours spécifique
    # try:
    #     course_id = "12345"  # Remplacer par un ID réel
    #     courses = parser.get_class_data(course_id)
    #     print(f"\nRessources trouvées: {len(courses)}")
    #     for course in courses:
    #         print(f"  - {course}")
    # except Exception as e:
    #     print(f"Erreur lors de la récupération des ressources: {e}")
    
    # Télécharger une ressource
    # try:
    #     # Pour un fichier
    #     filename = parser.download_element(
    #         link="https://celene.insa-cvl.fr/mod/resource/view.php?id=12345",
    #         elt_type="Fichier",
    #         save_path="mon_cours"
    #     )
    #     print(f"Fichier téléchargé: {filename}")
    # except Exception as e:
    #     print(f"Erreur lors du téléchargement: {e}")
    
    print("Module celene_parser chargé avec succès!")
    print("Consultez les exemples ci-dessus pour utiliser le module.")