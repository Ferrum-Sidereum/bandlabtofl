"""Tkinter desktop front-end for the converter."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .pipeline import convert, find_template


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BL2FLP — BandLab to FL Studio")
        self.geometry("820x560")
        self.minsize(720, 500)
        self._queue: queue.Queue[str] = queue.Queue()

        self.revision = tk.StringVar()
        self.assets = tk.StringVar()
        self.output = tk.StringVar()
        self.template = tk.StringVar()
        self.positions = tk.StringVar(value="auto")
        self.make_midi = tk.BooleanVar(value=True)
        self.make_states = tk.BooleanVar(value=True)

        try:
            self.template.set(str(find_template()))
        except FileNotFoundError:
            pass

        self._build()
        self.after(120, self._drain)

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Revision JSON / ZIP").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.revision).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Browse…", command=self._pick_revision).grid(row=0, column=2)

        ttk.Label(frame, text="Assets folder").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.assets).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Browse…", command=self._pick_assets).grid(row=1, column=2)

        ttk.Label(frame, text="Output .flp").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.output).grid(row=2, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Save as…", command=self._pick_output).grid(row=2, column=2)

        ttk.Label(frame, text="FL template").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.template).grid(row=3, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Browse…", command=self._pick_template).grid(row=3, column=2)

        options = ttk.Frame(frame)
        options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        ttk.Label(options, text="Positions:").pack(side="left")
        ttk.Combobox(
            options,
            textvariable=self.positions,
            values=("auto", "seconds", "ticks"),
            width=10,
            state="readonly",
        ).pack(side="left", padx=(6, 18))
        ttk.Checkbutton(options, text="Write MIDI fallback", variable=self.make_midi).pack(side="left")
        ttk.Checkbutton(options, text="Write .blwb state files", variable=self.make_states).pack(
            side="left", padx=12
        )

        self.run_button = ttk.Button(frame, text="Convert", command=self._convert)
        self.run_button.grid(row=5, column=0, columnspan=3, sticky="ew", pady=12)

        self.log = tk.Text(frame, height=16, wrap="word", state="disabled")
        self.log.grid(row=6, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(6, weight=1)

    def _pick_revision(self) -> None:
        path = filedialog.askopenfilename(
            title="Select BandLab revision",
            filetypes=[("Revision manifest", "*.json *.zip"), ("All files", "*.*")],
        )
        if not path:
            return
        self.revision.set(path)
        candidate = Path(path).parent / "assets"
        if candidate.is_dir() and not self.assets.get():
            self.assets.set(str(candidate))
        if not self.output.get():
            self.output.set(str(Path(path).with_suffix(".flp")))

    def _pick_assets(self) -> None:
        path = filedialog.askdirectory(title="Select assets folder")
        if path:
            self.assets.set(path)

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save FL Studio project",
            defaultextension=".flp",
            filetypes=[("FL Studio project", "*.flp")],
        )
        if path:
            self.output.set(path)

    def _pick_template(self) -> None:
        path = filedialog.askopenfilename(
            title="Select FL Studio template",
            filetypes=[("FL Studio project", "*.flp")],
        )
        if path:
            self.template.set(path)

    def _convert(self) -> None:
        if self.run_button["state"] == "disabled":
            return
        revision = self.revision.get().strip()
        output = self.output.get().strip()
        if not revision or not output:
            messagebox.showerror("BL2FLP", "Choose a revision manifest and an output file.")
            return
        options = {
            "assets": self.assets.get().strip() or None,
            "template": self.template.get().strip() or None,
            "positions": self.positions.get(),
            "export_midi_file": self.make_midi.get(),
            "write_states": self.make_states.get(),
        }
        self.run_button.configure(state="disabled")
        self._clear()
        thread = threading.Thread(
            target=self._worker,
            args=(revision, output, options),
            daemon=True,
        )
        thread.start()

    def _worker(self, revision: str, output: str, options: dict) -> None:
        try:
            summary = convert(revision, output, **options)
            stats = summary["stats"]
            self._queue.put(
                "Done: {tracks} tracks, {channels} channels, {patterns} patterns, {playlist_items} playlist items".format(
                    **{
                        key: stats.get(key, 0)
                        for key in ("tracks", "channels", "patterns", "playlist_items")
                    }
                )
            )
            self._queue.put(f"FLP: {summary['output']}")
            if summary["midi"]:
                self._queue.put(f"MIDI: {summary['midi']}")
            if summary["states"]:
                self._queue.put(f"States: {summary['states']}")
            for warning in summary["warnings"]:
                self._queue.put(f"warning[{warning['code']}]: {warning['message']}")
            self._queue.put(f"Report: {summary['report']}")
        except Exception as exc:
            self._queue.put(f"error: {exc}")
        finally:
            self._queue.put("__done__")

    def _drain(self) -> None:
        while True:
            try:
                message = self._queue.get_nowait()
            except queue.Empty:
                break
            if message == "__done__":
                self.run_button.configure(state="normal")
                continue
            self.log.configure(state="normal")
            self.log.insert("end", message + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(120, self._drain)

    def _clear(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
