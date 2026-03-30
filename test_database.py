import pytest
from pathlib import Path
import database as db

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Setup iniziale: devia il db su un file temporaneo sicuro gestito da pytest."""
    # Salviamo il percorso originale per sicurezza
    path_originale = db.DB_PATH
    
    # Deviamo sul database finto in una cartella temporanea univoca
    db.DB_PATH = tmp_path / "test_odontoiatria.db"
    db.init_db()
    
    yield # Qui vengono eseguiti i test
    
    # Pulizia finale: ripristina il path originale.
    # Non serve forzare l'eliminazione del file, pytest pulisce la cartella da solo!
    db.DB_PATH = path_originale

def test_paziente_crud():
    """Testa Creazione, Lettura e Ricerca di un paziente."""
    # 1. Creazione
    paz_id = db.inserisci_paziente(nome="Mario", cognome="Rossi", telefono="12345")
    assert paz_id is not None
    assert paz_id > 0

    # 2. Lettura esatta (con decrittografia automatica)
    paziente = db.get_paziente_by_id(paz_id)
    assert paziente is not None
    assert paziente["nome"] == "Mario"
    assert paziente["cognome"] == "Rossi"

    # 3. Ricerca
    risultati = db.cerca_pazienti("Rossi")
    assert len(risultati) == 1
    assert risultati[0]["id"] == paz_id

def test_salvataggio_foto_fallisce_senza_paziente(tmp_path):
    """Testa che il database blocchi l'inserimento di foto per pazienti inesistenti."""
    # Crea una finta immagine per superare il blocco "file non trovato"
    fake_img = tmp_path / "test.jpg"
    fake_img.write_text("fake")
    
    # Deve fallire perché il paziente 9999 non esiste (Foreign Key constraint)
    with pytest.raises(Exception):
        db.upload_foto(paziente_id=9999, sorgente_path=fake_img)