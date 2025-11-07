#!/usr/bin/env python3
"""
Script pour convertir tous les fichiers (PDF, code, texte) en JSON
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
import PyPDF2
from datetime import datetime


class UniversalConverter:
    """Convertit tous types de fichiers en JSON"""
    
    # Extensions supportées
    PDF_EXTENSIONS = {'.pdf'}
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
            "code": {"total": 0, "success": 0, "failed": 0, "skipped": 0},
            "text": {"total": 0, "success": 0, "failed": 0, "skipped": 0},
        }
    
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
            print(f" Error extracting PDF {pdf_path.name}: {e}")
            return None
    
    def extract_code_content(self, code_path: Path) -> Optional[Dict]:
        """Extrait le contenu d'un fichier code"""
        try:
            # Essayer plusieurs encodings
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
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
            return None
    
    def extract_text_content(self, text_path: Path) -> Optional[Dict]:
        """Extrait le contenu d'un fichier texte"""
        try:
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
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
                self.stats[file_type]["failed"] += 1
                return False
        else:
            self.stats[file_type]["failed"] += 1
            return False
    
    def convert_all(self):
        """Convertit tous les fichiers supportés"""
        print(f"🔍 Scanning {self.source_dir}...")
        
        # Trouver tous les fichiers
        all_files = []
        for ext_set in [self.PDF_EXTENSIONS, self.CODE_EXTENSIONS, self.TEXT_EXTENSIONS]:
            for ext in ext_set:
                all_files.extend(self.source_dir.rglob(f"*{ext}"))
        
        # Grouper par type
        files_by_type = {'pdf': [], 'code': [], 'text': []}
        for f in all_files:
            ftype = self.get_file_type(f)
            if ftype:
                files_by_type[ftype].append(f)
                self.stats[ftype]["total"] += 1
        
        print(f"\n Files found:")
        print(f"   PDFs: {len(files_by_type['pdf'])}")
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
        
        for file_type in ['pdf', 'code', 'text']:
            stats = self.stats[file_type]
            if stats['total'] > 0:
                print(f"\n{file_type.upper()}:")
                print(f"  Total:      {stats['total']}")
                print(f"  Success: {stats['success']}")
                print(f"  Skipped: {stats['skipped']}")
                print(f"  Failed:  {stats['failed']}")
        
        print("=" * 60)


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
    
    print("=" * 60)
    print("Universal File to JSON Converter")
    print("=" * 60)
    print(f"Supported: PDF, Code (.c, .py, .java, etc.), Text (.txt, .md, etc.)")
    if not args.no_clean:
        print("🧹 Text cleaning: ENABLED")
    print("=" * 60)
    
    # Si force, supprimer le target_dir
    if args.force:
        import shutil
        target_path = Path(args.target)
        if target_path.exists():
            print(f"🗑️  Removing {target_path} for fresh conversion...")
            shutil.rmtree(target_path)
    
    converter = UniversalConverter(args.source, args.target, clean_text=not args.no_clean)
    converter.convert_all()


if __name__ == "__main__":
    main()
