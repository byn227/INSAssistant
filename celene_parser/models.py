"""
Module contenant les modèles de données pour Celene Parser
"""

import subprocess
import webbrowser
from pathlib import Path
from platform import system as sys_platform
from typing import List, Optional

from .utils import logger


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
    def open_file(file: 'FileEntry', root_dir: str, folder: bool = False):
        """Ouvre le fichier dans l'application préférée"""
        system = sys_platform()
        
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
    def open_file_in_explorer(file: 'FileEntry', root_dir: str, folder: bool = False):
        """Ouvre le fichier dans l'explorateur de fichiers"""
        system = sys_platform()
        
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
        system = sys_platform()
        
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
        """Construit depuis HTML - nécessite CeleneParser.get_id_from_profile_url()"""
        from .parser import CeleneParser
        
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
