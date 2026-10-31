from pathlib import Path
import numpy as np
from PIL import Image

# Colore blu scuro, identico a quello di Da Vinci Eye
DAVINCI_BLUE = (15, 15, 180) 
WHITE = (255, 255, 255)

def clean_mask_numpy(mask):
    """
    Pulisce una maschera booleana da pixel isolati e buchi,
    mantenendo i bordi estremamente netti e affilati (sharp).
    """
    m = mask.astype(np.uint8)
    
    # Padding per gestire i bordi dell'immagine
    padded = np.pad(m, 1, mode='edge')
    neighbors = np.zeros_like(m, dtype=np.uint8)
    
    # Conteggio dei vicini (escluso il centro)
    for dy in [-1, 0, 1]:
        for dx in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            shifted = padded[1+dy:padded.shape[0]-1+dy, 1+dx:padded.shape[1]-1+dx]
            neighbors += shifted
            
    new_m = m.copy()
    # Rimuove i pixel bianchi isolati (meno di 2 vicini bianchi)
    new_m[(m == 1) & (neighbors < 2)] = 0
    # Chiude i buchi neri isolati (più di 5 vicini bianchi)
    new_m[(m == 0) & (neighbors > 5)] = 1
    
    return new_m.astype(bool)


def generate_cutout_phases(
    image: Image.Image,
    thresholds: list[int],
    levels_count: int,
    background_mask: Image.Image | None = None,
    background_value: int = 255,
) -> list[dict[str, Image.Image]]:
    
    # Usiamo l'immagine originale, nessun blur che ammorbidisce i bordi
    arr_img = np.asarray(image.convert("L"), dtype=np.uint8)

    # 1. MASCHERA SOGGETTO
    if background_mask is not None:
        subject_mask = np.asarray(background_mask.convert("L"), dtype=np.uint8) > 0
    else:
        # Esclude la carta bianca (soglia 250)
        subject_mask = arr_img < 250

    sorted_thresholds = sorted(thresholds, reverse=True)
    phases = []
    
    prev_pixel_count = -1
    total_pixels = arr_img.size

    # 2. COSTRUZIONE DELLE FASI
    for i in range(levels_count):
        if i == 0:
            tone_mask = subject_mask
        else:
            tone_mask = subject_mask & (arr_img <= sorted_thresholds[i - 1])

        # Pulizia chirurgica (Sharp Edges)
        tone_mask_clean = clean_mask_numpy(tone_mask)
        
        current_pixel_count = np.count_nonzero(tone_mask_clean)
        
        # SCARTA FASI INUTILI:
        # Se la fase ha meno dell'1% dei pixel totali, è una fase vuota (come i 2 puntini)
        if current_pixel_count / total_pixels < 0.01:
            continue
            
        # Se la fase è quasi identica alla precedente (differenza < 2%), saltala
        if prev_pixel_count != -1:
            diff = abs(prev_pixel_count - current_pixel_count)
            if diff / max(prev_pixel_count, 1) < 0.02:
                continue
                
        prev_pixel_count = current_pixel_count

        # 3. CREAZIONE DELLA MASCHERA RGB (Bianco e Blu Scuro)
        tone_img = Image.fromarray((tone_mask_clean * 255).astype(np.uint8))
        mask_rgb = Image.new("RGB", tone_img.size, WHITE)
        blu_solid = Image.new("RGB", tone_img.size, DAVINCI_BLUE)
        mask_rgb.paste(blu_solid, mask=tone_img)

        phases.append(
            {
                "mask": mask_rgb,
                "value": int(sorted_thresholds[i - 1]) if i > 0 else 255,
            }
        )

    return phases


def export_cutout_phases(
    phases: list[dict[str, Image.Image]],
    output_dir: str | Path,
) -> list[Path]:
    """
    Esporta solo le maschere isolate in PNG (Bianco/Blu).
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for index, phase in enumerate(phases, start=1):
        mask_path = output_path / f"fase_{index:02d}_maschera.png"
        
        phase["mask"].save(mask_path)
        saved_files.append(mask_path)

    return saved_files