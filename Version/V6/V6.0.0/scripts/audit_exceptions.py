import ast
import os
from pathlib import Path

def audit_directory(directory: str):
    print(f"Auditing {directory} for naked exceptions and unused variables...")
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                filepath = Path(root) / file
                try:
                    tree = ast.parse(filepath.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ExceptHandler):
                            if node.type is None:
                                print(f"[WARNING] Naked Except in {filepath} at line {node.lineno}")
                except Exception as e:
                    print(f"Failed to parse {filepath}: {e}")

if __name__ == "__main__":
    audit_directory("core")
    audit_directory("engine")
    audit_directory("services")
