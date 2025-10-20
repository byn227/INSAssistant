"""
Celene Parser - Module pour scraper et télécharger depuis Celene (INSA CVL)

Ce module fournit les outils nécessaires pour:
- S'authentifier via CAS (Central Authentication Service)
- Parser les cours et ressources sur Celene
- Télécharger automatiquement les fichiers et dossiers

Usage:
    from celene_parser import CeleneParser, Classes
    
    # Créer un parser
    parser = CeleneParser([], root_dir="/path/to/downloads")
    
    # Se connecter
    parser.set_credentials(("login", "password"))
    parser.login_to_celene()
    
    # Récupérer les cours
    classes = parser.get_user_joined_classes()
    
    # Télécharger les ressources d'un cours
    courses = parser.get_class_data(class_id)
"""

from .parser import CeleneParser
from .models import FileEntry, Course, Classes
from .auth import SecureStorage, CASAuth
from .utils import logger, DEBUG, CAS_SERVICE_ENUM

__version__ = "2.0.0"
__author__ = "INSA CVL Team"

__all__ = [
    # Core parser
    "CeleneParser",
    
    # Models
    "FileEntry",
    "Course", 
    "Classes",
    
    # Authentication
    "SecureStorage",
    "CASAuth",
    
    # Utils (public)
    "logger",
    "DEBUG",
    "CAS_SERVICE_ENUM",
]
