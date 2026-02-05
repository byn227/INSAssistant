import json
import re
from pathlib import Path
from typing import Any
from tqdm import tqdm

class TextCleaner:    
    def __init__(self):
        # Common OCR/encoding fixes for French
        self.replacements = {
            # Accented characters broken by OCR with special symbols
            "´e": "é",
            "´E": "É",
            "`e": "è",
            "`E": "È",
            "^e": "ê",
            "^E": "Ê",
            "¨e": "ë",
            "¨E": "Ë",
            
            "´a": "á",
            "`a": "à",
            "^a": "â",
            "´A": "Á",
            "`A": "À",
            "^A": "Â",
            
            "´o": "ó",
            "`o": "ò",
            "^o": "ô",
            "´O": "Ó",
            "`O": "Ò",
            "^O": "Ô",
            
            "´i": "í",
            "`i": "ì",
            "^i": "î",
            "¨i": "ï",
            
            "´u": "ú",
            "`u": "ù",
            "^u": "û",
            "¨u": "ü",
            
            # Alternative patterns with space
            "r´ e": "ré",
            "R´ e": "Ré",
            "´ e": "é",
            "` e": "è",
            "^ e": "ê",
            "¨ e": "ë",
            "´ a": "á",
            "` a": "à",
            "^ a": "â",
            "´ o": "ó",
            "` o": "ò",
            "^ o": "ô",
            "´ i": "í",
            "` i": "ì",
            "^ i": "î",
            "¨ i": "ï",
            "´ u": "ú",
            "` u": "ù",
            "^ u": "û",
            "¨ u": "ü",
            
            # Capital with space
            "´ E": "É",
            "` E": "È",
            "^ E": "Ê",
            "´ A": "Á",
            "` A": "À",
            "^ A": "Â",
            "´ O": "Ó",
            "` O": "Ò",
            "^ O": "Ô",
            
            # Special cases for qu'
            "qù": "qu'",
            "Qù": "Qu'",
            "qù": "qu'",  # Different unicode
            "Qù": "Qu'",
            
            # Broken patterns (common in OCR)
            "e'": "é",
            "E'": "É", 
            "a'": "à",
            "A'": "À",
            # Skip u' and U' - handled in patterns to avoid qu'un → qùun
            "o^": "ô",
            "O^": "Ô",
            "a^": "â",
            "A^": "Â",
            "e^": "ê",
            "E^": "Ê",
            "i^": "î",
            "I^": "Î",
            "u^": "û",
            "U^": "Û",
            
            "e`": "è",
            "E`": "È",
            
            # LaTeX/Math encoding issues
            "ˆo": "ô",
            "ˆO": "Ô",
            "ˆe": "ê",
            "ˆE": "Ê",
            "ˆa": "â",
            "ˆA": "Â",
            "ˆi": "î",
            "ˆI": "Î",
            "ˆu": "û",
            "ˆU": "Û",
            " ˆo": " ô",
            " ˆe": " ê",
            " ˆa": " â",
            
            # More LaTeX patterns
            "´e": "é",
            "`e": "è",
            "¨e": "ë",
            "´a": "à",
            "¨i": "ï",
            "¨u": "ü",
            
            # Common ligatures
            "oe": "œ",
            "OE": "Œ",
            "ﬁ": "fi",
            "ﬂ": "fl",
            
            # Math/special characters that should be removed or normalized
            "¸c": "ç",
            "¸C": "Ç",
            
            # Smart quotes to regular quotes
            "'": "'",
            "'": "'",
            """: '"',
            """: '"',
            "«": '"',
            "»": '"',
        }
        
        # Common broken words (OCR errors)
        # Pattern: broken word → correct word (use \s+ for flexible space matching)
        self.word_fixes = {
            # Technical terms with spaces inside
            r"\bSyst\s+eme\b": "Système",
            r"\bsyst\s+eme\b": "système",
            r"\bSyst\s+emes\b": "Systèmes",
            r"\bsyst\s+emes\b": "systèmes",
            
            r"\bprobl\s+eme\b": "problème",
            r"\bProbl\s+eme\b": "Problème",
            r"\bprobl\s+emes\b": "problèmes",
            
            r"\balgorith\s+me\b": "algorithme",
            r"\bAlgorith\s+me\b": "Algorithme",
            
            r"\bcompl\s+exit\s+e\b": "complexité",
            r"\bCompl\s+exit\s+e\b": "Complexité",
            
            r"\bd\s+efinition\b": "définition",
            r"\bD\s+efinition\b": "Définition",
            r"\bd\s+eﬁnition\b": "définition",  # LaTeX fi ligature
            r"\bD\s+eﬁnition\b": "Définition",
            r"\bd\s+eﬁnir\b": "définir",
            r"\bd\s+eﬁni\b": "défini",
            
            r"\bmod\s+ele\b": "modèle",
            r"\bMod\s+ele\b": "Modèle",
            r"\bmod\s+eles\b": "modèles",
            
            r"\bth\s+eor\s+eme\b": "théorème",
            r"\bTh\s+eor\s+eme\b": "Théorème",
            r"\bth\s+eorème\b": "théorème",  # Already has accent but spacing
            r"\bTh\s+eorème\b": "Théorème",
            
            r"\bm\s+ethode\b": "méthode",
            r"\bM\s+ethode\b": "Méthode",
            
            r"\br\s+eseau\b": "réseau",
            r"\bR\s+eseau\b": "Réseau",
            r"\br\s+eseaux\b": "réseaux",
            
            r"\bdon\s+nees\b": "données",
            r"\bDon\s+nees\b": "Données",
            
            r"\belec\s+tronique\b": "électronique",
            r"\bElec\s+tronique\b": "Électronique",
            
            r"\bpro\s+cedure\b": "procédure",
            r"\bPro\s+cedure\b": "Procédure",
            
            r"\bfon\s+ction\b": "fonction",
            r"\bFon\s+ction\b": "Fonction",
            
            r"\bex\s+ecution\b": "exécution",
            r"\bEx\s+ecution\b": "Exécution",
            
            # LaTeX-specific patterns
            r"\bcontr\s+ˆole\b": "contrôle",
            r"\bContr\s+ˆole\b": "Contrôle",
            r"\bcontr\s+ole\b": "contrôle",
            r"\bContr\s+ole\b": "Contrôle",
            
            r"\b([a-z]+)\s+eﬁ": r"\1éfi",  # Generic "éfi" fix
            r"\b([a-z]+)\s+ﬁ": r"\1fi",     # Generic "fi" ligature
        }
        
        # Missing accent corrections (whole word matching, case-sensitive)
        self.missing_accents = {
            r"\breseau(x?)\b": r"réseau\1",
            r"\bReseau(x?)\b": r"Réseau\1",
            r"\bmodele(s?)\b": r"modèle\1",
            r"\bModele(s?)\b": r"Modèle\1",
            r"\bsysteme(s?)\b": r"système\1",
            r"\bSysteme(s?)\b": r"Système\1",
            r"\betudiant(s?|e|es)\b": r"étudiant\1",
            r"\bEtudiant(s?|e|es)\b": r"Étudiant\1",
            r"\belectronique(s?)\b": r"électronique\1",
            r"\bElectronique(s?)\b": r"Électronique\1",
            r"\btelecommunication(s?)\b": r"télécommunication\1",
            r"\bTelecommunication(s?)\b": r"Télécommunication\1",
            r"\bgeneral(e|es|aux)?\b": r"général\1",
            r"\bGeneral(e|es|aux)?\b": r"Général\1",
            r"\bevolution(s?)\b": r"évolution\1",
            r"\bEvolution(s?)\b": r"Évolution\1",
            r"\betat(s?)\b": r"état\1",
            r"\bEtat(s?)\b": r"État\1",
            r"\betape(s?)\b": r"étape\1",
            r"\bEtape(s?)\b": r"Étape\1",
            r"\bequipe(s?)\b": r"équipe\1",
            r"\bEquipe(s?)\b": r"Équipe\1",
            r"\bequation(s?)\b": r"équation\1",
            r"\bEquation(s?)\b": r"Équation\1",
            r"\benergie(s?)\b": r"énergie\1",
            r"\bEnergie(s?)\b": r"Énergie\1",
        }
        
        # Patterns to fix (order matters!)
        self.patterns = [
            # Fix numbered lists: "1Plan" → "1. Plan"
            (r'\n(\d+)([A-Z])', r'\n\1. \2'),
            
            # Remove page numbers: "2/41 " at end
            (r'\s*\d+/\d+\s*$', '', re.MULTILINE),
            (r'\s*\d+/\d+\s+', ' '),
            
            # Fix broken apostrophes - but NOT for qu'
            (r"([^qu])'\s+e\b", r"\1è"),      # Don't match qu'e
            (r"([^qu])'\s+a\b", r"\1à"),
            (r"Mod`\s*ele\b", "Modèle"),  # Special case
            
            # Fix broken accents at word start: "D' efinition" → "Définition"
            (r"\b([AEIOU])'\s+e", r"\1é"),
            (r"\b([AEIOU])'\s+a", r"\1à"),
            (r"D´\s*e", "Dé"),  # Special case
            
            # Remove space after apostrophes (L', D', etc) - but keep space after word
            (r"([LlDdNnMmTtSsCcJj])'\s+(?=[a-zàâäéèêëïîôùûüÿœæç])", r"\1'"),
            
            # Multiple spaces → single space (do BEFORE other patterns)
            (r" {2,}", r" "),
            
            # Multiple newlines → max 2
            (r"\n{3,}", r"\n\n"),
            
            # Remove space before punctuation (but not between words)
            (r" +([.,;!?:])", r"\1"),
            
            # Add space after punctuation if missing (except at end)
            (r"([.,;!?:])([A-ZÀ-ÿ])", r"\1 \2"),
            
            # Remove trailing/leading whitespace per line
            (r"[ \t]+$", r"", re.MULTILINE),
            (r"^[ \t]+", r"", re.MULTILINE),
        ]
    
    def clean_text(self, text: str) -> str:
        """Clean a single text string"""
        if not text or not isinstance(text, str):
            return text
        
        #Apply character replacements
        for old, new in self.replacements.items():
            text = text.replace(old, new)
        
        #Fix broken words (intelligent correction)
        for pattern, replacement in self.word_fixes.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        #Fix missing accents in common French words
        for pattern, replacement in self.missing_accents.items():
            text = re.sub(pattern, replacement, text)
        
        #Apply regex patterns
        for item in self.patterns:
            if len(item) == 3:
                pattern, replacement, flags = item
                text = re.sub(pattern, replacement, text, flags=flags)
            else:
                pattern, replacement = item
                text = re.sub(pattern, replacement, text)
        
        # Remove control characters (except newline, tab)
        text = ''.join(char for char in text 
                      if char in '\n\t\r' or ord(char) >= 32)
        
        # Normalize Unicode
        text = text.replace('\xa0', ' ')  # Non-breaking space
        text = text.replace('\u200b', '')  # Zero-width space
        text = text.replace('\ufeff', '')  # BOM
        
        # Final cleanup
        text = text.strip()
        
        return text
    
    def clean_json_recursive(self, obj: Any) -> Any:
        """Recursively clean all text in JSON structure"""
        if isinstance(obj, str):
            return self.clean_text(obj)
        
        elif isinstance(obj, dict):
            return {key: self.clean_json_recursive(value) 
                   for key, value in obj.items()}
        
        elif isinstance(obj, list):
            return [self.clean_json_recursive(item) for item in obj]
        
        else:
            return obj
    
    def process_file(self, json_path: Path) -> tuple[bool, str]:
        """Process single JSON file (in-place)"""
        try:
            # Read
            with open(json_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if file is too small (likely corrupted/truncated)
            if len(content) < 100:
                return False, "File too small (truncated)"
            
            # Try to parse
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                # Try to fix common JSON issues
                content_fixed = content.strip()
                if not content_fixed.endswith('}') and not content_fixed.endswith(']'):
                    # File truncated, cannot fix
                    return False, f"Truncated JSON: {e}"
                return False, f"Invalid JSON: {e}"
            
            # Clean
            cleaned = self.clean_json_recursive(data)
            
            # Write back
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cleaned, f, ensure_ascii=False, indent=2)
            
            return True, "success"
            
        except Exception as e:
            return False, f"Error: {e}"
    
    def process_directory(self, dir_path: Path):
        """Process all JSON files in directory"""
        print("🧹 JSON Text Cleaner")
        print("=" * 80)
        print(f"Directory: {dir_path}")
        
        # Find JSON files
        json_files = list(dir_path.rglob("*.json"))
        json_files = [f for f in json_files 
                     if f.name not in ['conversion_report.json', 
                                      'missing_conversions.json',
                                      'training_data_pages.json',
                                      'training_data_from_json.json']]
        
        print(f"Found: {len(json_files)} JSON files\n")
        
        stats = {
            "success": 0,
            "failed": 0,
            "errors": []
        }
        
        for json_file in tqdm(json_files, desc="Cleaning"):
            success, msg = self.process_file(json_file)
            
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1
                stats["errors"].append({
                    "file": str(json_file.relative_to(dir_path)),
                    "error": msg
                })
        
        print("\n" + "=" * 80)
        print("✅ Cleaning completed!")
        print(f"   Success: {stats['success']}")
        print(f"   Failed: {stats['failed']}")
        
        if stats["errors"][:5]:  # Show first 5 errors
            print(f"\n❌ Errors (showing {min(5, len(stats['errors']))}):")
            for err in stats["errors"][:5]:
                print(f"   - {err['file']}: {err['error']}")
        
        print("=" * 80)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean text in JSON files")
    parser.add_argument('--dir', default='../Data_json', 
                       help='Directory containing JSON files')
    parser.add_argument('--test', action='store_true',
                       help='Test mode: show samples without writing')
    
    args = parser.parse_args()
    
    if args.test:
        # Test mode: show what would be cleaned
        cleaner = TextCleaner()
        test_texts = [
            "Outline\n1Plan du Cours\n2Qu'est-ce qu'un r´ eseau?\n3Le Mod` ele OSI\n4Adresses sur le r´ eseau\n5Encapsulage/D´ ecapsulage\n6Conclusion\n2/41 Adrien Boiret - September 4, 2025",
            "Syst  eme d'exploitation",
            "Th  eor  eme de Python",
            "R  eseau TCP/IP et don  nees",
        ]
        print("🧪 Test Mode\n")
        for text in test_texts:
            cleaned = cleaner.clean_text(text)
            print(f"Before: {text}")
            print(f"After:  {cleaned}\n")
    else:
        cleaner = TextCleaner()
        cleaner.process_directory(Path(args.dir))


if __name__ == "__main__":
    main()
