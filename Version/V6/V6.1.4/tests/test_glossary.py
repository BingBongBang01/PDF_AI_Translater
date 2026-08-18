import os
import json
import yaml
import csv
import pytest
from pdf_engine.glossary.parser import GlossaryParser
from pdf_engine.placeholder.manager import PlaceholderManager

@pytest.fixture
def temp_glossary_files(tmp_path):
    # JSON Profile
    json_path = tmp_path / "glossary.json"
    json_path.write_text(json.dumps({
        "academic": {"Deep Research": "심층 연구"},
        "ui": {"Button": "버튼"}
    }, ensure_ascii=False), encoding="utf-8")
    
    # YAML Profile
    yaml_path = tmp_path / "glossary.yaml"
    yaml_path.write_text("""
technical:
  Backend: 백엔드
default:
  Frontend: 프론트엔드
    """, encoding="utf-8")

    # CSV Flat
    csv_path = tmp_path / "glossary.csv"
    with open(csv_path, 'w', encoding="utf-8", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["API", "응용 프로그래밍 인터페이스"])

    return json_path, yaml_path, csv_path

def test_json_profile(temp_glossary_files):
    json_path, _, _ = temp_glossary_files
    GlossaryParser.clear_cache()
    
    academic = GlossaryParser.load(str(json_path), "academic")
    assert academic["Deep Research"] == "심층 연구"
    assert "Button" not in academic

def test_yaml_profile(temp_glossary_files):
    _, yaml_path, _ = temp_glossary_files
    GlossaryParser.clear_cache()
    
    tech = GlossaryParser.load(str(yaml_path), "technical")
    assert tech["Backend"] == "백엔드"
    
    default = GlossaryParser.load(str(yaml_path), "default")
    assert default["Frontend"] == "프론트엔드"

def test_csv_flat(temp_glossary_files):
    _, _, csv_path = temp_glossary_files
    GlossaryParser.clear_cache()
    
    data = GlossaryParser.load(str(csv_path), "academic") # Profile doesn't matter for flat CSV
    assert data["API"] == "응용 프로그래밍 인터페이스"

def test_glossary_protection_integration():
    glossary_map = {"Deep Research": "심층 연구", "API": "에이피아이"}
    pm = PlaceholderManager(glossary_map=glossary_map)
    
    text = "We are releasing Deep Research and the new API today."
    protected = pm.protect(text)
    
    # Ensure glossaries are turned into GL tokens
    assert "⟦GL0⟧" in protected
    assert "⟦GL1⟧" in protected
    assert "Deep Research" not in protected
    
    # Restore translation
    # Simulate LLM translated the surrounding sentence
    translated = protected.replace("We are releasing", "우리는 출시한다").replace("and the new", "그리고 새로운").replace("today.", "오늘.")
    
    restored = pm.restore(translated)
    assert "우리는 출시한다 심층 연구 그리고 새로운 에이피아이 오늘." in restored
