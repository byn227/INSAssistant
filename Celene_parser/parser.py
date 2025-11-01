"""
Module contenant la classe CeleneParser pour le parsing et téléchargement depuis Celene
"""

import os
import zipfile
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

from .utils import logger
from .auth import CASAuth
from .models import FileEntry, Course, Classes


class CeleneParser:
    """Classe principale pour parser et télécharger depuis Celene"""
    
    def __init__(self, courses: List[Classes], root_dir: str):
        """
        Initialise le parser Celene
        
        Args:
            courses: Liste des cours à traiter
            root_dir: Répertoire racine pour les téléchargements
        """
        self.credentials: Optional[Tuple[str, str]] = None
        self.cas_auth: Optional[CASAuth] = None
        self.logged_in = False
        self.courses = courses
        self.files: Dict[str, List[FileEntry]] = {}
        self.celene_endpoint = "https://celene.insa-cvl.fr"
        self.root_dir = Path(root_dir)
    
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
