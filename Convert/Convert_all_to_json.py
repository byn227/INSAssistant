import os
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set
import PyPDF2
from datetime import datetime

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    # Ne pas interrompre si python-docx manque; juste ignorer les .docx
    print(" python-docx non installé. Les fichiers .docx seront ignorés. (pip install python-docx)")

class UniversalConverter:
    """Convertit tous types de fichiers en JSON"""
    
    # Extensions supportées
    PDF_EXTENSIONS = {'.pdf'}
    DOCX_EXTENSIONS = {'.docx', '.doc'}
    CODE_EXTENSIONS = {'.c', '.cpp', '.h', '.hpp', '.py', '.java', '.js', '.ts', 
                       '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala',
                       '.sh', '.bash', '.sql', '.r', '.m', '.asm'}
    TEXT_EXTENSIONS = {'.txt', '.md', '.markdown', '.rst', '.tex',
                      '.csv', '.xml', '.html', '.css', '.yaml', '.yml',
                      '.ini', '.conf', '.config', '.properties'}
    # Exclure .log et .json de la conversion (fichiers système/cache)
    
    def __init__(self, source_dir: str = "Data", target_dir: str = "Data_json", 
                 clean_text: bool = True):
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.clean_text = clean_text
        self.stats = {
            "pdf": {"total": 0, "success": 0, "failed": 0, "skipped": 0},
            "docx": {"total": 0, "success": 0, "failed": 0, "skipped": 0},
            "code": {"total": 0, "success": 0, "failed": 0, "skipped": 0},
            "text": {"total": 0, "success": 0, "failed": 0, "skipped": 0},
        }
        # Registre des échecs pour un rapport détaillé
        self.failures: List[Dict] = []

    def _log_failure(self, file_type: str, path: Path, reason: str, error: Optional[str] = None):
        rel = str(path.relative_to(self.source_dir)) if path.is_absolute() or self.source_dir in path.parents else str(path)
        self.failures.append({
            "filetype": file_type,
            "file": rel,
            "reason": reason,
            "error": error or ""
        })
    
    def clean_extracted_text(self, text: str) -> str:
        """Nettoie le texte extrait"""
        if not text or not self.clean_text:
            return text
        
        # Supprimer les caractères de contrôle sauf newline, tab, carriage return
        text = ''.join(char for char in text if char in '\n\t\r' or ord(char) >= 32)
        
        # Normaliser les espaces multiples
        text = re.sub(r' +', ' ', text)
        
        # Normaliser les sauts de ligne (max 2)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Supprimer espaces en début/fin de ligne
        text = '\n'.join(line.strip() for line in text.split('\n'))
        text = text.strip()
        
        # Caractères Unicode problématiques
        replacements = {
            '\ufeff': '',  # BOM
            '\u200b': '',  # Zero width space
            '\xa0': ' ',   # Non-breaking space
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text
    
    def get_file_type(self, file_path: Path) -> Optional[str]:
        """Détermine le type de fichier"""
        ext = file_path.suffix.lower()
        if ext in self.PDF_EXTENSIONS:
            return 'pdf'
        elif ext in self.DOCX_EXTENSIONS and DOCX_AVAILABLE:
            return 'docx'
        elif ext in self.CODE_EXTENSIONS:
            return 'code'
        elif ext in self.TEXT_EXTENSIONS:
            return 'text'
        return None
    
    def extract_pdf_content(self, pdf_path: Path) -> Optional[Dict]:
        """Extrait le contenu d'un PDF"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                # Gérer les PDF chiffrés en essayant un mot de passe vide
                try:
                    if getattr(pdf_reader, 'is_encrypted', False):
                        try:
                            # PyPDF2 anciennes versions
                            res = pdf_reader.decrypt("")
                            if res == 0:
                                raise Exception("PDF chiffré (mot de passe requis)")
                        except Exception:
                            # Certaines versions de PyPDF2 ont une API différente
                            raise Exception("PDF chiffré (non déchiffrable)"
                                            )
                except Exception as enc_err:
                    self._log_failure('pdf', pdf_path, 'encrypted_pdf', str(enc_err))
                    return None
                metadata = pdf_reader.metadata
                num_pages = len(pdf_reader.pages)
                
                text_content = []
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    try:
                        text = page.extract_text()
                        cleaned_text = self.clean_extracted_text(text) if text else ""
                        text_content.append({
                            "page": page_num,
                            "text": cleaned_text
                        })
                    except Exception as e:
                        text_content.append({
                            "page": page_num,
                            "text": "",
                            "error": str(e)
                        })
                
                return {
                    "filename": pdf_path.name,
                    "filepath": str(pdf_path.relative_to(self.source_dir)),
                    "filetype": "pdf",
                    "metadata": {
                        "title": metadata.get('/Title', '') if metadata else '',
                        "author": metadata.get('/Author', '') if metadata else '',
                        "num_pages": num_pages
                    },
                    "pages": text_content,
                    "extracted_at": datetime.now().isoformat(),
                    "full_text": "\n\n".join([p["text"] for p in text_content])
                }
        except Exception as e:
            msg = str(e)
            print(f" Error extracting PDF {pdf_path.name}: {msg}")
            reason = 'pdf_read_error'
            # Cas courant: AES nécessite PyCryptodome
            if 'PyCryptodome is required for AES algorithm' in msg:
                reason = 'aes_pdf_requires_pycryptodome'
            self._log_failure('pdf', pdf_path, reason, msg)
            return None

    def extract_docx_content(self, docx_path: Path) -> Optional[Dict]:
        """Extrait le contenu d'un fichier Word (.docx) si support disponible"""
        if not DOCX_AVAILABLE:
            return None
        # Conversion automatique des anciens .doc vers .docx via LibreOffice/unoconv si possible
        converted_temp: Optional[Path] = None
        input_path = docx_path
        if docx_path.suffix.lower() == '.doc':
            rel = docx_path.relative_to(self.source_dir)
            print(f"↪️  Legacy .doc détecté, tentative de conversion: {rel}")
            try:
                converted_temp = self._convert_legacy_doc(docx_path)
                if converted_temp is None:
                    print("⏭  Ignored legacy .doc (non supporté): outil de conversion introuvable (soffice/unoconv)")
                    self._log_failure('docx', docx_path, 'unsupported_legacy_doc', 'Install LibreOffice (soffice) ou unoconv pour activer la conversion automatique')
                    return None
                input_path = converted_temp
            except Exception as conv_err:
                self._log_failure('docx', docx_path, 'doc_legacy_conversion_failed', str(conv_err))
                return None
        try:
            document = docx.Document(input_path)
            paragraphs = []
            for i, para in enumerate(document.paragraphs, 1):
                txt = para.text.strip()
                if txt:
                    cleaned = self.clean_extracted_text(txt)
                    paragraphs.append({
                        "paragraph_num": i,
                        "text": cleaned,
                        "style": para.style.name if para.style else "Normal"
                    })
            full_text = "\n\n".join(p["text"] for p in paragraphs)
            core = document.core_properties
            data = {
                "filename": docx_path.name,
                "filepath": str(docx_path.relative_to(self.source_dir)),
                "filetype": "docx",
                "metadata": {
                    "title": core.title or '',
                    "author": core.author or '',
                    "subject": core.subject or '',
                    "created": core.created.isoformat() if core.created else '',
                    "modified": core.modified.isoformat() if core.modified else '',
                    "num_paragraphs": len(paragraphs)
                },
                "paragraphs": paragraphs,
                "extracted_at": datetime.now().isoformat(),
                "full_text": full_text
            }
            if converted_temp is not None:
                # Indiquer que le document a été converti
                data["metadata"]["converted_from_doc"] = True
            return data
        except Exception as e:
            print(f"❌ Error extracting DOCX {docx_path.name}: {e}")
            self._log_failure('docx', docx_path, 'docx_read_error', str(e))
            return None
        finally:
            # Nettoyer le fichier temporaire converti si créé
            if converted_temp is not None:
                try:
                    if converted_temp.exists():
                        converted_temp.unlink()
                except Exception:
                    pass

    def _convert_legacy_doc(self, doc_path: Path) -> Optional[Path]:
        """Convertit un .doc vers .docx en utilisant LibreOffice (soffice) ou unoconv.
        Retourne le chemin du .docx temporaire si succès, sinon None.
        """
        soffice = shutil.which('soffice')
        unoconv = shutil.which('unoconv')
        if not soffice and not unoconv:
            return None
        tmpdir = Path(tempfile.mkdtemp(prefix='doc_convert_'))
        out_path = tmpdir / f"{doc_path.stem}.docx"
        try:
            if soffice:
                # LibreOffice headless conversion
                cmd = [soffice, '--headless', '--convert-to', 'docx', '--outdir', str(tmpdir), str(doc_path)]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                if res.returncode != 0:
                    raise RuntimeError(f"soffice conversion failed: {res.stderr.strip() or res.stdout.strip()}")
            else:
                # Fallback to unoconv
                cmd = [unoconv, '-f', 'docx', '-o', str(out_path), str(doc_path)]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                if res.returncode != 0:
                    raise RuntimeError(f"unoconv conversion failed: {res.stderr.strip() or res.stdout.strip()}")
            if not out_path.exists() or out_path.stat().st_size == 0:
                raise RuntimeError("Converted file not found or empty")
            return out_path
        except Exception as e:
            # Nettoyer le dossier temp en cas d'échec
            try:
                if out_path.exists():
                    out_path.unlink()
                tmpdir.rmdir()
            except Exception:
                pass
            raise e
    
    def extract_code_content(self, code_path: Path) -> Optional[Dict]:
        """Extrait le contenu d'un fichier code"""
        try:
            # Essayer plusieurs encodings
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'iso-8859-15']
            content = None
            encoding_used = None
            
            for encoding in encodings:
                try:
                    with open(code_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    encoding_used = encoding
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                print(f" Could not decode {code_path.name}")
                return None
            
            # Nettoyer si demandé
            if self.clean_text:
                content = self.clean_extracted_text(content)
            
            # Compter les lignes
            lines = content.split('\n')
            num_lines = len(lines)
            
            # Détecter le langage
            ext = code_path.suffix.lower()
            language_map = {
                '.c': 'C', '.cpp': 'C++', '.h': 'C/C++ Header',
                '.py': 'Python', '.java': 'Java', '.js': 'JavaScript',
                '.ts': 'TypeScript', '.go': 'Go', '.rs': 'Rust',
                '.rb': 'Ruby', '.php': 'PHP', '.sh': 'Shell',
                '.sql': 'SQL', '.r': 'R', '.m': 'MATLAB'
            }
            language = language_map.get(ext, 'Unknown')
            
            return {
                "filename": code_path.name,
                "filepath": str(code_path.relative_to(self.source_dir)),
                "filetype": "code",
                "language": language,
                "extension": ext,
                "metadata": {
                    "num_lines": num_lines,
                    "num_chars": len(content),
                    "encoding": encoding_used,
                    "size_bytes": code_path.stat().st_size
                },
                "content": content,
                "lines": lines,
                "extracted_at": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"❌ Error extracting code {code_path.name}: {e}")
            self._log_failure('code', code_path, 'code_read_error', str(e))
            return None
    
    def extract_text_content(self, text_path: Path) -> Optional[Dict]:
        """Extrait le contenu d'un fichier texte"""
        try:
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'iso-8859-15']
            content = None
            encoding_used = None
            
            for encoding in encodings:
                try:
                    with open(text_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    encoding_used = encoding
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                return None
            
            if self.clean_text:
                content = self.clean_extracted_text(content)
            
            lines = content.split('\n')
            
            return {
                "filename": text_path.name,
                "filepath": str(text_path.relative_to(self.source_dir)),
                "filetype": "text",
                "extension": text_path.suffix.lower(),
                "metadata": {
                    "num_lines": len(lines),
                    "num_chars": len(content),
                    "encoding": encoding_used,
                    "size_bytes": text_path.stat().st_size
                },
                "content": content,
                "lines": lines,
                "extracted_at": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error extracting text {text_path.name}: {e}")
            self._log_failure('text', text_path, 'text_read_error', str(e))
            return None
    
    def convert_file(self, file_path: Path) -> bool:
        """Convertit un fichier en JSON"""
        file_type = self.get_file_type(file_path)
        if not file_type:
            return False
        
        # Chemin de sortie
        relative_path = file_path.relative_to(self.source_dir)
        json_path = self.target_dir / relative_path.with_suffix('.json')
        json_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Vérifier si existe
        if json_path.exists():
            print(f"⏭  Skipped: {relative_path}")
            self.stats[file_type]["skipped"] += 1
            return True
        
        # Extraire selon le type
        print(f"📄 Converting [{file_type}]: {relative_path}")
        
        if file_type == 'pdf':
            content = self.extract_pdf_content(file_path)
        elif file_type == 'docx':
            content = self.extract_docx_content(file_path)
        elif file_type == 'code':
            content = self.extract_code_content(file_path)
        elif file_type == 'text':
            content = self.extract_text_content(file_path)
        else:
            content = None
        
        if content:
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(content, f, ensure_ascii=False, indent=2)
                print(f" Saved: {json_path.relative_to(self.target_dir)}")
                self.stats[file_type]["success"] += 1
                return True
            except Exception as e:
                print(f" Error saving: {e}")
                # Journaliser les échecs d'écriture pour le rapport
                self._log_failure(file_type, file_path, 'save_json_error', str(e))
                self.stats[file_type]["failed"] += 1
                return False
        else:
            self.stats[file_type]["failed"] += 1
            return False
    
    def convert_all(self):
        """Convertit tous les fichiers supportés"""
        print(f"🔍 Scanning {self.source_dir}...")
        
        # Trouver tous les fichiers (insensible à la casse des extensions)
        # Parcours unique puis filtrage par get_file_type
        all_files = [p for p in self.source_dir.rglob('*') if p.is_file()]
        
        # Grouper par type
        files_by_type = {'pdf': [], 'docx': [], 'code': [], 'text': []}
        for f in all_files:
            ftype = self.get_file_type(f)
            if ftype:
                files_by_type[ftype].append(f)
                self.stats[ftype]["total"] += 1
        
        print(f"\n Files found:")
        print(f"   PDFs: {len(files_by_type['pdf'])}")
        if DOCX_AVAILABLE:
            print(f"   DOCX: {len(files_by_type['docx'])}")
        print(f"   Code: {len(files_by_type['code'])}")
        print(f"   Text: {len(files_by_type['text'])}")
        print(f"   Total: {sum(len(v) for v in files_by_type.values())}")
        print("-" * 60)
        
        # Convertir
        total_processed = 0
        total_files = sum(len(v) for v in files_by_type.values())
        
        for file_type, files in files_by_type.items():
            if not files:
                continue
            print(f"\n{'='*60}")
            print(f"Processing {file_type.upper()} files ({len(files)} files)")
            print('='*60)
            
            for i, file_path in enumerate(files, 1):
                total_processed += 1
                print(f"\n[{total_processed}/{total_files}]")
                self.convert_file(file_path)
        
        # Statistiques finales
        print("\n" + "=" * 60)
        print(" FINAL STATISTICS")
        print("=" * 60)

        for file_type in ['pdf', 'docx', 'code', 'text']:
            stats = self.stats[file_type]
            if stats['total'] > 0:
                print(f"\n{file_type.upper()}:")
                print(f"  Total:      {stats['total']}")
                print(f"  Success: {stats['success']}")
                print(f"  Skipped: {stats['skipped']}")
                print(f"  Failed:  {stats['failed']}")

        print("=" * 60)
        # Écrire un rapport détaillé des échecs (si existants)
        if self.failures:
            report_path = self.target_dir / "conversion_report.json"
            try:
                with open(report_path, 'w', encoding='utf-8') as rf:
                    json.dump({
                        'stats': self.stats,
                        'failures': self.failures
                    }, rf, ensure_ascii=False, indent=2)
                print(f"📝 Rapport détaillé écrit: {report_path}")
            except Exception as e:
                print(f"⚠️  Impossible d'écrire le rapport: {e}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Convert all files (PDF, code, text) to JSON"
    )
    
    parser.add_argument('--source', default='Data', help='Source directory')
    parser.add_argument('--target', default='Data_json', help='Target directory')
    parser.add_argument('--force', action='store_true', help='Force re-conversion')
    parser.add_argument('--no-clean', action='store_true', help='Disable text cleaning')
    
    args = parser.parse_args()
    
    # Résolution intelligente des chemins quand lancé depuis Convert/
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    source_path = Path(args.source)
    target_path = Path(args.target)
    if not source_path.exists():
        alt = repo_root / args.source
        if alt.exists():
            print(f"ℹ️  Source '{source_path}' introuvable. Utilisation de '{alt}'.")
            source_path = alt
    if not target_path.is_absolute():
        target_path = repo_root / args.target
    if not source_path.exists():
        print(f"❌ Source directory not found: {source_path}")
        print("   Tip: run with --source ../Data when executing from Convert/")
        return

    print("=" * 60)
    print("Universal File to JSON Converter")
    print("=" * 60)
    supported = "PDF, " + ("DOCX, " if DOCX_AVAILABLE else "") + "Code (.c, .py, .java, etc.), Text (.txt, .md, etc.)"
    print(f"Supported: {supported}")
    if not args.no_clean:
        print("🧹 Text cleaning: ENABLED")
    print("=" * 60)
    
    # Si force, supprimer le target_dir
    if args.force:
        import shutil
        if target_path.exists():
            print(f"🗑️  Removing {target_path} for fresh conversion...")
            shutil.rmtree(target_path)
    
    # Créer la cible si besoin
    target_path.mkdir(parents=True, exist_ok=True)

    converter = UniversalConverter(str(source_path), str(target_path), clean_text=not args.no_clean)
    converter.convert_all()


if __name__ == "__main__":
    main()
