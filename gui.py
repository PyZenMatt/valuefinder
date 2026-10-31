import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw

from image_processing import load_grayscale_image, posterize_image, calculate_histogram
from mask_tools import create_polygon_mask, replace_background
from cutout_tools import generate_cutout_phases, export_cutout_phases

# ── Zoom levels available in the main canvas ──────────────────────────────────
ZOOM_LEVELS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
_DEFAULT_ZOOM_IDX = 3   # 100 %
_HIT_RADIUS = 10        # screen-pixel radius for vertex hit-detection


class ValueStudyApp(tk.Tk):
    """
    GIMP-style workspace layout:

        ┌─────────────────────────────────────────────────┐
        │  Top bar: Load · Save · View mode · Tonal vals  │
        ├──────────┬──────────────────────────────────────┤
        │ Sidebar  │  Main canvas (zoomable, scrollable)  │
        │ • tools  │  image + polygon overlay             │
        │ • zoom   │                                      │
        │ • bg     │                                      │
        ├──────────┴──────────────────────────────────────┤
        │  Bottom: histogram + tonal threshold sliders    │
        └─────────────────────────────────────────────────┘

    Polygon coordinates are stored exclusively in original image space.
    Screen coords are derived on the fly:  screen = image * zoom.
    """

    def __init__(self):
        super().__init__()
        self.title("Value Study Tool")
        self.geometry("1280x820")
        self.minsize(800, 550)

        # ── image / posterization ──────────────────────────────────────────
        self.original_image    = None
        self.image_path        = None
        self.histogram_data    = None
        self._posterized_image = None

        # ── tonal controls ─────────────────────────────────────────────────
        self.levels_count     = tk.IntVar(value=3)
        self.threshold_vars   = []
        self.background_value = tk.IntVar(value=220)

        # ── selection (all coords in original image space) ─────────────────
        self.subject_polygon_points = []
        self.selection_closed       = False
        self._drag_idx              = None
        self._last_press_added_point = False

        # ── canvas / view state ────────────────────────────────────────────
        self.view_mode    = tk.StringVar(value="original")
        self.current_tool = tk.StringVar(value="select")
        self._zoom_idx    = _DEFAULT_ZOOM_IDX
        self._zoom        = ZOOM_LEVELS[self._zoom_idx]
        self._tk_image    = None   # strong reference — prevents GC
        self._update_job  = None   # debounce handle

        self._build_ui()

    # ─────────────────────────────────────────────────── UI construction ──

    def _build_ui(self):
        self._build_topbar()

        content = tk.Frame(self)
        content.pack(fill=tk.BOTH, expand=True)

        self._build_sidebar(content)

        right = tk.Frame(content)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Build bottom panel before canvas so canvas gets the remaining space.
        self._build_bottom_panel(right)
        self._build_canvas(right)

    # ── Top bar ──────────────────────────────────────────────────────────

    def _build_topbar(self):
        bar = tk.Frame(self, bd=1, relief=tk.RAISED)
        bar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(bar, text="Carica immagine", command=self.load_image).pack(
            side=tk.LEFT, padx=5, pady=3)
        tk.Button(bar, text="Salva immagine", command=self.save_image).pack(
            side=tk.LEFT, padx=5, pady=3)

        tk.Button(
    bar,
    text="Esporta Cut Out",
    command=self.export_cutout,
).pack(side=tk.LEFT, padx=5, pady=3)

        _sep(bar)

        tk.Label(bar, text="Vista:").pack(side=tk.LEFT, padx=(0, 2))
        for text, val in [("Originale", "original"),
                          ("Posterizzata", "posterized"),
                          ("Finale", "final")]:
            tk.Radiobutton(
                bar, text=text,
                variable=self.view_mode, value=val,
                command=self._schedule_canvas_update,
            ).pack(side=tk.LEFT, padx=2)

        _sep(bar)

        tk.Label(bar, text="Valori tonali:").pack(side=tk.LEFT, padx=(0, 2))
        for v in [2, 3, 4, 5]:
            tk.Radiobutton(
                bar, text=str(v),
                variable=self.levels_count, value=v,
                command=self._on_levels_changed,
            ).pack(side=tk.LEFT, padx=2)

    # ── Left sidebar ─────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, width=215, bd=1, relief=tk.RAISED)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        sb.pack_propagate(False)

        kw = dict(padx=8, pady=2, fill=tk.X)   # common pack kwargs

        # ── Tool mode ──
        _section(sb, "Strumento")
        for text, val in [("✏  Aggiungi punto", "select"),
                          ("↔  Sposta vertici",  "move")]:
            tk.Radiobutton(
                sb, text=text,
                variable=self.current_tool, value=val,
                indicatoron=False, anchor=tk.W, width=19,
            ).pack(**kw)

        # ── Selection actions ──
        _section(sb, "Selezione")
        tk.Button(sb, text="Chiudi selezione", command=self.close_selection).pack(**kw)
        tk.Button(sb, text="Annulla ultimo",   command=self.undo_last_point).pack(**kw)
        tk.Button(sb, text="Reset selezione",  command=self.reset_selection).pack(**kw)

        # ── Zoom ──
        _section(sb, "Zoom")
        zrow = tk.Frame(sb)
        zrow.pack(**kw)
        tk.Button(zrow, text="-", width=3, command=self._zoom_out).pack(side=tk.LEFT)
        self._zoom_lbl = tk.Label(zrow, text="100%", width=5)
        self._zoom_lbl.pack(side=tk.LEFT, padx=4)
        tk.Button(zrow, text="+", width=3, command=self._zoom_in).pack(side=tk.LEFT)
        tk.Button(sb, text="Adatta alla finestra", command=self._fit_to_window).pack(**kw)

        # ── Background ──
        _section(sb, "Sfondo")
        grid = tk.Frame(sb)
        grid.pack(padx=8, pady=2)
        presets = [("Bianco 255", 255), ("Chiaro 220", 220),
                   ("Grigio 128", 128), ("Nero    0",   0)]
        for i, (label, val) in enumerate(presets):
            tk.Button(
                grid, text=label, width=10,
                command=lambda v=val: self._set_background(v),
            ).grid(row=i // 2, column=i % 2, padx=1, pady=1, sticky=tk.EW)

        tk.Scale(
            sb, from_=0, to=255,
            orient=tk.HORIZONTAL,
            variable=self.background_value,
            command=lambda _: self._schedule_canvas_update(),
            showvalue=True,
        ).pack(padx=8, pady=(2, 6), fill=tk.X)

    # ── Bottom panel ─────────────────────────────────────────────────────

    def _build_bottom_panel(self, parent):
        bottom = tk.Frame(parent, bd=1, relief=tk.GROOVE)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        self.histogram_canvas = tk.Canvas(bottom, height=80, bg="white")
        self.histogram_canvas.pack(fill=tk.X, padx=6, pady=(4, 0))

        self.sliders_frame = tk.Frame(bottom)
        self.sliders_frame.pack(fill=tk.X, padx=6, pady=(2, 6))

        self._rebuild_sliders_ui()

    # ── Main canvas ──────────────────────────────────────────────────────

    def _build_canvas(self, parent):
        cf = tk.Frame(parent)
        cf.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(cf, bg="#404040", cursor="crosshair")
        hbar = tk.Scrollbar(cf, orient=tk.HORIZONTAL, command=self._canvas.xview)
        vbar = tk.Scrollbar(cf, orient=tk.VERTICAL,   command=self._canvas.yview)
        self._canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        vbar.pack(side=tk.RIGHT,  fill=tk.Y)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",        self._on_drag)
        self._canvas.bind("<ButtonRelease-1>",  self._on_release)
        self._canvas.bind("<Double-Button-1>",  self._on_double_click)
        self._canvas.bind("<Motion>",           self._on_motion)

    # ─────────────────────────────────────────────────── Tonal sliders ──

    def _rebuild_sliders_ui(self):
        for w in self.sliders_frame.winfo_children():
            w.destroy()

        self.threshold_vars = []
        levels   = self.levels_count.get()
        defaults = [int(255 * (i + 1) / levels) for i in range(levels - 1)]

        for i, default in enumerate(defaults):
            var = tk.IntVar(value=default)
            self.threshold_vars.append(var)

            row = tk.Frame(self.sliders_frame)
            row.pack(fill=tk.X, pady=1)

            tk.Label(row, text=f"Soglia {i + 1}", width=10).pack(side=tk.LEFT)
            tk.Scale(
                row, from_=0, to=255,
                orient=tk.HORIZONTAL,
                variable=var,
                command=lambda _: self._on_thresholds_changed(),
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._on_thresholds_changed()

    # ─────────────────────────────────────────────────── Image loading ──

    def load_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("Immagini", "*.jpg *.jpeg *.png *.bmp *.webp"),
                       ("Tutti i file", "*.*")]
        )
        if not path:
            return

        self.image_path        = path
        self.original_image    = load_grayscale_image(path)
        self.histogram_data    = calculate_histogram(self.original_image)
        self._posterized_image = None

        self.reset_selection()          # clears polygon, schedules canvas update
        self._on_thresholds_changed()   # (re)builds posterized + histogram
        self.after(60, self._fit_to_window)

    # ──────────────────────────────────────────────────── Posterization ──

    def _on_levels_changed(self):
        """Called when the tonal-level radio buttons change."""
        self._rebuild_sliders_ui()   # also triggers _on_thresholds_changed

    def _on_thresholds_changed(self):
        """Recompute posterized image and refresh the display."""
        if self.original_image is None:
            return
        thresholds = [v.get() for v in self.threshold_vars]
        self._posterized_image = posterize_image(
            self.original_image, thresholds, self.levels_count.get()
        )
        self._draw_histogram()
        self._schedule_canvas_update()

    # ──────────────────────────────────────────────── Canvas rendering ──

    def _render_canvas(self, resample=Image.LANCZOS):
        """
        Build and display the current frame.

        Pipeline
        --------
        1. Select source image (original or posterized).
        2. Scale to display size (zoom x original size) using `resample`.
        3. In 'final' view with >=3 points: apply background replacement
           at display scale — mask creation and numpy ops stay small.
        4. Draw polygon overlay on top.
        5. Push to canvas.
        """
        if self.original_image is None:
            self._canvas.delete("all")
            return

        z      = self._zoom
        iw, ih = self.original_image.size
        sw     = max(1, int(iw * z))
        sh     = max(1, int(ih * z))

        mode = self.view_mode.get()
        src  = self._posterized_image if mode != "original" else self.original_image
        if src is None:
            src = self.original_image

        scaled = src.resize((sw, sh), resample)

        # Pre-compute polygon in screen space
        spts = [(int(x * z), int(y * z)) for x, y in self.subject_polygon_points]

        # Background replacement (final view, >=3 points — live preview)
        if mode == "final" and len(spts) >= 3:
            mask   = create_polygon_mask((sw, sh), spts)
            scaled = replace_background(scaled, mask, self.background_value.get())

        # Polygon overlay (all view modes)
        if spts:
            draw = ImageDraw.Draw(scaled)
            if len(spts) >= 2:
                draw.line(spts, fill=255, width=2)
            if self.selection_closed and len(spts) >= 3:
                draw.line([spts[-1], spts[0]], fill=255, width=2)
            for i, (sx, sy) in enumerate(spts):
                r     = 5
                shade = 160 if i == self._drag_idx else 255
                draw.ellipse((sx - r, sy - r, sx + r, sy + r), fill=shade, outline=0)

        self._tk_image = ImageTk.PhotoImage(scaled)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self._tk_image)
        self._canvas.configure(scrollregion=(0, 0, sw, sh))

    def _schedule_canvas_update(self):
        """Debounced canvas refresh (35 ms)."""
        if self._update_job is not None:
            self.after_cancel(self._update_job)
        self._update_job = self.after(35, self._render_canvas)

    # ────────────────────────────────────────────────────────── Zoom ──

    def _zoom_in(self):
        if self._zoom_idx < len(ZOOM_LEVELS) - 1:
            self._zoom_idx += 1
            self._apply_zoom()

    def _zoom_out(self):
        if self._zoom_idx > 0:
            self._zoom_idx -= 1
            self._apply_zoom()

    def _apply_zoom(self):
        self._zoom = ZOOM_LEVELS[self._zoom_idx]
        self._zoom_lbl.configure(text=f"{int(self._zoom * 100)}%")
        self._schedule_canvas_update()

    def _fit_to_window(self):
        if self.original_image is None:
            return
        self.update_idletasks()
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            self.after(50, self._fit_to_window)
            return
        iw, ih = self.original_image.size
        target = min(cw / iw, ch / ih)
        best = min(range(len(ZOOM_LEVELS)), key=lambda i: abs(ZOOM_LEVELS[i] - target))
        self._zoom_idx = best
        self._apply_zoom()

    # ──────────────────────────────────── Hit-detection & coordinates ──

    def _canvas_to_image(self, ex: int, ey: int) -> tuple:
        """Convert a canvas widget event position to image coordinates."""
        cx = self._canvas.canvasx(ex)
        cy = self._canvas.canvasy(ey)
        iw, ih = self.original_image.size
        return (
            max(0, min(iw - 1, int(round(cx / self._zoom)))),
            max(0, min(ih - 1, int(round(cy / self._zoom)))),
        )

    def _find_hit(self, cx, cy):
        """Return index of the first vertex within _HIT_RADIUS of (cx, cy)."""
        z = self._zoom
        for i, (ix, iy) in enumerate(self.subject_polygon_points):
            if abs(cx - ix * z) <= _HIT_RADIUS and abs(cy - iy * z) <= _HIT_RADIUS:
                return i
        return None

    # ──────────────────────────────────────────── Mouse event handlers ──

    def _on_press(self, event):
        if self.original_image is None:
            return
        cx  = self._canvas.canvasx(event.x)
        cy  = self._canvas.canvasy(event.y)
        hit = self._find_hit(cx, cy)

        if hit is not None:
            # Drag an existing vertex (works in both tool modes)
            self._drag_idx = hit
            self._last_press_added_point = False
            self._render_canvas()
        elif self.current_tool.get() == "select" and not self.selection_closed:
            # Add a new vertex
            self.subject_polygon_points.append(self._canvas_to_image(event.x, event.y))
            self._last_press_added_point = True
            self._render_canvas()
        else:
            self._last_press_added_point = False

    def _on_drag(self, event):
        if self._drag_idx is None:
            return
        self.subject_polygon_points[self._drag_idx] = self._canvas_to_image(event.x, event.y)
        # BILINEAR is faster during interactive drag; quality restored on release
        self._render_canvas(resample=Image.BILINEAR)

    def _on_release(self, event):
        if self._drag_idx is not None:
            self._drag_idx = None
            self._render_canvas()   # final-quality render after drag

    def _on_double_click(self, event):
        if self.selection_closed or self.current_tool.get() != "select":
            return
        # The second Button-1 event may have added a duplicate point; remove it.
        if self._last_press_added_point and self.subject_polygon_points:
            self.subject_polygon_points.pop()
            self._last_press_added_point = False
        self.close_selection()

    def _on_motion(self, event):
        cx     = self._canvas.canvasx(event.x)
        cy     = self._canvas.canvasy(event.y)
        cursor = "fleur" if self._find_hit(cx, cy) is not None else "crosshair"
        self._canvas.configure(cursor=cursor)

    # ─────────────────────────────────────── Selection action methods ──

    def close_selection(self):
        if len(self.subject_polygon_points) < 3:
            messagebox.showwarning(
                "Selezione incompleta",
                "Servono almeno 3 punti per creare una selezione.",
            )
            return
        self.selection_closed = True
        self._render_canvas()

    def undo_last_point(self):
        if self.subject_polygon_points:
            self.subject_polygon_points.pop()
            self.selection_closed = False
            self._render_canvas()

    def reset_selection(self):
        self.subject_polygon_points = []
        self.selection_closed = False
        self._drag_idx = None
        self._schedule_canvas_update()

    def _set_background(self, value: int):
        self.background_value.set(value)
        self._schedule_canvas_update()

    # ──────────────────────────────────────────────────── Histogram ──

    def _draw_histogram(self):
        if self.histogram_data is None:
            return
        self.histogram_canvas.delete("all")
        hist = self.histogram_data
        cw   = self.histogram_canvas.winfo_width()
        ch   = self.histogram_canvas.winfo_height()
        if cw <= 1:
            self.after(100, self._draw_histogram)
            return
        max_val = max(hist)
        if max_val == 0:
            return
        bw = cw / 256
        for i, count in enumerate(hist):
            x1 = i * bw
            bh = (count / max_val) * ch
            self.histogram_canvas.create_rectangle(
                x1, ch - bh, x1 + bw, ch, fill="gray", outline="")
        for var in self.threshold_vars:
            x = (var.get() / 255) * cw
            self.histogram_canvas.create_line(x, 0, x, ch, fill="red", width=2)

    # ─────────────────────────────────────────────────── Save image ──

    def save_image(self):
        if self.original_image is None:
            messagebox.showwarning("Nessuna immagine", "Carica prima un'immagine.")
            return

        output_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
        )
        if not output_path:
            return

        # Always posterize at full resolution
        thresholds = [v.get() for v in self.threshold_vars]
        result = posterize_image(
            self.original_image, thresholds, self.levels_count.get()
        )

        # Apply background mask at full resolution when a closed selection exists
        if self.selection_closed and len(self.subject_polygon_points) >= 3:
            mask   = create_polygon_mask(self.original_image.size, self.subject_polygon_points)
            result = replace_background(result, mask, self.background_value.get())

        result.save(output_path)
        messagebox.showinfo("Salvata", f"Immagine salvata correttamente in {output_path}.")

    def export_cutout(self):
        if self.original_image is None:
            messagebox.showwarning(
                "Nessuna immagine",
                "Carica prima un'immagine.",
            )
            return

        output_dir = filedialog.askdirectory(
            title="Scegli la cartella di esportazione Cut Out"
        )

        if not output_dir:
            return

        thresholds = [var.get() for var in self.threshold_vars]
        background_mask = None

        if self.selection_closed and len(self.subject_polygon_points) >= 3:
            background_mask = create_polygon_mask(
                self.original_image.size,
                self.subject_polygon_points,
            )

        try:
            phases = generate_cutout_phases(
                image=self.original_image,
                thresholds=thresholds,
                levels_count=self.levels_count.get(),
                background_mask=background_mask,
                background_value=self.background_value.get(),
            )

            if not phases:
                messagebox.showwarning(
                    "Nessuna fase",
                    "Non sono stati trovati toni da esportare.",
                )
                return

            saved_files = export_cutout_phases(phases, output_dir)

            messagebox.showinfo(
                "Esportazione completata",
                f"Esportate {len(phases)} fasi cumulative e "
                f"{len(phases)} maschere isolate.\n\n"
                f"File creati: {len(saved_files)}\n"
                f"Cartella: {output_dir}",
            )

        except (ValueError, OSError) as exc:
            messagebox.showerror(
                "Errore durante l'esportazione",
                str(exc),
            )
# ──────────────────────────────────────────────────── Layout helpers ──

def _sep(parent):
    """Vertical separator for the top toolbar."""
    tk.Frame(parent, width=2, bg="#aaaaaa").pack(
        side=tk.LEFT, fill=tk.Y, padx=8, pady=4)


def _section(parent, title: str):
    """Bold section label inside the sidebar."""
    tk.Label(parent, text=title, font=("", 9, "bold")).pack(
        padx=8, pady=(10, 3), anchor=tk.W)
