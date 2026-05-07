# Controle Fonte AFR FA3005P

Automação da fonte de tensão programável **AFR FA3005P** (família Korad/KA3005P) via porta serial. Inclui uma biblioteca em Python para controle programático e uma interface gráfica (Tkinter) com editor de forma de onda.

## Funcionalidades

- Comunicação serial com a fonte (ajuste de tensão, corrente, leitura de status, liga/desliga saída).
- Execução de sequências de teste a partir de arquivos `.txt` em formato simples.
- Repetição em ciclos com intervalo configurável.
- **Interface gráfica** com:
  - Listagem de dispositivos seriais e seleção de baudrate.
  - Carregamento de arquivos de teste e visualização da forma de onda.
  - Execução / parada do teste em thread separada (não trava a UI).
  - Botões manuais para ligar/desligar a saída (`OUTPUT1` / `OUTPUT0`).
  - **Editor de forma de onda**: monta o `.txt` passo a passo ou em rampas (V₁ → V₂, N passos), com preview em tempo real, edição da lista (excluir, reordenar) e salvamento.

## Requisitos

- Python 3.8+
- Tkinter (já incluso no Python padrão no Windows)
- Pacotes em [requirements.txt](requirements.txt): `pyserial`, `matplotlib`

```bash
pip install -r requirements.txt
```

## Estrutura do projeto

```
.
├── src/
│   ├── control_fonte.py      # Biblioteca de controle da fonte
│   └── interface/
│       └── gui_fonte.py      # Interface gráfica (Tkinter)
├── exemplos/                 # Arquivos .txt de teste
│   ├── comandos.txt
│   ├── comandos_AT.txt       # Referência do protocolo serial
│   └── rampa_0a8V_1Vs.txt    # Rampa 0→8 V→0 V, passos de 1 V/s
├── tests/                    # Testes (placeholder)
├── docs/                     # Documentação adicional (placeholder)
├── requirements.txt
├── LICENSE
└── README.md
```

## Uso

### Interface gráfica (recomendado)

A partir da raiz do projeto:

```bash
python src/interface/gui_fonte.py
```

1. Aba **Executar teste**:
   - Selecione a porta serial (use "Atualizar dispositivos" para listar) e o baudrate (default `9600`).
   - "Verificar / Conectar" abre a porta e consulta `VSET1?`, `ISET1?`, `STATUS?`.
   - "Selecionar .txt" carrega um arquivo da pasta `exemplos/` (ou outro local).
   - Defina o número de ciclos e use **Executar** / **Parar**.
   - Botões **Ligar saída** / **Desligar saída** controlam `OUTPUT1` / `OUTPUT0` manualmente.
2. Aba **Editor de forma de onda**:
   - Adicione passos manualmente (V, I, t) ou via rampa (V₁, V₂, corrente, nº de passos, tempo por passo).
   - Edite a lista (excluir, mover, limpar) e visualize o preview.
   - Carregue um `.txt` existente para editar e salvar como novo.
   - Informe o nome do arquivo e clique em **Salvar como TXT**.

### Linha de comando

O `control_fonte.py` traz um exemplo no `__main__` que executa o arquivo `exemplos/comandos.txt`:

```bash
python src/control_fonte.py
```

Ajuste `porta` no script conforme necessário.

### Uso programático

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from control_fonte import Fonte

fonte = Fonte(porta_serial="COM3", baudrate=9600)
comandos = Fonte.ler_arquivo_comandos("exemplos/rampa_0a8V_1Vs.txt")
fonte.repeat(ciclos=1, intervalo=0, cmd=comandos)
fonte.fechar()
```

## Formato do arquivo de teste

Cada linha descreve um passo:

```
{numero}:{tensao}:{corrente}:{tempo}{unidade}
```

- **numero**: índice do passo (inteiro, sequencial)
- **tensao**: em volts, com vírgula decimal — recomenda-se `XX,XX` (ex.: `08,00`)
- **corrente**: em ampères, com vírgula decimal — recomenda-se `X,XXX` (ex.: `1,000`)
- **tempo**: valor numérico com vírgula decimal seguido de unidade `ms`, `s` ou `h`

Exemplo (rampa 0→8 V em passos de 1 V/s, corrente limitada a 1 A):

```
1:00,00:1,000:1,000s
2:01,00:1,000:1,000s
3:02,00:1,000:1,000s
...
9:08,00:1,000:1,000s
```

## Protocolo serial

A fonte aceita comandos no estilo Korad (quebra de linha como terminador). Comandos principais usados:

| Comando        | Descrição                          |
|----------------|------------------------------------|
| `VSET1:XX,XX`  | Define tensão de saída             |
| `ISET1:X,XXX`  | Define limite de corrente          |
| `VSET1?`       | Lê tensão programada               |
| `ISET1?`       | Lê corrente programada             |
| `STATUS?`      | Lê status da fonte                 |
| `OUTPUT1`      | Liga a saída                       |
| `OUTPUT0`      | Desliga a saída                    |

Veja [exemplos/comandos_AT.txt](exemplos/comandos_AT.txt) para uma sessão de referência.

## Licença

[MIT](LICENSE)
