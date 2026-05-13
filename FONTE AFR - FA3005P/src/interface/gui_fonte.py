"""Interface gráfica para o controlador da fonte AFR FA3005P.

Mantém control_fonte.py inalterado: este arquivo apenas o consome.
"""

import json
import os
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

from serial.tools import list_ports

# Layout: este arquivo está em <root>/src/interface/gui_fonte.py
# control_fonte.py está em <root>/src/control_fonte.py
# exemplos/ está em <root>/exemplos/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))      # src/interface
SRC_DIR = os.path.dirname(SCRIPT_DIR)                        # src
PROJECT_ROOT = os.path.dirname(SRC_DIR)                      # raiz do projeto
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from control_fonte import Fonte

# Pasta padrão para diálogos de arquivo (exemplos de teste)
EXEMPLOS_DIR = os.path.join(PROJECT_ROOT, "exemplos")
if not os.path.isdir(EXEMPLOS_DIR):
    EXEMPLOS_DIR = PROJECT_ROOT

# Defaults vindos de control_fonte.py
DEFAULT_PORTA = "COM3"
DEFAULT_BAUDRATE = 9600
BAUDRATES = ["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"]

# Informações do projeto (exibidas em Ajuda → Sobre)
APP_NOME = "Controle Fonte AFR FA3005P"
APP_VERSAO = "1.0"
APP_AUTOR = "Rafael Macedo"
APP_EMAIL = "rafael.macedoengenharia@gmail.com"
APP_GITHUB = "https://github.com/RSMEngenhariaJF/automa--o-medidas"


# ---------- Helpers de formatação para o txt ----------
def _parse_num(s):
    """Aceita '1,000' ou '1.000' e retorna float."""
    return float(str(s).strip().replace(",", "."))


def fmt_v(v):
    """Formata tensão como 'XX,XX' (ex.: 8.0 -> '08,00')."""
    return f"{v:05.2f}".replace(".", ",")


def fmt_i(i):
    """Formata corrente como 'X,XXX' (ex.: 1.0 -> '1,000')."""
    return f"{i:.3f}".replace(".", ",")


def fmt_t(t):
    """Formata tempo (em s) como 'X,XXXs' (ex.: 1.0 -> '1,000s')."""
    return f"{t:.3f}".replace(".", ",") + "s"


class FonteGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Controle Fonte AFR FA3005P")
        self.root.geometry("1050x880")

        # --- Estado de execução ---
        self.fonte = None
        self.comandos = []          # lista (passo, vstr, istr, t_s) carregada de txt
        self.arquivo = None
        self.thread_exec = None
        self.parar_flag = threading.Event()

        # --- Estado do editor ---
        # cada item: (vstr, istr, t_s)
        self.editor_passos = []

        # --- Estado da calibração ---
        # cada ponto: (v_set, v_medido, i_medido) em floats
        self.cal_pontos = []
        self.cal_coef = None         # (a, b) para V_medido = a*V_set + b
        self.cal_r2 = None

        self._build_ui()

    # ============================================================
    # UI
    # ============================================================
    def _build_ui(self):
        self._build_menubar()

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        tab_exec = ttk.Frame(nb)
        tab_edit = ttk.Frame(nb)
        tab_cal = ttk.Frame(nb)
        nb.add(tab_exec, text="Executar teste")
        nb.add(tab_edit, text="Editor de forma de onda")
        nb.add(tab_cal, text="Calibração")

        self._build_tab_exec(tab_exec)
        self._build_tab_editor(tab_edit)
        self._build_tab_calibracao(tab_cal)

        # Log compartilhado (abaixo do notebook)
        frm_log = ttk.LabelFrame(self.root, text="Log")
        frm_log.pack(fill="both", expand=False, padx=4, pady=4)
        self.txt_log = tk.Text(frm_log, height=7, wrap="none")
        self.txt_log.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(frm_log, orient="vertical", command=self.txt_log.yview)
        sb.pack(side="right", fill="y")
        self.txt_log.config(yscrollcommand=sb.set)

    # ------------------- Aba Execução -------------------
    def _build_tab_exec(self, parent):
        # Conexão
        frm_conn = ttk.LabelFrame(parent, text="Conexão")
        frm_conn.pack(fill="x", padx=8, pady=4)

        ttk.Label(frm_conn, text="Porta:").pack(side="left", padx=4, pady=4)
        self.var_porta = tk.StringVar(value=DEFAULT_PORTA)
        self.cmb_porta = ttk.Combobox(frm_conn, textvariable=self.var_porta, width=28, values=[])
        self.cmb_porta.pack(side="left", padx=4)
        ttk.Button(frm_conn, text="Atualizar dispositivos", command=self.atualizar_portas).pack(side="left", padx=4)

        ttk.Label(frm_conn, text="Baudrate:").pack(side="left", padx=(12, 4))
        self.var_baud = tk.StringVar(value=str(DEFAULT_BAUDRATE))
        self.cmb_baud = ttk.Combobox(frm_conn, textvariable=self.var_baud, width=8,
                                     values=BAUDRATES, state="normal")
        self.cmb_baud.pack(side="left", padx=4)

        ttk.Button(frm_conn, text="Verificar / Conectar", command=self.conectar).pack(side="left", padx=8)
        ttk.Button(frm_conn, text="Desconectar", command=self.desconectar).pack(side="left", padx=4)
        self.lbl_status_conn = ttk.Label(frm_conn, text="Desconectado", foreground="red")
        self.lbl_status_conn.pack(side="left", padx=12)

        self.atualizar_portas(silent=True)

        # Arquivo
        frm_arq = ttk.LabelFrame(parent, text="Arquivo de teste")
        frm_arq.pack(fill="x", padx=8, pady=4)

        ttk.Button(frm_arq, text="Selecionar .txt", command=self.selecionar_arquivo).pack(side="left", padx=4, pady=4)
        ttk.Button(frm_arq, text="Visualizar forma de onda", command=self.plotar).pack(side="left", padx=4)
        self.lbl_arquivo = ttk.Label(frm_arq, text="(nenhum arquivo selecionado)")
        self.lbl_arquivo.pack(side="left", padx=12)

        # Execução
        frm_run = ttk.LabelFrame(parent, text="Execução")
        frm_run.pack(fill="x", padx=8, pady=4)

        ttk.Label(frm_run, text="Ciclos:").pack(side="left", padx=4, pady=4)
        self.var_ciclos = tk.StringVar(value="1")
        ttk.Entry(frm_run, textvariable=self.var_ciclos, width=6).pack(side="left", padx=4)

        self.btn_exec = ttk.Button(frm_run, text="Executar", command=self.executar)
        self.btn_exec.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(frm_run, text="Parar", command=self.parar, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        ttk.Separator(frm_run, orient="vertical").pack(side="left", fill="y", padx=8, pady=4)
        ttk.Button(frm_run, text="Ligar saída", command=self.ligar_saida).pack(side="left", padx=4)
        ttk.Button(frm_run, text="Desligar saída", command=self.desligar_saida).pack(side="left", padx=4)

        self.lbl_status_exec = ttk.Label(frm_run, text="Ocioso")
        self.lbl_status_exec.pack(side="left", padx=12)

        # Operação manual
        frm_man = ttk.LabelFrame(parent, text="Operação manual")
        frm_man.pack(fill="x", padx=8, pady=4)

        ttk.Label(frm_man, text="Tensão (V):").pack(side="left", padx=4, pady=4)
        self.var_man_vset = tk.StringVar(value="0,00")
        ttk.Entry(frm_man, textvariable=self.var_man_vset, width=10).pack(side="left", padx=4)
        ttk.Button(frm_man, text="Setar tensão", command=self.setar_tensao_manual).pack(side="left", padx=4)

        ttk.Separator(frm_man, orient="vertical").pack(side="left", fill="y", padx=12, pady=4)

        ttk.Label(frm_man, text="Corrente (A):").pack(side="left", padx=4)
        self.var_man_iset = tk.StringVar(value="1,000")
        ttk.Entry(frm_man, textvariable=self.var_man_iset, width=10).pack(side="left", padx=4)
        ttk.Button(frm_man, text="Setar corrente", command=self.setar_corrente_manual).pack(side="left", padx=4)

        # Gráfico
        frm_plot = ttk.LabelFrame(parent, text="Forma de onda (V e I) x tempo")
        frm_plot.pack(fill="both", expand=True, padx=8, pady=4)

        self.fig = Figure(figsize=(7, 3.0), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Tempo acumulado (s)")
        self.ax.set_ylabel("Valor")
        self.ax.grid(True)
        self.canvas = FigureCanvasTkAgg(self.fig, master=frm_plot)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    # ------------------- Aba Editor -------------------
    def _build_tab_editor(self, parent):
        # Linha superior: dois grupos (manual / rampa) lado a lado
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=8, pady=4)

        # Passo manual
        frm_man = ttk.LabelFrame(top, text="Adicionar passo manual")
        frm_man.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ttk.Label(frm_man, text="Tensão (V):").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        self.var_man_v = tk.StringVar(value="0,00")
        ttk.Entry(frm_man, textvariable=self.var_man_v, width=10).grid(row=0, column=1, padx=4, pady=2)

        ttk.Label(frm_man, text="Corrente (A):").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        self.var_man_i = tk.StringVar(value="1,000")
        ttk.Entry(frm_man, textvariable=self.var_man_i, width=10).grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(frm_man, text="Tempo (s):").grid(row=2, column=0, sticky="e", padx=4, pady=2)
        self.var_man_t = tk.StringVar(value="1,000")
        ttk.Entry(frm_man, textvariable=self.var_man_t, width=10).grid(row=2, column=1, padx=4, pady=2)

        ttk.Button(frm_man, text="Adicionar passo", command=self.editor_add_passo_manual)\
            .grid(row=3, column=0, columnspan=2, padx=4, pady=6, sticky="ew")

        # Rampa
        frm_rmp = ttk.LabelFrame(top, text="Adicionar rampa (gera N passos entre V₁ e V₂)")
        frm_rmp.pack(side="left", fill="x", expand=True, padx=(4, 0))

        ttk.Label(frm_rmp, text="V inicial:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        self.var_rmp_v1 = tk.StringVar(value="0,00")
        ttk.Entry(frm_rmp, textvariable=self.var_rmp_v1, width=10).grid(row=0, column=1, padx=4, pady=2)

        ttk.Label(frm_rmp, text="V final:").grid(row=0, column=2, sticky="e", padx=4, pady=2)
        self.var_rmp_v2 = tk.StringVar(value="8,00")
        ttk.Entry(frm_rmp, textvariable=self.var_rmp_v2, width=10).grid(row=0, column=3, padx=4, pady=2)

        ttk.Label(frm_rmp, text="Corrente (A):").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        self.var_rmp_i = tk.StringVar(value="1,000")
        ttk.Entry(frm_rmp, textvariable=self.var_rmp_i, width=10).grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(frm_rmp, text="Nº de passos:").grid(row=1, column=2, sticky="e", padx=4, pady=2)
        self.var_rmp_n = tk.StringVar(value="9")
        ttk.Entry(frm_rmp, textvariable=self.var_rmp_n, width=10).grid(row=1, column=3, padx=4, pady=2)

        ttk.Label(frm_rmp, text="Tempo por passo (s):").grid(row=2, column=0, sticky="e", padx=4, pady=2)
        self.var_rmp_t = tk.StringVar(value="1,000")
        ttk.Entry(frm_rmp, textvariable=self.var_rmp_t, width=10).grid(row=2, column=1, padx=4, pady=2)

        ttk.Button(frm_rmp, text="Adicionar rampa", command=self.editor_add_rampa)\
            .grid(row=3, column=0, columnspan=4, padx=4, pady=6, sticky="ew")

        # Linha do meio: lista de passos + preview do gráfico
        mid = ttk.Frame(parent)
        mid.pack(fill="both", expand=True, padx=8, pady=4)

        # Tabela
        frm_lst = ttk.LabelFrame(mid, text="Passos atuais")
        frm_lst.pack(side="left", fill="both", expand=True, padx=(0, 4))

        cols = ("passo", "V", "I", "tempo")
        self.tv = ttk.Treeview(frm_lst, columns=cols, show="headings", height=12)
        self.tv.heading("passo", text="#"); self.tv.column("passo", width=40, anchor="center")
        self.tv.heading("V", text="Tensão (V)"); self.tv.column("V", width=90, anchor="center")
        self.tv.heading("I", text="Corrente (A)"); self.tv.column("I", width=100, anchor="center")
        self.tv.heading("tempo", text="Tempo (s)"); self.tv.column("tempo", width=90, anchor="center")
        self.tv.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        sb_tv = ttk.Scrollbar(frm_lst, orient="vertical", command=self.tv.yview)
        sb_tv.pack(side="right", fill="y")
        self.tv.config(yscrollcommand=sb_tv.set)

        # Botões da tabela
        frm_btns = ttk.Frame(mid)
        frm_btns.pack(side="left", fill="y", padx=(0, 4))

        ttk.Button(frm_btns, text="Excluir selecionado", command=self.editor_excluir_selecionado).pack(fill="x", pady=2)
        ttk.Button(frm_btns, text="Excluir todos", command=self.editor_excluir_todos).pack(fill="x", pady=2)
        ttk.Button(frm_btns, text="Mover para cima", command=lambda: self.editor_mover(-1)).pack(fill="x", pady=2)
        ttk.Button(frm_btns, text="Mover para baixo", command=lambda: self.editor_mover(+1)).pack(fill="x", pady=2)
        ttk.Separator(frm_btns, orient="horizontal").pack(fill="x", pady=6)
        ttk.Button(frm_btns, text="Visualizar", command=self.editor_visualizar).pack(fill="x", pady=2)

        # Gráfico do editor
        frm_pv = ttk.LabelFrame(mid, text="Preview")
        frm_pv.pack(side="left", fill="both", expand=True, padx=(4, 0))

        self.fig_ed = Figure(figsize=(5, 3.0), dpi=100)
        self.ax_ed = self.fig_ed.add_subplot(111)
        self.ax_ed.set_xlabel("Tempo acumulado (s)")
        self.ax_ed.set_ylabel("Valor")
        self.ax_ed.grid(True)
        self.canvas_ed = FigureCanvasTkAgg(self.fig_ed, master=frm_pv)
        self.canvas_ed.get_tk_widget().pack(fill="both", expand=True)

        # Linha inferior: carregar / nome / salvar
        bot = ttk.LabelFrame(parent, text="Carregar / Salvar")
        bot.pack(fill="x", padx=8, pady=4)

        ttk.Button(bot, text="Carregar txt para editar...", command=self.editor_carregar_txt)\
            .pack(side="left", padx=4, pady=4)

        ttk.Separator(bot, orient="vertical").pack(side="left", fill="y", padx=8, pady=4)

        ttk.Label(bot, text="Nome do arquivo:").pack(side="left", padx=4)
        self.var_nome_arq = tk.StringVar(value="meu_teste")
        ttk.Entry(bot, textvariable=self.var_nome_arq, width=30).pack(side="left", padx=4)
        ttk.Label(bot, text=".txt").pack(side="left")

        ttk.Button(bot, text="Salvar como TXT", command=self.editor_salvar_txt)\
            .pack(side="left", padx=8)

    # ============================================================
    # Helpers
    # ============================================================
    def log(self, msg):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")

    def _set_status_exec(self, txt):
        self.root.after(0, lambda: self.lbl_status_exec.config(text=txt))

    def _set_buttons_running(self, rodando):
        def apply():
            self.btn_exec.config(state="disabled" if rodando else "normal")
            self.btn_stop.config(state="normal" if rodando else "disabled")
        self.root.after(0, apply)

    # ============================================================
    # Conexão / portas
    # ============================================================
    def atualizar_portas(self, silent=False):
        portas = list(list_ports.comports())
        valores = []
        for p in portas:
            desc = p.description or ""
            if desc and desc != "n/a":
                valores.append(f"{p.device} - {desc}")
            else:
                valores.append(p.device)
        self.cmb_porta["values"] = valores
        if not silent:
            if portas:
                self.log("[INFO] Dispositivos encontrados:")
                for p in portas:
                    self.log(f"  {p.device} | {p.description} | hwid={p.hwid}")
            else:
                self.log("[INFO] Nenhum dispositivo serial encontrado.")

    def _porta_selecionada(self):
        raw = self.var_porta.get().strip()
        return raw.split(" - ", 1)[0].strip() if raw else ""

    def conectar(self):
        if self.fonte and self.fonte.serial and self.fonte.serial.is_open:
            self.log("[INFO] Já conectado.")
            return
        porta = self._porta_selecionada()
        if not porta:
            messagebox.showerror("Erro", "Informe a porta serial (ex.: COM3).")
            return
        try:
            baud = int(self.var_baud.get().strip())
        except ValueError:
            messagebox.showerror("Erro", "Baudrate inválido.")
            return
        self.fonte = Fonte(porta_serial=porta, baudrate=baud)
        if self.fonte.serial and self.fonte.serial.is_open:
            self.lbl_status_conn.config(text=f"Conectado em {porta} @ {baud}", foreground="green")
            self.log(f"[INFO] Conectado em {porta} @ {baud} bps")
            try:
                vset = self.fonte.ler_vset()
                iset = self.fonte.ler_iset()
                status = self.fonte.ler_status()
                self.log(f"[INFO] VSET1?={vset} | ISET1?={iset} | STATUS?={status}")
            except Exception as e:
                self.log(f"[AVISO] Falha ao consultar fonte: {e}")
        else:
            self.lbl_status_conn.config(text="Falha ao conectar", foreground="red")
            self.log(f"[ERRO] Não foi possível abrir {porta}")

    def desconectar(self):
        if self.fonte:
            try:
                self.fonte.fechar()
            except Exception as e:
                self.log(f"[AVISO] {e}")
            self.fonte = None
        self.lbl_status_conn.config(text="Desconectado", foreground="red")

    # ============================================================
    # Aba Execução: arquivo + plot + run
    # ============================================================
    def selecionar_arquivo(self):
        path = filedialog.askopenfilename(
            title="Selecione o arquivo de teste",
            filetypes=[("Arquivos de texto", "*.txt"), ("Todos", "*.*")],
            initialdir=EXEMPLOS_DIR,
        )
        if not path:
            return
        comandos = Fonte.ler_arquivo_comandos(path)
        if not comandos:
            messagebox.showerror("Erro", "Não foi possível ler o arquivo (verifique o formato).")
            return
        self.arquivo = path
        self.comandos = comandos
        self.lbl_arquivo.config(text=os.path.basename(path))
        self.log(f"[INFO] Arquivo carregado: {path} ({len(comandos)} passos)")
        self._desenhar_plot(self.ax, self.canvas, [(v, i, t) for _, v, i, t in self.comandos])

    def plotar(self):
        if not self.comandos:
            messagebox.showinfo("Aviso", "Selecione um arquivo de teste primeiro.")
            return
        self._desenhar_plot(self.ax, self.canvas, [(v, i, t) for _, v, i, t in self.comandos])

    def _desenhar_plot(self, ax, canvas, dados):
        """Desenha forma de onda em degraus (step-and-hold).
        dados: lista de (vstr, istr, t_s)
        """
        ax.clear()
        ax.set_xlabel("Tempo acumulado (s)")
        ax.set_ylabel("Valor")
        ax.grid(True)
        if not dados:
            canvas.draw()
            return
        tempos, tensoes, correntes = [], [], []
        t = 0.0
        for vstr, istr, ts in dados:
            v = _parse_num(vstr)
            i = _parse_num(istr)
            tempos.append(t); tensoes.append(v); correntes.append(i)
            t += ts
            tempos.append(t); tensoes.append(v); correntes.append(i)
        ax.plot(tempos, tensoes, label="Tensão (V)", color="tab:blue")
        ax.plot(tempos, correntes, label="Corrente (A)", color="tab:red")
        ax.legend(loc="best")
        canvas.figure.tight_layout()
        canvas.draw()

    def executar(self):
        if not self.fonte or not self.fonte.serial or not self.fonte.serial.is_open:
            messagebox.showerror("Erro", "Conecte-se à fonte primeiro.")
            return
        if not self.comandos:
            messagebox.showerror("Erro", "Selecione um arquivo de teste primeiro.")
            return
        try:
            ciclos = int(self.var_ciclos.get())
            if ciclos < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Erro", "Número de ciclos inválido.")
            return

        self.parar_flag.clear()
        self._set_buttons_running(True)
        self._set_status_exec("Executando...")
        self.thread_exec = threading.Thread(target=self._loop_execucao, args=(ciclos,), daemon=True)
        self.thread_exec.start()

    def _loop_execucao(self, ciclos):
        try:
            self.log(f"[INFO] Iniciando execução ({ciclos} ciclo(s))")
            self.fonte.enviar_comando("OUTPUT1\\n")
            for c in range(ciclos):
                if self.parar_flag.is_set():
                    break
                self.log(f"[INFO] Ciclo {c + 1}/{ciclos}")
                for passo, vstr, istr, ts in self.comandos:
                    if self.parar_flag.is_set():
                        break
                    v_alvo = _parse_num(vstr)
                    v_envio = self.cal_compensar(v_alvo)
                    vstr_envio = fmt_v(v_envio)
                    if abs(v_envio - v_alvo) > 1e-6:
                        self.log(f"  Passo {passo}: V_alvo={vstr} -> V_comp={vstr_envio} | I={istr} | dwell={ts}s")
                    else:
                        self.log(f"  Passo {passo}: V={vstr} | I={istr} | dwell={ts}s")
                    self.fonte.setar_tensao(vstr_envio)
                    self.fonte.setar_corrente(istr)
                    fim = time.time() + ts
                    while time.time() < fim:
                        if self.parar_flag.is_set():
                            break
                        time.sleep(min(0.05, max(0.0, fim - time.time())))
            if self.parar_flag.is_set():
                self.log("[INFO] Execução interrompida pelo usuário (saída mantida no último estado).")
                self._set_status_exec("Parado")
            else:
                self.fonte.enviar_comando("OUTPUT0\\n")
                self.log("[INFO] Execução concluída. Saída desligada (OUTPUT0).")
                self._set_status_exec("Concluído")
        except Exception as e:
            self.log(f"[ERRO] {e}")
            self._set_status_exec("Erro")
        finally:
            self._set_buttons_running(False)

    def parar(self):
        if self.thread_exec and self.thread_exec.is_alive():
            self.parar_flag.set()
            self.log("[INFO] Solicitando parada...")
            self._set_status_exec("Parando...")

    def ligar_saida(self):
        if not self.fonte or not self.fonte.serial or not self.fonte.serial.is_open:
            messagebox.showerror("Erro", "Conecte-se à fonte primeiro.")
            return
        self.fonte.enviar_comando("OUTPUT1\\n")
        self.log("[INFO] OUTPUT1 enviado (saída ligada).")

    def desligar_saida(self):
        if not self.fonte or not self.fonte.serial or not self.fonte.serial.is_open:
            messagebox.showerror("Erro", "Conecte-se à fonte primeiro.")
            return
        self.fonte.enviar_comando("OUTPUT0\\n")
        self.log("[INFO] OUTPUT0 enviado (saída desligada).")

    def setar_tensao_manual(self):
        if not self.fonte or not self.fonte.serial or not self.fonte.serial.is_open:
            messagebox.showerror("Erro", "Conecte-se à fonte primeiro.")
            return
        try:
            v = _parse_num(self.var_man_vset.get())
        except Exception as e:
            messagebox.showerror("Erro", f"Tensão inválida: {e}")
            return
        vstr = fmt_v(v)
        self.fonte.setar_tensao(vstr)
        self.log(f"[MANUAL] VSET1:{vstr} enviado.")

    def setar_corrente_manual(self):
        if not self.fonte or not self.fonte.serial or not self.fonte.serial.is_open:
            messagebox.showerror("Erro", "Conecte-se à fonte primeiro.")
            return
        try:
            i = _parse_num(self.var_man_iset.get())
        except Exception as e:
            messagebox.showerror("Erro", f"Corrente inválida: {e}")
            return
        istr = fmt_i(i)
        self.fonte.setar_corrente(istr)
        self.log(f"[MANUAL] ISET1:{istr} enviado.")

    # ============================================================
    # Aba Editor
    # ============================================================
    def _refresh_lista(self):
        for iid in self.tv.get_children():
            self.tv.delete(iid)
        for idx, (vstr, istr, t_s) in enumerate(self.editor_passos, start=1):
            self.tv.insert("", "end", iid=str(idx),
                           values=(idx, vstr, istr, f"{t_s:.3f}".replace(".", ",")))

    def editor_add_passo_manual(self):
        try:
            v = _parse_num(self.var_man_v.get())
            i = _parse_num(self.var_man_i.get())
            t = _parse_num(self.var_man_t.get())
            if t <= 0:
                raise ValueError("Tempo deve ser > 0.")
        except Exception as e:
            messagebox.showerror("Erro", f"Valor inválido: {e}")
            return
        self.editor_passos.append((fmt_v(v), fmt_i(i), t))
        self._refresh_lista()
        self.log(f"[EDITOR] Passo manual adicionado: V={fmt_v(v)} | I={fmt_i(i)} | t={t:.3f}s")
        self.editor_visualizar()

    def editor_add_rampa(self):
        try:
            v1 = _parse_num(self.var_rmp_v1.get())
            v2 = _parse_num(self.var_rmp_v2.get())
            i = _parse_num(self.var_rmp_i.get())
            n = int(self.var_rmp_n.get().strip())
            t = _parse_num(self.var_rmp_t.get())
            if n < 1:
                raise ValueError("Nº de passos deve ser ≥ 1.")
            if t <= 0:
                raise ValueError("Tempo por passo deve ser > 0.")
        except Exception as e:
            messagebox.showerror("Erro", f"Valor inválido: {e}")
            return

        # Gera n valores entre v1 e v2 inclusive
        if n == 1:
            valores = [v1]
        else:
            passo_v = (v2 - v1) / (n - 1)
            valores = [v1 + k * passo_v for k in range(n)]

        for v in valores:
            self.editor_passos.append((fmt_v(v), fmt_i(i), t))
        self._refresh_lista()
        self.log(f"[EDITOR] Rampa adicionada: {v1}V→{v2}V em {n} passos, I={fmt_i(i)}, dwell={t:.3f}s/passo (+{n} passos)")
        self.editor_visualizar()

    def editor_excluir_selecionado(self):
        sel = self.tv.selection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecione um ou mais passos na lista.")
            return
        idxs = sorted({int(s) - 1 for s in sel}, reverse=True)
        for idx in idxs:
            if 0 <= idx < len(self.editor_passos):
                del self.editor_passos[idx]
        self._refresh_lista()
        self.log(f"[EDITOR] {len(idxs)} passo(s) removido(s).")
        self.editor_visualizar()

    def editor_excluir_todos(self):
        if not self.editor_passos:
            return
        if not messagebox.askyesno("Confirmar", "Remover todos os passos?"):
            return
        self.editor_passos.clear()
        self._refresh_lista()
        self.log("[EDITOR] Todos os passos removidos.")
        self.editor_visualizar()

    def editor_mover(self, delta):
        sel = self.tv.selection()
        if not sel:
            return
        # Move um item por vez (primeiro selecionado)
        idx = int(sel[0]) - 1
        novo = idx + delta
        if novo < 0 or novo >= len(self.editor_passos):
            return
        self.editor_passos[idx], self.editor_passos[novo] = \
            self.editor_passos[novo], self.editor_passos[idx]
        self._refresh_lista()
        self.tv.selection_set(str(novo + 1))
        self.editor_visualizar()

    def editor_visualizar(self):
        self._desenhar_plot(self.ax_ed, self.canvas_ed, list(self.editor_passos))

    def editor_carregar_txt(self):
        path = filedialog.askopenfilename(
            title="Carregar txt para editar",
            filetypes=[("Arquivos de texto", "*.txt"), ("Todos", "*.*")],
            initialdir=EXEMPLOS_DIR,
        )
        if not path:
            return
        cmds = Fonte.ler_arquivo_comandos(path)
        if not cmds:
            messagebox.showerror("Erro", "Não foi possível ler o arquivo.")
            return
        self.editor_passos = [(v, i, t) for _, v, i, t in cmds]
        nome = os.path.splitext(os.path.basename(path))[0]
        self.var_nome_arq.set(nome)
        self._refresh_lista()
        self.editor_visualizar()
        self.log(f"[EDITOR] Carregado para edição: {path} ({len(cmds)} passos)")

    def editor_salvar_txt(self):
        if not self.editor_passos:
            messagebox.showinfo("Aviso", "Não há passos para salvar.")
            return
        nome = self.var_nome_arq.get().strip()
        if not nome:
            messagebox.showerror("Erro", "Informe um nome para o arquivo.")
            return
        if not nome.lower().endswith(".txt"):
            nome += ".txt"

        # Sugere salvar na pasta do projeto, mas permite escolher outra
        path = filedialog.asksaveasfilename(
            title="Salvar arquivo de teste",
            defaultextension=".txt",
            initialdir=EXEMPLOS_DIR,
            initialfile=nome,
            filetypes=[("Arquivos de texto", "*.txt")],
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                for idx, (vstr, istr, t_s) in enumerate(self.editor_passos, start=1):
                    f.write(f"{idx}:{vstr}:{istr}:{fmt_t(t_s)}\n")
            self.log(f"[EDITOR] Arquivo salvo: {path} ({len(self.editor_passos)} passos)")
            messagebox.showinfo("Salvo", f"Arquivo salvo com sucesso:\n{path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar: {e}")

    # ============================================================
    # Aba Calibração
    # ============================================================
    def _build_tab_calibracao(self, parent):
        # Faixa de operação
        frm_faixa = ttk.LabelFrame(parent, text="Faixa de operação da medição")
        frm_faixa.pack(fill="x", padx=8, pady=4)

        ttk.Label(frm_faixa, text="V mín (V):").pack(side="left", padx=4, pady=4)
        self.var_cal_vmin = tk.StringVar(value="0,00")
        ttk.Entry(frm_faixa, textvariable=self.var_cal_vmin, width=10).pack(side="left", padx=4)

        ttk.Label(frm_faixa, text="V máx (V):").pack(side="left", padx=4)
        self.var_cal_vmax = tk.StringVar(value="30,00")
        ttk.Entry(frm_faixa, textvariable=self.var_cal_vmax, width=10).pack(side="left", padx=4)

        # Aplicar calibração na execução
        self.var_cal_ativo = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm_faixa, text="Usar calibração na execução",
                        variable=self.var_cal_ativo).pack(side="left", padx=20)

        # Entrada de pontos
        frm_in = ttk.LabelFrame(parent, text="Adicionar ponto de calibração")
        frm_in.pack(fill="x", padx=8, pady=4)

        # Linha 1: entrada manual
        row1 = ttk.Frame(frm_in)
        row1.pack(fill="x", padx=4, pady=2)
        ttk.Label(row1, text="V_set (V):").pack(side="left", padx=4)
        self.var_cal_vset = tk.StringVar(value="0,00")
        ttk.Entry(row1, textvariable=self.var_cal_vset, width=10).pack(side="left", padx=4)

        ttk.Label(row1, text="V_medido (V):").pack(side="left", padx=4)
        self.var_cal_vmed = tk.StringVar()
        ttk.Entry(row1, textvariable=self.var_cal_vmed, width=10).pack(side="left", padx=4)

        ttk.Label(row1, text="I_medido (A):").pack(side="left", padx=4)
        self.var_cal_imed = tk.StringVar()
        ttk.Entry(row1, textvariable=self.var_cal_imed, width=10).pack(side="left", padx=4)

        ttk.Button(row1, text="Adicionar ponto", command=self.cal_add_ponto)\
            .pack(side="left", padx=8)

        # Linha 2: auxiliar com fonte
        row2 = ttk.Frame(frm_in)
        row2.pack(fill="x", padx=4, pady=2)
        ttk.Label(row2, text="Auxiliar:").pack(side="left", padx=4)
        ttk.Button(row2, text="Aplicar V_set à fonte",
                   command=self.cal_aplicar_vset).pack(side="left", padx=4)
        ttk.Button(row2, text="Desligar saída",
                   command=self.desligar_saida).pack(side="left", padx=4)
        ttk.Label(row2, text="(meça V/I na carga e clique \"Adicionar ponto\")",
                  foreground="gray").pack(side="left", padx=4)

        # Tabela + gráfico
        mid = ttk.Frame(parent)
        mid.pack(fill="both", expand=True, padx=8, pady=4)

        frm_lst = ttk.LabelFrame(mid, text="Pontos registrados")
        frm_lst.pack(side="left", fill="both", expand=True, padx=(0, 4))

        cols = ("n", "vset", "vmed", "imed", "erro")
        self.tv_cal = ttk.Treeview(frm_lst, columns=cols, show="headings", height=10)
        self.tv_cal.heading("n", text="#"); self.tv_cal.column("n", width=40, anchor="center")
        self.tv_cal.heading("vset", text="V_set (V)"); self.tv_cal.column("vset", width=85, anchor="center")
        self.tv_cal.heading("vmed", text="V_medido (V)"); self.tv_cal.column("vmed", width=95, anchor="center")
        self.tv_cal.heading("imed", text="I_medido (A)"); self.tv_cal.column("imed", width=95, anchor="center")
        self.tv_cal.heading("erro", text="Erro (V)"); self.tv_cal.column("erro", width=80, anchor="center")
        self.tv_cal.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        sb_cal = ttk.Scrollbar(frm_lst, orient="vertical", command=self.tv_cal.yview)
        sb_cal.pack(side="right", fill="y")
        self.tv_cal.config(yscrollcommand=sb_cal.set)

        frm_btns = ttk.Frame(mid)
        frm_btns.pack(side="left", fill="y", padx=(0, 4))
        ttk.Button(frm_btns, text="Excluir selecionado", command=self.cal_excluir).pack(fill="x", pady=2)
        ttk.Button(frm_btns, text="Excluir todos", command=self.cal_limpar).pack(fill="x", pady=2)
        ttk.Separator(frm_btns, orient="horizontal").pack(fill="x", pady=6)
        ttk.Button(frm_btns, text="Calcular ajuste", command=self.cal_calcular).pack(fill="x", pady=2)

        # Gráfico
        frm_pv = ttk.LabelFrame(mid, text="Curva V_medido x V_set")
        frm_pv.pack(side="left", fill="both", expand=True, padx=(4, 0))

        self.fig_cal = Figure(figsize=(5, 3.0), dpi=100)
        self.ax_cal = self.fig_cal.add_subplot(111)
        self.ax_cal.set_xlabel("V_set (V)")
        self.ax_cal.set_ylabel("V_medido (V)")
        self.ax_cal.grid(True)
        self.canvas_cal = FigureCanvasTkAgg(self.fig_cal, master=frm_pv)
        self.canvas_cal.get_tk_widget().pack(fill="both", expand=True)

        # Status do ajuste + salvar/carregar
        bot = ttk.LabelFrame(parent, text="Ajuste linear (V_medido = a · V_set + b)")
        bot.pack(fill="x", padx=8, pady=4)

        self.lbl_cal_ajuste = ttk.Label(bot, text="a = —    b = —    R² = —", foreground="gray")
        self.lbl_cal_ajuste.pack(side="left", padx=8, pady=4)

        ttk.Separator(bot, orient="vertical").pack(side="left", fill="y", padx=8, pady=4)
        ttk.Button(bot, text="Carregar calibração...", command=self.cal_carregar).pack(side="left", padx=4)
        ttk.Button(bot, text="Salvar calibração...", command=self.cal_salvar).pack(side="left", padx=4)

    # ---------------- Ações da calibração ----------------
    def _cal_faixa(self):
        try:
            vmin = _parse_num(self.var_cal_vmin.get())
            vmax = _parse_num(self.var_cal_vmax.get())
            if vmax <= vmin:
                raise ValueError("V máx deve ser > V mín.")
            return vmin, vmax
        except Exception as e:
            raise ValueError(f"Faixa inválida: {e}")

    def _refresh_lista_cal(self):
        for iid in self.tv_cal.get_children():
            self.tv_cal.delete(iid)
        for idx, (vs, vm, im) in enumerate(self.cal_pontos, start=1):
            erro = vm - vs
            self.tv_cal.insert("", "end", iid=str(idx),
                               values=(idx,
                                       f"{vs:.3f}".replace(".", ","),
                                       f"{vm:.3f}".replace(".", ","),
                                       f"{im:.3f}".replace(".", ","),
                                       f"{erro:+.3f}".replace(".", ",")))
        self._desenhar_cal()

    def cal_add_ponto(self):
        try:
            vs = _parse_num(self.var_cal_vset.get())
            vm = _parse_num(self.var_cal_vmed.get())
            im = _parse_num(self.var_cal_imed.get())
        except Exception as e:
            messagebox.showerror("Erro", f"Valor inválido: {e}")
            return
        try:
            vmin, vmax = self._cal_faixa()
        except ValueError as e:
            messagebox.showerror("Erro", str(e))
            return
        if not (vmin <= vs <= vmax):
            if not messagebox.askyesno("Fora da faixa",
                                       f"V_set={vs} está fora da faixa [{vmin}, {vmax}]. Adicionar mesmo assim?"):
                return
        self.cal_pontos.append((vs, vm, im))
        self.cal_pontos.sort(key=lambda p: p[0])
        self._refresh_lista_cal()
        self.cal_calcular(silent=True)
        self.log(f"[CAL] Ponto adicionado: V_set={vs} V_medido={vm} I_medido={im}")
        # Limpa apenas os campos medidos para acelerar a próxima entrada
        self.var_cal_vmed.set("")
        self.var_cal_imed.set("")

    def cal_aplicar_vset(self):
        if not self.fonte or not self.fonte.serial or not self.fonte.serial.is_open:
            messagebox.showerror("Erro", "Conecte-se à fonte primeiro (aba Executar teste).")
            return
        try:
            vs = _parse_num(self.var_cal_vset.get())
        except Exception as e:
            messagebox.showerror("Erro", f"V_set inválido: {e}")
            return
        self.fonte.enviar_comando("OUTPUT1\\n")
        self.fonte.setar_tensao(fmt_v(vs))
        self.log(f"[CAL] V_set={fmt_v(vs)} aplicado à fonte. Meça V e I na carga e registre.")

    def cal_excluir(self):
        sel = self.tv_cal.selection()
        if not sel:
            messagebox.showinfo("Aviso", "Selecione um ponto na tabela.")
            return
        idxs = sorted({int(s) - 1 for s in sel}, reverse=True)
        for idx in idxs:
            if 0 <= idx < len(self.cal_pontos):
                del self.cal_pontos[idx]
        self._refresh_lista_cal()
        self.cal_calcular(silent=True)
        self.log(f"[CAL] {len(idxs)} ponto(s) removido(s).")

    def cal_limpar(self):
        if not self.cal_pontos:
            return
        if not messagebox.askyesno("Confirmar", "Remover todos os pontos de calibração?"):
            return
        self.cal_pontos.clear()
        self.cal_coef = None
        self.cal_r2 = None
        self.lbl_cal_ajuste.config(text="a = —    b = —    R² = —", foreground="gray")
        self._refresh_lista_cal()
        self.log("[CAL] Todos os pontos removidos.")

    def cal_calcular(self, silent=False):
        if len(self.cal_pontos) < 2:
            if not silent:
                messagebox.showinfo("Aviso", "É necessário pelo menos 2 pontos para o ajuste linear.")
            self.cal_coef = None
            self.cal_r2 = None
            self.lbl_cal_ajuste.config(text="a = —    b = —    R² = —", foreground="gray")
            self._desenhar_cal()
            return
        xs = np.array([p[0] for p in self.cal_pontos], dtype=float)
        ys = np.array([p[1] for p in self.cal_pontos], dtype=float)
        a, b = np.polyfit(xs, ys, 1)
        y_pred = a * xs + b
        ss_res = float(np.sum((ys - y_pred) ** 2))
        ss_tot = float(np.sum((ys - ys.mean()) ** 2))
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
        self.cal_coef = (float(a), float(b))
        self.cal_r2 = r2
        self.lbl_cal_ajuste.config(
            text=f"a = {a:.6f}    b = {b:+.6f}    R² = {r2:.6f}",
            foreground="black",
        )
        self._desenhar_cal()
        if not silent:
            self.log(f"[CAL] Ajuste: V_medido = {a:.6f}·V_set + {b:+.6f}   (R²={r2:.6f}, n={len(self.cal_pontos)})")

    def _desenhar_cal(self):
        self.ax_cal.clear()
        self.ax_cal.set_xlabel("V_set (V)")
        self.ax_cal.set_ylabel("V_medido (V)")
        self.ax_cal.grid(True)
        if self.cal_pontos:
            xs = [p[0] for p in self.cal_pontos]
            ys = [p[1] for p in self.cal_pontos]
            self.ax_cal.scatter(xs, ys, color="tab:blue", label="Pontos", zorder=3)
            try:
                vmin, vmax = self._cal_faixa()
            except ValueError:
                vmin, vmax = min(xs), max(xs)
            # Linha ideal y = x
            self.ax_cal.plot([vmin, vmax], [vmin, vmax], color="gray",
                             linestyle="--", linewidth=1, label="Ideal (y=x)")
            # Reta ajustada
            if self.cal_coef is not None:
                a, b = self.cal_coef
                self.ax_cal.plot([vmin, vmax],
                                 [a * vmin + b, a * vmax + b],
                                 color="tab:red", label=f"Ajuste (a={a:.4f}, b={b:+.4f})")
            self.ax_cal.legend(loc="best", fontsize=8)
        self.fig_cal.tight_layout()
        self.canvas_cal.draw()

    def cal_compensar(self, v_target):
        """Recebe V alvo (float) e retorna V_set compensado (float).
        Se calibração inativa ou não calculada, retorna o próprio v_target.
        """
        if not self.var_cal_ativo.get() or self.cal_coef is None:
            return v_target
        a, b = self.cal_coef
        if a == 0:
            return v_target
        v_set = (v_target - b) / a
        try:
            vmin, vmax = self._cal_faixa()
            v_set = max(vmin, min(vmax, v_set))
        except ValueError:
            pass
        return v_set

    def cal_salvar(self):
        if not self.cal_pontos:
            messagebox.showinfo("Aviso", "Não há pontos para salvar.")
            return
        try:
            vmin, vmax = self._cal_faixa()
        except ValueError as e:
            messagebox.showerror("Erro", str(e))
            return
        path = filedialog.asksaveasfilename(
            title="Salvar calibração",
            defaultextension=".json",
            initialdir=EXEMPLOS_DIR,
            initialfile="calibracao.json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        data = {
            "v_min": vmin,
            "v_max": vmax,
            "pontos": [{"v_set": vs, "v_medido": vm, "i_medido": im}
                       for vs, vm, im in self.cal_pontos],
            "ajuste_linear": (
                {"a": self.cal_coef[0], "b": self.cal_coef[1], "r2": self.cal_r2}
                if self.cal_coef is not None else None
            ),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log(f"[CAL] Calibração salva: {path}")
            messagebox.showinfo("Salvo", f"Calibração salva em:\n{path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar: {e}")

    def cal_carregar(self):
        path = filedialog.askopenfilename(
            title="Carregar calibração",
            initialdir=EXEMPLOS_DIR,
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.var_cal_vmin.set(f"{data.get('v_min', 0.0)}".replace(".", ","))
            self.var_cal_vmax.set(f"{data.get('v_max', 30.0)}".replace(".", ","))
            self.cal_pontos = [(p["v_set"], p["v_medido"], p["i_medido"])
                               for p in data.get("pontos", [])]
            self.cal_pontos.sort(key=lambda p: p[0])
            self._refresh_lista_cal()
            self.cal_calcular(silent=True)
            self.log(f"[CAL] Calibração carregada: {path} ({len(self.cal_pontos)} pontos)")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao carregar: {e}")

    # ============================================================
    # Menu e diálogo Sobre
    # ============================================================
    def _build_menubar(self):
        menubar = tk.Menu(self.root)

        menu_ajuda = tk.Menu(menubar, tearoff=0)
        menu_ajuda.add_command(label="Sobre...", command=self.mostrar_sobre)
        menubar.add_cascade(label="Ajuda", menu=menu_ajuda)

        self.root.config(menu=menubar)

    def mostrar_sobre(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Sobre — {APP_NOME}")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=APP_NOME, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frm, text=f"Versão {APP_VERSAO}").pack(anchor="w", pady=(0, 8))

        ttk.Label(frm, text="Automação e calibração da fonte de tensão AFR FA3005P.",
                  wraplength=380, justify="left").pack(anchor="w", pady=(0, 12))

        # Autor
        ttk.Label(frm, text="Autor:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(frm, text=APP_AUTOR).pack(anchor="w", padx=8)

        # E-mail (clicável)
        ttk.Label(frm, text="Contato:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))
        lbl_email = tk.Label(frm, text=APP_EMAIL, fg="blue", cursor="hand2")
        lbl_email.pack(anchor="w", padx=8)
        f_email = lbl_email.cget("font")
        lbl_email.configure(font=(f_email, 9, "underline") if isinstance(f_email, str) else f_email)
        lbl_email.bind("<Button-1>", lambda _: webbrowser.open(f"mailto:{APP_EMAIL}"))

        # GitHub (clicável)
        ttk.Label(frm, text="Repositório:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))
        lbl_gh = tk.Label(frm, text=APP_GITHUB, fg="blue", cursor="hand2")
        lbl_gh.pack(anchor="w", padx=8)
        f_gh = lbl_gh.cget("font")
        lbl_gh.configure(font=(f_gh, 9, "underline") if isinstance(f_gh, str) else f_gh)
        lbl_gh.bind("<Button-1>", lambda _: webbrowser.open(APP_GITHUB))

        ttk.Label(frm, text="Licença: MIT", foreground="gray").pack(anchor="w", pady=(12, 8))

        ttk.Button(frm, text="Fechar", command=dlg.destroy).pack(anchor="e", pady=(8, 0))

        # Centraliza em relação à janela principal
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    # ============================================================
    # Janela
    # ============================================================
    def on_close(self):
        try:
            self.parar_flag.set()
            self.desconectar()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = FonteGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
