import re
import time
import serial
import matplotlib.pyplot as plt


class Fonte:
    def __init__(self, porta_serial, baudrate=9600, timeout=1):
        try:
            self.serial = serial.Serial(
                port=porta_serial,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout
            )
            if not self.serial.is_open:
                self.serial.open()
            print(f"[INFO] Conectado com sucesso à porta {porta_serial}")
        except serial.SerialException as e:
            print(f"[ERRO] Falha ao abrir a porta serial '{porta_serial}': {e}")
            self.serial = None
        except Exception as e:
            print(f"[ERRO] Erro inesperado ao inicializar a comunicação serial: {e}")
            self.serial = None

    def fechar(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("[INFO] Conexão serial encerrada.")

    def enviar_comando(self, comando):
        if not self.serial or not self.serial.is_open:
            print("[ERRO] Porta serial não está aberta.")
            return
        #if not comando.endswith('\n'):
        #    comando += '\n'
        try:
            self.serial.reset_input_buffer()
            self.serial.write(comando.encode('utf-8'))
            time.sleep(0.1)
            print(f"comando enviado :{comando.encode('utf-8')}")
        except Exception as e:
            print(f"[ERRO] Falha ao enviar comando '{comando.strip()}': {e}")

    def setar_tensao(self, valor_str):
        self.enviar_comando(f"VSET1:{valor_str}\\n")

    def setar_corrente(self, valor_str):
        self.enviar_comando(f"ISET1:{valor_str}\\n")

    def _enviar_e_receber(self, comando):
        if not self.serial or not self.serial.is_open:
            print("[ERRO] Porta serial não está aberta.")
            return None
        try:
            #if not comando.endswith('\n'):
            #    comando += '\n'
            self.serial.write(comando.encode('utf-8'))
            time.sleep(0.1)
            if self.serial.in_waiting:
                resposta = self.serial.readline().decode('utf-8').strip()
                return resposta
            else:
                return None
        except Exception as e:
            print(f"[ERRO] Falha na comunicação com o comando '{comando.strip()}': {e}")
            return None

    def ler_status(self):
        return self._enviar_e_receber("STATUS?\\n")

    def ler_iset(self):
        return self._enviar_e_receber("ISET1?\\n")

    def ler_vset(self):
        return self._enviar_e_receber("VSET1?\\n")

    @staticmethod
    def _converter_tempo_para_segundos(tempo_str):
        match = re.match(r'(\d+,\d+)(ms|s|h)', tempo_str)
        if not match:
            raise ValueError(f"Formato de tempo inválido: {tempo_str}")
        valor_str, unidade = match.groups()
        valor = float(valor_str.replace(',', '.'))

        if unidade == 'ms':
            return round(valor / 1000, 3)
        elif unidade == 's':
            return round(valor, 3)
        elif unidade == 'h':
            return round(valor * 3600, 3)

    @staticmethod
    def ler_arquivo_comandos(nome_arquivo):
        comandos = []
        try:
            with open(nome_arquivo, 'r', encoding='utf-8') as f:
                for linha in f:
                    linha = linha.strip()
                    if not linha:
                        continue
                    partes = linha.split(':')
                    if len(partes) != 4:
                        raise ValueError(f"Linha mal formatada: {linha}")
                    passo = int(partes[0])
                    tensao = partes[1]
                    corrente = partes[2]
                    tempo_s = Fonte._converter_tempo_para_segundos(partes[3])
                    comandos.append((passo, tensao, corrente, tempo_s))
        except FileNotFoundError:
            print(f"[ERRO] Arquivo '{nome_arquivo}' não encontrado.")
        except Exception as e:
            print(f"[ERRO] Falha ao ler o arquivo '{nome_arquivo}': {e}")
        return comandos

    def executar_sequencia(self, comandos):
        for passo, tensao_str, corrente_str, tempo_s in comandos:
            print(f"[INFO] Passo {passo}: V={tensao_str}V | I={corrente_str}mA | Tempo={tempo_s}s")
            self.setar_tensao(tensao_str)
            self.setar_corrente(corrente_str)
            time.sleep(tempo_s)

    @staticmethod
    def plotar_comandos(comandos):
        tempos_acumulados = []
        tensoes = []
        correntes = []

        tempo_total = 0
        for _, tensao_str, corrente_str, tempo_s in comandos:
            tensao_f = float(tensao_str.replace(',', '.'))
            corrente_f = float(corrente_str.replace(',', '.'))

            tempos_acumulados.append(round(tempo_total, 3))
            tempo_total += tempo_s

            tensoes.append(tensao_f)
            correntes.append(corrente_f)

        plt.figure()
        plt.plot(tempos_acumulados, tensoes, label='Tensão (V)', marker='o')
        plt.plot(tempos_acumulados, correntes, label='Corrente (A)', marker='s')
        plt.xlabel('Tempo acumulado (s)')
        plt.ylabel('Valor')
        plt.title('Tensão e Corrente vs Tempo')
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.show()
    
    def repeat(self,ciclos, intervalo,cmd):
        i=0
        time.sleep(2)
        self.enviar_comando("ISET1?\\n")  # Ativa a saída da fonte
        time.sleep(2)
        self.enviar_comando("OUTPUT1\\n")  # Ativa a saída da fonte
        time.sleep(2)
        while(i<=ciclos):  
            print(f"Ciclo: {i+1}")  
            self.executar_sequencia(cmd)
            i=i+1
            if i > 0 and i % 50 == 0:
                time.sleep(intervalo) 
        self.enviar_comando("OUTPUT1\\n")  



if __name__ == "__main__":
    caminho_arquivo = 'comandos.txt'
    porta = 'COM3'  # Altere para a porta correta do seu dispositivo

    fonte = Fonte(porta_serial=porta)

    comandos = Fonte.ler_arquivo_comandos(caminho_arquivo)

    if comandos:
        
         fonte.repeat(600,300,comandos)
        #Fonte.plotar_comandos(comandos)

    fonte.fechar()
