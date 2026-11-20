import sys
from pathlib import Path
ORCHESTRATOR_ROOT = Path(__file__).resolve().parent.parent
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))
from homi_speak_chunking import chunk_text, verify_no_loss

def test_basic():
    text = "Dale, ya lo agregué a la lista. ¿Querés que te avise mañana? Che, ojo, todavía falta pagar la luz."
    chunks = chunk_text(text)
    assert len(chunks) == 3
    assert verify_no_loss(text, chunks)

def test_empty():
    assert chunk_text("") == []

def test_single():
    chunks = chunk_text("Hola.")
    assert len(chunks) == 1
    assert chunks[0].is_final

def test_ids():
    chunks = chunk_text("Esta es la primera oración completa. Esta es la segunda oración completa.")
    assert chunks[0].chunk_id == "chunk_001"
    assert chunks[1].chunk_id == "chunk_002"
