import os
import sys
import configparser
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any
import json
from datetime import datetime
import traceback # Import pour un meilleur affichage des erreurs
import re # Pour le nettoyage des noms de fichiers

# Import des classes du module celene_parser
from celene_parser import CeleneParser, SecureStorage, CASAuth, Classes, Course, FileEntry

class CeleneScraperConfig:
    """Classe pour gérer la configuration du scraper"""
    
    def __init__(self, config_file: str = "celene.conf"):
        self.config_file = Path(config_file) # Utilisation de pathlib pour une meilleure gestion des chemins
        self.config = configparser.ConfigParser()
        
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        
        self.config.read(self.config_file)
        
        # Charger les paramètres
        self.user = self.config.get('scraper', 'user', fallback=None)
        self.pwd = self.config.get('scraper', 'pwd', fallback=None)
        self.root_dir = Path(self.config.get('scraper', 'root_dir', fallback="celene_downloads")) # Renommé en root_dir
        self.base_url = self.config.get('scraper', 'base_url', fallback="https://celene.insa-cvl.fr") # Renommé en base_url
        
        if not self.user or not self.pwd:
            raise ValueError("User and password must be set in the configuration file.")

        # Créer le dossier root_dir s'il n'existe pas
        self.root_dir.mkdir(parents=True, exist_ok=True)
    
    def __str__(self):
        return (f"CeleneScraperConfig:\n"
                f"  User: {self.user}\n"
                f"  Root Directory: {self.root_dir.resolve()}\n"
                f"  Base URL: {self.base_url}")


class CeleneScraper:
    """Classe principale pour scraper Celene"""
    
    def __init__(self, config: CeleneScraperConfig, use_cache: bool = True):
        self.config = config
        self.use_cache = use_cache
        self.cache_file = config.root_dir / ".celene_cache.json" # Utilisation de pathlib
        self.log_file = config.root_dir / "scraper.log" # Utilisation de pathlib
        
        # Initialiser le parser en lui passant le répertoire racine
        # Assurez-vous que CeleneParser a un argument `root_dir` dans son __init__
        # (voir la modification suggérée pour celene_parser.py plus bas)
        self.parser = CeleneParser([], root_dir=str(config.root_dir)) 
        self.parser.set_credentials((config.user, config.pwd))
        # Le SecureStorage est géré par CASAuth, qui sera créé ou chargé par le parser.
        # Il n'est pas nécessaire de le passer ici directement.
    
    def log(self, message: str, level: str = "INFO"):
        """Logger avec timestamp et écriture dans la console et un fichier"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        print(log_message)
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_message + '\n')
        except Exception as e:
            print(f"[{timestamp}] [ERROR] Failed to write to log file: {e}")
    
    def load_cache(self) -> Dict[str, Any]:
        """Charge le cache depuis le fichier"""
        if not self.use_cache or not self.cache_file.exists():
            return {}
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            self.log("Cache loaded successfully.")
            return cache_data
        except json.JSONDecodeError as e:
            self.log(f"Error decoding cache file (corrupted?): {e}", "ERROR")
            return {}
        except Exception as e:
            self.log(f"Error loading cache: {e}", "ERROR")
            return {}
    
    def save_cache(self, cache: Dict[str, Any]):
        """Sauvegarde le cache"""
        if not self.use_cache:
            return
        
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            self.log("Cache saved successfully.")
        except Exception as e:
            self.log(f"Error saving cache: {e}", "ERROR")
    
    def connect(self) -> bool:
        """Connexion à Celene"""
        self.log("Connecting to Celene...")
        
        try:
            # Essayer de charger une session existante via le parser (qui utilise CASAuth)
            if self.parser.load_celene_session():
                self.log("Loaded existing session.")
                return True
            
            # Sinon, se connecter avec les credentials
            if self.parser.login_to_celene():
                self.log("Login successful.")
                return True
            else:
                self.log("Login failed. Check your credentials.", "ERROR")
                return False
        except Exception as e:
            self.log(f"Connection error: {e}", "ERROR")
            self.log(traceback.format_exc(), "DEBUG") # Afficher le traceback en mode debug
            return False
    
    def get_all_courses(self) -> List[Classes]:
        """Récupère tous les cours de l'utilisateur"""
        self.log("Fetching user courses...")
        
        try:
            courses = self.parser.get_user_joined_classes()
            self.log(f"Found {len(courses)} courses.")
            return courses
        except Exception as e:
            self.log(f"Error fetching courses: {e}", "ERROR")
            self.log(traceback.format_exc(), "DEBUG")
            return []
    
    def scrape_course(self, course: Classes, cache: Dict[str, Any]):
        """Scrape un cours spécifique et met à jour le cache"""
        course_id = course.celene_id
        course_name = course.name
        
        self.log(f"Scraping course: '{course_name}' (ID: {course_id})")
        
        # Le dossier de destination pour ce cours
        # Il sera relatif à self.config.root_dir, et sera passé au parser
        course_target_sub_dir = self._sanitize_filename(course_name)
        (self.config.root_dir / course_target_sub_dir).mkdir(parents=True, exist_ok=True)
        
        # Charger les fichiers déjà connus pour ce cours à partir du système de fichiers
        # pour s'assurer que parser.files est à jour.
        # Ceci est une amélioration pour gérer les fichiers existants localement.
        self._populate_parser_files_from_disk(course_id, course_target_sub_dir)

        # Récupérer les informations de ressources (le parser met à jour `downloaded` et `associated_file`)
        try:
            celene_resources = self.parser.get_class_data(course_id)
            self.log(f"  Found {len(celene_resources)} resources on Celene for this course.")
            
            # Mettre à jour le cache local pour ce cours
            current_course_cache = cache.setdefault(course_id, {
                'name': course_name,
                'last_scrape': None,
                'resource_count': 0,
                'downloaded_resource_names': []
            })
            
            # Assurer que downloaded_resource_names existe
            if 'downloaded_resource_names' not in current_course_cache:
                current_course_cache['downloaded_resource_names'] = []
            
            downloaded_count = 0
            for resource in celene_resources:
                # Utiliser le flag `downloaded` du `Course` qui est mis à jour par `parser.get_class_data`
                if resource.downloaded and resource.name in current_course_cache['downloaded_resource_names']:
                    self.log(f"    Skipping (already downloaded and in cache): '{resource.name}'")
                    continue
                
                # Le `downloaded` flag peut être True si un FileEntry existe pour cette ressource.
                # Cependant, nous voulons le retélécharger si le fichier n'est pas sur le disque
                # ou si nous ne l'avons pas en cache.
                # Nous passons le chemin relatif au root_dir du parser
                if self._download_resource(resource, course_target_sub_dir, course_id):
                    downloaded_count += 1
                    current_course_cache['downloaded_resource_names'].append(resource.name)
            
            self.log(f"  Downloaded {downloaded_count} new resources for '{course_name}'.")
            
            # Mettre à jour les métadonnées du cache pour le cours
            current_course_cache['last_scrape'] = datetime.now().isoformat()
            current_course_cache['resource_count'] = len(celene_resources)
            
        except Exception as e:
            self.log(f"  Error scraping course '{course_name}': {e}", "ERROR")
            self.log(traceback.format_exc(), "DEBUG")

    def _populate_parser_files_from_disk(self, course_id: str, course_target_sub_dir: str):
        """
        Scan le répertoire local du cours pour charger les fichiers existants dans parser.files
        afin que CeleneParser puisse marquer les ressources comme "déjà téléchargées".
        """
        course_local_path = self.config.root_dir / course_target_sub_dir
        if not course_local_path.is_dir():
            return

        self.parser.files[course_id] = [] # Vider les anciens ou initialiser
        for root, dirs, files in os.walk(course_local_path):
            current_relative_path = Path(root).relative_to(course_local_path)
            parent_folder_name = str(current_relative_path) if current_relative_path != Path('.') else None

            for file_name in files:
                # Ignorer les fichiers de cache
                if file_name == self.cache_file.name:
                    continue

                # Déduire le type à partir de l'extension si possible, sinon 'Fichier'
                file_type = "Fichier"
                if Path(file_name).suffix.lower() == ".zip":
                    file_type = "Dossier" # Potentiellement un dossier téléchargé en zip

                file_entry = FileEntry(
                    name=file_name,
                    entry_name=file_name, # Pour l'instant, on suppose que le nom d'entrée est le nom du fichier
                    file_type=file_type,
                    course_id=course_id,
                    latest=True, # On considère que les fichiers sur disque sont les derniers
                    parent=parent_folder_name # Parent si dans un sous-dossier
                )
                self.parser.files[course_id].append(file_entry)
        
        self.log(f"  Loaded {len(self.parser.files.get(course_id, []))} existing files for course {course_id} from disk.")


    def _download_resource(self, resource: Course, course_target_sub_dir: str, course_id: str) -> bool:
        """
        Télécharge une ressource.
        `course_target_sub_dir` est le chemin relatif où le fichier doit être enregistré,
        à partir du `root_dir` du scraper.
        """
        try:
            self.log(f"    Downloading: '{resource.name}' (Type: {resource.type})")
            
            # Le parser attend un chemin relatif à son `root_dir`
            # `course_target_sub_dir` est déjà relatif à `self.config.root_dir`
            downloaded_filename = self.parser.download_element(
                link=resource.link,
                elt_type=resource.type,
                save_path=course_target_sub_dir 
            )
            
            if downloaded_filename == "downloading": # Cas des liens URL ouverts dans le navigateur
                self.log(f"    🔗 Opened link in browser: '{resource.name}'")
                return True
            elif downloaded_filename:
                self.log(f"    ✓ Downloaded '{downloaded_filename}' for '{resource.name}'.")
                
                # Mettre à jour l'entrée du fichier dans le parser après le téléchargement
                # Ceci est essentiel pour que `get_class_data` puisse marquer `downloaded=True` lors des prochaines exécutions
                # Il faut ici créer un FileEntry correct et l'ajouter au parser.files
                file_entry = FileEntry(
                    name=downloaded_filename,
                    entry_name=resource.name, # Le nom de la ressource Celene
                    file_type=resource.type,
                    course_id=course_id,
                    latest=True,
                    parent=resource.parent_folder # Si la ressource était déjà dans un sous-dossier (ex: dossier Celene)
                )
                self.parser.add_file_to_downloaded_files(file_entry, course_id)

                return True
            else:
                self.log(f"    ✗ Failed to download: '{resource.name}'", "WARNING")
                return False
            
        except Exception as e:
            self.log(f"    ✗ Error downloading '{resource.name}': {e}", "ERROR")
            self.log(traceback.format_exc(), "DEBUG")
            return False
    
    def _sanitize_filename(self, filename: str) -> str:
        """Nettoie un nom de fichier pour qu'il soit sûr pour le système de fichiers"""
        # Caractères invalides pour la plupart des OS
        invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
        # Remplacer les caractères invalides par un underscore
        filename = re.sub(invalid_chars, '_', filename)
        # Supprimer les points au début ou à la fin, pour éviter les problèmes avec les fichiers cachés ou les chemins
        filename = filename.strip(' .')
        # Limiter la longueur du nom de fichier si nécessaire (utile pour certains OS ou systèmes de fichiers)
        if len(filename) > 200: 
            filename = filename[:200]
        return filename.strip()
    
    def scrape_all(self):
        """Scrape tous les cours"""
        self.log("=" * 60)
        self.log("Starting Celene Scraper in ALL COURSES mode")
        self.log("=" * 60)
        
        # Connexion
        if not self.connect():
            self.log("Failed to connect. Aborting.", "ERROR")
            return
        
        # Charger le cache
        cache = self.load_cache()
        
        # Récupérer les cours
        courses = self.get_all_courses()
        
        if not courses:
            self.log("No courses found.", "WARNING")
            return
        
        # Scraper chaque cours
        for i, course in enumerate(courses, 1):
            self.log(f"\n[{i}/{len(courses)}] Processing course '{course.name}'...")
            self.scrape_course(course, cache)
            # Sauvegarder le cache après chaque cours pour éviter la perte de données en cas d'interruption
            self.save_cache(cache)
        
        self.log("=" * 60)
        self.log("Scraping completed for all courses!")
        self.log("=" * 60)
    
    def scrape_specific_course(self, course_id: str):
        """Scrape un cours spécifique par son ID"""
        self.log(f"Scraping specific course with ID: {course_id}")
        
        if not self.connect():
            self.log("Failed to connect. Aborting.", "ERROR")
            return
        
        cache = self.load_cache()
        
        # Récupérer la liste complète pour trouver le nom du cours
        all_courses = self.get_all_courses()
        target_course = next((c for c in all_courses if c.celene_id == course_id), None)

        if not target_course:
            # Si le cours n'est pas dans la liste de l'utilisateur, on crée un objet Classes basique
            # et le scraper essaiera de récupérer les données si l'ID est valide.
            self.log(f"Course ID {course_id} not found in user's joined courses list. Attempting to scrape anyway with a generic name.")
            target_course = Classes(f"Course_{course_id}", course_id)
        
        self.scrape_course(target_course, cache)
        self.save_cache(cache)
        
        self.log(f"Scraping completed for course ID {course_id}!")
    
    def list_courses(self):
        """Liste tous les cours disponibles pour l'utilisateur"""
        self.log("Listing all available courses...")
        
        if not self.connect():
            self.log("Failed to connect. Aborting.", "ERROR")
            return
        
        courses = self.get_all_courses()
        
        if not courses:
            self.log("No courses found.", "WARNING")
            return
        
        print(f"\n{'=' * 60}")
        print(f"Found {len(courses)} courses for user '{self.config.user}':")
        print(f"{'=' * 60}")
        
        for i, course in enumerate(courses, 1):
            print(f"{i}. {course.name}")
            print(f"   ID: {course.celene_id}")
            print()
    
    def show_stats(self):
        """Affiche les statistiques basées sur le cache"""
        cache = self.load_cache()
        
        print(f"\n{'=' * 60}")
        print("Scraper Statistics")
        print(f"{'=' * 60}")
        print(f"Root download directory: {self.config.root_dir.resolve()}")
        print(f"Number of cached courses: {len(cache)}")
        
        if cache:
            print("\nCourse details:")
            total_resources = 0
            total_downloaded = 0
            for course_id, data in cache.items():
                course_name = data.get('name', f'Unknown Course (ID: {course_id})')
                resources_count = data.get('resource_count', 0)
                downloaded_count = len(data.get('downloaded_resource_names', []))
                
                print(f"  - '{course_name}'")
                print(f"    ID: {course_id}")
                print(f"    Last scraped: {data.get('last_scrape', 'Never')}")
                print(f"    Resources on Celene: {resources_count}")
                print(f"    Downloaded by scraper: {downloaded_count}")
                print()
                total_resources += resources_count
                total_downloaded += downloaded_count
            print(f"{'=' * 60}")
            print(f"Total unique resources on Celene (cached): {total_resources}")
            print(f"Total resources downloaded by scraper (cached): {total_downloaded}")
            print(f"{'=' * 60}")


def main():
    """Fonction principale du script Celene Scraper"""
    parser = argparse.ArgumentParser(
        description="Celene Scraper - Automatically download course materials from Celene",
        formatter_class=argparse.RawTextHelpFormatter # Pour un formatage multiligne si besoin
    )
    
    parser.add_argument(
        '-c', '--config',
        default='celene.conf',
        help='Path to the configuration file (default: celene.conf)'
    )
    
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable cache. Forces re-download of all resources.'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode, showing detailed logs and tracebacks.'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Command: scrape all
    subparsers.add_parser(
        'scrape', 
        help='Scrape all courses the user is enrolled in. This is the default command if none is specified.'
    )
    
    # Command: scrape specific course
    scrape_course_parser = subparsers.add_parser(
        'scrape-course', 
        help='Scrape a specific course by its Celene ID.'
    )
    scrape_course_parser.add_argument(
        'course_id', 
        help='The numerical ID of the course to scrape (e.g., "12345").'
    )
    
    # Command: list courses
    subparsers.add_parser(
        'list', 
        help='List all courses the user is enrolled in, showing their names and IDs.'
    )
    
    # Command: stats
    subparsers.add_parser(
        'stats', 
        help='Show statistics about scraped courses from the cache.'
    )
    
    args = parser.parse_args()
    
    # Si aucune commande n'est spécifiée, la valeur par défaut est 'scrape'
    if args.command is None:
        args.command = 'scrape'

    # Activer le debug si demandé
    if args.debug:
        os.environ['DEBUG'] = 'True'
        # Assurez-vous que le logger de celene_parser utilise os.environ['DEBUG']
    
    try:
        # Charger la configuration
        config = CeleneScraperConfig(args.config)
        print("--- Celene Scraper Configuration ---")
        print(config)
        print("------------------------------------")
        
        # Créer le scraper
        scraper = CeleneScraper(config, use_cache=not args.no_cache)
        
        # Exécuter la commande
        if args.command == 'scrape':
            scraper.scrape_all()
        elif args.command == 'scrape-course':
            scraper.scrape_specific_course(args.course_id)
        elif args.command == 'list':
            scraper.list_courses()
        elif args.command == 'stats':
            scraper.show_stats()
        
    except FileNotFoundError as e:
        print(f"\nError: {e}", file=sys.stderr)
        print(f"Please ensure '{args.config}' exists and is correctly configured.", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"\nConfiguration Error: {e}", file=sys.stderr)
        print(f"Please check your '{args.config}' file.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user (Ctrl+C). Exiting gracefully.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()