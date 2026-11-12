"""LAN Mapper desktop application. Start with: python app.py"""
from __future__ import annotations

import ipaddress
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import network

BG, PANEL, CARD = "#0c1220", "#131e30", "#1b2940"
TEXT, MUTED, ACCENT = "#edf3ff", "#9badc8", "#42d6b5"
NAME_PATH = Path(__file__).resolve().parent / "data" / "device-names.json"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LAN Mapper • Yerel ağ çalışma alanı")
        self.geometry("1180x820")
        self.minsize(980, 740)
        self.configure(bg=BG)
        self.devices = []
        self.adapters = []
        self.current = None
        self.busy = False
        self.stopping = threading.Event()
        self.events = queue.Queue()
        self.names_error = ""
        try:
            self.names = network.load_names(NAME_PATH)
        except (OSError, ValueError) as exc:
            self.names = {}
            self.names_error = str(exc)
        self.make_style()
        self.build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.poll)
        self.after(200, self.refresh)

    def make_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 25))
        style.configure("TButton", background=CARD, foreground=TEXT, padding=(15, 9), borderwidth=0)
        style.map("TButton", background=[("active", "#2c4260"), ("disabled", "#172132")], foreground=[("disabled", "#66758b")])
        style.configure("Accent.TButton", background=ACCENT, foreground=BG)
        style.map("Accent.TButton", background=[("active", "#79e7ce"), ("disabled", "#274b4a")])
        style.configure("TEntry", fieldbackground=CARD, foreground=TEXT, insertcolor=TEXT, padding=8)
        style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=TEXT, padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", TEXT)])
        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, padding=(24, 12), foreground=MUTED)
        style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACCENT)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=34, borderwidth=0)
        style.configure("Treeview.Heading", background=CARD, foreground=MUTED, padding=10)
        style.map("Treeview", background=[("selected", "#24575c")])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=CARD, borderwidth=0)

    def build(self):
        main = ttk.Frame(self, padding=24)
        main.pack(fill="both", expand=True)
        top = ttk.Frame(main)
        top.pack(fill="x")
        ttk.Label(top, text="LAN Mapper", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="YEREL AĞ  /  IPv4", foreground=ACCENT).pack(side="right")
        ttk.Label(main, text="Ağını tanı. Cihazlarını keşfet. Adreslerini anlamlandır.", style="Muted.TLabel").pack(anchor="w", pady=(4, 18))
        controls = ttk.Frame(main)
        controls.pack(fill="x")
        self.adapter_var = tk.StringVar()
        self.adapter = ttk.Combobox(controls, state="readonly", textvariable=self.adapter_var, width=55)
        self.adapter.pack(side="left", fill="x", expand=True)
        self.adapter.bind("<<ComboboxSelected>>", self.select_adapter)
        self.refresh_button = ttk.Button(controls, text="Ağ bilgilerini yenile", command=self.refresh)
        self.refresh_button.pack(side="left", padx=(12, 0))
        self.info = tk.StringVar(value="Etkin fiziksel Ethernet / Wi-Fi arayüzü aranıyor…")
        ttk.Label(main, textvariable=self.info, style="Muted.TLabel", wraplength=1080, justify="left").pack(anchor="w", pady=(12, 16))
        form = ttk.Frame(main, padding=14, style="Card.TFrame")
        form.pack(fill="x")
        self.start_ip, self.end_ip = tk.StringVar(), tk.StringVar()
        tk.Label(form, text="HEDEF ARALIĞI", bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(side="left", padx=(0, 14))
        self.start_entry = ttk.Entry(form, textvariable=self.start_ip, width=17)
        self.start_entry.pack(side="left")
        tk.Label(form, text=" → ", bg=PANEL, fg=MUTED).pack(side="left")
        self.end_entry = ttk.Entry(form, textvariable=self.end_ip, width=17)
        self.end_entry.pack(side="left")
        self.scan_button = ttk.Button(form, text="Keşfi başlat", style="Accent.TButton", command=self.start_scan, state="disabled")
        self.scan_button.pack(side="left", padx=(18, 8))
        self.stop_button = ttk.Button(form, text="Durdur", command=self.stop_scan, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Label(main, text="En fazla 64 hedef • Tek seferde 1 istek • En az 1 sn aralık • Başlatmadan önce onay", style="Muted.TLabel").pack(anchor="w", pady=(8, 12))
        self.notebook = ttk.Notebook(main, height=250)
        self.notebook.pack(fill="both", expand=True)
        map_tab, devices_tab, calc_tab = (ttk.Frame(self.notebook, padding=16) for _ in range(3))
        for frame, title in zip((map_tab, devices_tab, calc_tab), ("Ağ Haritası", "Cihazlar", "Subnet Hesaplayıcı")):
            self.notebook.add(frame, text=title)
        ttk.Label(map_tab, text="Mantıksal görünüm • Çizgiler fiziksel kablo veya Wi-Fi bağlantısını kanıtlamaz.", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        map_body = ttk.Frame(map_tab)
        map_body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(map_body, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(map_body, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.draw_map())
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-int(e.delta / 120), "units"))
        row = ttk.Frame(devices_tab)
        row.pack(fill="x", pady=(0, 12))
        ttk.Label(row, text="Yanıt yok = belirsiz. ARP kaydı eski olabilir.", style="Muted.TLabel").pack(side="left")
        ttk.Button(row, text="Adı değiştir", command=self.rename).pack(side="right")
        ttk.Button(row, text="CSV dışa aktar", command=self.export).pack(side="right", padx=8)
        table = ttk.Frame(devices_tab)
        table.pack(fill="both", expand=True)
        columns = ("name", "ip", "mac", "hostname", "icmp", "neighbor", "role")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        for key, title, width in zip(columns, ("Ad", "IPv4", "MAC", "Hostname", "ICMP", "Komşu durumu", "Rol"), (160, 130, 155, 160, 180, 120, 150)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=95, stretch=True)
        vscroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        hscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _: self.rename())
        ttk.Label(calc_tab, text="IPv4 adresi / CIDR veya subnet mask girin. Bu panel ağ isteği göndermez.", style="Muted.TLabel").pack(anchor="w")
        calc_row = ttk.Frame(calc_tab)
        calc_row.pack(fill="x", pady=16)
        self.calc_input = tk.StringVar(value="192.168.10.42/24")
        entry = ttk.Entry(calc_row, textvariable=self.calc_input, width=36)
        entry.pack(side="left")
        entry.bind("<Return>", lambda _: self.calculate())
        ttk.Button(calc_row, text="Hesapla", command=self.calculate).pack(side="left", padx=12)
        self.calc_result = tk.StringVar()
        ttk.Label(calc_tab, textvariable=self.calc_result, font=("Consolas", 12), justify="left").pack(anchor="w", pady=8)
        self.calculate()
        self.progress = ttk.Progressbar(main, mode="determinate")
        self.progress.pack(fill="x", pady=(16, 8))
        self.status = tk.StringVar(value="Hazırlanıyor…")
        ttk.Label(main, textvariable=self.status, style="Muted.TLabel", wraplength=1070).pack(anchor="w")

    def worker(self, kind, action):
        def run():
            try:
                self.events.put((kind, action()))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def set_busy(self, busy):
        self.busy = busy
        self.adapter.configure(state="disabled" if busy else "readonly")
        self.refresh_button.configure(state="disabled" if busy else "normal")
        self.scan_button.configure(state="normal" if not busy and self.current else "disabled")
        for entry in (self.start_entry, self.end_entry):
            entry.configure(state="disabled" if busy else "normal")
        if not busy:
            self.stop_button.configure(state="disabled")

    def refresh(self):
        if self.busy:
            return
        self.set_busy(True)
        self.status.set("Fiziksel arayüzler okunuyor; keşif yapılmıyor…")
        self.worker("interfaces", network.interfaces)

    def select_adapter(self, _=None):
        idx = self.adapter.current()
        self.current = self.adapters[idx] if 0 <= idx < len(self.adapters) else None
        self.devices = []
        self.render_devices()
        if not self.current:
            self.info.set("Uygun özel IPv4 adresine sahip etkin fiziksel arayüz yok.")
            self.start_ip.set("")
            self.end_ip.set("")
            self.scan_button.configure(state="disabled")
            return
        a = self.current
        net = a.network
        self.info.set(f"IPv4  {a.address}    •    Maske  {net.netmask}    •    Subnet  {net}    •    Gateway  {a.gateway or 'Yok'}\nKullanılabilir aralık  {network.subnet_info(str(net))['Kullanılabilir IP aralığı']}")
        if net.prefixlen >= 24:
            first = next(net.hosts())
            last = min(int(net.broadcast_address) - (net.prefixlen < 31), int(first) + network.MAX_TARGETS - 1)
            self.start_ip.set(str(first))
            self.end_ip.set(str(ipaddress.IPv4Address(last)))
            self.status.set("Hazır. Varsayılan aralık subnet'in ilk en fazla 64 adresidir; gerekirse düzenleyin.")
        else:
            self.start_ip.set("")
            self.end_ip.set("")
            self.status.set("Geniş subnet: otomatik hedef seçilmedi. Yerel subnet içinden en fazla 64 adres girin.")
        self.calc_input.set(f"{a.address}/{a.prefix}")
        self.calculate()
        self.scan_button.configure(state="normal")
        self.draw_map()

    def start_scan(self):
        if self.busy or not self.current:
            return
        try:
            targets = network.validate_targets(self.current, self.start_ip.get(), self.end_ip.get())
        except ValueError as exc:
            messagebox.showerror("Hedef aralığı", str(exc), parent=self)
            return
        a = self.current
        if not messagebox.askyesno("Yerel ağ keşfi onayı", f"Arayüz: {a.name}\nYerel subnet: {a.network}\nHedef: {targets[0]} – {targets[-1]} ({len(targets)} adres)\n\nEn fazla 1 ICMP isteği/sn, adres başına tek kontrol.\nYalnızca bu hedeflerin komşu kayıtları ve önbellekteki adları okunur.\n\nBu ağın size ait olduğunu ve keşfi başlatmayı onaylıyor musunuz?", parent=self):
            return
        self.devices = []
        self.render_devices()
        self.stopping.clear()
        self.set_busy(True)
        self.stop_button.configure(state="normal")
        self.progress.configure(value=0, maximum=len(targets))
        self.status.set("Yerel rota doğrulanıyor ve keşif başlatılıyor…")
        self.worker("discovery", lambda: network.discover(a, targets, self.stopping,
                    lambda n, total: self.events.put(("progress", (n, total)))))

    def stop_scan(self):
        self.stopping.set()
        self.stop_button.configure(state="disabled")
        self.status.set("Durduruluyor; devam eden sınırlı kontrolün bitmesi bekleniyor…")

    def poll(self):
        try:
            while True:
                kind, result = self.events.get_nowait()
                if kind == "progress":
                    n, total = result
                    self.progress.configure(value=n)
                    if not self.stopping.is_set():
                        self.status.set(f"Kontrol ediliyor: {n}/{total} • Yanıt alınamaması çevrimdışı olduğunu kanıtlamaz.")
                elif kind == "interfaces":
                    self.adapters = result
                    self.adapter["values"] = [f"{a.name}  •  {a.address}/{a.prefix}" for a in result]
                    self.adapter.set("")
                    if result:
                        self.adapter.current(0)
                    self.select_adapter()
                    self.set_busy(False)
                    if self.names_error:
                        messagebox.showwarning("Yerel cihaz adları okunamadı", self.names_error, parent=self)
                        self.names_error = ""
                elif kind == "discovery":
                    self.devices, warnings = result
                    for dev in self.devices:
                        dev.name = self.names.get(network.device_key(self.current, dev), "")
                    self.render_devices()
                    self.set_busy(False)
                    responded = sum(d.icmp == "Yanıt var" for d in self.devices)
                    observed = sum(self.observed(d) for d in self.devices)
                    self.status.set(f"{'Durduruldu' if self.stopping.is_set() else 'Tamamlandı'} • {len(self.devices)} hedef kontrol edildi • {responded} ICMP yanıtı • {observed} cihaz için yerel kanıt var.")
                    if warnings:
                        messagebox.showwarning("Keşif uyarıları", "\n".join(warnings[:5]), parent=self)
                elif kind == "error":
                    self.set_busy(False)
                    self.status.set("İşlem tamamlanamadı. Ağ bağlantısını kontrol edip yenileyin.")
                    messagebox.showerror("LAN Mapper", result, parent=self)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def observed(self, dev):
        return bool(dev.mac or dev.icmp == "Yanıt var" or dev.ip == self.current.address)

    def render_devices(self):
        self.tree.delete(*self.tree.get_children())
        for n, d in enumerate(self.devices):
            role = d.role if self.observed(d) else "Hedef / belirsiz"
            self.tree.insert("", "end", iid=str(n), values=(d.name or "—", d.ip, d.mac or "—", d.hostname or "—", d.icmp, d.neighbor or "—", role))
        self.draw_map()

    def draw_map(self):
        c = self.canvas
        c.delete("all")
        width = max(880, c.winfo_width())
        if not self.current:
            c.create_text(width / 2, 130, text="Yerel arayüz bilgileri bekleniyor", fill=MUTED, font=("Segoe UI", 14))
            return
        visible = [d for d in self.devices if self.observed(d) and d.ip != self.current.gateway]
        gateway = next((d for d in self.devices if d.ip == self.current.gateway), None)
        center = width / 2
        c.create_rectangle(center - 155, 25, center + 155, 95, fill=CARD, outline=ACCENT)
        label = gateway.name if gateway and gateway.name else "Modem / gateway"
        c.create_text(center, 47, text=label[:35], fill=TEXT, font=("Segoe UI Semibold", 12))
        c.create_text(center, 75, text=f"{self.current.gateway or 'Yapılandırılmamış'} • yapılandırma", fill=MUTED, font=("Segoe UI", 9))
        if not visible:
            c.create_text(center, 170, text="Keşfi başlattığınızda kanıt bulunan cihazlar burada görünür.\nICMP yanıtı veya MAC kaydı olmayan hedefler Cihazlar sekmesindedir.", fill=MUTED, justify="center", font=("Segoe UI", 11))
        else:
            c.create_line(center, 95, center, 115, fill="#385671", width=2)
            for n, d in enumerate(visible):
                col, row = n % 4, n // 4
                x, y = width * (col + .5) / 4, 160 + row * 115
                c.create_line(center, 115, x, y - 22, fill="#2d4560", dash=(3, 4))
                c.create_rectangle(x - 99, y - 22, x + 99, y + 57, fill=CARD, outline="#36506b")
                c.create_text(x, y - 2, text=(d.name or d.hostname or d.role)[:25], fill=TEXT, font=("Segoe UI Semibold", 10))
                c.create_text(x, y + 20, text=d.ip, fill=ACCENT, font=("Consolas", 10))
                c.create_text(x, y + 42, text="ICMP yanıtı" if d.icmp == "Yanıt var" else "Yerel kayıt • durum belirsiz", fill=MUTED, font=("Segoe UI", 9))
        c.configure(scrollregion=(0, 0, width, max(320, 240 + ((len(visible) - 1) // 4) * 115)))

    def rename(self):
        if self.busy:
            return
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Cihaz adı", "Cihazlar tablosundan bir satır seçin.", parent=self)
            return
        d = self.devices[int(selected[0])]
        name = simpledialog.askstring("Cihaz adı", "Yerel ad (en fazla 60 karakter; boş bırakarak kaldırın):", initialvalue=d.name, parent=self)
        if name is None:
            return
        name = name.strip()
        if len(name) > 60 or any(ord(ch) < 32 for ch in name):
            messagebox.showerror("Cihaz adı", "En fazla 60 karakter kullanın; kontrol karakteri eklemeyin.", parent=self)
            return
        updated = dict(self.names)
        key = network.device_key(self.current, d)
        if name:
            updated[key] = name
        else:
            updated.pop(key, None)
        try:
            network.save_names(NAME_PATH, updated)
        except OSError as exc:
            messagebox.showerror("Ad kaydedilemedi", str(exc), parent=self)
            return
        self.names, d.name = updated, name
        self.render_devices()

    def export(self):
        if not self.devices or self.busy:
            messagebox.showinfo("CSV", "Önce bir keşfi tamamlayın veya durdurun.", parent=self)
            return
        directory = Path(__file__).resolve().parent / "exports"
        directory.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self, initialdir=str(directory), initialfile="lan-inventory.csv", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                network.export_csv(Path(path), self.devices)
                self.status.set("CSV kaydedildi. Dosya kişisel IP/MAC bilgileri içerir; paylaşırken dikkat edin.")
            except OSError as exc:
                messagebox.showerror("CSV kaydedilemedi", str(exc), parent=self)

    def calculate(self):
        try:
            info = network.subnet_info(self.calc_input.get())
            self.calc_result.set("\n\n".join(f"{key:<29} {value}" for key, value in info.items()))
        except ValueError:
            self.calc_result.set("Geçerli bir IPv4/CIDR girin. Örnek: 192.168.10.42/24\nSubnet mask da kullanılabilir: 192.168.10.42/255.255.255.0")

    def close(self):
        self.stopping.set()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
