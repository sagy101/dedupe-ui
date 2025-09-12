import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from utils import human_size, to_long_path, has_blake3, DEFAULT_WORKERS
from stage1 import Stage1Scanner
from verifier import Verifier
from hashing import HASH_CACHE

# ================== GUI ==================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Two-Stage De-dupe (name+size → on-demand hash)")
        self.geometry("1300x780")
        self.minsize(1100, 600)

        # State
        self.folder_a = tk.StringVar(value="")
        self.folder_b = tk.StringVar(value="")
        self.workers = tk.IntVar(value=DEFAULT_WORKERS)
        self.algos = ["blake3","sha256"] if has_blake3() else ["sha256"]
        self.algo = tk.StringVar(value=self.algos[0])

        self.candidates: list[dict] = []  # rows from Stage 1 (PENDING / MATCH / DIFF / ERROR / DELETED)
        self.rowid_to_index: dict[str, int] = {}

        # Top controls
        top = ttk.Frame(self, padding=10); top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Folder A (keep):").grid(row=0, column=0, sticky="w", padx=(0,6))
        self.entry_a = ttk.Entry(top, textvariable=self.folder_a, width=80)
        self.entry_a.grid(row=0, column=1, sticky="we", padx=(0,6))
        ttk.Button(top, text="Browse…", command=self.browse_a).grid(row=0, column=2, sticky="w")

        ttk.Label(top, text="Folder B (dedupe target):").grid(row=1, column=0, sticky="w", padx=(0,6), pady=(8,0))
        self.entry_b = ttk.Entry(top, textvariable=self.folder_b, width=80)
        self.entry_b.grid(row=1, column=1, sticky="we", padx=(0,6), pady=(8,0))
        ttk.Button(top, text="Browse…", command=self.browse_b).grid(row=1, column=2, sticky="w", pady=(8,0))

        ttk.Label(top, text="Hasher:").grid(row=2, column=0, sticky="w", pady=(10,0))
        ttk.Combobox(top, values=self.algos, textvariable=self.algo, state="readonly", width=10)\
            .grid(row=2, column=1, sticky="w", pady=(10,0))
        ttk.Label(top, text="Workers:").grid(row=2, column=1, sticky="e", pady=(10,0))
        ttk.Spinbox(top, from_=1, to=64, textvariable=self.workers, width=6)\
            .grid(row=2, column=2, sticky="w", pady=(10,0))
        top.grid_columnconfigure(1, weight=1)

        # Actions
        actions = ttk.Frame(self, padding=(10,0,10,10)); actions.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(actions, text="Stage 1: Find name+size candidates", command=self.start_stage1).pack(side=tk.LEFT)
        ttk.Label(actions, text="   ").pack(side=tk.LEFT)
        self.btn_verify_sel = ttk.Button(actions, text="Stage 2: Verify hash (selected)", command=self.verify_selected, state="disabled")
        self.btn_verify_sel.pack(side=tk.LEFT)
        self.btn_verify_all = ttk.Button(actions, text="Stage 2: Verify hash (all pending)", command=self.verify_all_pending, state="disabled")
        self.btn_verify_all.pack(side=tk.LEFT)
        ttk.Label(actions, text="   ").pack(side=tk.LEFT)
        self.btn_delete = ttk.Button(actions, text="Delete Selected from Folder B (only verified matches)",
                                     command=self.delete_selected_matches, state="disabled")
        self.btn_delete.pack(side=tk.LEFT)

        # Progress & status
        prog = ttk.Frame(self, padding=(10,0,10,10)); prog.pack(side=tk.TOP, fill=tk.X)
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(prog, textvariable=self.status_var).pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(prog, orient="horizontal", mode="determinate", length=380)
        self.progress.pack(side=tk.RIGHT)

        # Stats line (Stage 1 and Stage 2 counters)
        stats = ttk.LabelFrame(self, text="Stats", padding=10)
        stats.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0,10))
        self.var_a_done      = tk.IntVar(value=0)
        self.var_a_total     = tk.IntVar(value=0)
        self.var_candidates  = tk.IntVar(value=0)
        self.var_v_done      = tk.IntVar(value=0)
        self.var_v_total     = tk.IntVar(value=0)
        self.var_v_matches   = tk.IntVar(value=0)

        def row(r, label, *vars_or_text):
            ttk.Label(stats, text=label).grid(row=r, column=0, sticky="w")
            c = 1
            for item in vars_or_text:
                if isinstance(item, tk.Variable):
                    ttk.Label(stats, textvariable=item).grid(row=r, column=c, sticky="w")
                else:
                    ttk.Label(stats, text=item).grid(row=r, column=c, sticky="w")
                c += 1

        row(0, "A indexed:", self.var_a_done, "/", self.var_a_total)
        row(1, "Candidates (name+size):", self.var_candidates)
        row(2, "Verified this round:", self.var_v_done, "/", self.var_v_total, "   Matches:", self.var_v_matches)
        for c in range(1, 8):
            stats.grid_columnconfigure(c, weight=1)

        # Table
        table_frame = ttk.Frame(self, padding=10); table_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        cols = ("Status","Name","Size","Hash Algo","Hash B","Path A (first match if many)","Path B")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="extended")
        for c, w in zip(cols, (90, 220, 110, 90, 230, 380, 380)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1); table_frame.grid_columnconfigure(0, weight=1)

        # Row coloring via tags
        self.tree.tag_configure("MATCH", background="#d9f7be")  # light green
        self.tree.tag_configure("DIFF", background="#ffd6d6")   # light red
        self.tree.tag_configure("ERROR", background="#ffe7ba")  # light orange

        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)

    # ---------- Helpers ----------
    def set_status(self, text: str, pct: float | None = None):
        self.status_var.set(text)
        if pct is not None:
            self.progress["value"] = max(0.0, min(100.0, pct*100.0))
        self.update_idletasks()

    def _on_selection_change(self, _evt=None):
        sel = self.tree.selection()
        enable_verify = bool(sel) and bool(self.candidates)
        self.btn_verify_sel.configure(state=("normal" if enable_verify else "disabled"))
        # Delete enabled only if at least one selected row is MATCH
        any_match = any(self.candidates[self.rowid_to_index[iid]]["status"] == "MATCH" for iid in sel) if sel else False
        self.btn_delete.configure(state=("normal" if any_match else "disabled"))

    def browse_a(self):
        p = filedialog.askdirectory(title="Select Folder A (keep)")
        if p: self.folder_a.set(p)

    def browse_b(self):
        p = filedialog.askdirectory(title="Select Folder B (dedupe target)")
        if p: self.folder_b.set(p)

    def _stage1_stats_cb(self, d: dict):
        if "a_done" in d: self.var_a_done.set(d["a_done"])
        if "a_total" in d: self.var_a_total.set(d["a_total"])
        if "candidates" in d: self.var_candidates.set(d["candidates"])

    def _stage1_progress_cb(self, text, pct):
        self.set_status(text, pct)

    def start_stage1(self):
        fa, fb = self.folder_a.get().strip(), self.folder_b.get().strip()
        if not fa or not fb:
            messagebox.showerror("Missing folders", "Please choose both Folder A and Folder B."); return
        if not os.path.isdir(fa) or not os.path.isdir(fb):
            messagebox.showerror("Invalid path", "One or both selected paths are not folders."); return
        if os.path.abspath(fa) == os.path.abspath(fb):
            messagebox.showerror("Same folder", "Folder A and Folder B must be different."); return

        # Clear table and state
        for iid in self.tree.get_children(): self.tree.delete(iid)
        self.candidates.clear()
        self.rowid_to_index.clear()
        self.var_v_done.set(0); self.var_v_total.set(0); self.var_v_matches.set(0)
        self.set_status("Stage 1: preparing…", 0.0)
        self.progress["value"] = 0
        self.btn_verify_sel.configure(state="disabled")
        self.btn_verify_all.configure(state="disabled")
        self.btn_delete.configure(state="disabled")

        def work():
            try:
                scanner = Stage1Scanner(fa, fb,
                                        ui_progress=lambda t,p: self.after(0, self._stage1_progress_cb, t, p),
                                        ui_stats=lambda d: self.after(0, self._stage1_stats_cb, d))
                results = scanner.run()

                def finish():
                    self.set_status(f"Stage 1 complete: {len(results)} candidate(s).", 1.0)
                    # Fill table
                    for idx, r in enumerate(results):
                        a_first = r["a_paths"][0] if r["a_paths"] else ""
                        iid = self.tree.insert("", "end", values=(
                            r["status"], r["name"], human_size(r["size"]), "", "", a_first, r["path_b"]
                        ))
                        self.rowid_to_index[iid] = idx
                    self.candidates = results
                    # enable hash buttons if we have candidates
                    enable = "normal" if results else "disabled"
                    self.btn_verify_sel.configure(state=enable)
                    self.btn_verify_all.configure(state=enable)
                self.after(0, finish)
            except Exception as e:
                self.after(0, messagebox.showerror, "Stage 1 failed", f"{e}")

        threading.Thread(target=work, daemon=True).start()

    # ---------- Stage 2 (verify hashing) ----------
    def _stage2_progress_cb(self, text, pct):
        self.set_status(text, pct)

    def _stage2_counter_cb(self, done, total, matches):
        self.var_v_done.set(done)
        self.var_v_total.set(total)
        self.var_v_matches.set(matches)

    def verify_selected(self):
        sel = list(self.tree.selection())
        if not sel:
            return
        rows = [self.candidates[self.rowid_to_index[iid]] for iid in sel]
        self._run_verifier(rows, also_update_only=sel)

    def verify_all_pending(self):
        # Hash all PENDING rows shown in the table
        pending_rows = [r for r in self.candidates if r.get("status") == "PENDING"]
        if not pending_rows:
            self.set_status("Nothing to verify: no pending rows.", None)
            return
        self._run_verifier(pending_rows, also_update_only=None)  # update all rows

    def _run_verifier(self, rows_to_verify: list[dict], also_update_only: list[str] | None):
        # disable buttons during verify
        self.btn_verify_sel.configure(state="disabled")
        self.btn_verify_all.configure(state="disabled")
        self.btn_delete.configure(state="disabled")
        self.set_status(f"Stage 2: starting verify (algo={self.algo.get()}, workers={self.workers.get()})…", 0.0)

        def work():
            try:
                verifier = Verifier(self.algo.get(), self.workers.get(),
                                    ui_progress=lambda t,p: self.after(0, self._stage2_progress_cb, t, p),
                                    ui_counter=lambda d,t,m: self.after(0, self._stage2_counter_cb, d, t, m))
                done, matches = verifier.verify_rows(rows_to_verify)

                def finish():
                    # Update table row visuals (only those that were in the selection if provided,
                    # otherwise update all rows)
                    targets = also_update_only or list(self.tree.get_children())
                    for iid in targets:
                        idx = self.rowid_to_index.get(iid)
                        if idx is None:
                            continue
                        r = self.candidates[idx]
                        # set row text + tags
                        a_first = r["a_paths"][0] if r["a_paths"] else ""
                        hash_b_short = (r["hash_b"][:16] + "…") if r.get("hash_b") else ""
                        self.tree.item(iid, values=(
                            r["status"], r["name"], human_size(r["size"]),
                            (r["hash_algo"] or ""), hash_b_short, a_first, r["path_b"]
                        ), tags=(r["status"],) if r["status"] in ("MATCH","DIFF","ERROR") else ())
                    self.set_status(f"Stage 2 complete: verified {done}, matches {matches}.", 1.0)
                    # Re-enable buttons
                    self.btn_verify_sel.configure(state="normal")
                    self.btn_verify_all.configure(state="normal")
                    # Recompute if delete can be enabled based on current selection
                    self._on_selection_change()
                    HASH_CACHE.save()
                self.after(0, finish)
            except Exception as e:
                self.after(0, messagebox.showerror, "Stage 2 failed", f"{e}")

        threading.Thread(target=work, daemon=True).start()

    # ---------- Deletion ----------
    def delete_selected_matches(self):
        sel = list(self.tree.selection())
        if not sel:
            return
        to_delete = []
        for iid in sel:
            idx = self.rowid_to_index[iid]
            r = self.candidates[idx]
            if r["status"] == "MATCH":
                to_delete.append((iid, r["path_b"]))
        if not to_delete:
            messagebox.showinfo("Nothing to delete", "Select verified MATCH rows (green) to delete from Folder B.")
            return
        if not messagebox.askyesno("Confirm deletion",
                                   f"Delete {len(to_delete)} file(s) from Folder B?\nThis action is PERMANENT."):
            return

        errors = []
        deleted = 0
        for iid, path_b in to_delete:
            try:
                os.remove(to_long_path(path_b))
                deleted += 1
                self.tree.delete(iid)
                # also mark in model
                idx = self.rowid_to_index.pop(iid, None)
                if idx is not None:
                    self.candidates[idx]["status"] = "DELETED"
            except Exception as e:
                errors.append((path_b, str(e)))

        # Rebuild rowid_to_index (since some rows removed)
        new_map = {}
        for iid in self.tree.get_children():
            idx = self.rowid_to_index.get(iid)
            if idx is not None:
                new_map[iid] = idx
        self.rowid_to_index = new_map

        msg = f"Deleted {deleted} file(s)."
        if errors:
            msg += f" {len(errors)} error(s) occurred."
        messagebox.showinfo("Deletion complete", msg)
        self._on_selection_change()  # refresh delete button
