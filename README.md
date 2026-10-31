# ValueFinder

ValueFinder è un'applicazione desktop Python progettata per supportare la pratica artistica visiva tradizionale. Aiuta gli artisti ad analizzare, semplificare e riprodurre le strutture tonali delle immagini di riferimento.

## Funzionalità Principali
- Caricamento immagini in scala di grigi e RGB.
- Posterizzazione per lo studio dei valori tonali.
- Posterizzazione RGB selezionabile dalla sezione Colore, con fusione luminanza opzionale.
- Generazione di maschere Cut Out progressive per la pittura a strati.
- Esportazione in alta risoluzione.

## Requisiti
- Python 3.10+
- Tkinter (incluso in Python)
- Dipendenze elencate in `requirements.txt`

## Installazione e Avvio
1. Creare un virtual environment: `python -m venv venv`
2. Attivarlo: `source venv/bin/activate` (Linux/Mac) o `venv\Scripts\activate` (Windows)
3. Installare le dipendenze: `pip install -r requirements.txt`
4. Avviare l'app: `python main.py`
