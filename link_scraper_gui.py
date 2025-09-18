# link_scraper_gui.py
# -*- coding: utf-8 -*-
import re
import threading
import concurrent.futures as futures
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk  # Treeview için

import requests
import pandas as pd
from bs4 import BeautifulSoup

# ttkbootstrap = modern tema
from ttkbootstrap import Style
from ttkbootstrap.constants import *
from ttkbootstrap.widgets import Frame, Button, Entry, Label, Progressbar



HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15


def clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title_desc(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    # Title: og:title -> twitter:title -> <title> -> <h1>
    title = ""
    for m in [
        soup.find("meta", property="og:title"),
        soup.find("meta", attrs={"name": "twitter:title"}),
    ]:
        if m and m.get("content"):
            title = clean(m["content"])
            break
    if not title and soup.title:
        title = clean(soup.title.get_text())
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = clean(h1.get_text())

    # Description: description -> og:description -> twitter:description
    desc = ""
    for m in [
        soup.find("meta", attrs={"name": "description"}),
        soup.find("meta", property="og:description"),
        soup.find("meta", attrs={"name": "twitter:description"}),
    ]:
        if m and m.get("content"):
            desc = clean(m["content"])
            break

    return title, desc


def fetch(url: str) -> dict:
    try:
        # http/https otomatik dene
        tries = []
        if url.startswith("http://"):
            tries = [url.replace("http://", "https://", 1), url]
        elif url.startswith("https://"):
            tries = [url, url.replace("https://", "http://", 1)]
        else:
            tries = [f"https://{url}", f"http://{url}"]

        last_exc = None
        for candidate in tries:
            try:
                r = requests.get(candidate, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
                if r.ok and r.text:
                    title, desc = extract_title_desc(r.text)
                    return {"url": candidate, "status": r.status_code, "title": title, "description": desc}
            except Exception as e:
                last_exc = e
                continue

        # Hepsi patladıysa:
        err = last_exc.__class__.__name__ if last_exc else "ERR"
        return {"url": url, "status": err, "title": "", "description": ""}

    except Exception as e:
        return {"url": url, "status": f"ERR:{e}", "title": "", "description": ""}


class App:
    def __init__(self, root):
        # Tema: "flatly" açık, "cyborg" veya "superhero" koyu
        self.style = Style(theme="flatly")
        self.root = root
        self.root.title("Link Başlık & Açıklama Toplayıcı")
        self.root.geometry("1024x700")
        self.root.minsize(900, 600)

        self.results = []
        self.scrape_thread = None
        self.is_scraping = False
        self.output_path = tk.StringVar(value=str(Path.cwd() / "scraped_links.xlsx"))

        self.build_ui()

    def build_ui(self):
        top = Frame(self.root, padding=15)
        top.pack(fill=X)

        Label(top, text="URL Listesi (her satıra bir URL)", bootstyle=SECONDARY).pack(anchor=W, pady=(0, 6))

        # Text alanı -> tkinter'den
        self.txt = tk.Text(top, height=8, wrap="word")
        self.txt.pack(fill=X)

        # Örnek URL butonu
        Button(top, text="Örnek URL ekle", bootstyle=LINK, command=self.fill_example).pack(anchor=W, pady=6)

        # Çıktı dosyası seçimi
        out_row = Frame(top)
        out_row.pack(fill=X, pady=(12, 0))
        Label(out_row, text="Excel Çıkışı:", bootstyle=SECONDARY).pack(side=LEFT)
        Entry(out_row, textvariable=self.output_path).pack(side=LEFT, fill=X, expand=True, padx=8)
        Button(out_row, text="Kaydet Yeri...", bootstyle=SECONDARY, command=self.choose_output).pack(side=LEFT)

        # Aksiyon butonları
        actions = Frame(top)
        actions.pack(fill=X, pady=10)
        Button(actions, text="Tarama Başlat", bootstyle=SUCCESS, command=self.start_scrape).pack(side=LEFT)
        Button(actions, text="Temizle", bootstyle=WARNING, command=self.clear_all).pack(side=LEFT, padx=8)
        Button(actions, text="Excel'e Aktar", bootstyle=INFO, command=self.export_excel).pack(side=LEFT)

        # Progress
        self.pb = Progressbar(top, mode="indeterminate", bootstyle=INFO, length=200)
        self.pb.pack(anchor=W, pady=(4, 0))

        # Alt kısım: Sonuç tablosu
        table_frame = Frame(self.root, padding=(15, 0, 15, 15))
        table_frame.pack(fill=BOTH, expand=True)

        Label(table_frame, text="Sonuçlar", bootstyle=SECONDARY).pack(anchor=W, pady=(0, 6))

        columns = ("url", "status", "title", "description")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)
        for col in columns:
            self.tree.heading(col, text=col.capitalize())
        self.tree.column("url", width=320, anchor=W)
        self.tree.column("status", width=80, anchor=W)
        self.tree.column("title", width=300, anchor=W)
        self.tree.column("description", width=500, anchor=W)

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=yscroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        yscroll.pack(side=LEFT, fill=Y)

    # --- UI Callbacks ---
    def fill_example(self):
        ex = (
            "https://beykozunsesi.com.tr/beykoz-haber\n"
        )
        self.txt.insert("1.0", ex)

    def choose_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="scraped_links.xlsx",
            title="Excel çıktısı kaydet"
        )
        if path:
            self.output_path.set(path)

    def clear_all(self):
        if self.is_scraping:
            messagebox.showwarning("Uyarı", "İşlem devam ederken temizlenemez.")
            return
        self.txt.delete("1.0", tk.END)
        self.results = []
        for i in self.tree.get_children():
            self.tree.delete(i)

    def start_scrape(self):
        if self.is_scraping:
            return
        urls = [u.strip() for u in self.txt.get("1.0", tk.END).splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo("Bilgi", "Lütfen en az bir URL giriniz.")
            return

        for i in self.tree.get_children():
            self.tree.delete(i)
        self.results = []

        self.is_scraping = True
        self.pb.start(10)
        self.scrape_thread = threading.Thread(target=self._scrape_worker, args=(urls,), daemon=True)
        self.scrape_thread.start()

    def _scrape_worker(self, urls: list[str]):
        try:
            rows = []
            with futures.ThreadPoolExecutor(max_workers=min(16, len(urls) or 1)) as ex:
                for res in ex.map(fetch, urls):
                    rows.append(res)
                    self.root.after(0, self._append_row_to_table, res)
            self.results = rows
        finally:
            self.root.after(0, self._end_progress)

    def _append_row_to_table(self, res: dict):
        self.tree.insert("", tk.END, values=(res["url"], res["status"], res["title"], res["description"]))

    def _end_progress(self):
        self.pb.stop()
        self.is_scraping = False
        messagebox.showinfo("Tamam", "Tarama tamamlandı.")

    def export_excel(self):
        if not self.results:
            messagebox.showinfo("Bilgi", "Sonuç yok. Önce taramayı çalıştırın.")
            return
        try:
            df = pd.DataFrame(self.results, columns=["url", "status", "title", "description"])
            out = Path(self.output_path.get())
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_excel(out, index=False)
            messagebox.showinfo("Başarılı", f"Excel kaydedildi:\n{out}")
        except Exception as e:
            messagebox.showerror("Hata", f"Excel yazarken hata: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
